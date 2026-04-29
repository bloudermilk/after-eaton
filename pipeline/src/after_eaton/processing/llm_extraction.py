"""LLM-based per-parcel structure extraction with persistent cache.

The cache lives as a single JSON file (`llm-extraction-cache.json`) shipped
alongside other release assets. Cache keys are deterministic over (parcel
identity, record contents, provider, model, prompt version) — see
``llm_prompts.parcel_cache_key``.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..sources.schemas import EpicCase
from .llm_prompts import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    ParcelContext,
    parcel_cache_key,
    render_user_prompt,
)
from .llm_provider import LLMError, OpenRouterProvider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExtractedStructure:
    struct_type: str
    sqft: int | None
    confidence: str
    evidence_case_numbers: tuple[str, ...]
    notes: str | None


@dataclass(frozen=True)
class LLMExtraction:
    key: str
    ain: str
    extracted_at: str
    model: str
    prompt_version: int
    input_case_numbers: tuple[str, ...]
    structures: tuple[ExtractedStructure, ...]
    reasoning: str
    input_tokens: int
    output_tokens: int


@dataclass
class ExtractionCache:
    """In-memory cache of LLM extractions, keyed by cache key.

    Held mutable so multiple ``extract_structures`` calls in a run can append
    new entries; persisted at end of run via ``save_cache``.
    """

    entries: dict[str, LLMExtraction] = field(default_factory=dict)
    prompt_version: int = PROMPT_VERSION


def load_cache(path: Path | str) -> ExtractionCache:
    """Load a cache file produced by ``save_cache``. Missing file → empty cache."""
    p = Path(path)
    if not p.exists():
        return ExtractionCache()
    try:
        payload = json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        logger.error("cache file %s is corrupt (%s) — starting empty", p, exc)
        return ExtractionCache()
    raw_entries = payload.get("entries", [])
    entries: dict[str, LLMExtraction] = {}
    for raw in raw_entries:
        try:
            entry = _entry_from_dict(raw)
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("dropping cache entry with invalid shape: %s", exc)
            continue
        entries[entry.key] = entry
    return ExtractionCache(
        entries=entries,
        prompt_version=int(payload.get("prompt_version") or PROMPT_VERSION),
    )


def save_cache(path: Path | str, cache: ExtractionCache) -> None:
    """Write the cache as a single JSON object; safe to upload as a release asset."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": _now_iso(),
        "prompt_version": cache.prompt_version,
        "entry_count": len(cache.entries),
        "entries": [_entry_to_dict(e) for e in cache.entries.values()],
    }
    p.write_text(json.dumps(payload, indent=2, sort_keys=False))


def prune_cache(cache: ExtractionCache, valid_ains: set[str]) -> int:
    """Drop entries whose AIN is no longer in the parcel set. Returns count dropped."""
    stale = [k for k, v in cache.entries.items() if v.ain not in valid_ains]
    for k in stale:
        del cache.entries[k]
    return len(stale)


def extract_structures(
    ctx: ParcelContext,
    records: list[EpicCase],
    *,
    provider: OpenRouterProvider,
    cache: ExtractionCache,
) -> LLMExtraction | None:
    """Return an LLMExtraction for one parcel, hitting cache or live API.

    Returns ``None`` on persistent failure (caller should fall back to regex
    and emit an `llm_extraction_failed` warning).
    """
    if not records:
        return None

    key = parcel_cache_key(
        ctx.ain,
        records,
        model_id=provider.model_id,
    )
    if key in cache.entries:
        return cache.entries[key]

    user_prompt = render_user_prompt(ctx, records)
    try:
        response = provider.extract(SYSTEM_PROMPT, user_prompt)
    except LLMError as exc:
        logger.error("LLM call failed for AIN %s: %s", ctx.ain, exc)
        return None

    parsed = _parse_response_content(response.content)
    if parsed is None:
        logger.error(
            "LLM response for AIN %s was not parseable JSON: %r",
            ctx.ain,
            response.content[:200],
        )
        return None

    structures = _coerce_structures(parsed.get("structures"))
    extraction = LLMExtraction(
        key=key,
        ain=ctx.ain,
        extracted_at=_now_iso(),
        model=provider.model_id,
        prompt_version=PROMPT_VERSION,
        input_case_numbers=tuple(str(rec.get("CASENUMBER") or "") for rec in records),
        structures=structures,
        reasoning=str(parsed.get("reasoning") or ""),
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
    )
    cache.entries[key] = extraction
    return extraction


# ---------- helpers ----------


_VALID_STRUCT_TYPES = frozenset(
    {"sfr", "adu", "jadu", "sb9", "mfr", "garage", "repair", "other"}
)
_VALID_CONFIDENCES = frozenset({"high", "medium", "low"})

_FENCED_JSON_RE = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE
)


def _parse_response_content(content: str) -> dict[str, Any] | None:
    text = content.strip()
    try:
        result = json.loads(text)
        return result if isinstance(result, dict) else None
    except json.JSONDecodeError:
        pass
    # Some models wrap JSON in markdown fences despite response_format hints.
    match = _FENCED_JSON_RE.search(text)
    if match:
        try:
            result = json.loads(match.group(1))
            return result if isinstance(result, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _coerce_structures(raw: Any) -> tuple[ExtractedStructure, ...]:
    if not isinstance(raw, list):
        return ()
    out: list[ExtractedStructure] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        st = str(item.get("struct_type") or "other").lower()
        if st not in _VALID_STRUCT_TYPES:
            logger.warning(
                "LLM returned unknown struct_type %r — coercing to 'other'", st
            )
            st = "other"
        sqft_raw = item.get("sqft")
        sqft = int(sqft_raw) if isinstance(sqft_raw, (int, float)) else None
        confidence = str(item.get("confidence") or "low").lower()
        if confidence not in _VALID_CONFIDENCES:
            confidence = "low"
        evidence_raw = item.get("evidence_case_numbers") or []
        if not isinstance(evidence_raw, list):
            evidence_raw = []
        evidence = tuple(str(e) for e in evidence_raw if e)
        notes_raw = item.get("notes")
        notes = str(notes_raw) if notes_raw else None
        out.append(
            ExtractedStructure(
                struct_type=st,
                sqft=sqft,
                confidence=confidence,
                evidence_case_numbers=evidence,
                notes=notes,
            )
        )
    return tuple(out)


def _entry_to_dict(entry: LLMExtraction) -> dict[str, Any]:
    payload = asdict(entry)
    # Tuples → lists for JSON serialization
    payload["input_case_numbers"] = list(entry.input_case_numbers)
    payload["structures"] = [
        {**asdict(s), "evidence_case_numbers": list(s.evidence_case_numbers)}
        for s in entry.structures
    ]
    return payload


def _entry_from_dict(raw: dict[str, Any]) -> LLMExtraction:
    structures = tuple(
        ExtractedStructure(
            struct_type=str(s["struct_type"]),
            sqft=int(s["sqft"]) if s.get("sqft") is not None else None,
            confidence=str(s.get("confidence") or "low"),
            evidence_case_numbers=tuple(
                str(e) for e in (s.get("evidence_case_numbers") or [])
            ),
            notes=str(s["notes"]) if s.get("notes") else None,
        )
        for s in raw.get("structures") or []
    )
    return LLMExtraction(
        key=str(raw["key"]),
        ain=str(raw["ain"]),
        extracted_at=str(raw.get("extracted_at") or ""),
        model=str(raw.get("model") or ""),
        prompt_version=int(raw.get("prompt_version") or PROMPT_VERSION),
        input_case_numbers=tuple(str(c) for c in (raw.get("input_case_numbers") or [])),
        structures=structures,
        reasoning=str(raw.get("reasoning") or ""),
        input_tokens=int(raw.get("input_tokens") or 0),
        output_tokens=int(raw.get("output_tokens") or 0),
    )


def _now_iso() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
