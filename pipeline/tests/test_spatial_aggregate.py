"""Tests for spatial assignment + per-region aggregation."""

from __future__ import annotations

from typing import Any

from after_eaton.processing.normalize import BsdStatus, DamageLevel
from after_eaton.processing.parcel_analysis import ParcelResult
from after_eaton.processing.spatial_aggregate import aggregate_by_region
from after_eaton.sources.schemas import DinsParcel


def _square(cx: float, cy: float, half: float = 0.5) -> dict[str, Any]:
    """Esri-style geometry for a square centered at (cx, cy)."""
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
    damage: DamageLevel = DamageLevel.DESTROYED,
    bsd_status: BsdStatus = BsdStatus.RED,
    rebuild_progress_num: int | None = 7,
) -> ParcelResult:
    return ParcelResult(
        ain=ain,
        apn=ain,
        address="",
        damage=damage,
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
        added_adu_count=0,
        rebuild_progress_num=rebuild_progress_num,
        rebuild_progress=None,
        permit_status=None,
        roe_status=None,
        debris_cleared=None,
        dins_count=1,
    )


def _dins(ain: str, geom: dict[str, Any]) -> DinsParcel:
    return {  # type: ignore[typeddict-item]
        "AIN_1": ain,
        "DAMAGE_1": "Destroyed (>50%)",
        "SQFTmain1": 1000.0,
        "DesignType1": "0101",
        "COMMUNITY": "Altadena",
        "_geometry": geom,
    }


def test_centroid_assignment_emits_correct_per_region_counts() -> None:
    # Two adjacent square tracts side-by-side: tract A spans x in [0, 10],
    # tract B spans x in [10, 20]. Both span y in [0, 10].
    tracts = [
        {
            "CT20": "A",
            "LABEL": "Tract A",
            "_geometry": {
                "rings": [
                    [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
                ]
            },
        },
        {
            "CT20": "B",
            "LABEL": "Tract B",
            "_geometry": {
                "rings": [
                    [[10, 0], [20, 0], [20, 10], [10, 10], [10, 0]],
                ]
            },
        },
    ]

    parcels = [
        # Two parcels in tract A (centroid at x = 2.5, 5.0)
        (_result("p1"), _dins("p1", _square(2.5, 5.0))),
        (_result("p2"), _dins("p2", _square(5.0, 5.0))),
        # One parcel in tract B (centroid at x = 15.0)
        (_result("p3"), _dins("p3", _square(15.0, 5.0))),
        # One parcel far outside both
        (_result("p4"), _dins("p4", _square(100.0, 100.0))),
    ]

    result = aggregate_by_region(parcels, tracts, id_fields=["CT20", "LABEL"])

    by_id = {f.identifiers["ct20"]: f for f in result.features}
    assert by_id["A"].counts.total_parcels == 2
    assert by_id["B"].counts.total_parcels == 1
    assert by_id["A"].identifiers["label"] == "Tract A"
    assert result.unassigned_ains == ["p4"]


def test_zero_parcel_region_still_emitted() -> None:
    tracts = [
        {
            "CT20": "A",
            "LABEL": "Tract A",
            "_geometry": {
                "rings": [
                    [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
                ]
            },
        },
        {
            "CT20": "EMPTY",
            "LABEL": "Empty Tract",
            "_geometry": {
                "rings": [
                    [[100, 100], [110, 100], [110, 110], [100, 110], [100, 100]],
                ]
            },
        },
    ]
    parcels = [
        (_result("p1"), _dins("p1", _square(5.0, 5.0))),
    ]

    result = aggregate_by_region(parcels, tracts, id_fields=["CT20", "LABEL"])

    by_id = {f.identifiers["ct20"]: f for f in result.features}
    assert by_id["A"].counts.total_parcels == 1
    assert by_id["EMPTY"].counts.total_parcels == 0
    # Counts default to zero, not null.
    assert by_id["EMPTY"].counts.destroyed_parcels == 0


def test_per_region_total_sums_to_burn_area_total() -> None:
    """Per-region totals must sum back to the burn-area total. Centroid
    assignment guarantees 1:1, so this is a hard invariant.
    """
    tracts = [
        {
            "CT20": "A",
            "LABEL": "A",
            "_geometry": {"rings": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]]},
        },
        {
            "CT20": "B",
            "LABEL": "B",
            "_geometry": {"rings": [[[10, 0], [20, 0], [20, 10], [10, 10], [10, 0]]]},
        },
    ]
    parcels = [
        (_result("p1"), _dins("p1", _square(2.5, 5.0))),
        (_result("p2"), _dins("p2", _square(5.0, 5.0))),
        (_result("p3"), _dins("p3", _square(7.5, 5.0))),
        (_result("p4"), _dins("p4", _square(15.0, 5.0))),
    ]

    result = aggregate_by_region(parcels, tracts, id_fields=["CT20", "LABEL"])
    summed = sum(f.counts.total_parcels for f in result.features)
    assert summed == len(parcels)
    assert result.unassigned_ains == []
