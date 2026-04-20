"""Local dev server for the stroke editor.

- Serves static files (editor HTML + fonts)
- GET  /font-data : extracts per-letter layer contours from SchoolroomGuidance.ttf
- POST /save      : applies per-sub-glyph transforms and writes font back

Usage:
    python server.py
    Then open http://localhost:8000/stroke_editor.html
"""

import http.server
import json
import math
import os
import sys

from fontTools.ttLib import TTFont

ROOT = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(ROOT, 'SchoolroomGuidance.ttf')
PORT = 8000


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
    def do_GET(self):
        if self.path == '/font-data':
            try:
                data = extract_font_data()
                body = json.dumps(data).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(f'Error: {e}'.encode())
                import traceback; traceback.print_exc()
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
                self.send_response(500)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(f'Error: {e}'.encode())
                import traceback; traceback.print_exc()
            return
        self.send_response(404); self.end_headers()

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def log_message(self, format, *args):
        # quieter logging
        if '/font-data' in args[0] or '/save' in args[0]:
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
