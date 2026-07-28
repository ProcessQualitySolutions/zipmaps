"""Build a .zipmapt template — a zipmap archive containing only schemata.

A template carries the map-item schemas a project has standardized on, so
any new zipmap starts from (and later validates against) the same schemata.

Usage:
    python scripts/make_template.py mymap                      # from a working folder -> mymap.zipmapt
    python scripts/make_template.py mymap.zipmap -o std.zipmapt  # schemata pulled out of a .zipmap
    python scripts/make_template.py --types weld,flange -o std.zipmapt  # from the starter schemas
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import _bootstrap  # noqa: F401
from _bootstrap import SKILL_ROOT
from zipmap import SCHEMATA_DIR, TEMPLATE_SUFFIX, ZipmapError, save_template

STARTER_SCHEMAS = SKILL_ROOT / "assets" / "schemas"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "source", nargs="?",
        help="working folder or .zipmap/.zipmapt to take schemata from (omit with --types)",
    )
    parser.add_argument(
        "--types", help="build from starter schemas instead (comma-separated: weld,flange,heat)"
    )
    parser.add_argument("-o", "--output", help=f"output path (default: <name>{TEMPLATE_SUFFIX})")
    args = parser.parse_args(argv)
    if bool(args.source) == bool(args.types):
        parser.error("pass exactly one of: a source folder/archive, or --types")

    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            if args.types:
                (tmp / SCHEMATA_DIR).mkdir()
                for t in [t.strip() for t in args.types.split(",") if t.strip()]:
                    src = STARTER_SCHEMAS / f"{t}.schema.json"
                    if not src.is_file():
                        print(f"ERROR: no starter schema for {t!r}", file=sys.stderr)
                        return 1
                    shutil.copy2(src, tmp / SCHEMATA_DIR / src.name)
                root, default_name = tmp, "template"
            else:
                source = Path(args.source)
                if source.is_dir():
                    root, default_name = source, source.name
                else:
                    (tmp / SCHEMATA_DIR).mkdir()
                    with zipfile.ZipFile(source) as zf:
                        for n in zf.namelist():
                            p = Path(n)
                            if p.parent.name == SCHEMATA_DIR and n.endswith(".schema.json"):
                                (tmp / SCHEMATA_DIR / p.name).write_bytes(zf.read(n))
                    root, default_name = tmp, source.stem
            output = Path(args.output) if args.output else Path(f"{default_name}{TEMPLATE_SUFFIX}")
            report, written = save_template(root, output=output)
    except (ZipmapError, OSError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(report.render())
    if written is None:
        return 1
    print(f"wrote {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
