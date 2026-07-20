"""Tests for the RentCast source, sales matching/normalization, cache, and the
Property Sales aggregate counts. No live calls — HTTP is mocked via pytest-httpx.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pytest_httpx import HTTPXMock

from altadata.processing.aggregate import (
    count_parcels,
    listing_age_bucket,
    property_sales_bucket,
    sold_owner_bucket,
)
from altadata.processing.geometry import circle_from_bounds, parcels_bounding_envelope
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


# --- query circle scoped to the parcel population --------------------------


def _parcel_with_ring(ring: list[list[float]]) -> dict[str, Any]:
    return {"_geometry": {"rings": [ring]}}


def test_parcels_bounding_envelope_spans_all_parcels() -> None:
    parcels = [
        _parcel_with_ring(
            [[-118.16, 34.17], [-118.15, 34.17], [-118.15, 34.18], [-118.16, 34.18]]
        ),
        _parcel_with_ring(
            [[-118.10, 34.20], [-118.09, 34.20], [-118.09, 34.21], [-118.10, 34.21]]
        ),
    ]
    env = parcels_bounding_envelope(parcels)  # type: ignore[arg-type]
    assert tuple(round(v, 2) for v in env) == (-118.16, 34.17, -118.09, 34.21)

    # The covering circle centers on the box and reaches every corner.
    lat, lon, radius = circle_from_bounds(env)
    assert (round(lat, 3), round(lon, 3)) == (34.19, -118.125)
    assert radius > 0


def test_parcels_bounding_envelope_raises_without_geometry() -> None:
    with pytest.raises(ValueError):
        parcels_bounding_envelope([{"AIN_1": "x"}])  # type: ignore[arg-type,list-item]


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


def _square(lon: float, lat: float, half: float = 0.0005) -> list[list[float]]:
    """A small closed square ring (Esri order) centered on `(lon, lat)`."""
    return [
        [lon - half, lat - half],
        [lon + half, lat - half],
        [lon + half, lat + half],
        [lon - half, lat + half],
        [lon - half, lat - half],
    ]


def _dins_geo(
    ain: str, apn: str, address: str, center: tuple[float, float]
) -> dict[str, Any]:
    """A DINS parcel with a square polygon around `center` for point matching."""
    parcel = _dins(ain, apn, address)
    parcel["_geometry"] = {"rings": [_square(*center)]}
    return parcel


def test_match_by_apn_then_point() -> None:
    center = (-118.13, 34.19)
    parcels = [
        _dins_geo(
            "5841009012", "5841-009-012", "411 PUNAHOU ST ALTADENA CA 91001", center
        )
    ]
    index = build_parcels_index(parcels)  # type: ignore[arg-type]
    # Dashed APN → digits match (primary path, no geometry needed).
    assert index.match_apn("5841-009-012") == "5841009012"
    assert index.match_apn(None) is None
    assert index.match_apn("0000000000") is None
    # Point inside the parcel WITH a matching street number → match.
    assert index.match_point(-118.13, 34.19, "411") == "5841009012"
    # Point outside every parcel → no match.
    assert index.match_point(-117.0, 34.0, "411") is None
    # Inside the parcel but the street number differs → rejected (false-positive guard).
    assert index.match_point(-118.13, 34.19, "999") is None
    # Inside but no number to check against → cannot satisfy the requirement.
    assert index.match_point(-118.13, 34.19, None) is None


def test_match_point_disambiguates_overlapping_parcels() -> None:
    # Two parcels share one polygon (real DINS condo case) but have different
    # street numbers; the number component selects the right AIN.
    center = (-118.13, 34.19)
    parcels = [
        _dins_geo("5751021042", "5751-021-042", "1501 CREEKSIDE CT NO A", center),
        _dins_geo("5751021044", "5751-021-044", "1503 CREEKSIDE CT NO A", center),
    ]
    index = build_parcels_index(parcels)  # type: ignore[arg-type]
    assert index.match_point(-118.13, 34.19, "1501") == "5751021042"
    assert index.match_point(-118.13, 34.19, "1503") == "5751021044"
    # A number neither parcel carries → no match.
    assert index.match_point(-118.13, 34.19, "1502") is None


def test_match_point_ambiguous_same_number_returns_none() -> None:
    # Condo units A/B sharing a polygon share the street number → unresolvable.
    center = (-118.13, 34.19)
    parcels = [
        _dins_geo("5751021042", "5751-021-042", "1501 CREEKSIDE CT NO A", center),
        _dins_geo("5751021043", "5751-021-043", "1501 CREEKSIDE CT NO B", center),
    ]
    index = build_parcels_index(parcels)  # type: ignore[arg-type]
    assert index.match_point(-118.13, 34.19, "1501") is None


def test_normalize_properties_filters_pre_fire_and_carries_owner() -> None:
    parcels = [_dins("5841009012", "5841-009-012", "411 PUNAHOU ST ALTADENA CA 91001")]
    index = build_parcels_index(parcels)  # type: ignore[arg-type]
    records = [
        {
            "assessorID": "5841-009-012",
            "formattedAddress": "411 Punahou St, Altadena, CA 91001",
            "lastSaleDate": "2025-03-14T00:00:00.000Z",
            "lastSalePrice": 1250000,
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
    assert info.owner_name == "ACME HOMES LLC"
    assert info.owner_type == "Organization"


def test_normalize_properties_reports_unmatched() -> None:
    # A matched post-fire sale, a matched PRE-fire sale (excluded but NOT
    # unmatched), and a genuine non-match (appended to unmatched).
    parcels = [_dins("5841009012", "5841-009-012", "411 PUNAHOU ST ALTADENA CA 91001")]
    index = build_parcels_index(parcels)  # type: ignore[arg-type]
    records = [
        {
            "assessorID": "5841-009-012",
            "formattedAddress": "411 Punahou St, Altadena, CA 91001",
            "lastSaleDate": "2025-03-14",
        },
        {  # matches a parcel but sold before the fire → excluded, not unmatched
            "assessorID": "5841-009-012",
            "formattedAddress": "411 Punahou St, Altadena, CA 91001",
            "lastSaleDate": "2019-06-01",
        },
        {"assessorID": "0000-000-000", "formattedAddress": "1 Nowhere Rd"},
    ]
    unmatched: list[str] = []
    sold = normalize_properties(records, index, unmatched=unmatched)  # type: ignore[arg-type]
    assert set(sold) == {"5841009012"}
    assert unmatched == ["1 Nowhere Rd"]


def test_normalize_listings_reports_unmatched() -> None:
    parcels = [_dins("5841009012", "5841-009-012", "411 PUNAHOU ST ALTADENA CA 91001")]
    index = build_parcels_index(parcels)  # type: ignore[arg-type]
    records = [
        {"formattedAddress": "1 Nowhere Rd", "status": "Active"},
        # No address and no assessorID match → labeled by assessorID.
        {"assessorID": "9999-999-999", "status": "Active"},
    ]
    unmatched: list[str] = []
    listings = normalize_listings(records, index, unmatched=unmatched)  # type: ignore[arg-type]
    assert listings == {}
    assert unmatched == ["1 Nowhere Rd", "9999-999-999"]


def test_normalize_listings_matches_active() -> None:
    # Listings carry no assessorID → matched by point-in-polygon on lat/long,
    # gated on the street number.
    parcels = [
        _dins_geo(
            "5841009012",
            "5841-009-012",
            "411 PUNAHOU ST ALTADENA CA 91001",
            (-118.13, 34.19),
        )
    ]
    index = build_parcels_index(parcels)  # type: ignore[arg-type]
    records = [
        {
            "formattedAddress": "411 Punahou St, Altadena, CA 91001",
            "latitude": 34.19,
            "longitude": -118.13,
            "listedDate": "2026-05-01T00:00:00.000Z",
            "status": "Active",
            "price": 999000,
        }
    ]
    listings = normalize_listings(records, index)  # type: ignore[arg-type]
    assert set(listings) == {"5841009012"}
    assert listings["5841009012"].listed_date.startswith("2026-05-01")
    assert listings["5841009012"].price == 999000


def test_normalize_listings_wrong_number_is_unmatched() -> None:
    # Geocoded point lands inside the parcel polygon, but the listing's street
    # number disagrees → treated as unmatched (never mis-assigned).
    parcels = [
        _dins_geo(
            "5841009012",
            "5841-009-012",
            "411 PUNAHOU ST ALTADENA CA 91001",
            (-118.13, 34.19),
        )
    ]
    index = build_parcels_index(parcels)  # type: ignore[arg-type]
    records = [
        {
            "formattedAddress": "999 Elsewhere Ave, Altadena, CA 91001",
            "latitude": 34.19,
            "longitude": -118.13,
            "status": "Active",
        }
    ]
    unmatched: list[str] = []
    listings = normalize_listings(records, index, unmatched=unmatched)  # type: ignore[arg-type]
    assert listings == {}
    assert unmatched == ["999 Elsewhere Ave, Altadena, CA 91001"]


def test_normalize_listings_reports_ambiguous_separately() -> None:
    # The listing's point lands in two same-number condo parcels sharing a
    # polygon → unresolvable → routed to `ambiguous`, NOT `unmatched`, with the
    # tied parcel AINs in the label.
    center = (-118.13, 34.19)
    parcels = [
        _dins_geo("5751021042", "5751-021-042", "1501 CREEKSIDE CT NO A", center),
        _dins_geo("5751021043", "5751-021-043", "1501 CREEKSIDE CT NO B", center),
    ]
    index = build_parcels_index(parcels)  # type: ignore[arg-type]
    records = [
        {
            "formattedAddress": "1501 Creekside Ct, Pasadena, CA 91107",
            "latitude": 34.19,
            "longitude": -118.13,
            "status": "Active",
        }
    ]
    unmatched: list[str] = []
    ambiguous: list[str] = []
    listings = normalize_listings(  # type: ignore[arg-type]
        records, index, unmatched=unmatched, ambiguous=ambiguous
    )
    assert listings == {}
    assert unmatched == []  # not a plain non-match
    assert len(ambiguous) == 1
    assert "5751021042" in ambiguous[0] and "5751021043" in ambiguous[0]


def test_apply_sales_overlays_fields() -> None:
    result = _result("5841009012", bsd_status=BsdStatus.RED)
    cache = SalesCache(
        sold={
            "5841009012": SaleInfo(
                ain="5841009012",
                sale_date="2025-03-14",
                sale_price=1250000,
                owner_name="JANE DOE",
                owner_type="Individual",
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
    assert result.owner_name == "JANE DOE"
    # owner_class is derived from owner_name (not RentCast's owner_type).
    assert result.owner_class == "individual"
    assert result.active_listing is True
    assert result.listing_date == "2026-05-01"
    # A parcel with both sale + listing resolves to "listed" on the map.
    assert property_sales_bucket(result) == "listed"


# --- cache persistence -----------------------------------------------------


def test_sales_cache_roundtrip(tmp_path: Path) -> None:
    cache = SalesCache(
        sold={
            "a": SaleInfo("a", "2025-04-01", 500000, "BUYER A", "Individual"),
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
        sold={"keep": SaleInfo("keep", "2025-04-01", 1, None, None)},
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
    counts = count_parcels(parcels, as_of="2026-07-20")
    assert counts.property_sold_post_fire_count == 2  # p1, p4
    assert counts.property_active_listing_count == 2  # p2, p4


def test_sold_owner_and_listing_age_buckets_scoped_and_bucketed() -> None:
    as_of = "2026-07-20"
    parcels = [
        # Sold to each buyer class within the population.
        _result("ind", sold_post_fire=True, owner_class="individual"),
        _result("tru", sold_post_fire=True, owner_class="trust"),
        _result("co", sold_post_fire=True, owner_class="company"),
        # Sold but no owner name → unknown; still in the population.
        _result("unk", sold_post_fire=True, owner_class=None),
        # GREEN sale is outside the population → resolves to "none", uncounted.
        _result(
            "green",
            bsd_status=BsdStatus.GREEN,
            sold_post_fire=True,
            owner_class="company",
        ),
        # Active listings at varied ages as of 2026-07-20.
        _result("l0", active_listing=True, listing_date="2026-07-10"),  # 10d
        _result("l1", active_listing=True, listing_date="2026-06-25"),  # 25d
        _result("l2", active_listing=True, listing_date="2026-06-01"),  # 49d
        _result("l3", active_listing=True, listing_date="2026-05-15"),  # 66d
        _result("l4", active_listing=True, listing_date="2026-01-01"),  # 200d
        # Listing with no date → "none", not counted in any age band.
        _result("lnd", active_listing=True, listing_date=None),
    ]

    # Per-parcel buckets resolve as expected (drives the map coloring/filter).
    assert sold_owner_bucket(parcels[0]) == "individual"
    assert sold_owner_bucket(parcels[1]) == "trust"
    assert sold_owner_bucket(parcels[2]) == "company"
    assert sold_owner_bucket(parcels[3]) == "unknown"
    assert sold_owner_bucket(parcels[4]) == "none"  # GREEN, out of population
    assert listing_age_bucket(parcels[5], as_of) == "under_30"
    assert listing_age_bucket(parcels[7], as_of) == "30_to_60"
    assert listing_age_bucket(parcels[8], as_of) == "60_plus"  # 66d
    assert listing_age_bucket(parcels[9], as_of) == "60_plus"  # 200d
    assert listing_age_bucket(parcels[10], as_of) == "none"  # undated

    counts = count_parcels(parcels, as_of=as_of)
    # The four owner-class counts partition property_sold_post_fire_count.
    assert counts.property_sold_to_individual_count == 1
    assert counts.property_sold_to_trust_count == 1
    assert counts.property_sold_to_company_count == 1
    assert counts.property_sold_owner_unknown_count == 1
    assert counts.property_sold_post_fire_count == 4  # GREEN sale excluded
    assert (
        counts.property_sold_to_individual_count
        + counts.property_sold_to_trust_count
        + counts.property_sold_to_company_count
        + counts.property_sold_owner_unknown_count
        == counts.property_sold_post_fire_count
    )
    # Listing-age bands; the dated ones sum to property_active_listing_count minus
    # the single undated listing. 60_plus collapses the old 60–90 and 90+ bands.
    assert counts.listing_age_under_30_count == 2  # l0, l1
    assert counts.listing_age_30_to_60_count == 1  # l2
    assert counts.listing_age_60_plus_count == 2  # l3 (66d) + l4 (200d)
    assert counts.property_active_listing_count == 6  # includes the undated one
    assert (
        counts.listing_age_under_30_count
        + counts.listing_age_30_to_60_count
        + counts.listing_age_60_plus_count
        == counts.property_active_listing_count - 1
    )


# --- helpers ---------------------------------------------------------------


def _result(
    ain: str,
    *,
    bsd_status: BsdStatus = BsdStatus.RED,
    sold_post_fire: bool = False,
    active_listing: bool = False,
    owner_class: str | None = None,
    listing_date: str | None = None,
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
        owner_class=owner_class,
        active_listing=active_listing,
        listing_date=listing_date,
    )
