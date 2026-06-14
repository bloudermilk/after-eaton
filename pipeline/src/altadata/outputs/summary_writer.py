"""Write the burn-area summary JSON."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ..processing.aggregate import SummaryResult


def write_summary_json(summary: SummaryResult, out_path: Path) -> None:
    """Write `summary.json` with `generated_at` first for diff-friendliness."""
    flat = asdict(summary)
    payload = {"generated_at": flat.pop("generated_at"), **flat}
    out_path.write_text(json.dumps(payload, indent=2))
