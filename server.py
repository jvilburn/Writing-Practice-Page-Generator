"""Local dev server for the stroke editor.

- Serves static files (editor HTML + fonts)
- GET  /font-data    : extracts per-letter layer contours from SchoolroomGuidance.ttf
- POST /save         : applies per-sub-glyph transforms and writes font back
- GET  /centerlines  : returns the centerlines.json sidecar
- POST /centerlines  : updates centerlines.json, regenerates arrow contours, writes TTF

Usage:
    python server.py
    Then open http://localhost:8000/stroke_editor.html
"""

import http.server
import json
import math
import os
import shutil
import sys

from fontTools.ttLib import TTFont

ROOT = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(ROOT, 'SchoolroomGuidance.ttf')
FONT_BACKUP_PATH = FONT_PATH + '.bak'
CENTERLINES_PATH = os.path.join(ROOT, 'centerlines.json')
PORT = 8000


def load_centerlines():
    """Read the centerlines sidecar; return an empty default if missing."""
    if not os.path.exists(CENTERLINES_PATH):
        return {'fontWidth': 0, 'head': {'vertices': []}, 'glyphs': {}}
    with open(CENTERLINES_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_centerlines(data):
    with open(CENTERLINES_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def backup_font():
    """Copy the live TTF to .bak (overwriting the previous backup)."""
    if os.path.exists(FONT_PATH):
        shutil.copy2(FONT_PATH, FONT_BACKUP_PATH)


SAMPLES_PER_PATH = 32  # total points along the centerline before offsetting


def _sample_segment(p0, p1, p2, p3, n):
    """Sample a cubic Bezier at n evenly-spaced t values. Returns
    [(x, y, tx, ty), ...] with (tx, ty) the unit tangent."""
    out = []
    for k in range(n):
        t = k / (n - 1) if n > 1 else 0.0
        u = 1 - t
        x = u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0]
        y = u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1]
        dx = 3 * u * u * (p1[0] - p0[0]) + 6 * u * t * (p2[0] - p1[0]) + 3 * t * t * (p3[0] - p2[0])
        dy = 3 * u * u * (p1[1] - p0[1]) + 6 * u * t * (p2[1] - p1[1]) + 3 * t * t * (p3[1] - p2[1])
        norm = math.hypot(dx, dy) or 1.0
        out.append((x, y, dx / norm, dy / norm))
    return out


def _sample_path(p0, segments, total):
    """Sample the multi-segment cubic Bezier path. Returns a list of
    (x, y, tx, ty) tuples. Each segment gets samples proportional to its
    arc length so straight stretches don't waste density."""
    if not segments:
        return [(p0[0], p0[1], 1.0, 0.0)]
    # Estimate per-segment arc length with a coarse pre-sampling.
    seg_lens = []
    prev = p0
    for seg in segments:
        pts = _sample_segment(prev, seg['p1'], seg['p2'], seg['p3'], 11)
        L = sum(math.hypot(pts[k + 1][0] - pts[k][0], pts[k + 1][1] - pts[k][1])
                for k in range(len(pts) - 1))
        seg_lens.append(L)
        prev = seg['p3']
    totalL = sum(seg_lens) or 1.0

    samples = []
    prev = p0
    for i, seg in enumerate(segments):
        n = max(2, round(total * seg_lens[i] / totalL))
        seg_samples = _sample_segment(prev, seg['p1'], seg['p2'], seg['p3'], n)
        if i > 0 and seg_samples:
            seg_samples = seg_samples[1:]  # avoid duplicating segment join points
        samples.extend(seg_samples)
        prev = seg['p3']
    return samples


BODY_PULLBACK_FRACTION = 0.9  # body ends 10% inside the arrowhead from its back


def _centerline_to_contours(centerline, font_width, head):
    """Build (body, head) contours from {centerline, font_width, head}.
    The body is the centerline offset by ±width/2, truncated short of the
    tip by (BODY_PULLBACK_FRACTION × arrowhead_length) so the arrowhead's
    trailing flares stick out beyond the body end. The head triangle is
    positioned with its tip at the centerline's last anchor.
    """
    p0 = tuple(centerline['p0'])
    segments = [
        {'p1': tuple(s['p1']), 'p2': tuple(s['p2']), 'p3': tuple(s['p3'])}
        for s in centerline['segments']
    ]
    samples = _sample_path(p0, segments, SAMPLES_PER_PATH)
    if not samples:
        return [[], []]

    # Arrowhead length = how far back from the tip the trailing flares
    # extend (max +u coord in the head-relative frame; +u points back).
    head_vertices = head.get('vertices', [])
    arrowhead_length = max((v[0] for v in head_vertices), default=0.0)
    pullback = arrowhead_length * BODY_PULLBACK_FRACTION

    # Truncate samples so the body's last point sits `pullback` arc-length
    # short of the tip (= samples[-1]).
    cum = [0.0]
    for i in range(1, len(samples)):
        cum.append(cum[-1] + math.hypot(
            samples[i][0] - samples[i - 1][0],
            samples[i][1] - samples[i - 1][1]))
    total_len = cum[-1]
    body_target = max(0.0, total_len - pullback)

    body_samples = []
    for i, s in enumerate(samples):
        if cum[i] <= body_target:
            body_samples.append(s)
            continue
        # Interpolate one final point exactly at body_target.
        prev = samples[i - 1]
        span = cum[i] - cum[i - 1]
        frac = (body_target - cum[i - 1]) / span if span > 0 else 0
        bx = prev[0] + frac * (s[0] - prev[0])
        by = prev[1] + frac * (s[1] - prev[1])
        body_samples.append((bx, by, s[2], s[3]))
        break
    if len(body_samples) < 2:
        body_samples = samples[:2] if len(samples) >= 2 else samples

    half_w = font_width / 2.0
    top = []
    bottom = []
    for x, y, tx, ty in body_samples:
        px, py = -ty, tx
        top.append((x + px * half_w, y + py * half_w))
        bottom.append((x - px * half_w, y - py * half_w))
    body_contour = top + list(reversed(bottom))

    tip_x, tip_y, tx, ty = samples[-1]
    head_contour = []
    for u, v in head_vertices:
        gx = tip_x - u * tx + v * ty
        gy = tip_y - u * ty - v * tx
        head_contour.append((gx, gy))
    return [body_contour, head_contour]


def _replace_glyph_contours(font, glyph_name, contours):
    """Overwrite glyph_name's TTF coordinates with the given contours.
    All points are emitted as on-curve (flag=1).
    """
    from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphCoordinates
    from fontTools.ttLib.tables.ttProgram import Program
    glyf = font['glyf']
    if glyph_name not in glyf:
        return
    g = glyf[glyph_name]
    coords = []
    flags = []
    end_pts = []
    for contour in contours:
        if not contour:
            continue
        for x, y in contour:
            coords.append((int(round(x)), int(round(y))))
            flags.append(1)
        end_pts.append(len(coords) - 1)
    if not end_pts:
        return
    g.numberOfContours = len(end_pts)
    g.coordinates = GlyphCoordinates(coords)
    g.flags = bytearray(flags)
    g.endPtsOfContours = end_pts
    g.program = Program()
    g.program.fromBytecode(b'')
    g.recalcBounds(glyf)


def regenerate_arrow_contours(font, centerlines):
    """Rewrite every arrow sub-glyph's TTF contour from its centerline +
    the global fontWidth + the canonical head shape. Sub-glyphs without a
    centerline entry are left untouched.
    """
    font_width = centerlines.get('fontWidth', 14)
    head = centerlines.get('head', {'vertices': []})
    glyf = font['glyf']
    hmtx = font['hmtx']
    n_done = 0
    n_failed = 0
    for gn, gdata in centerlines.get('glyphs', {}).items():
        cl = gdata.get('centerline')
        if not cl or 'p0' not in cl or 'segments' not in cl:
            continue
        try:
            contours = _centerline_to_contours(cl, font_width, head)
            _replace_glyph_contours(font, gn, contours)
            # Sync hmtx left-side bearing with new bounds.
            g = glyf[gn]
            if g.numberOfContours > 0 and gn in hmtx.metrics:
                adv, _ = hmtx[gn]
                hmtx[gn] = (adv, g.xMin)
            n_done += 1
        except Exception as e:
            print(f'  regen failed for {gn}: {e}')
            n_failed += 1
    print(f'  regenerated {n_done} arrow contours ({n_failed} failed)')


def extract_font_data():
    """Parse the guidance font into a JSON-friendly structure.

    Returns:
      {
        cap: int,
        glyphs: {
          'A': {
            advance: int,
            layers: [
              { name: 'A', palette: 0, contours: [[{x,y,on}, ...], ...], transform: {dx:0,dy:0,rot:0} },
              { name: 'A.s0.arrow', palette: 1, contours: [...], transform: {dx:0,dy:0,rot:0} },
              ...
            ]
          },
          ...
        }
      }
    """
    font = TTFont(FONT_PATH)
    cap = font['OS/2'].sCapHeight
    glyf = font['glyf']
    hmtx = font['hmtx']
    cmap = font.getBestCmap()
    colr = font.get('COLR')

    def glyph_contours(gn):
        g = glyf[gn]
        if g.numberOfContours <= 0:
            return []
        ends = g.endPtsOfContours
        starts = [0] + [e + 1 for e in ends[:-1]]
        contours = []
        for s, e in zip(starts, ends):
            c = []
            for i in range(s, e + 1):
                x, y = g.coordinates[i]
                on = g.flags[i] & 1
                c.append({'x': int(x), 'y': int(y), 'on': bool(on)})
            contours.append(c)
        return contours

    glyphs = {}
    for char in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz':
        gn = cmap.get(ord(char))
        if gn is None:
            continue

        advance = hmtx[gn][0]
        layers_info = []

        # Base letter layer
        layers_info.append({
            'name': gn,
            'palette': 0,
            'contours': glyph_contours(gn),
            'transform': {'dx': 0, 'dy': 0, 'rot': 0},
        })

        # COLR layers
        if colr is not None and gn in colr.ColorLayers:
            for layer in colr.ColorLayers[gn]:
                layer_gn = layer.name
                if layer_gn == gn:
                    continue  # skip duplicate base
                layers_info.append({
                    'name': layer_gn,
                    'palette': layer.colorID,
                    'contours': glyph_contours(layer_gn),
                    'transform': {'dx': 0, 'dy': 0, 'rot': 0},
                })

        glyphs[char] = {'advance': advance, 'layers': layers_info}

    return {'cap': cap, 'glyphs': glyphs}


def apply_transform_to_glyph(font, glyph_name, dx, dy, rot_deg):
    """Translate and rotate every contour point in a sub-glyph (about its centroid)."""
    glyf = font['glyf']
    if glyph_name not in glyf:
        return
    g = glyf[glyph_name]
    if g.numberOfContours <= 0:
        return
    coords = list(g.coordinates)
    # Centroid
    sx = sum(c[0] for c in coords)
    sy = sum(c[1] for c in coords)
    n = len(coords)
    cx = sx / n
    cy = sy / n
    rad = math.radians(rot_deg)
    cos_r = math.cos(rad)
    sin_r = math.sin(rad)
    new_coords = []
    for (x, y) in coords:
        # Rotate around centroid
        lx = x - cx
        ly = y - cy
        rx = lx * cos_r - ly * sin_r
        ry = lx * sin_r + ly * cos_r
        # Translate back + apply dx/dy
        new_coords.append((int(round(rx + cx + dx)), int(round(ry + cy + dy))))
    from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
    g.coordinates = GlyphCoordinates(new_coords)
    g.recalcBounds(glyf)


def apply_transforms(transforms):
    """transforms: {char: {subGlyphName: {dx, dy, rot}}}"""
    font = TTFont(FONT_PATH)
    hmtx = font['hmtx']
    for char, layers in transforms.items():
        for gn, tf in layers.items():
            before = list(font['glyf'][gn].coordinates)[:2] if gn in font['glyf'] else None
            apply_transform_to_glyph(font, gn, tf.get('dx', 0), tf.get('dy', 0), tf.get('rot', 0))
            # Sync hmtx lsb with new xMin
            g = font['glyf'][gn]
            if g.numberOfContours > 0:
                adv, _ = hmtx[gn]
                hmtx[gn] = (adv, g.xMin)
            after = list(font['glyf'][gn].coordinates)[:2]
            print(f'  {gn}: tf={tf}  xMin={g.xMin}  lsb={hmtx[gn][1]}  coords[0..1]={after}')
    font.save(FONT_PATH)
    print(f'  font.save({FONT_PATH}) done')


class Handler(http.server.SimpleHTTPRequestHandler):
    def _send_json(self, body, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, exc):
        self.send_response(500)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(f'Error: {exc}'.encode())
        import traceback; traceback.print_exc()

    def do_GET(self):
        if self.path == '/font-data':
            try:
                data = extract_font_data()
                self._send_json(json.dumps(data).encode('utf-8'))
            except Exception as e:
                self._send_error(e)
            return
        if self.path == '/centerlines':
            try:
                data = load_centerlines()
                self._send_json(json.dumps(data).encode('utf-8'))
            except Exception as e:
                self._send_error(e)
            return
        super().do_GET()

    def do_POST(self):
        if self.path == '/save':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            try:
                transforms = json.loads(body)
                apply_transforms(transforms)
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'OK')
                n = sum(len(v) for v in transforms.values())
                print(f'[save] applied {n} sub-glyph transforms')
            except Exception as e:
                self._send_error(e)
            return
        if self.path == '/centerlines':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            try:
                centerlines = json.loads(body)
                # Validate minimal shape so a malformed POST can't corrupt the file.
                if not isinstance(centerlines, dict) or 'glyphs' not in centerlines:
                    raise ValueError('payload missing required "glyphs" key')
                backup_font()
                save_centerlines(centerlines)
                font = TTFont(FONT_PATH)
                regenerate_arrow_contours(font, centerlines)
                font.save(FONT_PATH)
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'OK')
                n_arrows = len(centerlines.get('glyphs', {}))
                print(f'[centerlines] saved {n_arrows} arrows; '
                      f'fontWidth={centerlines.get("fontWidth")}; '
                      f'backup at {FONT_BACKUP_PATH}')
            except Exception as e:
                self._send_error(e)
            return
        self.send_response(404); self.end_headers()

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def log_message(self, format, *args):
        # quieter logging
        if '/font-data' in args[0] or '/save' in args[0] or '/centerlines' in args[0]:
            super().log_message(format, *args)


def main():
    os.chdir(ROOT)
    server = http.server.ThreadingHTTPServer(('localhost', PORT), Handler)
    print(f'Serving at http://localhost:{PORT}/')
    print(f'Open http://localhost:{PORT}/stroke_editor.html')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nShutting down')


if __name__ == '__main__':
    main()
