"""Assign parcels to census regions and roll up per-region counts.

Each parcel is assigned to exactly one region by centroid containment so
per-region counts always sum back to the burn-area totals in
`summary.json`. The output of this module powers the per-tract /
per-block-group GeoJSON files.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from shapely.geometry import Polygon, shape
from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree

from ..outputs.geojson_writer import esri_to_geojson
from ..sources.schemas import DinsParcel
from .aggregate import RegionCounts, count_parcels
from .parcel_analysis import ParcelResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegionFeature:
    """A region (tract or block group) with its identifier fields, GeoJSON
    geometry, and aggregated parcel counts.
    """

    identifiers: dict[str, str]
    geometry: dict[str, Any] | None
    counts: RegionCounts


@dataclass(frozen=True)
class SpatialAggregation:
    features: list[RegionFeature]
    unassigned_ains: list[str]


def aggregate_by_region(
    parcels: list[tuple[ParcelResult, DinsParcel]],
    regions: list[dict[str, Any]],
    *,
    id_fields: list[str],
) -> SpatialAggregation:
    """Assign each parcel to a region and emit one `RegionFeature` per region.

    `parcels` is a list of `(result, dins)` pairs — `dins` carries the
    parcel polygon used to compute its centroid.

    `regions` is a list of raw ArcGIS records (each carrying `_geometry`
    plus the id fields named in `id_fields`). The first id in `id_fields`
    is the primary region key; the rest (e.g. parent CT20 on a block group,
    or LABEL) are passed through as identifier properties.

    Regions with zero parcels are still emitted (with all counts = 0) so
    the consumer gets a stable geographic frame regardless of source drift.

    Parcels whose centroid does not fall inside any region are returned in
    `unassigned_ains` so the caller can surface them via QC. They are not
    counted into any region.
    """
    region_geoms = [_region_polygon(r) for r in regions]
    primary_field = id_fields[0]
    region_keys = [str(r[primary_field]) for r in regions]

    by_region: dict[str, list[ParcelResult]] = {k: [] for k in region_keys}

    valid_indices = [i for i, g in enumerate(region_geoms) if g is not None]
    valid_geoms: list[BaseGeometry] = [g for g in region_geoms if g is not None]
    tree: STRtree | None = STRtree(valid_geoms) if valid_geoms else None

    unassigned: list[str] = []
    for result, dins in parcels:
        centroid = _parcel_centroid(dins)
        if centroid is None or tree is None:
            unassigned.append(result.ain)
            continue
        match_idx = _find_containing_region(tree, valid_geoms, centroid)
        if match_idx is None:
            unassigned.append(result.ain)
            continue
        region_key = region_keys[valid_indices[match_idx]]
        by_region[region_key].append(result)

    if unassigned:
        logger.info(
            "spatial: %d/%d parcels unassigned to any region",
            len(unassigned),
            len(parcels),
        )

    features: list[RegionFeature] = []
    for region in regions:
        key = str(region[primary_field])
        identifiers = {f.lower(): _str_or_empty(region.get(f)) for f in id_fields}
        features.append(
            RegionFeature(
                identifiers=identifiers,
                geometry=esri_to_geojson(region.get("_geometry")),
                counts=count_parcels(by_region[key]),
            )
        )
    return SpatialAggregation(features=features, unassigned_ains=unassigned)


def _parcel_centroid(dins: DinsParcel) -> BaseGeometry | None:
    geom = dins.get("_geometry") or {}
    rings = geom.get("rings") or []
    if not rings:
        return None
    polygons: list[Polygon] = []
    for ring in rings:
        if len(ring) >= 3:
            polygons.append(Polygon(ring))
    if not polygons:
        return None
    if len(polygons) == 1:
        return polygons[0].centroid
    # Multi-ring parcel: take the largest ring's centroid. Avoids the
    # complexity of true multipolygons (interior rings vs. disjoint outer
    # rings) while staying deterministic.
    return max(polygons, key=lambda p: p.area).centroid


def _region_polygon(region: dict[str, Any]) -> BaseGeometry | None:
    geojson = esri_to_geojson(region.get("_geometry"))
    if not geojson:
        return None
    try:
        return shape(geojson)
    except (ValueError, TypeError):
        return None


def _find_containing_region(
    tree: STRtree,
    geoms: list[BaseGeometry],
    centroid: BaseGeometry,
) -> int | None:
    """Return the index (into `geoms`) of the region polygon containing
    `centroid`, or `None` if no polygon contains it.

    STRtree returns candidate indices by bounding-box overlap; the actual
    containment check is exact. A centroid sitting exactly on a shared
    boundary is awarded to the nearest candidate (deterministic tiebreaker)
    so it doesn't get reported as unassigned.
    """
    candidates = tree.query(centroid)
    if len(candidates) == 0:
        return None
    for idx in candidates:
        if geoms[int(idx)].contains(centroid):
            return int(idx)
    nearest = min(candidates, key=lambda i: geoms[int(i)].distance(centroid))
    return int(nearest)


def _str_or_empty(value: Any) -> str:
    if value is None:
        return ""
    return str(value)
