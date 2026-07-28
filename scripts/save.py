"""Save a zipmap working folder to a .zipmap archive.

Runs the full save pipeline — single-page PDF check, img/ layer
regeneration (PDF render + pixel-space data derivation), bounds check,
schema check, manifest generation — and only zips when everything passes.

Usage:
    python scripts/save.py mymap                      # -> mymap.zipmap
    python scripts/save.py mymap -o out/mymap.zipmap
    python scripts/save.py mymap --dpi 200
    python scripts/save.py mymap --title "..." --drawing-number ISO-3041 --revision B
    python scripts/save.py mymap --reuse-render   # drawing unchanged, only data edited
"""

from __future__ import annotations

import argparse
import sys

import _bootstrap  # noqa: F401
from zipmap import DEFAULT_DPI, ZipmapError, save


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("folder", help="zipmap working folder")
    parser.add_argument("-o", "--output", help="output .zipmap path (default: <folder>.zipmap)")
    parser.add_argument(
        "--dpi", type=int, default=DEFAULT_DPI,
        help="render DPI for PDF-backed zipmaps (default %(default)s; recorded in the manifest)",
    )
    parser.add_argument("--title", help="set/replace the manifest title")
    parser.add_argument("--drawing-number", help="set/replace the manifest drawing number")
    parser.add_argument("--revision", help="set/replace the manifest revision")
    parser.add_argument(
        "--reuse-render", action="store_true",
        help="skip re-rendering the PNG when the PDF's content hash and the DPI both "
             "match the existing manifest (the edit-save-edit loop); off by default, "
             "when every save regenerates the img/ layer from scratch",
    )
    args = parser.parse_args(argv)

    meta = {
        k: v
        for k, v in (
            ("title", args.title),
            ("drawing_number", args.drawing_number),
            ("revision", args.revision),
        )
        if v
    }
    try:
        report, output = save(
            args.folder, output=args.output, dpi=args.dpi, meta=meta or None,
            reuse_render=args.reuse_render,
        )
    except ZipmapError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(report.render())
    if output is None:
        return 1
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
