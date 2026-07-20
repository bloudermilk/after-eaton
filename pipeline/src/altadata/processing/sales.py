"""Match RentCast sales + listings to parcels and overlay them onto results.

RentCast is fetched for the whole burn area (see ``sources.rentcast``); this
module joins those records back to DINS parcels by AIN — the parcel's assessor
number, matched from RentCast's ``assessorID`` (APN) first, then by
point-in-polygon on the record's ``latitude``/``longitude`` and accepted only
when the parcel's street number matches (which rejects wrong-parcel hits and
disambiguates overlapping / multi-address DINS polygons such as shared condo
parcels) — and overlays the post-fire sale / active-listing fields onto each
``ParcelResult``.

The post-fire sold set is an *accumulator*: each pipeline run fetches only a
short recent window and upserts it into a persistent cache (``rentcast-cache.json``),
so the full set of sales since the fire survives across runs without re-fetching
everything. Active listings are a full snapshot, replaced each run. The cache
also provides resilience — on a fetch failure the CLI reuses the last-good cache.

RentCast is a *service*, not a published source (like OpenRouter): its raw API
responses are deliberately never written to a ``source-*.json`` release asset —
only the derived per-parcel fields flow into the data contract via ``ParcelResult``.
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

from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree

from ..outputs.geojson_writer import esri_to_geojson
from ..sources.schemas import DinsParcel, RentCastListing, RentCastProperty
from .owner_classifier import classify_owner
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
    """A post-fire sale matched to one parcel.

    Fields mirror RentCast's `owner` object: after a sale the current owner of
    record is the buyer, so `owner_*` here is the post-fire owner.
    """

    ain: str
    sale_date: str
    sale_price: int | None
    owner_name: str | None
    owner_type: str | None


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
    """Resolve a RentCast record back to a DINS parcel AIN.

    Two matchers, tried in order by the callers:

    - ``match_apn`` — exact, digit-normalized APN lookup (primary; sold records
      carry ``assessorID``).
    - ``match_point`` — number-gated point-in-polygon fallback (listings carry
      no APN). A single DINS polygon can contain several addressed parcels
      (overlapping geometry, shared condo parcels), so a containing polygon is
      accepted only when exactly one candidate's street number equals the
      record's; wrong-number hits and same-number ties resolve to ``None``
      rather than guessing.
    """

    by_apn: dict[str, str]
    number_by_ain: dict[str, str]
    ains: list[str]
    geoms: list[BaseGeometry]
    tree: STRtree | None

    def match_apn(self, assessor_id: str | None) -> str | None:
        """Resolve an AIN by APN / assessor digits."""
        if assessor_id:
            return self.by_apn.get(_digits(assessor_id))
        return None

    def match_point(
        self,
        longitude: float | None,
        latitude: float | None,
        number: str | None,
        *,
        ambiguous: list[str] | None = None,
    ) -> str | None:
        """Resolve an AIN by point-in-polygon, requiring the street number match.

        Returns an AIN only when exactly one parcel both contains the point and
        shares ``number``. No containing-and-number match (wrong-parcel hit)
        → ``None``. More than one (same-number units in a shared polygon) →
        ``None`` as well, but the tied candidate AINs are appended to
        ``ambiguous`` (when provided) so the caller can distinguish an
        unresolvable tie from a plain no-match.
        """
        if self.tree is None or longitude is None or latitude is None or not number:
            return None
        point = Point(longitude, latitude)
        matched = [
            self.ains[int(i)]
            for i in self.tree.query(point)
            if self.geoms[int(i)].contains(point)
            and self.number_by_ain.get(self.ains[int(i)]) == number
        ]
        if len(matched) == 1:
            return matched[0]
        if len(matched) > 1 and ambiguous is not None:
            ambiguous.extend(matched)
        return None


def build_parcels_index(parcels: list[DinsParcel]) -> ParcelsIndex:
    """Index DINS parcels by APN digits, street number, and polygon geometry."""
    by_apn: dict[str, str] = {}
    number_by_ain: dict[str, str] = {}
    ains: list[str] = []
    geoms: list[BaseGeometry] = []
    for parcel in parcels:
        ain = parcel["AIN_1"]
        by_apn[_digits(ain)] = ain
        apn = parcel.get("APN_1")
        if apn:
            by_apn.setdefault(_digits(str(apn)), ain)
        addr = parcel.get("SitusFullAddress") or parcel.get("SitusAddress")
        number = _street_number(_str_or_none(addr))
        if number:
            number_by_ain[ain] = number
        geom = _parcel_polygon(parcel)
        if geom is not None:
            ains.append(ain)
            geoms.append(geom)
    tree = STRtree(geoms) if geoms else None
    return ParcelsIndex(
        by_apn=by_apn,
        number_by_ain=number_by_ain,
        ains=ains,
        geoms=geoms,
        tree=tree,
    )


def normalize_properties(
    records: list[RentCastProperty],
    index: ParcelsIndex,
    *,
    cutoff: str = FIRE_CUTOFF,
    unmatched: list[str] | None = None,
    ambiguous: list[str] | None = None,
) -> dict[str, SaleInfo]:
    """Keep records that matched a parcel and sold strictly after ``cutoff``.

    Keyed by AIN; when several records map to one parcel the latest sale wins.
    Records that don't resolve to a parcel append an identifier to ``unmatched``,
    except point-in-polygon ties (several same-number parcels share a polygon),
    which append to ``ambiguous`` instead — both for info-level auditing.
    Pre-fire sales are excluded but not treated as unmatched.
    """
    out: dict[str, SaleInfo] = {}
    for rec in records:
        raw = dict(rec)
        outcome = _match_record(index, raw)
        if outcome.ain is None:
            _record_no_match(raw, outcome, unmatched=unmatched, ambiguous=ambiguous)
            continue
        ain = outcome.ain
        sale_date = _date_str(raw.get("lastSaleDate"))
        if sale_date is None or sale_date[:10] <= cutoff:
            continue
        owner = raw.get("owner") or {}
        names = owner.get("names") if isinstance(owner, dict) else None
        owner_name = " & ".join(str(n) for n in names) if names else None
        info = SaleInfo(
            ain=ain,
            sale_date=sale_date,
            sale_price=_int_or_none(raw.get("lastSalePrice")),
            owner_name=owner_name,
            owner_type=(owner.get("type") if isinstance(owner, dict) else None),
        )
        existing = out.get(ain)
        if existing is None or info.sale_date > existing.sale_date:
            out[ain] = info
    return out


def normalize_listings(
    records: list[RentCastListing],
    index: ParcelsIndex,
    *,
    unmatched: list[str] | None = None,
    ambiguous: list[str] | None = None,
) -> dict[str, ListingInfo]:
    """Match active sale listings to parcels, keyed by AIN (latest listing wins).

    Records that don't resolve to a parcel append an identifier to ``unmatched``,
    except point-in-polygon ties (several same-number parcels share a polygon),
    which append to ``ambiguous`` instead — both for info-level auditing.
    """
    out: dict[str, ListingInfo] = {}
    for rec in records:
        raw = dict(rec)
        outcome = _match_record(index, raw)
        if outcome.ain is None:
            _record_no_match(raw, outcome, unmatched=unmatched, ambiguous=ambiguous)
            continue
        ain = outcome.ain
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
            result.owner_name = sale.owner_name
            result.owner_type = sale.owner_type
            # Reclassify from owner_name every run (not stored on the cache), so
            # a rule change takes effect on the next run with no cache rebuild.
            result.owner_class = classify_owner(sale.owner_name)
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
            owner_name=_str_or_none(s.get("owner_name")),
            owner_type=_str_or_none(s.get("owner_type")),
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


@dataclass(frozen=True)
class MatchResult:
    """Outcome of resolving a RentCast record to a parcel.

    ``ambiguous_ains`` is non-empty only when point-in-polygon found more than
    one same-number candidate (e.g. condo units sharing a polygon) and declined
    to guess — distinct from a plain no-match, which the caller surfaces
    differently.
    """

    ain: str | None
    ambiguous_ains: tuple[str, ...] = ()


def _match_record(index: ParcelsIndex, raw: dict[str, Any]) -> MatchResult:
    """APN first, then number-gated point-in-polygon on the record's coordinates."""
    ain = index.match_apn(_str_or_none(raw.get("assessorID")))
    if ain is not None:
        return MatchResult(ain=ain)
    longitude, latitude = _coords(raw)
    number = _street_number(_str_or_none(raw.get("formattedAddress")))
    tie: list[str] = []
    ain = index.match_point(longitude, latitude, number, ambiguous=tie)
    return MatchResult(ain=ain, ambiguous_ains=tuple(tie))


def _ambiguity_label(raw: dict[str, Any], ains: tuple[str, ...]) -> str:
    """Identify an ambiguous record plus the parcels it couldn't be split between."""
    return f"{_record_label(raw)} (candidate parcels: {', '.join(ains)})"


def _record_no_match(
    raw: dict[str, Any],
    outcome: MatchResult,
    *,
    unmatched: list[str] | None,
    ambiguous: list[str] | None,
) -> None:
    """Route a failed match to the ambiguous or the plain-unmatched audit list."""
    if outcome.ambiguous_ains:
        if ambiguous is not None:
            ambiguous.append(_ambiguity_label(raw, outcome.ambiguous_ains))
    elif unmatched is not None:
        unmatched.append(_record_label(raw))


def _parcel_polygon(parcel: DinsParcel) -> BaseGeometry | None:
    """DINS parcel polygon as a shapely geometry (mirrors spatial_aggregate)."""
    geojson = esri_to_geojson(parcel.get("_geometry"))
    if not geojson:
        return None
    try:
        return shape(geojson)
    except (ValueError, TypeError):
        return None


def _street_number(addr: str | None) -> str | None:
    """Leading house number of an address ('411 PUNAHOU ST NO A' → '411')."""
    if not addr:
        return None
    match = re.match(r"\s*(\d+)", addr)
    return match.group(1) if match else None


def _coords(raw: dict[str, Any]) -> tuple[float | None, float | None]:
    """`(longitude, latitude)` from a raw RentCast record, floats or None."""
    return _float_or_none(raw.get("longitude")), _float_or_none(raw.get("latitude"))


def _record_label(raw: dict[str, Any]) -> str:
    """A human identifier for a RentCast record that didn't join to a parcel."""
    return (
        _str_or_none(raw.get("formattedAddress"))
        or _str_or_none(raw.get("assessorID"))
        or _str_or_none(raw.get("id"))
        or "<unidentified record>"
    )


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


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


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _now_iso() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
