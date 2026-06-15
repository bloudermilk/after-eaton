"""Regression tests for analyze_parcel() against hand-verified QA fixtures."""

from __future__ import annotations

from typing import Any

from altadata.processing.join import JoinedParcel
from altadata.processing.parcel_analysis import analyze_parcel


def _to_joined(fixture: dict[str, Any]) -> JoinedParcel:
    return JoinedParcel(din=fixture["dins"], cases=list(fixture["epic_cases"]))


def test_qa_parcel_matches_expected(qa_fixture: dict[str, Any]) -> None:
    joined = _to_joined(qa_fixture)
    result = analyze_parcel(joined)
    expected = qa_fixture["expected"]

    assert result.ain == qa_fixture["ain"]
    assert result.pre_sfr_sqft == expected["pre_sfr_sqft"]
    assert result.post_sfr_sqft == expected["post_sfr_sqft"]
    assert result.adds_sb9 is expected["adds_sb9"]
    assert result.adds_sb1123 is expected["adds_sb1123"]
    assert result.sb_pathway_conflict is expected["sb_pathway_conflict"]
    assert result.added_adu_count == expected["added_adu_count"]
    assert result.rebuild_progress_num == expected["rebuild_progress_num"]
    assert result.lfl_claimed == expected["lfl_claimed"]
    assert result.sfr_size_comparison == expected["sfr_size_comparison"]

    # Independent rebuild-progress milestones (optional per fixture). The case
    # counts are checked as a whole dict so a missing or extra milestone fails.
    milestones = expected.get("rebuild_milestone_cases")
    if milestones is not None:
        assert {
            "app_received": result.rebuild_app_received_cases,
            "zoning_cleared": result.rebuild_zoning_cleared_cases,
            "plans_received": result.rebuild_plans_received_cases,
            "plans_approved": result.rebuild_plans_approved_cases,
            "permit_issued": result.rebuild_permit_issued_cases,
            "in_construction": result.rebuild_in_construction_cases,
            "construction_completed": result.rebuild_construction_completed_cases,
        } == milestones
    if "rebuild_stage" in expected:
        assert result.rebuild_stage == expected["rebuild_stage"]
    if "rebuild_new_stage" in expected:
        assert result.rebuild_new_stage == expected["rebuild_new_stage"]
