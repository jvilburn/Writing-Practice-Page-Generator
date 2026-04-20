"""
Restyle SchoolroomGuidance.ttf in-place.

The font is the source of truth. This script:
- Reads each .sN.number sub-glyph, finds its center
- Rebuilds it in the current style (now: just a red digit, no circle)

Run this whenever you change the number-glyph style (DIGIT_SCALE, etc.).
"""

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphCoordinates
from fontTools.ttLib.tables.ttProgram import Program
import os
import re

FONT_PATH = os.path.join(os.path.dirname(__file__), "SchoolroomGuidance.ttf")
DIGIT_SCALE = 0.18


def get_digit_contours(font, digit_char, cx, cy, scale):
    """Extract a digit glyph's contours, scaled and positioned at (cx, cy)."""
    glyf = font['glyf']
    cmap = font.getBestCmap()
    gn = cmap.get(ord(digit_char))
    if gn is None:
        return []
    g = glyf[gn]
    if g.numberOfContours <= 0:
        return []
    coords = g.coordinates
    flags = g.flags
    ends = g.endPtsOfContours
    starts = [0] + [e + 1 for e in ends[:-1]]
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    center_x = (min(xs) + max(xs)) / 2
    center_y = (min(ys) + max(ys)) / 2
    contours = []
    for s, e in zip(starts, ends):
        contour = []
        for i in range(s, e + 1):
            x = (coords[i][0] - center_x) * scale + cx
            y = (coords[i][1] - center_y) * scale + cy
            on = flags[i] & 1
            contour.append(([x, y], on))
        contours.append(contour)
    return contours


def build_glyph_from_contours(contours_list):
    if not contours_list:
        g = Glyph()
        g.numberOfContours = 0
        g.coordinates = GlyphCoordinates([])
        g.flags = bytearray()
        g.endPtsOfContours = []
        g.program = Program()
        g.program.fromBytecode(b'')
        return g
    all_coords = []
    all_flags = []
    all_ends = []
    for pts, flgs in contours_list:
        start_idx = len(all_coords)
        for p in pts:
            all_coords.append((int(round(p[0])), int(round(p[1]))))
        all_flags.extend(flgs)
        all_ends.append(start_idx + len(pts) - 1)
    g = Glyph()
    g.numberOfContours = len(all_ends)
    g.coordinates = GlyphCoordinates(all_coords)
    g.flags = bytearray(all_flags)
    g.endPtsOfContours = all_ends
    g.program = Program()
    g.program.fromBytecode(b'')
    return g


def glyph_center(g):
    """Center of a glyph's bounding box (in font units)."""
    if g.numberOfContours <= 0 or len(g.coordinates) == 0:
        return (0, 0)
    xs = [c[0] for c in g.coordinates]
    ys = [c[1] for c in g.coordinates]
    # Use the bounding box of the LARGEST contour — typically the outer circle
    # or the digit itself. This is robust regardless of whether the current
    # glyph contains a circle + digit or just a digit.
    ends = g.endPtsOfContours
    starts = [0] + [e + 1 for e in ends[:-1]]
    best_size = -1
    cx, cy = 0, 0
    for s, e in zip(starts, ends):
        pts = list(g.coordinates[s:e+1])
        if not pts:
            continue
        contour_xs = [p[0] for p in pts]
        contour_ys = [p[1] for p in pts]
        w = max(contour_xs) - min(contour_xs)
        h = max(contour_ys) - min(contour_ys)
        size = w * h
        if size > best_size:
            best_size = size
            cx = (min(contour_xs) + max(contour_xs)) / 2
            cy = (min(contour_ys) + max(contour_ys)) / 2
    return (cx, cy)


def main():
    print(f"Loading {FONT_PATH}")
    font = TTFont(FONT_PATH)
    glyf = font['glyf']

    # Find all .sN.number sub-glyphs and restyle them
    number_pattern = re.compile(r'^(.+)\.s(\d+)\.number$')
    count = 0
    for gn in list(glyf.keys()):
        m = number_pattern.match(gn)
        if not m:
            continue
        base, idx_str = m.group(1), m.group(2)
        idx = int(idx_str)

        g = glyf[gn]
        cx, cy = glyph_center(g)

        digit_char = str(idx + 1)
        digit_contours = get_digit_contours(font, digit_char, cx, cy, DIGIT_SCALE)
        contours_list = []
        for dc in digit_contours:
            pts = [p for p, _ in dc]
            flgs = [on for _, on in dc]
            contours_list.append((pts, flgs))

        new_g = build_glyph_from_contours(contours_list)
        glyf[gn] = new_g
        count += 1

    font.save(FONT_PATH)
    size = os.path.getsize(FONT_PATH)
    print(f"Restyled {count} number sub-glyphs, saved ({size/1024:.1f} KB)")


if __name__ == '__main__':
    main()
