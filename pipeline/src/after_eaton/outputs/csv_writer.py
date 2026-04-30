"""Write the per-parcel CSV for end-user download.

One row per parcel; columns are every `ParcelResult` field in declaration
order. Booleans serialize to `true`/`false`; `None` becomes an empty cell;
enum values use `.value`. No geometry — keeps the file small and
spreadsheet-friendly.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, fields
from enum import Enum
from pathlib import Path
from typing import Any

from ..processing.parcel_analysis import ParcelResult


def _format(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def write_parcels_csv(results: list[ParcelResult], out_path: Path) -> None:
    columns = [f.name for f in fields(ParcelResult)]
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for result in results:
            row_dict = asdict(result)
            # asdict converts enums to their primitive values via dataclass
            # introspection on nested dataclasses, but Enum fields come
            # through unchanged — _format handles both cases.
            row_dict["damage"] = result.damage
            row_dict["bsd_status"] = result.bsd_status
            writer.writerow([_format(row_dict[c]) for c in columns])
