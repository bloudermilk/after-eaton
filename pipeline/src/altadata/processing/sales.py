"""Match RentCast sales + listings to parcels and overlay them onto results.

RentCast is fetched for the whole burn area (see ``sources.rentcast``); this
module joins those records back to DINS parcels by AIN — the parcel's assessor
number, matched from RentCast's ``assessorID`` first and the street address as a
fallback — and overlays the post-fire sale / active-listing fields onto each
``ParcelResult``.

The post-fire sold set is an *accumulator*: each pipeline run fetches only a
short recent window and upserts it into a persistent cache (``rentcast-cache.json``),
so the full set of sales since the fire survives across runs without re-fetching
everything. Active listings are a full snapshot, replaced each run. The cache
also provides resilience — on a fetch failure the CLI reuses the last-good cache.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from ..sources.schemas import DinsParcel, RentCastListing, RentCastProperty
from .parcel_analysis import ParcelResult

logger = logging.getLogger(__name__)

# Sales activity is only counted strictly after the fire ignition date. Dates
# are compared lexically on their ISO `YYYY-MM-DD` prefix (ISO sorts lexically).
FIRE_CUTOFF = "2025-01-07"

# Incremental lookback (days) used between full reconciles. It is deliberately
# wide, not just the gap between runs: RentCast's `lastSaleDate` reflects the
# county recording date, which lags the close by weeks — a verification pull
# showed a 30-day window returning nothing while a since-fire window returned
# 500+. 120 days covers that ingestion lag so newly-recorded (older-dated) sales
# are still caught; the monthly full reconcile below is the backstop for the
# rest. The window is time-bounded (not cumulative), so cost stays flat as the
# post-fire sales total grows.
INCREMENTAL_SALE_DAYS = 120

# How often to fall back to a full since-fire sweep (catches anything the rolling
# incremental window missed). One page = one request, so this stays cheap.
FULL_RECONCILE_EVERY_DAYS = 30


@dataclass
class SaleInfo:
    """A post-fire sale matched to one parcel (the current owner is the buyer)."""

    ain: str
    sale_date: str
    sale_price: int | None
    buyer_name: str | None
    owner_type: str | None
    owner_occupied: bool | None


@dataclass
class ListingInfo:
    """An active sale listing matched to one parcel."""

    ain: str
    listed_date: str | None
    status: str
    price: int | None


@dataclass
class SalesCache:
    """Persistent accumulator of post-fire sales + the latest listing snapshot."""

    sold: dict[str, SaleInfo] = field(default_factory=dict)
    listings: dict[str, ListingInfo] = field(default_factory=dict)
    generated_at: str = ""
    # True once a full backfill (saleDateRange since the fire) has been done, so
    # later runs can use the cheap incremental window instead.
    backfill_done: bool = False
    # Run date (ISO day) of the last full since-fire sweep; drives the periodic
    # reconcile (see full_refresh_due).
    last_full_refresh: str = ""


@dataclass(frozen=True)
class ParcelsIndex:
    """Lookup from RentCast identifiers back to a DINS parcel AIN."""

    by_apn: dict[str, str]
    by_address: dict[str, str]

    def match(self, assessor_id: str | None, address: str | None) -> str | None:
        """Resolve an AIN by APN/assessor digits first, then street address."""
        if assessor_id:
            ain = self.by_apn.get(_digits(assessor_id))
            if ain:
                return ain
        if address:
            ain = self.by_address.get(_norm_addr(address))
            if ain:
                return ain
        return None


def build_parcels_index(parcels: list[DinsParcel]) -> ParcelsIndex:
    """Index DINS parcels by APN/AIN digits and normalized situs address."""
    by_apn: dict[str, str] = {}
    by_address: dict[str, str] = {}
    for parcel in parcels:
        ain = parcel["AIN_1"]
        by_apn[_digits(ain)] = ain
        apn = parcel.get("APN_1")
        if apn:
            by_apn.setdefault(_digits(str(apn)), ain)
        addr = parcel.get("SitusFullAddress") or parcel.get("SitusAddress")
        if addr:
            by_address.setdefault(_norm_addr(str(addr)), ain)
    return ParcelsIndex(by_apn=by_apn, by_address=by_address)


def normalize_properties(
    records: list[RentCastProperty],
    index: ParcelsIndex,
    *,
    cutoff: str = FIRE_CUTOFF,
) -> dict[str, SaleInfo]:
    """Keep records that matched a parcel and sold strictly after ``cutoff``.

    Keyed by AIN; when several records map to one parcel the latest sale wins.
    """
    out: dict[str, SaleInfo] = {}
    for rec in records:
        raw = dict(rec)
        ain = index.match(
            _str_or_none(raw.get("assessorID")),
            _str_or_none(raw.get("formattedAddress")),
        )
        if ain is None:
            continue
        sale_date = _date_str(raw.get("lastSaleDate"))
        if sale_date is None or sale_date[:10] <= cutoff:
            continue
        owner = raw.get("owner") or {}
        names = owner.get("names") if isinstance(owner, dict) else None
        buyer = " & ".join(str(n) for n in names) if names else None
        info = SaleInfo(
            ain=ain,
            sale_date=sale_date,
            sale_price=_int_or_none(raw.get("lastSalePrice")),
            buyer_name=buyer,
            owner_type=(owner.get("type") if isinstance(owner, dict) else None),
            owner_occupied=_bool_or_none(raw.get("ownerOccupied")),
        )
        existing = out.get(ain)
        if existing is None or info.sale_date > existing.sale_date:
            out[ain] = info
    return out


def normalize_listings(
    records: list[RentCastListing],
    index: ParcelsIndex,
) -> dict[str, ListingInfo]:
    """Match active sale listings to parcels, keyed by AIN (latest listing wins)."""
    out: dict[str, ListingInfo] = {}
    for rec in records:
        raw = dict(rec)
        ain = index.match(
            _str_or_none(raw.get("assessorID")),
            _str_or_none(raw.get("formattedAddress")),
        )
        if ain is None:
            continue
        info = ListingInfo(
            ain=ain,
            listed_date=_date_str(raw.get("listedDate")),
            status=str(raw.get("status") or "Active"),
            price=_int_or_none(raw.get("price")),
        )
        existing = out.get(ain)
        if existing is None or _newer_listing(info, existing):
            out[ain] = info
    return out


def apply_sales(results: list[ParcelResult], cache: SalesCache) -> None:
    """Overlay cached sale/listing data onto each parcel result in place."""
    for result in results:
        sale = cache.sold.get(result.ain)
        if sale is not None:
            result.sold_post_fire = True
            result.last_sale_date = sale.sale_date
            result.last_sale_price = sale.sale_price
            result.buyer_name = sale.buyer_name
            result.owner_type = sale.owner_type
            result.owner_occupied = sale.owner_occupied
        listing = cache.listings.get(result.ain)
        if listing is not None:
            result.active_listing = True
            result.listing_date = listing.listed_date
            result.listing_status = listing.status
            result.listing_price = listing.price


def prune_sales_cache(cache: SalesCache, valid_ains: set[str]) -> int:
    """Drop cached entries whose AIN is no longer in the parcel set."""
    stale = [ain for ain in cache.sold if ain not in valid_ains]
    stale += [ain for ain in cache.listings if ain not in valid_ains]
    for ain in set(stale):
        cache.sold.pop(ain, None)
        cache.listings.pop(ain, None)
    return len(set(stale))


def full_backfill_days(generated_at: str, *, cutoff: str = FIRE_CUTOFF) -> int:
    """Days from ``cutoff`` to the run date — the saleDateRange for a full pull."""
    run_day = date.fromisoformat(generated_at[:10])
    delta = (run_day - date.fromisoformat(cutoff)).days
    return max(delta, 1)


def full_refresh_due(
    cache: SalesCache,
    generated_at: str,
    *,
    every_days: int = FULL_RECONCILE_EVERY_DAYS,
) -> bool:
    """True when a full since-fire sweep is overdue (or never done).

    Lets the daily pipeline self-schedule the periodic reconcile without a
    separate cron: an empty/old ``last_full_refresh`` forces a full pull.
    """
    if not cache.last_full_refresh:
        return True
    run_day = date.fromisoformat(generated_at[:10])
    try:
        last = date.fromisoformat(cache.last_full_refresh[:10])
    except ValueError:
        return True
    return (run_day - last).days >= every_days


# ---------- cache persistence (mirrors llm_extraction.save_cache) ----------


def load_sales_cache(path: Path | str) -> SalesCache:
    """Load a cache written by ``save_sales_cache``. Missing/corrupt → empty."""
    p = Path(path)
    if not p.exists():
        return SalesCache()
    try:
        payload = json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        logger.error("sales cache %s is corrupt (%s) — starting empty", p, exc)
        return SalesCache()
    sold = {
        s["ain"]: SaleInfo(
            ain=str(s["ain"]),
            sale_date=str(s["sale_date"]),
            sale_price=_int_or_none(s.get("sale_price")),
            buyer_name=_str_or_none(s.get("buyer_name")),
            owner_type=_str_or_none(s.get("owner_type")),
            owner_occupied=_bool_or_none(s.get("owner_occupied")),
        )
        for s in payload.get("sold") or []
        if isinstance(s, dict) and s.get("ain") and s.get("sale_date")
    }
    listings = {
        listing["ain"]: ListingInfo(
            ain=str(listing["ain"]),
            listed_date=_str_or_none(listing.get("listed_date")),
            status=str(listing.get("status") or "Active"),
            price=_int_or_none(listing.get("price")),
        )
        for listing in payload.get("listings") or []
        if isinstance(listing, dict) and listing.get("ain")
    }
    return SalesCache(
        sold=sold,
        listings=listings,
        generated_at=str(payload.get("generated_at") or ""),
        backfill_done=bool(payload.get("backfill_done")),
        last_full_refresh=str(payload.get("last_full_refresh") or ""),
    )


def save_sales_cache(path: Path | str, cache: SalesCache) -> None:
    """Write the cache via atomic write-temp-then-rename (kill-safe)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": cache.generated_at or _now_iso(),
        "backfill_done": cache.backfill_done,
        "last_full_refresh": cache.last_full_refresh,
        "sold_count": len(cache.sold),
        "listing_count": len(cache.listings),
        "sold": [asdict(s) for s in cache.sold.values()],
        "listings": [asdict(listing) for listing in cache.listings.values()],
    }
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=False))
    os.replace(tmp, p)


# ---------- helpers ----------


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def _norm_addr(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", value.upper()).strip()


def _newer_listing(candidate: ListingInfo, existing: ListingInfo) -> bool:
    return (candidate.listed_date or "") > (existing.listed_date or "")


def _date_str(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return None


def _bool_or_none(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _now_iso() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
