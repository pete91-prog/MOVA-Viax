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
import random
import time
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

_LOGGER = logging.getLogger(__name__)

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

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


_SENTINEL = 2147483647

# Soft garden palette — closer to the official MOVA app than flat crayon fills.
_BG = (236, 240, 232)
_GRID = (214, 222, 208)
_LAWN = (86, 164, 92, 255)
_LAWN_EDGE = (46, 108, 58, 255)
_LAWN_SHADOW = (36, 52, 40, 70)
_KEEPOUT_FILL = (232, 214, 190, 175)
_KEEPOUT_EDGE = (168, 108, 58, 240)
_OBSTACLE_FILL = (168, 128, 82, 220)
_OBSTACLE_EDGE = (104, 76, 46, 255)
_PATH = (38, 92, 58, 170)
_PATH_LIVE = (52, 214, 148, 230)
_PATH_LIVE_GLOW = (180, 255, 210, 80)
_MOWER_RING = (255, 255, 255, 255)
_MOWER_CORE = (226, 72, 72, 255)
_HUD_BG = (255, 255, 255, 220)
_HUD_STROKE = (210, 218, 206, 255)
_HUD_TEXT = (34, 44, 38, 255)
_HUD_MUTED = (92, 104, 94, 255)
_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/macos/Inter-Regular.ttf",
    "/usr/share/fonts/truetype/macos/Inter-Medium.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)
_FONT_BOLD_CANDIDATES = (
    "/usr/share/fonts/truetype/macos/Inter-SemiBold.ttf",
    "/usr/share/fonts/truetype/macos/Inter-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)


def _is_sentinel(point: Any) -> bool:
    return (
        isinstance(point, (list, tuple))
        and len(point) >= 2
        and point[0] == _SENTINEL
        and point[1] == _SENTINEL
    )


def _as_point(point: Any) -> tuple[float, float] | None:
    if not isinstance(point, (list, tuple)) or len(point) < 2:
        return None
    if _is_sentinel(point):
        return None
    try:
        return (float(point[0]), float(point[1]))
    except (TypeError, ValueError):
        return None


def _split_segments(raw: Any) -> list[list[tuple[float, float]]]:
    """Split a point list on Dreame/MOVA sentinel break markers."""
    segments: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    for item in raw or []:
        if _is_sentinel(item):
            if current:
                segments.append(current)
                current = []
            continue
        point = _as_point(item)
        if point is not None:
            current.append(point)
    if current:
        segments.append(current)
    return segments


def _collect_map_points(map_json: dict, live_coordinates: list | None) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for region in map_json.get("map") or []:
        for segment in _split_segments(region.get("data")):
            points.extend(segment)
        for segment in _split_segments(region.get("track")):
            points.extend(segment)
    for obstacle in map_json.get("obstacle") or []:
        for segment in _split_segments(obstacle.get("data")):
            points.extend(segment)
    for item in map_json.get("trajectory") or []:
        raw = item.get("data") if isinstance(item, dict) else item
        for segment in _split_segments(raw if isinstance(raw, list) else [item]):
            points.extend(segment)
    dock = map_json.get("dock")
    dock_point = _as_point(dock)
    if dock_point:
        points.append(dock_point)
    for segment in _split_segments(live_coordinates or []):
        points.extend(segment)
    return points


def _load_font(size: int, bold: bool = False):
    """Load a real UI font; fall back to Pillow's default bitmap font."""
    if not _HAS_PIL:
        return None
    for path in _FONT_BOLD_CANDIDATES if bold else _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, ValueError):
            continue
    return ImageFont.load_default()


def _draw_polyline(draw, points: list[tuple[float, float]], color, width: int) -> None:
    if len(points) < 2 or width < 1:
        return
    draw.line(points, fill=color, width=width, joint="curve")
    radius = max(width / 2, 1)
    for x, y in (points[0], points[-1]):
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)


def _polygon_mask(size: tuple[int, int], polygons: list[list[tuple[float, float]]]) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    for poly in polygons:
        if len(poly) >= 3:
            draw.polygon(poly, fill=255)
    return mask


def _clip_overlay(overlay: Image.Image, mask: Image.Image) -> Image.Image:
    clipped = overlay.copy()
    alpha = clipped.split()[-1]
    clipped.putalpha(Image.composite(alpha, Image.new("L", overlay.size, 0), mask))
    return clipped


def _grass_tile(size: int = 128) -> Image.Image:
    """Small repeating grass swatch — much cheaper than painting every blade."""
    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tile)
    rnd = random.Random(11)
    blades = (
        (70, 148, 76, 110),
        (48, 116, 58, 95),
        (102, 178, 98, 80),
        (62, 136, 68, 70),
        (118, 190, 112, 55),
        (40, 98, 52, 65),
    )
    for _ in range(420):
        x = rnd.randint(-2, size + 1)
        y = rnd.randint(-2, size + 1)
        color = blades[rnd.randrange(len(blades))]
        draw.line((x, y, x + rnd.randint(-3, 3), y + rnd.randint(-10, -2)), fill=color, width=1)
    return tile


def _paint_grass(layer: Image.Image, lawns: list[list[tuple[float, float]]]) -> None:
    """Fill lawns with short blades and a darker edge so they read as grass."""
    if not lawns:
        return
    mask = _polygon_mask(layer.size, lawns)
    width, height = layer.size
    tile = _grass_tile(128)
    grass = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    for x in range(0, width, tile.size[0]):
        for y in range(0, height, tile.size[1]):
            grass.paste(tile, (x, y))
    layer.alpha_composite(_clip_overlay(grass, mask))

    rim = Image.new("RGBA", layer.size, (32, 72, 40, 0))
    eroded = mask.filter(ImageFilter.MinFilter(17))
    edge = ImageChops.subtract(mask, eroded)
    rim.putalpha(edge.point(lambda p: int(p * 0.38)))
    layer.alpha_composite(rim)

    patches = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    pd = ImageDraw.Draw(patches)
    rnd = random.Random(19)
    for _ in range(16):
        cx, cy = rnd.randint(0, width), rnd.randint(0, height)
        rw, rh = rnd.randint(50, 130), rnd.randint(28, 80)
        pd.ellipse((cx - rw, cy - rh, cx + rw, cy + rh), fill=(150, 204, 130, 26))
    layer.alpha_composite(_clip_overlay(patches, mask))


def _draw_dock(draw, x: float, y: float, scale: float) -> None:
    """Charging-station glyph instead of a red blob."""
    s = max(scale, 0.85)
    body = 14 * s
    draw.ellipse((x - body, y - body + 3, x + body, y + body + 6), fill=(28, 36, 30, 40))
    draw.rounded_rectangle(
        (x - body * 0.85, y - body * 0.45, x + body * 0.85, y + body * 0.7),
        radius=3 * s,
        fill=(42, 50, 46, 255),
        outline=(236, 240, 232, 255),
        width=max(int(1.5 * s), 1),
    )
    pin_w, pin_h = 2.6 * s, 5.5 * s
    for px in (x - 4.4 * s, x + 1.8 * s):
        draw.rounded_rectangle(
            (px, y - pin_h * 0.15, px + pin_w, y + pin_h),
            radius=s,
            fill=(126, 214, 156, 255),
        )
    roof = [
        (x, y - body * 0.95),
        (x - body * 0.72, y - body * 0.12),
        (x + body * 0.72, y - body * 0.12),
    ]
    draw.polygon(roof, fill=(42, 50, 46, 255))


def _draw_mower(draw, x: float, y: float, scale: float) -> None:
    s = max(scale, 0.85)
    draw.ellipse((x - 11 * s, y - 8 * s, x + 11 * s, y + 14 * s), fill=(24, 30, 26, 45))
    draw.ellipse(
        (x - 9 * s, y - 9 * s, x + 9 * s, y + 9 * s),
        fill=_MOWER_RING,
        outline=(32, 42, 36, 255),
        width=max(int(1.6 * s), 1),
    )
    draw.ellipse((x - 5.2 * s, y - 5.2 * s, x + 5.2 * s, y + 5.2 * s), fill=_MOWER_CORE)


def _draw_card(draw, box, radius: int = 12) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=_HUD_BG, outline=_HUD_STROKE, width=1)


def _text_size(draw, text: str, font) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def render_map_png(
    map_json: dict | None,
    max_px: int = 1400,
    live_coordinates: list | None = None,
    show_title: bool = True,
    show_legend: bool = True,
) -> bytes | None:
    """Render a mower cleaning-record JSON map to PNG bytes.

    Regions of ``type`` 0 are the lawn; other regions are keep-out. Obstacle
    polygons are beds, the trajectory (and optional live path) is the mow
    track, and the dock is a charging-station marker.
    """
    if not _HAS_PIL or not map_json:
        return None

    points = _collect_map_points(map_json, live_coordinates)
    if len(points) < 3:
        return None

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    span_x = max(max_x - min_x, 1.0)
    span_y = max(max_y - min_y, 1.0)

    pad = 72
    scale = (max_px - 2 * pad) / max(span_x, span_y)
    width = max(int(span_x * scale) + 2 * pad, 640)
    height = max(int(span_y * scale) + 2 * pad, 480)
    # 1× is enough once grass texture is in play, and keeps live updates snappy.
    hi = 1
    canvas = Image.new("RGBA", (width * hi, height * hi), (*_BG, 255))

    def to_px(point: tuple[float, float] | list | tuple) -> tuple[float, float]:
        x = (float(point[0]) - min_x) * scale * hi + pad * hi
        y = (height * hi) - ((float(point[1]) - min_y) * scale * hi + pad * hi)
        return (x, y)

    # Soft paper grid
    grid = ImageDraw.Draw(canvas, "RGBA")
    step = max(int(36 * hi * (scale / max(scale, 0.01))), 28)
    for gx in range(0, canvas.size[0], step):
        grid.line((gx, 0, gx, canvas.size[1]), fill=(*_GRID, 90), width=1)
    for gy in range(0, canvas.size[1], step):
        grid.line((0, gy, canvas.size[0], gy), fill=(*_GRID, 90), width=1)

    lawns: list[list[tuple[float, float]]] = []
    keepouts: list[list[tuple[float, float]]] = []
    beds: list[list[tuple[float, float]]] = []
    tracks: list[list[tuple[float, float]]] = []

    for region in map_json.get("map") or []:
        for segment in _split_segments(region.get("data")):
            poly = [to_px(p) for p in segment]
            if len(poly) < 3:
                continue
            if region.get("type", 0) == 0:
                lawns.append(poly)
            else:
                keepouts.append(poly)
        for segment in _split_segments(region.get("track")):
            line = [to_px(p) for p in segment]
            if len(line) >= 2:
                tracks.append(line)

    for obstacle in map_json.get("obstacle") or []:
        for segment in _split_segments(obstacle.get("data")):
            poly = [to_px(p) for p in segment]
            if len(poly) >= 3:
                beds.append(poly)

    for item in map_json.get("trajectory") or []:
        raw = item.get("data") if isinstance(item, dict) else item
        for segment in _split_segments(raw if isinstance(raw, list) else [item]):
            line = [to_px(p) for p in segment]
            if len(line) >= 2:
                tracks.append(line)

    live_tracks = [
        [to_px(p) for p in segment]
        for segment in _split_segments(live_coordinates or [])
        if len(segment) >= 1
    ]

    # Drop shadow under the lawn so the garden sits on the page
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow, "RGBA")
    offset = 5 * hi
    for poly in lawns:
        shadow_draw.polygon([(x + offset, y + offset) for x, y in poly], fill=_LAWN_SHADOW)
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(7 * hi)))

    lawn_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    lawn_draw = ImageDraw.Draw(lawn_layer, "RGBA")
    for poly in lawns:
        lawn_draw.polygon(poly, fill=_LAWN)
    _paint_grass(lawn_layer, lawns)
    for poly in lawns:
        lawn_draw.line(poly + [poly[0]], fill=_LAWN_EDGE, width=max(3 * hi, 3), joint="curve")
    canvas.alpha_composite(lawn_layer)

    detail = ImageDraw.Draw(canvas, "RGBA")
    for poly in keepouts:
        detail.polygon(poly, fill=_KEEPOUT_FILL)
        detail.line(poly + [poly[0]], fill=_KEEPOUT_EDGE, width=max(3 * hi, 3))
    keepout_hatch = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    kh = ImageDraw.Draw(keepout_hatch)
    if keepouts:
        w, h = canvas.size
        for offset in range(-w - h, w + h, 14 * hi):
            kh.line((offset, 0, offset + h, h), fill=(168, 108, 58, 55), width=max(hi, 1))
        canvas.alpha_composite(_clip_overlay(keepout_hatch, _polygon_mask(canvas.size, keepouts)))

    for poly in beds:
        detail.polygon(
            [(x + 2, y + 3) for x, y in poly],
            fill=(40, 32, 22, 40),
        )
        detail.polygon(poly, fill=_OBSTACLE_FILL)
        detail.line(poly + [poly[0]], fill=_OBSTACLE_EDGE, width=max(2 * hi, 2), joint="curve")

    path_width = max(int(2.4 * hi), 3)
    for line in tracks:
        _draw_polyline(detail, line, _PATH, path_width)

    dock = map_json.get("dock")
    dock_point = _as_point(dock)
    if dock_point:
        _draw_dock(detail, *to_px(dock_point), scale=hi)

    for line in live_tracks:
        if len(line) >= 2:
            _draw_polyline(detail, line, _PATH_LIVE_GLOW, path_width + 6)
            _draw_polyline(detail, line, _PATH_LIVE, path_width + 1)
        if line:
            _draw_mower(detail, *line[-1], scale=hi * 0.95)

    if hi == 1:
        image = canvas.convert("RGBA")
    else:
        resample = getattr(Image, "Resampling", Image).LANCZOS
        image = canvas.resize((width, height), resample).convert("RGBA")
    hud = ImageDraw.Draw(image, "RGBA")
    title_font = _load_font(22, bold=True)
    body_font = _load_font(14)
    small_font = _load_font(12)

    summary = parse_clean_record(map_json) or {}
    title = str(summary.get("map_name") or map_json.get("map_name") or "Garden map").strip()
    if live_coordinates:
        title = "Live mowing"
    facts: list[str] = []
    mowed = summary.get("mowed_area")
    lawn_area = summary.get("lawn_area")
    if isinstance(mowed, (int, float)):
        facts.append(f"{mowed:g} m² mowed")
    elif isinstance(lawn_area, (int, float)):
        facts.append(f"{lawn_area:g} m² lawn")
    duration = summary.get("duration_min")
    if isinstance(duration, (int, float)):
        facts.append(f"{duration:g} min")
    if live_coordinates:
        facts.insert(0, f"{len(live_coordinates)} points")
    subtitle = "  ·  ".join(facts)

    if show_title:
        title_w, title_h = _text_size(hud, title, title_font)
        sub_w, sub_h = _text_size(hud, subtitle, body_font) if subtitle else (0, 0)
        card_w = max(title_w, sub_w) + 36
        card_h = title_h + (sub_h + 8 if subtitle else 0) + 24
        card_x = (width - card_w) // 2
        _draw_card(hud, (card_x, 16, card_x + card_w, 16 + card_h))
        hud.text((card_x + 18, 26), title, font=title_font, fill=_HUD_TEXT)
        if subtitle:
            hud.text((card_x + 18, 30 + title_h), subtitle, font=body_font, fill=_HUD_MUTED)

    if show_legend:
        items = [("Lawn", _LAWN), ("Mow path", _PATH)]
        if keepouts:
            items.append(("Keep-out", _KEEPOUT_EDGE))
        if beds:
            items.append(("Obstacle", _OBSTACLE_FILL))
        if live_coordinates:
            items.append(("Live path", _PATH_LIVE))
        if dock_point:
            items.append(("Dock", (42, 50, 46, 255)))
        row_h = 22
        legend_h = 18 + row_h * len(items)
        legend_w = 148
        lx, ly = width - legend_w - 18, height - legend_h - 18
        _draw_card(hud, (lx, ly, lx + legend_w, ly + legend_h), radius=10)
        for i, (label, color) in enumerate(items):
            iy = ly + 12 + i * row_h
            hud.rounded_rectangle((lx + 12, iy, lx + 28, iy + 12), radius=3, fill=color)
            hud.text((lx + 36, iy - 1), label, font=small_font, fill=_HUD_TEXT)

    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
