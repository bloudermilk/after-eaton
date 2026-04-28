"""Tests for LFL/Custom resolution across multiple sources.

Resolution rule: walk cases from most-recent (highest APPLY_DATE) to oldest;
for each case try DESCRIPTION first, then PROJECT_NAME; first non-None hit
wins. None means we couldn't determine the claim. `lfl_conflict` is True
when cases yield ≥2 distinct non-None signals.
"""

from __future__ import annotations

from typing import Any

from after_eaton.processing.join import JoinedParcel
from after_eaton.processing.parcel_analysis import analyze_parcel

# Epoch-ms timestamps used to control case ordering in tests.
T_OLDER = 1_700_000_000_000
T_NEWER = 1_750_000_000_000


def _case(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "MAIN_AIN": "1234567890",
        "MODULENAME": "PermitManagement",
        "DISASTER_TYPE": "Eaton Fire (01-2025)",
        "WORKCLASS_NAME": "New",
        "REBUILD_PROGRESS_NUM": 4,
        "APPLY_DATE": T_NEWER,
        "PROJECT_NAME": None,
        "DESCRIPTION": None,
    }
    base.update(overrides)
    return base


def _din() -> dict[str, Any]:
    return {
        "AIN_1": "1234567890",
        "DAMAGE_1": "Destroyed (>50%)",
        "DesignType1": "0130",
        "SQFTmain1": 1500,
        "COMMUNITY": "Altadena",
        "UseDescription": "Single",
    }


def test_description_beats_project_name_within_one_case() -> None:
    cases = [
        _case(
            PROJECT_NAME="Non-Like-for-Like Rebuild @ 1 Foo St",
            DESCRIPTION="EATON FIRE LIKE-FOR-LIKE REBUILD - NEW 1500 SF SFR",
        )
    ]
    res = analyze_parcel(JoinedParcel(din=_din(), cases=cases))
    # DESCRIPTION wins over PROJECT_NAME within the same case
    assert res.lfl_claimed is True
    assert res.lfl_conflict is True


def test_falls_through_to_project_name_when_description_silent() -> None:
    cases = [
        _case(
            PROJECT_NAME="Like-for-Like SFR Rebuild @ 1 Foo St",
            DESCRIPTION="EATON FIRE REBUILD - NEW 1500 SF SFR",
        )
    ]
    res = analyze_parcel(JoinedParcel(din=_din(), cases=cases))
    assert res.lfl_claimed is True
    assert res.lfl_conflict is False


def test_most_recent_case_wins_over_older() -> None:
    cases = [
        _case(  # older
            APPLY_DATE=T_OLDER,
            MODULENAME="PlanManagement",
            DESCRIPTION="EATON FIRE NON-LIKE-FOR-LIKE REBUILD",
        ),
        _case(  # newer
            APPLY_DATE=T_NEWER,
            DESCRIPTION="EATON FIRE LIKE-FOR-LIKE REBUILD - NEW 1500 SF SFR",
        ),
    ]
    res = analyze_parcel(JoinedParcel(din=_din(), cases=cases))
    assert res.lfl_claimed is True  # newer case's DESCRIPTION wins
    assert res.lfl_conflict is True


def test_falls_through_to_older_case_when_newer_is_silent() -> None:
    cases = [
        _case(  # newer but silent
            APPLY_DATE=T_NEWER,
            PROJECT_NAME="Eaton Rebuild @ 1 Foo St",
            DESCRIPTION="EATON FIRE REBUILD - NEW 1500 SF SFR",
        ),
        _case(  # older but informative
            APPLY_DATE=T_OLDER,
            MODULENAME="PlanManagement",
            DESCRIPTION="EATON FIRE NON-LIKE-FOR-LIKE REBUILD",
        ),
    ]
    res = analyze_parcel(JoinedParcel(din=_din(), cases=cases))
    assert res.lfl_claimed is False
    assert res.lfl_conflict is False


def test_no_signals_anywhere_returns_none() -> None:
    cases = [
        _case(
            PROJECT_NAME="Eaton Rebuild @ 1 Foo St",
            DESCRIPTION="EATON FIRE REBUILD - NEW 1500 SF SFR",
        )
    ]
    res = analyze_parcel(JoinedParcel(din=_din(), cases=cases))
    assert res.lfl_claimed is None
    assert res.lfl_conflict is False


def test_missing_apply_date_sorts_last() -> None:
    cases = [
        _case(  # has date, has signal
            APPLY_DATE=T_NEWER,
            DESCRIPTION="EATON FIRE LIKE-FOR-LIKE REBUILD - NEW 1500 SF SFR",
        ),
        _case(  # no date — sorts last
            APPLY_DATE=None,
            DESCRIPTION="EATON FIRE NON-LIKE-FOR-LIKE REBUILD",
        ),
    ]
    res = analyze_parcel(JoinedParcel(din=_din(), cases=cases))
    assert res.lfl_claimed is True
    assert res.lfl_conflict is True
