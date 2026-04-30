"""End-to-end test for _analyze_all in cli.py — covers the regex+LLM wiring."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from after_eaton.cli import _analyze_all
from after_eaton.processing.join import JoinedParcel
from after_eaton.processing.llm_extraction import ExtractionCache, load_cache
from after_eaton.processing.llm_provider import LLMResponse, OpenRouterProvider
from after_eaton.sources.schemas import DinsParcel, EpicCase


def _din(ain: str = "1234567890") -> DinsParcel:
    return cast(
        DinsParcel,
        {
            "AIN_1": ain,
            "DAMAGE_1": "Destroyed (>50%)",
            "SQFTmain1": 1200.0,
            "DesignType1": "0101",
            "COMMUNITY": "Altadena",
            "UseDescription": "Single",
            "_geometry": None,
        },
    )


def _permit(case: str, desc: str, *, ain: str = "1234567890") -> EpicCase:
    return cast(
        EpicCase,
        {
            "MAIN_AIN": ain,
            "MODULENAME": "PermitManagement",
            "WORKCLASS_NAME": "New",
            "REBUILD_PROGRESS_NUM": 6,
            "DESCRIPTION": desc,
            "CASENUMBER": case,
            "DISASTER_TYPE": "Eaton Fire (01-2025)",
            "PROJECT_NUMBER": "PRJ-1",
            "STATUS": "Issued",
            "APPLY_DATE": 1739952000000,
        },
    )


def _stub_provider(extract_fn) -> OpenRouterProvider:  # type: ignore[no-untyped-def]
    p = OpenRouterProvider(api_key="test-key")
    p.extract = extract_fn  # type: ignore[method-assign]
    return p


def _llm_response_for_two_units() -> LLMResponse:
    """A response that disagrees with regex on counts (claims 1 SFR + 1 ADU)."""
    return LLMResponse(
        content=json.dumps(
            {
                "structures": [
                    {
                        "struct_type": "sfr",
                        "sqft": 1949,
                        "confidence": "high",
                        "evidence_case_numbers": ["UNC-A"],
                        "notes": None,
                    },
                    {
                        "struct_type": "adu",
                        "sqft": 534,
                        "confidence": "high",
                        "evidence_case_numbers": ["UNC-B"],
                        "notes": None,
                    },
                ],
                "reasoning": "Two distinct permits, one SFR and one ADU.",
            }
        ),
        input_tokens=2000,
        output_tokens=500,
    )


def test_analyze_all_no_provider_runs_regex_only(tmp_path: Path) -> None:
    joined = [
        JoinedParcel(
            din=_din(),
            cases=[_permit("UNC-A", "EATON FIRE - NEW 1949 SF SFR")],
        )
    ]
    cache = ExtractionCache()
    results, warnings, info = _analyze_all(
        joined, provider=None, cache=cache, cache_path=tmp_path / "cache.json"
    )

    assert len(results) == 1
    assert info.enabled is False
    assert info.parcels_attempted == 0
    assert info.parcels_extracted == 0
    assert results[0].post_sfr_count == 1
    assert results[0].post_sfr_sqft == 1949
    assert warnings == []  # _analyze_all only yields LLM-related warnings


def test_analyze_all_with_provider_overrides_post_fields(tmp_path: Path) -> None:
    joined = [
        JoinedParcel(
            din=_din(),
            cases=[
                _permit("UNC-A", "EATON FIRE - NEW 1949 SF SFR"),
                _permit("UNC-B", "EATON FIRE - NEW 534 SF ADU"),
            ],
        )
    ]
    provider = _stub_provider(lambda _s, _u: _llm_response_for_two_units())

    cache = ExtractionCache()
    cache_path = tmp_path / "cache.json"
    results, warnings, info = _analyze_all(
        joined, provider=provider, cache=cache, cache_path=cache_path
    )

    assert len(results) == 1
    result = results[0]
    # LLM result is what got applied:
    assert result.post_sfr_count == 1
    assert result.post_sfr_sqft == 1949
    assert result.post_adu_count == 1
    assert result.post_adu_sqft == 534
    # Run info reflects the LLM call:
    assert info.enabled is True
    assert info.parcels_attempted == 1
    assert info.parcels_extracted == 1
    assert info.parcels_failed == 0
    assert info.cache_misses == 1
    assert info.cache_hits == 0
    # Cache populated:
    assert len(cache.entries) == 1
    # Cache flushed to disk on the miss (mid-run persistence).
    on_disk = load_cache(cache_path)
    assert len(on_disk.entries) == 1
    # Regex extracted only one structure (parser is deterministic), so LLM's
    # second structure should produce a count_disagreement warning for ADU.
    codes = [w.code for w in warnings]
    assert "extraction_count_disagreement" in codes


def test_analyze_all_failure_falls_back_to_regex(tmp_path: Path) -> None:
    joined = [
        JoinedParcel(
            din=_din(),
            cases=[_permit("UNC-A", "EATON FIRE - NEW 1949 SF SFR")],
        )
    ]
    provider = _stub_provider(
        lambda _s, _u: LLMResponse(content="not json", input_tokens=10, output_tokens=2)
    )

    cache = ExtractionCache()
    cache_path = tmp_path / "cache.json"
    results, warnings, info = _analyze_all(
        joined, provider=provider, cache=cache, cache_path=cache_path
    )

    assert len(results) == 1
    assert results[0].post_sfr_sqft == 1949  # regex result preserved
    assert info.parcels_failed == 1
    assert info.parcels_extracted == 0
    assert any(w.code == "llm_extraction_failed" for w in warnings)
    # Failure path doesn't mutate the cache, so no file is written.
    assert not cache_path.exists()


def test_analyze_all_skips_parcels_without_qualifying_records(tmp_path: Path) -> None:
    """A parcel with no qualifying records (no PermitManagement-New or
    PlanManagement-Rebuild) should not be sent to the LLM."""
    joined = [
        JoinedParcel(
            din=_din(),
            cases=[],  # no cases at all
        )
    ]

    def must_not_be_called(_s: str, _u: str) -> LLMResponse:
        raise AssertionError("provider should not be called for parcel with no records")

    provider = _stub_provider(must_not_be_called)
    cache = ExtractionCache()
    results, warnings, info = _analyze_all(
        joined, provider=provider, cache=cache, cache_path=tmp_path / "cache.json"
    )
    assert len(results) == 1
    assert info.parcels_attempted == 0


def test_analyze_all_treats_plan_only_parcel_as_plan_only(tmp_path: Path) -> None:
    """A parcel with only a PlanManagement record (no PermitManagement) should
    be sent to the LLM and counted as plan_only."""
    plan_record = cast(
        EpicCase,
        {
            "MAIN_AIN": "1234567890",
            "MODULENAME": "PlanManagement",
            "WORKCLASS_NAME": "Rebuild",
            "REBUILD_PROGRESS_NUM": 2,
            "DESCRIPTION": "EATON FIRE NON LIKE FOR LIKE REBUILD - NEW 1500 SF SFR",
            "CASENUMBER": "CREC-A",
            "DISASTER_TYPE": "Eaton Fire (01-2025)",
            "STATUS": "Open",
            "APPLY_DATE": 1739952000000,
        },
    )
    joined = [JoinedParcel(din=_din(), cases=[plan_record])]
    provider = _stub_provider(lambda _s, _u: _llm_response_for_two_units())
    cache = ExtractionCache()
    results, warnings, info = _analyze_all(
        joined, provider=provider, cache=cache, cache_path=tmp_path / "cache.json"
    )

    assert info.parcels_attempted == 1
    assert info.parcels_extracted == 1
    assert info.plan_only_parcels == 1
    assert any(w.code == "extraction_only_llm" for w in warnings)
    assert results[0].post_sfr_count == 1
    assert results[0].post_adu_count == 1
