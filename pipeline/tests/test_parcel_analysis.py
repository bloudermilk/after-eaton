"""Regression tests for analyze_parcel() against hand-verified QA fixtures."""

from __future__ import annotations

from typing import Any

from after_eaton.processing.join import JoinedParcel
from after_eaton.processing.parcel_analysis import analyze_parcel


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
    assert result.added_adu_count == expected["added_adu_count"]
    assert result.rebuild_progress_num == expected["rebuild_progress_num"]
    assert result.lfl_claimed == expected["lfl_claimed"]
    assert result.sfr_size_comparison == expected["sfr_size_comparison"]
