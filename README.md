# Writing Practice Page Generator

A single-page web app that generates printable handwriting worksheets for early learners. Supports both print and cursive letter styles with ruled lines, tracing, and stroke guidance.

## Features

- **Print and cursive** letter styles
- **Ruled lines** with topline, midline, and baseline
- **Trace mode** with adjustable repetitions and blank practice lines
- **Stroke guidance** arrows showing how to form each letter
- **Alphabet or custom text** input
- **Portrait and landscape** orientation
- **Schoolroom font** — a custom font based on Outfit (OFL) with 50% midline built in, so uppercase and lowercase scale consistently
- **Fully self-contained** — `index.html` has all fonts embedded; download and open in a browser, no server needed

## Usage

Open `index.html` in a browser and use the controls to configure your worksheet, then print.

For extra spacing between words in custom mode, add extra spaces.

## Development

Edit `index-dev.html` (the source file with external font references), then run:

```
python embed_fonts.py
```

This generates `index.html` with all fonts embedded as base64 data URIs.

## Fonts

- **Schoolroom** — Custom font derived from [Outfit](https://fonts.google.com/specimen/Outfit) (OFL). Uppercase from weight 300, lowercase from weight 400 scaled to 80%. Ascenders extended to cap height. Modified Q tail and I crossbars.
- **FRB American Cursive** — Cursive font family (GPL v3) used for cursive mode.

## License

Schoolroom font is based on Outfit, licensed under the [SIL Open Font License](https://openfontlicense.org/).
FRB American Cursive is licensed under GPL v3.
