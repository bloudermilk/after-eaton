"""Normalization helpers: damage levels, BSD safety-assessment tags,
rebuild progress."""

from __future__ import annotations

from enum import StrEnum


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
