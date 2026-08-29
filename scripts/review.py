"""Render a zipmap as a throw-away HTML page for human review.

The page is a pre-upload checkstand: a reviewer opens it, eyeballs every
label against the drawing, and only then sends the map to a weld tracking
system (e.g. QC Database). It is 100% deterministic — the zipmap's required
PNG plus its img/ data files, rendered as-is with front-end tooling only.
No backend, no dependencies, one file you can delete afterwards.

What the page does:

    - tabs below the image, one per map-item type: schema name + item count
    - the active type's labels render at 50% opacity in its prominent color;
      every other type renders at 20%; clicking the active tab deselects it
      (all layers drop to 20%)
    - below the tabs, one table per type with that type's complete JSON
      data — every type's table is always shown, whatever tab is active
    - the first column is the text label drawn at each item's x/y; click any
      other column header to use that column as the label instead — a
      render-only, in-memory swap that never touches the data

Usage:
    python scripts/review.py mymap                # folder -> mymap_review.html
    python scripts/review.py mymap.zipmap -o check.html
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import struct
import sys
import zipfile
from pathlib import Path

import _bootstrap  # noqa: F401
from view import PALETTE, read_map


def build_review_html(
    name: str,
    png: bytes,
    manifest: dict,
    datasets: dict[str, dict],
    schemas: dict[str, dict],
) -> str:
    """Return the self-contained review page as a string."""
    if png[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("img drawing is not a PNG")
    width, height = struct.unpack(">II", png[16:24])

    types = []
    for i, stem in enumerate(sorted(datasets)):
        items = datasets[stem].get("items", [])
        # column order = field order as first seen across the items, so the
        # table shows the data exactly as authored and column 1 (usually id)
        # is the default map label
        columns: list[str] = []
        for item in items:
            if isinstance(item, dict):
                for k in item:
                    if k not in columns:
                        columns.append(k)
        types.append(
            {
                "name": stem,
                "color": PALETTE[i % len(PALETTE)],
                "geometry": (schemas.get(stem, {}).get("zipmap") or {}).get("geometry", "flag"),
                "columns": columns,
                "items": items,
            }
        )

    payload = {"name": name, "width": width, "height": height,
               "manifest": manifest, "types": types}
    # "</" must not appear literally inside a <script> block.
    zipmap_json = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    b64 = base64.b64encode(png).decode("ascii")

    meta_bits = [
        html.escape(str(manifest[k]))
        for k in ("title", "drawing_number", "revision")
        if manifest.get(k)
    ]
    subtitle = " &middot; ".join(meta_bits) or f"{width} &times; {height} px"

    return (
        REVIEW_TEMPLATE.replace("__NAME__", html.escape(name))
        .replace("__SUBTITLE__", subtitle)
        .replace("__PNG_B64__", b64)
        .replace("__ZIPMAP_JSON__", zipmap_json)
    )


# Plain JS, same recipe as view.py: state -> render() redraws everything.
# State is {active: type name or null, labelKey: {type: column}} and nothing
# in ZIPMAP is ever mutated — the label swap is purely a render choice.
REVIEW_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__NAME__ — zipmap review</title>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; font-family: system-ui, sans-serif; background: #f4f4f2; color: #222; }
  header { padding: 10px 16px; background: #22303d; color: #fff;
           display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; }
  header h1 { font-size: 16px; margin: 0; }
  header .sub { font-size: 12px; opacity: 0.75; }
  header .note { margin-left: auto; font-size: 11px; opacity: 0.6; }
  #tabs { display: flex; gap: 6px; padding: 0 16px 10px; flex-wrap: wrap; cursor: pointer; }
  #tabs button { font: inherit; font-size: 13px; padding: 6px 14px; cursor: pointer;
                 border: 1px solid #ccc; border-top: none; background: #e9e9e6;
                 border-radius: 0 0 6px 6px; color: #444; }
  #tabs button.active { background: #fff; font-weight: 700; border-bottom-width: 3px; }
  #tabs button .n { opacity: 0.65; font-weight: 400; }
  #drawing { margin: 10px 16px 0; background: #fff; border: 1px solid #ccc; }
  #drawing svg { display: block; width: 100%; height: auto; }
  #tablewrap { margin: 12px 16px 24px; cursor: pointer; }
  #tablewrap .tip { font-size: 12px; color: #666; margin: 0 0 6px; }
  #tablewrap h3 { font-size: 15px; margin: 18px 0 6px; }
  #tablewrap .tw { overflow-x: auto; }
  table { border-collapse: collapse; background: #fff; font-size: 13px; min-width: 50%;
          cursor: pointer; }
  th, td { border: 1px solid #ddd; padding: 4px 10px; text-align: left; white-space: nowrap; }
  th { cursor: pointer; user-select: none; background: #f0f0ee; position: sticky; top: 0; }
  th:hover { background: #e2e8ee; }
  th.labelcol { color: #fff; }
  tr:nth-child(even) td { background: #fafaf8; }
</style></head><body>
<header>
  <h1>__NAME__</h1><span class="sub">__SUBTITLE__</span>
  <span class="note">throw-away review page — data is read-only</span>
</header>
<div id="drawing"><svg id="svg" xmlns="http://www.w3.org/2000/svg"></svg></div>
<div id="tabs"></div>
<div id="tablewrap"></div>
<script>
const ZIPMAP = __ZIPMAP_JSON__;   // rendered as-is, never mutated
const PNG_URI = "data:image/png;base64,__PNG_B64__";
const W = ZIPMAP.width, H = ZIPMAP.height;
const FS = Math.max(12, Math.min(W, H) * 0.018);

const state = {
  active: ZIPMAP.types.length ? ZIPMAP.types[0].name : null,
  // per-type label column; defaults to the table's first column
  labelKey: Object.fromEntries(ZIPMAP.types.map(t => [t.name, t.columns[0] ?? "id"])),
};

function esc(s) { return String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
function cell(v) { return v === undefined || v === null ? "" : (typeof v === "object" ? JSON.stringify(v) : String(v)); }

function markerSVG(t, item) {
  const x = item.x, y = item.y, x2 = item.x2 ?? x, y2 = item.y2 ?? y;
  const label = esc(cell(item[state.labelKey[t.name]]) || "?");
  if (t.geometry === "rect") {
    const rx = Math.min(x, x2), ry = Math.min(y, y2);
    return `<rect x="${rx}" y="${ry}" width="${Math.abs(x2-x)}" height="${Math.abs(y2-y)}"
      fill="${t.color}" fill-opacity="0.25" stroke="${t.color}" stroke-width="${Math.max(1.5, FS*0.12)}"/>
      <text x="${rx + FS*0.3}" y="${ry + FS}" fill="${t.color}" font-size="${FS}"
      font-family="sans-serif" font-weight="bold">${label}</text>`;
  }
  const anchor = x2 >= x ? "start" : "end";
  const dx = x2 >= x ? FS * 0.4 : -FS * 0.4;
  return `<line x1="${x}" y1="${y}" x2="${x2}" y2="${y2}" stroke="${t.color}" stroke-width="${Math.max(1.5, FS*0.1)}"/>
    <circle cx="${x}" cy="${y}" r="${Math.max(3, FS*0.28)}" fill="${t.color}"/>
    <text x="${x2 + dx}" y="${y2 + FS*0.35}" fill="${t.color}" font-size="${FS}"
    font-family="sans-serif" font-weight="bold" text-anchor="${anchor}">${label}</text>`;
}

function renderTabs() {
  document.getElementById("tabs").innerHTML = ZIPMAP.types.map(t => {
    const on = t.name === state.active;
    return `<button data-tab="${esc(t.name)}" class="${on ? "active" : ""}"
      style="border-bottom-color:${t.color};${on ? "color:" + t.color : ""}">
      ${esc(t.name)} <span class="n">(${t.items.length})</span></button>`;
  }).join("");
}

function renderOverlay() {
  const layers = ZIPMAP.types.map(t => {
    const op = t.name === state.active ? 0.5 : 0.2;
    const shapes = t.items.filter(it => it && typeof it === "object").map(it => markerSVG(t, it));
    return `<g opacity="${op}">${shapes.join("")}</g>`;
  });
  const svg = document.getElementById("svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.innerHTML = `<image href="${PNG_URI}" width="${W}" height="${H}"/>` + layers.join("");
}

function renderTables() {
  const wrap = document.getElementById("tablewrap");
  if (!ZIPMAP.types.length) { wrap.innerHTML = ""; return; }
  const parts = [`<p class="tip">Click a column header to use it as the map label
    (render-only; the data itself never changes).</p>`];
  for (const t of ZIPMAP.types) {
    const lk = state.labelKey[t.name];
    const head = t.columns.map(c =>
      `<th data-type="${esc(t.name)}" data-col="${esc(c)}" class="${c === lk ? "labelcol" : ""}"
       style="${c === lk ? "background:" + t.color : ""}" title="use as map label">${esc(c)}</th>`
    ).join("");
    const rows = t.items.map(it =>
      `<tr>${t.columns.map(c => `<td>${esc(cell(it && it[c]))}</td>`).join("")}</tr>`
    ).join("");
    parts.push(`<h3 style="color:${t.color}">${esc(t.name)} <span style="opacity:0.65;font-weight:400">(${t.items.length})</span></h3>
      <div class="tw"><table><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></div>`);
  }
  wrap.innerHTML = parts.join("");
}

function renderAll() { renderTabs(); renderOverlay(); renderTables(); }

document.getElementById("tabs").addEventListener("click", e => {
  const btn = e.target.closest("[data-tab]");
  if (!btn) return;
  state.active = btn.dataset.tab === state.active ? null : btn.dataset.tab;
  renderTabs();
  renderOverlay();
});

document.getElementById("tablewrap").addEventListener("click", e => {
  const th = e.target.closest("[data-col]");
  if (!th) return;
  state.labelKey[th.dataset.type] = th.dataset.col;
  renderOverlay();
  renderTables();
});

renderAll();
</script></body></html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("target", help="zipmap working folder or .zipmap file")
    parser.add_argument("-o", "--output", help="output HTML path (default: <name>_review.html)")
    args = parser.parse_args(argv)

    target = Path(args.target)
    try:
        png, manifest, datasets, schemas = read_map(target)
        name = target.stem if target.is_file() else target.name
        doc = build_review_html(name, png, manifest, datasets, schemas)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    out = Path(args.output) if args.output else Path(f"{name}_review.html")
    out.write_text(doc, encoding="utf-8")
    total = sum(len(d.get("items", [])) for d in datasets.values())
    print(f"wrote {out} ({total} item(s), {len(datasets)} type(s))")
    print("  open it in a browser — the HTML embeds the drawing as base64 and is "
          "not for reading")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
