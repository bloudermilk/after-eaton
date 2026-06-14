"""Tests for the compact (point) parcels GeoJSON writer, the representative
point helper, and the shared per-parcel bucket classifiers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from altadata.outputs.geojson_writer import write_parcels_compact_geojson
from altadata.processing.aggregate import adu_bucket, lfl_bucket, sfr_size_bucket
from altadata.processing.geometry import representative_point
from altadata.processing.join import JoinedParcel
from altadata.processing.normalize import BsdStatus, DamageLevel
from altadata.processing.parcel_analysis import ParcelResult
from altadata.sources.schemas import DinsParcel, EpicCase


def _square(cx: float, cy: float, half: float = 0.5) -> dict[str, Any]:
    return {
        "rings": [
            [
                [cx - half, cy - half],
                [cx + half, cy - half],
                [cx + half, cy + half],
                [cx - half, cy + half],
                [cx - half, cy - half],
            ]
        ]
    }


def _result(
    ain: str,
    *,
    address: str = "1 MAIN ST",
    pre_sfr_sqft: int | None = 1000,
    post_sfr_sqft: int | None = None,
    lfl_claimed: bool | None = None,
    rebuild_progress_num: int | None = None,
    added_adu_count: int = 0,
    adds_sb9: bool = False,
    adds_sb1123: bool = False,
    rebuild_stage: int = 0,
    bsd_status: BsdStatus = BsdStatus.RED,
) -> ParcelResult:
    return ParcelResult(
        ain=ain,
        apn=ain,
        address=address,
        damage=DamageLevel.DESTROYED,
        bsd_status=bsd_status,
        pre_sfr_count=1,
        pre_sfr_sqft=pre_sfr_sqft,
        pre_adu_count=0,
        pre_adu_sqft=None,
        pre_mfr_count=0,
        pre_mfr_sqft=None,
        post_sfr_count=None,
        post_sfr_sqft=post_sfr_sqft,
        post_adu_count=None,
        post_adu_sqft=None,
        post_mfr_count=None,
        post_mfr_sqft=None,
        lfl_claimed=lfl_claimed,
        lfl_conflict=False,
        sfr_size_comparison=None,
        adds_sb9=adds_sb9,
        adds_sb1123=adds_sb1123,
        sb_pathway_conflict=False,
        added_adu_count=added_adu_count,
        rebuild_progress_num=rebuild_progress_num,
        rebuild_progress=None,
        permit_status=None,
        roe_status=None,
        debris_cleared=None,
        dins_count=1,
        rebuild_stage=rebuild_stage,
    )


def _dins(ain: str, geom: dict[str, Any] | None) -> DinsParcel:
    return {  # type: ignore[typeddict-item]
        "AIN_1": ain,
        "DAMAGE_1": "Destroyed (>50%)",
        "SQFTmain1": 1000.0,
        "DesignType1": "0101",
        "COMMUNITY": "Altadena",
        "_geometry": geom,
    }


def _case(ain: str, x: float | None, y: float | None) -> EpicCase:
    geom = {"x": x, "y": y} if x is not None and y is not None else None
    return {  # type: ignore[typeddict-item]
        "MAIN_AIN": ain,
        "MODULENAME": "PermitManagement",
        "REBUILD_PROGRESS_NUM": 5,
        "DESCRIPTION": None,
        "_geometry": geom,
    }


# --- representative_point --------------------------------------------------


def test_representative_point_prefers_epic_point() -> None:
    # DINS polygon centroid is at (2.5, 5.0); the EPIC case point is elsewhere.
    joined = JoinedParcel(
        din=_dins("p1", _square(2.5, 5.0)),
        cases=[_case("p1", -118.15, 34.19)],
    )
    assert representative_point(joined) == (-118.15, 34.19)


def test_representative_point_falls_back_to_dins_centroid() -> None:
    # No case geometry → use the DINS polygon centroid.
    joined = JoinedParcel(
        din=_dins("p1", _square(2.5, 5.0)),
        cases=[_case("p1", None, None)],
    )
    point = representative_point(joined)
    assert point is not None
    assert point == (2.5, 5.0)


def test_representative_point_none_when_no_geometry() -> None:
    joined = JoinedParcel(din=_dins("p1", None), cases=[])
    assert representative_point(joined) is None


# --- compact writer --------------------------------------------------------


def test_compact_geojson_emits_points_and_minimal_props(tmp_path: Path) -> None:
    pairs = [
        (
            _result(
                "p1",
                address="1 MAIN ST",
                pre_sfr_sqft=1000,
                post_sfr_sqft=1500,  # ratio 1.5 → larger_over_30
                lfl_claimed=True,
                rebuild_progress_num=5,
                added_adu_count=2,
                adds_sb9=True,
                adds_sb1123=False,
            ),
            JoinedParcel(
                din=_dins("p1", _square(2.5, 5.0)), cases=[_case("p1", -118.1, 34.2)]
            ),
        ),
    ]
    out = tmp_path / "parcels-compact.geojson"
    write_parcels_compact_geojson(pairs, out, generated_at="2026-06-13T00:00:00+00:00")

    payload = json.loads(out.read_text())
    assert payload["type"] == "FeatureCollection"
    assert payload["metadata"]["generated_at"] == "2026-06-13T00:00:00+00:00"
    feat = payload["features"][0]
    assert feat["geometry"] == {"type": "Point", "coordinates": [-118.1, 34.2]}
    # Only the frontend-used properties, nothing more.
    assert set(feat["properties"]) == {
        "ain",
        "address",
        "sfr_size_bucket",
        "lfl_bucket",
        "adu_bucket",
        "adds_sb9",
        "adds_sb1123",
        "bsd_red_or_yellow",
        "rebuild_app_received",
        "rebuild_zoning_cleared",
        "rebuild_plans_received",
        "rebuild_plans_approved",
        "rebuild_permit_issued",
        "rebuild_in_construction",
        "rebuild_construction_completed",
        "rebuild_stage",
    }
    assert feat["properties"] == {
        "ain": "p1",
        "address": "1 MAIN ST",
        "sfr_size_bucket": "larger_over_30",
        "lfl_bucket": "lfl",
        "adu_bucket": "added_2",
        "adds_sb9": True,
        "adds_sb1123": False,
        # _result defaults bsd_status to RED → in the damaged/destroyed scope.
        "bsd_red_or_yellow": True,
        # _result defaults rebuild_stage to 0, so no stage is reached.
        "rebuild_app_received": False,
        "rebuild_zoning_cleared": False,
        "rebuild_plans_received": False,
        "rebuild_plans_approved": False,
        "rebuild_permit_issued": False,
        "rebuild_in_construction": False,
        "rebuild_construction_completed": False,
        "rebuild_stage": 0,
    }


def test_compact_geojson_stage_flags_are_cumulative(tmp_path: Path) -> None:
    """A parcel at stage 5 is flagged for every stage up to 5 and none beyond,
    so selecting any of those stages on the map lights this dot — matching the
    monotonic card counts."""
    pairs = [
        (
            _result("p1", rebuild_progress_num=5, rebuild_stage=5),
            JoinedParcel(
                din=_dins("p1", _square(2.5, 5.0)), cases=[_case("p1", -118.1, 34.2)]
            ),
        ),
    ]
    out = tmp_path / "parcels-compact.geojson"
    write_parcels_compact_geojson(pairs, out, generated_at="2026-06-13T00:00:00+00:00")

    props = json.loads(out.read_text())["features"][0]["properties"]
    assert props["rebuild_stage"] == 5
    assert props["rebuild_app_received"] is True
    assert props["rebuild_zoning_cleared"] is True
    assert props["rebuild_plans_received"] is True
    assert props["rebuild_plans_approved"] is True
    assert props["rebuild_permit_issued"] is True
    assert props["rebuild_in_construction"] is False
    assert props["rebuild_construction_completed"] is False


def test_compact_geojson_bsd_red_or_yellow_flag(tmp_path: Path) -> None:
    """The map's "Damaged or destroyed" baseline filters on `bsd_red_or_yellow`,
    true only for the County's Red- (destroyed) and Yellow-tagged (damaged)
    Safety Assessment scope — Green and untagged parcels are excluded."""
    pairs = [
        (
            _result(ain, bsd_status=status),
            JoinedParcel(
                din=_dins(ain, _square(2.5, 5.0)), cases=[_case(ain, -118.1, 34.2)]
            ),
        )
        for ain, status in [
            ("red", BsdStatus.RED),
            ("yellow", BsdStatus.YELLOW),
            ("green", BsdStatus.GREEN),
            ("none", BsdStatus.NONE),
        ]
    ]
    out = tmp_path / "parcels-compact.geojson"
    write_parcels_compact_geojson(pairs, out, generated_at="2026-06-13T00:00:00+00:00")

    flags = {
        f["properties"]["ain"]: f["properties"]["bsd_red_or_yellow"]
        for f in json.loads(out.read_text())["features"]
    }
    assert flags == {"red": True, "yellow": True, "green": False, "none": False}


def test_compact_geojson_drops_pointless_parcels(tmp_path: Path) -> None:
    pairs = [
        (_result("p1"), JoinedParcel(din=_dins("p1", _square(0.0, 0.0)), cases=[])),
        # No DINS rings and no case geometry → not plottable, dropped.
        (_result("p2"), JoinedParcel(din=_dins("p2", None), cases=[])),
    ]
    out = tmp_path / "parcels-compact.geojson"
    write_parcels_compact_geojson(pairs, out, generated_at="2026-06-13T00:00:00+00:00")
    payload = json.loads(out.read_text())
    ains = [f["properties"]["ain"] for f in payload["features"]]
    assert ains == ["p1"]


# --- classifiers -----------------------------------------------------------


def test_sfr_size_bucket_values() -> None:
    assert (
        sfr_size_bucket(_result("a", pre_sfr_sqft=1000, post_sfr_sqft=600))
        == "smaller_over_30"
    )
    assert (
        sfr_size_bucket(_result("a", pre_sfr_sqft=1000, post_sfr_sqft=1000))
        == "within_10"
    )
    assert (
        sfr_size_bucket(_result("a", pre_sfr_sqft=1000, post_sfr_sqft=None))
        == "unknown"
    )


def test_lfl_bucket_values() -> None:
    assert lfl_bucket(_result("a", lfl_claimed=True, rebuild_progress_num=5)) == "lfl"
    assert lfl_bucket(_result("a", lfl_claimed=False, rebuild_progress_num=5)) == "nlfl"
    assert (
        lfl_bucket(_result("a", lfl_claimed=None, rebuild_progress_num=5)) == "unknown"
    )
    assert (
        lfl_bucket(_result("a", lfl_claimed=None, rebuild_progress_num=None)) == "none"
    )


def test_adu_bucket_values() -> None:
    assert adu_bucket(_result("a", added_adu_count=0)) == "none"
    assert adu_bucket(_result("a", added_adu_count=1)) == "added_1"
    assert adu_bucket(_result("a", added_adu_count=2)) == "added_2"
    assert adu_bucket(_result("a", added_adu_count=5)) == "added_3_plus"
