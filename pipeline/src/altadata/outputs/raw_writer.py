"""Write raw fetched source records to disk for reproducibility/audit."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def write_raw_records(
    records: Iterable[dict[str, Any]],
    out_path: Path,
    *,
    source_name: str,
    fetched_at: str,
) -> None:
    """Persist a list of raw source records as a JSON object with metadata.

    Each record is the flat ArcGIS attributes dict merged with a `_geometry`
    key — i.e. exactly what the fetcher returned and what validators read.
    Re-running the rest of the pipeline against this file should reproduce
    the same outputs.
    """
    materialized = list(records)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "source": source_name,
        "fetched_at": fetched_at,
        "record_count": len(materialized),
        "records": materialized,
    }
    out_path.write_text(json.dumps(payload, default=str))
