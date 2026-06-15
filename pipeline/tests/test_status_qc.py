"""Status audit (qc/status.py) and the unrecognized-status hard-fail gate."""

from __future__ import annotations

from typing import Any

from altadata.qc.aggregate import UNRECOGNIZED_STATUS_MAX, check_thresholds
from altadata.qc.status import summarize_statuses
from altadata.sources.schemas import EpicCase


def _case(status: Any) -> EpicCase:
    base: dict[str, Any] = {
        "MAIN_AIN": "1",
        "MODULENAME": "PlanManagement",
        "STATUS": status,
    }
    return base  # type: ignore[return-value]


def test_summarize_classifies_and_counts() -> None:
    cases = [
        _case("Issued"),
        _case("Issued"),
        _case("Void"),
        _case(None),
        _case("Mystery Status"),
    ]
    summary = summarize_statuses(cases)
    assert summary.total_cases == 5
    assert summary.dropped_total == 1
    assert summary.unrecognized_total == 1

    d = summary.to_dict()
    assert d["total_cases"] == 5
    assert d["dropped_total"] == 1
    assert d["unrecognized_total"] == 1
    # Sorted by count descending — the two "Issued" cases lead.
    assert d["statuses"][0] == {
        "status": "Issued",
        "count": 2,
        "classification": "active",
    }
    by_status = {s["status"]: s["classification"] for s in d["statuses"]}
    assert by_status["Void"] == "inactive"
    assert by_status["(none)"] == "active"
    assert by_status["Mystery Status"] == "unrecognized"


def test_null_status_not_counted_as_unrecognized() -> None:
    summary = summarize_statuses([_case(None), _case(""), _case("   ")])
    assert summary.unrecognized_total == 0
    assert summary.counts["(none)"] == 3


def test_gate_passes_at_limit() -> None:
    cases = [_case(f"Unknown {i}") for i in range(UNRECOGNIZED_STATUS_MAX)]
    summary = summarize_statuses(cases)
    checks = check_thresholds([], [], [], status_summary=summary)
    gate = next(c for c in checks if c.name == "unrecognized_status_count")
    assert gate.passed is True
    assert gate.actual == float(UNRECOGNIZED_STATUS_MAX)


def test_gate_fails_above_limit() -> None:
    cases = [_case(f"Unknown {i}") for i in range(UNRECOGNIZED_STATUS_MAX + 1)]
    summary = summarize_statuses(cases)
    checks = check_thresholds([], [], [], status_summary=summary)
    gate = next(c for c in checks if c.name == "unrecognized_status_count")
    assert gate.passed is False


def test_gate_absent_when_no_summary() -> None:
    checks = check_thresholds([], [], [])
    assert all(c.name != "unrecognized_status_count" for c in checks)
