"""Per-parcel point geometry.

Two related concerns live here so they share a single source of truth:

- `dins_polygon_centroid` — the centroid of a DINS parcel polygon, used to
  assign parcels to census regions (see `spatial_aggregate`).
- `representative_point` — the best available map point for a parcel, used by
  the compact web GeoJSON. It prefers an EPIC-LA case's own point geometry
  (the permit's address location) and falls back to the DINS polygon centroid.
"""

from __future__ import annotations

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


def bounding_envelope(
    perimeter: list[FirePerimeter],
) -> tuple[float, float, float, float]:
    """Return `(xmin, ymin, xmax, ymax)` in WGS84 spanning all perimeter rings.

    Used to bound the EPIC-LA Case History query to the burn area so we never
    page the county-wide history. Raises if no polygon geometry is present.
    """
    xs: list[float] = []
    ys: list[float] = []
    for rec in perimeter:
        geom = rec.get("_geometry") or {}
        for ring in geom.get("rings") or []:
            for point in ring:
                xs.append(float(point[0]))
                ys.append(float(point[1]))
    if not xs:
        raise ValueError("perimeter has no polygon geometry to bound")
    return (min(xs), min(ys), max(xs), max(ys))


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
