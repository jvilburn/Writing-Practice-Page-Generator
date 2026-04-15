"""Generate centerline dots for all 52 letters using the tangent-perpendicular
opposite-edge-finding method."""

from fontTools.ttLib import TTFont
import numpy as np
import json

font = TTFont('Andika-Regular.ttf')
glyf = font['glyf']
cmap = font.getBestCmap()
hmtx = font['hmtx']
os2 = font['OS/2']
cap = os2.sCapHeight

# Stroke width from I stem (pts 3-4 and 9-10: x=380 to x=570)
expected_sw = 190
tolerance = 0.25
min_sw = expected_sw * (1 - tolerance)
max_sw = expected_sw * (1 + tolerance)
min_edge_dist = expected_sw * 0.35

def sample_contour(coords, flags, start, end, step=2):
    n = end - start + 1
    expanded = []
    for i in range(n):
        idx = start + i
        p = np.array(coords[idx], dtype=float)
        on = flags[idx] & 1
        expanded.append((p, on))
    full = []
    for i in range(len(expanded)):
        p, on = expanded[i]
        full.append((p, on))
        if not on:
            next_i = (i + 1) % len(expanded)
            p_next, on_next = expanded[next_i]
            if not on_next:
                full.append(((p + p_next) / 2, 1))
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
    return np.array(pts) if pts else np.empty((0, 2))

from scipy.spatial import KDTree

def generate_centerline(char):
    gn = cmap.get(ord(char))
    if gn is None:
        return None
    g = glyf[gn]
    if g.numberOfContours <= 0:
        return None

    adv = hmtx[gn][0]
    w = round(adv / cap, 3)
    coords = g.coordinates
    flags = g.flags
    ends = g.endPtsOfContours
    contour_starts = [0] + [e + 1 for e in ends[:-1]]

    all_contour_pts = []
    for start, end_idx in zip(contour_starts, ends):
        pts = sample_contour(coords, flags, start, end_idx, step=2)
        if len(pts) > 0:
            all_contour_pts.append(pts)

    if not all_contour_pts:
        return None

    all_pts = np.vstack(all_contour_pts)
    tree = KDTree(all_pts)

    centerline_raw = []
    for contour_pts in all_contour_pts:
        n = len(contour_pts)
        for i in range(n):
            p = contour_pts[i]
            p_next = contour_pts[(i + 1) % n]
            tangent = p_next - p
            tlen = np.linalg.norm(tangent)
            if tlen < 0.1:
                continue
            tangent /= tlen
            perp = np.array([tangent[1], -tangent[0]])

            for sign in [1, -1]:
                direction = perp * sign
                target = p + direction * expected_sw
                candidates = tree.query_ball_point(target, max_sw - expected_sw + 20)

                best_dist = None
                best_pt = None
                for ci in candidates:
                    cp = all_pts[ci]
                    proj = np.dot(cp - p, direction)
                    if min_sw <= proj <= max_sw:
                        perp_dist = abs(np.dot(cp - p, tangent))
                        if perp_dist < 20:
                            if best_dist is None or abs(proj - expected_sw) < abs(best_dist - expected_sw):
                                best_dist = proj
                                best_pt = cp

                if best_pt is not None:
                    midpoint = (p + best_pt) / 2
                    centerline_raw.append(midpoint)
                    break

    # Filter dots too close to edge
    filtered = []
    for mp in centerline_raw:
        dist, _ = tree.query(mp)
        if dist >= min_edge_dist:
            filtered.append(mp)

    # Normalize and subsample
    points = []
    for p in filtered[::5]:
        nx = round(p[0] / cap, 3)
        ny = round(1.0 - p[1] / cap, 3)
        points.append([nx, ny])

    return {'w': w, 'points': points}

# Generate for all letters
all_data = {}
for char in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz':
    print(f'{char}...', end=' ', flush=True)
    result = generate_centerline(char)
    if result:
        all_data[char] = result
        print(f'{len(result["points"])} pts')
    else:
        print('FAILED')

# Write as JSON
with open('centerline_dots.json', 'w') as f:
    json.dump(all_data, f)

print(f'\nDone. {len(all_data)} letters generated.')
