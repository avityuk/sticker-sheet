# Sticker Sheet

Small utility for turning a folder of transparent PNGs into a printable US letter PDF sticker sheet.

This repo currently includes:

- `make_sticker_pdf.py`: generates the PDF layout
- `cats/`: source PNG stickers
- `cats_sheet.pdf`: example/generated output

## Requirements

- Python 3.10+
- `Pillow`
- `reportlab`

Install dependencies directly with:

```bash
pip install pillow reportlab
```

Or use a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install pillow reportlab
```

## Usage

The script requires:

- `--images-per-page`
- `--orientation`

Example:

```bash
python3 make_sticker_pdf.py \
  --input-dir cats \
  --output cats_sheet.pdf \
  --images-per-page 6 \
  --orientation portrait
```

## Options

- `--input-dir`: folder containing PNG files, defaults to `cats`
- `--output`: output PDF path, defaults to `cats_sheet.pdf`
- `--images-per-page`: number of stickers placed on each page
- `--page-count`: force an exact number of pages and cycle images if needed
- `--orientation`: `portrait` or `landscape`
- `--margin-in`: page margin in inches, defaults to `0.5`
- `--cell-padding-in`: inner spacing inside each grid cell, defaults to `0.05`
- `--min-dpi`: warn when placed images fall below this print DPI, defaults to `300`

## Behavior

- PNG files are loaded in natural filename order.
- Transparent outer whitespace is trimmed before layout.
- Images are scaled to fit within a symmetric grid on US letter pages.
- The script prints layout and DPI warnings after generating the PDF.
