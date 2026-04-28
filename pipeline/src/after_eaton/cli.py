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
from .outputs.summary_writer import write_summary_json
from .processing.aggregate import aggregate_burn_area
from .processing.join import join_cases_to_parcels
from .processing.parcel_analysis import analyze_parcel
from .qc.aggregate import QcFailedError, check_thresholds
from .qc.per_record import check_record
from .qc.report import QcReport, enforce, print_report, write_report
from .sources.dins import fetch_dins_parcels
from .sources.epicla import fetch_epicla_cases

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

    if not parcels or not cases:
        logger.error("source returned zero rows; refusing to publish")
        sys.exit(2)

    joined = join_cases_to_parcels(parcels, cases)
    results = [analyze_parcel(jp) for jp in joined]

    record_warnings = []
    for jp, res in zip(joined, results, strict=True):
        record_warnings.extend(check_record(jp, res))

    thresholds = check_thresholds(joined, results, record_warnings)
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

    pairs = [(r, jp.din) for jp, r in zip(joined, results, strict=True)]
    write_parcels_geojson(pairs, out_dir / "parcels.geojson", generated_at=generated_at)

    logger.info("wrote outputs to %s", out_dir)


if __name__ == "__main__":  # pragma: no cover
    run()
