"""
Generate stroke guide paths from Schoolroom font glyph outlines.

Each glyph contour is split into segments. Short segments (<100 font units)
are stroke ends/caps and are excluded. The remaining long segments become
stroke guide paths.
"""

from fontTools.ttLib import TTFont
import numpy as np
import math
import os

FONT_PATH = os.path.join(os.path.dirname(__file__), "Schoolroom.ttf")
MIN_SEG_LEN = 100  # font units; segments shorter than this are stroke caps

font = TTFont(FONT_PATH)
glyf = font['glyf']
cmap = font.getBestCmap()
hmtx = font['hmtx']
os2 = font['OS/2']
cap = os2.sCapHeight


def sample_contour(coords, flags, start, end, step=4):
    """Sample points along a TrueType contour."""
    n = end - start + 1
    expanded = []
    for i in range(n):
        idx = start + i
        p = np.array(coords[idx], dtype=float)
        on = flags[idx] & 1
        expanded.append((p, on))
    # Insert implied on-curve points between consecutive off-curve points
    full = []
    for i in range(len(expanded)):
        p, on = expanded[i]
        full.append((p, on))
        if not on:
            next_i = (i + 1) % len(expanded)
            p_next, on_next = expanded[next_i]
            if not on_next:
                full.append(((p + p_next) / 2, 1))
    # Evaluate into dense point list
    pts = []
    n2 = len(full)
    i = 0
    while i < n2:
        p0, on0 = full[i]
        if on0:
            next_i = (i + 1) % n2
            p1, on1 = full[next_i]
            if on1:
                seg_len = np.linalg.norm(p1 - p0)
                nsteps = max(1, int(seg_len / step))
                for t in np.linspace(0, 1, nsteps, endpoint=False):
                    pts.append(p0 + t * (p1 - p0))
                i += 1
            else:
                next2_i = (i + 2) % n2
                p2, _ = full[next2_i]
                seg_len = np.linalg.norm(p1 - p0) + np.linalg.norm(p2 - p1)
                nsteps = max(2, int(seg_len / step))
                for t in np.linspace(0, 1, nsteps, endpoint=False):
                    pts.append((1-t)**2 * p0 + 2*(1-t)*t * p1 + t**2 * p2)
                i += 2
        else:
            i += 1
    return pts


def contour_length(pts):
    """Total arc length of a point list."""
    total = 0
    for i in range(1, len(pts)):
        total += np.linalg.norm(pts[i] - pts[i-1])
    return total


def process_char(char):
    """Extract outline segments for a character, excluding short caps.

    1. Sample entire contour densely
    2. Find on-curve control points and measure edges between them
    3. Short edges (<MIN_SEG_LEN) are stroke caps — mark those sample regions
    4. Remaining long runs become stroke outline segments
    """
    gn = cmap.get(ord(char))
    if gn is None:
        return None
    g = glyf[gn]
    if g.numberOfContours <= 0:
        return None

    adv = hmtx[gn][0]
    w = round(adv / cap, 2)
    raw_coords = g.coordinates
    flags = g.flags
    ends = g.endPtsOfContours
    contour_starts = [0] + [e + 1 for e in ends[:-1]]

    all_strokes = []

    for c_start, c_end in zip(contour_starts, ends):
        n_pts = c_end - c_start + 1
        if n_pts < 3:
            continue

        # Sample the full contour densely
        dense = sample_contour(raw_coords, flags, c_start, c_end, step=1)
        if len(dense) < 4:
            continue
        dense = [np.array(p) for p in dense]

        # Get on-curve points and measure edges between them
        on_curve_positions = []  # positions in font units
        for i in range(n_pts):
            idx = c_start + i
            if flags[idx] & 1:
                on_curve_positions.append(np.array(raw_coords[idx], dtype=float))

        if len(on_curve_positions) < 2:
            # No corners, whole contour is one stroke
            total = contour_length(dense)
            if total >= MIN_SEG_LEN:
                all_strokes.append(normalize_points(dense))
            continue

        # Measure edge lengths between consecutive on-curve points
        edge_lengths = []
        for i in range(len(on_curve_positions)):
            p1 = on_curve_positions[i]
            p2 = on_curve_positions[(i + 1) % len(on_curve_positions)]
            edge_lengths.append(np.linalg.norm(p2 - p1))

        # Find which on-curve points bound short (cap) edges
        cap_points = set()  # indices into on_curve_positions
        for i, length in enumerate(edge_lengths):
            if length < MIN_SEG_LEN:
                cap_points.add(i)
                cap_points.add((i + 1) % len(on_curve_positions))

        if not cap_points:
            # No caps — whole contour is one stroke
            all_strokes.append(normalize_points(dense))
            continue

        # Map each on-curve point to nearest index in dense array
        on_curve_dense_idx = []
        for oc in on_curve_positions:
            best_i = 0
            best_d = float('inf')
            for i, dp in enumerate(dense):
                d = np.linalg.norm(dp - oc)
                if d < best_d:
                    best_d = d
                    best_i = i
            on_curve_dense_idx.append(best_i)

        # Mark dense points that fall within cap edges
        n_dense = len(dense)
        is_cap = [False] * n_dense
        for i, length in enumerate(edge_lengths):
            if length < MIN_SEG_LEN:
                di_start = on_curve_dense_idx[i]
                di_end = on_curve_dense_idx[(i + 1) % len(on_curve_positions)]
                # Mark from di_start to di_end (wrapping)
                if di_end >= di_start:
                    for j in range(di_start, di_end + 1):
                        is_cap[j % n_dense] = True
                else:
                    for j in range(di_start, n_dense):
                        is_cap[j] = True
                    for j in range(0, di_end + 1):
                        is_cap[j] = True

        # Split dense array at cap regions
        # Find first cap point to start
        first_cap = None
        for i in range(n_dense):
            if is_cap[i]:
                first_cap = i
                break

        if first_cap is None:
            all_strokes.append(normalize_points(dense))
            continue

        segments = []
        seg = []
        for j in range(n_dense):
            idx = (first_cap + j) % n_dense
            if is_cap[idx]:
                if seg:
                    segments.append(seg)
                    seg = []
            else:
                seg.append(dense[idx])
        if seg:
            segments.append(seg)

        for seg in segments:
            if len(seg) < 3:
                continue
            length = contour_length(seg)
            if length < MIN_SEG_LEN:
                continue
            all_strokes.append(normalize_points(seg))

    if not all_strokes:
        return None

    # Build stroke data
    strokes = []
    for seg in all_strokes:
        simplified = simplify_rdp(np.array(seg), tolerance=0.008)
        if len(simplified) < 2:
            continue
        d = points_to_svg_path(simplified)
        start_pt = [round(float(simplified[0][0]), 3), round(float(simplified[0][1]), 3)]
        angle = compute_angle(simplified)
        strokes.append({
            'd': d,
            'start': start_pt,
            'angle': angle,
        })

    # Sort by stroke order: top-to-bottom, left-to-right
    strokes.sort(key=lambda s: (
        round(s['start'][1] * 3) / 3,
        s['start'][0],
    ))

    return {'w': w, 'strokes': strokes}


def normalize_points(pts):
    """Convert from font units to normalized coords (x/cap, y flipped)."""
    return [[p[0] / cap, 1.0 - p[1] / cap] for p in pts]


def simplify_rdp(points, tolerance=0.008):
    """Ramer-Douglas-Peucker simplification."""
    if len(points) <= 2:
        return points
    points = np.array(points)
    start = points[0]
    end = points[-1]
    line_vec = end - start
    line_len = np.linalg.norm(line_vec)
    if line_len < 1e-10:
        return np.array([start, end])
    line_unit = line_vec / line_len
    diffs = points - start
    dists = np.abs(diffs[:, 0] * line_unit[1] - diffs[:, 1] * line_unit[0])
    max_idx = np.argmax(dists)
    max_dist = dists[max_idx]
    if max_dist > tolerance:
        left = simplify_rdp(points[:max_idx + 1], tolerance)
        right = simplify_rdp(points[max_idx:], tolerance)
        return np.vstack([left[:-1], right])
    else:
        return np.array([start, end])


def points_to_svg_path(points):
    """Convert points to SVG path with L segments."""
    if len(points) < 2:
        return ""
    d = f"M {points[0][0]:.3f},{points[0][1]:.3f}"
    for i in range(1, len(points)):
        d += f" L {points[i][0]:.3f},{points[i][1]:.3f}"
    return d


def compute_angle(points):
    """Compute initial stroke direction angle in degrees."""
    if len(points) < 2:
        return 90
    p0 = np.array(points[0])
    ahead = min(len(points) - 1, max(1, len(points) // 4))
    p1 = np.array(points[ahead])
    dx = p1[0] - p0[0]
    dy = p1[1] - p0[1]
    return round(math.degrees(math.atan2(dy, dx)))


def format_js(all_data):
    """Format as JavaScript STROKE_DATA block."""
    lines = []
    lines.append("    // Stroke guidance data for Schoolroom font — auto-generated from outlines")
    lines.append("    // Coordinates: x in [0, width], y: 0=cap top, 1=baseline")
    lines.append("    // Use stroke_editor.html to refine paths and stroke order")
    lines.append("    const STROKE_DATA = {")

    for char in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz':
        data = all_data.get(char)
        if data is None:
            gn = cmap.get(ord(char))
            w = round(hmtx[gn][0] / cap, 2) if gn else 0.5
            lines.append(f"      '{char}': {{ w: {w}, strokes: [] }},")
            continue

        strokes_parts = []
        for s in data['strokes']:
            strokes_parts.append(
                f"        {{ d: '{s['d']}', start: [{s['start'][0]}, {s['start'][1]}], angle: {s['angle']} }}"
            )
        strokes_str = ",\n".join(strokes_parts)
        lines.append(f"      '{char}': {{ w: {data['w']}, strokes: [")
        lines.append(strokes_str)
        lines.append("      ]},")

    lines.append("    };")
    return "\n".join(lines)


def main():
    print(f"Font: {FONT_PATH}")
    print(f"Cap height: {cap}, Min segment length: {MIN_SEG_LEN}")

    all_data = {}
    for char in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz':
        print(f"  {char}...", end=" ", flush=True)
        result = process_char(char)
        if result:
            print(f"w={result['w']}, {len(result['strokes'])} strokes")
            all_data[char] = result
        else:
            print("FAILED")

    js = format_js(all_data)
    out_path = os.path.join(os.path.dirname(__file__), "schoolroom_strokes.js")
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(js)

    print(f"\nWritten to {out_path}")
    print(f"Generated: {len(all_data)}/52 letters")


if __name__ == '__main__':
    main()
