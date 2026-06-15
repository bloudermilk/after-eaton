"""Normalization helpers: damage levels, BSD safety-assessment tags,
rebuild progress, and EPIC-LA case-status classification."""

from __future__ import annotations

from enum import StrEnum

from ..sources.schemas import EpicCase


class DamageLevel(StrEnum):
    """FIRESCOPE %-loss bucket from DINS `DAMAGE_1`."""

    NO_DAMAGE = "no_damage"
    NO_DATA = "no_data"
    AFFECTED = "affected"  # 1-9%
    MINOR = "minor"  # 10-25%
    MAJOR = "major"  # 26-50%
    DESTROYED = "destroyed"  # >50%


class BsdStatus(StrEnum):
    """Safety-assessment tag from DINS `BSD_Tag`. This is what the LA County
    Recovery Map uses for its headline destroyed/damaged-parcel counts.
    Per the published metric definitions:
      - red:   "Red Tagged" — uninhabitable (Recovery Map: "destroyed unit")
      - yellow:"Yellow Tagged" — limited access (Recovery Map: "damaged unit")
      - green: "Green Tagged" — safe to occupy
      - none:  no safety-assessment tag recorded
    """

    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"
    NONE = "none"


RAW_TO_DAMAGE: dict[str | None, DamageLevel] = {
    "No Damage": DamageLevel.NO_DAMAGE,
    "No Data/Vacant": DamageLevel.NO_DATA,
    "Affected (1-9%)": DamageLevel.AFFECTED,
    "Minor (10-25%)": DamageLevel.MINOR,
    "Major (26-50%)": DamageLevel.MAJOR,
    "Destroyed (>50%)": DamageLevel.DESTROYED,
    None: DamageLevel.NO_DATA,
}

RAW_TO_BSD: dict[str | None, BsdStatus] = {
    "Red": BsdStatus.RED,
    "Yellow": BsdStatus.YELLOW,
    "Green": BsdStatus.GREEN,
    None: BsdStatus.NONE,
    "": BsdStatus.NONE,
}


def normalize_damage(raw: str | None) -> DamageLevel:
    """Map a raw DINS DAMAGE_1 string to the canonical DamageLevel.

    Unknown values fall back to NO_DATA so the pipeline continues, but the
    caller is responsible for surfacing them via QC.
    """
    return RAW_TO_DAMAGE.get(raw, DamageLevel.NO_DATA)


def normalize_bsd(raw: str | None) -> BsdStatus:
    """Map a raw DINS BSD_Tag string to BsdStatus. Unknown values map to NONE."""
    if raw is None:
        return BsdStatus.NONE
    return RAW_TO_BSD.get(raw.strip(), BsdStatus.NONE)


REBUILD_PROGRESS_LABELS: dict[int, str] = {
    1: "Rebuild Applications Received",
    2: "Zoning Reviews Cleared",
    3: "Full Building Plans Received",
    4: "Building Plans Approved",
    5: "Building Permits Issued",
    6: "Rebuild In Construction",
    7: "Construction Completed",
}


def rebuild_progress_label(num: int | None) -> str | None:
    if num is None:
        return None
    return REBUILD_PROGRESS_LABELS.get(num)


# The seven INDEPENDENT rebuild-progress milestones, in lifecycle order. Each
# tuple is (stage number, short key used by outputs/frontend, EPIC-LA field).
# A case has "reached" a milestone when its field is non-null. The milestones
# are not strictly nested (a case can hold a later one without an earlier one),
# which is why a milestone count must be taken per field rather than derived
# from the latest-stage `REBUILD_PROGRESS_NUM`. See METHODOLOGY.md → Rebuild
# progress for why the latest-stage field is unsuitable for these counts.
REBUILD_STAGES: tuple[tuple[int, str, str], ...] = (
    (1, "app_received", "REBUILD_APP_RECEIVED"),
    (2, "zoning_cleared", "ZONING_REV_CLEARED"),
    (3, "plans_received", "BUILD_PLAN_REV_PROC"),
    (4, "plans_approved", "BUILD_PLAN_APPROVED"),
    (5, "permit_issued", "BUILD_PERMIT_ISSUED"),
    (6, "in_construction", "REBUILD_IN_CONS"),
    (7, "construction_completed", "CONS_COMPLETED"),
)


# EPIC-LA case `STATUS` classification.
#
# We must not assert a future rebuild state from a record the county has marked
# dead. Cases whose status is terminal-negative (voided, cancelled, withdrawn,
# revoked, denied, rejected, expired) are dropped from every count; pending /
# submitted / approved / issued / completed cases are kept (they happened, or
# still might). This is a DENYLIST: anything not explicitly inactive is counted,
# including null/unknown statuses ("might happen").
#
# `ACTIVE_STATUSES` is the allowlist of recognized live statuses observed across
# both EPIC-LA sources. It is kept exact (not used for filtering) so that a NEW
# county status — in neither set — trips the `unrecognized_status_count` QC gate
# (see qc/aggregate.py) and forces a human to classify it before it skews counts.
# Both sets hold normalized values: lowercased and outer-trimmed.
INACTIVE_STATUSES: frozenset[str] = frozenset(
    {
        "void",
        "voided",
        "cancelled",
        "canceled",
        "withdrawn",
        "revoked",
        "denied",
        "rejected",
        "expired",
    }
)

ACTIVE_STATUSES: frozenset[str] = frozenset(
    {
        "issued",
        "open",
        "waiting for applicant",
        "in review",
        "review",
        "approved pending clearances",
        "approved ready for permit",
        "approved",
        "zoning cleared",
        "hold",
        "on hold",
        "new",
        "new - online",
        "finaled",
        "completed",
        "accepted",
        "recorded",
    }
)


def _normalize_status(status: str | None) -> str:
    """Lowercase and outer-trim a raw STATUS string; None/missing -> ""."""
    return (status or "").strip().lower()


def is_active_status(status: str | None) -> bool:
    """True unless the status is explicitly terminal-negative.

    Null/empty/unknown statuses return True (counted) — the denylist only
    excludes values it positively recognizes as dead.
    """
    return _normalize_status(status) not in INACTIVE_STATUSES


def is_recognized_status(status: str | None) -> bool:
    """True if the status is null/empty (expected) or in a known set.

    Returns False for any value we have never classified — the signal the
    `unrecognized_status_count` QC gate counts.
    """
    norm = _normalize_status(status)
    return norm == "" or norm in ACTIVE_STATUSES or norm in INACTIVE_STATUSES


def filter_active_cases(cases: list[EpicCase]) -> list[EpicCase]:
    """Drop cases whose STATUS is terminal-negative (see INACTIVE_STATUSES)."""
    return [c for c in cases if is_active_status(c.get("STATUS"))]
