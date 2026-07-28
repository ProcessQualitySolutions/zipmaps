"""Open (extract) a .zipmap or .zipmapt into a working folder, validate, summarize.

Opening a .zipmapt template also creates empty pdf/ and img/ dirs, so the
result is immediately usable as the starting folder of a real zipmap.

Usage:
    python scripts/open.py mymap.zipmap             # -> ./mymap/ next to the archive
    python scripts/open.py std.zipmapt -d newmap    # template -> ready working folder
    python scripts/open.py mymap.zipmap --no-validate
"""

from __future__ import annotations

import argparse
import sys

import _bootstrap  # noqa: F401
from zipmap import ZipmapError, open_zipmap, summarize


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("zipmap", help="path to a .zipmap or .zipmapt file")
    parser.add_argument("-d", "--dest", help="extraction folder (default: archive name)")
    parser.add_argument("--no-validate", action="store_true", help="extract only, skip validation")
    args = parser.parse_args(argv)

    try:
        report, dest, info = open_zipmap(args.zipmap, dest=args.dest, validate=not args.no_validate)
    except (ZipmapError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"extracted to {dest}")
    if args.no_validate:
        return 0
    print(report.render())
    if report.ok:
        print(summarize(info))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
