"""Burn-area aggregation: roll ParcelResult list into a SummaryResult."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass

from .normalize import REBUILD_STAGES, BsdStatus, DamageLevel
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
    # Rebuild-progress funnel: parcels at or beyond each milestone. A parcel is
    # counted at every stage up to and including the furthest one it reached
    # (`rebuild_stage`), so these counts are MONOTONIC — they decline by
    # construction. This intentionally differs from LA County's case-level
    # dashboard, which counts each milestone independently and is non-monotonic;
    # the per-parcel `rebuild_*_cases` fields on parcels.geojson / parcels.csv
    # preserve that case-level view for a future feature and are not surfaced in
    # the app today. See METHODOLOGY.md -> Rebuild progress.
    rebuild_app_received_parcels: int
    rebuild_zoning_cleared_parcels: int
    rebuild_plans_received_parcels: int
    rebuild_plans_approved_parcels: int
    rebuild_permit_issued_parcels: int
    rebuild_in_construction_parcels: int
    rebuild_construction_completed_parcels: int
    # New-construction milestones funnel — the one published in the app. Counts
    # every parcel with a new-building ("New" workclass) permit (`rebuild_new_stage`),
    # regardless of original damage level, so it tracks new-from-scratch building
    # across the fire area. Monotonic like the fields above and starts at "plans
    # received" (stage 3); New permits never carry the earlier application/zoning
    # milestones. The denominator is `rebuild_new_plans_received_parcels` (Plans
    # received is the 100% baseline). See METHODOLOGY.md -> New construction.
    rebuild_new_plans_received_parcels: int
    rebuild_new_plans_approved_parcels: int
    rebuild_new_permit_issued_parcels: int
    rebuild_new_in_construction_parcels: int
    rebuild_new_construction_completed_parcels: int
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
    sb1123_count: int
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
    # "Rebuild progress" split of the County's Destroyed/Damaged population
    # (BSD Red- or Yellow-tagged parcels — == bsd_red_or_yellow_count). A parcel
    # is "rebuilding" if it has any active fire EPIC case, else "not started".
    # The two are mutually exclusive and sum to bsd_red_or_yellow_count.
    rebuild_progress_not_started_count: int
    rebuild_progress_rebuilding_count: int
    # Post-fire real-estate activity within the Destroyed/Damaged (BSD red/yellow)
    # population — the "Property Sales" card. Each is a share of
    # bsd_red_or_yellow_count. Counted independently: a parcel both sold and
    # listed (rare) counts in both (see property_sales_bucket for the map's
    # single-bucket precedence).
    property_sold_post_fire_count: int
    property_active_listing_count: int


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


# Per-parcel bucket classifiers. These are the single source of truth for
# both the published counts below and the per-parcel bucket properties on
# `parcels-compact.geojson`, so the map can never drift from the summary.
def sfr_size_bucket(parcel: ParcelResult) -> str:
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


def lfl_bucket(parcel: ParcelResult) -> str:
    """Like-for-like classification. `none` = parcel has no permit at all;
    `unknown` = has a permit but no clear LFL/Custom claim."""
    if parcel.lfl_claimed is True:
        return "lfl"
    if parcel.lfl_claimed is False:
        return "nlfl"
    if parcel.rebuild_progress_num is not None:
        return "unknown"
    return "none"


def adu_bucket(parcel: ParcelResult) -> str:
    """How many ADUs the parcel added relative to pre-fire. `none` = added 0."""
    added = parcel.added_adu_count
    if added == 1:
        return "added_1"
    if added == 2:
        return "added_2"
    if added >= 3:
        return "added_3_plus"
    return "none"


def rebuild_progress_bucket(parcel: ParcelResult) -> str:
    """Rebuild-progress split of the County's Destroyed/Damaged population.

    The population is the BSD Red- or Yellow-tagged parcels (what LA County's
    Recovery Map publishes as "Destroyed/Damaged Parcels"). Within it, a parcel
    is `rebuilding` when it has any active fire EPIC case (a live case in any
    stage) and `not_started` when it has none. `none` = outside the population
    (no/green safety tag) — not shown or selectable on the map.
    """
    if parcel.bsd_status not in (BsdStatus.RED, BsdStatus.YELLOW):
        return "none"
    return "rebuilding" if parcel.fire_case_count > 0 else "not_started"


def property_sales_bucket(parcel: ParcelResult) -> str:
    """Post-fire real-estate activity within the Destroyed/Damaged population.

    Scoped to BSD Red/Yellow parcels — the same population as the "Rebuild
    progress" card and the `property_*_count` denominator — so the map filter
    lines up with the card counts. `listed` takes precedence over `sold` on the
    rare parcel that is both (a home is not usually both at once). `none` =
    outside the population or no post-fire sale/listing.
    """
    if parcel.bsd_status not in (BsdStatus.RED, BsdStatus.YELLOW):
        return "none"
    if parcel.active_listing:
        return "listed"
    if parcel.sold_post_fire:
        return "sold"
    return "none"


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

    # Monotonic funnel: a parcel counts toward a stage when its furthest
    # milestone reached (`rebuild_stage`) is at or beyond that stage — i.e. we
    # assume a parcel at stage N also passed every earlier stage, so the counts
    # strictly decline. (LA County's dashboard is non-monotonic; see the
    # RegionCounts docstring and METHODOLOGY.md -> Rebuild progress.)
    rebuild = {
        key: sum(1 for p in parcels if p.rebuild_stage >= num)
        for num, key, _ in REBUILD_STAGES
    }

    # New-construction funnel (the one the app publishes): same monotonic rule,
    # counting every new-building permit (`rebuild_new_stage`) regardless of the
    # parcel's original damage level. Stages 1-2 are omitted — New permits never
    # carry the application/zoning milestones, so the funnel starts at stage 3,
    # which ("plans received") is the funnel's 100% baseline.
    rebuild_new = {
        key: sum(1 for p in parcels if p.rebuild_new_stage >= num)
        for num, key, _ in REBUILD_STAGES
        if num >= 3
    }

    # "Unknown" only counts parcels that have a permit but no LFL signal —
    # parcels with no permit at all fall in the `none` bucket (not counted here).
    lfl = sum(1 for p in parcels if lfl_bucket(p) == "lfl")
    nlfl = sum(1 for p in parcels if lfl_bucket(p) == "nlfl")
    lfl_unknown = sum(1 for p in parcels if lfl_bucket(p) == "unknown")

    size_buckets = {
        "smaller_over_30": 0,
        "smaller_10_to_30": 0,
        "within_10": 0,
        "larger_10_to_30": 0,
        "larger_over_30": 0,
        "unknown": 0,
    }
    for p in parcels:
        size_buckets[sfr_size_bucket(p)] += 1

    sb9 = sum(1 for p in parcels if p.adds_sb9)
    sb1123 = sum(1 for p in parcels if p.adds_sb1123)
    adu_added_1 = sum(1 for p in parcels if adu_bucket(p) == "added_1")
    adu_added_2 = sum(1 for p in parcels if adu_bucket(p) == "added_2")
    adu_added_3_plus = sum(1 for p in parcels if adu_bucket(p) == "added_3_plus")

    dwelling_rebuild = sum(
        1 for p in parcels if (p.post_sfr_count or 0) > 0 or (p.post_adu_count or 0) > 0
    )

    # Rebuild-progress split of the Destroyed/Damaged (BSD red/yellow) population.
    rebuild_progress_not_started = sum(
        1 for p in parcels if rebuild_progress_bucket(p) == "not_started"
    )
    rebuild_progress_rebuilding = sum(
        1 for p in parcels if rebuild_progress_bucket(p) == "rebuilding"
    )

    # Property sales within the Destroyed/Damaged (BSD red/yellow) population.
    # Counted independently (not via property_sales_bucket, which is single-valued
    # for the map) so the two card numbers match their own predicates exactly.
    damaged_pop = [
        p for p in parcels if p.bsd_status in (BsdStatus.RED, BsdStatus.YELLOW)
    ]
    property_sold = sum(1 for p in damaged_pop if p.sold_post_fire)
    property_listed = sum(1 for p in damaged_pop if p.active_listing)

    return RegionCounts(
        total_parcels=total,
        damaged_parcels=damaged,
        destroyed_parcels=destroyed,
        bsd_red_count=bsd_red,
        bsd_yellow_count=bsd_yellow,
        bsd_green_count=bsd_green,
        bsd_red_or_yellow_count=bsd_red + bsd_yellow,
        rebuild_app_received_parcels=rebuild["app_received"],
        rebuild_zoning_cleared_parcels=rebuild["zoning_cleared"],
        rebuild_plans_received_parcels=rebuild["plans_received"],
        rebuild_plans_approved_parcels=rebuild["plans_approved"],
        rebuild_permit_issued_parcels=rebuild["permit_issued"],
        rebuild_in_construction_parcels=rebuild["in_construction"],
        rebuild_construction_completed_parcels=rebuild["construction_completed"],
        rebuild_new_plans_received_parcels=rebuild_new["plans_received"],
        rebuild_new_plans_approved_parcels=rebuild_new["plans_approved"],
        rebuild_new_permit_issued_parcels=rebuild_new["permit_issued"],
        rebuild_new_in_construction_parcels=rebuild_new["in_construction"],
        rebuild_new_construction_completed_parcels=rebuild_new[
            "construction_completed"
        ],
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
        sb1123_count=sb1123,
        adu_added_1_count=adu_added_1,
        adu_added_2_count=adu_added_2,
        adu_added_3_plus_count=adu_added_3_plus,
        dwelling_rebuild_count=dwelling_rebuild,
        rebuild_progress_not_started_count=rebuild_progress_not_started,
        rebuild_progress_rebuilding_count=rebuild_progress_rebuilding,
        property_sold_post_fire_count=property_sold,
        property_active_listing_count=property_listed,
    )


def aggregate_burn_area(
    parcels: list[ParcelResult],
    generated_at: str,
) -> SummaryResult:
    counts = count_parcels(parcels)
    return SummaryResult(generated_at=generated_at, **asdict(counts))
