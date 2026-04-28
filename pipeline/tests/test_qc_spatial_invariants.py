"""Tests for the spatial QC threshold checks."""

from __future__ import annotations

from after_eaton.processing.aggregate import RegionCounts
from after_eaton.processing.normalize import BsdStatus, DamageLevel
from after_eaton.processing.parcel_analysis import ParcelResult
from after_eaton.processing.spatial_aggregate import (
    RegionFeature,
    SpatialAggregation,
)
from after_eaton.qc.aggregate import check_thresholds


def _result(ain: str) -> ParcelResult:
    return ParcelResult(
        ain=ain,
        apn=ain,
        address="",
        damage=DamageLevel.DESTROYED,
        bsd_status=BsdStatus.RED,
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
        post_sb9_count=None,
        post_sb9_sqft=None,
        lfl_claimed=None,
        lfl_conflict=False,
        sfr_size_comparison=None,
        adds_sb9=False,
        added_adu_count=0,
        rebuild_progress_num=7,
        rebuild_progress=None,
        permit_status=None,
        roe_status=None,
        debris_cleared=None,
        dins_count=1,
    )


def _zero_counts(total: int = 0) -> RegionCounts:
    return RegionCounts(
        total_parcels=total,
        damaged_parcels=0,
        destroyed_parcels=0,
        bsd_red_count=0,
        bsd_yellow_count=0,
        bsd_green_count=0,
        bsd_red_or_yellow_count=0,
        no_permit_count=0,
        permit_in_review_count=0,
        permit_issued_count=0,
        construction_count=0,
        completed_count=0,
        lfl_count=0,
        nlfl_count=0,
        lfl_unknown_count=0,
        sfr_larger_count=0,
        sfr_identical_count=0,
        sfr_smaller_count=0,
        sb9_count=0,
        added_adu_count=0,
    )


def _tract(ct20: str, total: int) -> RegionFeature:
    return RegionFeature(
        identifiers={"ct20": ct20, "label": ct20},
        geometry=None,
        counts=_zero_counts(total),
    )


def _bg(bg20: str, ct20: str, total: int) -> RegionFeature:
    return RegionFeature(
        identifiers={"bg20": bg20, "ct20": ct20, "label": bg20},
        geometry=None,
        counts=_zero_counts(total),
    )


def _named(checks, name):  # type: ignore[no-untyped-def]
    return next(c for c in checks if c.name == name)


def test_tract_total_matches_summary_passes_when_balanced() -> None:
    results = [_result(str(i)) for i in range(10)]
    tracts = SpatialAggregation(
        features=[_tract("A", 6), _tract("B", 4)],
        unassigned_ains=[],
    )
    bgs = SpatialAggregation(
        features=[_bg("A1", "A", 6), _bg("B1", "B", 4)],
        unassigned_ains=[],
    )
    checks = check_thresholds(
        [], results, [], tract_aggregation=tracts, block_group_aggregation=bgs
    )
    c = _named(checks, "tract_total_matches_summary")
    assert c.passed
    assert c.actual == 0


def test_tract_total_matches_summary_balances_with_unassigned() -> None:
    """sum(tracts) + len(unassigned) must equal burn-area total."""
    results = [_result(str(i)) for i in range(10)]
    tracts = SpatialAggregation(
        features=[_tract("A", 8)],
        unassigned_ains=["x", "y"],
    )
    bgs = SpatialAggregation(
        features=[_bg("A1", "A", 8)],
        unassigned_ains=[],
    )
    checks = check_thresholds(
        [], results, [], tract_aggregation=tracts, block_group_aggregation=bgs
    )
    assert _named(checks, "tract_total_matches_summary").passed


def test_tract_total_matches_summary_fails_on_drift() -> None:
    results = [_result(str(i)) for i in range(10)]
    tracts = SpatialAggregation(
        features=[_tract("A", 7)],  # missing 3 parcels, no unassigned reported
        unassigned_ains=[],
    )
    bgs = SpatialAggregation(features=[_bg("A1", "A", 7)], unassigned_ains=[])
    checks = check_thresholds(
        [], results, [], tract_aggregation=tracts, block_group_aggregation=bgs
    )
    c = _named(checks, "tract_total_matches_summary")
    assert not c.passed
    assert c.actual == 3


def test_tract_partitions_into_block_groups_passes() -> None:
    tracts = SpatialAggregation(
        features=[_tract("A", 10), _tract("B", 5)],
        unassigned_ains=[],
    )
    bgs = SpatialAggregation(
        features=[
            _bg("A1", "A", 4),
            _bg("A2", "A", 6),
            _bg("B1", "B", 5),
        ],
        unassigned_ains=[],
    )
    checks = check_thresholds(
        [],
        [_result(str(i)) for i in range(15)],
        [],
        tract_aggregation=tracts,
        block_group_aggregation=bgs,
    )
    c = _named(checks, "tract_partitions_into_block_groups")
    assert c.passed
    assert c.actual == 0


def test_tract_partitions_into_block_groups_fails_on_mismatch() -> None:
    tracts = SpatialAggregation(
        features=[_tract("A", 10)],
        unassigned_ains=[],
    )
    bgs = SpatialAggregation(
        features=[_bg("A1", "A", 4), _bg("A2", "A", 5)],  # 4+5=9, tract says 10
        unassigned_ains=[],
    )
    checks = check_thresholds(
        [],
        [_result(str(i)) for i in range(10)],
        [],
        tract_aggregation=tracts,
        block_group_aggregation=bgs,
    )
    c = _named(checks, "tract_partitions_into_block_groups")
    assert not c.passed
    assert c.actual == 1
    assert "ct20=A" in c.detail


def test_invariant_checks_are_skipped_without_aggregations() -> None:
    """check_thresholds keeps backwards compat: invariant checks only fire
    when both aggregations are passed."""
    checks = check_thresholds([], [_result("1")], [])
    names = [c.name for c in checks]
    assert "tract_total_matches_summary" not in names
    assert "tract_partitions_into_block_groups" not in names
