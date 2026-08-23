"""Integration test: render a historical map through the SVG generator.

Exercises the ``historical_file_path`` code path in
``generate_svg_map_image``, including ``_scale_map_data`` which scales
decimeter coordinates ×10 to centimeters while preserving sentinel markers.

Uses the same captured session fixture as the live-mowing integration test
but renders it as a *historical* map (``historical_file_path`` is set).
"""

import json
import re
from pathlib import Path
from unittest.mock import Mock

import pytest

from custom_components.mova_viax.dreame.svg_map_generator import (
    generate_svg_map_image,
    _scale_map_data,
)

TEST_DATA_DIR = Path(__file__).parent / "test_data"
FIXTURE_JSON = TEST_DATA_DIR / "live_mowing_session_20260322.json"

HISTORICAL_GOLDEN_SVG = TEST_DATA_DIR / "historical_map_golden.svg"
HISTORICAL_ACTUAL_SVG = TEST_DATA_DIR / "historical_map_actual.svg"

_TIMESTAMP_RE = re.compile(r"Updated: \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
_DISTANCE_RE = re.compile(r"Distance: [\d.]+m")

_SENTINEL = 2147483647


@pytest.fixture()
def session_fixture():
    with open(FIXTURE_JSON, "r") as f:
        return json.load(f)


def _normalise_svg(svg_text: str) -> str:
    svg_text = _TIMESTAMP_RE.sub("Updated: TIMESTAMP", svg_text)
    svg_text = _DISTANCE_RE.sub("Distance: Xm", svg_text)
    return svg_text


def _assert_svg_matches_golden(
    svg_bytes: bytes,
    actual_path: Path,
    golden_path: Path,
    stage_label: str,
) -> None:
    actual_path.write_bytes(svg_bytes)

    if not golden_path.exists():
        golden_path.write_bytes(svg_bytes)
        return

    golden_text = _normalise_svg(golden_path.read_text(encoding="utf-8"))
    actual_text = _normalise_svg(svg_bytes.decode("utf-8"))

    assert actual_text == golden_text, (
        f"[{stage_label}] Rendered SVG differs from golden reference.\n"
        f"Actual saved to: {actual_path}\n"
        f"If the change is intentional, update the golden file:\n"
        f"  cp {actual_path} {golden_path}"
    )


class TestScaleMapData:
    """Unit tests for _scale_map_data to guard sentinel handling."""

    def test_sentinels_are_preserved(self):
        data = {
            "map": [{
                "data": [[10, 20], [30, 40]],
                "track": [
                    [100, 200],
                    [_SENTINEL, _SENTINEL],
                    [300, 400],
                ],
            }],
        }
        scaled = _scale_map_data(data, factor=10)
        track = scaled["map"][0]["track"]
        assert track[0] == [1000, 2000]
        assert track[1] == [_SENTINEL, _SENTINEL], "sentinel must not be scaled"
        assert track[2] == [3000, 4000]

    def test_boundary_points_scaled(self):
        data = {"map": [{"data": [[5, -3], [0, 0]]}]}
        scaled = _scale_map_data(data, factor=10)
        assert scaled["map"][0]["data"] == [[50, -30], [0, 0]]

    def test_obstacles_scaled(self):
        data = {"obstacle": [{"data": [[1, 2], [3, 4]]}]}
        scaled = _scale_map_data(data, factor=10)
        assert scaled["obstacle"][0]["data"] == [[10, 20], [30, 40]]

    def test_trajectories_scaled(self):
        data = {"trajectory": [{"data": [[7, 8]]}]}
        scaled = _scale_map_data(data, factor=10)
        assert scaled["trajectory"][0]["data"] == [[70, 80]]

    def test_dock_scaled(self):
        data = {"dock": [127, 2, 3583]}
        scaled = _scale_map_data(data, factor=10)
        assert scaled["dock"] == [1270, 20, 3583], "only x,y scaled, heading preserved"

    def test_empty_data_noop(self):
        assert _scale_map_data({}) == {}


class TestHistoricalMapIntegration:
    """Render a historical map and compare against a golden SVG."""

    def test_render_historical_map(self, session_fixture):
        map_data = session_fixture["map_data"]

        coordinator = Mock()
        coordinator.device = Mock()
        coordinator.device.mower_coordinates = None
        coordinator.device_connected = True

        svg_bytes = generate_svg_map_image(
            map_data,
            historical_file_path="/fake/historical/map.json",
            coordinator=coordinator,
            rotation=0,
        )

        _assert_svg_matches_golden(
            svg_bytes,
            HISTORICAL_ACTUAL_SVG,
            HISTORICAL_GOLDEN_SVG,
            "historical-map",
        )

    def test_sentinels_preserved_in_fixture(self, session_fixture):
        """Verify that the fixture data actually contains sentinels and
        that _scale_map_data preserves them (regression for the sentinel
        scaling bug)."""
        map_data = session_fixture["map_data"]

        # Fixture must have sentinels
        tracks = map_data["map"][0]["track"]
        sentinel_indices = [
            i for i, p in enumerate(tracks)
            if isinstance(p, list) and p[0] == _SENTINEL and p[1] == _SENTINEL
        ]
        assert sentinel_indices, "fixture should contain sentinel markers"

        # After scaling, sentinels must still be present and unchanged
        scaled = _scale_map_data(map_data, factor=10)
        scaled_tracks = scaled["map"][0]["track"]
        for idx in sentinel_indices:
            assert scaled_tracks[idx] == [_SENTINEL, _SENTINEL], (
                f"sentinel at index {idx} was scaled"
            )
