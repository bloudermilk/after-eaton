"""Tests for the EPIC-LA Case History SB-1123 supplement and its filters."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from altadata.processing.parcel_analysis import (
    filter_fire_cases,
    select_qualifying_records,
)
from altadata.sources.epicla_case_history import fetch_case_history_sb1123
from altadata.sources.schemas import CASE_HISTORY_SOURCE, EpicCase


def _raw(ain: str, desc: str = "Subdivide vacant lot under SB1123") -> dict[str, Any]:
    return {
        "MAIN_AIN": ain,
        "MODULENAME": "PlanManagement",
        "WORKCLASS_NAME": "Subdivisions",
        "DESCRIPTION": desc,
        "CASENUMBER": f"CREB-{ain}",
        "APPLY_DATE": 1739952000000,
        "_geometry": {"x": -118.1, "y": 34.2},
    }


def test_fetch_case_history_adapts_and_bounds_query() -> None:
    raw = [_raw("5829019023"), _raw("", desc="no joinable ain")]
    captured: dict[str, Any] = {}

    def fake_fetch_all(url: str, params: dict[str, str]) -> list[dict[str, Any]]:
        captured["url"] = url
        captured["params"] = params
        return raw

    with patch("altadata.sources.epicla_case_history.fetch_all", fake_fetch_all):
        out = fetch_case_history_sb1123((-118.2, 34.1, -118.0, 34.3))

    # Null-AIN record dropped; the rest adapted to the EpicCase contract.
    assert len(out) == 1
    rec = out[0]
    assert rec["MAIN_AIN"] == "5829019023"
    assert rec["REBUILD_PROGRESS_NUM"] is None  # backfilled
    assert rec["_source"] == CASE_HISTORY_SOURCE

    # Query is bounded: spatial envelope + post-fire date + SB-1123 text.
    params = captured["params"]
    assert params["geometryType"] == "esriGeometryEnvelope"
    assert params["geometry"] == "-118.2,34.1,-118.0,34.3"
    assert params["inSR"] == "4326"
    assert "APPLY_DATE >= DATE" in params["where"]
    assert "1123" in params["where"]


def _case(**overrides: Any) -> EpicCase:
    base: dict[str, Any] = {
        "MAIN_AIN": "1",
        "MODULENAME": "PlanManagement",
        "WORKCLASS_NAME": "Subdivisions",
        "REBUILD_PROGRESS_NUM": None,
        "DESCRIPTION": "Subdivide vacant lot under SB1123",
        "DISASTER_TYPE": None,
    }
    base.update(overrides)
    return base  # type: ignore[return-value]


def test_filter_fire_cases_includes_case_history_marker() -> None:
    # Null disaster type and no "eaton fire" text, but the supplement marker
    # makes it fire-related.
    marked = _case(_source=CASE_HISTORY_SOURCE)
    assert filter_fire_cases([marked]) == [marked]


def test_filter_fire_cases_excludes_unmarked_non_eaton() -> None:
    unmarked = _case(DESCRIPTION="ordinary subdivision")
    assert filter_fire_cases([unmarked]) == []


def test_select_qualifying_includes_sb1123_plan_cases() -> None:
    sb1123 = _case(DESCRIPTION="SB 1123 SUBDIVISION, (10) FEE-SIMPLE LOTS")
    rebuild = _case(WORKCLASS_NAME="Rebuild", DESCRIPTION="rebuild SFR")
    plain = _case(DESCRIPTION="ordinary subdivision, no state bill")

    out = select_qualifying_records([sb1123, rebuild, plain])
    assert sb1123 in out
    assert rebuild in out
    assert plain not in out  # PlanManagement, not Rebuild, no SB-1123
