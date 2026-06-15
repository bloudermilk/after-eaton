"""Tests for aggregate_burn_area math."""

from __future__ import annotations

from altadata.processing.aggregate import aggregate_burn_area
from altadata.processing.normalize import BsdStatus, DamageLevel
from altadata.processing.parcel_analysis import ParcelResult


def _make(
    *,
    ain: str = "1",
    damage: DamageLevel = DamageLevel.DESTROYED,
    bsd_status: BsdStatus = BsdStatus.RED,
    rebuild_progress_num: int | None = None,
    lfl_claimed: bool | None = None,
    sfr_size_comparison: str | None = None,
    pre_sfr_sqft: int | None = 1000,
    post_sfr_sqft: int | None = None,
    adds_sb9: bool = False,
    adds_sb1123: bool = False,
    sb_pathway_conflict: bool = False,
    added_adu_count: int = 0,
    rebuild_stage: int = 0,
    rebuild_new_stage: int = 0,
) -> ParcelResult:
    return ParcelResult(
        ain=ain,
        apn=ain,
        address="",
        damage=damage,
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
        sfr_size_comparison=sfr_size_comparison,  # type: ignore[arg-type]
        adds_sb9=adds_sb9,
        adds_sb1123=adds_sb1123,
        sb_pathway_conflict=sb_pathway_conflict,
        added_adu_count=added_adu_count,
        rebuild_progress_num=rebuild_progress_num,
        rebuild_progress=None,
        permit_status=None,
        roe_status=None,
        debris_cleared=None,
        dins_count=1,
        rebuild_stage=rebuild_stage,
        rebuild_new_stage=rebuild_new_stage,
    )


def test_basic_counts() -> None:
    parcels = [
        _make(
            ain="1",
            damage=DamageLevel.DESTROYED,
            bsd_status=BsdStatus.RED,
            rebuild_progress_num=7,
            lfl_claimed=True,
            pre_sfr_sqft=1000,
            post_sfr_sqft=1300,  # +30% → larger_10_to_30 (boundary inclusive)
        ),
        _make(
            ain="2",
            damage=DamageLevel.DESTROYED,
            bsd_status=BsdStatus.YELLOW,
            rebuild_progress_num=4,
            lfl_claimed=None,
            pre_sfr_sqft=1000,
            post_sfr_sqft=900,  # 0.9 ratio → within_10 (boundary inclusive)
            adds_sb9=True,
            added_adu_count=2,
        ),
        _make(
            ain="3",
            damage=DamageLevel.MAJOR,
            bsd_status=BsdStatus.YELLOW,
            rebuild_progress_num=None,
            pre_sfr_sqft=1000,
            post_sfr_sqft=None,  # unknown bucket
            adds_sb1123=True,
        ),
        _make(
            ain="4",
            damage=DamageLevel.NO_DAMAGE,
            bsd_status=BsdStatus.GREEN,
            rebuild_progress_num=None,
            pre_sfr_sqft=None,  # unknown bucket
            post_sfr_sqft=None,
        ),
    ]
    s = aggregate_burn_area(parcels, "2026-04-27T00:00:00Z")

    assert s.total_parcels == 4
    assert s.damaged_parcels == 3  # excludes NO_DAMAGE
    assert s.destroyed_parcels == 2
    assert s.bsd_red_count == 1
    assert s.bsd_yellow_count == 2
    assert s.bsd_green_count == 1
    assert s.bsd_red_or_yellow_count == 3
    assert s.lfl_count == 1
    assert s.lfl_unknown_count == 1  # only parcel 2 (has permit, no LFL signal)
    assert s.sfr_size_pct_smaller_over_30 == 0
    assert s.sfr_size_pct_smaller_10_to_30 == 0
    assert s.sfr_size_pct_within_10 == 1
    assert s.sfr_size_pct_larger_10_to_30 == 1
    assert s.sfr_size_pct_larger_over_30 == 0
    assert s.sfr_size_pct_unknown == 2
    assert s.sb9_count == 1
    assert s.sb1123_count == 1
    assert s.adu_added_1_count == 0
    assert s.adu_added_2_count == 1
    assert s.adu_added_3_plus_count == 0
    assert s.generated_at == "2026-04-27T00:00:00Z"


def test_sfr_size_buckets_boundary() -> None:
    """Boundaries:
    - ratio < 0.70 → smaller_over_30; 0.70 → smaller_10_to_30
    - ratio < 0.90 → smaller_10_to_30; 0.90 → within_10
    - 1.10 → within_10; 1.11 → larger_10_to_30
    - 1.30 → larger_10_to_30; 1.31 → larger_over_30
    """
    parcels = [
        _make(ain="a1", pre_sfr_sqft=1000, post_sfr_sqft=600),  # 0.60 → smaller_over_30
        _make(
            ain="a2", pre_sfr_sqft=1000, post_sfr_sqft=700
        ),  # 0.70 → smaller_10_to_30
        _make(
            ain="b", pre_sfr_sqft=1000, post_sfr_sqft=899
        ),  # 0.899 → smaller_10_to_30
        _make(ain="c", pre_sfr_sqft=1000, post_sfr_sqft=900),  # 0.90 → within_10
        _make(ain="d", pre_sfr_sqft=1000, post_sfr_sqft=1100),  # 1.10 → within_10
        _make(ain="e", pre_sfr_sqft=1000, post_sfr_sqft=1110),  # 1.11 → larger_10_to_30
        _make(ain="f", pre_sfr_sqft=1000, post_sfr_sqft=1300),  # 1.30 → larger_10_to_30
        _make(ain="g", pre_sfr_sqft=1000, post_sfr_sqft=1310),  # 1.31 → larger_over_30
        _make(ain="h", pre_sfr_sqft=0, post_sfr_sqft=1000),  # zero pre → unknown
    ]
    s = aggregate_burn_area(parcels, "2026-04-27T00:00:00Z")
    assert s.sfr_size_pct_smaller_over_30 == 1
    assert s.sfr_size_pct_smaller_10_to_30 == 2
    assert s.sfr_size_pct_within_10 == 2
    assert s.sfr_size_pct_larger_10_to_30 == 2
    assert s.sfr_size_pct_larger_over_30 == 1
    assert s.sfr_size_pct_unknown == 1


def test_rebuild_funnel_counts_are_monotonic() -> None:
    """The published funnel is cumulative on the furthest stage reached: a parcel
    at stage N is counted at every stage 1..N, so the counts strictly decline.

    (The non-monotonic, case-level view is preserved in the per-parcel
    `rebuild_*_cases` fields and exercised in test_parcel_analysis, not here.)
    """
    parcels = [
        _make(ain="A", rebuild_stage=7),  # completed → counts at all 7 stages
        _make(ain="B", rebuild_stage=5),  # permit issued → stages 1..5
        _make(ain="C", rebuild_stage=2),  # zoning cleared → stages 1..2
        _make(ain="D", rebuild_stage=0),  # no milestone → counted nowhere
    ]
    s = aggregate_burn_area(parcels, "2026-04-27T00:00:00Z")

    counts = [
        s.rebuild_app_received_parcels,
        s.rebuild_zoning_cleared_parcels,
        s.rebuild_plans_received_parcels,
        s.rebuild_plans_approved_parcels,
        s.rebuild_permit_issued_parcels,
        s.rebuild_in_construction_parcels,
        s.rebuild_construction_completed_parcels,
    ]
    assert counts == [3, 3, 2, 2, 2, 1, 1]
    # Strictly non-increasing across the funnel, by construction.
    assert all(counts[i] >= counts[i + 1] for i in range(len(counts) - 1))


def test_new_construction_funnel_counts_all_new_builds_and_is_monotonic() -> None:
    """The published new-construction funnel counts every parcel with a
    new-building permit (`rebuild_new_stage`), regardless of original damage,
    monotonically, starting at stage 3 (plans received — the 100% baseline)."""
    parcels = [
        # Reached each New stage — counted up to their stage.
        _make(ain="A", damage=DamageLevel.DESTROYED, rebuild_new_stage=7),
        _make(ain="B", damage=DamageLevel.DESTROYED, rebuild_new_stage=6),
        _make(ain="C", damage=DamageLevel.DESTROYED, rebuild_new_stage=3),
        # New construction on a NON-destroyed lot — now counted like any other.
        _make(ain="D", damage=DamageLevel.MAJOR, rebuild_new_stage=7),
        # No New permit — not in any funnel row (but still in destroyed_parcels).
        _make(ain="E", damage=DamageLevel.DESTROYED, rebuild_new_stage=0),
    ]
    s = aggregate_burn_area(parcels, "2026-04-27T00:00:00Z")

    counts = [
        s.rebuild_new_plans_received_parcels,  # stage >= 3: A, B, C, D
        s.rebuild_new_plans_approved_parcels,  # stage >= 4: A, B, D
        s.rebuild_new_permit_issued_parcels,  # stage >= 5: A, B, D
        s.rebuild_new_in_construction_parcels,  # stage >= 6: A, B, D
        s.rebuild_new_construction_completed_parcels,  # stage >= 7: A, D
    ]
    assert counts == [4, 3, 3, 3, 2]
    # The non-destroyed completion (D) is now counted; destroyed_parcels is the
    # damage tally, unaffected by the funnel scope change.
    assert s.destroyed_parcels == 4
    assert all(counts[i] >= counts[i + 1] for i in range(len(counts) - 1))


def test_adu_distribution_buckets() -> None:
    parcels = [
        _make(ain="0", added_adu_count=0),  # not in any bucket
        _make(ain="1", added_adu_count=1),
        _make(ain="2a", added_adu_count=2),
        _make(ain="2b", added_adu_count=2),
        _make(ain="3", added_adu_count=3),
        _make(ain="5", added_adu_count=5),
    ]
    s = aggregate_burn_area(parcels, "2026-04-27T00:00:00Z")
    assert s.adu_added_1_count == 1
    assert s.adu_added_2_count == 2
    assert s.adu_added_3_plus_count == 2
