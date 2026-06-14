"""Tests for prompt rendering and cache-key derivation."""

from __future__ import annotations

from altadata.processing.llm_prompts import (
    BASE_PROMPT_VERSION,
    PROMPT_VERSION,
    ParcelContext,
    effective_prompt_version,
    parcel_cache_key,
    render_user_prompt,
)
from altadata.sources.schemas import EpicCase


def test_effective_prompt_version_scopes_to_sb1123() -> None:
    assert effective_prompt_version(True) == PROMPT_VERSION
    assert effective_prompt_version(False) == BASE_PROMPT_VERSION


def test_base_version_below_current() -> None:
    # The soft rollout only avoids work while the base lags the current version.
    assert BASE_PROMPT_VERSION < PROMPT_VERSION


def _record(**overrides: object) -> EpicCase:
    base: dict[str, object] = {
        "MAIN_AIN": "1234567890",
        "MODULENAME": "PermitManagement",
        "WORKCLASS_NAME": "New",
        "REBUILD_PROGRESS_NUM": 6,
        "DESCRIPTION": "EATON FIRE REBUILD - NEW 1500 SF SFR",
        "CASENUMBER": "UNC-BLDR250101000001",
        "PROJECT_NAME": "Like-for-Like Rebuild",
        "PROJECT_NUMBER": "PRJ2025-000001",
        "STATUS": "Issued",
        "APPLY_DATE": 1739952000000,  # 2025-02-19
    }
    base.update(overrides)
    return base  # type: ignore[return-value]


def _ctx() -> ParcelContext:
    return ParcelContext(
        ain="1234567890",
        address="123 Main St",
        damage="Destroyed (>50%)",
        pre_fire_summary="1 SFR (1200 SF)",
    )


def test_user_prompt_includes_required_fields() -> None:
    out = render_user_prompt(_ctx(), [_record()])
    assert "AIN: 1234567890" in out
    assert "Address: 123 Main St" in out
    assert "DAMAGE: Destroyed (>50%)" in out
    assert "Pre-fire structures (from DINS): 1 SFR (1200 SF)" in out
    assert "RECORDS (1 qualifying" in out
    assert "CASENUMBER:     UNC-BLDR250101000001" in out
    assert "PROJECT_NAME:   Like-for-Like Rebuild" in out
    assert "PROJECT_NUMBER: PRJ2025-000001" in out
    assert "PROGRESS:       6 (Issued)" in out
    assert "APPLY_DATE:     2025-02-19" in out
    assert "EATON FIRE REBUILD - NEW 1500 SF SFR" in out


def test_user_prompt_handles_null_project_number() -> None:
    rec = _record(PROJECT_NUMBER=None, PROJECT_NAME=None, PROJECTNAME=None)
    out = render_user_prompt(_ctx(), [rec])
    assert "PROJECT_NUMBER: (none)" in out
    assert "PROJECT_NAME:   (none)" in out


def test_user_prompt_orders_records_by_apply_date() -> None:
    early = _record(CASENUMBER="UNC-A", APPLY_DATE=1700000000000)
    late = _record(CASENUMBER="UNC-B", APPLY_DATE=1740000000000)
    out = render_user_prompt(_ctx(), [late, early])
    pos_a = out.index("UNC-A")
    pos_b = out.index("UNC-B")
    assert pos_a < pos_b


def test_cache_key_is_deterministic_and_order_independent() -> None:
    a = _record(CASENUMBER="UNC-A", DESCRIPTION="alpha")
    b = _record(CASENUMBER="UNC-B", DESCRIPTION="beta")
    k1 = parcel_cache_key("X", [a, b], model_id="m")
    k2 = parcel_cache_key("X", [b, a], model_id="m")
    assert k1 == k2


def test_cache_key_changes_on_description_edit() -> None:
    a = _record(CASENUMBER="UNC-A", DESCRIPTION="alpha")
    b_v1 = _record(CASENUMBER="UNC-B", DESCRIPTION="beta")
    b_v2 = _record(CASENUMBER="UNC-B", DESCRIPTION="beta updated")
    k_v1 = parcel_cache_key("X", [a, b_v1], model_id="m")
    k_v2 = parcel_cache_key("X", [a, b_v2], model_id="m")
    assert k_v1 != k_v2


def test_cache_key_ignores_status_and_progress_changes() -> None:
    a = _record(CASENUMBER="UNC-A", STATUS="Issued", REBUILD_PROGRESS_NUM=6)
    b = _record(CASENUMBER="UNC-A", STATUS="Finaled", REBUILD_PROGRESS_NUM=7)
    k1 = parcel_cache_key("X", [a], model_id="m")
    k2 = parcel_cache_key("X", [b], model_id="m")
    assert k1 == k2


def test_cache_key_changes_on_model_swap() -> None:
    rec = _record()
    k1 = parcel_cache_key("X", [rec], model_id="anthropic/claude-sonnet-4-6")
    k2 = parcel_cache_key("X", [rec], model_id="openai/gpt-4o")
    assert k1 != k2


def test_cache_key_changes_on_prompt_version_bump() -> None:
    rec = _record()
    k1 = parcel_cache_key("X", [rec], model_id="m", prompt_version=1)
    k2 = parcel_cache_key("X", [rec], model_id="m", prompt_version=2)
    assert k1 != k2


def test_cache_key_default_uses_module_constant() -> None:
    rec = _record()
    explicit = parcel_cache_key("X", [rec], model_id="m", prompt_version=PROMPT_VERSION)
    default = parcel_cache_key("X", [rec], model_id="m")
    assert explicit == default
