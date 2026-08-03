---
name: zipmaps
description: >-
  Create, validate, convert, and render transportable weld/flange/heat maps
  stored as .zipmap files — a deliberately flexible, portable package: a plain
  zip of a single construction drawing (single-page PDF and/or PNG), JSON
  map-item data with x/y + x2/y2 coordinates, the JSON Schemas that define each
  item type (open — you define the fields), and optionally the drawing's
  extraction record (bill of materials, drawing parameters).
  Use when the user works with .zipmap files, wants a portable weld map,
  flange map, heat map, or any drawing-plus-mapped-items package, or wants to
  translate a map out of one system's format into another's for API upload:
  scaffolding one, saving (which renders the PDF to PNG, converts PDF-point
  coordinates to pixels, bounds-checks, and schema-validates),
  opening/validating one, producing an HTML overlay or interactive HTML
  viewer, printing a paginated PDF map sheet (fpdf2), exporting a
  .zipmap.json interchange document (base64 PNG for web views + base64
  single-page PDF for turnover + extraction data + pixel-space items keyed
  by server-side schema id) to POST to an API, or working with .zipmapt
  templates. Multiple steps run as one chained command
  via scripts/zm.py
  (schemata-only archives that standardize item types). Image-only zipmaps
  need no third-party packages; PDF-backed ones need pymupdf.
license: MIT
---

# zipmaps — Transportable Weld/Flange/Heat Map Skill

*Developed by the [qcdatabase.ai](https://qcdatabase.ai) team.*

A `.zipmap` is a plain zip archive that packages **one drawing + its map-item
data + the schemas that define that data**, modeled on how `.skill` files
work. It is web-ready by construction: every valid zipmap contains a PNG of
the drawing, so a browser can display it with zero conversion.

```
example.zipmap
├── manifest.json               format version, drawing meta, render DPI
├── extracted_data.json         optional: the drawing's extraction record
├── schemata/<type>.schema.json one JSON Schema per map-item type
├── pdf/                        optional: drawing.pdf + PDF-space <type>.json
└── img/                        required: drawing.png + pixel-space <type>.json
```

The **`zipmap` Python library is bundled** under `src/` — every script adds
it to `sys.path` itself. Image-only zipmaps run on the **standard library
alone**; PDF-backed zipmaps additionally need `pymupdf`
(`pip install pymupdf`). If `jsonschema` is installed it is used for schema
validation; otherwise a bundled draft-07-subset validator takes over.

## The format is open on purpose

**zipmaps standardizes the container, not the content.** Only three things are
fixed, and they are the minimum needed for a drawing and its points to survive
a trip between systems:

| Fixed by the format | Entirely yours |
|---|---|
| The archive layout (`manifest.json`, `schemata/`, `img/`, optional `pdf/`) | Which item **types** exist — `weld`, `support`, `tie_in`, `punch`, `valve`, anything |
| The data-file wrapper: `space`, `width`, `height`, `schema`, `items` | Every **field** on an item beyond the five below — names, types, nesting, units, language |
| Five item fields: `id`, `x`, `y`, `x2`, `y2` (numbers, in bounds) | The whole of `extracted_data.json` — an opaque object the format never inspects |

JSON is usually a strictness tool; here the schemas are used the other way
round — as *documentation that travels*. A schema in `schemata/` says "this is
what my fields mean," not "this is what fields are allowed to be." So:

- `"additionalProperties": true` is the default posture. Keep extra fields;
  don't prune what you don't recognize.
- **Never rename, normalize, translate, or drop a source system's field names**
  to look more like the starters in `assets/starter_schemas/`. Those three
  files are examples that `init.py --types` copies — not a vocabulary the
  format endorses. If the source calls it `joint_no`, the zipmap calls it
  `joint_no`, and the schema you write describes `joint_no`.
- A new item type is a new schema file. It never requires a format revision,
  a code change, or permission.
- `.zipmapt` templates and server-side `schema_id`s exist for the same reason:
  the authority over field meaning lives with the project or the receiving
  system, never in this skill.

### Translating between systems

The common job this format is built for: **take a map that lives in system A's
shape and hand it to system B's API.** That mapping is judgment work — field
names differ, units differ, one system's `status` is another's
`bolt_up_state` — which is exactly what you (an AI) are for, while the
mechanical half stays scripted.

```
system A export  ──you map the fields──▶  schemata/*.schema.json + <type>.json
   (CSV, XML, a                             │
    vendor's JSON,                          ▼   scripts/zm.py save :: to_json
    a marked-up PDF)                   mymap.zipmap ──▶ mymap.zipmap.json ──▶ POST to B
```

Working rules for a translation:

1. **Write the schema to fit the data, not the data to fit a schema.** Read a
   sample of the source, name the types and fields it actually has, and author
   `schemata/<type>.schema.json` from that. Only `id`/`x`/`y`/`x2`/`y2` are
   non-negotiable — supply `x2`/`y2` equal to `x`/`y` if the source has no
   second point and the type is a plain pin.
2. **Carry unknown fields through.** A field you can't interpret still belongs
   in the item; describe it loosely (`{"type": "string"}`) or leave it to
   `additionalProperties`. Dropping it is data loss the receiver can't undo.
3. **Coordinates are the one thing you must get right**, and you don't compute
   them: put PDF-space numbers in `pdf/<type>.json` and let `save.py` derive
   pixels. Bounds and space are checked for you.
4. **Match the target's `schema_id`s at the end, not the field names up
   front.** Export names each dataset's server-side schema id; the receiving
   system validates the fields against its own definition. Get real ids from
   that system — never invent one.
5. If the target's schema genuinely demands different names, do that rename
   **once, explicitly, as the last step before export**, and say so — not
   silently while authoring.

The output is meant to be push-ready: `to_json.py` emits a single JSON object
(base64 PNG + base64 PDF + extraction record + pixel-space items grouped by
`schema_id`) that POSTs straight to the target endpoint with no unzipping and
no coordinate math on the receiving side.

## Learn the format first

| File | Covers |
|------|--------|
| `references/format_spec.md` | The normative `.zipmap` spec: layout, manifest, data files, coordinate spaces, the save pipeline, and a summary of the `.zipmap.json` document. **Start here.** |
| `references/schema_authoring.md` | Writing `schemata/*.schema.json` for new item types; the `zipmap.geometry` flag/rect hint; the `zipmap.schema_id` binding; validator subset. |
| `references/zipmap_json_spec.md` | The full `.zipmap.json` interchange spec, written for API implementers: every field, the receiver validation checklist, an envelope JSON Schema, Python/TypeScript reference decoders, sizing and security. Read when someone is **building or consuming an endpoint**. |

Key rules to keep in mind (all enforced by the scripts — don't re-derive
them by hand):

- **A zipmap without an image is invalid; without a PDF it's fine.** PNG only.
- **PDFs are single-page**, named `pdf/drawing.pdf`. One drawing per zipmap.
- **`pdf/` is authoritative when present** — saving regenerates the entire
  `img/` layer (PNG render + pixel-coordinate data) from it, every time.
  Never hand-edit `img/` files on a PDF-backed map; edit `pdf/` data instead.
- Data files pair with schemas by name: `img/weld.json` ↔
  `schemata/weld.schema.json`.
- Map-item `id` uniqueness is **not enforced** — do not "fix" duplicate IDs
  unless the user asks.
- `extracted_data.json` (optional, at the root) is the **drawing's own**
  extraction record — BOM, line number, title-block parameters. It has no
  schema here and needs none: **the only rule is that it is a JSON object.**
  See **Drawing extraction data** below.
- A `.zipmapt` is a **template**: the same archive with only `schemata/`
  inside. See **Templates** below.
- A `.zipmap.json` is the **interchange document**: the same map as one JSON
  object for APIs. See **Exporting to .zipmap.json** below.

## Templates: check for .zipmapt files FIRST

**Before creating any zipmap, look for `.zipmapt` files in the working
directory and project folder** (`Glob **/*.zipmapt`). A template is how a
project standardizes its item types, so when one exists its schemata are the
authority — open it and build on it instead of using the generic starters:

```bash
python scripts/zm.py open company_std.zipmapt -d newmap   # template -> ready working folder
# or graft the template's schemas onto a fresh scaffold:
python scripts/zm.py init newmap --from-template company_std.zipmapt --title "..."
```

Read the extracted schemas to learn each type's fields (size, schedule,
rating, …) and author the data files to match — the save pipeline will
validate against those exact schemata. If several templates exist and it's
unclear which applies, ask the user. To create a template from an existing
map or from starters:

```bash
python scripts/zm.py make_template mymap -o company_std.zipmapt   # from a folder or .zipmap
python scripts/zm.py make_template --types weld,flange -o std.zipmapt
```

## Run steps as one chain, not one at a time

Speed matters: **all deterministic work is scripted — never convert
coordinates, validate schemas, or check bounds by inference.** Every script
has `--help`.

`scripts/zm.py` runs any number of those scripts **in a single process**,
steps separated by `::`. Each separate `python scripts/X.py` costs ~145 ms of
interpreter and import startup — and a turn of your own. Chaining pays that
once:

```bash
python scripts/zm.py save mymap :: validate mymap :: to_json mymap :: render mymap
#   ^ 154 ms, one turn      (the same four as separate commands: 528 ms, four turns)
```

**When you already know the next steps, put them in one chain.** Only split
when a later step genuinely depends on your reading the earlier output (e.g.
you must inspect a validation failure before deciding what to fix). Add
`--json` for machine-readable JSON Lines, one object per step. `-k` continues
past a failure instead of stopping.

`zm.py <cmd>` takes that script's exact flags — `zm.py save --help` *is*
`save.py --help` — and a single command with no `::` behaves identically to
running the script directly. The individual scripts all still work unchanged.

| Script | Does |
|--------|------|
| `scripts/zm.py` | **The bundled runner** — every script below as a subcommand, chained with `::` in one process. Also `--file jobs.json` / `--stdin` for a long sequence, `--dry-run`, `--list`. **Prefer this whenever you have two or more steps in mind.** |
| `scripts/init.py` | Scaffold a working folder (`schemata/`, `pdf/`, `img/`) with starter schemas (`--types weld,flange,heat`) or a template's schemas (`--from-template std.zipmapt`), optional manifest meta, optional `--demo` placeholder drawing. |
| `scripts/save.py` | **The save pipeline** — single-page check, PNG render at `--dpi` (default 300), pixel-data derivation, bounds + schema validation, manifest write, zip. Only writes `<name>.zipmap` when everything passes. **Use this after every edit.** `--reuse-render` skips re-rasterizing when the PDF and DPI are unchanged. |
| `scripts/open.py` | Extract a `.zipmap` (or `.zipmapt` template) to a working folder, validate it, print a summary. Templates come out with empty `pdf/`+`img/` ready to fill. |
| `scripts/validate.py` | All checks, no zip — accepts a working folder, a `.zipmap`, a `.zipmapt`, or a `.zipmap.json`. Exit code 0/1; use it to answer "is this file good?". |
| `scripts/to_json.py` | **Export to `<name>.zipmap.json`** — base64 PNG (web) + base64 single-page PDF (turnover) + the extraction record + pixel-space items grouped by server-side `schema_id`, ready to POST. Takes a folder or a `.zipmap`. `--no-pdf` / `--no-extracted-data` / `--extracted-data FILE`. |
| `scripts/make_template.py` | Build a `.zipmapt` (schemata only) from a working folder, a `.zipmap`, or `--types` starters. |
| `scripts/render.py` | Self-contained HTML overlay of the `img/` layer (embedded PNG + SVG pins/rects/labels, color per type). Zero deps; the fastest visual proof. |
| `scripts/view.py` | Interactive single-file HTML viewer: pan/zoom, layer toggles, clickable items with a detail panel. Zero deps. Its `build_viewer_html()` function and embedded `ZIPMAP` JSON block are the reference pattern for building a custom web viewer or editor. |
| `scripts/print_pdf.py` | Print a zipmap to a paginated PDF (drawing overlay page + item tables) with **fpdf2** (`pip install fpdf2`). Rarely needed, but it is the worked guide for constructing maps as PDFs — pixel→page-mm math, callout drawing, tabulation. |
| `scripts/pdf2img.py` | Standalone single-page PDF → PNG at a DPI (save.py already does this). |
| `scripts/transform.py` | Standalone PDF-space → pixel-space data conversion (save.py already does this). Pure math with explicit dims, so it works without pymupdf. |

## Typical flows

**Create a zipmap from a PDF drawing** — scaffold first, because you have to
put the drawing and data in before anything can be saved:

```bash
python scripts/zm.py init mymap --types weld --title "Unit 3 CW Iso" --drawing-number ISO-3041 --revision A
# put the drawing at mymap/pdf/drawing.pdf
# write mymap/pdf/weld.json  (space "pdf", width/height = page points, items[])
# optionally write mymap/extracted_data.json  (any JSON object — BOM, params)
python scripts/zm.py save mymap :: render mymap    # -> mymap.zipmap + overlay, one turn
```

**Create an image-only zipmap** (no PDF, no dependencies): same, but drop a
PNG at `mymap/img/drawing.png` and author `mymap/img/weld.json` in pixels.

**Open / inspect / verify someone else's zipmap** — one chain, one turn:

```bash
python scripts/zm.py open theirs.zipmap :: render theirs.zipmap
python scripts/zm.py validate theirs.zipmap        # just the verdict
```

**Edit an existing zipmap:** open it, edit the authoritative layer (`pdf/`
data if `source` is `"pdf"`, else `img/` data), then save again — chaining the
re-save with whatever you want to see afterwards:

```bash
python scripts/zm.py save mymap :: render mymap :: to_json mymap
```

Meta fields (`title`, `drawing_number`, `revision`, `created`) carry over
automatically; override with `save --title ...` etc. When the drawing itself
is untouched and you are only iterating on item data, add `--reuse-render` to
the save step: it skips re-rasterizing the PDF (which is most of a save's
cost) whenever the PDF's content hash and the DPI both still match.

## Drawing extraction data

Two different kinds of data attach to a drawing, and they are easy to
conflate:

| | Lives in | Defined by | Coordinates |
|---|---|---|---|
| **Map items** — welds, flanges, heats | `img/<type>.json` | `schemata/<type>.schema.json`, or a server-side `schema_id` | yes, x/y + x2/y2 |
| **Extraction record** — BOM, drawing parameters | `extracted_data.json` (one file, one object) | the **receiving system's** extraction schema | none |

The extraction record is what was read *off* the sheet: bill of materials,
line number, revision, tagged items, fluid service, title-block summary,
reference drawings. A drawing has exactly one, and it is a single JSON
object — not an array, not one file per extractor.

**The zipmap format enforces nothing about its contents.** It must parse and
it must be an object; that is the whole contract, deliberately, for the same
reason `schema_id` exists: the fields belong to the receiving system's
drawing-extraction schema (in QC Database, configured per document folder),
which versions independently. So:

- **Do not author a JSON Schema for it** and do not put it in `schemata/` —
  that directory is only for map-item types.
- **Do not invent, rename, normalize, or drop keys.** Copy through exactly
  what the extractor produced. Renaming `nps` to `size` silently corrupts
  the record for a receiver whose schema says `nps`.
- If you need to know the real field names for a project, get them from the
  tracking system (its drawing/document extraction schema), not from here.

```bash
# just write the file; save packs it and validate checks it is an object
python scripts/zm.py save mymap :: validate mymap        # -> reports the field shape
```

```python
from zipmap import load_extracted_data, write_extracted_data
write_extracted_data("mymap", extractor_output)   # -> mymap/extracted_data.json
record = load_extracted_data("mymap")             # None when the map has none
```

It travels into the `.zipmap.json` as `extracted_data`, verbatim.

## Exporting to .zipmap.json

When the map has to reach an **API** rather than a person or a filesystem,
export it. A `.zipmap.json` is one JSON object — the drawing as base64 PNG
*and* as base64 single-page PDF, the extraction record, plus every item in
pixel coordinates — so an endpoint can accept it whole with no unzipping and
no PDF math:

```json
{ "zipmap_json": "1.1", "image": {"format": "png", "width": 800, "height": 600},
  "pdf": {"format": "pdf", "width": 792, "height": 612, "pages": 1},
  "extracted_data": {"line_number": "...", "bill_of_materials": [ {...} ]},
  "b64": "iVBORw0KGgo...", "pdf_b64": "JVBERi0x...",
  "map_item_datasets": [ {"schema_id": "wsc_01H2XYZ", "map_items": [ {...} ]} ] }
```

**Both drawings travel when there are both.** The PNG is what a browser puts
on a canvas — and it is the coordinate space every item is measured in; it
is the one drawing the format requires. The PDF is the print master a
turnover package needs at full vector fidelity, which a raster can never be
turned back into. `pdf_b64` is **optional in the format** — an image-only
map has none to send, and a document without it is fully valid. Requiring
one is a *receiving system's* policy (QC Database has it; other trackers
need not), not a rule of the interchange format. It is included **by
default** whenever the map is PDF-backed; only pass `--no-pdf` when the user
explicitly wants a smaller, web-only payload. If a destination requires one
and the map is image-only, the map must be rebuilt from the PDF, not
patched.

The document **drops the JSON Schemas and names a `schema_id` instead**,
pointing at the map-item schema held server-side in the weld/flange/heat
tracking system. So a `schema_id` is **required for every type** — the
export fails without one. Bind ids into the schemata once and they travel
with the zipmap (and with any `.zipmapt` made from it):

```bash
# bind the ids once, export, and verify the document — one turn
python scripts/zm.py to_json mymap --schema-id weld=wsc_01H2XYZ --bind \
                  :: validate mymap.zipmap.json
python scripts/zm.py to_json mymap                                # later: no flags needed
python scripts/zm.py to_json mymap.zipmap -o payload.json --compact   # from an archive
python scripts/to_json.py mymap --stdout --compact | curl -X POST -d @- ...

python scripts/to_json.py mymap --extracted-data bom.json   # record from an extractor
python scripts/to_json.py mymap --no-pdf                    # web-only payload
python scripts/to_json.py mymap --no-extracted-data         # omit the record
```

(Use `to_json.py` directly for `--stdout`: the document goes to stdout, so it
wants its own invocation — `zm.py --json` refuses that combination rather than
wrap a base64 PNG in a JSON line.)

Get real ids from the tracking system's map-item schema list — **never
invent one**; if none is known, ask the user rather than guessing. Export
reads the `img/` layer, so **run `save.py` first** on a PDF-backed map to
be sure that layer is current.

Export is one-way: a `.zipmap.json` can't become a `.zipmap` by itself,
because the schemata it dropped are what the archive format requires. (The
PDF now survives the trip, so the loss is narrower than it was — but the
schemas are still gone.)

When the user is **writing the endpoint** rather than sending to one, hand
them `references/zipmap_json_spec.md` — it is the complete receiver-side
specification (validation order, envelope JSON Schema, working decoders,
payload sizing, security).

## Always save through the pipeline

**Never zip a zipmap folder by hand** and never write a `.zipmap` any other
way — `save.py` is the only path, because it is what guarantees the format's
contract (image present, coordinates in bounds, data matching schemata,
manifest accurate). A `.zipmap` that exists must be a `.zipmap` that
validates. If a save fails, fix the reported errors in the working folder
and save again; don't work around the gate.

## Authoring map items

The wrapper of a data file is fixed; only `items` vary by type:

```json
{ "space": "pdf", "width": 792, "height": 612, "schema": "weld",
  "items": [ { "id": "W-101", "x": 220, "y": 300, "x2": 265, "y2": 340,
               "size": "2\"", "schedule": "80", "material": "A106-B" } ] }
```

- `(x, y)` = the map point; `(x2, y2)` = label-flag anchor, or opposite
  corner when the type's schema hints `"zipmap": {"geometry": "rect"}`.
- PDF space: points, origin **bottom-left**, y up. Image space: pixels,
  origin **top-left**, y down. The pipeline converts; you never do.
- **`id`, `x`, `y`, `x2`, `y2` are the only fields the format knows about.**
  Everything beside them (`size`, `schedule`, `material` above) is that
  project's vocabulary, carried verbatim.
- New item type = new schema file, no format change: copy the closest starter
  from `assets/starter_schemas/` — or write one from scratch when none is
  close, which is normal — adjust fields, save. See
  `references/schema_authoring.md`.

## Worked example

`examples/simple_weld_map/` is a complete image-only working folder (drawing
PNG, weld and heat data, schemas, manifest, and an `extracted_data.json`
showing a realistic BOM record). Copy it as a template or use it to test:

```bash
python scripts/zm.py validate examples/simple_weld_map \
                  :: save examples/simple_weld_map -o /tmp/simple_weld_map.zipmap
# its schemas carry no schema_id (ids are server-specific), so supply them to export:
python scripts/zm.py to_json examples/simple_weld_map \
    --schema-id weld=<id> --schema-id heat=<id> -o /tmp/simple_weld_map.zipmap.json
```

## Present the result

After creating or modifying a zipmap, tell the user the archive path and
give them the `render.py` HTML overlay (or a summary from `open.py`) so they
can see their items on the drawing — the overlay is the human-readable
deliverable. Use `view.py` instead when the user wants to explore the map
(pan/zoom, click items for their fields), `print_pdf.py` when they ask for a
printable/PDF copy, and `to_json.py` when the destination is an API rather
than a person.
