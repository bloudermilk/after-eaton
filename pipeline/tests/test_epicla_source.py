"""Tests for the Eaton-tagged EPIC-LA fetch (sources/epicla.py)."""

from __future__ import annotations

from typing import Any

import pytest

from altadata.sources import epicla
from altadata.sources.arcgis import SourceError


def _case(ain: str | None) -> dict[str, Any]:
    return {
        "MAIN_AIN": ain,
        "MODULENAME": "Building",
        "REBUILD_PROGRESS_NUM": None,
        "DESCRIPTION": None,
    }


def _patch_fetch(
    monkeypatch: pytest.MonkeyPatch, records: list[dict[str, Any]]
) -> None:
    monkeypatch.setattr(epicla, "fetch_all", lambda url, params: records)


def test_drops_records_with_null_or_empty_main_ain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_fetch(monkeypatch, [_case("5829019023"), _case(None), _case("")])
    cases = epicla.fetch_epicla_cases()
    assert [c["MAIN_AIN"] for c in cases] == ["5829019023"]


def test_aborts_when_every_record_lacks_main_ain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_fetch(monkeypatch, [_case(None), _case(None)])
    with pytest.raises(SourceError, match="all 2 records"):
        epicla.fetch_epicla_cases()
