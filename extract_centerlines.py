"""Bootstrap: extract centerlines + width + head shape from each arrow
sub-glyph in SchoolroomGuidance.ttf, write to centerlines.json.

Each arrow is stored as TWO contours:
  - contour 0: the body outline (4 points for a straight arrow, many points
               for a curved arrow). Closed polygon. The closure (last → first)
               is one short edge of the body; somewhere in the middle is the
               other short edge that abuts the arrowhead.
  - contour 1: the arrowhead triangle (3 points).

Algorithm per arrow:
  1. Identify the head-end short edge of the body: the consecutive-point pair
     (body[i], body[i+1]) whose midpoint is closest to the head triangle's
     centroid. Treat the wrap-around pair (body[n-1], body[0]) as the cap-end
     short edge.
  2. Split the body into two long edges:
       top    = body[0..i]
       bottom = body[i+1..n-1]
  3. Pair top points with bottom points by cumulative arc-length parameter.
     Each pair midpoint is a centerline sample.
  4. Add cap midpoint (body[n-1] + body[0]) / 2 as the first sample, head
     midpoint (body[i] + body[i+1]) / 2 as the last sample.
  5. Fit a cubic Bezier to those samples (endpoints fixed).
  6. Width = mean of pair distances across the body.
  7. Head: contour 1 vertices, recorded in a head-relative frame
     (origin = head endpoint, +x = body tangent at head, +y = perpendicular).

Run:
    python extract_centerlines.py             # writes centerlines.json
    python extract_centerlines.py --preview   # also writes preview/*.png
"""
import argparse
import json
import math
import os
from fontTools.ttLib import TTFont

ROOT = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(ROOT, 'SchoolroomGuidance.ttf')
CENTERLINES_PATH = os.path.join(ROOT, 'centerlines.json')
PREVIEW_DIR = os.path.join(ROOT, 'preview')


def get_arrow_glyph_names(font):
    return sorted([n for n in font['glyf'].keys() if n.endswith('.arrow')])


def get_contours(glyf, glyph_name):
    """Return list of contours; each is a list of (x, y) tuples (on-curve only
    in this font — flags are all 1 for arrows)."""
    g = glyf[glyph_name]
    if g.numberOfContours <= 0:
        return []
    ends = g.endPtsOfContours
    starts = [0] + [e + 1 for e in ends[:-1]]
    contours = []
    for s, e in zip(starts, ends):
        contour = []
        for i in range(s, e + 1):
            x, y = g.coordinates[i]
            contour.append((float(x), float(y)))
        contours.append(contour)
    return contours


def centroid(points):
    n = len(points)
    return (sum(p[0] for p in points) / n, sum(p[1] for p in points) / n)


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def midpoint(a, b):
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


WIDTH_MIN = 10
WIDTH_MAX = 18


def find_head_edge(body, head_centroid):
    """Return the index i such that (body[i], body[i+1]) is the body's
    head-end short edge. Excludes the wrap-around pair (n-1, 0), which is
    the cap-end short edge.

    The body has two short edges (cap and head end) at roughly the stroke
    width and many longer edges along the body's curving sides. Among
    consecutive-point pairs whose distance falls in the stroke-width band,
    pick the one whose midpoint is closest to the head triangle's
    centroid. Falls back to the shortest pair if none are in band.
    """
    n = len(body)
    in_band = [i for i in range(n - 1)
               if WIDTH_MIN <= dist(body[i], body[i + 1]) <= WIDTH_MAX]
    if in_band:
        return min(in_band,
                   key=lambda i: dist(midpoint(body[i], body[i + 1]),
                                      head_centroid))
    # Fallback: shortest non-closure pair.
    return min(range(n - 1), key=lambda i: dist(body[i], body[i + 1]))


def pair_edges_by_arclength(top, bottom, n_pairs):
    """top and bottom are sequences of points along the body's two long edges.
    Returns a list of (top_pt, bot_pt) pairs sampled at uniform cumulative
    arc-length along each edge, with len == n_pairs (including endpoints).
    """
    def cumulative(pts):
        cum = [0.0]
        for i in range(1, len(pts)):
            cum.append(cum[-1] + dist(pts[i - 1], pts[i]))
        total = cum[-1] or 1.0
        return [c / total for c in cum]

    def sample_at(pts, fracs, target):
        # Linear interpolation by fraction along the polyline.
        for i in range(1, len(fracs)):
            if fracs[i] >= target or i == len(fracs) - 1:
                if fracs[i] == fracs[i - 1]:
                    return pts[i]
                t = (target - fracs[i - 1]) / (fracs[i] - fracs[i - 1])
                x = pts[i - 1][0] + t * (pts[i][0] - pts[i - 1][0])
                y = pts[i - 1][1] + t * (pts[i][1] - pts[i - 1][1])
                return (x, y)
        return pts[-1]

    tf = cumulative(top)
    bf = cumulative(bottom)
    pairs = []
    for k in range(n_pairs):
        target = k / (n_pairs - 1) if n_pairs > 1 else 0.0
        pairs.append((sample_at(top, tf, target), sample_at(bottom, bf, target)))
    return pairs


def fit_cubic_bezier(samples):
    p0 = samples[0]
    p3 = samples[-1]
    cum = [0.0]
    for i in range(1, len(samples)):
        cum.append(cum[-1] + dist(samples[i - 1], samples[i]))
    total = cum[-1] or 1.0
    ts = [c / total for c in cum]
    a11 = a12 = a22 = 0.0
    bx1 = bx2 = by1 = by2 = 0.0
    for t, s in zip(ts, samples):
        b1 = 3 * (1 - t) ** 2 * t
        b2 = 3 * (1 - t) * t ** 2
        rx = s[0] - (1 - t) ** 3 * p0[0] - t ** 3 * p3[0]
        ry = s[1] - (1 - t) ** 3 * p0[1] - t ** 3 * p3[1]
        a11 += b1 * b1
        a12 += b1 * b2
        a22 += b2 * b2
        bx1 += b1 * rx
        bx2 += b2 * rx
        by1 += b1 * ry
        by2 += b2 * ry
    det = a11 * a22 - a12 * a12
    if abs(det) < 1e-9:
        p1 = (p0[0] + (p3[0] - p0[0]) / 3, p0[1] + (p3[1] - p0[1]) / 3)
        p2 = (p0[0] + 2 * (p3[0] - p0[0]) / 3, p0[1] + 2 * (p3[1] - p0[1]) / 3)
        return p0, p1, p2, p3
    p1 = ((a22 * bx1 - a12 * bx2) / det, (a22 * by1 - a12 * by2) / det)
    p2 = ((a11 * bx2 - a12 * bx1) / det, (a11 * by2 - a12 * by1) / det)
    return p0, p1, p2, p3


def total_signed_curvature(samples):
    """Sum of turning angles between consecutive sample vectors. Returns
    absolute total in radians; ~0 for a straight line, ~2π for a full loop.

    Drops samples that duplicate (or near-duplicate) the previous one — the
    extracted samples may include both the body head-end midpoint and the
    arrowhead tip at almost the same coordinate, which produces a spurious
    huge turn at the end of the path.
    """
    # Drop samples that are very close to the previous one. The body
    # head-end midpoint and arrowhead tip can sit within a few font units
    # of each other and form a near-zero vector that produces a spurious
    # ~180° turn at the end of the path. Threshold relative to typical
    # sample spacing.
    if len(samples) >= 2:
        spacings = [dist(samples[i], samples[i + 1])
                    for i in range(len(samples) - 1)]
        threshold = max(2.0, sorted(spacings)[len(spacings) // 2] * 0.25)
    else:
        threshold = 2.0
    pts = [samples[0]]
    for s in samples[1:]:
        if dist(s, pts[-1]) > threshold:
            pts.append(s)
    total = 0.0
    for i in range(1, len(pts) - 1):
        v1 = (pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
        v2 = (pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
        cross = v1[0] * v2[1] - v1[1] * v2[0]
        dot = v1[0] * v2[0] + v1[1] * v2[1]
        total += math.atan2(cross, dot)
    return abs(total)


def choose_segment_count(samples):
    """Pick how many cubic Bezier segments to use. A single cubic can
    approximate up to ~120° of arc cleanly; beyond that we split.
    """
    angle = total_signed_curvature(samples)
    if angle < math.radians(130):
        return 1
    if angle < math.radians(220):
        return 2
    if angle < math.radians(310):
        return 3
    return 4


def fit_multi_segment_bezier(samples, n_segments):
    """Fit `n_segments` cubic Bezier curves to `samples`. Returns
    (p0, [{'p1', 'p2', 'p3'}, ...]). Segments share endpoints (segment[k]
    starts at segment[k-1]'s p3) so the centerline is continuous.

    Segment boundaries are chosen at points of equal cumulative curvature
    (not equal arc length) so that bends in the path become segment
    boundaries. Lets a J-shape get one straight segment + one curved
    segment instead of two segments that each smear half the bend.
    """
    if n_segments <= 1 or len(samples) < 4:
        p0, p1, p2, p3 = fit_cubic_bezier(samples)
        return p0, [{'p1': p1, 'p2': p2, 'p3': p3}]

    # Cumulative absolute turning angle at each sample.
    cum_curv = [0.0]
    for i in range(1, len(samples) - 1):
        v1 = (samples[i][0] - samples[i - 1][0],
              samples[i][1] - samples[i - 1][1])
        v2 = (samples[i + 1][0] - samples[i][0],
              samples[i + 1][1] - samples[i][1])
        cross = v1[0] * v2[1] - v1[1] * v2[0]
        dot = v1[0] * v2[0] + v1[1] * v2[1]
        cum_curv.append(cum_curv[-1] + abs(math.atan2(cross, dot)))
    cum_curv.append(cum_curv[-1])  # last sample carries final accumulator
    total = cum_curv[-1] or 1.0

    boundaries = [0]
    for k in range(1, n_segments):
        target = total * k / n_segments
        idx = next((i for i, c in enumerate(cum_curv) if c >= target),
                   len(samples) - 1)
        if idx <= boundaries[-1]:
            idx = boundaries[-1] + 1
        boundaries.append(min(idx, len(samples) - 1))
    boundaries.append(len(samples) - 1)

    p0 = samples[boundaries[0]]
    segments = []
    for k in range(n_segments):
        seg = samples[boundaries[k]: boundaries[k + 1] + 1]
        if len(seg) < 2:
            continue
        _, p1, p2, p3 = fit_cubic_bezier(seg)
        segments.append({'p1': p1, 'p2': p2, 'p3': p3})

    return p0, segments


def extract_arrow(body, head):
    if len(body) < 4 or len(head) < 3:
        return None
    head_c = centroid(head)
    i = find_head_edge(body, head_c)
    n = len(body)
    cap_end = midpoint(body[n - 1], body[0])
    body_head_end = midpoint(body[i], body[i + 1])
    # Tip of the arrowhead = the head triangle vertex CLOSEST to the body's
    # head-end midpoint. This is where the body terminates (visually the
    # "point" of the arrow). The other two vertices are trailing flares
    # that fan out behind the tip.
    tip = min(head, key=lambda v: dist(v, body_head_end))

    # Top/bottom long edges of the body run cap → head.
    top = list(body[: i + 1])
    bottom = list(reversed(body[i + 1 :]))
    n_pairs = max(8, min(48, max(len(top), len(bottom))))
    pairs = pair_edges_by_arclength(top, bottom, n_pairs)
    body_midpoints = [midpoint(t, b) for t, b in pairs[1:-1]]

    # Centerline samples: cap end → body midpoints → body head end → tip.
    # Both body_head_end and tip anchor the curve through the head segment so
    # the Bezier extends straight from the body into the arrowhead tip.
    samples = [cap_end] + body_midpoints + [body_head_end, tip]

    if len(pairs) > 2:
        widths = [dist(t, b) for t, b in pairs[1:-1]]
        width = sum(widths) / len(widths)
    else:
        width = dist(*pairs[0]) if pairs else 0.0

    # Head-relative frame: origin at tip, +x points back toward body, +y
    # perpendicular. Compute the back direction from the centerline's
    # tangent at the tip, using a sample far enough back that the vector
    # is non-trivial (tip ≈ body_head_end on many arrows, so the immediate
    # neighbor would give a near-zero direction).
    back_src = None
    for i in range(len(samples) - 2, -1, -1):
        if dist(samples[i], tip) > 5:
            back_src = samples[i]
            break
    if back_src is None:
        back_src = body_head_end
    bx = back_src[0] - tip[0]
    by = back_src[1] - tip[1]
    bnorm = math.hypot(bx, by) or 1.0
    tx, ty = bx / bnorm, by / bnorm
    px, py = -ty, tx
    head_local = []
    for x, y in head:
        rx = x - tip[0]
        ry = y - tip[1]
        u = rx * tx + ry * ty
        v = rx * px + ry * py
        head_local.append((u, v))

    return {
        'samples': samples,
        'width': width,
        'head_local': head_local,
    }


def main(preview=False):
    font = TTFont(FONT_PATH)
    arrow_names = get_arrow_glyph_names(font)
    print(f'Found {len(arrow_names)} arrow sub-glyphs')

    glyphs = {}
    widths = []
    canonical_head = None

    for gn in arrow_names:
        contours = get_contours(font['glyf'], gn)
        if len(contours) != 2:
            print(f'  skip {gn}: {len(contours)} contours')
            continue
        body, head = contours[0], contours[1]
        if len(head) != 3 and len(body) == 3:
            body, head = head, body  # swap if order differs
        if len(head) != 3:
            print(f'  skip {gn}: head has {len(head)} pts, expected 3')
            continue
        result = extract_arrow(body, head)
        if result is None:
            print(f'  skip {gn}: extraction failed')
            continue
        n_segs = choose_segment_count(result['samples'])
        p0, segments = fit_multi_segment_bezier(result['samples'], n_segs)
        glyphs[gn] = {
            'centerline': {
                'p0': [round(p0[0], 2), round(p0[1], 2)],
                'segments': [
                    {
                        'p1': [round(s['p1'][0], 2), round(s['p1'][1], 2)],
                        'p2': [round(s['p2'][0], 2), round(s['p2'][1], 2)],
                        'p3': [round(s['p3'][0], 2), round(s['p3'][1], 2)],
                    }
                    for s in segments
                ],
            },
        }
        widths.append(result['width'])
        if canonical_head is None:
            canonical_head = result['head_local']
        last_p3 = segments[-1]['p3'] if segments else p0
        print(f'  {gn}: width={result["width"]:.1f}  '
              f'segs={len(segments)}  '
              f'p0=({p0[0]:.0f},{p0[1]:.0f})  '
              f'tip=({last_p3[0]:.0f},{last_p3[1]:.0f})')

    widths_sorted = sorted(widths)
    font_width = round(widths_sorted[len(widths_sorted) // 2]) if widths_sorted else 0
    head_data = {
        'vertices': [[round(x, 2), round(y, 2)] for (x, y) in (canonical_head or [])],
    }
    out = {'fontWidth': font_width, 'head': head_data, 'glyphs': glyphs}
    with open(CENTERLINES_PATH, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2)
    print(f'Wrote {CENTERLINES_PATH} (fontWidth={font_width}, '
          f'{len(glyphs)} arrows, head={len(head_data["vertices"])} pts)')

    if preview:
        write_previews(font, arrow_names)


def write_previews(font, arrow_names):
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print('Pillow not installed; skipping previews')
        return
    with open(CENTERLINES_PATH, 'r', encoding='utf-8') as f:
        cl = json.load(f)
    os.makedirs(PREVIEW_DIR, exist_ok=True)
    for gn in arrow_names:
        if gn not in cl['glyphs']:
            continue
        contours = get_contours(font['glyf'], gn)
        if len(contours) != 2:
            continue
        body, head = contours[0], contours[1]
        all_pts = body + head
        if not all_pts:
            continue
        xs = [p[0] for p in all_pts]
        ys = [p[1] for p in all_pts]
        margin = 30
        scale = 0.5
        W = int((max(xs) - min(xs)) * scale + margin * 2)
        H = int((max(ys) - min(ys)) * scale + margin * 2)
        if W < 60 or H < 60:
            scale = 1.0
            W = int((max(xs) - min(xs)) * scale + margin * 2)
            H = int((max(ys) - min(ys)) * scale + margin * 2)
        x0, y0 = min(xs), min(ys)

        def to_px(p):
            return (int((p[0] - x0) * scale + margin),
                    int(H - ((p[1] - y0) * scale + margin)))

        img = Image.new('RGB', (W, H), (255, 255, 255))
        d = ImageDraw.Draw(img)
        d.polygon([to_px(p) for p in body], outline=(180, 180, 180))
        d.polygon([to_px(p) for p in head], outline=(150, 150, 150))
        c = cl['glyphs'][gn]['centerline']
        p0 = c['p0']
        # Render each segment of the centerline; the last segment's p3 is
        # the arrow tip.
        anchor = p0
        for seg in c['segments']:
            p1, p2, p3 = seg['p1'], seg['p2'], seg['p3']
            pts = []
            for k in range(40):
                t = k / 39
                x = ((1 - t) ** 3 * anchor[0] + 3 * (1 - t) ** 2 * t * p1[0] +
                     3 * (1 - t) * t ** 2 * p2[0] + t ** 3 * p3[0])
                y = ((1 - t) ** 3 * anchor[1] + 3 * (1 - t) ** 2 * t * p1[1] +
                     3 * (1 - t) * t ** 2 * p2[1] + t ** 3 * p3[1])
                pts.append((x, y))
            for a, b in zip(pts, pts[1:]):
                d.line([to_px(a), to_px(b)], fill=(220, 0, 0), width=2)
            anchor = p3
        tip = c['segments'][-1]['p3'] if c['segments'] else p0
        for p, color in ((p0, (0, 140, 0)), (tip, (0, 0, 200))):
            cx, cy = to_px(p)
            d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], outline=color, width=2)
        # Disambiguate uppercase/lowercase glyph names on case-insensitive
        # filesystems (e.g. Windows): A.s0.arrow → Aupper-s0-arrow.png,
        # a.s0.arrow → Alower-s0-arrow.png.
        first = gn[0]
        rest = gn[1:].replace('.', '-')
        suffix = 'upper' if first.isupper() else 'lower'
        fname = f'{first.upper()}{suffix}{rest}.png'
        img.save(os.path.join(PREVIEW_DIR, fname))
    print(f'Wrote previews to {PREVIEW_DIR}/')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--preview', action='store_true')
    args = parser.parse_args()
    main(preview=args.preview)
