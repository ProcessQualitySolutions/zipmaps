"""Render a zipmap to a self-contained HTML overlay for visual verification.

Reads the img/ layer (the web-ready layer) of a working folder or a
.zipmap archive and writes one HTML file: the drawing PNG embedded as
base64 with an SVG overlay of every map item — flag items as a pin, leader
line, and label; rect items as an outlined rectangle — followed by one
data table per item type showing every field of every item, so the page
stands alone as a complete human-readable preview. Zero dependencies.

Geometry per type comes from the schema's optional top-level hint
    "zipmap": { "geometry": "flag" | "rect" }
(default "flag").

Usage:
    python scripts/render.py mymap                # folder -> mymap_overlay.html
    python scripts/render.py mymap.zipmap -o check.html
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import sys
import zipfile
from pathlib import Path

import _bootstrap  # noqa: F401
from zipmap import DRAWING_PNG, IMG_DIR, SCHEMATA_DIR
from zipmap.imaging import png_size

PALETTE = ["#c0392b", "#1f618d", "#1e8449", "#9a5b00", "#6c3483", "#148f77"]


def _read_source(target: Path) -> tuple[bytes, dict[str, dict], dict[str, dict]]:
    """Return (png_bytes, {type: data_dict}, {type: schema_dict})."""
    datasets: dict[str, dict] = {}
    schemas: dict[str, dict] = {}
    if target.is_file():
        with zipfile.ZipFile(target) as zf:
            names = set(zf.namelist())
            png_name = f"{IMG_DIR}/{DRAWING_PNG}"
            if png_name not in names:
                raise FileNotFoundError(f"{target} has no {png_name}")
            png = zf.read(png_name)
            for n in sorted(names):
                if n.startswith(f"{IMG_DIR}/") and n.endswith(".json"):
                    datasets[Path(n).stem] = json.loads(zf.read(n))
                elif n.startswith(f"{SCHEMATA_DIR}/") and n.endswith(".schema.json"):
                    schemas[Path(n).name[: -len(".schema.json")]] = json.loads(zf.read(n))
        return png, datasets, schemas
    png_path = target / IMG_DIR / DRAWING_PNG
    if not png_path.is_file():
        raise FileNotFoundError(f"{png_path} not found")
    for p in sorted((target / IMG_DIR).glob("*.json")):
        datasets[p.stem] = json.loads(p.read_text(encoding="utf-8"))
    for p in sorted((target / SCHEMATA_DIR).glob("*.schema.json")):
        schemas[p.name[: -len(".schema.json")]] = json.loads(p.read_text(encoding="utf-8"))
    return png_path.read_bytes(), datasets, schemas


def _item_svg(item: dict, geometry: str, color: str, fs: float) -> str:
    x, y = item.get("x", 0), item.get("y", 0)
    x2, y2 = item.get("x2", x), item.get("y2", y)
    label = html.escape(str(item.get("id", "?")))
    r = max(3.0, fs * 0.28)
    if geometry == "rect":
        rx, ry = min(x, x2), min(y, y2)
        rw, rh = abs(x2 - x), abs(y2 - y)
        return (
            f'<rect x="{rx}" y="{ry}" width="{rw}" height="{rh}" fill="{color}" '
            f'fill-opacity="0.12" stroke="{color}" stroke-width="{max(1.5, fs * 0.12)}"/>'
            f'<text x="{rx + fs * 0.3}" y="{ry + fs}" fill="{color}" font-size="{fs}" '
            f'font-family="sans-serif" font-weight="bold">{label}</text>'
        )
    anchor = "start" if x2 >= x else "end"
    dx = fs * 0.4 if x2 >= x else -fs * 0.4
    return (
        f'<line x1="{x}" y1="{y}" x2="{x2}" y2="{y2}" stroke="{color}" '
        f'stroke-width="{max(1.5, fs * 0.1)}"/>'
        f'<circle cx="{x}" cy="{y}" r="{r}" fill="{color}"/>'
        f'<text x="{x2 + dx}" y="{y2 + fs * 0.35}" fill="{color}" font-size="{fs}" '
        f'font-family="sans-serif" font-weight="bold" text-anchor="{anchor}">{label}</text>'
    )


def _type_table(stem: str, items: list, color: str) -> str:
    """One HTML table per item type: column order = field order as first seen."""
    columns: list[str] = []
    for item in items:
        if isinstance(item, dict):
            for k in item:
                if k not in columns:
                    columns.append(k)
    if not columns:
        return (
            f'<h3 style="color:{color}">{html.escape(stem)} (0)</h3>'
            "<p>no items</p>"
        )

    def cell(v: object) -> str:
        if v is None:
            return ""
        return html.escape(v if isinstance(v, str) else json.dumps(v))

    head = "".join(f"<th>{html.escape(c)}</th>" for c in columns)
    rows = "".join(
        "<tr>" + "".join(f"<td>{cell(item.get(c))}</td>" for c in columns) + "</tr>"
        for item in items
        if isinstance(item, dict)
    )
    return (
        f'<h3 style="color:{color}">{html.escape(stem)} ({len(items)})</h3>'
        f'<div class="tw"><table><thead><tr style="background:{color}">{head}</tr></thead>'
        f"<tbody>{rows}</tbody></table></div>"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("target", help="zipmap working folder or .zipmap file")
    parser.add_argument("-o", "--output", help="output HTML path (default: <name>_overlay.html)")
    args = parser.parse_args(argv)

    target = Path(args.target)
    try:
        png, datasets, schemas = _read_source(target)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    import struct

    if png[:8] != b"\x89PNG\r\n\x1a\n":
        print("ERROR: img drawing is not a PNG", file=sys.stderr)
        return 1
    w, h = struct.unpack(">II", png[16:24])
    fs = max(12.0, min(w, h) * 0.018)  # label font size scaled to the drawing

    shapes, legend, tables = [], [], []
    for i, (stem, data) in enumerate(sorted(datasets.items())):
        color = PALETTE[i % len(PALETTE)]
        geometry = (schemas.get(stem, {}).get("zipmap") or {}).get("geometry", "flag")
        items = data.get("items", [])
        legend.append(
            f'<span style="color:{color};font-weight:bold">&#9632; {html.escape(stem)} '
            f"({len(items)})</span>"
        )
        for item in items:
            if isinstance(item, dict):
                shapes.append(_item_svg(item, geometry, color, fs))
        tables.append(_type_table(stem, items, color))

    b64 = base64.b64encode(png).decode("ascii")
    name = target.stem if target.is_file() else target.name
    doc = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{html.escape(name)} — zipmap overlay</title>
<style>body{{margin:16px;font-family:sans-serif;background:#fff}}svg{{max-width:100%;height:auto;border:1px solid #ccc}}
h3{{margin:18px 0 6px;font-size:15px}}.tw{{overflow-x:auto}}
table{{border-collapse:collapse;font-size:13px}}th,td{{border:1px solid #ddd;padding:3px 10px;text-align:left;white-space:nowrap}}
th{{color:#fff}}tr:nth-child(even) td{{background:#fafaf8}}</style>
</head><body>
<h2 style="margin:0 0 4px">{html.escape(name)}</h2>
<p style="margin:0 0 12px">{' &nbsp; '.join(legend) or 'no map items'}</p>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">
<image href="data:image/png;base64,{b64}" width="{w}" height="{h}"/>
{''.join(shapes)}
</svg>
{''.join(tables)}
</body></html>
"""
    out = Path(args.output) if args.output else Path(f"{name}_overlay.html")
    out.write_text(doc, encoding="utf-8")
    total = sum(len(d.get("items", [])) for d in datasets.values())
    print(f"wrote {out} ({total} item(s) over {w}x{h} px)")
    print("  open it in a browser — the HTML embeds the drawing as base64 and is "
          "not for reading")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
