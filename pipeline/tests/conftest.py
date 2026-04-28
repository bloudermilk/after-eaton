"""Shared pytest fixtures: QA fixture loader."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

QA_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "qa"


def _load_qa_fixtures() -> list[dict[str, Any]]:
    fixtures: list[dict[str, Any]] = []
    for path in sorted(QA_FIXTURE_DIR.glob("*.json")):
        with path.open() as fh:
            fixtures.append(json.load(fh))
    return fixtures


@pytest.fixture(params=_load_qa_fixtures(), ids=lambda f: f["ain"])
def qa_fixture(request: pytest.FixtureRequest) -> dict[str, Any]:
    return request.param  # type: ignore[no-any-return]
