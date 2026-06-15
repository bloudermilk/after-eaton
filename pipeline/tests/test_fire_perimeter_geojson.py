"""Tests for the dissolved fire-perimeter GeoJSON writer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from altadata.outputs.fire_perimeter_writer import write_fire_perimeter_geojson
from altadata.sources.schemas import FirePerimeter


def _square(cx: float, cy: float, half: float = 0.5) -> FirePerimeter:
    """An ArcGIS-style perimeter record: one square ring centered at (cx, cy)."""
    return {
        "_geometry": {
            "rings": [
                [
                    [cx - half, cy - half],
                    [cx + half, cy - half],
                    [cx + half, cy + half],
                    [cx - half, cy + half],
                    [cx - half, cy - half],
                ]
            ]
        },
    }


def _iter_coords(geometry: dict[str, Any]) -> list[float]:
    """Flatten every numeric coordinate in a GeoJSON geometry."""
    nums: list[float] = []

    def walk(node: Any) -> None:
        if isinstance(node, (int, float)):
            nums.append(float(node))
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(geometry["coordinates"])
    return nums


def _write(
    perimeter: list[FirePerimeter], tmp_path: Path, **kwargs: Any
) -> dict[str, Any]:
    out = tmp_path / "fire-perimeter.geojson"
    write_fire_perimeter_geojson(
        perimeter, out, generated_at="2026-06-14T00:00:00+00:00", **kwargs
    )
    return json.loads(out.read_text())


def test_dissolves_overlapping_rings_into_single_feature(tmp_path: Path) -> None:
    # Two squares overlapping in x[0, 0.5] should merge into one boundary with
    # no interior seam — a single Polygon feature, not two.
    payload = _write([_square(0.0, 0.0), _square(0.5, 0.0)], tmp_path)

    assert payload["type"] == "FeatureCollection"
    assert len(payload["features"]) == 1
    feature = payload["features"][0]
    assert feature["geometry"]["type"] == "Polygon"
    # Union spans the combined x-range; the shared interior edge is dissolved.
    xs = _iter_coords(feature["geometry"])[0::2]
    assert min(xs) == -0.5
    assert max(xs) == 1.0


def test_rounds_coordinates_to_precision(tmp_path: Path) -> None:
    high_precision = _square(0.123456789, 0.987654321, half=0.111111111)
    payload = _write([high_precision], tmp_path, precision=5)

    coords = _iter_coords(payload["features"][0]["geometry"])
    assert coords  # sanity: geometry survived
    for value in coords:
        assert round(value, 5) == value


def test_empty_perimeter_yields_no_features(tmp_path: Path) -> None:
    payload = _write([], tmp_path)
    assert payload["type"] == "FeatureCollection"
    assert payload["features"] == []


def test_includes_generated_at_metadata(tmp_path: Path) -> None:
    payload = _write([_square(0.0, 0.0)], tmp_path)
    assert payload["metadata"]["generated_at"] == "2026-06-14T00:00:00+00:00"
