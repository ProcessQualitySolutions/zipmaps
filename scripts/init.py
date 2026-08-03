"""Scaffold a new zipmap working folder.

Creates <name>/ with schemata/, pdf/, img/ and copies the requested starter
schemas in. Optionally seeds manifest meta fields and a placeholder demo
drawing so the folder saves immediately.

Usage:
    python scripts/init.py mymap                          # weld schema only
    python scripts/init.py mymap --types weld,flange,heat
    python scripts/init.py mymap --from-template std.zipmapt   # schemas from a .zipmapt template
    python scripts/init.py mymap --title "Unit 3 CW Iso" --drawing-number ISO-3041 --revision A
    python scripts/init.py mymap --demo                   # adds a placeholder img/drawing.png

Drop your single-page drawing at <name>/pdf/drawing.pdf (or a PNG at
<name>/img/drawing.png), add data files, then run scripts/save.py.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import _bootstrap  # noqa: F401
from _bootstrap import SKILL_ROOT
from zipmap import FORMAT_VERSION, IMG_DIR, MANIFEST, PDF_DIR, SCHEMATA_DIR

# Examples only — nothing in the format requires these types or their fields.
STARTER_SCHEMAS = SKILL_ROOT / "assets" / "starter_schemas"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("name", help="folder to create (its name becomes the .zipmap name)")
    parser.add_argument(
        "--types",
        default="weld",
        help="comma-separated starter schemas to copy (available: %s)"
        % ", ".join(sorted(p.name[: -len(".schema.json")] for p in STARTER_SCHEMAS.glob("*.schema.json"))),
    )
    parser.add_argument(
        "--from-template",
        help="a .zipmapt file whose schemata to use instead of --types starters",
    )
    parser.add_argument("--title", help="drawing title (seeded into the manifest)")
    parser.add_argument("--drawing-number", help="drawing number (seeded into the manifest)")
    parser.add_argument("--revision", help="drawing revision (seeded into the manifest)")
    parser.add_argument(
        "--demo", action="store_true", help="generate a placeholder img/drawing.png (800x600)"
    )
    args = parser.parse_args(argv)

    root = Path(args.name)
    if root.exists():
        print(f"error: {root} already exists", file=sys.stderr)
        return 1
    for sub in (SCHEMATA_DIR, PDF_DIR, IMG_DIR):
        (root / sub).mkdir(parents=True)

    if args.from_template:
        import zipfile

        copied = 0
        with zipfile.ZipFile(args.from_template) as zf:
            for n in zf.namelist():
                p = Path(n)
                if p.parent.name == SCHEMATA_DIR and n.endswith(".schema.json"):
                    (root / SCHEMATA_DIR / p.name).write_bytes(zf.read(n))
                    copied += 1
        if not copied:
            print(f"error: {args.from_template} contains no schemata", file=sys.stderr)
            return 1
        print(f"copied {copied} schema(s) from template {args.from_template}")
    else:
        for t in [t.strip() for t in args.types.split(",") if t.strip()]:
            src = STARTER_SCHEMAS / f"{t}.schema.json"
            if src.is_file():
                shutil.copy2(src, root / SCHEMATA_DIR / src.name)
            else:
                print(f"note: no starter schema for {t!r} — author {SCHEMATA_DIR}/{t}.schema.json yourself")

    meta = {
        k: v
        for k, v in (
            ("title", args.title),
            ("drawing_number", args.drawing_number),
            ("revision", args.revision),
        )
        if v
    }
    if meta:
        (root / MANIFEST).write_text(
            json.dumps({"zipmap": FORMAT_VERSION, **meta}, indent=2) + "\n", encoding="utf-8"
        )

    if args.demo:
        from zipmap.imaging import make_demo_drawing

        w, h = make_demo_drawing(root / IMG_DIR / "drawing.png")
        print(f"wrote placeholder {IMG_DIR}/drawing.png ({w}x{h})")

    print(f"scaffolded {root}/ ({SCHEMATA_DIR}, {PDF_DIR}, {IMG_DIR})")
    print(f"next: add {PDF_DIR}/drawing.pdf or {IMG_DIR}/drawing.png plus data files, "
          f"then: python scripts/save.py {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
