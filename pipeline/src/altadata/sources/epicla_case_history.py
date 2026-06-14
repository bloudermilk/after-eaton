"""Fetch SB-1123 small-lot subdivision cases from the EPIC-LA Case History.

SB-1123 subdivisions are filed as general planning cases with a null
`DISASTER_TYPE`, so the Eaton-tagged EPIC view (`sources/epicla.py`) never sees
them. We pull them from the county-wide Case History view instead, bounded to
the burn-area envelope and to post-fire applications so we never page the full
~900k-record history. Each adapted record is stamped with `_source` so the
downstream fire-case filter treats it as an Eaton recovery case (which it is,
by construction).
"""

from __future__ import annotations

import logging

from .arcgis import fetch_all
from .schemas import CASE_HISTORY_SOURCE, EpicCase, validate_epicla

logger = logging.getLogger(__name__)

# Layer 0 of the county-wide EPIC-LA Case History view holds case records.
CASE_HISTORY_QUERY_URL = (
    "https://services.arcgis.com/RmCCgQtiZLDCtblq/ArcGIS/rest/services/"
    "EPIC-LA_Case_History_view/FeatureServer/0/query"
)

# SB-1123 mentions across the three pathway-bearing text fields. Intentionally
# broad (it casts a wide net at the server); `_resolve_sb_pathway` re-validates
# each returned case with the `_SB1123_RE` regex.
_SB1123_WHERE = (
    "(UPPER(DESCRIPTION) LIKE '%SB 1123%' OR UPPER(DESCRIPTION) LIKE '%SB-1123%' "
    "OR UPPER(DESCRIPTION) LIKE '%SB1123%' "
    "OR UPPER(DESCRIPTION) LIKE '%SENATE BILL 1123%' "
    "OR UPPER(PROJECT_NAME) LIKE '%1123%' OR UPPER(PROJECTNAME) LIKE '%1123%')"
)
# Eaton Fire ignition; we only want applications filed on or after it.
_POST_FIRE_WHERE = "APPLY_DATE >= DATE '2025-01-07'"


def fetch_case_history_sb1123(
    envelope: tuple[float, float, float, float],
    *,
    url: str = CASE_HISTORY_QUERY_URL,
) -> list[EpicCase]:
    """Fetch burn-area SB-1123 cases, adapted to the `EpicCase` shape.

    ``envelope`` is ``(xmin, ymin, xmax, ymax)`` in WGS84 — the burn-area
    bounding box, used as a server-side spatial filter. The Case History view
    shares the Eaton view's schema except it omits `REBUILD_PROGRESS_NUM` (these
    planning cases carry no numeric rebuild stage), so we backfill it as `None`
    to satisfy the schema, drop any record with no joinable `MAIN_AIN`, and
    stamp `_source` for the fire-case filter.
    """
    xmin, ymin, xmax, ymax = envelope
    raw = fetch_all(
        url,
        {
            "where": f"{_SB1123_WHERE} AND {_POST_FIRE_WHERE}",
            "geometry": f"{xmin},{ymin},{xmax},{ymax}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
        },
    )
    adapted = []
    for rec in raw:
        if not rec.get("MAIN_AIN"):
            continue  # no parcel to join to — drops out anyway
        rec.setdefault("REBUILD_PROGRESS_NUM", None)
        rec["_source"] = CASE_HISTORY_SOURCE
        adapted.append(rec)
    dropped = len(raw) - len(adapted)
    if dropped:
        logger.info("case-history: dropped %d records with no MAIN_AIN", dropped)
    return validate_epicla(adapted)
