"""Find text labels on a PDF drawing and capture them as map items.

Built for drawings that arrive **pre-labeled** — the engineer already printed
weld numbers (or tag numbers, support marks, …) on the sheet. The text layer
of the PDF knows exactly where every label sits, so bounding boxes come from
pymupdf's text extraction — deterministic, pixel-accurate, and fast. No
leader lines are interpreted: each captured item is a rectangle drawn on the
label text itself, which makes the label a clickable artifact.

Two modes:

Scan (default) — list every text label with its bbox, in zipmap PDF space
(points, origin bottom-left), as one JSON report on stdout:

    python scripts/labels.py mymap/pdf/drawing.pdf
    python scripts/labels.py mymap --pattern "FW-\\d+"      # folder works too

Emit — write a ready PDF-space data file (space "pdf", rect items whose
x/y + x2/y2 are opposite corners of the label's bbox):

    python scripts/labels.py mymap --pattern "FW-\\d+" --emit weld \\
        -o mymap/pdf/weld.json

The pattern is matched against the whole label text (re.fullmatch); pass
--search to match anywhere instead. If the pattern has a capture group,
group 1 becomes the item id, otherwise the full label text does. Pair the
emitted file with a schema hinting `"zipmap": {"geometry": "rect"}` so
renderers draw the box, then run save.py as usual.

Requires pymupdf (pip install pymupdf). Scanned/raster PDFs have no text
layer and yield nothing — this tool does not OCR.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import _bootstrap  # noqa: F401
from zipmap import ZipmapError


def resolve_pdf(target: str) -> Path:
    """Accept a PDF path or a working folder (uses <folder>/pdf/drawing.pdf)."""
    p = Path(target)
    if p.is_dir():
        p = p / "pdf" / "drawing.pdf"
    if not p.is_file():
        raise ZipmapError(f"no PDF at {p}")
    return p


def extract_labels(pdf_path: Path, mode: str) -> tuple[float, float, list[dict]]:
    """Return (width_pt, height_pt, labels) with bboxes in zipmap PDF space.

    pymupdf reports bboxes with the origin top-left (y down); zipmap PDF
    space is origin bottom-left (y up), so y is flipped against the page
    height here — the emitted numbers drop into pdf/<type>.json verbatim.
    (x, y) is the label's top-left corner, (x2, y2) its bottom-right.
    """
    try:
        import fitz  # type: ignore  # pymupdf
    except ImportError as exc:
        raise ZipmapError(
            "pymupdf is required to read the PDF text layer: pip install pymupdf"
        ) from exc

    with fitz.open(str(pdf_path)) as doc:
        if doc.page_count != 1:
            raise ZipmapError(
                f"{pdf_path} has {doc.page_count} pages — PDFs must be single-page"
            )
        page = doc[0]
        w, h = float(page.rect.width), float(page.rect.height)
        raw: list[tuple[float, float, float, float, str]] = []
        if mode == "words":
            for x0, y0, x1, y1, word, *_ in page.get_text("words"):
                raw.append((x0, y0, x1, y1, word))
        else:  # lines
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    text = "".join(s["text"] for s in line["spans"]).strip()
                    if text:
                        x0, y0, x1, y1 = line["bbox"]
                        raw.append((x0, y0, x1, y1, text))

    raw.sort(key=lambda r: (round(r[1], 1), r[0]))  # reading order, stable re-runs
    labels = [
        {
            "text": text,
            "x": round(x0, 2),
            "y": round(h - y0, 2),
            "x2": round(x1, 2),
            "y2": round(h - y1, 2),
        }
        for x0, y0, x1, y1, text in raw
    ]
    return w, h, labels


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("target", help="single-page PDF, or a working folder (pdf/drawing.pdf)")
    parser.add_argument("--pattern", help="regex a label must match (fullmatch unless --search)")
    parser.add_argument("--search", action="store_true",
                        help="match the pattern anywhere in the label, not the whole text")
    parser.add_argument("-i", "--ignore-case", action="store_true")
    parser.add_argument("--mode", choices=("words", "lines"), default="words",
                        help="words: one label per word (default); lines: whole text lines, "
                             "for labels with internal spaces like 'FW 101'")
    parser.add_argument("--emit", metavar="TYPE",
                        help="write a PDF-space data file for this item type instead of a scan "
                             "report (requires --pattern)")
    parser.add_argument("--pad", type=float, default=1.0,
                        help="points of padding around each emitted bbox (default %(default)s)")
    parser.add_argument("-o", "--output", help="output path (default: stdout)")
    args = parser.parse_args(argv)

    if args.emit and not args.pattern:
        parser.error("--emit requires --pattern: decide which labels are items first "
                     "(scan without --pattern to see them all)")

    try:
        pdf = resolve_pdf(args.target)
        w, h, labels = extract_labels(pdf, args.mode)
    except (ZipmapError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    rx = None
    if args.pattern:
        try:
            rx = re.compile(args.pattern, re.IGNORECASE if args.ignore_case else 0)
        except re.error as exc:
            print(f"ERROR: bad --pattern: {exc}", file=sys.stderr)
            return 1
        matched = []
        for lab in labels:
            m = rx.search(lab["text"]) if args.search else rx.fullmatch(lab["text"])
            if m:
                lab["_id"] = m.group(1) if m.groups() else lab["text"]
                matched.append(lab)
        labels = matched

    if args.emit:
        pad = args.pad
        items = [
            {
                "id": lab["_id"],
                "x": round(max(0.0, lab["x"] - pad), 2),
                "y": round(min(h, lab["y"] + pad), 2),
                "x2": round(min(w, lab["x2"] + pad), 2),
                "y2": round(max(0.0, lab["y2"] - pad), 2),
                "label_text": lab["text"],
            }
            for lab in labels
        ]
        doc = {"space": "pdf", "width": w, "height": h, "schema": args.emit, "items": items}
        summary = f"{len(items)} {args.emit} item(s)"
    else:
        for lab in labels:
            lab.pop("_id", None)
        dupes = {t: n for t, n in Counter(lab["text"] for lab in labels).items() if n > 1}
        doc = {
            "pdf": str(pdf), "width": w, "height": h, "mode": args.mode,
            "pattern": args.pattern, "count": len(labels),
            "duplicates": dupes, "labels": labels,
        }
        summary = f"{len(labels)} label(s)"

    text = json.dumps(doc, indent=2) + "\n"
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"wrote {args.output} ({summary})")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
