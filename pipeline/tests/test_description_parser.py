"""Unit tests for the EPIC-LA DESCRIPTION free-text parser."""

from __future__ import annotations

from after_eaton.processing.description_parser import (
    extract_lfl_claim,
    mentions_sb9,
    parse_description,
)


def test_single_sfr_with_comma_sqft() -> None:
    desc = (
        "EATON FIRE REBUILD - NEW 1-STORY 3,218 S.F. SINGLE FAMILY RESIDENCE "
        "WITH 102 S.F. NEW ATTACHED ENTRY PORCH"
    )
    result = parse_description(desc)
    assert len(result) == 1
    assert result[0].struct_type == "sfr"
    assert result[0].sqft == 3218.0


def test_single_sfd_short_form() -> None:
    desc = "EATON FIRE REBUILD - (N) 2,140 SF SFD (4 BED, 3 BATH)"
    result = parse_description(desc)
    assert len(result) == 1
    assert result[0].struct_type == "sfr"
    assert result[0].sqft == 2140.0


def test_numbered_multi_structure() -> None:
    desc = (
        "1. EATON FIRE REBUILD - NEW 2-STORY 1107 SF SB9 (2 BEDROOMS AND 2 BATHROOMS)"
        " WITH 464 SF ATTACHED GARAGE WITH 651 SF STORAGE\n"
        "2. EATON FIRE REBUILD - NEW 2-STORY 1115 SF SFR (2 BEDROOMS AND 2 BATHROOMS)"
        " WITH 50 SF PORCH\n"
        "3. EATON FIRE REBUILD - NEW 2-STORY 1110 SF ADU \n"
        "4. EATON FIRE REBUILD - NEW 2-STORY 1110 SF ADU "
    )
    result = parse_description(desc)
    assert len(result) == 4
    types = [r.struct_type for r in result]
    sqfts = [r.sqft for r in result]
    # Item 1: bare "SB9" with no other type keyword falls back to sfr.
    # Items 2-4: positive type matches.
    assert types == ["sfr", "sfr", "adu", "adu"]
    assert sqfts == [1107.0, 1115.0, 1110.0, 1110.0]


def test_lfl_plan_description() -> None:
    desc = "(EATON FIRE LIKE FOR LIKE) New single family home, 2,135 SF. drpdrt"
    result = parse_description(desc)
    assert len(result) == 1
    assert result[0].struct_type == "sfr"
    assert result[0].sqft == 2135.0


def test_empty_or_none() -> None:
    assert parse_description(None) == []
    assert parse_description("") == []


def test_no_sqft_falls_back_to_unknown() -> None:
    result = parse_description("EATON FIRE REBUILD - rebuild project")
    assert len(result) == 1
    assert result[0].sqft is None
    # No structure keyword either
    assert result[0].struct_type == "unknown"


def test_lfl_claim_variants() -> None:
    assert extract_lfl_claim("Like-for-Like SFR Rebuild @ 3458 Monterosa Dr") is True
    assert extract_lfl_claim("like for like sfr rebuild") is True
    assert (
        extract_lfl_claim("Non-Like-for-Like SFR Rebuild @ 2915 N Fair Oaks Ave")
        is False
    )
    assert extract_lfl_claim("Eaton Rebuild @ 411 Punahou St") is None
    assert extract_lfl_claim("") is None
    assert extract_lfl_claim(None) is None


def test_jadu_classification() -> None:
    desc = "1. NEW 800 SF SFR\n2. NEW 500 SF JADU"
    result = parse_description(desc)
    assert [r.struct_type for r in result] == ["sfr", "jadu"]


def test_duplex_classified_as_mfr() -> None:
    desc = "NEW 2,400 SF DUPLEX"
    result = parse_description(desc)
    assert result[0].struct_type == "mfr"
    assert result[0].sqft == 2400.0


def test_sqft_unit_can_run_into_structure_token() -> None:
    """The unit and the structure type can share characters: "1,705 SFR"."""
    result = parse_description(
        "EATON FIRE REBUILD. NEW 1-STORY 1,705 SFR (3 BED, 2 BATH)"
    )
    assert result[0].struct_type == "sfr"
    assert result[0].sqft == 1705.0


def test_sqft_at_segment_end_with_no_trailing_whitespace() -> None:
    # Segment splitter strips trailing whitespace — sqft must still match at EOL
    desc = (
        "1. EATON CANYON NON LIKE FOR LIKE REBUILD - 1 STORY SFD 1412 SF\n"
        "2. NEW - 1 STORY ADU 735 SF"
    )
    result = parse_description(desc)
    assert [(s.struct_type, s.sqft) for s in result] == [
        ("sfr", 1412.0),
        ("adu", 735.0),
    ]


def test_residential_beats_garage_when_clause_order_inverts() -> None:
    # Description starts with a 'WITH 524 SF ATTACHED GARAGE' clause; the
    # primary structure (the SFR) appears later. Residential should still win.
    desc = (
        "WITH 524 SF ATTACHED GARAGE WITH 270 SF REAR PATIO WITH "
        "(EATON FIRE LIKE FOR LIKE) NEW 2-STORY 3,484 SF SINGLE FAMILY "
        "RESIDENCE (4 BEDROOMS AND 4.5 BATHROOM)"
    )
    result = parse_description(desc)
    assert len(result) == 1
    assert result[0].struct_type == "sfr"
    assert result[0].sqft == 3484.0


def test_sb9_does_not_capture_9_as_sqft() -> None:
    """Bare "SB9 SFR" must not yield 9 sqft — there's no word boundary before the 9."""
    desc = "EATON FIRE REBUILD 1-STORY 710 S.F. SB9 SFR (2 BEDROOMS AND 1 BATHROOM)"
    result = parse_description(desc)
    # Positive SFR match wins over the SB-9 fallback.
    assert result[0].struct_type == "sfr"
    assert result[0].sqft == 710.0


def test_bare_sb9_falls_back_to_sfr() -> None:
    """A segment mentioning SB-9 with no other type keyword classifies as SFR."""
    desc = (
        "EATON FIRE REBUILD - NEW 2-STORY 1107 SF SB9 (2 BEDROOMS AND 2 BATHROOMS) "
        "WITH 464 SF ATTACHED GARAGE WITH 651 SF STORAGE"
    )
    result = parse_description(desc)
    assert len(result) == 1
    assert result[0].struct_type == "sfr"
    assert result[0].sqft == 1107.0


def test_sb9_adu_classifies_as_adu() -> None:
    """A SB-9 ADU is still an ADU — positive ADU match beats the SB-9 fallback."""
    desc = "EATON FIRE REBUILD - NEW 800 SF SB9 ADU (1 BED, 1 BATH)"
    result = parse_description(desc)
    assert result[0].struct_type == "adu"


def test_sb9_variants_via_mentions_sb9() -> None:
    assert mentions_sb9("NEW 1107 SF SB9 unit") is True
    assert mentions_sb9("project filed under SB-9") is True
    assert mentions_sb9("SB 9 lot split") is True
    assert mentions_sb9("Senate Bill 9 entitlement") is True
    assert mentions_sb9("standard SFR rebuild") is False
    assert mentions_sb9(None) is False
    assert mentions_sb9("") is False


def test_temporary_housing_classification() -> None:
    for desc in [
        "EATON FIRE TEMPORARY HOUSING",
        "Eaton Fire Temporary housing (RV)",
        "(EATON FIRE Temp. Housing)",
        "Placement of motor home on Altadena Property",
    ]:
        result = parse_description(desc)
        assert len(result) == 1
        assert result[0].struct_type == "temporary_housing", desc


def test_repair_classification() -> None:
    for desc in [
        "EATON FIRE REPAIR AND ALTERATION - REPLACE ELECTRICAL FIRE / "
        "WATER DAMAGED INTERIOR PLYWOOD",
        "Kitchen and Bathroom Remodel - No Change of Layout",
        "VOLUNTARY SEISMIC RETROFIT PER LA CITY STD PLAN #1.",
    ]:
        result = parse_description(desc)
        assert len(result) == 1
        assert result[0].struct_type in ("repair", "seismic"), desc


def test_residential_beats_repair() -> None:
    """A repair-keyword permit that names an SFR with sqft is still an SFR rebuild."""
    desc = "EATON FIRE DAMAGED REPAIR EXISTING SFR 746 SF"
    result = parse_description(desc)
    assert result[0].struct_type == "sfr"
    assert result[0].sqft == 746.0


def test_retaining_wall_classification() -> None:
    desc = (
        "EATON FIRE REBUILD - NEW 37'-8\" PROPERTY RETAINING WALL "
        "WITH MAXIMUM RETAINED HEIGHT OF 5'."
    )
    result = parse_description(desc)
    assert result[0].struct_type == "retaining_wall"


def test_spelled_out_square_foot_unit() -> None:
    # Real EPIC-LA case: "1,680-square-foot single-family residence"
    desc = (
        "Construction of a 1,680-square-foot single-family residence with "
        "covered 90 sf front porch and attached 539-square-foot garage"
    )
    result = parse_description(desc)
    assert len(result) == 1
    assert result[0].struct_type == "sfr"
    assert result[0].sqft == 1680.0


def test_spelled_out_square_foot_variants() -> None:
    cases = [
        ("NEW 1,200 SQUARE FOOT SFR", 1200.0),
        ("NEW 950-square-foot ADU", 950.0),
        ("NEW 2,400 sq ft single family residence", 2400.0),
        ("NEW 850 sq. ft. ADU", 850.0),
        ("3,218 SQFT SFR", 3218.0),
        ("EATON REBUILD - 1,500 square feet single-family residence", 1500.0),
    ]
    for desc, expected_sqft in cases:
        result = parse_description(desc)
        assert result[0].sqft == expected_sqft, f"{desc!r} -> {result[0]}"
