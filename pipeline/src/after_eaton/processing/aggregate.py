"""Burn-area aggregation: roll ParcelResult list into a SummaryResult."""

from __future__ import annotations

from dataclasses import dataclass

from .normalize import BsdStatus, DamageLevel
from .parcel_analysis import ParcelResult


@dataclass(frozen=True)
class SummaryResult:
    generated_at: str
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
    sfr_larger_count: int
    sfr_identical_count: int
    sfr_smaller_count: int
    sb9_count: int
    added_adu_count: int


_DAMAGED_LEVELS = {
    DamageLevel.AFFECTED,
    DamageLevel.MINOR,
    DamageLevel.MAJOR,
    DamageLevel.DESTROYED,
}


def aggregate_burn_area(
    parcels: list[ParcelResult],
    generated_at: str,
) -> SummaryResult:
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

    sfr_larger = sum(1 for p in parcels if p.sfr_size_comparison == "larger")
    sfr_identical = sum(1 for p in parcels if p.sfr_size_comparison == "identical")
    sfr_smaller = sum(1 for p in parcels if p.sfr_size_comparison == "smaller")

    sb9 = sum(1 for p in parcels if p.adds_sb9)
    added_adu = sum(1 for p in parcels if p.added_adu_count > 0)

    return SummaryResult(
        generated_at=generated_at,
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
        sfr_larger_count=sfr_larger,
        sfr_identical_count=sfr_identical,
        sfr_smaller_count=sfr_smaller,
        sb9_count=sb9,
        added_adu_count=added_adu,
    )
