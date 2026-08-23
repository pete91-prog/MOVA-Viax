"""SVG-based map visualization for Dreame Mower Camera Entity.

This module provides SVG generation functions as an alternative to PIL/matplotlib
for better quality and HAOS compatibility.
"""

import html
import logging
from typing import Any, Dict, List, Tuple
from datetime import datetime

_LOGGER = logging.getLogger(__name__)


# Map visualization constants
# NOTE: Rotation (90°, 180°, 270°) currently only works correctly when WIDTH == HEIGHT (square canvas).
# Non-square dimensions will cause the rotated content to be clipped or misaligned because
# the rotated bounding box exceeds the canvas boundaries. Keep these values equal for rotation support.
MAP_IMAGE_WIDTH = 1200
MAP_IMAGE_HEIGHT = 1200
MAP_PADDING = 50

# Color definitions (hex colors for SVG)
COLORS_SVG = {
    'background': '#eef2ec',
    'live_background': '#eef2ec',
    'map_boundary': '#2e6c3a',
    'mowing_path': '#265c3a',
    'trajectory': '#8a8f88',
    'obstacle': "#68502e",
    'obstacle_fill': "#a8805290",
    'live_path': '#28c984',
    'live_boundary': '#2e6c3a',
    'start_position': '#2bb673',
    'current_position': '#e24848',
    'text_color': '#222c26',
    'grid_color': '#d6ddd0',
    'text_bg': "#fffffff0",
    'card_stroke': '#d4dcd0',
    'muted_text': '#5c685e',
}

# Zone fill colors — garden greens first, then muted companions
# Each entry is (fill_with_alpha, outline)
ZONE_COLORS = [
    ('#56a45ce6', '#2e6c3a'),  # Grass
    ('#6aa9c0d8', '#3d7f96'),  # Blue
    ('#d7b48cd8', '#a8845c'),  # Beige/tan
    ('#d9a2a2d8', '#b07878'),  # Pink/salmon
    ('#d4c878d8', '#b0a25a'),  # Yellow
    ('#b09ac8d8', '#8c78ac'),  # Purple
    ('#7cbcb4d8', '#5a9088'),  # Teal
    ('#c8a888d8', '#a08460'),  # Warm brown
]
ZONE_LABEL_COLOR = '#243028'
_SINGLE_ZONE_FILL = '#56a45ce6'
_FONT = "Inter, Segoe UI, Helvetica, Arial, sans-serif"


def calculate_bounds(all_points: List[List[int]]) -> Tuple[int, int, int, int]:
    """Calculate the bounding box for all coordinate points.
    
    Returns:
        Tuple of (min_x, min_y, max_x, max_y)
    """
    if not all_points:
        return 0, 0, 100, 100
    
    valid_points = [p for p in all_points if p[0] != 2147483647 and p[1] != 2147483647]
    if not valid_points:
        return 0, 0, 100, 100
    
    min_x = min(p[0] for p in valid_points)
    max_x = max(p[0] for p in valid_points)
    min_y = min(p[1] for p in valid_points)
    max_y = max(p[1] for p in valid_points)
    
    return min_x, min_y, max_x, max_y


def coord_to_pixel(x: int, y: int, bounds: Tuple[int, int, int, int], 
                   img_width: int, img_height: int, padding: int = MAP_PADDING) -> Tuple[int, int]:
    """Convert mower coordinates to image pixel coordinates.
    
    Args:
        x, y: Mower coordinates
        bounds: (min_x, min_y, max_x, max_y) from calculate_bounds
        img_width, img_height: Image dimensions
        padding: Padding around the edges
    
    Returns:
        Tuple of (pixel_x, pixel_y)
    """
    min_x, min_y, max_x, max_y = bounds
    
    # Handle edge case where all coordinates are the same
    if max_x == min_x:
        max_x = min_x + 100
    if max_y == min_y:
        max_y = min_y + 100
    
    # Calculate scale factors
    coord_width = max_x - min_x
    coord_height = max_y - min_y
    available_width = img_width - 2 * padding
    available_height = img_height - 2 * padding
    
    scale_x = available_width / coord_width
    scale_y = available_height / coord_height
    
    # Use the smaller scale to maintain aspect ratio
    scale = min(scale_x, scale_y)

    # Centre content in the available space
    rendered_width = coord_width * scale
    rendered_height = coord_height * scale
    offset_x = padding + (available_width - rendered_width) / 2
    offset_y = padding + (available_height - rendered_height) / 2

    # Convert coordinates
    pixel_x = int(offset_x + (x - min_x) * scale)
    # Flip Y coordinate (image coordinates have origin at top-left)
    pixel_y = int(offset_y + (max_y - y) * scale)
    
    return pixel_x, pixel_y


def create_svg_document(width: int, height: int, background_color: str = "white") -> List[str]:
    """Create the basic SVG document structure.
    
    Returns:
        List of SVG lines that can be joined
    """
    return [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">',
        f'<rect width="100%" height="100%" fill="{background_color}"/>'
    ]


def svg_path_from_segments(segments: List[List[List[int]]], bounds: Tuple[int, int, int, int],
                          img_width: int, img_height: int, stroke_color: str, stroke_width: float = 2,
                          dashed: bool = False, padding: int = MAP_PADDING) -> str:
    """Create SVG path element from path segments."""
    if not segments:
        return ""
    
    path_data = []
    for segment in segments:
        if len(segment) < 2:
            continue
        
        # Convert first point and move to it
        pixel_x, pixel_y = coord_to_pixel(segment[0][0], segment[0][1], bounds, img_width, img_height, padding)
        path_data.append(f"M {pixel_x} {pixel_y}")
        prev_pixel = (pixel_x, pixel_y)
        
        # Draw lines to subsequent points, skipping consecutive duplicates
        for point in segment[1:]:
            pixel_x, pixel_y = coord_to_pixel(point[0], point[1], bounds, img_width, img_height, padding)
            # Only add if this pixel position is different from the previous one
            if (pixel_x, pixel_y) != prev_pixel:
                path_data.append(f"L {pixel_x} {pixel_y}")
                prev_pixel = (pixel_x, pixel_y)
    
    path_str = " ".join(path_data)
    dash_attr = ' stroke-dasharray="10,5"' if dashed else ''
    return (
        f'<path d="{path_str}" stroke="{stroke_color}" stroke-width="{stroke_width}"'
        f'{dash_attr} fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
    )


def svg_polygon(points: List[List[int]], bounds: Tuple[int, int, int, int], 
               img_width: int, img_height: int, fill_color: str, stroke_color: str,
               padding: int = MAP_PADDING) -> str:
    """Create SVG polygon element."""
    if len(points) < 3:
        return ""
    
    # Convert coordinates to pixels
    pixel_points = []
    for point in points:
        pixel_x, pixel_y = coord_to_pixel(point[0], point[1], bounds, img_width, img_height, padding)
        pixel_points.append(f"{pixel_x},{pixel_y}")
    
    points_str = " ".join(pixel_points)
    return (
        f'<polygon points="{points_str}" fill="{fill_color}" stroke="{stroke_color}" '
        f'stroke-linejoin="round"/>'
    )


def svg_circle(x: int, y: int, bounds: Tuple[int, int, int, int], 
              img_width: int, img_height: int, radius: int, fill_color: str, stroke_color: str,
              padding: int = MAP_PADDING) -> str:
    """Create SVG circle element."""
    pixel_x, pixel_y = coord_to_pixel(x, y, bounds, img_width, img_height, padding)
    return f'<circle cx="{pixel_x}" cy="{pixel_y}" r="{radius}" fill="{fill_color}" stroke="{stroke_color}"/>'


def svg_dashed_path(points: List[List[int]], bounds: Tuple[int, int, int, int], 
                   img_width: int, img_height: int, stroke_color: str, stroke_width: float = 2,
                   padding: int = MAP_PADDING) -> str:
    """Create SVG dashed path for trajectories."""
    if len(points) < 2:
        return ""
    
    # Convert first point and move to it
    pixel_x, pixel_y = coord_to_pixel(points[0][0], points[0][1], bounds, img_width, img_height, padding)
    path_data = [f"M {pixel_x} {pixel_y}"]
    
    # Draw lines to subsequent points
    for point in points[1:]:
        pixel_x, pixel_y = coord_to_pixel(point[0], point[1], bounds, img_width, img_height, padding)
        path_data.append(f"L {pixel_x} {pixel_y}")
    
    path_str = " ".join(path_data)
    return (
        f'<path d="{path_str}" stroke="{stroke_color}" stroke-width="{stroke_width}" '
        f'stroke-dasharray="10,5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
    )


def svg_text_with_background(text: str, x: int, y: int, font_size: int = 12, 
                            text_color: str = '#000000', bg_color: str = '#ffffff', 
                            padding: int = 5) -> str:
    """Create SVG text with background rectangle."""
    lines = text.split('\n')
    max_width = max(len(line) for line in lines) * font_size * 0.6
    total_height = len(lines) * (font_size + 2)
    
    rect = (
        f'<rect x="{x - padding}" y="{y - padding}" width="{max_width + 2*padding}" '
        f'height="{total_height + 2*padding}" rx="10" fill="{bg_color}" '
        f'stroke="{COLORS_SVG["card_stroke"]}"/>'
    )
    
    text_elements = []
    for i, line in enumerate(lines):
        line_y = y + font_size + i * (font_size + 2)
        text_elements.append(
            f'<text x="{x}" y="{line_y}" font-family="{_FONT}" font-size="{font_size}" '
            f'fill="{text_color}">{line}</text>'
        )
    
    return f'<g>{rect}{"".join(text_elements)}</g>'


def finish_svg_document(svg_lines: List[str]) -> str:
    """Close the SVG document and return as string."""
    svg_lines.append('</svg>')
    return '\n'.join(svg_lines)


def _svg_defs() -> List[str]:
    """Shared filters and grass hatch used by the garden map."""
    return [
        '<defs>',
        '<filter id="lawnShadow" x="-10%" y="-10%" width="120%" height="120%">',
        '<feDropShadow dx="1.4" dy="2.6" stdDeviation="3.2" flood-color="#243028" flood-opacity="0.20"/>',
        '</filter>',
        '<pattern id="grassHatch" width="10" height="10" patternUnits="userSpaceOnUse">',
        '<path d="M-1 1 L1 -1 M0 10 L10 0 M9 11 L11 9" stroke="#3f7d45" stroke-width="0.55" opacity="0.16"/>',
        '</pattern>',
        '</defs>',
    ]


def svg_dock_marker(x: int, y: int, bounds: Tuple[int, int, int, int],
                    img_width: int, img_height: int, padding: int = MAP_PADDING) -> str:
    """Charging-station glyph at the dock coordinates."""
    px, py = coord_to_pixel(x, y, bounds, img_width, img_height, padding)
    return (
        f'<g transform="translate({px},{py})">'
        f'<rect x="-10" y="-5" width="20" height="14" rx="3" fill="#2a322e" stroke="#eef2ec"/>'
        f'<rect x="-6" y="-1" width="3" height="6" rx="1" fill="#7ed69c"/>'
        f'<rect x="3" y="-1" width="3" height="6" rx="1" fill="#7ed69c"/>'
        f'<polygon points="0,-12 -9,-2 9,-2" fill="#2a322e"/>'
        f'</g>'
    )


def svg_mower_marker(x: int, y: int, bounds: Tuple[int, int, int, int],
                     img_width: int, img_height: int, padding: int = MAP_PADDING,
                     live: bool = False) -> str:
    """White-ringed mower position instead of a raw red dot."""
    px, py = coord_to_pixel(x, y, bounds, img_width, img_height, padding)
    core = COLORS_SVG['live_path'] if live else COLORS_SVG['current_position']
    return (
        f'<g transform="translate({px},{py})">'
        f'<circle cx="1" cy="3" r="10" fill="#1a201c" opacity="0.16"/>'
        f'<circle cx="0" cy="0" r="8.5" fill="#ffffff" stroke="#243028" stroke-width="1.4"/>'
        f'<circle cx="0" cy="0" r="5" fill="{core}"/>'
        f'</g>'
    )



def _scale_map_data(data: Dict[str, Any], factor: int = 10) -> Dict[str, Any]:
    """Scale all coordinate points in map data by the given factor.

    Historical ali_dreame JSON files store coordinates in decimeters while the
    internal coordinate system (batch API, pose coverage) uses centimeters.
    """
    def scale_points(points: list) -> list:
        return [
            p if not isinstance(p, list) or len(p) < 2 or (p[0] == 2147483647 and p[1] == 2147483647)
            else [p[0] * factor, p[1] * factor]
            for p in points
        ]

    result = dict(data)

    if "map" in result:
        scaled_maps = []
        for item in result["map"]:
            scaled_item = dict(item)
            if "data" in scaled_item:
                scaled_item["data"] = scale_points(scaled_item["data"])
            if "track" in scaled_item:
                scaled_item["track"] = scale_points(scaled_item["track"])
            scaled_maps.append(scaled_item)
        result["map"] = scaled_maps

    if "obstacle" in result:
        scaled_obs = []
        for obs in result["obstacle"]:
            scaled_obs.append({**obs, "data": scale_points(obs.get("data", []))})
        result["obstacle"] = scaled_obs

    if "trajectory" in result:
        scaled_traj = []
        for traj in result["trajectory"]:
            scaled_traj.append({**traj, "data": scale_points(traj.get("data", []))})
        result["trajectory"] = scaled_traj

    # Scale dock position [x, y, heading] — only x and y
    if "dock" in result:
        dock = result["dock"]
        if isinstance(dock, list) and len(dock) >= 2:
            result["dock"] = [dock[0] * factor, dock[1] * factor] + dock[2:]

    return result


def generate_svg_map_image(data: Dict[str, Any], historical_file_path: str | None, coordinator, rotation: int,
                           live_coordinates: List[List[int]] | None = None,
                           show_title: bool = True, show_legend: bool = True,
                           padding: int = MAP_PADDING) -> bytes:
    """Generate map image in SVG format from map data.

    Args:
        data: Map data dictionary
        historical_file_path: Path to historical map file or None for current map
        coordinator: Coordinator instance
        rotation: Rotation angle in degrees (0, 90, 180, or 270) - required
        live_coordinates: Optional list of [x, y] coordinate pairs (in map units) for live overlay
        show_title: Whether to render the map title text
        show_legend: Whether to render the color legend
        padding: Padding around the map content in pixels (default: 50)
    """

    # Historical files use decimeter coordinates; scale to centimeters to match
    # the internal coordinate system (batch API / pose coverage).
    if historical_file_path:
        data = _scale_map_data(data)
    
    # Create SVG document with a soft garden-paper background
    svg_lines = create_svg_document(MAP_IMAGE_WIDTH, MAP_IMAGE_HEIGHT, COLORS_SVG['background'])
    svg_lines.extend(_svg_defs())

    try:
        # Collect all coordinate points for bounds calculation
        all_points = []

        # Plot map data as the main mowing path
        map_items = data.get("map", [])
        # Per-zone data: list of (zone_segments, zone_track_segments, name, type) tuples
        zone_data: List[Tuple[List[List[List[int]]], List[List[List[int]]], str, int]] = []

        if map_items:
            for i, item in enumerate(map_items):
                item_data = item.get("data", [])
                item_track = item.get("track", [])
                item_name = item.get("name", "")
                item_type = item.get("type", 0)

                all_points.extend(item_data)
                if not live_coordinates:
                    all_points.extend(item_track)

                # Parse boundary segments from "data" (split by sentinel)
                zone_segments: List[List[List[int]]] = []
                current_segment: List[List[int]] = []
                for point in item_data:
                    if point[0] == 2147483647 and point[1] == 2147483647:
                        if len(current_segment) > 1:
                            zone_segments.append(current_segment)
                        current_segment = []
                    else:
                        current_segment.append(point)
                if len(current_segment) > 1:
                    zone_segments.append(current_segment)

                # Parse track segments from "track" (split by sentinel)
                zone_track_segments: List[List[List[int]]] = []
                current_track_segment: List[List[int]] = []
                for point in item_track:
                    if point[0] == 2147483647 and point[1] == 2147483647:
                        if len(current_track_segment) > 1:
                            zone_track_segments.append(current_track_segment)
                        current_track_segment = []
                    else:
                        current_track_segment.append(point)
                if len(current_track_segment) > 1:
                    zone_track_segments.append(current_track_segment)

                zone_data.append((zone_segments, zone_track_segments, item_name, item_type))

        # Add obstacle points
        obstacles = data.get("obstacle", [])
        for obstacle in obstacles:
            obstacle_data = obstacle.get("data", [])
            all_points.extend(obstacle_data)

        # Add trajectory points (inter-zone navigation paths)
        trajectories = data.get("trajectory", [])
        for trajectory in trajectories:
            trajectory_data = trajectory.get("data", [])
            all_points.extend(trajectory_data)

        # Add current mower position if available
        mower_position = None
        if not live_coordinates:
            # For historical maps, use dock position from map data (already scaled)
            dock = data.get("dock")
            if historical_file_path and dock and isinstance(dock, list) and len(dock) >= 2:
                mower_position = [int(dock[0]), int(dock[1])]
                all_points.append(mower_position)
            elif hasattr(coordinator.device, 'mower_coordinates') and coordinator.device.mower_coordinates:
                mower_pos = coordinator.device.mower_coordinates
                if mower_pos is not None:
                    mower_position = [int(mower_pos[0]), int(mower_pos[1])]
                    all_points.append(mower_position)

        # Add live coordinates to bounds (already in map units from pose handler)
        if live_coordinates:
            all_points.extend(live_coordinates)

        multi_zone = False
        if not all_points:
            svg_lines.append(
                f'<text x="{MAP_IMAGE_WIDTH // 2}" y="{MAP_IMAGE_HEIGHT // 2}" font-family="{_FONT}" '
                f'font-size="16" fill="{COLORS_SVG["text_color"]}" text-anchor="middle">No map data available</text>'
            )
        else:
            bounds = calculate_bounds(all_points)

            # Start rotation group if rotation is specified
            if rotation in [90, 180, 270]:
                center_x = MAP_IMAGE_WIDTH // 2
                center_y = MAP_IMAGE_HEIGHT // 2
                svg_lines.append(f'<g transform="rotate({rotation}, {center_x}, {center_y})">')

            # 0. Draw inter-zone connection paths (type=1) as dashed grey — behind zone fills
            multi_zone = len([z for z in zone_data if z[3] == 0]) > 1
            for i, (z_segs, _z_tracks, _z_name, z_type) in enumerate(zone_data):
                if z_type != 1:
                    continue
                for seg in z_segs:
                    if len(seg) >= 2:
                        dashed = svg_dashed_path(seg, bounds, MAP_IMAGE_WIDTH, MAP_IMAGE_HEIGHT, COLORS_SVG['trajectory'], 2, padding=padding)
                        if dashed:
                            svg_lines.append(dashed)

            # 1. Draw lawn fills for every type=0 zone (single-zone maps used to be outline-only)
            for i, (z_segs, _z_tracks, _z_name, z_type) in enumerate(zone_data):
                if not z_segs or z_type != 0:
                    continue
                fill_color, outline_color = (
                    ZONE_COLORS[i % len(ZONE_COLORS)] if multi_zone
                    else (_SINGLE_ZONE_FILL, COLORS_SVG['map_boundary'])
                )
                for seg in z_segs:
                    if len(seg) >= 3:
                        poly = svg_polygon(seg, bounds, MAP_IMAGE_WIDTH, MAP_IMAGE_HEIGHT,
                                           fill_color, 'none', padding=padding)
                        if poly:
                            svg_lines.append(poly.replace('/>', ' filter="url(#lawnShadow)"/>'))
                        hatch = svg_polygon(seg, bounds, MAP_IMAGE_WIDTH, MAP_IMAGE_HEIGHT,
                                            'url(#grassHatch)', outline_color, padding=padding)
                        if hatch:
                            svg_lines.append(hatch)

            # 2. Draw zone boundary outlines (skip type=1 inter-zone paths)
            for i, (z_segs, _z_tracks, _z_name, z_type) in enumerate(zone_data):
                if z_segs and z_type == 0:
                    color = ZONE_COLORS[i % len(ZONE_COLORS)][1] if multi_zone else COLORS_SVG['map_boundary']
                    boundary_path = svg_path_from_segments(z_segs, bounds, MAP_IMAGE_WIDTH, MAP_IMAGE_HEIGHT, color, 2.4, padding=padding)
                    if boundary_path:
                        svg_lines.append(boundary_path)

            # 3. Draw mowing tracks per zone (skip in live mode — replaced by live path)
            if not live_coordinates:
                for i, (_z_segs, z_tracks, _z_name, z_type) in enumerate(zone_data):
                    if z_tracks and z_type == 0:
                        track_path = svg_path_from_segments(z_tracks, bounds, MAP_IMAGE_WIDTH, MAP_IMAGE_HEIGHT, COLORS_SVG['mowing_path'], 1.8, padding=padding)
                        if track_path:
                            svg_lines.append(track_path.replace('/>', ' opacity="0.55"/>'))

            # 4. Draw obstacles
            for obstacle in obstacles:
                obstacle_data = obstacle.get("data", [])
                if obstacle_data:
                    obstacle_polygon = svg_polygon(obstacle_data, bounds, MAP_IMAGE_WIDTH, MAP_IMAGE_HEIGHT,
                                                 COLORS_SVG['obstacle_fill'], COLORS_SVG['obstacle'], padding=padding)
                    if obstacle_polygon:
                        svg_lines.append(obstacle_polygon)

            # 5. Draw zone labels
            for i, (z_segs, _z_tracks, z_name, _z_type) in enumerate(zone_data):
                if not z_name or not z_segs:
                    continue
                # Compute centroid from all boundary points in this zone
                all_zone_pts = [pt for seg in z_segs for pt in seg]
                if len(all_zone_pts) < 3:
                    continue
                cx = sum(p[0] for p in all_zone_pts) // len(all_zone_pts)
                cy = sum(p[1] for p in all_zone_pts) // len(all_zone_pts)
                px, py = coord_to_pixel(cx, cy, bounds, MAP_IMAGE_WIDTH, MAP_IMAGE_HEIGHT, padding)
                svg_lines.append(
                    f'<text x="{px}" y="{py}" font-family="{_FONT}" font-size="13" font-weight="600" '
                    f'fill="{ZONE_LABEL_COLOR}" text-anchor="middle" dominant-baseline="central">'
                    f'{html.escape(str(z_name))}</text>'
                )

            # 6. Draw charging station when the map includes a dock
            dock = data.get("dock")
            if isinstance(dock, list) and len(dock) >= 2:
                svg_lines.append(svg_dock_marker(int(dock[0]), int(dock[1]), bounds,
                                                 MAP_IMAGE_WIDTH, MAP_IMAGE_HEIGHT, padding=padding))

            # 7. Draw current mower position (only when not in live mode, and not just the dock)
            if mower_position and not live_coordinates:
                at_dock = (
                    isinstance(dock, list) and len(dock) >= 2
                    and int(dock[0]) == mower_position[0]
                    and int(dock[1]) == mower_position[1]
                )
                if not at_dock:
                    svg_lines.append(svg_mower_marker(mower_position[0], mower_position[1], bounds,
                                                      MAP_IMAGE_WIDTH, MAP_IMAGE_HEIGHT, padding=padding))

            # 8. Draw live tracking overlay (coordinates already in map units)
            if live_coordinates:
                # Filter out sentinel break markers for rendering
                valid_live = [p for p in live_coordinates if p[0] != 2147483647 and p[1] != 2147483647]
                if len(valid_live) > 1:
                    glow = svg_path_from_segments([valid_live], bounds, MAP_IMAGE_WIDTH, MAP_IMAGE_HEIGHT,
                                                  '#b8ffd4', 8, padding=padding)
                    if glow:
                        svg_lines.append(glow.replace('/>', ' opacity="0.45"/>'))
                    live_path = svg_path_from_segments([valid_live], bounds, MAP_IMAGE_WIDTH, MAP_IMAGE_HEIGHT,
                                                      COLORS_SVG['live_path'], 3.4, padding=padding)
                    if live_path:
                        svg_lines.append(live_path)
                    svg_lines.append(svg_circle(valid_live[0][0], valid_live[0][1], bounds,
                                               MAP_IMAGE_WIDTH, MAP_IMAGE_HEIGHT, 5,
                                               COLORS_SVG['start_position'], '#ffffff', padding=padding))
                    svg_lines.append(svg_mower_marker(valid_live[-1][0], valid_live[-1][1], bounds,
                                                      MAP_IMAGE_WIDTH, MAP_IMAGE_HEIGHT, padding=padding, live=True))
                elif len(valid_live) == 1:
                    svg_lines.append(svg_mower_marker(valid_live[0][0], valid_live[0][1], bounds,
                                                      MAP_IMAGE_WIDTH, MAP_IMAGE_HEIGHT, padding=padding, live=True))

            # Close rotation group if it was opened
            if rotation in [90, 180, 270]:
                svg_lines.append('</g>')

        # Draw title (outside rotation group)
        if show_title:
            if live_coordinates:
                title = "Live mowing"
            elif historical_file_path:
                title = data.get("map_name") or "Previous session"
            else:
                title = data.get("map_name") or "Garden map"
            title_width = max(len(title) * 9.2, 140)
            title_x = MAP_IMAGE_WIDTH // 2 - title_width / 2
            svg_lines.append(
                f'<rect x="{title_x}" y="14" width="{title_width}" height="32" rx="16" '
                f'fill="{COLORS_SVG["text_bg"]}" stroke="{COLORS_SVG["card_stroke"]}"/>'
            )
            svg_lines.append(
                f'<text x="{MAP_IMAGE_WIDTH // 2}" y="35" font-family="{_FONT}" font-size="16" '
                f'font-weight="600" fill="{COLORS_SVG["text_color"]}" text-anchor="middle">{html.escape(str(title))}</text>'
            )

        # Add legend in top left
        if show_legend:
            legend_items = []
            has_segments = any(z_segs for z_segs, _, _, _ in zone_data)
            has_tracks = any(z_tracks for _, z_tracks, _, _ in zone_data)
            if has_segments:
                legend_items.append(("Lawn", ZONE_COLORS[0][0] if multi_zone else _SINGLE_ZONE_FILL))
            if has_tracks and not live_coordinates:
                legend_items.append(("Mow path", COLORS_SVG['mowing_path']))
            if obstacles:
                legend_items.append(("Obstacle", COLORS_SVG['obstacle']))
            has_inter_zone = any(z_type == 1 for _, _, _, z_type in zone_data)
            if has_inter_zone or trajectories:
                legend_items.append(("Link path", COLORS_SVG['trajectory']))
            dock = data.get("dock")
            if isinstance(dock, list) and len(dock) >= 2:
                legend_items.append(("Dock", "#2a322e"))
            if live_coordinates:
                if len(live_coordinates) > 1:
                    legend_items.append(("Live path", COLORS_SVG['live_path']))
                legend_items.append(("Mower", COLORS_SVG['current_position']))
            elif mower_position:
                legend_items.append(("Mower", COLORS_SVG['current_position']))

            if legend_items:
                legend_x = 18
                legend_y = 58
                card_h = 16 + len(legend_items) * 22
                svg_lines.append(
                    f'<rect x="{legend_x}" y="{legend_y}" width="132" height="{card_h}" rx="10" '
                    f'fill="{COLORS_SVG["text_bg"]}" stroke="{COLORS_SVG["card_stroke"]}"/>'
                )
                for i, (label, color) in enumerate(legend_items):
                    y_pos = legend_y + 12 + i * 22
                    svg_lines.append(
                        f'<rect x="{legend_x + 12}" y="{y_pos}" width="14" height="10" rx="3" fill="{color}"/>'
                    )
                    svg_lines.append(
                        f'<text x="{legend_x + 32}" y="{y_pos + 9}" font-family="{_FONT}" '
                        f'font-size="11" fill="{COLORS_SVG["text_color"]}">{label}</text>'
                    )

        # Add status overlay
        if live_coordinates:
            # Calculate live status info (coordinates are already in map units)
            total_distance: float = 0.0
            valid_live_for_dist = [p for p in live_coordinates if p[0] != 2147483647 and p[1] != 2147483647]
            if len(valid_live_for_dist) > 1:
                for i in range(1, len(valid_live_for_dist)):
                    prev = valid_live_for_dist[i-1]
                    curr = valid_live_for_dist[i]
                    dx = curr[0] - prev[0]
                    dy = curr[1] - prev[1]
                    total_distance += (dx**2 + dy**2) ** 0.5
                total_distance = total_distance / 1000  # Convert map units to meters

            progress_info = ""
            if hasattr(coordinator.device, '_pose_coverage_handler'):
                handler = coordinator.device._pose_coverage_handler
                if handler.progress_percent is not None:
                    progress_info = f"Progress: {handler.progress_percent:.1f}%"
                if handler.current_area_sqm is not None:
                    progress_info += f" | Area: {handler.current_area_sqm:.1f}m²"

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            status_lines = [
                "Live session",
                f"Tracking: {len(live_coordinates)} coordinates",
                f"Distance: {total_distance:.1f}m",
                progress_info,
                f"Updated: {timestamp}"
            ]
            filtered_lines = [line for line in status_lines if line.strip()]
            status_text = "\n".join(filtered_lines)
            status_bg = svg_text_with_background(status_text, 18, MAP_IMAGE_HEIGHT - 96, 11,
                                                 COLORS_SVG['text_color'], COLORS_SVG['text_bg'])
            svg_lines.append(status_bg)
        else:
            # Add timestamp from map data (use 'start' timestamp if available)
            start_timestamp = data.get("start")
            if start_timestamp:
                from datetime import timezone
                timestamp = datetime.fromtimestamp(start_timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                timestamp_text = f"Started: {timestamp}"
            else:
                timestamp_text = "No time information"
            timestamp_bg = svg_text_with_background(timestamp_text, 18, MAP_IMAGE_HEIGHT - 28, 11,
                                                  COLORS_SVG['muted_text'], COLORS_SVG['text_bg'], 8)
            svg_lines.append(timestamp_bg)

    except Exception as ex:
        # Create error message
        _LOGGER.error("Error generating map SVG: %s", ex, exc_info=True)
        error_text = f"Error generating map: {str(ex)}"
        svg_lines.append(
            f'<text x="{MAP_IMAGE_WIDTH // 2}" y="{MAP_IMAGE_HEIGHT // 2}" font-family="{_FONT}" '
            f'font-size="14" fill="{COLORS_SVG["current_position"]}" text-anchor="middle">{error_text}</text>'
        )

    # Complete SVG document and return as bytes
    svg_content = finish_svg_document(svg_lines)
    result_bytes = svg_content.encode('utf-8')
    return result_bytes
