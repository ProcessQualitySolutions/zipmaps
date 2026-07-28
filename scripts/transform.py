"""Convert a PDF-space data file to pixel space (standalone; save.py does this itself).

Pure math — no PDF library needed when you pass the page size explicitly:

    python scripts/transform.py pdf/weld.json --pdf-height 612 --dpi 300 \
        --img-width 3300 --img-height 2550 -o img/weld.json

Or read the page size and rendered image size from the actual files:

    python scripts/transform.py pdf/weld.json --from-pdf pdf/drawing.pdf \
        --from-png img/drawing.png --dpi 300 -o img/weld.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import _bootstrap  # noqa: F401
from zipmap import DEFAULT_DPI, ZipmapError, convert_data_file
from zipmap.imaging import png_size


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("data", help="PDF-space data file (space: \"pdf\")")
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    parser.add_argument("--pdf-height", type=float, help="PDF page height in points")
    parser.add_argument("--img-width", type=int, help="rendered image width in pixels")
    parser.add_argument("--img-height", type=int, help="rendered image height in pixels")
    parser.add_argument("--from-pdf", help="read page height from this PDF (needs pymupdf)")
    parser.add_argument("--from-png", help="read image dimensions from this PNG")
    parser.add_argument("-o", "--output", help="output path (default: stdout)")
    args = parser.parse_args(argv)

    try:
        pdf_h = args.pdf_height
        if pdf_h is None:
            if not args.from_pdf:
                parser.error("pass --pdf-height or --from-pdf")
            from zipmap.pdfio import pdf_info

            _pages, _w, pdf_h = pdf_info(args.from_pdf)
        img_w, img_h = args.img_width, args.img_height
        if img_w is None or img_h is None:
            if not args.from_png:
                parser.error("pass --img-width/--img-height or --from-png")
            img_w, img_h = png_size(args.from_png)

        data = json.loads(Path(args.data).read_text(encoding="utf-8"))
        if data.get("space") != "pdf":
            print(f"ERROR: {args.data} is not PDF-space data (space={data.get('space')!r})",
                  file=sys.stderr)
            return 1
        out = convert_data_file(data, pdf_h, args.dpi, img_w, img_h)
    except (ZipmapError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    text = json.dumps(out, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"wrote {args.output} ({len(out['items'])} item(s))")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
