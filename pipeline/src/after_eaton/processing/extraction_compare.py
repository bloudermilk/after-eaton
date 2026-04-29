"""Compare regex vs LLM extractions per-parcel; surface disagreements as warnings.

The regex path remains the cross-validation channel: it always runs on
PermitManagement records (current behavior). When the LLM extractor produces
output, we bucket its structures into the same per-type counts/sqft shape as
the regex output and compare. Disagreements are emitted as ``info``-severity
warnings; the LLM result wins on disagreement (but both are recorded).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

from ..qc.per_record import RecordWarning
from .llm_extraction import LLMExtraction
from .parcel_analysis import ParcelResult, PostFire, SfrSizeComparison

_IDENTICAL_TOLERANCE = 10  # sqft — must match parcel_analysis._IDENTICAL_TOLERANCE

_RESIDENTIAL_TYPES = ("sfr", "adu", "sb9", "mfr")
_SQFT_DISAGREEMENT_RATIO = 0.10  # > 10% delta = flag as sqft disagreement


def override_with_llm(
    result: ParcelResult,
    extraction: LLMExtraction,
    *,
    has_qualifying_permit: bool,
) -> tuple[ParcelResult, list[ComparisonIssue]]:
    """Apply an LLM extraction to a regex-derived ParcelResult.

    Returns a new ParcelResult with post_* fields replaced (and the few derived
    flags that depend on them recomputed) plus the comparison issues to surface
    as per-record warnings.

    ``has_qualifying_permit`` indicates whether the regex path had a
    PermitManagement record to extract from — used to distinguish "regex
    disagrees" from "regex had no opinion (plan-only parcel)".
    """
    llm_post = derive_post_from_llm(extraction)
    regex_post_for_compare = (
        PostFire(
            sfr_count=result.post_sfr_count,
            sfr_sqft=result.post_sfr_sqft,
            adu_count=result.post_adu_count,
            adu_sqft=result.post_adu_sqft,
            mfr_count=result.post_mfr_count,
            mfr_sqft=result.post_mfr_sqft,
            sb9_count=result.post_sb9_count,
            sb9_sqft=result.post_sb9_sqft,
        )
        if has_qualifying_permit
        else None
    )
    issues = compare_extractions(
        regex_post_for_compare, llm_post, extraction=extraction
    )

    new_result = dataclasses.replace(
        result,
        post_sfr_count=llm_post.sfr_count,
        post_sfr_sqft=llm_post.sfr_sqft,
        post_adu_count=llm_post.adu_count,
        post_adu_sqft=llm_post.adu_sqft,
        post_mfr_count=llm_post.mfr_count,
        post_mfr_sqft=llm_post.mfr_sqft,
        post_sb9_count=llm_post.sb9_count,
        post_sb9_sqft=llm_post.sb9_sqft,
        adds_sb9=bool(llm_post.sb9_count and llm_post.sb9_count > 0),
        added_adu_count=max(0, (llm_post.adu_count or 0) - result.pre_adu_count),
        sfr_size_comparison=_compare_sfr(result.pre_sfr_sqft, llm_post.sfr_sqft),
    )
    return new_result, issues


def _compare_sfr(
    pre_sqft: int | None,
    post_sqft: int | None,
) -> SfrSizeComparison | None:
    """Mirror of parcel_analysis._compare_sfr — kept here to avoid a circular import."""
    if pre_sqft is None or post_sqft is None:
        return None
    diff = post_sqft - pre_sqft
    if abs(diff) <= _IDENTICAL_TOLERANCE:
        return "identical"
    return "larger" if diff > 0 else "smaller"


@dataclass(frozen=True)
class ComparisonIssue:
    """One disagreement / signal worth surfacing as a per-record QC warning."""

    code: str
    severity: str
    detail: str


def derive_post_from_llm(extraction: LLMExtraction) -> PostFire:
    """Bucket an LLMExtraction's structures into the existing PostFire shape.

    Counts each residential structure once; sums sqft within type. Only the
    residential types (sfr/adu/sb9/mfr) flow through; garage/repair/other
    structures the LLM identifies are dropped here (they don't map onto the
    output schema).
    """
    counts: dict[str, int] = {t: 0 for t in _RESIDENTIAL_TYPES}
    sqfts: dict[str, list[int]] = {t: [] for t in _RESIDENTIAL_TYPES}
    for s in extraction.structures:
        t = s.struct_type
        if t == "jadu":
            t = "adu"  # jadu rolls up under adu in the existing schema
        if t not in counts:
            continue
        counts[t] += 1
        if s.sqft is not None:
            sqfts[t].append(s.sqft)

    return PostFire(
        sfr_count=counts["sfr"],
        sfr_sqft=sum(sqfts["sfr"]) if sqfts["sfr"] else None,
        adu_count=counts["adu"],
        adu_sqft=sum(sqfts["adu"]) if sqfts["adu"] else None,
        mfr_count=counts["mfr"],
        mfr_sqft=sum(sqfts["mfr"]) if sqfts["mfr"] else None,
        sb9_count=counts["sb9"],
        sb9_sqft=sum(sqfts["sb9"]) if sqfts["sb9"] else None,
    )


def compare_extractions(
    regex: PostFire | None,
    llm: PostFire,
    *,
    extraction: LLMExtraction,
) -> list[ComparisonIssue]:
    """Compare regex (may be None for plan-only parcels) vs LLM-derived PostFire.

    Returns the issues to surface as per-record warnings.
    """
    issues: list[ComparisonIssue] = []

    if regex is None:
        # Plan-only parcel — regex has no opinion. Surface that we relied on LLM.
        if any(_struct_count(llm, t) for t in _RESIDENTIAL_TYPES):
            issues.append(
                ComparisonIssue(
                    code="extraction_only_llm",
                    severity="info",
                    detail=(
                        "no qualifying PermitManagement record; structures "
                        "inferred from PlanManagement records via LLM"
                    ),
                )
            )
    else:
        for t in _RESIDENTIAL_TYPES:
            r_count = _struct_count(regex, t)
            l_count = _struct_count(llm, t)
            r_sqft = _struct_sqft(regex, t)
            l_sqft = _struct_sqft(llm, t)
            if r_count != l_count:
                issues.append(
                    ComparisonIssue(
                        code="extraction_count_disagreement",
                        severity="info",
                        detail=(
                            f"{t}: regex={r_count}, llm={l_count}; "
                            f"reasoning: {extraction.reasoning[:160]}"
                        ),
                    )
                )
            elif (
                r_sqft is not None
                and l_sqft is not None
                and r_sqft > 0
                and abs(r_sqft - l_sqft) / r_sqft > _SQFT_DISAGREEMENT_RATIO
            ):
                issues.append(
                    ComparisonIssue(
                        code="extraction_sqft_disagreement",
                        severity="info",
                        detail=f"{t}: regex_sqft={r_sqft}, llm_sqft={l_sqft}",
                    )
                )

    if any(s.confidence == "low" for s in extraction.structures):
        issues.append(
            ComparisonIssue(
                code="extraction_low_confidence",
                severity="info",
                detail=(
                    "LLM marked at least one structure as low-confidence; "
                    f"reasoning: {extraction.reasoning[:160]}"
                ),
            )
        )

    return issues


def _struct_count(post: PostFire, type_name: str) -> int:
    val = getattr(post, f"{type_name}_count")
    return int(val) if val else 0


def _struct_sqft(post: PostFire, type_name: str) -> int | None:
    val = getattr(post, f"{type_name}_sqft")
    return int(val) if val is not None else None


# Warning codes emitted by the comparator + LLM-extraction pipeline.
EXTRACTION_WARNING_CODES = frozenset(
    {
        "extraction_count_disagreement",
        "extraction_sqft_disagreement",
        "extraction_only_llm",
        "extraction_low_confidence",
        "llm_extraction_failed",
    }
)


@dataclass(frozen=True)
class ExtractionRunInfo:
    """Per-run context for the LLM-extraction pass; folded into qc-report.json."""

    enabled: bool
    model: str
    prompt_version: int
    parcels_attempted: int
    parcels_extracted: int  # successful LLM responses
    parcels_failed: int  # LLM call errored
    plan_only_parcels: int  # parcels with no qualifying PermitManagement record
    cache_hits: int
    cache_misses: int


def extraction_metrics(
    info: ExtractionRunInfo, warnings: list[RecordWarning]
) -> dict[str, Any]:
    """Compose the ``extraction_comparison`` block for qc-report.json."""
    by_code: dict[str, set[str]] = {code: set() for code in EXTRACTION_WARNING_CODES}
    for w in warnings:
        if w.code in by_code:
            by_code[w.code].add(w.ain)

    disagreements = len(by_code["extraction_count_disagreement"]) + len(
        by_code["extraction_sqft_disagreement"]
    )
    agreement_rate = (
        1.0 - disagreements / info.parcels_extracted if info.parcels_extracted else 1.0
    )

    return {
        "enabled": info.enabled,
        "model": info.model,
        "prompt_version": info.prompt_version,
        "parcels_attempted": info.parcels_attempted,
        "parcels_extracted": info.parcels_extracted,
        "parcels_failed": info.parcels_failed,
        "plan_only_parcels": info.plan_only_parcels,
        "cache_hits": info.cache_hits,
        "cache_misses": info.cache_misses,
        "agreement_rate": round(agreement_rate, 4),
        "count_disagreements": len(by_code["extraction_count_disagreement"]),
        "sqft_disagreements": len(by_code["extraction_sqft_disagreement"]),
        "low_confidence_parcels": len(by_code["extraction_low_confidence"]),
        "extraction_failures": len(by_code["llm_extraction_failed"]),
    }
