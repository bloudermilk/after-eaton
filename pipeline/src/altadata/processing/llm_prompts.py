"""Prompts and cache-key derivation for LLM-based structure extraction.

Bump ``PROMPT_VERSION`` whenever the system prompt changes meaningfully —
that invalidates all cached extractions cleanly. Add a brief note here when
bumping so downstream readers know what changed.

History:
- v1: initial prompt covering plan + permit records, structure-level dedup,
  worked example for floor-label rule (AIN 5845016021 → 4 ADUs).
- v2: SB-9 modeled as a permitting pathway, not a structure type. Removed
  "sb9" from struct_type enum; added guidance that SB-9-described units are
  primary dwellings (sfr) under SB-9 entitlement and that any SB-9 mention
  on the parcel is a heuristic for multiple primary dwellings.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from ..sources.schemas import EpicCase

PROMPT_VERSION = 2

_REBUILD_PROGRESS_LABELS: dict[int, str] = {
    1: "Plans Submitted",
    2: "Plans Under Review",
    3: "Plans Approved",
    4: "Permit Issued",
    5: "Construction Started",
    6: "Issued",
    7: "Finaled",
}

SYSTEM_PROMPT = """\
You are an expert in interpreting Los Angeles County rebuild records (plan applications and building permits) for parcels affected by the Eaton Fire of January 2025 in Altadena, CA.

Your job: given the full set of fire-related records filed for one parcel, infer the FINAL STATE of structures on the property, assuming all currently filed plans and permits are carried through to completion. You will see two record types:

  - PlanManagement (early-stage zoning/plan review; WORKCLASS = "Rebuild")
  - PermitManagement (the actual building permit; WORKCLASS = "New" or "Rebuild Project")

For one structure, both a plan record and a permit record may exist (the plan is filed first, the permit is filed later for the same project). Treat plan + permit on the same project + same described structure as ONE structure.

DEFINITION OF A STRUCTURE
A "structure" for our purposes is one independently-habitable dwelling unit, each of which would receive its own street address. Two ADUs stacked in one physical building (each with its own kitchen, bathroom, bedroom set) count as TWO structures, not one. A two-story SFR with a single kitchen on the ground floor and bedrooms upstairs is ONE structure.

SB-9 IS A PATHWAY, NOT A STRUCTURE TYPE
California's SB-9 is a permitting pathway that lets a single parcel build more than one primary dwelling (typically up to two SFRs without a lot split, or more with one), plus ADUs/JADUs as separately allowed. A description that says "SB9 unit" or "1107 SF SB9 (2 BR / 2 BA)" is describing an SFR being built under SB-9 entitlement — classify it as "sfr". A description that says "SB9 ADU" is describing an ADU built under SB-9 — classify it as "adu".

If any record on this parcel mentions SB-9, treat it as a HEURISTIC that the parcel is likely building MULTIPLE PRIMARY DWELLINGS. Use that signal when interpreting ambiguous structure descriptions: e.g., if a numbered-list description shows "1. NEW 2-STORY 1107 SF SB9 ... 2. NEW 2-STORY 1115 SF SFR ...", that is two SFRs on one parcel (count=2), not one SFR.

DEDUP RULES (apply in order)

1. NUMBERED LIST ITEMS in a single record's DESCRIPTION (lines starting "1.", "2.", "3.") are DISTINCT structures within that record. Each numbered item gets its own entry in the output.

2. EXPLICIT REVISION / REPLACEMENT / VOIDING language across records — only these phrases imply two records describe the same structure:
       "REVISION TO PERMIT [number]"
       "REPLACES PERMIT [number]"
       "SUPERSEDES PERMIT [number]"
       "VOIDS PERMIT [number]"
   In these cases, prefer the most recently APPLIED record's interpretation.

3. PLAN + PERMIT FOR SAME PROJECT. A PlanManagement "Rebuild" record and a PermitManagement record sharing PROJECT_NUMBER (or, if PROJECT_NUMBER is null, with very similar DESCRIPTION text) describe the same structure. Use the MOST RECENT record's data (highest APPLY_DATE), regardless of whether the most recent is the plan or the permit. Plans get revised after permits are filed; the latest submission reflects current intent.

4. EXPLICIT BUILDING / UNIT SEPARATORS — these indicate DISTINCT structures even within one project:
       "UNIT 1" / "UNIT 2"
       "BUILDING 1" / "BUILDING 2"
       "FIRST BUILDING" / "SECOND BUILDING"
       "FRONT" / "REAR" (when describing distinct dwellings)

5. FLOOR LABELS DO NOT AUTOMATICALLY MERGE. "1ST FLOOR" + "2ND FLOOR" with matching sqft are TWO structures if each is described as a complete independent dwelling (each has its own kitchen, bath, bedrooms). They are ONE structure only if the description makes clear it's a single multi-story home (e.g., "kitchen on first floor, bedrooms on second").

   Worked example — "EATON FIRE AFFECTED PROPERTY --- 2 NEW ADU DUPLEXS R-3 OCCUPANCY ... 798 SF PER UNIT" plus four permits each labeled "ADU 798 SF WITH 2 BEDROOMS AND 2 BATHROOMS AND COMMON STAIRWAY, 1ST/2ND FLOOR, FIRST/SECOND BUILDING" → 2 buildings × 2 stacked units each × own kitchen/bath/bedrooms = 4 ADUs. The shared stairway doesn't merge the units; each is independently habitable.

6. CROSS-REFERENCES like "PERMIT FEES PAID UNDER BLDR…" are billing conveniences and DO NOT imply duplication. Treat the records as independent unless rules 2 or 3 also apply.

7. SAME TYPE + DIFFERENT SQFT → always DISTINCT structures.

8. PERMITS WITH WORKCLASS_NAME = "Temporary Housing Project" are excluded from input; if you somehow see one, ignore it (RVs / trailers are not part of the planned final state).

OUTPUT FORMAT (JSON, no prose)

{
  "structures": [
    {
      "struct_type": "sfr" | "adu" | "jadu" | "mfr" | "garage" | "repair" | "other",
      "sqft": <integer or null>,
      "confidence": "high" | "medium" | "low",
      "evidence_case_numbers": ["UNC-...", ...],
      "notes": "<short, only if non-obvious; otherwise null>"
    }
  ],
  "reasoning": "<1-2 sentences explaining your interpretation>"
}

CONFIDENCE GUIDANCE
- "high": clear, unambiguous signal; no conflicting records
- "medium": some interpretation required (rule 3 or 5 applied)
- "low": genuinely ambiguous; flag for human review
"""


@dataclass(frozen=True)
class ParcelContext:
    """Per-parcel metadata passed alongside the qualifying records."""

    ain: str
    address: str
    damage: str
    pre_fire_summary: str


def render_user_prompt(ctx: ParcelContext, records: list[EpicCase]) -> str:
    """Render the per-parcel user prompt.

    Records are sorted ascending by APPLY_DATE so the LLM sees the chronology
    explicitly.
    """
    lines: list[str] = [
        "PARCEL CONTEXT",
        f"AIN: {ctx.ain}",
        f"Address: {ctx.address or '(unknown)'}",
        f"DAMAGE: {ctx.damage or '(unknown)'}",
        f"Pre-fire structures (from DINS): {ctx.pre_fire_summary}",
        "",
        f"RECORDS ({len(records)} qualifying, sorted by APPLY_DATE):",
        "",
    ]
    ordered = sorted(records, key=lambda r: r.get("APPLY_DATE") or 0)
    for idx, rec in enumerate(ordered, start=1):
        lines.extend(_render_record_block(idx, rec))
    return "\n".join(lines)


def parcel_cache_key(
    ain: str,
    records: list[EpicCase],
    *,
    model_id: str,
    prompt_version: int = PROMPT_VERSION,
) -> str:
    """Deterministic cache key per parcel.

    Sorted to be order-independent. Includes model + prompt version so either
    change invalidates the cache cleanly. Excludes mutable status / progress
    fields — a permit moving from "Issued" to "Finaled" doesn't change the
    structure inference.
    """
    parts = sorted(
        (
            (rec.get("CASENUMBER") or ""),
            hashlib.sha256((rec.get("DESCRIPTION") or "").encode()).hexdigest(),
        )
        for rec in records
    )
    payload = {
        "ain": ain,
        "records": parts,
        "prompt_version": prompt_version,
        "model": model_id,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return f"sha256:{digest}"


def _render_record_block(idx: int, rec: EpicCase) -> list[str]:
    progress = rec.get("REBUILD_PROGRESS_NUM")
    progress_label = (
        _REBUILD_PROGRESS_LABELS.get(int(progress))
        if isinstance(progress, (int, float))
        else None
    )
    progress_str = (
        f"{int(progress)} ({progress_label})"
        if progress is not None and progress_label
        else (str(int(progress)) if isinstance(progress, (int, float)) else "(unknown)")
    )

    return [
        f"[{idx}] CASENUMBER:     {rec.get('CASENUMBER') or '(unknown)'}",
        f"    MODULENAME:     {rec.get('MODULENAME') or '(unknown)'}",
        f"    WORKCLASS:      {rec.get('WORKCLASS_NAME') or '(unknown)'}",
        f"    PROJECT_NUMBER: {_project_number(rec)}",
        f"    PROJECT_NAME:   {rec.get('PROJECT_NAME') or rec.get('PROJECTNAME') or '(none)'}",
        f"    STATUS:         {rec.get('STATUS') or '(unknown)'}",
        f"    PROGRESS:       {progress_str}",
        f"    APPLY_DATE:     {_format_date(rec.get('APPLY_DATE'))}",
        "    DESCRIPTION:",
        *_indent_block(rec.get("DESCRIPTION") or "(blank)", "      "),
        "",
    ]


def _project_number(rec: EpicCase) -> str:
    pn = rec.get("PROJECT_NUMBER")
    return str(pn) if pn else "(none)"


def _format_date(epoch_ms: float | None) -> str:
    if epoch_ms is None:
        return "(unknown)"
    try:
        dt = datetime.fromtimestamp(float(epoch_ms) / 1000.0, tz=UTC)
        return dt.strftime("%Y-%m-%d")
    except (ValueError, OSError):
        return "(invalid)"


def _indent_block(text: str, prefix: str) -> list[str]:
    return [prefix + line for line in text.splitlines()] or [prefix + "(blank)"]
