"""Print a zipmap to a paginated PDF with FPDF — drawing overlay + item tables.

Rarely needed (render.py / view.py cover day-to-day viewing), but kept as
the worked example of **constructing a map as a PDF**: page setup, fitting
a raster drawing onto a page, converting pixel coordinates to page
millimetres, drawing flag/rect callouts, and tabulating item data. If a
user needs a custom PDF deliverable, start from this file.

Requires the ``fpdf2`` package (``pip install fpdf2``). Reads only the
web-ready layer (img/ + schemata + manifest), so it works on any valid
zipmap, PDF-backed or image-only.

Output structure:
    page 1    the drawing, fitted to the page, with all map items overlaid
    page 2+   one table per item type listing every field (skip: --no-table)

Usage:
    python scripts/print_pdf.py mymap.zipmap             # -> mymap_map.pdf
    python scripts/print_pdf.py mymap -o out.pdf --page-size a3 --no-table
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

import _bootstrap  # noqa: F401

# Reuse the archive/folder reader from the HTML viewer script.
from view import PALETTE, read_map

MM_PER_PT = 25.4 / 72  # font sizes are in points; page geometry is in mm


def _hex_rgb(color: str) -> tuple[int, int, int]:
    return tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))


def _latin1(text: str) -> str:
    """FPDF's built-in core fonts only cover latin-1; degrade gracefully."""
    return text.encode("latin-1", "replace").decode("latin-1")


def print_zipmap_pdf(
    name: str,
    png: bytes,
    manifest: dict,
    datasets: dict[str, dict],
    schemas: dict[str, dict],
    output: Path,
    page_size: str = "letter",
    margin: float = 12.0,
    table: bool = True,
) -> None:
    """Write a PDF printout of the map. All lengths in millimetres."""
    try:
        from fpdf import FPDF
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("print_pdf.py needs the fpdf2 package: pip install fpdf2") from exc

    import io
    import struct

    if png[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("img drawing is not a PNG")
    img_w, img_h = struct.unpack(">II", png[16:24])

    # --- page setup ---------------------------------------------------------
    # Match page orientation to the drawing so the image gets the most area.
    orientation = "L" if img_w >= img_h else "P"
    pdf = FPDF(orientation=orientation, unit="mm", format=page_size)
    pdf.set_auto_page_break(auto=True, margin=margin)
    pdf.add_page()

    # --- header band ----------------------------------------------------------
    title = manifest.get("title") or name
    meta = " · ".join(
        str(manifest[k]) for k in ("drawing_number", "revision") if manifest.get(k)
    )
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(30, 30, 30)
    pdf.set_xy(margin, margin)
    pdf.cell(0, 6, _latin1(title))
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(90, 90, 90)
    pdf.set_xy(margin, margin + 6)
    counts = "   ".join(
        f"{stem}: {len(d.get('items', []))}" for stem, d in sorted(datasets.items())
    )
    pdf.cell(0, 5, _latin1(" · ".join(filter(None, [meta, counts]))))
    header_h = 14.0

    # --- fit the drawing on the page -----------------------------------------
    # img/ coordinates are pixels with origin TOP-LEFT and y DOWN — the same
    # direction FPDF's page space uses (mm, origin top-left, y down). So
    # pixel -> page is a pure uniform scale plus offset; there is no y-flip
    # here. (The bottom-left, y-up flip of raw PDF content space was already
    # handled by the save pipeline when it derived img/ from pdf/.)
    avail_w = pdf.w - 2 * margin
    avail_h = pdf.h - 2 * margin - header_h
    scale = min(avail_w / img_w, avail_h / img_h)  # mm per pixel
    ox = margin + (avail_w - img_w * scale) / 2  # centre the drawing
    oy = margin + header_h + (avail_h - img_h * scale) / 2

    def X(px: float) -> float:
        return ox + px * scale

    def Y(py: float) -> float:
        return oy + py * scale

    pdf.image(io.BytesIO(png), x=ox, y=oy, w=img_w * scale, h=img_h * scale)
    pdf.set_draw_color(120, 120, 120)
    pdf.set_line_width(0.3)
    pdf.rect(ox, oy, img_w * scale, img_h * scale)

    # --- overlay the map items -------------------------------------------------
    # Sizes track the drawing scale (like the HTML viewers) with print floors.
    fs_px = max(12.0, min(img_w, img_h) * 0.018)  # label size in drawing px
    label_pt = max(6.0, fs_px * scale / MM_PER_PT)  # ...converted to points
    pin_r = max(0.8, fs_px * 0.28 * scale)  # pin radius, mm
    line_w = max(0.25, fs_px * 0.1 * scale)  # stroke width, mm

    type_colors: dict[str, str] = {}
    for i, (stem, data) in enumerate(sorted(datasets.items())):
        color = PALETTE[i % len(PALETTE)]
        type_colors[stem] = color
        r, g, b = _hex_rgb(color)
        geometry = (schemas.get(stem, {}).get("zipmap") or {}).get("geometry", "flag")
        pdf.set_draw_color(r, g, b)
        pdf.set_fill_color(r, g, b)
        pdf.set_text_color(r, g, b)
        pdf.set_line_width(line_w)
        pdf.set_font("Helvetica", "B", label_pt)

        for item in data.get("items", []):
            if not isinstance(item, dict):
                continue
            x, y = item.get("x", 0), item.get("y", 0)
            x2, y2 = item.get("x2", x), item.get("y2", y)
            label = _latin1(str(item.get("id", "?")))
            if geometry == "rect":
                # outlined rectangle between the two corners, label inside
                rx, ry = X(min(x, x2)), Y(min(y, y2))
                pdf.rect(rx, ry, abs(x2 - x) * scale, abs(y2 - y) * scale)
                pdf.text(rx + 1.0, ry + label_pt * MM_PER_PT, label)
            else:
                # flag: leader line from the point to the label anchor
                pdf.line(X(x), Y(y), X(x2), Y(y2))
                pdf.ellipse(X(x) - pin_r, Y(y) - pin_r, 2 * pin_r, 2 * pin_r, style="F")
                tw = pdf.get_string_width(label)
                tx = X(x2) + 0.8 if x2 >= x else X(x2) - 0.8 - tw
                pdf.text(tx, Y(y2) + label_pt * MM_PER_PT * 0.35, label)

    # --- item tables, one section per type ------------------------------------
    if table and any(d.get("items") for d in datasets.values()):
        pdf.add_page()
        for stem, data in sorted(datasets.items()):
            items = [i for i in data.get("items", []) if isinstance(i, dict)]
            if not items:
                continue
            # Column order: coords first, then fields in schema order, then
            # anything the schema didn't declare.
            declared = list((schemas.get(stem, {}).get("properties") or {}))
            cols = ["id", "x", "y", "x2", "y2"]
            cols += [k for k in declared if k not in cols]
            cols += [k for it in items for k in it if k not in cols]

            r, g, b = _hex_rgb(type_colors[stem])
            pdf.set_text_color(r, g, b)
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 8, _latin1(f"{stem} ({len(items)})"), new_x="LMARGIN", new_y="NEXT")

            col_w = (pdf.w - 2 * margin) / len(cols)
            pdf.set_text_color(40, 40, 40)
            pdf.set_draw_color(180, 180, 180)
            pdf.set_font("Helvetica", "B", 7.5)
            for c in cols:
                pdf.cell(col_w, 5, _latin1(c), border="B")
            pdf.ln()
            pdf.set_font("Helvetica", "", 7.5)
            for item in items:
                for c in cols:
                    v = item.get(c, "")
                    txt = _latin1("" if v == "" else str(v))
                    while txt and pdf.get_string_width(txt) > col_w - 1.2:
                        txt = txt[:-1]  # hard-truncate to the column
                    pdf.cell(col_w, 4.5, txt, border="B")
                pdf.ln()
            pdf.ln(4)

    pdf.output(str(output))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("target", help="zipmap working folder or .zipmap file")
    parser.add_argument("-o", "--output", help="output PDF path (default: <name>_map.pdf)")
    parser.add_argument(
        "--page-size", default="letter", choices=["letter", "legal", "a4", "a3"],
        help="paper size (default: letter; orientation follows the drawing)",
    )
    parser.add_argument("--margin", type=float, default=12.0, help="page margin in mm")
    parser.add_argument("--no-table", action="store_true", help="skip the item table pages")
    args = parser.parse_args(argv)

    target = Path(args.target)
    try:
        png, manifest, datasets, schemas = read_map(target)
        name = target.stem if target.is_file() else target.name
        out = Path(args.output) if args.output else Path(f"{name}_map.pdf")
        print_zipmap_pdf(
            name, png, manifest, datasets, schemas, out,
            page_size=args.page_size, margin=args.margin, table=not args.no_table,
        )
    except (OSError, ValueError, KeyError, RuntimeError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    total = sum(len(d.get("items", [])) for d in datasets.values())
    print(f"wrote {out} ({total} item(s), {len(datasets)} type(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
