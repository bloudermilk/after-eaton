"""Per-parcel analysis: combine DINS + EPIC-LA into a single ParcelResult."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from ..sources.schemas import DinsParcel, EpicCase
from .description_parser import (
    ParsedStructure,
    StructType,
    extract_lfl_claim,
    parse_description,
)
from .join import JoinedParcel
from .normalize import (
    BsdStatus,
    DamageLevel,
    normalize_bsd,
    normalize_damage,
    rebuild_progress_label,
)

SfrSizeComparison = Literal["smaller", "identical", "larger"]

_IDENTICAL_TOLERANCE = 10  # sqft

_EATON_DISASTER = "Eaton Fire (01-2025)"
_EATON_DESC_RE = re.compile(r"eaton fire", re.I)
_PRIMARY_PERMIT_WORKCLASSES = {"New", "Rebuild Project"}
_PLAN_REBUILD_WORKCLASS = "Rebuild"


@dataclass
class ParcelResult:
    ain: str
    apn: str
    address: str
    # FIRESCOPE %-loss bucket from DINS `DAMAGE_1`
    damage: DamageLevel
    # Safety-assessment tag from DINS `BSD_Tag` — what LA County's Recovery
    # Map uses for its destroyed/damaged headline counts. See normalize.py.
    bsd_status: BsdStatus
    # Pre-fire (from DINS)
    pre_sfr_count: int
    pre_sfr_sqft: int | None
    pre_adu_count: int
    pre_adu_sqft: int | None
    pre_mfr_count: int
    pre_mfr_sqft: int | None
    # Post-fire (from EPIC-LA)
    post_sfr_count: int | None
    post_sfr_sqft: int | None
    post_adu_count: int | None
    post_adu_sqft: int | None
    post_mfr_count: int | None
    post_mfr_sqft: int | None
    post_sb9_count: int | None
    post_sb9_sqft: int | None
    # Rebuild characterization
    lfl_claimed: bool | None
    # True when fire cases produced two or more distinct LFL/Custom signals
    # (most-recent case still wins per `_resolve_lfl`; the flag is only for
    # surfacing noisy source data via QC).
    lfl_conflict: bool
    sfr_size_comparison: SfrSizeComparison | None
    adds_sb9: bool
    added_adu_count: int
    # Progress
    rebuild_progress_num: int | None
    rebuild_progress: str | None
    # Pass-through DINS fields
    permit_status: str | None
    roe_status: str | None
    debris_cleared: str | None
    dins_count: int


def analyze_parcel(joined: JoinedParcel) -> ParcelResult:
    din = joined.din
    fire_cases = filter_fire_cases(joined.cases)

    pre = analyze_pre_fire(din)
    progress = _max_progress(fire_cases)
    primary = _select_primary_permit(fire_cases)
    post = _analyze_post_fire(primary)
    lfl_claimed, lfl_conflict = _resolve_lfl(fire_cases)

    sfr_cmp = _compare_sfr(pre.sfr_sqft, post.sfr_sqft)
    adds_sb9 = bool(post.sb9_count and post.sb9_count > 0)
    added_adu_count = max(0, (post.adu_count or 0) - pre.adu_count)

    return ParcelResult(
        ain=din["AIN_1"],
        apn=str(din.get("APN_1") or din["AIN_1"]),
        address=str(din.get("SitusFullAddress") or din.get("SitusAddress") or ""),
        damage=normalize_damage(din.get("DAMAGE_1")),
        bsd_status=normalize_bsd(din.get("BSD_Tag")),
        pre_sfr_count=pre.sfr_count,
        pre_sfr_sqft=pre.sfr_sqft,
        pre_adu_count=pre.adu_count,
        pre_adu_sqft=pre.adu_sqft,
        pre_mfr_count=pre.mfr_count,
        pre_mfr_sqft=pre.mfr_sqft,
        post_sfr_count=post.sfr_count,
        post_sfr_sqft=post.sfr_sqft,
        post_adu_count=post.adu_count,
        post_adu_sqft=post.adu_sqft,
        post_mfr_count=post.mfr_count,
        post_mfr_sqft=post.mfr_sqft,
        post_sb9_count=post.sb9_count,
        post_sb9_sqft=post.sb9_sqft,
        lfl_claimed=lfl_claimed,
        lfl_conflict=lfl_conflict,
        sfr_size_comparison=sfr_cmp,
        adds_sb9=adds_sb9,
        added_adu_count=added_adu_count,
        rebuild_progress_num=progress,
        rebuild_progress=rebuild_progress_label(progress),
        permit_status=_to_str_or_none(din.get("Permit_Status")),
        roe_status=_to_str_or_none(din.get("ROE_Status")),
        debris_cleared=_to_str_or_none(din.get("Debris_Cleared")),
        dins_count=int(din.get("DINS_Count") or 0),
    )


# ---------- helpers ----------


@dataclass(frozen=True)
class PreFire:
    sfr_count: int
    sfr_sqft: int | None
    adu_count: int
    adu_sqft: int | None
    mfr_count: int
    mfr_sqft: int | None


@dataclass(frozen=True)
class PostFire:
    sfr_count: int | None
    sfr_sqft: int | None
    adu_count: int | None
    adu_sqft: int | None
    mfr_count: int | None
    mfr_sqft: int | None
    sb9_count: int | None
    sb9_sqft: int | None


def analyze_pre_fire(din: DinsParcel) -> PreFire:
    use_desc = (din.get("UseDescription") or "").strip().lower()
    is_single_use = use_desc == "single"

    sfr_sqfts: list[float] = []
    adu_sqfts: list[float] = []
    mfr_sqfts: list[float] = []

    for slot in range(1, 6):
        design_type = din.get(f"DesignType{slot}")
        if not design_type:
            continue
        sqft = din.get(f"SQFTmain{slot}")
        prefix = str(design_type)[:2]
        sqft_val = float(sqft) if isinstance(sqft, (int, float)) else 0.0
        if prefix == "01":
            if slot == 1:
                sfr_sqfts.append(sqft_val)
            elif is_single_use:
                adu_sqfts.append(sqft_val)
            else:
                sfr_sqfts.append(sqft_val)
        elif prefix in {"02", "03", "04", "05"}:
            mfr_sqfts.append(sqft_val)

    return PreFire(
        sfr_count=len(sfr_sqfts),
        sfr_sqft=_sum_int(sfr_sqfts),
        adu_count=len(adu_sqfts),
        adu_sqft=_sum_int(adu_sqfts),
        mfr_count=len(mfr_sqfts),
        mfr_sqft=_sum_int(mfr_sqfts),
    )


def pre_fire_summary(din: DinsParcel) -> str:
    """Human-readable summary of pre-fire structures, for the LLM prompt."""
    pre = analyze_pre_fire(din)
    parts: list[str] = []
    if pre.sfr_count:
        parts.append(f"{pre.sfr_count} SFR ({pre.sfr_sqft or '?'} SF total)")
    if pre.adu_count:
        parts.append(f"{pre.adu_count} ADU ({pre.adu_sqft or '?'} SF total)")
    if pre.mfr_count:
        parts.append(f"{pre.mfr_count} MFR ({pre.mfr_sqft or '?'} SF total)")
    return ", ".join(parts) if parts else "(none recorded)"


def _resolve_lfl(fire_cases: list[EpicCase]) -> tuple[bool | None, bool]:
    """Pick the parcel's LFL/Custom claim by walking cases from most to
    least recent. Returns (claim, had_conflict).

    For each case in reverse-chronological order (by APPLY_DATE):
      1. Try DESCRIPTION; if a signal is present, that's the answer.
      2. Otherwise try PROJECT_NAME; if a signal is present, that's the answer.
    If neither field on the most recent case yields a signal, fall through
    to the next-most-recent case. None means we couldn't determine the
    claim from any case.

    `had_conflict` is True iff cases yielded two or more distinct non-None
    signals. The chosen value is still deterministic per the rule above —
    the flag just surfaces noisy/disagreeing source data for human review.
    """
    # Sort descending by APPLY_DATE; cases without a date sort last so they
    # don't drown out cases that do carry recency evidence.
    ordered = sorted(
        fire_cases,
        key=lambda c: c.get("APPLY_DATE") or 0,
        reverse=True,
    )

    chosen: bool | None = None
    all_signals: list[bool] = []

    for case in ordered:
        desc_signal = extract_lfl_claim(case.get("DESCRIPTION"))
        pname_signal = extract_lfl_claim(case.get("PROJECT_NAME"))
        if desc_signal is not None:
            all_signals.append(desc_signal)
        if pname_signal is not None:
            all_signals.append(pname_signal)
        if chosen is None:
            if desc_signal is not None:
                chosen = desc_signal
            elif pname_signal is not None:
                chosen = pname_signal

    conflict = len(set(all_signals)) > 1
    return chosen, conflict


def filter_fire_cases(cases: list[EpicCase]) -> list[EpicCase]:
    fire: list[EpicCase] = []
    for case in cases:
        if case.get("DISASTER_TYPE") == _EATON_DISASTER:
            fire.append(case)
            continue
        desc = case.get("DESCRIPTION") or ""
        if desc and _EATON_DESC_RE.search(desc):
            fire.append(case)
    return fire


def _max_progress(cases: list[EpicCase]) -> int | None:
    nums: list[int] = []
    for c in cases:
        n = c.get("REBUILD_PROGRESS_NUM")
        if isinstance(n, (int, float)) and n is not None:
            nums.append(int(n))
    return max(nums) if nums else None


def _select_primary_permit(cases: list[EpicCase]) -> EpicCase | None:
    candidates = [
        c
        for c in cases
        if c.get("MODULENAME") == "PermitManagement"
        and c.get("WORKCLASS_NAME") in _PRIMARY_PERMIT_WORKCLASSES
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda c: c.get("REBUILD_PROGRESS_NUM") or 0)


def select_qualifying_records(cases: list[EpicCase]) -> list[EpicCase]:
    """Return all fire-related records eligible for LLM-based structure inference.

    Includes PermitManagement records with WORKCLASS_NAME ∈ {"New", "Rebuild
    Project"} and PlanManagement records with WORKCLASS_NAME == "Rebuild".
    Skips Temporary Housing Project records — RVs/trailers aren't part of the
    planned final state.
    """
    return [
        c
        for c in cases
        if (
            (
                c.get("MODULENAME") == "PermitManagement"
                and c.get("WORKCLASS_NAME") in _PRIMARY_PERMIT_WORKCLASSES
            )
            or (
                c.get("MODULENAME") == "PlanManagement"
                and c.get("WORKCLASS_NAME") == _PLAN_REBUILD_WORKCLASS
            )
        )
    ]


def _analyze_post_fire(primary: EpicCase | None) -> PostFire:
    if primary is None:
        return PostFire(None, None, None, None, None, None, None, None)

    structures = parse_description(primary.get("DESCRIPTION"))

    by_type: dict[StructType, list[ParsedStructure]] = {}
    for s in structures:
        by_type.setdefault(s.struct_type, []).append(s)

    def bucket(label: StructType) -> tuple[int, int | None]:
        items = by_type.get(label, [])
        sqfts = [s.sqft for s in items if s.sqft is not None]
        total = int(sum(sqfts)) if sqfts else None
        return len(items), total

    sfr_n, sfr_sq = bucket("sfr")
    adu_n, adu_sq = bucket("adu")
    mfr_n, mfr_sq = bucket("mfr")
    sb9_n, sb9_sq = bucket("sb9")

    return PostFire(
        sfr_count=sfr_n,
        sfr_sqft=sfr_sq,
        adu_count=adu_n,
        adu_sqft=adu_sq,
        mfr_count=mfr_n,
        mfr_sqft=mfr_sq,
        sb9_count=sb9_n,
        sb9_sqft=sb9_sq,
    )


def _compare_sfr(
    pre_sqft: int | None,
    post_sqft: int | None,
) -> SfrSizeComparison | None:
    if pre_sqft is None or post_sqft is None:
        return None
    diff = post_sqft - pre_sqft
    if abs(diff) <= _IDENTICAL_TOLERANCE:
        return "identical"
    return "larger" if diff > 0 else "smaller"


def _sum_int(values: list[float]) -> int | None:
    if not values:
        return None
    return int(sum(values))


def _to_str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None
