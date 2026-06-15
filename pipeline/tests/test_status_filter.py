"""The case-status filter as observed through analyze_parcel.

Terminal-negative cases must not contribute to any ParcelResult field; pending /
approved / completed cases must still count. The filter lives in normalize.py and
is applied both globally (cli.py) and defensively inside analyze_parcel.
"""

from __future__ import annotations

from typing import Any

from altadata.processing.join import JoinedParcel
from altadata.processing.parcel_analysis import analyze_parcel
from altadata.sources.schemas import CASE_HISTORY_SOURCE, DinsParcel, EpicCase


def _din(**overrides: Any) -> DinsParcel:
    base: dict[str, Any] = {
        "AIN_1": "5840000000",
        "APN_1": "5840-000-000",
        "SitusFullAddress": "1 TEST ST ALTADENA CA 91001",
        "DAMAGE_1": "Destroyed (>50%)",
        "BSD_Tag": "Red",
        "UseDescription": "Single",
        "DesignType1": "0130",
        "SQFTmain1": 1000,
        "DINS_Count": 1,
    }
    base.update(overrides)
    return base  # type: ignore[return-value]


def _permit(**overrides: Any) -> EpicCase:
    base: dict[str, Any] = {
        "MAIN_AIN": "5840000000",
        "MODULENAME": "PermitManagement",
        "WORKCLASS_NAME": "New",
        "DISASTER_TYPE": "Eaton Fire (01-2025)",
        "DESCRIPTION": "EATON FIRE REBUILD - NEW 2-STORY 1500 SF SFR (3 BEDROOMS)",
        "STATUS": "Issued",
        "REBUILD_PROGRESS_NUM": 5,
        "BUILD_PERMIT_ISSUED": "Building Permits Issued",
        "APPLY_DATE": 1757923200000,
    }
    base.update(overrides)
    return base  # type: ignore[return-value]


def _sb1123_plan(**overrides: Any) -> EpicCase:
    base: dict[str, Any] = {
        "MAIN_AIN": "5840000000",
        "MODULENAME": "PlanManagement",
        "WORKCLASS_NAME": "Subdivisions",
        "DESCRIPTION": "SB 1123 SUBDIVISION - (8) FEE-SIMPLE SINGLE FAMILY LOTS",
        "DISASTER_TYPE": None,
        "_source": CASE_HISTORY_SOURCE,
        "STATUS": "Accepted",
        "REBUILD_PROGRESS_NUM": None,
        "APPLY_DATE": 1739952000000,
    }
    base.update(overrides)
    return base  # type: ignore[return-value]


def test_voided_sb1123_not_counted() -> None:
    joined = JoinedParcel(din=_din(), cases=[_sb1123_plan(STATUS="Void")])
    assert analyze_parcel(joined).adds_sb1123 is False


def test_active_sb1123_counted() -> None:
    joined = JoinedParcel(din=_din(), cases=[_sb1123_plan(STATUS="Accepted")])
    assert analyze_parcel(joined).adds_sb1123 is True


def test_voided_permit_ignored_live_permit_wins() -> None:
    # The voided permit looks "further along" (stage 7) but must be ignored; the
    # live permit (stage 5) determines progress.
    void = _permit(
        STATUS="Void",
        REBUILD_PROGRESS_NUM=7,
        BUILD_PERMIT_ISSUED=None,
        CONS_COMPLETED="Construction Completed",
    )
    live = _permit(STATUS="Issued", REBUILD_PROGRESS_NUM=5)
    result = analyze_parcel(JoinedParcel(din=_din(), cases=[void, live]))
    assert result.rebuild_progress_num == 5
    assert result.rebuild_stage == 5
    assert result.rebuild_construction_completed_cases == 0


def test_all_voided_parcel_reverts_to_no_activity() -> None:
    cases = [_permit(STATUS="Void"), _sb1123_plan(STATUS="Void")]
    result = analyze_parcel(JoinedParcel(din=_din(), cases=cases))
    assert result.rebuild_stage == 0
    assert result.rebuild_progress_num is None
    assert result.post_sfr_sqft is None
    assert result.post_sfr_count is None
    assert result.adds_sb1123 is False


def test_pending_status_kept() -> None:
    permit = _permit(
        STATUS="In Review",
        REBUILD_PROGRESS_NUM=2,
        BUILD_PERMIT_ISSUED=None,
        ZONING_REV_CLEARED="Zoning Reviews Cleared",
    )
    result = analyze_parcel(JoinedParcel(din=_din(), cases=[permit]))
    assert result.rebuild_progress_num == 2
    assert result.rebuild_stage == 2


def test_null_status_kept() -> None:
    result = analyze_parcel(JoinedParcel(din=_din(), cases=[_permit(STATUS=None)]))
    assert result.rebuild_progress_num == 5


def test_finaled_completed_kept() -> None:
    permit = _permit(
        STATUS="Finaled",
        REBUILD_PROGRESS_NUM=7,
        CONS_COMPLETED="Construction Completed",
    )
    result = analyze_parcel(JoinedParcel(din=_din(), cases=[permit]))
    assert result.rebuild_progress_num == 7
    assert result.rebuild_stage == 7
