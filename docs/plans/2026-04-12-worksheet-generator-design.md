# Handwriting Worksheet Generator — Design

## Overview

A local, single-page web application for creating printable handwriting practice sheets. The user selects letter style, practice mode, and line style from a control panel, types content into a live preview, and prints directly from the browser.

## UI Layout

Two-panel layout:

- **Left panel (controls):** Letter style, practice mode, line style, content preset, font size, repetition/blank line counts, orientation, print button.
- **Right panel (live preview):** US Letter-proportioned page (landscape default) showing ruled lines and text exactly as they will print. User types content that renders in real time.

## Options

### Letter Style
- **Print (block)** — clean sans-serif font
- **Cursive** — FRB American Cursive (GPL v3), with OpenType contextual alternates for correct letter connections

### Practice Mode
- **Dotted/gray trace** — light gray outline letters on ruled lines; student traces over them. Each word/line repeats to fill the page (repetition count configurable).
- **Copy** — solid model text on a line above, followed by configurable number of blank ruled lines for freehand practice (default: 3, no upper limit).

### Line Style
- **3-line ruled** — top line, dashed midline, baseline (standard handwriting paper)
- **Simple baseline** — single line to write on

### Content
- **Full alphabet** — A-Z, a-z, or both, filling the page
- **Custom** — user types words or sentences directly

### Other Controls
- Font size slider (adjusts letter size and line spacing together)
- Number of trace repetitions (trace mode)
- Number of blank practice lines (copy mode)
- Page orientation: landscape (default) / portrait
- Margins adjustment

## Technical Approach

### Rendering
- DOM-based rendering using styled HTML elements — fonts render natively with OpenType contextual alternates intact
- Gray trace letters via CSS low-opacity color on the font
- Ruled lines drawn with CSS borders/pseudo-elements

### Print / Export
- CSS `@media print` hides the control panel, prints only the preview
- Browser print dialog provides "Save as PDF" option

### Font
- **FRB American Cursive** (GPL v3) from github.com/ctrlcctrlv/FRBAmericanCursive
- 3+ glyph versions per character selected via OpenType contextual alternates
- Covers Zaner-Bloser, D'Nealian, and Palmer Method styles (American cursive traditions)
- Loaded from local `fonts/` directory

### File Structure
```
ReadingClass/
  index.html              (the app — single file)
  fonts/
    FRBAmericanCursive-Regular.ttf  (+ variants as needed)
  docs/
    plans/
      2026-04-12-worksheet-generator-design.md
```

## Licensing
- FRB American Cursive: GPL v3 — free to use, modify, distribute. Tool and font must remain GPL if distributed. No restrictions on printed output.
