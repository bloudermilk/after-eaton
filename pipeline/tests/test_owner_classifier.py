"""Unit tests for the RentCast owner-name classifier.

Edge cases are pulled from the real post-fire sales cache: the classifier was
validated to reproduce the hand-checked labels with zero company-boundary
mismatches (individual 182 / trust 46 / company 195 / 12 null).
"""

from __future__ import annotations

from altadata.processing.owner_classifier import classify_owner


def test_no_name_is_none() -> None:
    # No owner name → None (not "unknown"), mirroring the other nullable fields.
    assert classify_owner(None) is None
    assert classify_owner("") is None
    assert classify_owner("   ") is None


def test_company_variants() -> None:
    for name in [
        "SOCAL FLIPPERS INC",
        "OCEAN DEVELOPMENT INC",
        "AD BUILD 1 LLC",
        "149 MARATHON RD LLC",  # single-purpose shell LLC
        "ERB HOLDING LLC",
        "BLACK LION PROPERTIES LLC",
        "NP ALTADENA 2 LLC",
        "SHENG FENG GLOBAL",
        "SUNRISE CAPITAL PARTNERS",
        "ACME CONSTRUCTION",
        "PACIFIC HOMES GROUP",
        "MARENGO REAL ESTATE",
    ]:
        assert classify_owner(name) == "company", name


def test_trust_variants() -> None:
    for name in [
        "THE GINA ROSSETTI LIVING TRUST",
        "SERRA ANTHONY J SERRA FAMILY TRUST",
        "DOLORES DRIVE TRUST",  # street-named title trust, no person; still a trust
        "SMITH REVOCABLE TRUST",
        "JONES SURVIVORS TRUST",
        # RentCast truncates long names — partial tokens must still read as trust.
        "HINKEL FAMILY REVOCABLE WEALTH TRUS",
        "Kurt A And Karen D Franklin Living",
    ]:
        assert classify_owner(name) == "trust", name


def test_individual_variants() -> None:
    for name in [
        "Daniel James Vickerstaffe & Wendy Susana Cortez",
        "LOPEZ REYNALDO E & MARTHA S E",
        "JANE DOE",
        "PETER TRAN",  # "TR" inside TRAN must NOT trigger the trust rule
    ]:
        assert classify_owner(name) == "individual", name


def test_company_beats_trust_precedence() -> None:
    # A business carrying a family/trust word is still a company (checked first).
    assert classify_owner("IRON FAMILY INVESTMENTS LLC") == "company"
    assert classify_owner("FAMILY LEGACY HOLDINGS") == "company"


def test_classification_is_case_insensitive() -> None:
    assert classify_owner("socal flippers inc") == "company"
    assert classify_owner("the gina rossetti living trust") == "trust"
    assert classify_owner("jane doe") == "individual"
