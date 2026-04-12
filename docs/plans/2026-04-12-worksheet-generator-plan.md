# Handwriting Worksheet Generator — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-with-review to implement this plan task-by-task.

**Goal:** Build a local single-page web app for creating and printing handwriting practice worksheets with print and cursive letter styles, trace and copy modes, stroke guidance, and configurable ruled lines.

**Architecture:** Single HTML file with embedded CSS and JS. FRB American Cursive font loaded from local `fonts/` directory. DOM-based rendering with CSS `@media print` for clean output. Two-panel layout: controls on left, live WYSIWYG preview on right.

**Tech Stack:** HTML5, CSS3, vanilla JavaScript, FRB American Cursive font (woff2), SVG for print stroke guidance

---

### Task 1: Download Fonts

**Files:**
- Create: `fonts/FRBAmericanCursive-400-Regular.woff2`
- Create: `fonts/FRBAmericanCursive-400-Dotted.woff2`
- Create: `fonts/FRBAmericanCursive-400-ArrowPath.woff2`
- Create: `fonts/FRBAmericanCursive-400-GuidelinesArrowsDottedRegular.woff2`
- Create: `fonts/LICENSE-FRBAmericanCursive.txt`

**Step 1: Download font files from GitHub**

Run:
```bash
cd /c/Users/johnv/Documents/ReadingClass/fonts
curl -L -O "https://github.com/ctrlcctrlv/FRBAmericanCursive/raw/main/dist/FRBAmericanCursive-400-Regular.woff2"
curl -L -O "https://github.com/ctrlcctrlv/FRBAmericanCursive/raw/main/dist/FRBAmericanCursive-400-Dotted.woff2"
curl -L -O "https://github.com/ctrlcctrlv/FRBAmericanCursive/raw/main/dist/FRBAmericanCursive-400-ArrowPath.woff2"
curl -L -O "https://github.com/ctrlcctrlv/FRBAmericanCursive/raw/main/dist/FRBAmericanCursive-400-GuidelinesArrowsDottedRegular.woff2"
curl -L -O "https://github.com/ctrlcctrlv/FRBAmericanCursive/raw/main/LICENSE"
mv LICENSE LICENSE-FRBAmericanCursive.txt
```

**Step 2: Verify files downloaded**

Run: `ls -la fonts/`
Expected: Five files present with reasonable sizes.

**Step 3: Commit**

```bash
git init
git add fonts/ docs/
git commit -m "feat: add FRB American Cursive fonts and design docs"
```

---

### Task 2: HTML Skeleton with Two-Panel Layout

**Files:**
- Create: `index.html`

**Step 1: Create the HTML file with basic structure**

Build `index.html` with:
- `<!DOCTYPE html>` with viewport meta for proper scaling
- CSS `@font-face` declarations loading all cursive font variants from `fonts/`
- Two-column flex layout: `#controls` (left, ~280px) and `#preview` (right, flex-grow)
- Preview area styled as landscape US Letter (11:8.5 ratio) with white background, margin auto-centered
- `@media print` rules that hide `#controls` and make `#preview` fill the page
- Placeholder preview content

```html
<!-- Key structural elements -->
<div id="app">
  <aside id="controls">
    <!-- form controls go here -->
  </aside>
  <main id="preview-container">
    <div id="preview">
      <!-- live preview renders here -->
    </div>
  </main>
</div>
```

**Step 2: Open in browser and verify**

Open `index.html` in browser. Verify:
- Two-panel layout visible
- Preview area is landscape-proportioned
- Controls panel on left

**Step 3: Commit**

```bash
git add index.html
git commit -m "feat: HTML skeleton with two-panel layout"
```

---

### Task 3: Control Panel UI

**Files:**
- Modify: `index.html`

**Step 1: Add all control inputs to the `#controls` aside**

Controls (top to bottom):
1. **Letter Style** — radio buttons: Print, Cursive
2. **Practice Mode** — radio buttons: Trace (gray/dotted), Copy (model + blank lines)
3. **Line Style** — radio buttons: 3-line ruled, Simple baseline
4. **Show Stroke Guidance** — checkbox (independent toggle, works in both trace and copy modes)
5. **Content** — radio buttons: Full Alphabet, Custom
   - Sub-option for alphabet: checkboxes for Uppercase, Lowercase
   - Text input area (textarea) for custom content, visible when Custom selected
6. **Font Size** — range slider (min 24px, max 72px, default 48px)
7. **Trace Repetitions** — number input (min 1, max 20, default 4), visible in trace mode
8. **Blank Practice Lines** — number input (min 1, no max, default 3), visible in copy mode
9. **Orientation** — radio buttons: Landscape (default), Portrait
10. **Print** button — large, prominent

Style the controls with clean labels, grouped sections with subtle borders/headers.

**Step 2: Add JS to show/hide conditional controls**

- Show textarea only when "Custom" is selected
- Show "Trace Repetitions" only in Trace mode
- Show "Blank Practice Lines" only in Copy mode
- Show alphabet sub-options only when "Full Alphabet" is selected

**Step 3: Verify in browser**

Open and click through all options. Verify conditional visibility works.

**Step 4: Commit**

```bash
git add index.html
git commit -m "feat: control panel with all inputs and conditional visibility"
```

---

### Task 4: Ruled Line Rendering

**Files:**
- Modify: `index.html`

**Step 1: Implement ruled line generation in JS**

Write a `renderLines()` function that:
- Clears the preview area
- Calculates how many lines fit on the page based on font size and orientation
- For **3-line ruled**: draws top line (solid), midline (dashed), baseline (solid) for each writing line using CSS borders on div elements
- For **simple baseline**: draws only a solid bottom border per line
- Lines should be spaced proportionally to the selected font size
- Lines fill the full preview width with appropriate margins

```javascript
function renderLines() {
  const preview = document.getElementById('preview');
  preview.innerHTML = '';
  const lineStyle = document.querySelector('input[name="lineStyle"]:checked').value;
  const fontSize = parseInt(document.getElementById('fontSize').value);
  const lineHeight = fontSize * 2.2; // space for ascenders/descenders + gap

  const availableHeight = preview.clientHeight - 40; // margins
  const lineCount = Math.floor(availableHeight / lineHeight);

  for (let i = 0; i < lineCount; i++) {
    const lineGroup = createLineGroup(lineStyle, fontSize, lineHeight);
    preview.appendChild(lineGroup);
  }
}
```

**Step 2: Wire up controls to trigger re-render**

All radio buttons, sliders, and inputs call `renderLines()` on change.

**Step 3: Verify in browser**

Switch between 3-line ruled and simple baseline. Adjust font size slider. Lines should update live.

**Step 4: Commit**

```bash
git add index.html
git commit -m "feat: ruled line rendering with 3-line and simple baseline styles"
```

---

### Task 5: Print Letter Rendering (Block/Sans-Serif)

**Files:**
- Modify: `index.html`

**Step 1: Implement text rendering for print/block style**

Update `renderLines()` to become `renderPreview()` which:
- Gets the content (alphabet or custom text from textarea)
- For **trace mode**: renders text on each line in light gray (`color: #ccc`) using a clean sans-serif font (e.g., `Arial, sans-serif`), repeated per "trace repetitions" setting
- For **copy mode**: renders solid black model text on line N, then leaves the next N blank lines (per "blank practice lines" setting), repeating
- Text sits on the baseline of each ruled line group
- For full alphabet: generates "A B C D E..." or "a b c d e..." or both

**Step 2: Verify in browser**

- Select Print + Trace + Custom, type "cat dog". Verify gray text appears on lines.
- Select Print + Copy + Custom, type "hello". Verify solid text with blank lines below.
- Select Full Alphabet. Verify alphabet fills the page.

**Step 3: Commit**

```bash
git add index.html
git commit -m "feat: print/block letter rendering in trace and copy modes"
```

---

### Task 6: Cursive Letter Rendering

**Files:**
- Modify: `index.html`

**Step 1: Wire up FRB American Cursive font**

Ensure `@font-face` declarations are correct:

```css
@font-face {
  font-family: 'FRBCursive';
  src: url('fonts/FRBAmericanCursive-400-Regular.woff2') format('woff2');
  font-weight: normal;
  font-style: normal;
}

@font-face {
  font-family: 'FRBCursiveDotted';
  src: url('fonts/FRBAmericanCursive-400-Dotted.woff2') format('woff2');
  font-weight: normal;
  font-style: normal;
}

@font-face {
  font-family: 'FRBCursiveArrow';
  src: url('fonts/FRBAmericanCursive-400-ArrowPath.woff2') format('woff2');
  font-weight: normal;
  font-style: normal;
}

@font-face {
  font-family: 'FRBCursiveGuideDotted';
  src: url('fonts/FRBAmericanCursive-400-GuidelinesArrowsDottedRegular.woff2') format('woff2');
  font-weight: normal;
  font-style: normal;
}
```

All cursive font families use `font-feature-settings: "calt" 1;` to enable contextual alternates.

**Step 2: Update renderPreview() for cursive**

When letter style is "cursive":
- **Trace mode, no guidance**: use `FRBCursiveDotted`
- **Trace mode, with guidance**: use `FRBCursiveGuideDotted` (dotted + arrows + guidelines)
- **Copy mode, no guidance**: use `FRBCursive` for model text
- **Copy mode, with guidance**: use `FRBCursiveArrow` for model text (solid + arrows)

**Step 3: Verify in browser**

- Select Cursive + Trace, type "bio" — verify dotted cursive with correct b-to-i and i-to-o connections
- Toggle stroke guidance — verify arrows appear
- Select Cursive + Copy, type "hello world" — verify solid cursive model text
- Toggle stroke guidance — verify arrows on model text

**Step 4: Commit**

```bash
git add index.html
git commit -m "feat: cursive rendering with FRB American Cursive and contextual alternates"
```

---

### Task 7: Print Stroke Guidance (SVG Overlays)

**Files:**
- Modify: `index.html`

**Step 1: Define stroke data for all 52 print letters**

Create a JavaScript object `PRINT_STROKE_DATA` containing stroke path data for each letter (A-Z uppercase, a-z lowercase). Each letter definition includes:
- An array of strokes, each with:
  - SVG path (`d` attribute) defining the stroke shape
  - Stroke number (order)
  - Arrow direction (start point and end point for directional arrow)

Example structure:
```javascript
const PRINT_STROKE_DATA = {
  'A': {
    width: 0.6,  // relative to fontSize
    height: 1.0,
    strokes: [
      { d: 'M 0.3,1 L 0.0,0', num: 1, arrow: { x: 0.3, y: 1, angle: -70 } },
      { d: 'M 0.3,1 L 0.6,0', num: 2, arrow: { x: 0.3, y: 1, angle: 70 } },
      { d: 'M 0.1,0.5 L 0.5,0.5', num: 3, arrow: { x: 0.1, y: 0.5, angle: 0 } },
    ]
  },
  'a': {
    width: 0.5,
    height: 0.5,
    strokes: [
      { d: 'M 0.45,0.5 C 0.45,0.2 ...', num: 1, arrow: { x: 0.45, y: 0.5, angle: -90 } },
      { d: 'M 0.45,0 L 0.45,0.5', num: 2, arrow: { x: 0.45, y: 0, angle: 90 } },
    ]
  },
  // ... all 52 letters
};
```

Use standard Zaner-Bloser manuscript stroke order (the accepted teaching standard for US schools).

**Step 2: Implement SVG overlay renderer**

Write `renderStrokeGuidance(letter, x, y, fontSize)` that:
- Creates an SVG element positioned over the letter
- Draws each stroke path as a light colored line
- Adds a small numbered circle at each stroke's start point
- Adds a small directional arrow at the start showing direction of stroke
- Numbers are clearly visible (small filled circles with white text)

**Step 3: Integrate with renderPreview()**

When "Show Stroke Guidance" is checked and letter style is "Print":
- After rendering each letter's text, overlay the SVG stroke guidance on top
- In trace mode: gray letter underneath, stroke guidance on top
- In copy mode: solid model letter with stroke guidance on the model line only (not blank lines)

**Step 4: Verify in browser**

- Select Print + Trace + Guidance, type "Aa Bb" — verify numbered start points and directional arrows on each letter
- Select Print + Copy + Guidance — verify guidance appears on model text only
- Toggle guidance off — verify overlay disappears
- Test several letters for correct stroke order

**Step 5: Commit**

```bash
git add index.html
git commit -m "feat: print letter stroke guidance with numbered start points and direction arrows"
```

---

### Task 8: Print Styling and Page Fit

**Files:**
- Modify: `index.html`

**Step 1: Refine @media print CSS**

```css
@media print {
  #controls { display: none; }
  #preview-container {
    width: 100%;
    height: 100%;
    overflow: visible;
  }
  #preview {
    width: 100%;
    height: 100%;
    box-shadow: none;
    border: none;
    margin: 0;
    padding: 0.5in;
  }
  @page {
    size: landscape letter;
    margin: 0;
  }
}
```

**Step 2: Handle orientation switch**

When orientation changes:
- Update `@page` size directive dynamically (inject a `<style>` tag)
- Update preview aspect ratio to match
- Re-render lines

**Step 3: Verify by printing**

File > Print (or Ctrl+P). Verify:
- Controls are hidden
- Content fills the page correctly
- Landscape by default
- Switch to portrait, print again — verify orientation changes
- Stroke guidance SVGs print correctly

**Step 4: Commit**

```bash
git add index.html
git commit -m "feat: print styling with orientation support"
```

---

### Task 9: Polish and Edge Cases

**Files:**
- Modify: `index.html`

**Step 1: Handle edge cases**

- Empty custom text: show placeholder message in preview
- Very long words: allow text to wrap or truncate at page edge
- Font loading: show "Loading fonts..." until `@font-face` loads, then render
- Ensure preview scrolls if content exceeds one page (with page break indicators)

**Step 2: Visual polish**

- Clean typography in controls panel
- Subtle section dividers between control groups
- Hover state on Print button
- Active/selected states on radio buttons
- Responsive: if window is narrow, stack panels vertically

**Step 3: Final browser test**

Test all combinations (2 letter styles x 2 modes x 2 line styles x guidance on/off) with both alphabet and custom content.

**Step 4: Commit**

```bash
git add index.html
git commit -m "feat: polish UI and handle edge cases"
```

---

### Task 10: Final Verification

**Step 1: Full test matrix**

Test and print each combination:
| Letter Style | Mode  | Line Style    | Guidance | Content   |
|-------------|-------|---------------|----------|-----------|
| Print       | Trace | 3-line ruled  | Off      | Alphabet  |
| Print       | Trace | 3-line ruled  | On       | Custom    |
| Print       | Trace | Simple base   | On       | Custom    |
| Print       | Copy  | 3-line ruled  | Off      | Custom    |
| Print       | Copy  | 3-line ruled  | On       | Alphabet  |
| Print       | Copy  | Simple base   | Off      | Alphabet  |
| Cursive     | Trace | 3-line ruled  | Off      | Alphabet  |
| Cursive     | Trace | 3-line ruled  | On       | Custom    |
| Cursive     | Trace | Simple base   | On       | Custom    |
| Cursive     | Copy  | 3-line ruled  | Off      | Custom    |
| Cursive     | Copy  | 3-line ruled  | On       | Alphabet  |
| Cursive     | Copy  | Simple base   | Off      | Alphabet  |

**Step 2: Verify cursive connections**

Type these words and verify connections look correct:
- "bio" (b-i, i-o transitions)
- "on" (o-n transition)
- "the" (t-h, h-e transitions)
- "quick brown fox" (variety of connections)

**Step 3: Verify print stroke guidance accuracy**

Check stroke order for these letters against Zaner-Bloser standard:
- Uppercase: A, B, E, G, M, R, S
- Lowercase: a, b, d, e, g, p, q

**Step 4: Final commit**

```bash
git add -A
git commit -m "docs: complete implementation and testing"
```
