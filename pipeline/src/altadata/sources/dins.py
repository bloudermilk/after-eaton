"""Fetch DINS-tagged parcels for the Eaton Fire burn area (Altadena)."""

from __future__ import annotations

from .arcgis import fetch_all
from .schemas import DinsParcel, validate_dins

DINS_QUERY_URL = (
    "https://services.arcgis.com/RmCCgQtiZLDCtblq/ArcGIS/rest/services/"
    "2025_Parcels_with_DINS_data/FeatureServer/5/query"
)

# DINS tags damaged parcels with COMMUNITY = "Altadena" for Eaton.
_ALTADENA_WHERE = "COMMUNITY = 'Altadena'"


def fetch_dins_parcels(
    *,
    where: str = _ALTADENA_WHERE,
    url: str = DINS_QUERY_URL,
) -> list[DinsParcel]:
    """Fetch and validate DINS parcels for the Altadena burn area."""
    raw = fetch_all(url, {"where": where})
    return validate_dins(raw)
