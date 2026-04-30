"""Tests for LLM-based structure extraction (cache, parsing, prune)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import pytest

from after_eaton.processing.llm_extraction import (
    ExtractedStructure,
    ExtractionCache,
    LLMExtraction,
    extract_structures,
    load_cache,
    prune_cache,
    save_cache,
)
from after_eaton.processing.llm_prompts import (
    PROMPT_VERSION,
    ParcelContext,
    parcel_cache_key,
)
from after_eaton.processing.llm_provider import LLMResponse, OpenRouterProvider
from after_eaton.sources.schemas import EpicCase


def _ctx(ain: str = "1234567890") -> ParcelContext:
    return ParcelContext(
        ain=ain,
        address="1 Main St",
        damage="Destroyed (>50%)",
        pre_fire_summary="1 SFR (1200 SF)",
    )


def _record(
    case: str = "UNC-A", desc: str = "EATON FIRE - NEW 1500 SF SFR"
) -> EpicCase:
    return {  # type: ignore[typeddict-item]
        "MAIN_AIN": "1234567890",
        "MODULENAME": "PermitManagement",
        "WORKCLASS_NAME": "New",
        "REBUILD_PROGRESS_NUM": 6,
        "DESCRIPTION": desc,
        "CASENUMBER": case,
        "PROJECT_NUMBER": "PRJ2025-1",
        "STATUS": "Issued",
        "APPLY_DATE": 1739952000000,
    }


def _good_response_content() -> str:
    return json.dumps(
        {
            "structures": [
                {
                    "struct_type": "sfr",
                    "sqft": 1500,
                    "confidence": "high",
                    "evidence_case_numbers": ["UNC-A"],
                    "notes": None,
                }
            ],
            "reasoning": "single SFR rebuild permit",
        }
    )


def _stub_provider(
    extract_fn: Callable[[str, str], LLMResponse],
) -> OpenRouterProvider:
    """Build an OpenRouterProvider with a fake api_key and replace .extract."""
    p = OpenRouterProvider(api_key="test-key")
    p.extract = extract_fn  # type: ignore[method-assign]
    return p


def test_extract_structures_calls_provider_and_caches() -> None:
    captured: dict[str, str] = {}

    def fake_extract(system: str, user: str) -> LLMResponse:
        captured["sys"] = system
        captured["user"] = user
        return LLMResponse(_good_response_content(), 100, 30)

    provider = _stub_provider(fake_extract)
    cache = ExtractionCache()
    out1 = extract_structures(_ctx(), [_record()], provider=provider, cache=cache)
    assert out1 is not None
    assert out1.ain == "1234567890"
    assert len(out1.structures) == 1
    assert out1.structures[0].struct_type == "sfr"
    assert out1.structures[0].sqft == 1500
    assert out1.input_tokens == 100
    assert out1.output_tokens == 30
    assert len(cache.entries) == 1

    # Second call hits cache.
    def raiser(_s: str, _u: str) -> LLMResponse:
        raise AssertionError("provider should not be called on cache hit")

    provider.extract = raiser  # type: ignore[method-assign]
    out2 = extract_structures(_ctx(), [_record()], provider=provider, cache=cache)
    assert out2 == out1


def test_extract_structures_returns_none_on_invalid_json() -> None:
    provider = _stub_provider(lambda _s, _u: LLMResponse("this is not JSON", 50, 10))
    cache = ExtractionCache()
    out = extract_structures(_ctx(), [_record()], provider=provider, cache=cache)
    assert out is None
    assert len(cache.entries) == 0  # invalid responses not cached


def test_extract_structures_handles_fenced_json() -> None:
    fenced = f"```json\n{_good_response_content()}\n```"
    provider = _stub_provider(lambda _s, _u: LLMResponse(fenced, 50, 10))
    cache = ExtractionCache()
    out = extract_structures(_ctx(), [_record()], provider=provider, cache=cache)
    assert out is not None
    assert out.structures[0].struct_type == "sfr"


def test_extract_structures_returns_none_on_empty_records() -> None:
    cache = ExtractionCache()
    provider = _stub_provider(lambda _s, _u: LLMResponse("{}", 0, 0))
    out = extract_structures(_ctx(), [], provider=provider, cache=cache)
    assert out is None


def test_extract_structures_coerces_unknown_struct_type() -> None:
    bad = json.dumps(
        {
            "structures": [
                {"struct_type": "townhouse", "sqft": 800, "confidence": "high"}
            ],
            "reasoning": "...",
        }
    )
    provider = _stub_provider(lambda _s, _u: LLMResponse(bad, 1, 1))
    cache = ExtractionCache()
    out = extract_structures(_ctx(), [_record()], provider=provider, cache=cache)
    assert out is not None
    assert out.structures[0].struct_type == "other"


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    extraction = LLMExtraction(
        key="sha256:abc",
        ain="1234",
        extracted_at="2026-04-28T12:00:00Z",
        model="anthropic/claude-sonnet-4-6",
        prompt_version=1,
        input_case_numbers=("UNC-A", "UNC-B"),
        structures=(
            ExtractedStructure(
                struct_type="sfr",
                sqft=1500,
                confidence="high",
                evidence_case_numbers=("UNC-A",),
                notes=None,
            ),
        ),
        reasoning="...",
        input_tokens=100,
        output_tokens=30,
    )
    cache = ExtractionCache(entries={extraction.key: extraction})
    path = tmp_path / "cache.json"
    save_cache(path, cache)
    loaded = load_cache(path)
    assert loaded.entries[extraction.key] == extraction
    payload = json.loads(path.read_text())
    assert payload["prompt_version"] == PROMPT_VERSION
    assert len(payload["entries"]) == 1
    assert payload["entries"][0]["input_case_numbers"] == ["UNC-A", "UNC-B"]


def test_load_cache_missing_file_returns_empty(tmp_path: Path) -> None:
    cache = load_cache(tmp_path / "nope.json")
    assert cache.entries == {}


def test_load_cache_corrupt_file_returns_empty(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("not json")
    cache = load_cache(path)
    assert cache.entries == {}


def test_prune_drops_stale_ains() -> None:
    e1 = LLMExtraction(
        key="k1",
        ain="A",
        extracted_at="x",
        model="m",
        prompt_version=1,
        input_case_numbers=(),
        structures=(),
        reasoning="",
        input_tokens=0,
        output_tokens=0,
    )
    e2 = LLMExtraction(
        key="k2",
        ain="B",
        extracted_at="x",
        model="m",
        prompt_version=1,
        input_case_numbers=(),
        structures=(),
        reasoning="",
        input_tokens=0,
        output_tokens=0,
    )
    cache = ExtractionCache(entries={"k1": e1, "k2": e2})
    dropped = prune_cache(cache, valid_ains={"A"})
    assert dropped == 1
    assert "k1" in cache.entries
    assert "k2" not in cache.entries


def test_cache_key_match_is_what_drives_cache_hit() -> None:
    """Sanity: the same ctx+records+model produces same key, so a parcel run
    twice in the same session hits cache."""
    ctx = _ctx()
    records = [_record()]
    k1 = parcel_cache_key(ctx.ain, records, model_id="m", prompt_version=PROMPT_VERSION)
    k2 = parcel_cache_key(ctx.ain, records, model_id="m", prompt_version=PROMPT_VERSION)
    assert k1 == k2


def _entry(key: str, ain: str) -> LLMExtraction:
    return LLMExtraction(
        key=key,
        ain=ain,
        extracted_at="2026-04-29T00:00:00Z",
        model="m",
        prompt_version=PROMPT_VERSION,
        input_case_numbers=(),
        structures=(),
        reasoning="",
        input_tokens=0,
        output_tokens=0,
    )


def test_save_cache_leaves_no_tmp_file(tmp_path: Path) -> None:
    """Atomic write: the .tmp sibling does not linger after a successful save."""
    path = tmp_path / "cache.json"
    cache = ExtractionCache(entries={"k1": _entry("k1", "A")})
    save_cache(path, cache)
    assert path.exists()
    assert not (tmp_path / "cache.json.tmp").exists()
    siblings = list(tmp_path.iterdir())
    assert len(siblings) == 1, f"expected only cache.json, found {siblings}"


def test_save_cache_preserves_original_on_write_failure(tmp_path: Path) -> None:
    """If the temp write blows up, the previously-saved file is untouched."""
    path = tmp_path / "cache.json"
    save_cache(path, ExtractionCache(entries={"k1": _entry("k1", "A")}))
    original_bytes = path.read_bytes()

    bigger = ExtractionCache(entries={"k1": _entry("k1", "A"), "k2": _entry("k2", "B")})

    real_write_text = Path.write_text

    def boom(self: Path, *args: object, **kwargs: object) -> int:
        if self.suffix == ".tmp":
            raise OSError("disk full")
        return real_write_text(self, *args, **kwargs)  # type: ignore[arg-type]

    with patch.object(Path, "write_text", boom):
        with pytest.raises(OSError, match="disk full"):
            save_cache(path, bigger)

    # Original file content untouched (atomic-rename semantics).
    assert path.read_bytes() == original_bytes
    reloaded = load_cache(path)
    assert set(reloaded.entries.keys()) == {"k1"}


def test_extract_structures_caller_can_persist_after_each_miss(tmp_path: Path) -> None:
    """Simulate a mid-run crash: persist after each cache miss, then 'kill' and
    reload — completed extractions survive."""
    path = tmp_path / "cache.json"
    cache = ExtractionCache()

    def fake_extract(_s: str, _u: str) -> LLMResponse:
        return LLMResponse(_good_response_content(), 100, 30)

    provider = _stub_provider(fake_extract)

    out1 = extract_structures(
        _ctx("AIN-A"), [_record(case="A")], provider=provider, cache=cache
    )
    assert out1 is not None
    save_cache(path, cache)  # caller saves after the miss

    out2 = extract_structures(
        _ctx("AIN-B"), [_record(case="B")], provider=provider, cache=cache
    )
    assert out2 is not None
    save_cache(path, cache)

    # Drop the in-memory cache (simulate process death) and reload from disk.
    del cache
    reloaded = load_cache(path)
    assert len(reloaded.entries) == 2
    assert {e.ain for e in reloaded.entries.values()} == {"AIN-A", "AIN-B"}
