"""Classify a RentCast post-fire owner name as individual, trust, or company."""

from __future__ import annotations

import re
from typing import Literal

OwnerClass = Literal["individual", "trust", "company"]

# A legal suffix or business-activity keyword, matched as a whole uppercase token
# (the lookarounds stop us firing on a keyword embedded in a longer word). This
# is checked FIRST so a company that also carries a family/trust word — e.g.
# "IRON FAMILY INVESTMENTS LLC" — still classifies as a company, not a trust.
_COMPANY_RE = re.compile(
    r"(?<![A-Z])(?:"
    r"LLC|L\.L\.C|INC|INCORPORATED|CORP|CORPORATION|LP|L\.P|LLP|LTD|LIMITED|"
    r"COMPANY|FOUNDATION|HOLDINGS?|INVESTMENTS?|CAPITAL|DEVELOPMENT|PROPERTIES|"
    r"PROPERTY|REALTY|VENTURES?|PARTNERS|GROUP|BUILDERS?|CONSTRUCTION|HOMES|"
    r"EQUITY|ENTERPRISES?|MANAGEMENT|REDEVELOPMENT|REAL ESTATE|DYNAMICS|"
    r"SOLUTIONS|TRADING|PROCESSING|LEASING|GLOBAL|SYNERGY"
    r")(?![A-Z])"
)

# A trust / estate-planning vehicle. Truncation-tolerant: RentCast clips long
# owner names (e.g. "…FAMILY TRU", "…LIVING F"), so partial tokens such as TRUS /
# TR / RLT are matched on purpose. Reached only after the company check, so at
# worst it relabels an individual as a trust — both group together as "not a
# company" for the who's-buying split, making that boundary harmless.
_TRUST_RE = re.compile(
    r"(?<![A-Z])(?:"
    r"TRUST|TRUS|REVOCABLE|IRREVOCABLE|LIVING|FAMILY|SURVIVOR|BYPASS|DECEDENT|"
    r"FMTR|FMLY|RLT|TR"
    r")(?![A-Z])"
)


def classify_owner(name: str | None) -> OwnerClass | None:
    """Classify an owner name: company (legal suffix/keyword) → trust → individual.

    Returns ``None`` when there is no owner name — consistent with the other
    nullable owner fields (no ``"unknown"`` sentinel string). Company is checked
    before trust so a business carrying a family/trust word still reads as a
    company; everything with no company or trust token is a plain individual.
    """
    if not name or not name.strip():
        return None
    upper = name.upper()
    if _COMPANY_RE.search(upper):
        return "company"
    if _TRUST_RE.search(upper):
        return "trust"
    return "individual"
