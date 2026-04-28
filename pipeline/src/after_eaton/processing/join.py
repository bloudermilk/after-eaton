"""Join EPIC-LA cases onto DINS parcels by APN."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

from ..sources.schemas import DinsParcel, EpicCase

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JoinedParcel:
    din: DinsParcel
    cases: list[EpicCase]


def join_cases_to_parcels(
    parcels: list[DinsParcel],
    cases: list[EpicCase],
) -> list[JoinedParcel]:
    """Group cases by MAIN_AIN and left-join to parcels.

    Cases whose MAIN_AIN does not appear in `parcels` are dropped (they fall
    outside the burn area we care about) and reported in aggregate.
    """
    by_ain: dict[str, list[EpicCase]] = defaultdict(list)
    for case in cases:
        by_ain[case["MAIN_AIN"]].append(case)

    parcel_ains = {p["AIN_1"] for p in parcels}
    orphans = [ain for ain in by_ain if ain not in parcel_ains]
    if orphans:
        logger.info(
            "join: %d EPIC-LA AINs had no matching DINS parcel (dropped)",
            len(orphans),
        )

    no_case_count = 0
    joined: list[JoinedParcel] = []
    for parcel in parcels:
        ain = parcel["AIN_1"]
        cases_for = by_ain.get(ain, [])
        if not cases_for:
            no_case_count += 1
        joined.append(JoinedParcel(din=parcel, cases=cases_for))

    logger.info(
        "join: %d parcels (%d with at least one EPIC case)",
        len(joined),
        len(joined) - no_case_count,
    )
    return joined
