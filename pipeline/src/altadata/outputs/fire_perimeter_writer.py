"""Write the Eaton Fire burn perimeter as a web-ready GeoJSON outline.

The ArcGIS source carries the perimeter as ~20 overlapping "heat perimeter"
rings at 12-13 decimal places. Rendered raw that would draw spurious interior
seam lines and ship far more coordinate data than an outline needs. So we
dissolve the rings into a single boundary (`unary_union`), simplify it, and
round coordinates before serializing — the frontend gets one small, clean
outline. Geometry stays in WGS84 (EPSG:4326), matching the other outputs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from ..sources.schemas import FirePerimeter
from .geojson_writer import esri_to_geojson


def write_fire_perimeter_geojson(
    perimeter: list[FirePerimeter],
    out_path: Path,
    *,
    generated_at: str,
    simplify_tolerance: float = 5e-5,
    precision: int = 5,
) -> None:
    """Write the dissolved fire perimeter as a single-feature FeatureCollection.

    `simplify_tolerance` is in degrees (~5e-5 deg ≈ 5.5 m); `precision` is the
    number of decimal places coordinates are rounded to (5 ≈ 1.1 m). An empty
    `perimeter` (or one with no usable geometry) yields a FeatureCollection with
    no features rather than an error — the map treats a missing outline as
    "nothing to draw".
    """
    geoms: list[BaseGeometry] = []
    for rec in perimeter:
        geojson = esri_to_geojson(rec.get("_geometry"))
        if not geojson:
            continue
        try:
            geom = shape(geojson)
        except (ValueError, TypeError):
            continue
        if not geom.is_empty:
            geoms.append(geom)

    features: list[dict[str, Any]] = []
    if geoms:
        dissolved = unary_union(geoms)
        if simplify_tolerance > 0:
            dissolved = dissolved.simplify(simplify_tolerance, preserve_topology=True)
        features.append(
            {
                "type": "Feature",
                "properties": {"name": "Eaton Fire perimeter"},
                "geometry": _round_coords(mapping(dissolved), precision),
            }
        )

    payload = {
        "type": "FeatureCollection",
        "metadata": {"generated_at": generated_at},
        "features": features,
    }
    out_path.write_text(json.dumps(payload))


def _round_coords(obj: Any, precision: int) -> Any:
    """Recursively round every coordinate float in a GeoJSON geometry mapping."""
    if isinstance(obj, float):
        return round(obj, precision)
    if isinstance(obj, (list, tuple)):
        return [_round_coords(v, precision) for v in obj]
    if isinstance(obj, dict):
        return {k: _round_coords(v, precision) for k, v in obj.items()}
    return obj
