"""Fetch EPIC-LA fire recovery cases for the Eaton Fire."""

from __future__ import annotations

import logging

from .arcgis import SourceError, fetch_all
from .schemas import EpicCase, validate_epicla

logger = logging.getLogger(__name__)

# Layer 0 of the EPICLA_Eaton_Palisades FeatureServer holds case records.
EPICLA_QUERY_URL = (
    "https://services.arcgis.com/RmCCgQtiZLDCtblq/arcgis/rest/services/"
    "EPICLA_Eaton_Palisades/FeatureServer/0/query"
)

_EATON_WHERE = "DISASTER_TYPE = 'Eaton Fire (01-2025)'"


def fetch_epicla_cases(
    *,
    where: str = _EATON_WHERE,
    url: str = EPICLA_QUERY_URL,
) -> list[EpicCase]:
    """Fetch and validate EPIC-LA cases for the Eaton Fire.

    Records with a null/empty `MAIN_AIN` have no parcel to join to (the join
    drops them regardless), so they're filtered out before validation rather
    than failing the whole run. If *every* record lacks one, that's schema
    drift, not a stray bad row — abort.
    """
    raw = fetch_all(url, {"where": where})
    joinable = [rec for rec in raw if rec.get("MAIN_AIN")]
    dropped = len(raw) - len(joinable)
    if dropped:
        logger.warning("EPIC-LA: dropped %d records with no MAIN_AIN", dropped)
    if raw and not joinable:
        raise SourceError(f"EPIC-LA: all {len(raw)} records have no MAIN_AIN")
    return validate_epicla(joinable)
