"""Per-parcel QC warnings (do not abort, just collect)."""

from __future__ import annotations

from dataclasses import dataclass

from ..processing.description_parser import parse_description
from ..processing.join import JoinedParcel
from ..processing.normalize import DamageLevel
from ..processing.parcel_analysis import ParcelResult


@dataclass(frozen=True)
class RecordWarning:
    ain: str
    code: str
    detail: str
    # "data": flags a parser/source quality issue worth fixing.
    # "info": surfaces real-world ambiguity that doesn't indicate a bug.
    # Only "data" warnings count toward the warning_rate threshold.
    severity: str = "data"


_MIN_REASONABLE_SQFT = 200
_MAX_REASONABLE_SQFT = 20_000


def check_record(
    joined: JoinedParcel,
    result: ParcelResult,
) -> list[RecordWarning]:
    warnings: list[RecordWarning] = []

    if result.damage == DamageLevel.DESTROYED and not joined.cases:
        warnings.append(
            RecordWarning(
                ain=result.ain,
                code="destroyed_no_epicla",
                detail="parcel marked DESTROYED but has no EPIC-LA cases",
                severity="info",
            )
        )

    if result.post_sfr_sqft is not None:
        if (
            result.post_sfr_sqft < _MIN_REASONABLE_SQFT
            or result.post_sfr_sqft > _MAX_REASONABLE_SQFT
        ):
            warnings.append(
                RecordWarning(
                    ain=result.ain,
                    code="implausible_post_sfr_sqft",
                    detail=f"post_sfr_sqft={result.post_sfr_sqft}",
                )
            )

    primary = _find_primary_permit_with_units(joined)
    if primary is not None:
        structures = parse_description(primary.get("DESCRIPTION"))
        if structures and all(s.struct_type == "unknown" for s in structures):
            warnings.append(
                RecordWarning(
                    ain=result.ain,
                    code="permit_all_unknown_structures",
                    detail="NEW_DWELLING_UNITS > 0 but description parsed as unknown",
                )
            )

    if result.sfr_size_comparison is not None and result.lfl_claimed is None:
        warnings.append(
            RecordWarning(
                ain=result.ain,
                code="size_compared_without_lfl_signal",
                detail=(
                    f"sfr_size_comparison={result.sfr_size_comparison} "
                    "but no source states LFL/Custom"
                ),
                severity="info",
            )
        )

    if result.lfl_conflict:
        warnings.append(
            RecordWarning(
                ain=result.ain,
                code="lfl_conflict",
                detail=(
                    "LFL/Custom signals disagreed across PROJECT_NAME / "
                    "DESCRIPTION fields; most-recent case's signal won"
                ),
                severity="data",
            )
        )

    return warnings


def _find_primary_permit_with_units(joined: JoinedParcel) -> dict | None:  # type: ignore[type-arg]
    for case in joined.cases:
        if case.get("MODULENAME") != "PermitManagement":
            continue
        units = case.get("NEW_DWELLING_UNITS")
        if units and units > 0:
            return dict(case)
    return None
