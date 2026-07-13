"""Tests for the RentCast source, sales matching/normalization, cache, and the
Property Sales aggregate counts. No live calls — HTTP is mocked via pytest-httpx.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pytest_httpx import HTTPXMock

from altadata.processing.aggregate import count_parcels, property_sales_bucket
from altadata.processing.normalize import BsdStatus, DamageLevel
from altadata.processing.parcel_analysis import ParcelResult
from altadata.processing.sales import (
    ListingInfo,
    SaleInfo,
    SalesCache,
    apply_sales,
    build_parcels_index,
    full_backfill_days,
    full_refresh_due,
    load_sales_cache,
    normalize_listings,
    normalize_properties,
    prune_sales_cache,
    save_sales_cache,
)
from altadata.sources import rentcast
from altadata.sources.rentcast import (
    fetch_rentcast_properties,
    fetch_rentcast_sale_listings,
)

# --- source: query params + pagination + 404 ------------------------------


def test_fetch_properties_builds_params_and_headers(
    httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RENTCAST_API_KEY", "k")
    httpx_mock.add_response(json=[{"id": "1"}])  # short page → one request

    out = fetch_rentcast_properties(34.19, -118.13, 2.5, sale_date_range=7)

    assert out == [{"id": "1"}]
    req = httpx_mock.get_request()
    assert req is not None
    assert req.url.path == "/v1/properties"
    assert req.headers["X-Api-Key"] == "k"
    params = req.url.params
    assert params["saleDateRange"] == "7"
    assert params["latitude"] == "34.190000"
    assert params["longitude"] == "-118.130000"
    assert params["radius"] == "2.500000"
    assert params["limit"] == "500"
    assert params["offset"] == "0"


def test_fetch_sale_listings_defaults_to_active(
    httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RENTCAST_API_KEY", "k")
    httpx_mock.add_response(json=[{"id": "L1"}])

    out = fetch_rentcast_sale_listings(34.19, -118.13, 2.5)

    assert out == [{"id": "L1"}]
    req = httpx_mock.get_request()
    assert req is not None
    assert req.url.path == "/v1/listings/sale"
    assert req.url.params["status"] == "Active"


def test_fetch_paginates_until_short_page(
    httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RENTCAST_API_KEY", "k")
    monkeypatch.setattr(rentcast, "_PAGE_SIZE", 2)
    # First full page (== page size) forces a second request; the short second
    # page ends pagination.
    httpx_mock.add_response(json=[{"id": "1"}, {"id": "2"}])
    httpx_mock.add_response(json=[{"id": "3"}])

    out = fetch_rentcast_properties(34.19, -118.13, 2.5, sale_date_range=7)

    assert [r["id"] for r in out] == ["1", "2", "3"]
    reqs = httpx_mock.get_requests()
    assert len(reqs) == 2
    assert reqs[0].url.params["offset"] == "0"
    assert reqs[1].url.params["offset"] == "2"


def test_fetch_404_is_empty_not_error(
    httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    # RentCast returns 404 when a query matches no records — a normal empty
    # result for a small burn area, not a failure.
    monkeypatch.setenv("RENTCAST_API_KEY", "k")
    httpx_mock.add_response(status_code=404, json={"status": 404})

    assert fetch_rentcast_properties(34.19, -118.13, 2.5, sale_date_range=7) == []


# --- matching + normalization ---------------------------------------------


def _dins(ain: str, apn: str, address: str) -> dict[str, Any]:
    return {
        "AIN_1": ain,
        "APN_1": apn,
        "SitusFullAddress": address,
        "DAMAGE_1": "Destroyed (>50%)",
        "SQFTmain1": 1000.0,
        "DesignType1": "0101",
        "COMMUNITY": "Altadena",
    }


def test_match_by_apn_then_address() -> None:
    parcels = [
        _dins("5841009012", "5841-009-012", "411 PUNAHOU ST ALTADENA CA 91001"),
    ]
    index = build_parcels_index(parcels)  # type: ignore[arg-type]
    # Dashed APN → digits match.
    assert index.match("5841-009-012", None) == "5841009012"
    # Address with different punctuation/case still matches after normalization.
    assert index.match(None, "411 Punahou St, Altadena, CA 91001") == "5841009012"
    # No signal → no match.
    assert index.match("0000000000", "999 Nowhere Rd") is None


def test_normalize_properties_filters_pre_fire_and_carries_owner() -> None:
    parcels = [_dins("5841009012", "5841-009-012", "411 PUNAHOU ST ALTADENA CA 91001")]
    index = build_parcels_index(parcels)  # type: ignore[arg-type]
    records = [
        {
            "assessorID": "5841-009-012",
            "formattedAddress": "411 Punahou St, Altadena, CA 91001",
            "lastSaleDate": "2025-03-14T00:00:00.000Z",
            "lastSalePrice": 1250000,
            "ownerOccupied": False,
            "owner": {"names": ["ACME HOMES LLC"], "type": "Organization"},
        },
        {
            # Sold BEFORE the fire → must be excluded.
            "assessorID": "5841-009-012",
            "formattedAddress": "411 Punahou St, Altadena, CA 91001",
            "lastSaleDate": "2019-06-01",
            "lastSalePrice": 800000,
        },
        {
            # No matching parcel → dropped.
            "assessorID": "0000-000-000",
            "formattedAddress": "1 Nowhere Rd",
            "lastSaleDate": "2025-05-01",
        },
    ]
    sold = normalize_properties(records, index)  # type: ignore[arg-type]

    assert set(sold) == {"5841009012"}
    info = sold["5841009012"]
    assert info.sale_date.startswith("2025-03-14")
    assert info.sale_price == 1250000
    assert info.buyer_name == "ACME HOMES LLC"
    assert info.owner_type == "Organization"
    assert info.owner_occupied is False


def test_normalize_listings_matches_active() -> None:
    parcels = [_dins("5841009012", "5841-009-012", "411 PUNAHOU ST ALTADENA CA 91001")]
    index = build_parcels_index(parcels)  # type: ignore[arg-type]
    records = [
        {
            "formattedAddress": "411 Punahou St, Altadena, CA 91001",
            "listedDate": "2026-05-01T00:00:00.000Z",
            "status": "Active",
            "price": 999000,
        }
    ]
    listings = normalize_listings(records, index)  # type: ignore[arg-type]
    assert set(listings) == {"5841009012"}
    assert listings["5841009012"].listed_date.startswith("2026-05-01")
    assert listings["5841009012"].price == 999000


def test_apply_sales_overlays_fields() -> None:
    result = _result("5841009012", bsd_status=BsdStatus.RED)
    cache = SalesCache(
        sold={
            "5841009012": SaleInfo(
                ain="5841009012",
                sale_date="2025-03-14",
                sale_price=1250000,
                buyer_name="JANE DOE",
                owner_type="Individual",
                owner_occupied=True,
            )
        },
        listings={
            "5841009012": ListingInfo(
                ain="5841009012",
                listed_date="2026-05-01",
                status="Active",
                price=999000,
            )
        },
    )
    apply_sales([result], cache)

    assert result.sold_post_fire is True
    assert result.last_sale_date == "2025-03-14"
    assert result.buyer_name == "JANE DOE"
    assert result.owner_occupied is True
    assert result.active_listing is True
    assert result.listing_date == "2026-05-01"
    # A parcel with both sale + listing resolves to "listed" on the map.
    assert property_sales_bucket(result) == "listed"


# --- cache persistence -----------------------------------------------------


def test_sales_cache_roundtrip(tmp_path: Path) -> None:
    cache = SalesCache(
        sold={
            "a": SaleInfo("a", "2025-04-01", 500000, "BUYER A", "Individual", True),
        },
        listings={
            "b": ListingInfo("b", "2026-06-01", "Active", 750000),
        },
        generated_at="2026-07-12T00:00:00Z",
        backfill_done=True,
    )
    path = tmp_path / "rentcast-cache.json"
    save_sales_cache(path, cache)
    loaded = load_sales_cache(path)

    assert loaded.backfill_done is True
    assert loaded.sold["a"] == cache.sold["a"]
    assert loaded.listings["b"] == cache.listings["b"]


def test_load_missing_cache_is_empty(tmp_path: Path) -> None:
    loaded = load_sales_cache(tmp_path / "does-not-exist.json")
    assert loaded.sold == {} and loaded.listings == {}
    assert loaded.backfill_done is False


def test_prune_sales_cache_drops_unknown_ains() -> None:
    cache = SalesCache(
        sold={"keep": SaleInfo("keep", "2025-04-01", 1, None, None, None)},
        listings={"drop": ListingInfo("drop", "2026-01-01", "Active", 1)},
    )
    dropped = prune_sales_cache(cache, valid_ains={"keep"})
    assert dropped == 1
    assert set(cache.sold) == {"keep"}
    assert cache.listings == {}


def test_full_backfill_days_counts_from_fire() -> None:
    # 2025-01-08 is one day after the 2025-01-07 cutoff.
    assert full_backfill_days("2025-01-08T00:00:00Z") == 1
    assert full_backfill_days("2025-02-06T00:00:00Z") == 30


def test_full_refresh_due_schedules_periodic_reconcile() -> None:
    # Never reconciled → due.
    assert full_refresh_due(SalesCache(), "2026-07-12T00:00:00Z") is True
    fresh = SalesCache(last_full_refresh="2026-07-01")
    # 11 days later → not yet due (default 30-day cadence).
    assert full_refresh_due(fresh, "2026-07-12T00:00:00Z") is False
    # 30+ days later → due again.
    assert full_refresh_due(fresh, "2026-08-01T00:00:00Z") is True


# --- aggregate: counts scoped to the Destroyed/Damaged population ----------


def test_property_counts_scoped_to_damaged_population() -> None:
    parcels = [
        _result("p1", bsd_status=BsdStatus.RED, sold_post_fire=True),
        _result("p2", bsd_status=BsdStatus.YELLOW, active_listing=True),
        # GREEN parcel that sold: outside the population → not counted.
        _result("p3", bsd_status=BsdStatus.GREEN, sold_post_fire=True),
        # Both sold and listed within the population → counts in both.
        _result(
            "p4", bsd_status=BsdStatus.RED, sold_post_fire=True, active_listing=True
        ),
    ]
    counts = count_parcels(parcels)
    assert counts.property_sold_post_fire_count == 2  # p1, p4
    assert counts.property_active_listing_count == 2  # p2, p4


# --- helpers ---------------------------------------------------------------


def _result(
    ain: str,
    *,
    bsd_status: BsdStatus = BsdStatus.RED,
    sold_post_fire: bool = False,
    active_listing: bool = False,
) -> ParcelResult:
    return ParcelResult(
        ain=ain,
        apn=ain,
        address="",
        damage=DamageLevel.DESTROYED,
        bsd_status=bsd_status,
        pre_sfr_count=1,
        pre_sfr_sqft=1000,
        pre_adu_count=0,
        pre_adu_sqft=None,
        pre_mfr_count=0,
        pre_mfr_sqft=None,
        post_sfr_count=None,
        post_sfr_sqft=None,
        post_adu_count=None,
        post_adu_sqft=None,
        post_mfr_count=None,
        post_mfr_sqft=None,
        lfl_claimed=None,
        lfl_conflict=False,
        sfr_size_comparison=None,
        adds_sb9=False,
        adds_sb1123=False,
        sb_pathway_conflict=False,
        added_adu_count=0,
        rebuild_progress_num=None,
        rebuild_progress=None,
        permit_status=None,
        roe_status=None,
        debris_cleared=None,
        dins_count=1,
        sold_post_fire=sold_post_fire,
        active_listing=active_listing,
    )
