"""Fetch EPIC-LA fire recovery cases for the Eaton Fire."""

from __future__ import annotations

from .arcgis import fetch_all
from .schemas import EpicCase, validate_epicla

# Layer 0 of the EPICLA_Eaton_Palisades FeatureServer holds case records.
EPICLA_QUERY_URL = (
    "https://services.arcgis.com/RmCCgQtiZLDCtblq/arcgis/rest/services/"
    "EPICLA_Eaton_Palisades/FeatureServer/0/query"
)

_EATON_WHERE = "DISASTER_TYPE = 'Eaton Fire (01-2025)'"


def fetch_epicla_cases(
    *,
    where: str = _EATON_WHERE,
    url: str = EPICLA_QUERY_URL,
) -> list[EpicCase]:
    """Fetch and validate EPIC-LA cases for the Eaton Fire."""
    raw = fetch_all(url, {"where": where})
    return validate_epicla(raw)
