"""Write per-region (census tract / block group) GeoJSON FeatureCollections."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..processing.spatial_aggregate import RegionFeature


def write_regions_geojson(
    regions: list[RegionFeature],
    out_path: Path,
    *,
    generated_at: str,
) -> None:
    """Write a FeatureCollection with one feature per region.

    Properties on each feature are the region's identifiers (e.g. ct20,
    bg20, label) plus every count field from `RegionCounts`. Geometry is
    the region polygon in EPSG:4326.
    """
    features = [_to_feature(r) for r in regions]
    payload = {
        "type": "FeatureCollection",
        "metadata": {"generated_at": generated_at},
        "features": features,
    }
    out_path.write_text(json.dumps(payload))


def _to_feature(region: RegionFeature) -> dict[str, Any]:
    properties: dict[str, Any] = dict(region.identifiers)
    properties.update(asdict(region.counts))
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": region.geometry,
    }
