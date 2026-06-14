"""Free-text parser for EPIC-LA case DESCRIPTION and PROJECT_NAME fields."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

StructType = Literal[
    "sfr",
    "adu",
    "jadu",
    "mfr",
    "garage",
    "temporary_housing",
    "repair",
    "retaining_wall",
    "seismic",
    "unknown",
]

# struct types that count toward post-fire dwelling counts
RESIDENTIAL_TYPES: frozenset[StructType] = frozenset({"sfr", "adu", "jadu", "mfr"})


@dataclass(frozen=True)
class ParsedStructure:
    sqft: float | None
    struct_type: StructType
    raw_segment: str


# Note: deliberately do *not* match a bare "SF" — that's the sqft unit and
# appears immediately before the structure keyword in most descriptions.
_SFR_RE = re.compile(r"\bSF[RDH]\b|\bSINGLE[\s-]+FAMIL", re.I)
_ADU_RE = re.compile(r"\bADUS?\b|\bACCESSORY\s+DWELL", re.I)
_JADU_RE = re.compile(r"\bJADUS?\b|\bJUNIOR\s+ADU", re.I)
_SB9_RE = re.compile(r"\bSB[\- ]?9\b|\bSENATE\s+BILL\s*9", re.I)
_MFR_RE = re.compile(
    r"\bDUPLEX\b|\bTRIPLEX\b|\bMFR\b|\bMULTI[\s-]*FAMIL|\bCONDO\s+UNIT", re.I
)
_GARAGE_RE = re.compile(r"\bGARAGE\b|\bCARPORT\b", re.I)
_TEMP_HOUSING_RE = re.compile(
    r"\bTEMP(?:\.|ORARY)?\s+HOUSING|\bTEMP\.?\s+HOUSING|"
    r"\b(?:RV|MOTOR\s+HOME|TRAILER|CAMPER)\b",
    re.I,
)
_REPAIR_RE = re.compile(
    r"\bREPAIR\b|\bALTERATION\b|\bREPLACE\b|\bRENOVAT|\bRESTORATION\b|"
    r"\bREMODEL\b|\bTENANT\s+IMPROV",
    re.I,
)
_RETAINING_WALL_RE = re.compile(
    r"\bRETAINING\s+WALL|\bCMU\s+WALL|\b(?:LANDSCAPING|GRADING)\b",
    re.I,
)
_SEISMIC_RE = re.compile(r"\bSEISMIC\s+(?:RETROFIT|UPGRADE|REROFIT)", re.I)

# Three priority tiers. Within a tier we pick the earliest match.
# Across tiers we pick the highest-priority tier with any match.
# T1 (residential primary) beats T2 (garage), which beats T3 (non-structural).
_T1_PRIMARY: list[tuple[StructType, re.Pattern[str]]] = [
    ("jadu", _JADU_RE),
    ("adu", _ADU_RE),
    ("sfr", _SFR_RE),
    ("mfr", _MFR_RE),
]
_T2_SECONDARY: list[tuple[StructType, re.Pattern[str]]] = [
    ("garage", _GARAGE_RE),
]
_T3_NONSTRUCT: list[tuple[StructType, re.Pattern[str]]] = [
    ("temporary_housing", _TEMP_HOUSING_RE),
    ("repair", _REPAIR_RE),
    ("retaining_wall", _RETAINING_WALL_RE),
    ("seismic", _SEISMIC_RE),
]

# Leading word boundary keeps us from picking the trailing "9" in tokens like
# "SB9 SFR" as 9 sqft. Two unit forms are accepted:
#   - abbreviated: "SF", "S.F.", "SQFT", "sq ft", "sq. ft." …
#   - spelled out: "square foot", "square feet", "square-foot",
#                  "1,680-square-foot" (hyphens common in compound modifiers)
_SQFT_RE = re.compile(
    r"""\b(\d[\d,]*\.?\d*)
        (?:
            \s*S\.?\s*[FQ]\.?                       # SF, S.F., SQ, SQFT, sq ft
          | [\s-]+(?:square|sq)\s*\.?[\s-]*         # "square" / "sq" / "sq."
            (?:foot|feet|ft\.?)                     # foot/feet/ft/ft.
        )""",
    re.IGNORECASE | re.VERBOSE,
)

_LIST_ITEM_RE = re.compile(r"^\s*\d+\.\s", re.MULTILINE)
_LFL_NEG_RE = re.compile(r"non[\s-]*like[\s-]*for[\s-]*like", re.I)
_LFL_POS_RE = re.compile(r"like[\s-]*for[\s-]*like", re.I)


def parse_description(description: str | None) -> list[ParsedStructure]:
    """Split a DESCRIPTION into structures and classify each.

    A description with numbered list items (`1.`, `2.`, ...) is split per
    item; otherwise the whole string is treated as a single segment.
    """
    if not description or not description.strip():
        return []

    segments = _split_segments(description)
    return [_parse_segment(seg) for seg in segments]


def mentions_sb9(text: str | None) -> bool:
    """True iff the text mentions SB-9 in any common form."""
    if not text:
        return False
    return _SB9_RE.search(text) is not None


def extract_lfl_claim(project_name: str | None) -> bool | None:
    """Read the like-for-like claim from PROJECT_NAME.

    Returns True for "Like-for-Like ...", False for "Non-Like-for-Like ...",
    None when the project name does not state either way.
    """
    if not project_name:
        return None
    if _LFL_NEG_RE.search(project_name):
        return False
    if _LFL_POS_RE.search(project_name):
        return True
    return None


def _split_segments(description: str) -> list[str]:
    if not _LIST_ITEM_RE.search(description):
        return [description.strip()]

    parts: list[str] = []
    current: list[str] = []
    for line in description.splitlines():
        if _LIST_ITEM_RE.match(line):
            if current:
                parts.append("\n".join(current).strip())
                current = []
            line = _LIST_ITEM_RE.sub("", line, count=1)
        current.append(line)
    if current:
        parts.append("\n".join(current).strip())
    return [p for p in parts if p]


def _parse_segment(segment: str) -> ParsedStructure:
    sqfts = [(m.start(), _to_float(m.group(1))) for m in _SQFT_RE.finditer(segment)]

    # Tier 1: positive primary residential matches always win.
    matches: list[tuple[int, StructType]] = []
    for label, pattern in _T1_PRIMARY:
        for m in pattern.finditer(segment):
            matches.append((m.start(), label))
    if matches:
        pos, label = min(matches)
        chosen_sqft = _pick_sqft_near(pos, sqfts)
        return ParsedStructure(sqft=chosen_sqft, struct_type=label, raw_segment=segment)

    # SB-9 fallback: a segment that mentions SB-9 but no primary type keyword
    # almost always describes a primary dwelling under SB-9 entitlement
    # (e.g. "1107 SF SB9 (2 BR / 2 BA) WITH ATTACHED GARAGE"). Classify as
    # SFR. This must precede T2/T3 — a SB-9 unit with an attached-garage
    # clause is still a primary dwelling, not a garage.
    sb9_match = _SB9_RE.search(segment)
    if sb9_match is not None:
        chosen_sqft = _pick_sqft_near(sb9_match.start(), sqfts)
        return ParsedStructure(sqft=chosen_sqft, struct_type="sfr", raw_segment=segment)

    # Tiers 2 & 3: secondary/non-structural fallbacks.
    for tier in (_T2_SECONDARY, _T3_NONSTRUCT):
        matches = []
        for label, pattern in tier:
            for m in pattern.finditer(segment):
                matches.append((m.start(), label))
        if matches:
            pos, label = min(matches)
            chosen_sqft = _pick_sqft_near(pos, sqfts)
            return ParsedStructure(
                sqft=chosen_sqft, struct_type=label, raw_segment=segment
            )

    chosen_sqft = sqfts[0][1] if sqfts else None
    return ParsedStructure(sqft=chosen_sqft, struct_type="unknown", raw_segment=segment)


def _pick_sqft_near(
    anchor: int,
    sqfts: list[tuple[int, float | None]],
) -> float | None:
    if not sqfts:
        return None
    _, value = min(sqfts, key=lambda x: abs(x[0] - anchor))
    return value


def _to_float(raw: str) -> float | None:
    cleaned = raw.replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None
