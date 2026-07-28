"""Export a zipmap to a .zipmap.json interchange document.

Flattens a working folder or a .zipmap archive into a single JSON object —
the base64 PNG for web views, the base64 single-page PDF for high-fidelity
turnover, the drawing's extraction record, and every map item in pixel
coordinates grouped by the server-side schema each type resolves to:

    {"zipmap_json": "1.1",
     "image": {"format": "png", "width": 800, "height": 600},
     "pdf": {"format": "pdf", "width": 792, "height": 612, "pages": 1},
     "extracted_data": {"bill_of_materials": [...], "line_number": "..."},
     "b64": "iVBORw0K...",
     "pdf_b64": "JVBERi0x...",
     "map_item_datasets": [{"schema_id": "...", "map_items": [{...}]}]}

No JSON Schemas travel in the document — each dataset names a `schema_id`
instead, so a schema_id is REQUIRED for every map-item type. Ids come from
`schemata/<type>.schema.json` (`"zipmap": {"schema_id": "..."}` or `$id`),
or from --schema-id on the command line.

The PDF and the extraction record travel by default whenever the source has
them; --no-pdf and --no-extracted-data leave them out.

Usage:
    python scripts/to_json.py mymap                        # -> mymap.zipmap.json
    python scripts/to_json.py mymap.zipmap -o out.json
    python scripts/to_json.py mymap --schema-id weld=wsc_01H2 --schema-id heat=hsc_9K
    python scripts/to_json.py mymap --schema-id weld=wsc_01H2 --bind   # remember it
    python scripts/to_json.py mymap --extracted-data bom.json          # from an extractor
    python scripts/to_json.py mymap --no-pdf --compact                 # web payload only
    python scripts/to_json.py mymap --stdout | curl -d @- ...
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import _bootstrap  # noqa: F401
from zipmap import JSON_SUFFIX, ZipmapError, bind_schema_id, to_json, write_json


def _parse_ids(pairs: list[str], parser: argparse.ArgumentParser) -> dict[str, str]:
    ids: dict[str, str] = {}
    for pair in pairs or []:
        if "=" not in pair:
            parser.error(f"--schema-id expects <type>=<id>, got {pair!r}")
        type_name, _, schema_id = pair.partition("=")
        type_name, schema_id = type_name.strip(), schema_id.strip()
        if not type_name or not schema_id:
            parser.error(f"--schema-id expects <type>=<id>, got {pair!r}")
        ids[type_name] = schema_id
    return ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("target", help="zipmap working folder or .zipmap archive")
    parser.add_argument("-o", "--output", help=f"output path (default: <name>{JSON_SUFFIX})")
    parser.add_argument(
        "--schema-id", action="append", metavar="TYPE=ID", dest="schema_ids",
        help="server-side schema id for a map-item type; repeatable",
    )
    parser.add_argument(
        "--bind", action="store_true",
        help="also write each --schema-id into schemata/<type>.schema.json so later "
             "exports resolve it automatically (working folders only)",
    )
    parser.add_argument(
        "--compact", action="store_true", help="emit minified JSON instead of indented"
    )
    parser.add_argument(
        "--no-meta", action="store_true",
        help="omit title/drawing_number/revision from the document",
    )
    parser.add_argument(
        "--no-pdf", action="store_true",
        help="omit pdf_b64 — the PNG alone. Smaller payload, but a receiver that "
             "needs a print-fidelity drawing for turnover will not get one",
    )
    parser.add_argument(
        "--no-extracted-data", action="store_true",
        help="omit extracted_data even when the zipmap carries one",
    )
    parser.add_argument(
        "--extracted-data", metavar="FILE",
        help="read the drawing extraction record (BOM, drawing parameters) from a "
             "JSON file instead of the zipmap's extracted_data.json. Any object "
             "shape is accepted — the receiving system's extraction schema defines it",
    )
    parser.add_argument(
        "--no-validate", action="store_true",
        help="export even if the zipmap fails validation (errors become warnings)",
    )
    parser.add_argument(
        "--stdout", action="store_true", help="write the document to stdout instead of a file"
    )
    args = parser.parse_args(argv)

    ids = _parse_ids(args.schema_ids, parser)
    target = Path(args.target)

    extracted = None
    if args.extracted_data:
        if args.no_extracted_data:
            parser.error("--extracted-data and --no-extracted-data are contradictory")
        try:
            extracted = json.loads(Path(args.extracted_data).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"ERROR: --extracted-data {args.extracted_data}: {exc}", file=sys.stderr)
            return 1
        if not isinstance(extracted, dict):
            print(
                f"ERROR: --extracted-data {args.extracted_data}: must be a JSON object "
                f"(one extraction record for the drawing), got {type(extracted).__name__}",
                file=sys.stderr,
            )
            return 1

    if args.bind:
        if not ids:
            parser.error("--bind needs at least one --schema-id")
        if not target.is_dir():
            parser.error("--bind works on a working folder, not an archive")
        for type_name, schema_id in ids.items():
            try:
                path = bind_schema_id(target, type_name, schema_id)
            except (FileNotFoundError, OSError, ValueError) as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                return 1
            print(f"bound schema_id {schema_id} into {path.name}")

    common = dict(
        schema_ids=ids,
        validate=not args.no_validate,
        include_meta=not args.no_meta,
        include_pdf=not args.no_pdf,
        include_extracted_data=not args.no_extracted_data,
        extracted_data=extracted,
    )

    try:
        if args.stdout:
            report, doc = to_json(target, **common)
            print(report.render(), file=sys.stderr)
            if doc is None:
                return 1
            if args.compact:
                json.dump(doc, sys.stdout, separators=(",", ":"))
            else:
                json.dump(doc, sys.stdout, indent=2)
            sys.stdout.write("\n")
            return 0

        report, output = write_json(
            target, output=args.output, indent=None if args.compact else 2, **common
        )
    except (ZipmapError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(report.render())
    if output is None:
        return 1
    size_kib = output.stat().st_size / 1024
    print(f"wrote {output} ({size_kib:.1f} KiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
