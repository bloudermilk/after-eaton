"""Tests for SB-9 vs SB-1123 pathway resolution across multiple cases.

SB-9 and SB-1123 are mutually exclusive in practice — a parcel uses one or
the other. The resolver walks cases by descending APPLY_DATE; the most
recent case to mention either bill wins. `sb_pathway_conflict` is True iff
the union of mentions across cases includes both bills.
"""

from __future__ import annotations

from typing import Any

from altadata.processing.join import JoinedParcel
from altadata.processing.parcel_analysis import analyze_parcel

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
        "PROJECTNAME": None,
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


def test_no_mentions_returns_all_false() -> None:
    cases = [_case(DESCRIPTION="EATON FIRE REBUILD - NEW 1500 SF SFR")]
    res = analyze_parcel(JoinedParcel(din=_din(), cases=cases))
    assert res.adds_sb9 is False
    assert res.adds_sb1123 is False
    assert res.sb_pathway_conflict is False


def test_only_sb9_mention() -> None:
    cases = [_case(DESCRIPTION="EATON FIRE REBUILD - NEW 1107 SF SB9 unit")]
    res = analyze_parcel(JoinedParcel(din=_din(), cases=cases))
    assert res.adds_sb9 is True
    assert res.adds_sb1123 is False
    assert res.sb_pathway_conflict is False


def test_only_sb1123_mention() -> None:
    cases = [_case(DESCRIPTION="EATON FIRE REBUILD - NEW 1107 SF SB1123 unit")]
    res = analyze_parcel(JoinedParcel(din=_din(), cases=cases))
    assert res.adds_sb9 is False
    assert res.adds_sb1123 is True
    assert res.sb_pathway_conflict is False


def test_sb1123_wins_when_more_recent() -> None:
    cases = [
        _case(
            APPLY_DATE=T_OLDER,
            DESCRIPTION="EATON FIRE REBUILD - NEW 1107 SF SB9 unit",
        ),
        _case(
            APPLY_DATE=T_NEWER,
            DESCRIPTION="EATON FIRE REBUILD - NEW 1107 SF SB1123 unit",
        ),
    ]
    res = analyze_parcel(JoinedParcel(din=_din(), cases=cases))
    assert res.adds_sb9 is False
    assert res.adds_sb1123 is True
    assert res.sb_pathway_conflict is True


def test_sb9_wins_when_more_recent() -> None:
    cases = [
        _case(
            APPLY_DATE=T_OLDER,
            DESCRIPTION="EATON FIRE REBUILD - NEW 1107 SF SB1123 unit",
        ),
        _case(
            APPLY_DATE=T_NEWER,
            DESCRIPTION="EATON FIRE REBUILD - NEW 1107 SF SB9 unit",
        ),
    ]
    res = analyze_parcel(JoinedParcel(din=_din(), cases=cases))
    assert res.adds_sb9 is True
    assert res.adds_sb1123 is False
    assert res.sb_pathway_conflict is True


def test_single_case_mentions_both_later_position_wins() -> None:
    cases = [
        _case(
            DESCRIPTION="EATON FIRE - filed under SB-9; supersedes SB-1123 prior intent"
        )
    ]
    res = analyze_parcel(JoinedParcel(din=_din(), cases=cases))
    # SB-1123 appears later in the DESCRIPTION than SB-9.
    assert res.adds_sb9 is False
    assert res.adds_sb1123 is True
    assert res.sb_pathway_conflict is True


def test_project_name_mention_picked_up() -> None:
    cases = [
        _case(
            PROJECT_NAME="SB-1123 Small-Lot Subdivision @ 1 Foo St",
            DESCRIPTION="EATON FIRE REBUILD - NEW 1107 SF",
        )
    ]
    res = analyze_parcel(JoinedParcel(din=_din(), cases=cases))
    assert res.adds_sb9 is False
    assert res.adds_sb1123 is True
    assert res.sb_pathway_conflict is False


def test_missing_apply_date_still_resolves() -> None:
    cases = [_case(APPLY_DATE=None, DESCRIPTION="NEW 1107 SF SB9 unit")]
    res = analyze_parcel(JoinedParcel(din=_din(), cases=cases))
    assert res.adds_sb9 is True
    assert res.adds_sb1123 is False
    assert res.sb_pathway_conflict is False
