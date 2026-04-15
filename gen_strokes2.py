"""
Generate stroke centerlines by sampling the center of each stroke on a grid.

For each grid position:
1. At a given x, find all vertical runs (top/bottom pairs) of ink
2. For each run, compute y_center = (top + bottom) / 2
3. At that y_center, find the horizontal run containing x, get x_center = (left + right) / 2
4. (x_center, y_center) is a true stroke center point

Then cluster the center points into strokes and fit paths.
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont
import math
import os
import json

RENDER_SIZE = 800  # large for precision

def load_font():
    path = os.path.join(os.path.dirname(__file__), "Andika-Regular.ttf")
    if not os.path.exists(path):
        import urllib.request
        url = "https://github.com/google/fonts/raw/main/ofl/andika/Andika-Regular.ttf"
        urllib.request.urlretrieve(url, path)
    return path

def render_char(font_path, char, size):
    """Render character and return binary array + baseline position."""
    font = ImageFont.truetype(font_path, size)
    ascent, descent = font.getmetrics()

    canvas_w = size * 3
    canvas_h = size * 3
    img = Image.new('L', (canvas_w, canvas_h), 0)
    draw = ImageDraw.Draw(img)

    origin_x = size
    origin_y = size
    draw.text((origin_x, origin_y), char, font=font, fill=255)

    arr = np.array(img)
    baseline = origin_y + ascent

    return arr, baseline, font.getlength(char)

def find_ink_runs(line, threshold=80):
    """Find runs of ink pixels in a 1D array.
    Returns list of (start, end) pairs."""
    in_ink = False
    runs = []
    start = 0
    for i, v in enumerate(line):
        if v > threshold and not in_ink:
            start = i
            in_ink = True
        elif v <= threshold and in_ink:
            runs.append((start, i - 1))
            in_ink = False
    if in_ink:
        runs.append((start, len(line) - 1))
    return runs

def find_stroke_centers(arr, threshold=80):
    """Find stroke center points by grid sampling.

    For each x, find vertical ink runs.
    For each run center y, find the horizontal run containing x.
    Average to get true center point.
    """
    h, w = arr.shape
    centers = []

    # Sample every 2 pixels for speed
    step = 2

    for x in range(0, w, step):
        col = arr[:, x]
        v_runs = find_ink_runs(col, threshold)

        for v_start, v_end in v_runs:
            y_center = (v_start + v_end) / 2.0

            # At this y, find horizontal run containing x
            y_int = int(round(y_center))
            if y_int < 0 or y_int >= h:
                continue

            row = arr[y_int, :]
            h_runs = find_ink_runs(row, threshold)

            # Find which horizontal run contains x
            for h_start, h_end in h_runs:
                if h_start <= x <= h_end:
                    x_center = (h_start + h_end) / 2.0
                    # Refine: at x_center, re-find vertical center
                    x_int = int(round(x_center))
                    if 0 <= x_int < w:
                        col2 = arr[:, x_int]
                        v_runs2 = find_ink_runs(col2, threshold)
                        # Find the vertical run closest to y_center
                        best_run = None
                        best_dist = float('inf')
                        for vs, ve in v_runs2:
                            vc = (vs + ve) / 2
                            d = abs(vc - y_center)
                            if d < best_dist:
                                best_dist = d
                                best_run = (vs, ve)
                        if best_run:
                            y_center2 = (best_run[0] + best_run[1]) / 2.0
                            centers.append((x_center, y_center2))
                    else:
                        centers.append((x_center, y_center))
                    break

    return np.array(centers) if centers else np.empty((0, 2))

def cluster_stroke_points(centers, min_dist=8):
    """Cluster center points into separate strokes using connected components."""
    if len(centers) == 0:
        return []

    from scipy.spatial import KDTree

    tree = KDTree(centers)
    visited = set()
    clusters = []

    for i in range(len(centers)):
        if i in visited:
            continue

        # BFS to find connected points
        cluster = []
        queue = [i]
        visited.add(i)

        while queue:
            idx = queue.pop(0)
            cluster.append(idx)
            neighbors = tree.query_ball_point(centers[idx], min_dist)
            for n in neighbors:
                if n not in visited:
                    visited.add(n)
                    queue.append(n)

        clusters.append(centers[np.array(cluster)])

    return clusters

def order_stroke_points(points):
    """Order points along the stroke path by nearest-neighbor walk."""
    if len(points) <= 2:
        return points

    # Start from the point with smallest y (topmost), or leftmost if tie
    start_idx = 0
    for i in range(len(points)):
        if points[i][1] < points[start_idx][1] - 2:
            start_idx = i
        elif abs(points[i][1] - points[start_idx][1]) <= 2 and points[i][0] < points[start_idx][0]:
            start_idx = i

    ordered = [points[start_idx]]
    remaining = list(range(len(points)))
    remaining.remove(start_idx)

    while remaining:
        last = ordered[-1]
        best_idx = None
        best_dist = float('inf')
        for idx in remaining:
            d = np.linalg.norm(points[idx] - last)
            if d < best_dist:
                best_dist = d
                best_idx = idx
        remaining.remove(best_idx)
        ordered.append(points[best_idx])

    return np.array(ordered)

def simplify_points(points, tolerance=2.0):
    """Ramer-Douglas-Peucker simplification."""
    if len(points) <= 2:
        return points

    start = points[0]
    end = points[-1]
    line_vec = end - start
    line_len = np.linalg.norm(line_vec)

    if line_len < 1e-10:
        return np.array([start, end])

    line_unit = line_vec / line_len
    diffs = points - start
    # Cross product for 2D
    dists = np.abs(diffs[:, 0] * line_unit[1] - diffs[:, 1] * line_unit[0])

    max_idx = np.argmax(dists)
    max_dist = dists[max_idx]

    if max_dist > tolerance:
        left = simplify_points(points[:max_idx + 1], tolerance)
        right = simplify_points(points[max_idx:], tolerance)
        return np.vstack([left[:-1], right])
    else:
        return np.array([start, end])

def points_to_path(points):
    """Convert simplified points to SVG path with lines and curves."""
    if len(points) < 2:
        return ""

    path = f"M {points[0][0]:.2f},{points[0][1]:.2f}"

    if len(points) == 2:
        path += f" L {points[1][0]:.2f},{points[1][1]:.2f}"
        return path

    # Use cubic bezier via Catmull-Rom conversion
    for i in range(1, len(points)):
        if len(points) <= 3 or i == len(points) - 1:
            path += f" L {points[i][0]:.2f},{points[i][1]:.2f}"
        else:
            p0 = points[max(0, i - 1)]
            p1 = points[i]
            p2 = points[min(len(points) - 1, i + 1)]
            p_prev = points[max(0, i - 2)]

            cp1 = p0 + (p1 - p_prev) / 6
            cp2 = p1 - (p2 - p0) / 6

            path += f" C {cp1[0]:.2f},{cp1[1]:.2f} {cp2[0]:.2f},{cp2[1]:.2f} {p1[0]:.2f},{p1[1]:.2f}"

    return path

def compute_angle(points):
    """Compute stroke start angle in degrees."""
    if len(points) < 2:
        return 90
    p0 = points[0]
    # Look ahead a bit for stability
    ahead = min(len(points) - 1, max(1, len(points) // 4))
    p1 = points[ahead]
    dx = p1[0] - p0[0]
    dy = p1[1] - p0[1]
    return round(math.degrees(math.atan2(dy, dx)))

def analyze_char(font_path, char, cap_top, baseline, x_height_top):
    """Analyze one character and return stroke data."""
    arr, bl, char_advance = render_char(font_path, char, RENDER_SIZE)

    # Find ink bounds
    rows = np.any(arr > 80, axis=1)
    cols = np.any(arr > 80, axis=0)
    if not rows.any():
        return None

    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]

    char_width = cmax - cmin

    # Reference heights
    is_lower = char.islower()
    y_top = cap_top  # all letters use cap_top as y=0 reference
    y_range = baseline - cap_top  # pixels from y=0 to y=1

    if y_range <= 0 or char_width <= 0:
        return None

    # Find stroke centers
    centers = find_stroke_centers(arr, threshold=80)
    if len(centers) == 0:
        return None

    # Remove duplicate/near-duplicate points
    if len(centers) > 1:
        from scipy.spatial import KDTree
        tree = KDTree(centers)
        unique_mask = np.ones(len(centers), dtype=bool)
        for i in range(len(centers)):
            if not unique_mask[i]:
                continue
            neighbors = tree.query_ball_point(centers[i], 1.5)
            for n in neighbors:
                if n != i and n > i:
                    unique_mask[n] = False
        centers = centers[unique_mask]

    # Cluster into strokes
    clusters = cluster_stroke_points(centers, min_dist=RENDER_SIZE * 0.025)

    # Filter tiny clusters
    min_points = 5
    clusters = [c for c in clusters if len(c) >= min_points]

    if not clusters:
        return None

    # Process each cluster into a stroke
    strokes = []
    for cluster in clusters:
        ordered = order_stroke_points(cluster)
        simplified = simplify_points(ordered, tolerance=RENDER_SIZE * 0.008)

        # Normalize coordinates
        norm_points = []
        for x, y in simplified:
            nx = (x - cmin) / y_range
            ny = (y - y_top) / y_range
            norm_points.append([round(nx, 2), round(ny, 2)])

        norm_points = np.array(norm_points)

        path = points_to_path(norm_points)
        start = [norm_points[0][0], norm_points[0][1]]
        angle = compute_angle(norm_points)

        strokes.append({
            'd': path,
            'start': [float(start[0]), float(start[1])],
            'angle': int(angle),
        })

    # Sort by stroke order heuristic
    strokes.sort(key=lambda s: (
        round(s['start'][1] * 3) / 3,
        s['start'][0],
    ))

    w = round(char_width / y_range, 2)

    return {
        'w': w,
        'strokes': strokes,
    }

def get_reference_positions(font_path):
    """Get cap top, baseline, x-height positions from rendered H and x."""
    arr_h, bl_h, _ = render_char(font_path, 'H', RENDER_SIZE)
    rows = np.any(arr_h > 80, axis=1)
    cap_top = np.where(rows)[0][0]

    arr_x, bl_x, _ = render_char(font_path, 'x', RENDER_SIZE)
    rows = np.any(arr_x > 80, axis=1)
    x_top = np.where(rows)[0][0]

    return cap_top, bl_h, x_top

def main():
    font_path = load_font()
    print(f"Font: {font_path}")

    cap_top, baseline, x_height_top = get_reference_positions(font_path)
    print(f"cap_top={cap_top}, baseline={baseline}, x_height_top={x_height_top}")
    print(f"Cap height: {baseline - cap_top}px")

    # Just do 'A' for testing
    test_chars = ['A']
    for char in test_chars:
        print(f"\n--- {char} ---")
        result = analyze_char(font_path, char, cap_top, baseline, x_height_top)
        if result:
            print(f"w: {result['w']}")
            print(f"Strokes: {len(result['strokes'])}")
            for i, s in enumerate(result['strokes']):
                print(f"  {i+1}: start={s['start']}, angle={s['angle']}")
                print(f"     d: {s['d'][:80]}...")

            # Format as JS
            print(f"\n      '{char}': {{ w: {result['w']}, strokes: [")
            for s in result['strokes']:
                print(f"        {{ d: '{s['d']}', start: {s['start']}, angle: {s['angle']} }},")
            print(f"      ]}},")
        else:
            print("FAILED")

if __name__ == '__main__':
    main()
