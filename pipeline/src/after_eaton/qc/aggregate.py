"""Dataset-level QC threshold checks (hard fail)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..processing.description_parser import parse_description
from ..processing.join import JoinedParcel
from ..processing.parcel_analysis import ParcelResult
from .per_record import RecordWarning

# Tunable thresholds — keep names stable for ops review. These are the
# original PLAN.md values; they're hard CI gates, not aspirational targets.
DESCRIPTION_PARSE_MIN_RATE = 0.90
SFR_SQFT_EXTRACTION_MIN_RATE = 0.85
WARNING_RATE_MAX = 0.05
MIN_COMPLETED_REBUILDS = 1

_EATON_DESC_RE = re.compile(r"eaton fire", re.I)
# Independent of the parser regexes, on purpose: a parser regression can't
# shrink the denominator and silently mask itself.
_SFR_KEYWORD_RE = re.compile(r"\bSF[RDH]\b|\bSINGLE[\s-]+FAMIL", re.I)
_SQFT_PROBE_RE = re.compile(r"\b\d[\d,]*\.?\d*\s*S\.?\s*[FQ]", re.I)


@dataclass(frozen=True)
class ThresholdCheck:
    name: str
    actual: float
    threshold: float
    passed: bool
    detail: str


def check_thresholds(
    joined: list[JoinedParcel],
    results: list[ParcelResult],
    warnings: list[RecordWarning],
) -> list[ThresholdCheck]:
    return [
        _description_parse_rate(joined),
        _sfr_sqft_extraction_rate(joined),
        _warning_rate(results, warnings),
        _completed_rebuild_count(results),
    ]


def _description_parse_rate(joined: list[JoinedParcel]) -> ThresholdCheck:
    """Of fire-related PermitManagement cases with a non-null DESCRIPTION,
    what fraction does the parser classify to a known type or extract a
    sqft from? Vague descriptions like "Like for Like Rebuild" are counted
    in the denominator and reported honestly as failures.
    """
    candidates = 0
    parsed_ok = 0
    for jp in joined:
        for case in jp.cases:
            if case.get("MODULENAME") != "PermitManagement":
                continue
            desc = case.get("DESCRIPTION")
            if not desc:
                continue
            if not (
                case.get("DISASTER_TYPE") == "Eaton Fire (01-2025)"
                or _EATON_DESC_RE.search(desc)
            ):
                continue
            candidates += 1
            structs = parse_description(desc)
            if structs and any(
                s.struct_type != "unknown" or s.sqft is not None for s in structs
            ):
                parsed_ok += 1

    rate = parsed_ok / candidates if candidates else 1.0
    return ThresholdCheck(
        name="description_parse_rate",
        actual=rate,
        threshold=DESCRIPTION_PARSE_MIN_RATE,
        passed=rate >= DESCRIPTION_PARSE_MIN_RATE,
        detail=f"{parsed_ok}/{candidates} fire permits parsed to a structure",
    )


def _sfr_sqft_extraction_rate(joined: list[JoinedParcel]) -> ThresholdCheck:
    """Of permits whose DESCRIPTION mentions an SFR keyword and a numeric
    sqft, what fraction does the parser classify as `sfr` with a sqft?

    Note: candidates include "ADU 800 SF SFD" and "DUPLEX … SFR …" — cases
    where SFR keyword is descriptor for a non-SFR primary structure. The
    parser correctly classifies these as ADU/MFR, which counts as a miss
    here. That's accepted: this metric measures end-to-end SFR-extraction
    behavior on what looks like an SFR description, not parser purity.
    """
    candidates = 0
    extracted = 0
    for jp in joined:
        for case in jp.cases:
            if case.get("MODULENAME") != "PermitManagement":
                continue
            desc = case.get("DESCRIPTION") or ""
            if not desc:
                continue
            if not (_SFR_KEYWORD_RE.search(desc) and _SQFT_PROBE_RE.search(desc)):
                continue
            candidates += 1
            structs = parse_description(desc)
            if any(s.struct_type == "sfr" and s.sqft is not None for s in structs):
                extracted += 1

    rate = extracted / candidates if candidates else 1.0
    return ThresholdCheck(
        name="sfr_sqft_extraction_rate",
        actual=rate,
        threshold=SFR_SQFT_EXTRACTION_MIN_RATE,
        passed=rate >= SFR_SQFT_EXTRACTION_MIN_RATE,
        detail=(
            f"{extracted}/{candidates} permits whose DESCRIPTION mentions "
            "SFR/SFD/SINGLE-FAMILY + sqft were parsed as sfr+sqft"
        ),
    )


def _warning_rate(
    results: list[ParcelResult],
    warnings: list[RecordWarning],
) -> ThresholdCheck:
    total = len(results) or 1
    # Only "data" warnings count — "info" warnings flag real-world ambiguity
    # (e.g. destroyed parcel with no permit yet) that can't be fixed in code.
    data_warnings = [w for w in warnings if w.severity == "data"]
    flagged = len({w.ain for w in data_warnings})
    rate = flagged / total
    return ThresholdCheck(
        name="warning_rate",
        actual=rate,
        threshold=WARNING_RATE_MAX,
        passed=rate <= WARNING_RATE_MAX,
        detail=(
            f"{flagged}/{total} parcels raised at least one data-severity "
            f"warning (info-severity warnings excluded)"
        ),
    )


def _completed_rebuild_count(results: list[ParcelResult]) -> ThresholdCheck:
    completed = sum(1 for r in results if r.rebuild_progress_num == 7)
    return ThresholdCheck(
        name="min_completed_rebuilds",
        actual=float(completed),
        threshold=float(MIN_COMPLETED_REBUILDS),
        passed=completed >= MIN_COMPLETED_REBUILDS,
        detail=f"{completed} parcels reported Construction Completed",
    )


class QcFailedError(RuntimeError):
    """Raised when one or more aggregate thresholds fail."""

    def __init__(self, failed: list[ThresholdCheck]) -> None:
        self.failed = failed
        names = ", ".join(c.name for c in failed)
        super().__init__(f"QC threshold(s) failed: {names}")
