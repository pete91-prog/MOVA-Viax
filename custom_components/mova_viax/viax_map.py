"""Saved-map support for MOVA ViAX mowers that publish cleaning-record JSON.

ViAX-series mowers such as ``mova.mower.g2420b`` often do not stream the
protobuf/vector map used by other Dreame/MOVA models. After each run they
emit a clean-record event (siid 4 / eiid 1) whose ``piid 9`` argument is the
name of a JSON object in Dreame/MOVA cloud storage. That JSON already contains
decoded map geometry (boundary polygons in centimetres, dock, obstacles, and
the mow trajectory).

This module fetches the latest such object and renders it to a PNG that the
map camera can serve when the standard vector-map pipeline has no data.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

_LOGGER = logging.getLogger(__name__)

try:
    from PIL import Image, ImageDraw

    _HAS_PIL = True
except ImportError:  # pragma: no cover - Pillow is a declared requirement
    _HAS_PIL = False

# siid 4 / eiid 1 clean-record event. Its piid 9 argument is the cloud object
# name of the run's JSON record, which carries the map geometry.
_CLEAN_RECORD_EVENT = "4.1"

_VIAX_MODEL_MARKERS = (
    "viax",
    "g2420",
)


def _device_model(device: Any) -> str:
    """Best-effort full MIoT model string for a device."""
    info = getattr(device, "info", None)
    cloud = getattr(device, "cloud_device", None)
    candidates = [
        getattr(info, "model", None),
        getattr(device, "model", None),
        getattr(cloud, "_model", None),
    ]
    for model in candidates:
        if model:
            return str(model)
    return ""


def is_viax_json_map(device: Any, model: str | None = None) -> bool:
    """Return True for mowers whose map arrives as a cloud JSON record."""
    resolved = (model or _device_model(device)).lower()
    if any(marker in resolved for marker in _VIAX_MODEL_MARKERS):
        return True
    return "mower" in resolved and not getattr(device, "vector_map", None)


def _find_object_name(obj: Any) -> str | None:
    """Recursively find an ``...dreame....json`` object name in a nested value."""
    if isinstance(obj, str):
        if obj.endswith(".json") and "dreame" in obj:
            return obj
        stripped = obj.strip()
        if stripped[:1] in ("[", "{"):
            try:
                return _find_object_name(json.loads(stripped))
            except (ValueError, TypeError):
                return None
        return None
    if isinstance(obj, dict):
        for value in obj.values():
            found = _find_object_name(value)
            if found:
                return found
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            found = _find_object_name(value)
            if found:
                return found
    return None


def fetch_latest_map_json(cloud: Any) -> dict | None:
    """Fetch and parse the most recent cleaning-record JSON for the device."""
    try:
        events = cloud.get_device_event(_CLEAN_RECORD_EVENT, 1)
    except Exception as ex:  # pragma: no cover - network/cloud errors
        _LOGGER.debug("ViAX map: get_device_event failed: %s", ex)
        return None

    object_name = _find_object_name(events)
    if not object_name:
        _LOGGER.debug("ViAX map: no map object name found in events: %r", events)
        return None

    try:
        url = cloud.get_interim_file_url(object_name)
        if not url:
            _LOGGER.debug("ViAX map: no signed url for %s", object_name)
            return None
        data = cloud.get_file(url)
        if not data:
            _LOGGER.debug("ViAX map: empty download for %s", object_name)
            return None
        return json.loads(data.decode("utf-8"))
    except Exception as ex:  # pragma: no cover - network/parse errors
        _LOGGER.debug("ViAX map: download/parse failed for %s: %s", object_name, ex)
        return None


def parse_clean_record(record: dict | None) -> dict | None:
    """Extract a per-run summary from a cleaning-record JSON object."""
    if not record:
        return None
    start = record.get("start")
    end = record.get("end")
    duration_min = None
    completed = None
    if isinstance(start, (int, float)) and isinstance(end, (int, float)) and end >= start:
        duration_min = round((end - start) / 60, 1)
    if isinstance(end, (int, float)) and end > 0:
        completed = datetime.fromtimestamp(end, tz=timezone.utc)
    faults = record.get("faults") or []
    return {
        "mowed_area": record.get("areas"),
        "lawn_area": record.get("map_area"),
        "duration_min": duration_min,
        "completed": completed,
        "fault_count": len(faults) if isinstance(faults, list) else 0,
        "faults": faults,
        "map_name": record.get("map_name"),
    }


def refresh_device_map(device: Any, min_interval: int = 55) -> None:
    """Fetch the latest cloud map + record and cache it on the device.

    Stores ``device.viax_map_json`` (raw geometry for the camera) and
    ``device.viax_last_mow`` (parsed summary for sensors). Throttled by
    ``min_interval`` seconds. Blocking (cloud I/O) — call in an executor.
    """
    now = time.time()
    if (
        getattr(device, "viax_map_json", None) is not None
        and (now - getattr(device, "_viax_map_ts", 0)) < min_interval
    ):
        return
    cloud = getattr(device, "cloud_device", None)
    if cloud is None:
        return
    map_json = fetch_latest_map_json(cloud)
    if map_json:
        device.viax_map_json = map_json
        device.viax_last_mow = parse_clean_record(map_json)
        device._viax_map_ts = now


def render_map_png(map_json: dict | None, max_px: int = 1024) -> bytes | None:
    """Render a mower cleaning-record JSON map to PNG bytes.

    Regions of ``type`` 0 are the mow area (filled green); other regions are
    treated as keep-out. Obstacle polygons are drawn as beds, the trajectory as
    the mow path, and the dock as a marker.
    """
    if not _HAS_PIL or not map_json:
        return None

    regions = map_json.get("map") or []
    obstacles = map_json.get("obstacle") or []
    trajectory = map_json.get("trajectory") or []
    dock = map_json.get("dock")

    points: list = []
    for region in regions:
        points += region.get("data") or []
    for obstacle in obstacles:
        points += obstacle.get("data") or []
    for segment in trajectory:
        points += segment.get("data") or []
    if dock and len(dock) >= 2:
        points.append(dock[:2])

    points = [p for p in points if isinstance(p, (list, tuple)) and len(p) >= 2]
    if len(points) < 3:
        return None

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    span_x = max(max_x - min_x, 1)
    span_y = max(max_y - min_y, 1)

    pad = 24
    scale = min((max_px - 2 * pad) / max(span_x, span_y), 0.5)
    width = int(span_x * scale) + 2 * pad
    height = int(span_y * scale) + 2 * pad

    def to_px(point: list | tuple) -> tuple[float, float]:
        x = (point[0] - min_x) * scale + pad
        y = height - ((point[1] - min_y) * scale + pad)
        return (x, y)

    image = Image.new("RGB", (width, height), (247, 248, 246))
    draw = ImageDraw.Draw(image, "RGBA")

    for region in regions:
        poly = [to_px(p) for p in (region.get("data") or []) if len(p) >= 2]
        if len(poly) < 3:
            continue
        if region.get("type") == 0:
            draw.polygon(poly, fill=(120, 190, 120, 150), outline=(60, 130, 60, 255))
        else:
            draw.polygon(poly, fill=(180, 180, 180, 120), outline=(120, 120, 120, 255))

    for obstacle in obstacles:
        poly = [to_px(p) for p in (obstacle.get("data") or []) if len(p) >= 2]
        if len(poly) >= 3:
            draw.polygon(poly, fill=(150, 110, 70, 170), outline=(110, 80, 50, 255))

    for segment in trajectory:
        line = [to_px(p) for p in (segment.get("data") or []) if len(p) >= 2]
        if len(line) >= 2:
            draw.line(line, fill=(40, 90, 200, 200), width=2)

    if dock and len(dock) >= 2:
        dx, dy = to_px(dock[:2])
        r = 7
        draw.ellipse(
            [dx - r, dy - r, dx + r, dy + r],
            fill=(230, 60, 60, 255),
            outline=(120, 20, 20, 255),
        )

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
