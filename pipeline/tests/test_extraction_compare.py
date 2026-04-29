"""Tests for the regex-vs-LLM extraction comparator + run-info metrics."""

from __future__ import annotations

from after_eaton.processing.extraction_compare import (
    ExtractionRunInfo,
    compare_extractions,
    derive_post_from_llm,
    extraction_metrics,
)
from after_eaton.processing.llm_extraction import (
    ExtractedStructure,
    LLMExtraction,
)
from after_eaton.processing.parcel_analysis import PostFire
from after_eaton.qc.per_record import RecordWarning


def _extraction(*structures: ExtractedStructure, reasoning: str = "") -> LLMExtraction:
    return LLMExtraction(
        key="k",
        ain="A",
        extracted_at="x",
        model="m",
        prompt_version=1,
        input_case_numbers=(),
        structures=tuple(structures),
        reasoning=reasoning,
        input_tokens=0,
        output_tokens=0,
    )


def _struct(
    struct_type: str = "sfr",
    sqft: int | None = 1500,
    confidence: str = "high",
) -> ExtractedStructure:
    return ExtractedStructure(
        struct_type=struct_type,
        sqft=sqft,
        confidence=confidence,
        evidence_case_numbers=(),
        notes=None,
    )


def test_derive_post_buckets_by_type() -> None:
    extraction = _extraction(
        _struct("sfr", 1500),
        _struct("adu", 600),
        _struct("adu", 800),
        _struct("sb9", 700),
    )
    post = derive_post_from_llm(extraction)
    assert post.sfr_count == 1
    assert post.sfr_sqft == 1500
    assert post.adu_count == 2
    assert post.adu_sqft == 1400
    assert post.sb9_count == 1
    assert post.sb9_sqft == 700
    assert post.mfr_count == 0


def test_derive_post_rolls_jadu_into_adu() -> None:
    extraction = _extraction(_struct("jadu", 400))
    post = derive_post_from_llm(extraction)
    assert post.adu_count == 1
    assert post.adu_sqft == 400


def test_derive_post_drops_non_residential() -> None:
    extraction = _extraction(_struct("sfr", 1500), _struct("garage", 400))
    post = derive_post_from_llm(extraction)
    assert post.sfr_count == 1
    # garage doesn't appear in counts


def test_compare_no_issues_when_agreement() -> None:
    regex = PostFire(
        sfr_count=1,
        sfr_sqft=1500,
        adu_count=0,
        adu_sqft=None,
        mfr_count=0,
        mfr_sqft=None,
        sb9_count=0,
        sb9_sqft=None,
    )
    llm_post = derive_post_from_llm(_extraction(_struct("sfr", 1500)))
    issues = compare_extractions(
        regex, llm_post, extraction=_extraction(_struct("sfr", 1500))
    )
    assert issues == []


def test_compare_emits_count_disagreement() -> None:
    # Only differ on ADU; SFR matches.
    regex = PostFire(
        sfr_count=0,
        sfr_sqft=None,
        adu_count=4,
        adu_sqft=3192,
        mfr_count=0,
        mfr_sqft=None,
        sb9_count=0,
        sb9_sqft=None,
    )
    llm_extraction = _extraction(
        _struct("adu", 1596),
        _struct("adu", 1596),
        reasoning="four floor permits → two two-story ADUs",
    )
    llm_post = derive_post_from_llm(llm_extraction)
    issues = compare_extractions(regex, llm_post, extraction=llm_extraction)
    codes = [i.code for i in issues]
    assert "extraction_count_disagreement" in codes
    detail = next(i.detail for i in issues if i.code == "extraction_count_disagreement")
    assert "adu" in detail


def test_compare_emits_sqft_disagreement_when_counts_match() -> None:
    regex = PostFire(
        sfr_count=1,
        sfr_sqft=1000,
        adu_count=0,
        adu_sqft=None,
        mfr_count=0,
        mfr_sqft=None,
        sb9_count=0,
        sb9_sqft=None,
    )
    llm_extraction = _extraction(_struct("sfr", 1500))
    llm_post = derive_post_from_llm(llm_extraction)
    issues = compare_extractions(regex, llm_post, extraction=llm_extraction)
    codes = [i.code for i in issues]
    assert "extraction_sqft_disagreement" in codes


def test_compare_no_sqft_disagreement_within_tolerance() -> None:
    regex = PostFire(
        sfr_count=1,
        sfr_sqft=1500,
        adu_count=0,
        adu_sqft=None,
        mfr_count=0,
        mfr_sqft=None,
        sb9_count=0,
        sb9_sqft=None,
    )
    # 5% delta — under 10% tolerance
    llm_extraction = _extraction(_struct("sfr", 1575))
    llm_post = derive_post_from_llm(llm_extraction)
    issues = compare_extractions(regex, llm_post, extraction=llm_extraction)
    assert all(i.code != "extraction_sqft_disagreement" for i in issues)


def test_compare_plan_only_emits_extraction_only_llm() -> None:
    llm_extraction = _extraction(_struct("sfr", 1500))
    llm_post = derive_post_from_llm(llm_extraction)
    issues = compare_extractions(None, llm_post, extraction=llm_extraction)
    codes = [i.code for i in issues]
    assert "extraction_only_llm" in codes


def test_compare_emits_low_confidence() -> None:
    regex = PostFire(
        sfr_count=1,
        sfr_sqft=1500,
        adu_count=0,
        adu_sqft=None,
        mfr_count=0,
        mfr_sqft=None,
        sb9_count=0,
        sb9_sqft=None,
    )
    llm_extraction = _extraction(_struct("sfr", 1500, confidence="low"))
    llm_post = derive_post_from_llm(llm_extraction)
    issues = compare_extractions(regex, llm_post, extraction=llm_extraction)
    assert any(i.code == "extraction_low_confidence" for i in issues)


def test_extraction_metrics_aggregates_warnings() -> None:
    info = ExtractionRunInfo(
        enabled=True,
        model="anthropic/claude-sonnet-4-6",
        prompt_version=1,
        parcels_attempted=10,
        parcels_extracted=8,
        parcels_failed=2,
        plan_only_parcels=1,
        cache_hits=5,
        cache_misses=3,
    )
    warnings = [
        RecordWarning(
            ain="A", code="extraction_count_disagreement", detail="", severity="info"
        ),
        RecordWarning(
            ain="B", code="extraction_count_disagreement", detail="", severity="info"
        ),
        RecordWarning(
            ain="A", code="extraction_sqft_disagreement", detail="", severity="info"
        ),
        RecordWarning(
            ain="C", code="extraction_low_confidence", detail="", severity="info"
        ),
        RecordWarning(
            ain="D", code="llm_extraction_failed", detail="", severity="data"
        ),
    ]
    metrics = extraction_metrics(info, warnings)
    assert metrics["enabled"] is True
    assert metrics["model"] == "anthropic/claude-sonnet-4-6"
    assert metrics["parcels_attempted"] == 10
    assert metrics["parcels_extracted"] == 8
    assert metrics["count_disagreements"] == 2  # A and B
    assert metrics["sqft_disagreements"] == 1  # A
    assert metrics["low_confidence_parcels"] == 1  # C
    assert metrics["extraction_failures"] == 1  # D
    # 8 extracted; (count+sqft) = 3 disagreement events → 5/8 agreement.
    assert metrics["agreement_rate"] == 0.625


def test_extraction_metrics_empty_run() -> None:
    info = ExtractionRunInfo(
        enabled=False,
        model="",
        prompt_version=0,
        parcels_attempted=0,
        parcels_extracted=0,
        parcels_failed=0,
        plan_only_parcels=0,
        cache_hits=0,
        cache_misses=0,
    )
    metrics = extraction_metrics(info, [])
    assert metrics["agreement_rate"] == 1.0
    assert metrics["enabled"] is False
