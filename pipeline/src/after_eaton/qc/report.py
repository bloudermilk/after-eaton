"""Format and persist a QC pass/fail report."""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import IO, Any

from .aggregate import QcFailedError, ThresholdCheck
from .per_record import RecordWarning

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QcReport:
    generated_at: str
    total_parcels: int
    warnings: list[RecordWarning]
    thresholds: list[ThresholdCheck]
    # Informational metrics — included in qc-report.json but not gated.
    extraction_comparison: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.thresholds)


def write_report(report: QcReport, out_path: Path) -> None:
    payload: dict[str, Any] = {
        "generated_at": report.generated_at,
        "total_parcels": report.total_parcels,
        "passed": report.passed,
        "thresholds": [asdict(c) for c in report.thresholds],
        "warnings": [asdict(w) for w in report.warnings],
    }
    if report.extraction_comparison:
        payload["extraction_comparison"] = report.extraction_comparison
    out_path.write_text(json.dumps(payload, indent=2))


def print_report(report: QcReport, stream: IO[str] = sys.stdout) -> None:
    print("=" * 60, file=stream)
    print("QC Report", file=stream)
    print(f"  generated_at: {report.generated_at}", file=stream)
    print(f"  total parcels: {report.total_parcels}", file=stream)
    print(f"  warnings: {len(report.warnings)}", file=stream)
    print("-" * 60, file=stream)
    for c in report.thresholds:
        marker = "PASS" if c.passed else "FAIL"
        print(
            f"  [{marker}] {c.name}: actual={c.actual:.3f} "
            f"threshold={c.threshold:.3f} -- {c.detail}",
            file=stream,
        )
    if report.warnings:
        print("-" * 60, file=stream)
        print("  Per-record warnings:", file=stream)
        for w in report.warnings:
            print(f"    - {w.ain} [{w.code}] {w.detail}", file=stream)
    print("=" * 60, file=stream)


def enforce(report: QcReport) -> None:
    failed = [c for c in report.thresholds if not c.passed]
    if failed:
        raise QcFailedError(failed)
