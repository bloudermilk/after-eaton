"""End-to-end pipeline entrypoint."""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import click

from .outputs.geojson_writer import write_parcels_geojson
from .outputs.raw_writer import write_raw_records
from .outputs.region_writer import write_regions_geojson
from .outputs.summary_writer import write_summary_json
from .processing.aggregate import aggregate_burn_area
from .processing.join import join_cases_to_parcels
from .processing.parcel_analysis import analyze_parcel
from .processing.spatial_aggregate import aggregate_by_region
from .qc.aggregate import QcFailedError, check_thresholds
from .qc.per_record import check_record, check_spatial_assignment
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
def run(out_dir: Path, log_level: str) -> None:
    """Fetch sources, join, analyze, QC, and write outputs."""
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(UTC).isoformat(timespec="seconds")

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
    results = [analyze_parcel(jp) for jp in joined]
    pairs = [(r, jp.din) for jp, r in zip(joined, results, strict=True)]

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

    record_warnings = []
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


if __name__ == "__main__":  # pragma: no cover
    run()
