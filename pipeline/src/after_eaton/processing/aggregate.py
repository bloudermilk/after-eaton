"""Burn-area aggregation: roll ParcelResult list into a SummaryResult."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass

from .normalize import BsdStatus, DamageLevel
from .parcel_analysis import ParcelResult


@dataclass(frozen=True)
class RegionCounts:
    """Per-region counting fields. Shared by the burn-area summary and the
    per-tract / per-block-group aggregations so a single source-of-truth set
    of predicates governs every count we publish.
    """

    total_parcels: int
    # DINS DAMAGE_1 (FIRESCOPE %-loss) buckets
    damaged_parcels: int
    destroyed_parcels: int
    # DINS BSD_Tag (Safety Assessment) buckets — these are the figures the
    # LA County Recovery Map publishes as "Destroyed/Damaged Parcels".
    bsd_red_count: int
    bsd_yellow_count: int
    bsd_green_count: int
    bsd_red_or_yellow_count: int
    no_permit_count: int
    permit_in_review_count: int
    permit_issued_count: int
    construction_count: int
    completed_count: int
    lfl_count: int
    nlfl_count: int
    lfl_unknown_count: int
    # Relative SFR size, post-fire vs. pre-fire, by percentage bucket.
    # Denominator = parcels with both pre_sfr_sqft and post_sfr_sqft known
    # and pre_sfr_sqft > 0; everything else lands in `_unknown` for
    # transparency. Cutoffs are exclusive at 10% (so ±10% is its own band)
    # and inclusive at 30% on the wider bands.
    sfr_size_pct_smaller_over_30: int
    sfr_size_pct_smaller_10_to_30: int
    sfr_size_pct_within_10: int
    sfr_size_pct_larger_10_to_30: int
    sfr_size_pct_larger_over_30: int
    sfr_size_pct_unknown: int
    sb9_count: int
    # Distribution of parcels by how many ADUs they added relative to pre-fire.
    # Parcels with added_adu_count == 0 are not in any of these buckets.
    adu_added_1_count: int
    adu_added_2_count: int
    adu_added_3_plus_count: int
    # Parcels rebuilding at least one SFR, ADU, or JADU. Used as a denominator
    # for the share-of-dwelling-rebuilders charts on the home page. JADUs roll
    # into post_adu_count via the LLM extraction (jadu→adu), so checking
    # post_sfr_count and post_adu_count covers all three types in practice.
    dwelling_rebuild_count: int


@dataclass(frozen=True, kw_only=True)
class SummaryResult(RegionCounts):
    """Burn-area-wide totals carrying the run's `generated_at` timestamp."""

    generated_at: str


_DAMAGED_LEVELS = {
    DamageLevel.AFFECTED,
    DamageLevel.MINOR,
    DamageLevel.MAJOR,
    DamageLevel.DESTROYED,
}


def _sfr_size_bucket(parcel: ParcelResult) -> str:
    pre = parcel.pre_sfr_sqft
    post = parcel.post_sfr_sqft
    if pre is None or post is None or pre <= 0:
        return "unknown"
    ratio = post / pre
    # ±10% is inclusive on both ends; the smaller/larger bands begin at
    # exactly 10% (exclusive) and the >30% bands begin at exactly 30%
    # (exclusive). A parcel rebuilt at ratio 0.9 / 1.1 / 0.7 / 1.3 lands in
    # the inner band of the pair.
    if ratio < 0.7:
        return "smaller_over_30"
    if ratio < 0.9:
        return "smaller_10_to_30"
    if ratio <= 1.10:
        return "within_10"
    if ratio <= 1.30:
        return "larger_10_to_30"
    return "larger_over_30"


def count_parcels(parcels: Iterable[ParcelResult]) -> RegionCounts:
    """Compute every published count field for a parcel set.

    Used both by `aggregate_burn_area` and by per-region (tract / block
    group) aggregation, so the same predicates govern every publish path.
    """
    parcels = list(parcels)
    total = len(parcels)
    damaged = sum(1 for p in parcels if p.damage in _DAMAGED_LEVELS)
    destroyed = sum(1 for p in parcels if p.damage == DamageLevel.DESTROYED)
    bsd_red = sum(1 for p in parcels if p.bsd_status == BsdStatus.RED)
    bsd_yellow = sum(1 for p in parcels if p.bsd_status == BsdStatus.YELLOW)
    bsd_green = sum(1 for p in parcels if p.bsd_status == BsdStatus.GREEN)

    no_permit = sum(1 for p in parcels if p.rebuild_progress_num is None)
    in_review = sum(1 for p in parcels if p.rebuild_progress_num in (1, 2, 3, 4))
    issued = sum(1 for p in parcels if p.rebuild_progress_num == 5)
    construction = sum(1 for p in parcels if p.rebuild_progress_num == 6)
    completed = sum(1 for p in parcels if p.rebuild_progress_num == 7)

    lfl = sum(1 for p in parcels if p.lfl_claimed is True)
    nlfl = sum(1 for p in parcels if p.lfl_claimed is False)
    # "Unknown" only counts parcels that have a permit but no LFL signal —
    # parcels with no permit at all are tracked separately by no_permit_count.
    lfl_unknown = sum(
        1
        for p in parcels
        if p.lfl_claimed is None and p.rebuild_progress_num is not None
    )

    size_buckets = {
        "smaller_over_30": 0,
        "smaller_10_to_30": 0,
        "within_10": 0,
        "larger_10_to_30": 0,
        "larger_over_30": 0,
        "unknown": 0,
    }
    for p in parcels:
        size_buckets[_sfr_size_bucket(p)] += 1

    sb9 = sum(1 for p in parcels if p.adds_sb9)
    adu_added_1 = sum(1 for p in parcels if p.added_adu_count == 1)
    adu_added_2 = sum(1 for p in parcels if p.added_adu_count == 2)
    adu_added_3_plus = sum(1 for p in parcels if p.added_adu_count >= 3)

    dwelling_rebuild = sum(
        1
        for p in parcels
        if (p.post_sfr_count or 0) > 0 or (p.post_adu_count or 0) > 0
    )

    return RegionCounts(
        total_parcels=total,
        damaged_parcels=damaged,
        destroyed_parcels=destroyed,
        bsd_red_count=bsd_red,
        bsd_yellow_count=bsd_yellow,
        bsd_green_count=bsd_green,
        bsd_red_or_yellow_count=bsd_red + bsd_yellow,
        no_permit_count=no_permit,
        permit_in_review_count=in_review,
        permit_issued_count=issued,
        construction_count=construction,
        completed_count=completed,
        lfl_count=lfl,
        nlfl_count=nlfl,
        lfl_unknown_count=lfl_unknown,
        sfr_size_pct_smaller_over_30=size_buckets["smaller_over_30"],
        sfr_size_pct_smaller_10_to_30=size_buckets["smaller_10_to_30"],
        sfr_size_pct_within_10=size_buckets["within_10"],
        sfr_size_pct_larger_10_to_30=size_buckets["larger_10_to_30"],
        sfr_size_pct_larger_over_30=size_buckets["larger_over_30"],
        sfr_size_pct_unknown=size_buckets["unknown"],
        sb9_count=sb9,
        adu_added_1_count=adu_added_1,
        adu_added_2_count=adu_added_2,
        adu_added_3_plus_count=adu_added_3_plus,
        dwelling_rebuild_count=dwelling_rebuild,
    )


def aggregate_burn_area(
    parcels: list[ParcelResult],
    generated_at: str,
) -> SummaryResult:
    counts = count_parcels(parcels)
    return SummaryResult(generated_at=generated_at, **asdict(counts))
