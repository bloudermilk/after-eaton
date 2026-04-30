"""End-to-end pipeline entrypoint."""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import click
from dotenv import load_dotenv

from .outputs.csv_writer import write_parcels_csv
from .outputs.geojson_writer import write_parcels_geojson
from .outputs.raw_writer import write_raw_records
from .outputs.region_writer import write_regions_geojson
from .outputs.summary_writer import write_summary_json
from .processing.aggregate import aggregate_burn_area
from .processing.extraction_compare import (
    ExtractionRunInfo,
    extraction_metrics,
    override_with_llm,
)
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
from .processing.parcel_analysis import (
    ParcelResult,
    analyze_parcel,
    filter_fire_cases,
    pre_fire_summary,
    select_qualifying_records,
)
from .processing.spatial_aggregate import aggregate_by_region
from .qc.aggregate import QcFailedError, check_thresholds
from .qc.per_record import RecordWarning, check_record, check_spatial_assignment
from .qc.report import QcReport, enforce, print_report, write_report
from .sources.census import fetch_census_block_groups, fetch_census_tracts
from .sources.dins import fetch_dins_parcels
from .sources.epicla import fetch_epicla_cases
from .sources.fire_perimeter import fetch_fire_perimeter

logger = logging.getLogger("after_eaton")


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
def run(
    out_dir: Path,
    log_level: str,
    llm_extraction: bool,
    llm_model: str,
    llm_cache_path: Path | None,
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
        joined, provider=provider, cache=extraction_cache
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
    )
    report = QcReport(
        generated_at=generated_at,
        total_parcels=len(results),
        warnings=record_warnings,
        thresholds=thresholds,
        extraction_comparison=extraction_metrics(run_info, record_warnings),
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
    write_parcels_csv(results, out_dir / "parcels.csv")

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


def _analyze_all(
    joined: list[JoinedParcel],
    *,
    provider: OpenRouterProvider | None,
    cache: ExtractionCache,
) -> tuple[list[ParcelResult], list[RecordWarning], ExtractionRunInfo]:
    """Run analyze_parcel on each joined parcel; if a provider is given, run
    LLM extraction in parallel and overlay its result."""
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

        fire_cases = filter_fire_cases(jp.cases)
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
