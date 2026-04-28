"""Fetch the Eaton Fire perimeter polygon."""

from __future__ import annotations

from .arcgis import fetch_all
from .schemas import FirePerimeter, validate_fire_perimeter

FIRE_PERIMETER_QUERY_URL = (
    "https://services.arcgis.com/RmCCgQtiZLDCtblq/arcgis/rest/services/"
    "Eaton_Fire_Perimeter/FeatureServer/0/query"
)


def fetch_fire_perimeter(
    *,
    url: str = FIRE_PERIMETER_QUERY_URL,
) -> list[FirePerimeter]:
    """Fetch and validate Eaton Fire perimeter polygons."""
    raw = fetch_all(url, {"where": "1=1"})
    return validate_fire_perimeter(raw)
