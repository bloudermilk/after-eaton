"""Tests for aggregate_burn_area math."""

from __future__ import annotations

from after_eaton.processing.aggregate import aggregate_burn_area
from after_eaton.processing.normalize import BsdStatus, DamageLevel
from after_eaton.processing.parcel_analysis import ParcelResult


def _make(
    *,
    ain: str = "1",
    damage: DamageLevel = DamageLevel.DESTROYED,
    bsd_status: BsdStatus = BsdStatus.RED,
    rebuild_progress_num: int | None = None,
    lfl_claimed: bool | None = None,
    sfr_size_comparison: str | None = None,
    adds_sb9: bool = False,
    added_adu_count: int = 0,
) -> ParcelResult:
    return ParcelResult(
        ain=ain,
        apn=ain,
        address="",
        damage=damage,
        bsd_status=bsd_status,
        pre_sfr_count=1,
        pre_sfr_sqft=1000,
        pre_adu_count=0,
        pre_adu_sqft=None,
        pre_mfr_count=0,
        pre_mfr_sqft=None,
        post_sfr_count=None,
        post_sfr_sqft=None,
        post_adu_count=None,
        post_adu_sqft=None,
        post_mfr_count=None,
        post_mfr_sqft=None,
        post_sb9_count=None,
        post_sb9_sqft=None,
        lfl_claimed=lfl_claimed,
        lfl_conflict=False,
        sfr_size_comparison=sfr_size_comparison,  # type: ignore[arg-type]
        adds_sb9=adds_sb9,
        added_adu_count=added_adu_count,
        rebuild_progress_num=rebuild_progress_num,
        rebuild_progress=None,
        permit_status=None,
        roe_status=None,
        debris_cleared=None,
        dins_count=1,
    )


def test_basic_counts() -> None:
    parcels = [
        _make(
            ain="1",
            damage=DamageLevel.DESTROYED,
            bsd_status=BsdStatus.RED,
            rebuild_progress_num=7,
            lfl_claimed=True,
            sfr_size_comparison="larger",
        ),
        _make(
            ain="2",
            damage=DamageLevel.DESTROYED,
            bsd_status=BsdStatus.YELLOW,
            rebuild_progress_num=4,
            lfl_claimed=None,
            sfr_size_comparison="smaller",
            adds_sb9=True,
            added_adu_count=2,
        ),
        _make(
            ain="3",
            damage=DamageLevel.MAJOR,
            bsd_status=BsdStatus.YELLOW,
            rebuild_progress_num=None,
        ),
        _make(
            ain="4",
            damage=DamageLevel.NO_DAMAGE,
            bsd_status=BsdStatus.GREEN,
            rebuild_progress_num=None,
        ),
    ]
    s = aggregate_burn_area(parcels, "2026-04-27T00:00:00Z")

    assert s.total_parcels == 4
    assert s.damaged_parcels == 3  # excludes NO_DAMAGE
    assert s.destroyed_parcels == 2
    assert s.bsd_red_count == 1
    assert s.bsd_yellow_count == 2
    assert s.bsd_green_count == 1
    assert s.bsd_red_or_yellow_count == 3
    assert s.no_permit_count == 2
    assert s.permit_in_review_count == 1
    assert s.completed_count == 1
    assert s.lfl_count == 1
    assert s.lfl_unknown_count == 1  # only parcel 2 (has permit, no LFL signal)
    assert s.sfr_larger_count == 1
    assert s.sfr_smaller_count == 1
    assert s.sb9_count == 1
    assert s.added_adu_count == 1
    assert s.generated_at == "2026-04-27T00:00:00Z"
