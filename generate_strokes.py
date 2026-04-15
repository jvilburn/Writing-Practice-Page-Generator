"""
Generate stroke guidance data for Andika font by analyzing glyph centerlines.

Renders each letter at high resolution, skeletonizes to find centerlines,
then converts to SVG path data in the coordinate system used by the app:
  - y=0 is top of cap height (uppercase) or top of ascender (lowercase)
  - y=1 is baseline
  - x is relative to character width
"""

import json
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from skimage.morphology import skeletonize
from skimage import measure
from scipy.ndimage import label
from scipy.spatial.distance import cdist
import math
import os

# Config
FONT_PATH = None  # Will try to find Andika
RENDER_SIZE = 400  # px font size for analysis
CANVAS_PAD = 100   # padding around glyph

def find_andika_font():
    """Try to find Andika font on the system."""
    candidates = [
        # Common Windows paths
        r"C:\Users\johnv\AppData\Local\Microsoft\Windows\Fonts\Andika-Regular.ttf",
        r"C:\Windows\Fonts\Andika-Regular.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p

    # Try to download from Google Fonts API
    import urllib.request
    url = "https://github.com/google/fonts/raw/main/ofl/andika/Andika-Regular.ttf"
    local_path = os.path.join(os.path.dirname(__file__), "Andika-Regular.ttf")
    if not os.path.exists(local_path):
        print(f"Downloading Andika font...")
        urllib.request.urlretrieve(url, local_path)
    return local_path

def render_glyph(font, char, size, pad):
    """Render a single character and return binary image + metrics."""
    canvas_w = size * 2 + pad * 2
    canvas_h = size * 2 + pad * 2
    img = Image.new('L', (canvas_w, canvas_h), 0)
    draw = ImageDraw.Draw(img)

    # Draw the character
    baseline_y = pad + int(size * 1.2)
    draw.text((pad, pad), char, font=font, fill=255)

    arr = np.array(img)

    # Find bounding box of non-zero pixels
    rows = np.any(arr > 30, axis=1)
    cols = np.any(arr > 30, axis=0)
    if not rows.any() or not cols.any():
        return None, None

    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]

    # Get the actual baseline using font metrics
    bbox = font.getbbox(char)
    ascent, descent = font.getmetrics()

    return arr, {
        'rmin': rmin, 'rmax': rmax,
        'cmin': cmin, 'cmax': cmax,
        'ascent': ascent,
        'descent': descent,
        'bbox': bbox,
    }

def get_glyph_metrics(font, char):
    """Get precise glyph metrics using pillow."""
    # Render at known position
    size = RENDER_SIZE
    canvas_w = size * 3
    canvas_h = size * 3

    # Use getbbox for the character
    bbox = font.getbbox(char)
    # bbox = (left, top, right, bottom) relative to origin

    ascent, descent = font.getmetrics()

    # Render to find actual ink bounds
    img = Image.new('L', (canvas_w, canvas_h), 0)
    draw = ImageDraw.Draw(img)
    origin_x = size
    origin_y = size  # This is where the text origin (top-left of bbox) goes
    draw.text((origin_x, origin_y), char, font=font, fill=255)

    arr = np.array(img)
    rows = np.any(arr > 30, axis=1)
    cols = np.any(arr > 30, axis=0)

    if not rows.any():
        return None

    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]

    # The baseline is at origin_y + ascent
    baseline = origin_y + ascent

    return {
        'arr': arr,
        'rmin': int(rmin),
        'rmax': int(rmax),
        'cmin': int(cmin),
        'cmax': int(cmax),
        'baseline': int(baseline),
        'origin_x': origin_x,
        'origin_y': origin_y,
        'ascent': ascent,
        'descent': descent,
        'char_width': font.getlength(char),
    }

def extract_skeleton(arr, threshold=30):
    """Extract skeleton (centerline) from glyph image."""
    binary = arr > threshold
    skeleton = skeletonize(binary)
    return skeleton

def trace_skeleton_paths(skeleton):
    """Trace connected paths through the skeleton.
    Returns list of paths, each path is a list of (row, col) points."""

    # Find all skeleton points
    points = np.argwhere(skeleton)
    if len(points) == 0:
        return []

    # Label connected components
    labeled, num_features = label(skeleton)

    paths = []
    for component_id in range(1, num_features + 1):
        component_points = np.argwhere(labeled == component_id)
        if len(component_points) < 3:
            continue

        # Order points by tracing through the skeleton
        ordered = order_skeleton_points(component_points, skeleton)
        paths.append(ordered)

    return paths

def order_skeleton_points(points, skeleton):
    """Order skeleton points by walking along the skeleton."""
    if len(points) <= 2:
        return points.tolist()

    # Find endpoints (points with only 1 neighbor) or use the topmost point
    neighbors_count = np.zeros(len(points))
    point_set = set(map(tuple, points))

    for i, (r, c) in enumerate(points):
        count = 0
        for dr in [-1, 0, 1]:
            for dc in [-1, 0, 1]:
                if dr == 0 and dc == 0:
                    continue
                if (r + dr, c + dc) in point_set:
                    count += 1
        neighbors_count[i] = count

    # Find endpoints (1 neighbor)
    endpoints = np.where(neighbors_count == 1)[0]

    if len(endpoints) > 0:
        start_idx = endpoints[0]
    else:
        # Use topmost-leftmost point
        start_idx = 0
        for i, (r, c) in enumerate(points):
            if r < points[start_idx][0] or (r == points[start_idx][0] and c < points[start_idx][1]):
                start_idx = i

    # Walk from start point
    ordered = []
    visited = set()
    current = tuple(points[start_idx])

    while current is not None:
        ordered.append(list(current))
        visited.add(current)

        r, c = current
        next_point = None
        # Check 8-connected neighbors
        for dr in [-1, 0, 1]:
            for dc in [-1, 0, 1]:
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if (nr, nc) in point_set and (nr, nc) not in visited:
                    next_point = (nr, nc)
                    break
            if next_point:
                break

        current = next_point

    return ordered

def simplify_path(points, tolerance=3.0):
    """Simplify a path using the Ramer-Douglas-Peucker algorithm."""
    if len(points) <= 2:
        return points

    points = np.array(points, dtype=float)

    # Find the point farthest from the line between first and last
    start = points[0]
    end = points[-1]

    line_vec = end - start
    line_len = np.linalg.norm(line_vec)

    if line_len < 1e-10:
        return [points[0].tolist(), points[-1].tolist()]

    line_unit = line_vec / line_len

    # Distance of each point from the line
    dists = np.abs(np.cross(line_unit, start - points))

    max_idx = np.argmax(dists)
    max_dist = dists[max_idx]

    if max_dist > tolerance:
        left = simplify_path(points[:max_idx + 1].tolist(), tolerance)
        right = simplify_path(points[max_idx:].tolist(), tolerance)
        return left[:-1] + right
    else:
        return [points[0].tolist(), points[-1].tolist()]

def points_to_svg_path(points):
    """Convert a list of points to an SVG path string.
    Uses line segments for straight parts and curves where needed."""
    if len(points) < 2:
        return ""

    # Start with M command
    path = f"M {points[0][0]:.4f},{points[0][1]:.4f}"

    if len(points) == 2:
        path += f" L {points[1][0]:.4f},{points[1][1]:.4f}"
        return path

    # For longer paths, use cubic bezier curves
    # Simple approach: use Catmull-Rom to cubic Bezier conversion
    i = 1
    while i < len(points):
        if i == len(points) - 1:
            path += f" L {points[i][0]:.4f},{points[i][1]:.4f}"
            i += 1
        elif i == len(points) - 2:
            # Two points left, use quadratic or line
            path += f" L {points[i][0]:.4f},{points[i][1]:.4f}"
            path += f" L {points[i+1][0]:.4f},{points[i+1][1]:.4f}"
            i += 2
        else:
            # Use cubic bezier through next few points
            p0 = np.array(points[i-1])
            p1 = np.array(points[i])
            p2 = np.array(points[i+1])
            p3 = np.array(points[min(i+2, len(points)-1)])

            # Catmull-Rom to Bezier control points
            cp1 = p1 + (p2 - p0) / 6
            cp2 = p2 - (p3 - p1) / 6

            path += f" C {cp1[0]:.4f},{cp1[1]:.4f} {cp2[0]:.4f},{cp2[1]:.4f} {p2[0]:.4f},{p2[1]:.4f}"
            i += 1

    return path

def compute_stroke_angle(points):
    """Compute the initial stroke direction angle in degrees."""
    if len(points) < 2:
        return 90

    p0 = np.array(points[0])
    # Use a point a few steps ahead for more stable angle
    ahead = min(len(points) - 1, max(1, len(points) // 5))
    p1 = np.array(points[ahead])

    dx = p1[0] - p0[0]  # x is horizontal
    dy = p1[1] - p0[1]  # y is vertical (down is positive)

    angle = math.degrees(math.atan2(dy, dx))
    return round(angle)

def find_junctions(skeleton):
    """Find junction points in the skeleton (points with 3+ neighbors)."""
    points = np.argwhere(skeleton)
    point_set = set(map(tuple, points))
    junctions = []

    for r, c in points:
        count = 0
        for dr in [-1, 0, 1]:
            for dc in [-1, 0, 1]:
                if dr == 0 and dc == 0:
                    continue
                if (r + dr, c + dc) in point_set:
                    count += 1
        if count >= 3:
            junctions.append((r, c))

    return junctions

def split_at_junctions(skeleton):
    """Split skeleton into separate strokes at junction points."""
    junctions = find_junctions(skeleton)

    if not junctions:
        # No junctions — trace as single path
        return trace_skeleton_paths(skeleton)

    # Remove junction points to split into segments
    modified = skeleton.copy()
    for r, c in junctions:
        modified[r, c] = False

    # Trace the segments
    segments = trace_skeleton_paths(modified)

    # Re-add junction points to nearest segment endpoints
    for jr, jc in junctions:
        for seg in segments:
            if len(seg) == 0:
                continue
            start = seg[0]
            end = seg[-1]

            start_dist = abs(start[0] - jr) + abs(start[1] - jc)
            end_dist = abs(end[0] - jr) + abs(end[1] - jc)

            if start_dist <= 2:
                seg.insert(0, [jr, jc])
            elif end_dist <= 2:
                seg.append([jr, jc])

    return segments

def analyze_letter(font, char, ref_cap_top, ref_baseline):
    """Analyze a single letter and return stroke data."""
    metrics = get_glyph_metrics(font, char)
    if metrics is None:
        return None

    arr = metrics['arr']
    baseline = metrics['baseline']

    # Determine cap top based on reference characters
    # For uppercase, use the ref_cap_top
    # For lowercase, the top varies (ascenders vs x-height)

    is_lower = char.islower()

    # Extract and skeletonize the glyph
    binary = arr > 30
    skeleton = skeletonize(binary)

    # Split at junctions to get individual strokes
    strokes = split_at_junctions(skeleton)

    if not strokes:
        return None

    # Filter out very short strokes (noise)
    min_length = RENDER_SIZE * 0.05
    strokes = [s for s in strokes if len(s) >= max(3, min_length)]

    if not strokes:
        return None

    # Normalize coordinates:
    # x: relative to character width (0 to w_ratio)
    # y: 0 = cap top (or ascender top), 1 = baseline

    char_left = metrics['cmin']
    char_width = metrics['cmax'] - metrics['cmin']

    if char_width <= 0:
        return None

    y_top = ref_cap_top
    y_range = ref_baseline - ref_cap_top  # pixels from top to baseline

    if y_range <= 0:
        return None

    # Width as fraction of height (same coordinate scale as original data)
    w_ratio = char_width / y_range

    normalized_strokes = []
    for stroke_points in strokes:
        norm_points = []
        for r, c in stroke_points:
            nx = (c - char_left) / y_range  # x normalized to same scale as y
            ny = (r - y_top) / y_range       # 0 at top, 1 at baseline
            norm_points.append([nx, ny])

        # Simplify the path
        simplified = simplify_path(norm_points, tolerance=0.015)

        if len(simplified) < 2:
            continue

        # Convert to SVG path (x, y format)
        svg_path = points_to_svg_path(simplified)

        # Compute start point and angle
        start = [round(simplified[0][0], 2), round(simplified[0][1], 2)]
        angle = compute_stroke_angle(simplified)

        normalized_strokes.append({
            'd': svg_path,
            'start': start,
            'angle': angle,
            'num_points': len(simplified),
        })

    # Sort strokes by a heuristic stroke order:
    # Generally top-to-bottom, left-to-right, verticals before horizontals
    normalized_strokes.sort(key=lambda s: (
        round(s['start'][1] * 4) / 4,  # Group by approximate vertical position
        s['start'][0],                   # Then left to right
    ))

    return {
        'w': round(w_ratio, 2),
        'strokes': normalized_strokes,
        'char_width_px': char_width,
    }

def get_reference_metrics(font):
    """Get reference cap height and baseline from 'H' character."""
    metrics = get_glyph_metrics(font, 'H')
    if metrics is None:
        raise ValueError("Cannot measure reference character H")

    return {
        'cap_top': metrics['rmin'],
        'baseline': metrics['baseline'],
        'x_height_top': None,  # Will measure from 'x'
    }

def get_x_height(font):
    """Get x-height reference from 'x' character."""
    metrics = get_glyph_metrics(font, 'x')
    if metrics is None:
        raise ValueError("Cannot measure reference character x")
    return metrics['rmin']

def format_stroke_data(all_data):
    """Format the stroke data as JavaScript for inclusion in index.html."""
    lines = []
    lines.append("    // Stroke guidance data for Andika font — auto-generated from glyph analysis")
    lines.append("    // Coordinates: x in [0, width], y 0=top 1=baseline")
    lines.append("    // Uppercase: y=0 is cap height, y=1 is baseline")
    lines.append("    // Lowercase: y=0.5 is x-height (midline), y=1 is baseline, ascenders to y=0, descenders to y~1.4")
    lines.append("    const STROKE_DATA = {")
    lines.append("      // UPPERCASE")

    for char in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
        data = all_data.get(char)
        if data is None:
            lines.append(f"      // '{char}': could not analyze")
            continue

        strokes_str = []
        for s in data['strokes']:
            d = s['d']
            start = s['start']
            angle = s['angle']
            strokes_str.append(
                f"        {{ d: '{d}', start: [{start[0]}, {start[1]}], angle: {angle} }}"
            )

        lines.append(f"      '{char}': {{ w: {data['w']}, strokes: [")
        lines.append(",\n".join(strokes_str))
        lines.append("      ]},")

    lines.append("      // LOWERCASE")

    for char in 'abcdefghijklmnopqrstuvwxyz':
        data = all_data.get(char)
        if data is None:
            lines.append(f"      // '{char}': could not analyze")
            continue

        strokes_str = []
        for s in data['strokes']:
            d = s['d']
            start = s['start']
            angle = s['angle']
            strokes_str.append(
                f"        {{ d: '{d}', start: [{start[0]}, {start[1]}], angle: {angle} }}"
            )

        lines.append(f"      '{char}': {{ w: {data['w']}, strokes: [")
        lines.append(",\n".join(strokes_str))
        lines.append("      ]},")

    lines.append("    };")
    return "\n".join(lines)

def main():
    font_path = find_andika_font()
    print(f"Using font: {font_path}")

    font = ImageFont.truetype(font_path, RENDER_SIZE)

    # Get reference metrics
    ref = get_reference_metrics(font)
    cap_top = ref['cap_top']
    baseline = ref['baseline']
    x_height_top = get_x_height(font)

    print(f"Reference metrics: cap_top={cap_top}, baseline={baseline}, x_height_top={x_height_top}")
    print(f"Cap height: {baseline - cap_top}px, x-height: {baseline - x_height_top}px")

    all_data = {}

    # Process uppercase
    print("\nProcessing uppercase letters...")
    for char in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
        print(f"  {char}...", end=" ")
        data = analyze_letter(font, char, cap_top, baseline)
        if data:
            print(f"w={data['w']}, {len(data['strokes'])} strokes")
            all_data[char] = data
        else:
            print("FAILED")

    # Process lowercase
    print("\nProcessing lowercase letters...")
    for char in 'abcdefghijklmnopqrstuvwxyz':
        print(f"  {char}...", end=" ")
        data = analyze_letter(font, char, cap_top, baseline)
        if data:
            print(f"w={data['w']}, {len(data['strokes'])} strokes")
            all_data[char] = data
        else:
            print("FAILED")

    # Output
    js_code = format_stroke_data(all_data)

    output_path = os.path.join(os.path.dirname(__file__), "stroke_data.js")
    with open(output_path, 'w') as f:
        f.write(js_code)

    print(f"\nStroke data written to {output_path}")
    print("Copy the STROKE_DATA object into index.html to replace the existing one.")

if __name__ == '__main__':
    main()
