"""Write the parcel-level GeoJSON FeatureCollection."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..processing.aggregate import adu_bucket, lfl_bucket, sfr_size_bucket
from ..processing.geometry import representative_point
from ..processing.join import JoinedParcel
from ..processing.normalize import REBUILD_STAGES, BsdStatus
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
    properties: dict[str, Any] = {
        "ain": result.ain,
        "address": result.address,
        "sfr_size_bucket": sfr_size_bucket(result),
        "lfl_bucket": lfl_bucket(result),
        "adu_bucket": adu_bucket(result),
        "adds_sb9": result.adds_sb9,
        "adds_sb1123": result.adds_sb1123,
        # County "Damaged/Destroyed Parcels" scope: Red- or Yellow-tagged in the
        # post-fire Safety Assessment. Lets the map filter to the funnel's
        # "Damaged or destroyed" baseline (== summary.bsd_red_or_yellow_count).
        "bsd_red_or_yellow": result.bsd_status in (BsdStatus.RED, BsdStatus.YELLOW),
        # Furthest milestone reached, for the map's stage color ramp.
        "rebuild_stage": result.rebuild_stage,
        # Raw pre/post counts + sqft and the damage/safety classifications power
        # the per-parcel detail popup. The buckets above are for coloring; the
        # popup shows the underlying numbers. Post-fire fields stay null (not 0)
        # when no primary permit was found, so "not yet filed" reads correctly.
        "pre_sfr_count": result.pre_sfr_count,
        "post_sfr_count": result.post_sfr_count,
        "pre_sfr_sqft": result.pre_sfr_sqft,
        "post_sfr_sqft": result.post_sfr_sqft,
        "pre_adu_count": result.pre_adu_count,
        "post_adu_count": result.post_adu_count,
        "added_adu_count": result.added_adu_count,
        # FIRESCOPE %-loss bucket (destroyed/major/…) and full Red/Yellow/Green
        # safety tag, for context in the popup.
        "damage": result.damage.value,
        "bsd_status": result.bsd_status.value,
    }
    # One boolean per rebuild milestone, set when the parcel's furthest stage is
    # at or beyond that milestone (monotonic — assumes earlier stages were
    # passed). Lets the map filter to "reached stage N" and keeps the lit dots
    # equal to the card's count for that row. Derived from REBUILD_STAGES so the
    # props stay in lockstep with the pipeline.
    for num, key, _ in REBUILD_STAGES:
        properties[f"rebuild_{key}"] = result.rebuild_stage >= num
    return {
        "type": "Feature",
        "properties": properties,
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
