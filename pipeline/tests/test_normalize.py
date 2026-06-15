"""Unit tests for the EPIC-LA case-status taxonomy in processing/normalize.py."""

from __future__ import annotations

from typing import Any

import pytest

from altadata.processing.normalize import (
    filter_active_cases,
    is_active_status,
    is_recognized_status,
)
from altadata.sources.schemas import EpicCase


def _case(status: Any) -> EpicCase:
    base: dict[str, Any] = {
        "MAIN_AIN": "1",
        "MODULENAME": "PlanManagement",
        "STATUS": status,
    }
    return base  # type: ignore[return-value]


@pytest.mark.parametrize(
    "status",
    [
        None,
        "",
        "Issued",
        "  Issued  ",
        "In Review",
        "Hold",
        "New - Online",
        "Recorded",
        # Unknown compound status: counted (exact-match denylist), but flagged
        # unrecognized by is_recognized_status (see below).
        "Cancelled - Duplicate",
    ],
)
def test_is_active_true_unless_explicitly_inactive(status: str | None) -> None:
    assert is_active_status(status) is True


@pytest.mark.parametrize(
    "status",
    [
        "Void",
        "voided",
        "  VOIDED ",
        "Cancelled",
        "canceled",
        "Withdrawn",
        "WITHDRAWN",
        "Revoked",
        "Denied",
        "Rejected",
        "Expired",
    ],
)
def test_is_active_false_for_terminal_negative(status: str) -> None:
    assert is_active_status(status) is False


@pytest.mark.parametrize("status", [None, "", "Issued", "Void", "withdrawn"])
def test_is_recognized_true_for_known_or_null(status: str | None) -> None:
    assert is_recognized_status(status) is True


@pytest.mark.parametrize(
    "status", ["Cancelled - Duplicate", "Some New County Status", "Pending Foo"]
)
def test_is_recognized_false_for_unknown(status: str) -> None:
    assert is_recognized_status(status) is False


def test_filter_active_cases_drops_inactive_keeps_rest() -> None:
    live = _case("Issued")
    pending = _case(None)
    void = _case("Void")
    withdrawn = _case("Withdrawn")
    assert filter_active_cases([live, pending, void, withdrawn]) == [live, pending]


def test_filter_active_cases_empty() -> None:
    assert filter_active_cases([]) == []


def test_filter_active_cases_all_inactive() -> None:
    assert filter_active_cases([_case("Void"), _case("Expired")]) == []
