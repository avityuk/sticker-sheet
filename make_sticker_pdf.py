#!/usr/bin/env python3
"""Lay out PNG images from a folder onto US letter PDF pages for printing."""

from __future__ import annotations

import argparse
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover - import guard
    raise SystemExit(
        "Missing dependency: Pillow. Install with: pip install pillow reportlab"
    ) from exc

try:
    from reportlab.lib.pagesizes import letter, landscape, portrait
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
except ImportError as exc:  # pragma: no cover - import guard
    raise SystemExit(
        "Missing dependency: reportlab. Install with: pip install reportlab pillow"
    ) from exc

POINTS_PER_INCH = 72.0
TARGET_DPI = 300.0


@dataclass(frozen=True)
class Grid:
    rows: int
    cols: int


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float


def natural_sort_key(path: Path) -> list[object]:
    parts = re.split(r"(\d+)", path.name.lower())
    key: list[object] = []
    for part in parts:
        if part.isdigit():
            key.append(int(part))
        else:
            key.append(part)
    return key


def trim_transparent_whitespace(image: Image.Image) -> tuple[Image.Image, bool]:
    """Return an RGBA image cropped to its non-transparent rectangular bounds."""
    rgba = image.convert("RGBA")
    bbox = rgba.getchannel("A").getbbox()
    if bbox is None:
        return rgba, False
    if bbox == (0, 0, rgba.width, rgba.height):
        return rgba, False
    return rgba.crop(bbox), True


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a printable US-letter PDF from PNG files in a folder "
            "using a symmetric grid layout with transparent-edge trimming."
        )
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("cats"),
        help="Folder containing PNG files (default: cats)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("cats_sheet.pdf"),
        help="Output PDF path (default: cats_sheet.pdf)",
    )
    parser.add_argument(
        "--images-per-page",
        type=int,
        required=True,
        help="How many images to place on each page.",
    )
    parser.add_argument(
        "--page-count",
        type=int,
        default=None,
        help=(
            "Generate exactly this many pages. When set, pages are fully filled "
            "and images are cycled as needed."
        ),
    )
    parser.add_argument(
        "--orientation",
        choices=("portrait", "landscape"),
        required=True,
        help="Page orientation.",
    )
    parser.add_argument(
        "--margin-in",
        type=float,
        default=0.5,
        help="Page margin in inches (default: 0.5).",
    )
    parser.add_argument(
        "--cell-padding-in",
        type=float,
        default=0.05,
        help=(
            "Rectangular whitespace border inside each grid cell in inches "
            "(default: 0.05). Increase for more spacing between images."
        ),
    )
    parser.add_argument(
        "--min-dpi",
        type=float,
        default=TARGET_DPI,
        help=(
            "Warn when any placed image would print below this DPI "
            f"(default: {int(TARGET_DPI)})."
        ),
    )
    return parser.parse_args(list(argv))


def choose_grid(images_per_page: int, content_width: float, content_height: float) -> Grid:
    # Prefer exact factor pairs for predictable full pages; choose the one with
    # the largest cell area and closest shape to the page ratio.
    target_ratio = content_width / content_height
    candidates: list[tuple[float, float, int, int]] = []

    for rows in range(1, images_per_page + 1):
        if images_per_page % rows != 0:
            continue
        cols = images_per_page // rows
        cell_w = content_width / cols
        cell_h = content_height / rows
        area_score = cell_w * cell_h
        shape_penalty = abs((cell_w / cell_h) - target_ratio)
        # Sort: highest area first, then smallest shape penalty.
        candidates.append((-area_score, shape_penalty, rows, cols))

    if not candidates:
        return Grid(rows=1, cols=images_per_page)

    candidates.sort()
    _, _, best_rows, best_cols = candidates[0]
    return Grid(rows=best_rows, cols=best_cols)


def centered_slots(rows: int, cols: int, count: int) -> list[tuple[int, int]]:
    if count <= 0:
        return []

    all_slots: list[tuple[float, int, int]] = []
    center_r = rows / 2.0
    center_c = cols / 2.0

    for r in range(rows):
        for c in range(cols):
            slot_r = r + 0.5
            slot_c = c + 0.5
            dist = (slot_r - center_r) ** 2 + (slot_c - center_c) ** 2
            all_slots.append((dist, r, c))

    all_slots.sort(key=lambda item: (item[0], item[1], item[2]))
    chosen = [(r, c) for _, r, c in all_slots[:count]]
    chosen.sort()
    return chosen


def fit_contain(src_w: int, src_h: int, dst: Rect) -> Rect:
    if src_w <= 0 or src_h <= 0:
        return dst

    scale = min(dst.width / src_w, dst.height / src_h)
    draw_w = src_w * scale
    draw_h = src_h * scale
    draw_x = dst.x + (dst.width - draw_w) / 2.0
    draw_y = dst.y + (dst.height - draw_h) / 2.0
    return Rect(draw_x, draw_y, draw_w, draw_h)


def effective_dpi(px: int, points: float) -> float:
    inches = points / POINTS_PER_INCH
    if inches <= 0:
        return 0.0
    return px / inches


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)

    if args.images_per_page <= 0:
        print("Error: --images-per-page must be greater than 0.", file=sys.stderr)
        return 2
    if args.page_count is not None and args.page_count <= 0:
        print("Error: --page-count must be greater than 0.", file=sys.stderr)
        return 2
    if args.margin_in < 0:
        print("Error: --margin-in cannot be negative.", file=sys.stderr)
        return 2
    if args.cell_padding_in < 0:
        print("Error: --cell-padding-in cannot be negative.", file=sys.stderr)
        return 2
    if args.min_dpi <= 0:
        print("Error: --min-dpi must be greater than 0.", file=sys.stderr)
        return 2

    if not args.input_dir.exists() or not args.input_dir.is_dir():
        print(f"Error: input folder does not exist: {args.input_dir}", file=sys.stderr)
        return 2

    images = sorted(args.input_dir.glob("*.png"), key=natural_sort_key)
    if not images:
        print(f"Error: no PNG files found in {args.input_dir}", file=sys.stderr)
        return 2

    page_size = portrait(letter) if args.orientation == "portrait" else landscape(letter)
    page_w, page_h = page_size

    margin_pt = args.margin_in * POINTS_PER_INCH
    padding_pt = args.cell_padding_in * POINTS_PER_INCH

    content_w = page_w - 2 * margin_pt
    content_h = page_h - 2 * margin_pt
    if content_w <= 0 or content_h <= 0:
        print("Error: margin too large for US letter page.", file=sys.stderr)
        return 2

    grid = choose_grid(args.images_per_page, content_w, content_h)
    cell_w = content_w / grid.cols
    cell_h = content_h / grid.rows

    c = canvas.Canvas(str(args.output), pagesize=page_size)
    dpi_warnings: list[str] = []
    trimmed_count = 0

    if args.page_count is None:
        pages = math.ceil(len(images) / args.images_per_page)
        placement_images = list(images)
        cycling_used = False
    else:
        pages = args.page_count
        total_slots = pages * args.images_per_page
        placement_images = [images[i % len(images)] for i in range(total_slots)]
        cycling_used = total_slots > len(images)

    for page_num in range(pages):
        start = page_num * args.images_per_page
        page_images = placement_images[start : start + args.images_per_page]

        slots = centered_slots(grid.rows, grid.cols, len(page_images))

        for image_path, (row, col) in zip(page_images, slots):
            cell_x = margin_pt + col * cell_w
            cell_y = page_h - margin_pt - (row + 1) * cell_h

            target = Rect(
                x=cell_x + padding_pt,
                y=cell_y + padding_pt,
                width=max(cell_w - 2 * padding_pt, 1),
                height=max(cell_h - 2 * padding_pt, 1),
            )

            with Image.open(image_path) as im:
                processed_image, was_trimmed = trim_transparent_whitespace(im)
                if was_trimmed:
                    trimmed_count += 1

                src_w, src_h = processed_image.size
                draw_rect = fit_contain(src_w, src_h, target)

                dpi_x = effective_dpi(src_w, draw_rect.width)
                dpi_y = effective_dpi(src_h, draw_rect.height)
                min_actual = min(dpi_x, dpi_y)
                if min_actual < args.min_dpi:
                    dpi_warnings.append(
                        f"{image_path.name}: ~{min_actual:.0f} DPI at placed size"
                    )

                c.drawImage(
                    ImageReader(processed_image),
                    draw_rect.x,
                    draw_rect.y,
                    width=draw_rect.width,
                    height=draw_rect.height,
                    preserveAspectRatio=True,
                    anchor="c",
                    mask="auto",
                )

        c.showPage()

    c.save()

    print(
        f"Wrote {args.output} with {len(placement_images)} image placement(s) "
        f"across {pages} page(s)."
    )
    print(
        f"Layout: {grid.rows} row(s) x {grid.cols} column(s), "
        f"{args.images_per_page} image(s)/page, {args.orientation}."
    )
    if args.page_count is not None:
        print(
            "Fill mode: fixed page count enabled"
            f" ({args.page_count} page(s), cycling={'yes' if cycling_used else 'no'})."
        )
    print(
        "Transparent trim: "
        f"{trimmed_count}/{len(placement_images)} placement(s) cropped to "
        "rectangular alpha bounds."
    )

    if dpi_warnings:
        print("\\nWarning: some images may print below target DPI:")
        for warning in dpi_warnings:
            print(f"- {warning}")
    else:
        print(f"All placed images meet or exceed {args.min_dpi:.0f} DPI target.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
