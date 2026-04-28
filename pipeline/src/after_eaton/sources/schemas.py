"""Typed records and validators for ArcGIS source data."""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict


class DinsParcel(TypedDict, total=False):
    """A single DINS-tagged parcel (LA County 2025 Parcels with DINS)."""

    AIN_1: str
    DAMAGE_1: str | None
    SQFTmain1: float | None
    DesignType1: str | None
    COMMUNITY: str | None
    # Address / identity
    APN_1: NotRequired[str | None]
    SitusFullAddress: NotRequired[str | None]
    SitusAddress: NotRequired[str | None]
    SitusCity: NotRequired[str | None]
    SitusZIP: NotRequired[str | None]
    # Use / structures
    UseDescription: NotRequired[str | None]
    UseType: NotRequired[str | None]
    STRUCTURECATEGORY: NotRequired[str | None]
    Total_Units: NotRequired[float | None]
    Tot_SqFt: NotRequired[float | None]
    DINS_Count: NotRequired[float | None]
    YearBuilt1: NotRequired[str | None]
    YearBuilt2: NotRequired[str | None]
    YearBuilt3: NotRequired[str | None]
    YearBuilt4: NotRequired[str | None]
    YearBuilt5: NotRequired[str | None]
    SQFTmain2: NotRequired[float | None]
    SQFTmain3: NotRequired[float | None]
    SQFTmain4: NotRequired[float | None]
    SQFTmain5: NotRequired[float | None]
    DesignType2: NotRequired[str | None]
    DesignType3: NotRequired[str | None]
    DesignType4: NotRequired[str | None]
    DesignType5: NotRequired[str | None]
    Units1: NotRequired[float | None]
    Units2: NotRequired[float | None]
    Units3: NotRequired[float | None]
    Units4: NotRequired[float | None]
    Units5: NotRequired[float | None]
    # Status pass-through
    Permit_Status: NotRequired[str | None]
    ROE_Status: NotRequired[str | None]
    Debris_Cleared: NotRequired[str | None]
    BSD_Tag: NotRequired[str | None]
    Fire_Name: NotRequired[str | None]
    _geometry: NotRequired[dict[str, Any] | None]


class FirePerimeter(TypedDict, total=False):
    """Eaton Fire Perimeter polygon."""

    OBJECTID: int
    type: NotRequired[str | None]
    _geometry: NotRequired[dict[str, Any] | None]


class CensusTract(TypedDict, total=False):
    """A single 2020 census tract polygon (LA County Demographics layer 14)."""

    CT20: str
    LABEL: NotRequired[str | None]
    _geometry: NotRequired[dict[str, Any] | None]


class CensusBlockGroup(TypedDict, total=False):
    """A single 2020 census block group polygon (LA County Demographics layer 15)."""

    BG20: str
    CT20: NotRequired[str | None]
    LABEL: NotRequired[str | None]
    _geometry: NotRequired[dict[str, Any] | None]


class EpicCase(TypedDict, total=False):
    """A single EPIC-LA fire recovery case."""

    MAIN_AIN: str
    MODULENAME: str
    REBUILD_PROGRESS_NUM: int | None
    DESCRIPTION: str | None
    # Identity / context
    CASENUMBER: NotRequired[str | None]
    PROJECT_NAME: NotRequired[str | None]
    PROJECTNAME: NotRequired[str | None]
    DISASTER_TYPE: NotRequired[str | None]
    WORKCLASS_NAME: NotRequired[str | None]
    USE_PROPOSED1: NotRequired[str | None]
    USE_CURR: NotRequired[str | None]
    ACCESSORY_DWELLING_UNIT: NotRequired[float | None]
    NEW_DWELLING_UNITS: NotRequired[float | None]
    JUNIOR_ADU: NotRequired[float | None]
    STAT_CLASS: NotRequired[str | None]
    REBUILD_PROGRESS: NotRequired[str | None]
    APPLY_DATE: NotRequired[float | None]
    COMPLETE_DATE: NotRequired[float | None]
    ISSUANCE_DATE: NotRequired[float | None]
    STATUS: NotRequired[str | None]
    MAIN_ADDRESS: NotRequired[str | None]
    PERMIT_VALUATION: NotRequired[float | None]
    _geometry: NotRequired[dict[str, Any] | None]


class SchemaError(ValueError):
    """Raised when a fetched record does not match the expected schema."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


_DINS_REQUIRED: dict[str, tuple[type, ...]] = {
    "AIN_1": (str,),
    "DAMAGE_1": (str, type(None)),
    "SQFTmain1": (int, float, type(None)),
    "DesignType1": (str, type(None)),
    "COMMUNITY": (str, type(None)),
}

_EPIC_REQUIRED: dict[str, tuple[type, ...]] = {
    "MAIN_AIN": (str,),
    "MODULENAME": (str,),
    "REBUILD_PROGRESS_NUM": (int, float, type(None)),
    "DESCRIPTION": (str, type(None)),
}

_TRACT_REQUIRED: dict[str, tuple[type, ...]] = {
    "CT20": (str,),
}

_BG_REQUIRED: dict[str, tuple[type, ...]] = {
    "BG20": (str,),
}


def _check_required(
    record: dict[str, Any],
    required: dict[str, tuple[type, ...]],
    *,
    label: str,
) -> None:
    for field, allowed in required.items():
        if field not in record:
            raise SchemaError(f"{label}: missing required field '{field}'", field=field)
        value = record[field]
        if not isinstance(value, allowed):
            raise SchemaError(
                f"{label}: field '{field}' has unexpected type "
                f"{type(value).__name__} (expected one of "
                f"{[t.__name__ for t in allowed]})",
                field=field,
            )


def validate_dins(records: list[dict[str, Any]]) -> list[DinsParcel]:
    """Validate raw DINS feature dicts and narrow them to DinsParcel."""
    out: list[DinsParcel] = []
    for raw in records:
        _check_required(raw, _DINS_REQUIRED, label="DINS")
        ain = raw["AIN_1"]
        if not ain or not isinstance(ain, str):
            raise SchemaError("DINS: AIN_1 must be a non-empty string", field="AIN_1")
        out.append(raw)  # type: ignore[arg-type]
    return out


def validate_epicla(records: list[dict[str, Any]]) -> list[EpicCase]:
    """Validate raw EPIC-LA feature dicts and narrow them to EpicCase."""
    out: list[EpicCase] = []
    for raw in records:
        _check_required(raw, _EPIC_REQUIRED, label="EPIC-LA")
        ain = raw["MAIN_AIN"]
        if not ain or not isinstance(ain, str):
            raise SchemaError(
                "EPIC-LA: MAIN_AIN must be a non-empty string", field="MAIN_AIN"
            )
        out.append(raw)  # type: ignore[arg-type]
    return out


def validate_fire_perimeter(records: list[dict[str, Any]]) -> list[FirePerimeter]:
    """Validate raw fire-perimeter records.

    The fire-perimeter layer carries no required attribute fields beyond
    what ArcGIS auto-generates, so we only confirm geometry is present.
    """
    out: list[FirePerimeter] = []
    for raw in records:
        if not raw.get("_geometry"):
            raise SchemaError(
                "fire-perimeter: record missing geometry", field="_geometry"
            )
        out.append(raw)  # type: ignore[arg-type]
    return out


def validate_census_tracts(records: list[dict[str, Any]]) -> list[CensusTract]:
    """Validate raw census-tract feature dicts and narrow them to CensusTract."""
    out: list[CensusTract] = []
    for raw in records:
        _check_required(raw, _TRACT_REQUIRED, label="census-tracts")
        ct = raw["CT20"]
        if not ct or not isinstance(ct, str):
            raise SchemaError(
                "census-tracts: CT20 must be a non-empty string", field="CT20"
            )
        out.append(raw)  # type: ignore[arg-type]
    return out


def validate_census_block_groups(
    records: list[dict[str, Any]],
) -> list[CensusBlockGroup]:
    """Validate raw census-block-group feature dicts."""
    out: list[CensusBlockGroup] = []
    for raw in records:
        _check_required(raw, _BG_REQUIRED, label="census-block-groups")
        bg = raw["BG20"]
        if not bg or not isinstance(bg, str):
            raise SchemaError(
                "census-block-groups: BG20 must be a non-empty string", field="BG20"
            )
        out.append(raw)  # type: ignore[arg-type]
    return out
