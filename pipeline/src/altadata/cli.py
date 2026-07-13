"""End-to-end pipeline entrypoint."""

from __future__ import annotations

import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import click
from dotenv import load_dotenv

from .outputs.csv_writer import write_parcels_csv
from .outputs.fire_perimeter_writer import write_fire_perimeter_geojson
from .outputs.geojson_writer import (
    write_parcels_compact_geojson,
    write_parcels_geojson,
)
from .outputs.raw_writer import write_raw_records
from .outputs.region_writer import write_regions_geojson
from .outputs.summary_writer import write_summary_json
from .processing.aggregate import aggregate_burn_area
from .processing.extraction_compare import (
    ExtractionRunInfo,
    extraction_metrics,
    override_with_llm,
)
from .processing.geometry import bounding_envelope, circle_from_bounds
from .processing.join import JoinedParcel, join_cases_to_parcels
from .processing.llm_extraction import (
    ExtractionCache,
    extract_structures,
    load_cache,
    prune_cache,
    save_cache,
)
from .processing.llm_prompts import ParcelContext
from .processing.llm_provider import LLMError, OpenRouterProvider
from .processing.normalize import filter_active_cases
from .processing.parcel_analysis import (
    ParcelResult,
    analyze_parcel,
    filter_fire_cases,
    pre_fire_summary,
    select_qualifying_records,
)
from .processing.sales import (
    INCREMENTAL_SALE_DAYS,
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
from .processing.spatial_aggregate import aggregate_by_region
from .qc.aggregate import QcFailedError, check_thresholds
from .qc.per_record import RecordWarning, check_record, check_spatial_assignment
from .qc.report import QcReport, enforce, print_report, write_report
from .qc.status import summarize_statuses
from .sources.census import fetch_census_block_groups, fetch_census_tracts
from .sources.dins import fetch_dins_parcels
from .sources.epicla import fetch_epicla_cases
from .sources.epicla_case_history import fetch_case_history_sb1123
from .sources.fire_perimeter import fetch_fire_perimeter
from .sources.rentcast import (
    RentCastError,
    fetch_rentcast_properties,
    fetch_rentcast_sale_listings,
)
from .sources.schemas import DinsParcel, EpicCase, FirePerimeter

logger = logging.getLogger("altadata")


@click.command()
@click.option(
    "--out-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("data"),
    show_default=True,
    help="Directory to write parcels.geojson, summary.json, qc-report.json into.",
)
@click.option(
    "--log-level",
    default="INFO",
    show_default=True,
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
)
@click.option(
    "--llm-extraction/--no-llm-extraction",
    default=True,
    show_default=True,
    help="Enable LLM-based structure extraction (requires OPENROUTER_API_KEY in env).",
)
@click.option(
    "--llm-model",
    default="anthropic/claude-haiku-4.5",
    show_default=True,
    help="OpenRouter routing string for the model.",
)
@click.option(
    "--llm-cache-path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Path to llm-extraction-cache.json (default: <out-dir>/llm-extraction-cache.json).",  # noqa: E501
)
@click.option(
    "--rentcast/--no-rentcast",
    default=True,
    show_default=True,
    help="Enable RentCast sales/listings overlay (requires RENTCAST_API_KEY in env).",
)
@click.option(
    "--rentcast-full-refresh",
    is_flag=True,
    default=False,
    help="Force a full post-fire sales backfill instead of the cheap incremental "
    "window (use for the periodic reconcile).",
)
@click.option(
    "--rentcast-cache-path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Path to rentcast-cache.json (default: <out-dir>/rentcast-cache.json).",
)
def run(
    out_dir: Path,
    log_level: str,
    llm_extraction: bool,
    llm_model: str,
    llm_cache_path: Path | None,
    rentcast: bool,
    rentcast_full_refresh: bool,
    rentcast_cache_path: Path | None,
) -> None:
    """Fetch sources, join, analyze, QC, and write outputs."""
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )
    # .env is loaded for local development; CI sets env vars directly.
    load_dotenv(Path.cwd() / ".env")
    out_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(UTC).isoformat(timespec="seconds")

    cache_path = llm_cache_path or (out_dir / "llm-extraction-cache.json")

    logger.info("fetching DINS parcels")
    parcels = fetch_dins_parcels()
    logger.info("fetched %d DINS parcels", len(parcels))
    write_raw_records(
        cast(list[dict[str, Any]], parcels),
        out_dir / "source-dins.json",
        source_name="2025_Parcels_with_DINS_data",
        fetched_at=generated_at,
    )

    logger.info("fetching EPIC-LA cases")
    cases = fetch_epicla_cases()
    logger.info("fetched %d EPIC-LA cases", len(cases))
    write_raw_records(
        cast(list[dict[str, Any]], cases),
        out_dir / "source-epicla.json",
        source_name="EPICLA_Eaton_Palisades",
        fetched_at=generated_at,
    )

    logger.info("fetching Eaton Fire perimeter")
    perimeter = fetch_fire_perimeter()
    logger.info("fetched %d perimeter polygons", len(perimeter))
    write_raw_records(
        cast(list[dict[str, Any]], perimeter),
        out_dir / "source-fire-perimeter.json",
        source_name="Eaton_Fire_Perimeter",
        fetched_at=generated_at,
    )

    if not parcels or not cases or not perimeter:
        logger.error("source returned zero rows; refusing to publish")
        sys.exit(2)

    # SB-1123 small-lot subdivisions are filed without a disaster tag, so they
    # never appear in the Eaton-tagged EPIC view. Pull them from the county-wide
    # Case History, bounded to the burn-area envelope + post-fire date, and merge
    # them in. An empty result is fine — it just means no SB-1123 cases yet.
    logger.info("fetching SB-1123 cases from EPIC-LA Case History")
    case_history = fetch_case_history_sb1123(bounding_envelope(perimeter))
    logger.info("fetched %d SB-1123 case-history cases", len(case_history))
    write_raw_records(
        cast(list[dict[str, Any]], case_history),
        out_dir / "source-epicla-case-history.json",
        source_name="EPIC-LA_Case_History",
        fetched_at=generated_at,
    )
    cases = _merge_cases(cases, case_history)

    # Audit STATUS values across all fire cases BEFORE dropping inactive ones, so
    # the report can show what was dropped and flag any unclassified status. Then
    # drop terminal-negative cases (voided/cancelled/etc.) so they never count
    # toward any downstream metric. Raw snapshots above keep the full pull.
    status_summary = summarize_statuses(filter_fire_cases(cases))
    cases = filter_active_cases(cases)
    logger.info(
        "EPIC-LA status: %d fire cases, %d dropped as inactive, %d unrecognized",
        status_summary.total_cases,
        status_summary.dropped_total,
        status_summary.unrecognized_total,
    )

    logger.info("fetching census tracts within perimeter envelope")
    tracts = fetch_census_tracts(perimeter)
    logger.info("fetched %d census tracts", len(tracts))
    write_raw_records(
        cast(list[dict[str, Any]], tracts),
        out_dir / "source-2020-census-tracts.json",
        source_name="2020_Census_Tracts",
        fetched_at=generated_at,
    )

    logger.info("fetching census block groups for fetched tracts")
    block_groups = fetch_census_block_groups(tracts)
    logger.info("fetched %d census block groups", len(block_groups))
    write_raw_records(
        cast(list[dict[str, Any]], block_groups),
        out_dir / "source-2020-census-block-groups.json",
        source_name="2020_Census_Block_Groups",
        fetched_at=generated_at,
    )

    if not tracts or not block_groups:
        logger.error("census source returned zero rows; refusing to publish")
        sys.exit(2)

    joined = join_cases_to_parcels(parcels, cases)

    provider, llm_disabled_reason = _maybe_build_provider(llm_extraction, llm_model)
    extraction_cache = (
        load_cache(cache_path) if provider is not None else ExtractionCache()
    )
    if provider is not None:
        logger.info(
            "LLM extraction enabled (model=%s); cache has %d entries",
            provider.model_id,
            len(extraction_cache.entries),
        )
    else:
        logger.warning("LLM extraction disabled: %s", llm_disabled_reason)

    results, llm_warnings, run_info = _analyze_all(
        joined,
        provider=provider,
        cache=extraction_cache,
        cache_path=cache_path,
    )
    pairs = [(r, jp.din) for jp, r in zip(joined, results, strict=True)]

    if provider is not None:
        prune_cache(extraction_cache, valid_ains={r.ain for r in results})
        save_cache(cache_path, extraction_cache)
        logger.info(
            "LLM cache saved to %s (%d entries; %d cache hits, %d misses, %d failures)",
            cache_path,
            len(extraction_cache.entries),
            run_info.cache_hits,
            run_info.cache_misses,
            run_info.parcels_failed,
        )

    # Overlay RentCast post-fire sales + active listings onto the results before
    # any aggregation or output, so the "Property Sales" counts and the per-parcel
    # popup fields flow through the same single-source-of-truth paths as every
    # other metric. RentCast is supplementary: failures degrade to cached data.
    sales_cache_path = rentcast_cache_path or (out_dir / "rentcast-cache.json")
    sales_cache, sales_warnings = _collect_sales(
        enabled=rentcast,
        full_refresh=rentcast_full_refresh,
        parcels=parcels,
        perimeter=perimeter,
        cache_path=sales_cache_path,
        out_dir=out_dir,
        generated_at=generated_at,
    )
    apply_sales(results, sales_cache)

    tract_aggregation = aggregate_by_region(
        pairs,
        cast(list[dict[str, Any]], tracts),
        id_fields=["CT20", "LABEL"],
    )
    block_group_aggregation = aggregate_by_region(
        pairs,
        cast(list[dict[str, Any]], block_groups),
        id_fields=["BG20", "CT20", "LABEL"],
    )

    record_warnings: list[RecordWarning] = list(llm_warnings)
    record_warnings.extend(sales_warnings)
    if not llm_extraction:
        record_warnings.append(
            RecordWarning(
                ain="*",
                code="llm_disabled",
                detail=llm_disabled_reason or "LLM extraction disabled by flag",
                severity="info",
            )
        )
    for jp, res in zip(joined, results, strict=True):
        record_warnings.extend(check_record(jp, res))
    record_warnings.extend(check_spatial_assignment(tract_aggregation.unassigned_ains))

    thresholds = check_thresholds(
        joined,
        results,
        record_warnings,
        tract_aggregation=tract_aggregation,
        block_group_aggregation=block_group_aggregation,
        status_summary=status_summary,
    )
    report = QcReport(
        generated_at=generated_at,
        total_parcels=len(results),
        warnings=record_warnings,
        thresholds=thresholds,
        extraction_comparison=extraction_metrics(run_info, record_warnings),
        status_distribution=status_summary.to_dict(),
    )
    print_report(report)
    write_report(report, out_dir / "qc-report.json")

    try:
        enforce(report)
    except QcFailedError as exc:
        logger.error("aborting: %s", exc)
        sys.exit(3)

    summary = aggregate_burn_area(results, generated_at)
    write_summary_json(summary, out_dir / "summary.json")

    write_parcels_geojson(pairs, out_dir / "parcels.geojson", generated_at=generated_at)
    write_parcels_compact_geojson(
        list(zip(results, joined, strict=True)),
        out_dir / "parcels-compact.geojson",
        generated_at=generated_at,
    )
    write_parcels_csv(results, out_dir / "parcels.csv")

    write_fire_perimeter_geojson(
        perimeter, out_dir / "fire-perimeter.geojson", generated_at=generated_at
    )

    write_regions_geojson(
        tract_aggregation.features,
        out_dir / "2020-census-tracts.geojson",
        generated_at=generated_at,
    )
    write_regions_geojson(
        block_group_aggregation.features,
        out_dir / "2020-census-block-groups.geojson",
        generated_at=generated_at,
    )

    logger.info("wrote outputs to %s", out_dir)


def _collect_sales(
    *,
    enabled: bool,
    full_refresh: bool,
    parcels: list[DinsParcel],
    perimeter: list[FirePerimeter],
    cache_path: Path,
    out_dir: Path,
    generated_at: str,
) -> tuple[SalesCache, list[RecordWarning]]:
    """Fetch RentCast sales/listings, upsert into the cache, and return it.

    Never raises: RentCast is supplementary, so a missing key or fetch failure
    logs a warning and falls back to the last-good cache (empty on a cold start),
    so the daily release always publishes. The returned warnings surface in the
    QC report.
    """
    cache = load_sales_cache(cache_path)
    warnings: list[RecordWarning] = []
    props: list[Any] = []
    listings: list[Any] = []

    if not enabled:
        warnings.append(
            RecordWarning(
                ain="*",
                code="rentcast_disabled",
                detail="RentCast overlay disabled by --no-rentcast",
                severity="info",
            )
        )
    elif not os.environ.get("RENTCAST_API_KEY"):
        warnings.append(
            RecordWarning(
                ain="*",
                code="rentcast_disabled",
                detail="RENTCAST_API_KEY not set; reusing cached sales data",
                severity="info",
            )
        )
    else:
        try:
            index = build_parcels_index(parcels)
            lat, lon, radius = circle_from_bounds(bounding_envelope(perimeter))
            # Full since-fire sweep on a cold cache, when forced, or when the
            # periodic reconcile is due; otherwise the cheap rolling window.
            do_full = (
                full_refresh
                or not cache.backfill_done
                or full_refresh_due(cache, generated_at)
            )
            window = (
                full_backfill_days(generated_at) if do_full else INCREMENTAL_SALE_DAYS
            )
            logger.info(
                "fetching RentCast (%s; saleDateRange=%d days; "
                "center=%.4f,%.4f r=%.2fmi)",
                "full reconcile" if do_full else "incremental",
                window,
                lat,
                lon,
                radius,
            )
            props = list(
                fetch_rentcast_properties(lat, lon, radius, sale_date_range=window)
            )
            listings = list(fetch_rentcast_sale_listings(lat, lon, radius))
            logger.info(
                "RentCast returned %d sold-property records, %d active listings",
                len(props),
                len(listings),
            )

            new_sold = normalize_properties(props, index)
            cache.sold.update(new_sold)
            cache.listings = normalize_listings(listings, index)
            cache.backfill_done = True
            cache.generated_at = generated_at
            if do_full:
                cache.last_full_refresh = generated_at
            prune_sales_cache(cache, {p["AIN_1"] for p in parcels})
            save_sales_cache(cache_path, cache)
            logger.info(
                "RentCast cache saved to %s (%d post-fire sales, %d active listings)",
                cache_path,
                len(cache.sold),
                len(cache.listings),
            )

            # Surface likely join drift: records came back but none matched a
            # parcel (e.g. RentCast changed its assessorID/address format).
            if (props or listings) and not new_sold and not cache.listings:
                warnings.append(
                    RecordWarning(
                        ain="*",
                        code="rentcast_no_matches",
                        detail=(
                            f"RentCast returned {len(props)} properties + "
                            f"{len(listings)} listings but none joined to a parcel"
                        ),
                        severity="data",
                    )
                )
        except RentCastError as exc:
            logger.warning("RentCast fetch failed (%s); reusing cached sales", exc)
            warnings.append(
                RecordWarning(
                    ain="*",
                    code="rentcast_fetch_failed",
                    detail=str(exc),
                    severity="data",
                )
            )

    # Always snapshot the raw pulls (empty when disabled/failed) so the published
    # release + audit trail carry a RentCast source file every run.
    write_raw_records(
        cast(list[dict[str, Any]], props),
        out_dir / "source-rentcast-properties.json",
        source_name="RentCast /properties",
        fetched_at=generated_at,
    )
    write_raw_records(
        cast(list[dict[str, Any]], listings),
        out_dir / "source-rentcast-sale-listings.json",
        source_name="RentCast /listings/sale",
        fetched_at=generated_at,
    )

    return cache, warnings


def _maybe_build_provider(
    enabled: bool,
    model_id: str,
) -> tuple[OpenRouterProvider | None, str | None]:
    if not enabled:
        return None, "disabled by --no-llm-extraction"
    try:
        return OpenRouterProvider(model_id=model_id), None
    except LLMError as exc:
        return None, str(exc)


def _merge_cases(base: list[EpicCase], extra: list[EpicCase]) -> list[EpicCase]:
    """Append supplemental cases, skipping any CASENUMBER already present.

    SB-1123 case-history records carry a null disaster type so they shouldn't
    collide with the Eaton view, but we dedupe on CASENUMBER as a safety net.
    """
    seen = {c.get("CASENUMBER") for c in base if c.get("CASENUMBER")}
    merged = list(base)
    for case in extra:
        number = case.get("CASENUMBER")
        if number and number in seen:
            continue
        merged.append(case)
        if number:
            seen.add(number)
    return merged


def _analyze_all(
    joined: list[JoinedParcel],
    *,
    provider: OpenRouterProvider | None,
    cache: ExtractionCache,
    cache_path: Path,
) -> tuple[list[ParcelResult], list[RecordWarning], ExtractionRunInfo]:
    """Run analyze_parcel on each joined parcel; if a provider is given, run
    LLM extraction in parallel and overlay its result.

    The cache is flushed atomically to ``cache_path`` after every cache miss,
    so a hard kill cannot lose completed extractions.
    """
    results: list[ParcelResult] = []
    warnings: list[RecordWarning] = []
    parcels_attempted = 0
    parcels_extracted = 0
    parcels_failed = 0
    plan_only_parcels = 0
    cache_hits = 0
    cache_misses = 0

    for jp in joined:
        result = analyze_parcel(jp)
        if provider is None:
            results.append(result)
            continue

        # cases are already inactive-filtered globally; wrap defensively so this
        # path stays correct if called on an unfiltered list (mirrors
        # analyze_parcel).
        fire_cases = filter_active_cases(filter_fire_cases(jp.cases))
        qualifying = select_qualifying_records(fire_cases)
        has_qualifying_permit = any(
            c.get("MODULENAME") == "PermitManagement" for c in qualifying
        )
        if not qualifying:
            results.append(result)
            continue

        parcels_attempted += 1
        if not has_qualifying_permit:
            plan_only_parcels += 1

        ctx = ParcelContext(
            ain=result.ain,
            address=result.address,
            damage=result.damage.value
            if hasattr(result.damage, "value")
            else str(result.damage),
            pre_fire_summary=pre_fire_summary(jp.din),
        )
        cache_size_before = len(cache.entries)
        extraction = extract_structures(ctx, qualifying, provider=provider, cache=cache)
        if extraction is None:
            parcels_failed += 1
            warnings.append(
                RecordWarning(
                    ain=result.ain,
                    code="llm_extraction_failed",
                    detail="LLM call failed or returned unparseable output",
                    severity="data",
                )
            )
            results.append(result)
            continue
        parcels_extracted += 1
        if len(cache.entries) > cache_size_before:
            cache_misses += 1
            save_cache(cache_path, cache)
        else:
            cache_hits += 1

        new_result, issues = override_with_llm(
            result, extraction, has_qualifying_permit=has_qualifying_permit
        )
        for issue in issues:
            warnings.append(
                RecordWarning(
                    ain=new_result.ain,
                    code=issue.code,
                    detail=issue.detail,
                    severity=issue.severity,
                )
            )
        results.append(new_result)

    info = ExtractionRunInfo(
        enabled=provider is not None,
        model=provider.model_id if provider else "",
        prompt_version=cache.prompt_version,
        parcels_attempted=parcels_attempted,
        parcels_extracted=parcels_extracted,
        parcels_failed=parcels_failed,
        plan_only_parcels=plan_only_parcels,
        cache_hits=cache_hits,
        cache_misses=cache_misses,
    )
    return results, warnings, info


if __name__ == "__main__":  # pragma: no cover
    run()
