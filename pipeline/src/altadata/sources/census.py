"""Fetch 2020 census tracts (by perimeter envelope) and the block groups
that subdivide them (by parent CT20).

Tracts are filtered spatially against the fire-perimeter envelope; block
groups are then filtered to the parent tract IDs we just fetched. The
resulting set of block groups is exactly the partition of those tracts —
no orphan block groups whose tract was filtered out, no stray groups
from neighbouring tracts that happened to clip the perimeter envelope.
"""

from __future__ import annotations

import json

from .arcgis import fetch_all
from .schemas import (
    CensusBlockGroup,
    CensusTract,
    FirePerimeter,
    validate_census_block_groups,
    validate_census_tracts,
)

CENSUS_TRACTS_QUERY_URL = (
    "https://public.gis.lacounty.gov/public/rest/services/"
    "LACounty_Dynamic/Demographics/MapServer/14/query"
)
CENSUS_BLOCK_GROUPS_QUERY_URL = (
    "https://public.gis.lacounty.gov/public/rest/services/"
    "LACounty_Dynamic/Demographics/MapServer/15/query"
)


def fetch_census_tracts(
    perimeter: list[FirePerimeter],
    *,
    url: str = CENSUS_TRACTS_QUERY_URL,
) -> list[CensusTract]:
    """Fetch tracts intersecting the perimeter envelope (EPSG:4326)."""
    raw = fetch_all(url, _envelope_params(perimeter))
    return validate_census_tracts(raw)


def fetch_census_block_groups(
    tracts: list[CensusTract],
    *,
    url: str = CENSUS_BLOCK_GROUPS_QUERY_URL,
) -> list[CensusBlockGroup]:
    """Fetch every block group whose parent CT20 is in `tracts`.

    Filtering by parent tract (rather than the perimeter envelope) means
    each fetched tract is partitioned exactly by its block groups — useful
    for invariants like "sum of a tract's block-group counts equals the
    tract's count".
    """
    if not tracts:
        return []
    quoted = ",".join(f"'{t['CT20']}'" for t in tracts)
    raw = fetch_all(url, {"where": f"CT20 IN ({quoted})"})
    return validate_census_block_groups(raw)


def _envelope_params(perimeter: list[FirePerimeter]) -> dict[str, str]:
    xmin, ymin, xmax, ymax = _perimeter_envelope(perimeter)
    geometry = json.dumps({"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax})
    return {
        "where": "1=1",
        "geometry": geometry,
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
    }


def _perimeter_envelope(
    perimeter: list[FirePerimeter],
) -> tuple[float, float, float, float]:
    """Return (xmin, ymin, xmax, ymax) covering all perimeter rings.

    Geometry is in EPSG:4326 because `arcgis.fetch_all` requests `outSR=4326`.
    """
    xs: list[float] = []
    ys: list[float] = []
    for feat in perimeter:
        geom = feat.get("_geometry") or {}
        for ring in geom.get("rings") or []:
            for pt in ring:
                xs.append(float(pt[0]))
                ys.append(float(pt[1]))
    if not xs or not ys:
        raise ValueError("fire perimeter has no usable ring coordinates")
    return min(xs), min(ys), max(xs), max(ys)
