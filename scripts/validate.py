"""Validate a zipmap working folder, a .zipmap archive, or a .zipmap.json.

Runs every check the save pipeline runs (structure, single-page PDF,
bounds, schema, manifest consistency) and prints a report. Exits non-zero
if anything fails.

Usage:
    python scripts/validate.py mymap             # a working folder
    python scripts/validate.py mymap.zipmap      # an archive (extracted to a temp dir)
    python scripts/validate.py std.zipmapt       # a template (schemata-only checks)
    python scripts/validate.py mymap.zipmap.json # an interchange document
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# tempfile and zipfile are imported inside the archive branch only: together
# they cost ~25 ms, and validating a working folder or a .zipmap.json needs
# neither.

import _bootstrap  # noqa: F401
from zipmap import (
    JSON_SUFFIX,
    ZipmapError,
    load_json_doc,
    open_zipmap,
    summarize,
    summarize_json,
    validate_folder,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("target", help="working folder, .zipmap, .zipmapt, or .zipmap.json file")
    args = parser.parse_args(argv)

    target = Path(args.target)
    try:
        if target.name.endswith(JSON_SUFFIX):
            report, doc, info = load_json_doc(target)
            print(report.render())
            if report.ok:
                print(summarize_json(doc, info))
            return 0 if report.ok else 1
        if target.is_file():
            import tempfile
            import zipfile

            try:
                with tempfile.TemporaryDirectory() as tmp:
                    report, _dest, info = open_zipmap(target, dest=Path(tmp) / target.stem)
            except zipfile.BadZipFile:
                print(f"ERROR: {target} is not a zip archive — a .zipmap/.zipmapt is a "
                      f"zip, and a JSON document must be named <name>{JSON_SUFFIX}",
                      file=sys.stderr)
                return 1
        else:
            # a working folder may not have a manifest yet (save writes it)
            report, info = validate_folder(target, require_manifest=False)
        print(report.render())
        if report.ok:
            print(summarize(info))
        return 0 if report.ok else 1
    except (ZipmapError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
