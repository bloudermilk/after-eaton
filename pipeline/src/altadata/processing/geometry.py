"""Per-parcel point geometry.

Two related concerns live here so they share a single source of truth:

- `dins_polygon_centroid` — the centroid of a DINS parcel polygon, used to
  assign parcels to census regions (see `spatial_aggregate`).
- `representative_point` — the best available map point for a parcel, used by
  the compact web GeoJSON. It prefers an EPIC-LA case's own point geometry
  (the permit's address location) and falls back to the DINS polygon centroid.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any

from shapely.geometry import Point, Polygon

from ..sources.schemas import DinsParcel, EpicCase, FirePerimeter
from .join import JoinedParcel


def dins_polygon_centroid(dins: DinsParcel) -> Point | None:
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


def _rings_envelope(
    records: Iterable[Mapping[str, Any]],
) -> tuple[float, float, float, float] | None:
    """`(xmin, ymin, xmax, ymax)` over every `_geometry.rings` point, or None."""
    xs: list[float] = []
    ys: list[float] = []
    for rec in records:
        geom = rec.get("_geometry") or {}
        for ring in geom.get("rings") or []:
            for point in ring:
                xs.append(float(point[0]))
                ys.append(float(point[1]))
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def bounding_envelope(
    perimeter: list[FirePerimeter],
) -> tuple[float, float, float, float]:
    """Return `(xmin, ymin, xmax, ymax)` in WGS84 spanning all perimeter rings.

    Used to bound the EPIC-LA Case History query to the burn area so we never
    page the county-wide history. Raises if no polygon geometry is present.
    """
    env = _rings_envelope(perimeter)
    if env is None:
        raise ValueError("perimeter has no polygon geometry to bound")
    return env


def parcels_bounding_envelope(
    parcels: list[DinsParcel],
) -> tuple[float, float, float, float]:
    """Return `(xmin, ymin, xmax, ymax)` spanning all DINS parcel polygons.

    Scopes the RentCast area query to the Altadena parcel population
    (COMMUNITY = 'Altadena') instead of the full Eaton fire perimeter, which
    extends miles east into unpopulated foothills. Every parcel a sale/listing
    can join back to lies in this box, so the covering circle stays tight while
    still reaching every parcel. Raises if no parcel carries geometry.
    """
    env = _rings_envelope(parcels)
    if env is None:
        raise ValueError("DINS parcels have no polygon geometry to bound")
    return env


def circle_from_bounds(
    bounds: tuple[float, float, float, float],
) -> tuple[float, float, float]:
    """Return `(latitude, longitude, radius_miles)` for a WGS84 bounding box.

    RentCast's area queries take a center point + radius rather than an
    envelope, so we wrap the burn-area bounds in the smallest circle that
    covers them (center-to-corner distance, +5% margin, capped at RentCast's
    100-mile maximum). Used to scope the sales/listing pulls to the burn area.
    """
    xmin, ymin, xmax, ymax = bounds
    lat = (ymin + ymax) / 2
    lon = (xmin + xmax) / 2
    mi_per_deg_lat = 69.0
    mi_per_deg_lon = 69.0 * math.cos(math.radians(lat))
    half_lat_mi = (ymax - ymin) / 2 * mi_per_deg_lat
    half_lon_mi = (xmax - xmin) / 2 * mi_per_deg_lon
    radius = math.hypot(half_lat_mi, half_lon_mi) * 1.05
    return lat, lon, min(round(radius, 3), 100.0)


def representative_point(joined: JoinedParcel) -> tuple[float, float] | None:
    """Return the best available `(lon, lat)` map point for a parcel.

    Prefers an EPIC-LA case's own point geometry — every case for a parcel
    shares the same `MAIN_AIN` and sits at the parcel's address location, so
    any valid case point is representative. Falls back to the centroid of the
    DINS parcel polygon. Returns `None` only when neither is available.
    """
    for case in joined.cases:
        point = _epic_point(case)
        if point is not None:
            return point
    centroid = dins_polygon_centroid(joined.din)
    if centroid is None:
        return None
    return (centroid.x, centroid.y)


def _epic_point(case: EpicCase) -> tuple[float, float] | None:
    geom = case.get("_geometry") or {}
    x = geom.get("x")
    y = geom.get("y")
    if isinstance(x, (int, float)) and isinstance(y, (int, float)):
        return (float(x), float(y))
    return None
