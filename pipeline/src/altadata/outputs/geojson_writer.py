"""Write the parcel-level GeoJSON FeatureCollection."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..processing.aggregate import adu_bucket, lfl_bucket, sfr_size_bucket
from ..processing.geometry import representative_point
from ..processing.join import JoinedParcel
from ..processing.parcel_analysis import ParcelResult
from ..sources.schemas import DinsParcel


def write_parcels_geojson(
    pairs: list[tuple[ParcelResult, DinsParcel]],
    out_path: Path,
    *,
    generated_at: str,
) -> None:
    features = [_to_feature(result, parcel) for result, parcel in pairs]
    payload = {
        "type": "FeatureCollection",
        "metadata": {"generated_at": generated_at},
        "features": features,
    }
    out_path.write_text(json.dumps(payload))


def write_parcels_compact_geojson(
    pairs: list[tuple[ParcelResult, JoinedParcel]],
    out_path: Path,
    *,
    generated_at: str,
) -> None:
    """Write the web-optimized parcel GeoJSON consumed by the frontend map.

    One `Point` per parcel (centroid via `representative_point`) carrying only
    the properties the map reads. Parcels with no resolvable point are dropped
    since they cannot be plotted. The full-fidelity `parcels.geojson` (polygons
    + every attribute) is written separately and left untouched.
    """
    features: list[dict[str, Any]] = []
    for result, joined in pairs:
        point = representative_point(joined)
        if point is None:
            continue
        features.append(_to_compact_feature(result, point))
    payload = {
        "type": "FeatureCollection",
        "metadata": {"generated_at": generated_at},
        "features": features,
    }
    out_path.write_text(json.dumps(payload))


def _to_compact_feature(
    result: ParcelResult, point: tuple[float, float]
) -> dict[str, Any]:
    return {
        "type": "Feature",
        "properties": {
            "ain": result.ain,
            "address": result.address,
            "sfr_size_bucket": sfr_size_bucket(result),
            "lfl_bucket": lfl_bucket(result),
            "adu_bucket": adu_bucket(result),
            "adds_sb9": result.adds_sb9,
            "adds_sb1123": result.adds_sb1123,
        },
        "geometry": {"type": "Point", "coordinates": [point[0], point[1]]},
    }


def _to_feature(result: ParcelResult, parcel: DinsParcel) -> dict[str, Any]:
    raw_geom = parcel.get("_geometry")
    geometry = esri_to_geojson(raw_geom)
    properties = asdict(result)
    properties["damage"] = result.damage.value
    properties["bsd_status"] = result.bsd_status.value
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": geometry,
    }


def esri_to_geojson(geom: dict[str, Any] | None) -> dict[str, Any] | None:
    """Convert an Esri ArcGIS geometry dict to a GeoJSON geometry.

    Public so the per-region GeoJSON writer can reuse the same conversion.
    """
    if not geom:
        return None
    rings = geom.get("rings")
    if rings:
        if len(rings) == 1:
            return {"type": "Polygon", "coordinates": rings}
        return {"type": "MultiPolygon", "coordinates": [[r] for r in rings]}
    if "x" in geom and "y" in geom:
        return {"type": "Point", "coordinates": [geom["x"], geom["y"]]}
    paths = geom.get("paths")
    if paths:
        if len(paths) == 1:
            return {"type": "LineString", "coordinates": paths[0]}
        return {"type": "MultiLineString", "coordinates": paths}
    return None
