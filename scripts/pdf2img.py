"""Render a single-page PDF to a PNG (standalone; save.py does this itself).

Usage:
    python scripts/pdf2img.py drawing.pdf                 # -> drawing.png
    python scripts/pdf2img.py drawing.pdf -o out.png --dpi 200

Requires pymupdf (pip install pymupdf).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import _bootstrap  # noqa: F401
from zipmap import DEFAULT_DPI, ZipmapError
from zipmap.pdfio import pdf_info, render_png


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("pdf", help="single-page PDF to render")
    parser.add_argument("-o", "--output", help="output PNG path (default: alongside the PDF)")
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    args = parser.parse_args(argv)

    pdf = Path(args.pdf)
    out = Path(args.output) if args.output else pdf.with_suffix(".png")
    try:
        pages, w, h = pdf_info(pdf)
        if pages != 1:
            print(f"ERROR: {pdf} has {pages} pages — PDFs must be single-page", file=sys.stderr)
            return 1
        px_w, px_h = render_png(pdf, out, args.dpi)
    except (ZipmapError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {out} ({px_w}x{px_h} px from {w:.0f}x{h:.0f} pt at {args.dpi} dpi)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
