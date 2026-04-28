"""Write the burn-area summary JSON."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ..processing.aggregate import SummaryResult


def write_summary_json(summary: SummaryResult, out_path: Path) -> None:
    out_path.write_text(json.dumps(asdict(summary), indent=2))
