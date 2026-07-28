"""Build an interactive, self-contained HTML viewer for a zipmap.

Unlike render.py (a static SVG snapshot), this produces a small single-file
web app: the drawing PNG plus every img/ data file and schema are embedded
as JSON, and client-side JavaScript draws the overlay. It supports:

    - wheel zoom (about the cursor) and drag pan
    - per-type layer toggles
    - a sidebar item list; click a row or a marker to select an item
    - a detail panel showing every field of the selected item

It is intentionally a *basic reference implementation*: the embedded
``ZIPMAP`` JSON object is exactly the web-ready layer of the format
(manifest + img/ data + schemata), so a custom viewer or editor starts from
the same three inputs and replaces the JavaScript. Zero dependencies.

Usage:
    python scripts/view.py mymap                 # folder -> mymap_viewer.html
    python scripts/view.py mymap.zipmap -o v.html
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
from zipmap import DRAWING_PNG, IMG_DIR, MANIFEST, SCHEMATA_DIR

PALETTE = ["#c0392b", "#1f618d", "#1e8449", "#9a5b00", "#6c3483", "#148f77"]


def read_map(target: Path) -> tuple[bytes, dict, dict[str, dict], dict[str, dict]]:
    """Read the web-ready layer of a working folder or .zipmap archive.

    Returns (png_bytes, manifest, {type: data_dict}, {type: schema_dict}).
    The manifest may be {} for a working folder that has never been saved.
    """
    manifest: dict = {}
    datasets: dict[str, dict] = {}
    schemas: dict[str, dict] = {}
    if target.is_file():
        with zipfile.ZipFile(target) as zf:
            names = set(zf.namelist())
            png_name = f"{IMG_DIR}/{DRAWING_PNG}"
            if png_name not in names:
                raise FileNotFoundError(f"{target} has no {png_name}")
            png = zf.read(png_name)
            if MANIFEST in names:
                manifest = json.loads(zf.read(MANIFEST))
            for n in sorted(names):
                if n.startswith(f"{IMG_DIR}/") and n.endswith(".json"):
                    datasets[Path(n).stem] = json.loads(zf.read(n))
                elif n.startswith(f"{SCHEMATA_DIR}/") and n.endswith(".schema.json"):
                    schemas[Path(n).name[: -len(".schema.json")]] = json.loads(zf.read(n))
        return png, manifest, datasets, schemas
    png_path = target / IMG_DIR / DRAWING_PNG
    if not png_path.is_file():
        raise FileNotFoundError(f"{png_path} not found")
    if (target / MANIFEST).is_file():
        manifest = json.loads((target / MANIFEST).read_text(encoding="utf-8"))
    for p in sorted((target / IMG_DIR).glob("*.json")):
        datasets[p.stem] = json.loads(p.read_text(encoding="utf-8"))
    for p in sorted((target / SCHEMATA_DIR).glob("*.schema.json")):
        schemas[p.name[: -len(".schema.json")]] = json.loads(p.read_text(encoding="utf-8"))
    return png_path.read_bytes(), manifest, datasets, schemas


def build_viewer_html(
    name: str,
    png: bytes,
    manifest: dict,
    datasets: dict[str, dict],
    schemas: dict[str, dict],
) -> str:
    """Return a self-contained HTML viewer page as a string.

    ``datasets`` and ``schemas`` are keyed by type stem (e.g. "weld"). The
    page embeds one JSON object, ``ZIPMAP``, mirroring the format's web
    contract: readers need only manifest + img/ data + schemata. Everything
    visual happens in the page's JavaScript, so this function is the whole
    Python side of a viewer.
    """
    if png[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("img drawing is not a PNG")
    width, height = struct.unpack(">II", png[16:24])

    types = []
    for i, stem in enumerate(sorted(datasets)):
        types.append(
            {
                "name": stem,
                "color": PALETTE[i % len(PALETTE)],
                "geometry": (schemas.get(stem, {}).get("zipmap") or {}).get("geometry", "flag"),
                "items": datasets[stem].get("items", []),
            }
        )

    payload = {
        "name": name,
        "width": width,
        "height": height,
        "manifest": manifest,
        "types": types,
    }
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
        VIEWER_TEMPLATE.replace("__NAME__", html.escape(name))
        .replace("__SUBTITLE__", subtitle)
        .replace("__PNG_B64__", b64)
        .replace("__ZIPMAP_JSON__", zipmap_json)
    )


# The client side. Kept deliberately plain (no framework, no build step) so
# it reads as a recipe: state -> renderOverlay() redraws the SVG, and every
# interaction just mutates state and re-renders.
VIEWER_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__NAME__ — zipmap viewer</title>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; font-family: system-ui, sans-serif; height: 100vh;
         display: flex; flex-direction: column; background: #f4f4f2; }
  header { padding: 8px 14px; background: #22303d; color: #fff;
           display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; }
  header h1 { font-size: 16px; margin: 0; }
  header .sub { font-size: 12px; opacity: 0.75; }
  header .toggles { margin-left: auto; display: flex; gap: 12px; font-size: 13px; }
  header .toggles label { cursor: pointer; user-select: none; }
  #main { flex: 1; display: flex; min-height: 0; }
  #stage { flex: 1; overflow: hidden; cursor: grab; background: #d9d9d4; position: relative; }
  #stage.panning { cursor: grabbing; }
  #stage svg { display: block; }
  #hint { position: absolute; bottom: 8px; left: 10px; font-size: 11px; color: #555; }
  #reset { position: absolute; top: 8px; left: 10px; font-size: 12px; }
  aside { width: 280px; border-left: 1px solid #ccc; background: #fff;
          display: flex; flex-direction: column; min-height: 0; }
  #list { flex: 1; overflow-y: auto; }
  #list h3 { font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em;
             margin: 10px 12px 4px; }
  #list .row { padding: 4px 12px; font-size: 13px; cursor: pointer; }
  #list .row:hover { background: #eef3f7; }
  #list .row.sel { background: #dbe8f3; font-weight: 600; }
  #detail { border-top: 1px solid #ccc; padding: 10px 12px; font-size: 12px;
            max-height: 40%; overflow-y: auto; }
  #detail table { border-collapse: collapse; width: 100%; }
  #detail td { padding: 2px 4px; vertical-align: top; border-bottom: 1px solid #eee; }
  #detail td:first-child { color: #666; white-space: nowrap; }
  .marker { cursor: pointer; }
</style></head><body>
<header>
  <h1>__NAME__</h1><span class="sub">__SUBTITLE__</span>
  <span class="toggles" id="toggles"></span>
</header>
<div id="main">
  <div id="stage">
    <svg id="svg" xmlns="http://www.w3.org/2000/svg"></svg>
    <button id="reset">reset view</button>
    <span id="hint">wheel = zoom &nbsp; drag = pan &nbsp; click = select</span>
  </div>
  <aside>
    <div id="list"></div>
    <div id="detail">Click an item on the drawing or in the list.</div>
  </aside>
</div>
<script>
const ZIPMAP = __ZIPMAP_JSON__;   // manifest + img-layer data, verbatim
const PNG_URI = "data:image/png;base64,__PNG_B64__";

// ---- state ---------------------------------------------------------------
const state = {
  scale: 1, tx: 0, ty: 0,                       // view transform (screen px)
  visible: Object.fromEntries(ZIPMAP.types.map(t => [t.name, true])),
  selected: null,                               // {type, index} or null
};

const svg = document.getElementById("svg");
const stage = document.getElementById("stage");
const W = ZIPMAP.width, H = ZIPMAP.height;
const FS = Math.max(12, Math.min(W, H) * 0.018); // label font size, drawing px

// ---- rendering -----------------------------------------------------------
function markerSVG(t, item, i) {
  const sel = state.selected && state.selected.type === t.name && state.selected.index === i;
  const stroke = sel ? Math.max(3, FS * 0.2) : Math.max(1.5, FS * 0.1);
  const x = item.x, y = item.y, x2 = item.x2 ?? x, y2 = item.y2 ?? y;
  const label = esc(String(item.id ?? "?"));
  const g = `<g class="marker" data-type="${t.name}" data-index="${i}">`;
  if (t.geometry === "rect") {
    const rx = Math.min(x, x2), ry = Math.min(y, y2);
    return g + `<rect x="${rx}" y="${ry}" width="${Math.abs(x2-x)}" height="${Math.abs(y2-y)}"
      fill="${t.color}" fill-opacity="${sel ? 0.28 : 0.12}" stroke="${t.color}" stroke-width="${stroke}"/>
      <text x="${rx + FS*0.3}" y="${ry + FS}" fill="${t.color}" font-size="${FS}"
      font-family="sans-serif" font-weight="bold">${label}</text></g>`;
  }
  const anchor = x2 >= x ? "start" : "end";
  const dx = x2 >= x ? FS * 0.4 : -FS * 0.4;
  return g + `<line x1="${x}" y1="${y}" x2="${x2}" y2="${y2}" stroke="${t.color}" stroke-width="${stroke}"/>
    <circle cx="${x}" cy="${y}" r="${Math.max(3, FS*0.28) * (sel ? 1.5 : 1)}" fill="${t.color}"/>
    <text x="${x2 + dx}" y="${y2 + FS*0.35}" fill="${t.color}" font-size="${FS}"
    font-family="sans-serif" font-weight="bold" text-anchor="${anchor}">${label}</text></g>`;
}

function renderOverlay() {
  const shapes = ZIPMAP.types
    .filter(t => state.visible[t.name])
    .flatMap(t => t.items.map((item, i) => markerSVG(t, item, i)));
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("width", W * state.scale);
  svg.setAttribute("height", H * state.scale);
  svg.style.transform = `translate(${state.tx}px, ${state.ty}px)`;
  svg.innerHTML = `<image href="${PNG_URI}" width="${W}" height="${H}"/>` + shapes.join("");
}

function renderList() {
  const parts = [];
  for (const t of ZIPMAP.types) {
    parts.push(`<h3 style="color:${t.color}">${esc(t.name)} (${t.items.length})</h3>`);
    t.items.forEach((item, i) => {
      const sel = state.selected && state.selected.type === t.name && state.selected.index === i;
      parts.push(`<div class="row${sel ? " sel" : ""}" data-type="${t.name}" data-index="${i}">
        ${esc(String(item.id ?? "(no id)"))}</div>`);
    });
  }
  document.getElementById("list").innerHTML = parts.join("");
}

function renderDetail() {
  const el = document.getElementById("detail");
  if (!state.selected) { el.textContent = "Click an item on the drawing or in the list."; return; }
  const t = ZIPMAP.types.find(t => t.name === state.selected.type);
  const item = t.items[state.selected.index];
  const rows = Object.entries(item)
    .map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(JSON.stringify(v))}</td></tr>`);
  el.innerHTML = `<b style="color:${t.color}">${esc(t.name)}</b><table>${rows.join("")}</table>`;
}

function renderAll() { renderOverlay(); renderList(); renderDetail(); }
function esc(s) { return s.replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }

// ---- interactions ----------------------------------------------------------
function select(type, index) {
  const same = state.selected && state.selected.type === type && state.selected.index === index;
  state.selected = same ? null : { type, index };
  renderAll();
}

document.getElementById("main").addEventListener("click", e => {
  const hit = e.target.closest("[data-type]");
  if (hit) select(hit.dataset.type, Number(hit.dataset.index));
});

// layer toggles
const toggles = document.getElementById("toggles");
toggles.innerHTML = ZIPMAP.types.map(t =>
  `<label style="color:${t.color}"><input type="checkbox" checked data-layer="${t.name}"> ${esc(t.name)}</label>`
).join("");
toggles.addEventListener("change", e => {
  state.visible[e.target.dataset.layer] = e.target.checked;
  renderOverlay();
});

// zoom about the cursor: keep the drawing point under the mouse fixed
stage.addEventListener("wheel", e => {
  e.preventDefault();
  const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
  const rect = stage.getBoundingClientRect();
  const mx = e.clientX - rect.left, my = e.clientY - rect.top;
  state.tx = mx - (mx - state.tx) * factor;
  state.ty = my - (my - state.ty) * factor;
  state.scale = Math.min(20, Math.max(0.05, state.scale * factor));
  renderOverlay();
}, { passive: false });

// drag to pan
let pan = null;
stage.addEventListener("pointerdown", e => {
  pan = { x: e.clientX - state.tx, y: e.clientY - state.ty };
  stage.classList.add("panning");
  stage.setPointerCapture(e.pointerId);
});
stage.addEventListener("pointermove", e => {
  if (!pan) return;
  state.tx = e.clientX - pan.x;
  state.ty = e.clientY - pan.y;
  renderOverlay();
});
stage.addEventListener("pointerup", () => { pan = null; stage.classList.remove("panning"); });

function fitView() {
  const pad = 20;
  state.scale = Math.min((stage.clientWidth - pad) / W, (stage.clientHeight - pad) / H);
  state.tx = (stage.clientWidth - W * state.scale) / 2;
  state.ty = (stage.clientHeight - H * state.scale) / 2;
  renderOverlay();
}
document.getElementById("reset").addEventListener("click", fitView);

renderAll();
fitView();
</script></body></html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("target", help="zipmap working folder or .zipmap file")
    parser.add_argument("-o", "--output", help="output HTML path (default: <name>_viewer.html)")
    args = parser.parse_args(argv)

    target = Path(args.target)
    try:
        png, manifest, datasets, schemas = read_map(target)
        name = target.stem if target.is_file() else target.name
        doc = build_viewer_html(name, png, manifest, datasets, schemas)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    out = Path(args.output) if args.output else Path(f"{name}_viewer.html")
    out.write_text(doc, encoding="utf-8")
    total = sum(len(d.get("items", [])) for d in datasets.values())
    print(f"wrote {out} ({total} item(s), {len(datasets)} type(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
