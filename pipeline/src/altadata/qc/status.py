"""EPIC-LA case-status audit for the QC report.

Summarizes the `STATUS` values seen across fire cases *before* the inactive
filter runs, so the report can show what was dropped and surface any status the
pipeline has never classified. The `unrecognized_total` here feeds the
`unrecognized_status_count` hard-fail gate in `qc/aggregate.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..processing.normalize import (
    is_active_status,
    is_recognized_status,
)
from ..sources.schemas import EpicCase

_NULL_LABEL = "(none)"


def _classify(status: str | None) -> str:
    if not is_recognized_status(status):
        return "unrecognized"
    if not is_active_status(status):
        return "inactive"
    return "active"


@dataclass(frozen=True)
class StatusSummary:
    """Per-status counts and classification across a set of fire cases."""

    # Raw STATUS string (null/empty shown as "(none)") -> case count.
    counts: dict[str, int] = field(default_factory=dict)
    # Raw STATUS string -> "active" | "inactive" | "unrecognized".
    classifications: dict[str, str] = field(default_factory=dict)

    @property
    def total_cases(self) -> int:
        return sum(self.counts.values())

    @property
    def dropped_total(self) -> int:
        return sum(
            n
            for label, n in self.counts.items()
            if self.classifications.get(label) == "inactive"
        )

    @property
    def unrecognized_total(self) -> int:
        return sum(
            n
            for label, n in self.counts.items()
            if self.classifications.get(label) == "unrecognized"
        )

    def to_dict(self) -> dict[str, Any]:
        """Serializable audit block for qc-report.json, sorted by count desc."""
        statuses = [
            {
                "status": label,
                "count": self.counts[label],
                "classification": self.classifications[label],
            }
            for label in sorted(
                self.counts, key=lambda label: (-self.counts[label], label)
            )
        ]
        return {
            "total_cases": self.total_cases,
            "dropped_total": self.dropped_total,
            "unrecognized_total": self.unrecognized_total,
            "statuses": statuses,
        }


def summarize_statuses(cases: list[EpicCase]) -> StatusSummary:
    """Tally STATUS values across ``cases`` (call on the pre-filter fire set)."""
    counts: dict[str, int] = {}
    classifications: dict[str, str] = {}
    for case in cases:
        raw = case.get("STATUS")
        label = raw.strip() if isinstance(raw, str) and raw.strip() else _NULL_LABEL
        counts[label] = counts.get(label, 0) + 1
        classifications.setdefault(label, _classify(raw))
    return StatusSummary(counts=counts, classifications=classifications)
