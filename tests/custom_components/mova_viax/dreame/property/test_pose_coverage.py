"""Tests for pose coverage property handler with 20-bit parsing and mission completion."""

import struct
import pytest
from custom_components.mova_viax.dreame.property.pose_coverage import (
    PoseCoverageHandler,
    _parse_pose,
    _parse_track_deltas,
    _parse_task,
    _POSE_SCALE,
)


# ---------------------------------------------------------------------------
# Helpers for building correctly-encoded test payloads
# ---------------------------------------------------------------------------


def _encode_pose_bytes(x: int, y: int, angle_deg: float = 0.0) -> list[int]:
    """Encode X, Y, angle into 6 pose bytes using 20-bit overlapping format."""
    x_20 = x & 0xFFFFF
    y_20 = y & 0xFFFFF
    b0 = x_20 & 0xFF
    b1 = (x_20 >> 8) & 0xFF
    x_hi = (x_20 >> 16) & 0x0F
    y_lo = y_20 & 0x0F
    b2 = (y_lo << 4) | x_hi
    b3 = (y_20 >> 4) & 0xFF
    b4 = (y_20 >> 12) & 0xFF
    b5 = round(angle_deg / 360.0 * 255)
    return [b0, b1, b2, b3, b4, b5]


def _encode_task_bytes(
    region_id: int = 0,
    task_id: int = 0,
    percent_x100: int = 0,
    total_centisqm: int = 0,
    finish_centisqm: int = 0,
) -> list[int]:
    """Encode 10-byte task block."""
    return [
        region_id,
        task_id,
        percent_x100 & 0xFF,
        (percent_x100 >> 8) & 0xFF,
        total_centisqm & 0xFF,
        (total_centisqm >> 8) & 0xFF,
        (total_centisqm >> 16) & 0xFF,
        finish_centisqm & 0xFF,
        (finish_centisqm >> 8) & 0xFF,
        (finish_centisqm >> 16) & 0xFF,
    ]


def _encode_trace_bytes(
    start_index: int = 0,
    deltas: list[tuple[int, int]] | None = None,
    pad_to: int = 15,
) -> list[int]:
    """Encode a trace chunk: 3-byte index + pairs of int16 LE deltas."""
    result = [
        start_index & 0xFF,
        (start_index >> 8) & 0xFF,
        (start_index >> 16) & 0xFF,
    ]
    for dx, dy in (deltas or []):
        result.extend(list(struct.pack("<hh", dx, dy)))
    # pad remaining pairs to zeros
    while len(result) < pad_to:
        result.append(0)
    return result


def _build_full_payload(
    x: int = 0,
    y: int = 0,
    angle: float = 0.0,
    region_id: int = 0,
    task_id: int = 0,
    percent_x100: int = 0,
    total_centisqm: int = 0,
    finish_centisqm: int = 0,
    trace_deltas: list[tuple[int, int]] | None = None,
) -> list[int]:
    """Build a full 33-byte sentinel-framed payload."""
    pose = _encode_pose_bytes(x, y, angle)
    trace = _encode_trace_bytes(deltas=trace_deltas, pad_to=15)
    task = _encode_task_bytes(region_id, task_id, percent_x100, total_centisqm, finish_centisqm)
    return [0xCE] + pose + trace + task + [0xCE]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def handler():
    """Create a pose coverage handler for testing."""
    return PoseCoverageHandler()


# ---------------------------------------------------------------------------
# Low-level parsing tests
# ---------------------------------------------------------------------------


class TestParsePose:
    """Tests for the 20-bit overlapping pose extraction."""

    def test_positive_small(self):
        data = [0xCE] + _encode_pose_bytes(100, 200)
        x, y, _angle = _parse_pose(data, offset=1)
        assert x == 100
        assert y == 200

    def test_zero(self):
        data = [0xCE] + _encode_pose_bytes(0, 0)
        x, y, _angle = _parse_pose(data, offset=1)
        assert x == 0
        assert y == 0

    def test_negative(self):
        data = [0xCE] + _encode_pose_bytes(-100, -200)
        x, y, _angle = _parse_pose(data, offset=1)
        assert x == -100
        assert y == -200

    def test_large_positive(self):
        data = [0xCE] + _encode_pose_bytes(50000, 40000)
        x, y, _angle = _parse_pose(data, offset=1)
        assert x == 50000
        assert y == 40000

    def test_large_negative(self):
        data = [0xCE] + _encode_pose_bytes(-50000, -40000)
        x, y, _angle = _parse_pose(data, offset=1)
        assert x == -50000
        assert y == -40000

    def test_mixed_signs(self):
        data = [0xCE] + _encode_pose_bytes(300, -500)
        x, y, _angle = _parse_pose(data, offset=1)
        assert x == 300
        assert y == -500

    def test_20bit_boundary(self):
        """Values near the 20-bit signed boundary (±524287)."""
        data = [0xCE] + _encode_pose_bytes(524287, -524288)
        x, y, _angle = _parse_pose(data, offset=1)
        assert x == 524287
        assert y == -524288

    def test_angle(self):
        data = [0xCE] + _encode_pose_bytes(0, 0, 180.0)
        _x, _y, angle = _parse_pose(data, offset=1)
        # byte 5 = round(180/360*255) = 128 -> 128/255*360 ≈ 180.71
        assert abs(angle - 180.0) < 1.5


class TestParseTrackDeltas:
    """Tests for track delta extraction."""

    def test_basic_deltas(self):
        trace = _encode_trace_bytes(start_index=0, deltas=[(5, -3), (10, 7)])
        raw = [0] * 7 + trace  # offset 7
        _idx, pts = _parse_track_deltas(raw, offset=7, length=15, base_x=1000, base_y=2000)
        assert pts[0] == [1000 + 5 * _POSE_SCALE, 2000 + (-3) * _POSE_SCALE]
        assert pts[1] == [1000 + 10 * _POSE_SCALE, 2000 + 7 * _POSE_SCALE]

    def test_sentinel_detection(self):
        # dx=32767, dy=32767 -> both > 32766 -> sentinel
        trace = _encode_trace_bytes(deltas=[(32767, 32767)])
        raw = [0] * 7 + trace
        _idx, pts = _parse_track_deltas(raw, offset=7, length=15, base_x=0, base_y=0)
        assert pts[0] == [2147483647, 2147483647]

    def test_start_index(self):
        trace = _encode_trace_bytes(start_index=42, deltas=[(1, 1)])
        raw = [0] * 7 + trace
        idx, _pts = _parse_track_deltas(raw, offset=7, length=15, base_x=0, base_y=0)
        assert idx == 42

    def test_too_short(self):
        idx, pts = _parse_track_deltas([0] * 10, offset=7, length=2, base_x=0, base_y=0)
        assert idx == 0
        assert pts == []


class TestParseTask:
    """Tests for task/progress extraction."""

    def test_basic_task(self):
        task_bytes = _encode_task_bytes(
            region_id=5,
            task_id=1,
            percent_x100=9600,  # 96.0%
            total_centisqm=10000,  # 100.00 sqm
            finish_centisqm=9600,  # 96.00 sqm
        )
        raw = [0] * 22 + task_bytes
        task = _parse_task(raw, offset=22)
        assert task["region_id"] == 5
        assert task["task_id"] == 1
        assert task["progress_percent"] == 96.0
        assert task["total_area_sqm"] == 100.0
        assert task["current_area_sqm"] == 96.0


# ---------------------------------------------------------------------------
# Handler integration tests
# ---------------------------------------------------------------------------


class TestHandlerInitialization:
    def test_defaults(self, handler):
        assert handler.current_area_sqm is None
        assert handler.total_area_sqm is None
        assert handler.progress_percent is None
        assert handler.x_coordinate is None
        assert handler.y_coordinate is None
        assert handler._mission_completed is False


class TestFullFormatParsing:
    """Test full 33-byte payload parsing through the handler."""

    def test_coordinates_in_map_units(self, handler):
        payload = _build_full_payload(x=100, y=200)
        assert handler.parse_value(payload) is True
        # Coordinates should be pose * _POSE_SCALE
        assert handler.x_coordinate == 100 * _POSE_SCALE
        assert handler.y_coordinate == 200 * _POSE_SCALE

    def test_negative_coordinates(self, handler):
        payload = _build_full_payload(x=-300, y=-500)
        assert handler.parse_value(payload) is True
        assert handler.x_coordinate == -300 * _POSE_SCALE
        assert handler.y_coordinate == -500 * _POSE_SCALE

    def test_progress_from_task(self, handler):
        payload = _build_full_payload(
            percent_x100=9600,
            total_centisqm=10000,
            finish_centisqm=9600,
        )
        assert handler.parse_value(payload) is True
        assert handler.progress_percent == 96.0
        assert handler.total_area_sqm == 100.0
        assert handler.current_area_sqm == 96.0

    def test_track_points_extracted(self, handler):
        payload = _build_full_payload(
            x=100, y=200,
            trace_deltas=[(5, -3), (10, 7)],
        )
        assert handler.parse_value(payload) is True
        coords = handler.get_coordinates_notification_data()
        pts = coords["track_points"]
        assert len(pts) >= 2
        # First delta: base + delta*SCALE
        assert pts[0] == [100 * _POSE_SCALE + 5 * _POSE_SCALE, 200 * _POSE_SCALE + (-3) * _POSE_SCALE]
        assert pts[1] == [100 * _POSE_SCALE + 10 * _POSE_SCALE, 200 * _POSE_SCALE + 7 * _POSE_SCALE]

    def test_heading(self, handler):
        payload = _build_full_payload(angle=90.0)
        handler.parse_value(payload)
        assert handler.heading is not None
        assert abs(handler.heading - 90.0) < 2.0  # byte quantization

    def test_segment_from_region_id(self, handler):
        payload = _build_full_payload(region_id=5)
        handler.parse_value(payload)
        assert handler.segment == 5


class TestMissionCompletion:
    """Test mission completion flag lifecycle."""

    def test_caps_progress_at_100(self, handler):
        payload = _build_full_payload(percent_x100=9600, total_centisqm=10000, finish_centisqm=9600)
        handler.parse_value(payload)
        assert handler.progress_percent == 96.0

        handler.mark_mission_completed()
        assert handler.progress_percent == 100.0

    def test_flag_affects_subsequent_parsing(self, handler):
        handler.mark_mission_completed()
        payload = _build_full_payload(percent_x100=9600, total_centisqm=10000, finish_centisqm=9600)
        handler.parse_value(payload)
        assert handler.progress_percent == 100.0

    def test_reset_mission_completion(self, handler):
        handler.mark_mission_completed()
        assert handler._mission_completed is True
        handler.reset_mission_completion()
        assert handler._mission_completed is False

    def test_complete_lifecycle(self, handler):
        # 1. Parse 50%
        p50 = _build_full_payload(percent_x100=5000, total_centisqm=10000, finish_centisqm=5000)
        handler.parse_value(p50)
        assert handler.progress_percent == 50.0

        # 2. Parse 96%
        p96 = _build_full_payload(percent_x100=9600, total_centisqm=10000, finish_centisqm=9600)
        handler.parse_value(p96)
        assert handler.progress_percent == 96.0

        # 3. Complete
        handler.mark_mission_completed()
        assert handler.progress_percent == 100.0

        # 4. Subsequent updates stay at 100%
        handler.parse_value(p96)
        assert handler.progress_percent == 100.0

        # 5. New mission
        handler.reset_mission_completion()
        p30 = _build_full_payload(percent_x100=3000, total_centisqm=10000, finish_centisqm=3000)
        handler.parse_value(p30)
        assert handler.progress_percent == 30.0

    def test_zero_progress_not_capped(self, handler):
        payload = _build_full_payload(percent_x100=0, total_centisqm=10000, finish_centisqm=0)
        handler.parse_value(payload)
        handler.mark_mission_completed()
        assert handler.progress_percent == 0.0

    def test_no_prior_progress(self, handler):
        handler.mark_mission_completed()
        assert handler.progress_percent is None


class TestShortFormats:
    """Test shorter payload formats."""

    def test_pose_only_13_bytes(self, handler):
        pose = _encode_pose_bytes(100, 200)
        payload = [0xCE] + pose + [0, 0, 0, 0, 0] + [0xCE]
        assert len(payload) == 13
        assert handler.parse_value(payload) is True
        assert handler.x_coordinate == 100 * _POSE_SCALE
        assert handler.y_coordinate == 200 * _POSE_SCALE

    def test_8_bytes_acknowledged(self, handler):
        payload = [0xCE, 0, 0, 0, 0, 0, 0, 0xCE]
        assert handler.parse_value(payload) is True

    def test_alt_format_task_only(self, handler):
        """11-byte format: task(10) + CE (no leading sentinel)."""
        task = _encode_task_bytes(percent_x100=5000, total_centisqm=10000, finish_centisqm=5000)
        payload = task + [0xCE]
        assert len(payload) == 11
        assert handler.parse_value(payload) is True
        assert handler.progress_percent == 50.0


class TestNotificationData:
    """Test notification data accessors."""

    def test_progress_notification(self, handler):
        payload = _build_full_payload(percent_x100=7650, total_centisqm=10000, finish_centisqm=7650)
        handler.parse_value(payload)
        data = handler.get_progress_notification_data()
        assert data["current_area_sqm"] == 76.5
        assert data["total_area_sqm"] == 100.0
        assert data["progress_percent"] == 76.5

    def test_coordinates_notification_includes_track(self, handler):
        payload = _build_full_payload(x=10, y=20, trace_deltas=[(1, 2)])
        handler.parse_value(payload)
        data = handler.get_coordinates_notification_data()
        assert data["x"] == 10 * _POSE_SCALE
        assert data["y"] == 20 * _POSE_SCALE
        assert "track_points" in data
        assert len(data["track_points"]) >= 1

    def test_progress_capped_at_100(self, handler):
        """Percent > 10000 (100%) should be capped to 100."""
        payload = _build_full_payload(percent_x100=11000, total_centisqm=10000, finish_centisqm=11000)
        handler.parse_value(payload)
        assert handler.progress_percent == 100.0


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_invalid_type(self, handler):
        assert handler.parse_value("not a list") is False

    def test_too_short(self, handler):
        assert handler.parse_value([0xCE, 0, 0, 0xCE]) is False

    def test_bad_sentinels(self, handler):
        assert handler.parse_value([0, 0, 0, 0, 0, 0, 0, 0]) is False

    def test_path_history_accumulates(self, handler):
        p1 = _build_full_payload(x=10, y=20, trace_deltas=[(1, 1)])
        p2 = _build_full_payload(x=30, y=40, trace_deltas=[(2, 2)])
        handler.parse_value(p1)
        handler.parse_value(p2)
        assert len(handler.path_history) >= 2

    def test_clear_path_history(self, handler):
        p = _build_full_payload(x=10, y=20, trace_deltas=[(1, 1)])
        handler.parse_value(p)
        handler.clear_path_history()
        assert handler.path_history == []
