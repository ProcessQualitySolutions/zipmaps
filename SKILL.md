---
name: zipmaps
description: >-
  Create, validate, convert, and render weld/flange/heat maps stored as .zipmap
  files — a flexible zip of one drawing (single-page PDF and/or PNG), JSON
  map-item data with x/y + x2/y2 coordinates, open JSON Schemas defining each
  item type, and optionally the extraction record. Use when the user handles
  .zipmap/.zipmapt files, wants a portable weld map, flange map, heat map, or
  any drawing-plus-items package, or translates a map between system formats
  for API upload: scaffolding, saving (renders PDF to PNG, converts PDF points
  to pixels, bounds-checks, schema-validates), capturing pre-labeled weld/tag
  numbers off the PDF text layer (labels.py, explicit request only),
  HTML overlay or interactive viewer, paginated PDF map sheet (fpdf2), or exporting a .zipmap.json interchange doc for API POST.
  For many drawings, write a conversion script/skill/MCP server into this
  standard rather than hand-mapping each. Steps chain via scripts/zm.py.
  Image-only zipmaps need only the stdlib; PDF-backed ones need pymupdf.
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

## One drawing is inference. A project is a converter you write.

You can absolutely build a zipmap by raw inference — read the source, author
the schemas and data files by hand, save. For **one** drawing that is the
right move, and the rest of this skill assumes it.

But a real construction project is never one drawing. It is a pipe rack with
180 isometrics, a vendor export covering a whole unit, a folder of marked-up
PDFs from one contractor in one consistent format. Hand-authoring 180 maps by
inference is slow, expensive, and — worse — **inconsistent**: item 4,000 gets
mapped by a differently-primed model than item 12, and nothing catches the
drift.

**So: after the first one or two maps, stop inferring and write the
converter.** Your job shifts from *doing the conversion* to *building the
thing that does the conversion*, tailored to the source format in front of
you.

```
drawing 1  ──inference──▶  a working zipmap        (you learn the source shape here)
drawing 2  ──inference──▶  a second one            (confirms the pattern, exposes edge cases)
drawings 3..N ──────────▶  YOU WRITE A CONVERTER ──▶ zipmaps, deterministically
```

**This skill is the standard, not the converter.** It defines what a valid
`.zipmap` is and gives you the pipeline that guarantees it (`save`,
`validate`, `to_json`). It deliberately does **not** ship an importer for
anyone's source format, because there is no such thing as *the* source
format — it's a CSV this week, a Navisworks export next week, an XML
schedule after that. The converter is the piece that has to be written fresh
for each user's data, and writing it is your job.

### What to build

Pick the delivery vehicle that fits how the user will actually run it:

| Build this | When |
|---|---|
| **A script** (`convert_<source>.py` in their repo) | The default. One source format, run from the command line or a loop over a folder. Fastest to write, easiest for them to read and tweak. |
| **A new skill** (its own `SKILL.md` + scripts) | The conversion needs judgment on every run — reading a drawing, deciding item types, resolving ambiguity — and they'll do it repeatedly with an AI in the loop. |
| **An MCP server** | The data lives behind an API or database, or the conversion should be callable from any Claude session/tool, not just this repo. |
| **A batch runner around the scripts** | The per-drawing mapping is already trivial and the real work is looping, retrying, and reporting across N drawings. |

Whatever the vehicle, the rules are the same:

1. **It emits into this format; it never reimplements it.** The converter's
   job ends at writing a working folder — `schemata/*.schema.json`,
   `pdf/<type>.json` (or `img/`), `manifest` meta, `extracted_data.json`. Then
   it calls `scripts/zm.py save … :: validate …` (or imports `zipmap` from
   `src/`) and lets the pipeline do coordinates, bounds, rendering, and
   packaging. **Never** hand-roll the zip, the PDF→PNG render, or the
   point→pixel math in a converter — that's exactly the duplication this
   format exists to prevent.
2. **Schemas are authored once, by you, from a sample — then reused.** Do the
   field-mapping judgment on drawings 1–2, freeze the result as a `.zipmapt`
   template, and have the converter graft that template onto every subsequent
   map (`init --from-template`). That is what keeps drawing 180 consistent
   with drawing 1.
3. **Field names still come through verbatim.** A converter makes the
   *mechanics* deterministic; it does not license renaming or dropping the
   source's fields. Same rules as above.
4. **It must be re-runnable and idempotent.** Sources get revised. Re-running
   over the same folder should reproduce the same zipmaps, not append or
   double-map.
5. **It reports, per drawing.** Which succeeded, which failed validation and
   why, which were skipped. On a 180-drawing run, a silent failure is the
   expensive kind. `zm.py --json -k` gives you machine-readable per-step
   results for exactly this.

### How to approach it

Ask what the source data actually is *before* mapping anything — a folder of
PDFs, a CSV export, a vendor JSON, a database, a set of DWGs. Then:

1. Get a representative sample and convert it by hand, through this skill.
2. Show the user that map (`render.py`) and confirm the field mapping is right.
   Do not scale up a mapping they haven't looked at.
3. Freeze the schemas into a `.zipmapt`.
4. Write the converter, run it over the sample, and check it reproduces the
   hand-built map.
5. Run the batch; report per-drawing results.
6. Hand them the converter as a durable artifact — it belongs in their repo,
   with a README, not in a scratch directory. Next month's drawings should
   not need an AI to re-derive it.

If the user asks for one map, give them one map. If the request or the folder
listing implies many, say plainly that you'll build a converter rather than
grind through them by inference, and get on with it.

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
| `scripts/render.py` | Self-contained HTML overlay of the `img/` layer (embedded PNG + SVG pins/rects/labels, color per type) **plus one data table per item type below the map** showing every field of every item. Zero deps; the fastest visual proof. |
| `scripts/review.py` | **Throw-away HTML review page** for a human to check a map before it is uploaded to a tracking system: tabs per item type (name + count), active type's labels at 50% opacity / others at 20%, full JSON data table below the image, and click-a-column-header to switch which field is drawn as the map label (render-only, never mutates data). Zero deps. Produce it **on request** when the user wants to review a map. |
| `scripts/view.py` | Interactive single-file HTML viewer: pan/zoom, layer toggles, clickable items with a detail panel. Zero deps. Its `build_viewer_html()` function and embedded `ZIPMAP` JSON block are the reference pattern for building a custom web viewer or editor. |
| `scripts/print_pdf.py` | Print a zipmap to a paginated PDF (drawing overlay page + item tables) with **fpdf2** (`pip install fpdf2`). Rarely needed, but it is the worked guide for constructing maps as PDFs — pixel→page-mm math, callout drawing, tabulation. |
| `scripts/labels.py` | **Capture pre-labeled drawings**: list every text label on the PDF with its bounding box (pymupdf text layer — deterministic, no AI), filter by `--pattern` regex, and `--emit <type>` a ready `pdf/<type>.json` of rect items sitting on the label text. See **Pre-labeled drawings** below. |
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

# send to QC Database: wrap in the request envelope, gzip, POST (trailing slash!)
python scripts/to_json.py mymap --stdout --compact \
  | jq -c '{package_id: "<package-uuid>", mode: "append", document: .}' \
  | gzip \
  | curl -X POST "https://<host>/api/mapping/projects/<project-uuid>/zipmaps/" \
         -H 'Content-Type: application/json' -H 'Content-Encoding: gzip' \
         -H 'Authorization: Bearer <token>' --data-binary @-

python scripts/to_json.py mymap --extracted-data bom.json   # record from an extractor
python scripts/to_json.py mymap --no-pdf                    # web-only payload
python scripts/to_json.py mymap --no-extracted-data         # omit the record
```

(Use `to_json.py` directly for `--stdout`: the document goes to stdout, so it
wants its own invocation — `zm.py --json` refuses that combination rather than
wrap a base64 PNG in a JSON line.)

Get real ids from the tracking system's map-item schema list — **never
invent one**; if none is known, ask the user rather than guessing. For QC
Database the `schema_id` must be the server's **MapItemSchema UUID** — the
server accepts nothing else: no slug, no name, no fallback. In particular,
the exporter's last-resort fallback to a schema's `$id` URI produces an id
the server cannot resolve, so never rely on it — fetch the UUID from the
schema list endpoint (or the `list_map_item_schemas` MCP tool) and bind it
explicitly with `--schema-id <type>=<uuid> --bind`. Export reads the `img/`
layer, so **run `save.py` first** on a PDF-backed map to be sure that layer
is current.

### Sending to QC Database

The live endpoint is:

```
POST /api/mapping/projects/{project_id}/zipmaps/
```

Four contract points that each independently kill an upload:

- **The path has no `/v1/` and the trailing slash is mandatory.** A
  slashless POST is caught by Django's `APPEND_SLASH` redirect, which
  drops the body and bypasses the gzip middleware — the retry arrives
  empty and un-decompressed.
- **The body is an envelope, not a bare document.** POSTing a raw
  `.zipmap.json` returns **422** every time. Wrap it:

  ```json
  { "package_id": "<uuid>", "mode": "append",
    "document": { "zipmap_json": "1.1", "b64": "…", "map_item_datasets": [ … ] } }
  ```

  `mode` is `"append"` (add items) or `"replace"` (supersede at the
  drawing level: any live drawing in the package sharing the same
  non-empty `drawing_number` is soft-deleted — the whole drawing and
  all its items — and a new drawing is created).
- **`schema_id` must be a MapItemSchema UUID** (see above).
- **Size limits are real and layered.** The edge returns **413 at
  ~32 MB on the wire**, so compress: with `Content-Encoding: gzip` the
  JSON path accepts up to a **40 MB base64 aggregate** (all `b64` +
  `pdf_b64` combined, pre-gzip). The multipart path caps at a **30 MB raw
  aggregate**. The PNG itself is capped at **40 megapixels**
  (width × height) — choose the render DPI so the sheet stays under it
  (an ANSI D sheet at 300 DPI is 6600 × 10200 ≈ 67 MP and will be
  rejected; at 200 DPI it is ≈ 30 MP and fits; letter at 300 DPI is
  ≈ 8.4 MP, never a problem).

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

## Pre-labeled drawings: capture existing weld numbers as label rects

Some structural/piping drawings arrive with the weld numbers **already
printed on the sheet by the engineer**. For those, don't place pins by
inference — the PDF's text layer already knows exactly where every label
sits, and `scripts/labels.py` reads it deterministically. The result is a
map where each engineer-printed label becomes a clickable rectangle drawn
**on the label text itself**.

**Use this mode only when the user explicitly asks for it.** Whether a
drawing's text really is per-weld labeling is often not obvious, so the
decision belongs to the user. But do make them aware: when you're mapping a
PDF-backed drawing and notice repeated tag-like text (`FW-101`, `SW 12`,
`W1`…), say once that label-capture mode exists and is much faster and more
accurate than inferring positions — then wait to be asked.

Ground rules for the mode:

- **Do not interpret leader lines.** The captured rectangle marks the label
  text, not the weld the label's leader points at. That is the point of the
  mode: the label becomes the clickable artifact, and chasing leader lines
  by inference is exactly the slow, error-prone work this avoids.
- **Bounding boxes come from the script, never from you.** Your inference is
  limited to *which* labels are welds. Do that by scanning first, reading
  the label list, and writing a `--pattern` regex that matches the project's
  numbering; review what matched before emitting.
- The emitted items are rects: `x/y` and `x2/y2` are opposite corners of the
  label's bbox (plus `--pad`, default 1 pt), already in zipmap PDF space.
  Hint the schema with `"zipmap": {"geometry": "rect"}` so renderers draw
  the box. Each item also carries `label_text` (the raw text; `id` is the
  regex's capture group 1 when one exists, else the full text).
- Needs a **text-layer PDF** (and pymupdf). A scanned/raster drawing yields
  nothing — tell the user OCR is outside this tool rather than silently
  falling back to inference.
- Duplicate label text produces duplicate ids; the scan report lists them
  under `duplicates`. Leave them — id uniqueness is not the format's rule.

The flow, once asked:

```bash
python scripts/zm.py labels mymap                          # scan: every label + bbox
# read the list, decide the weld-number pattern, review the matches:
python scripts/zm.py labels mymap --pattern "FW[- ]?\d+" --mode lines
# emit the data file, set the schema geometry to rect, then the usual pipeline:
python scripts/zm.py labels mymap --pattern "FW[- ]?\d+" --mode lines \
        --emit weld -o mymap/pdf/weld.json :: save mymap :: render mymap
```

`--mode words` (default) treats each word as a label; `--mode lines` joins a
whole text line, for labels with internal spaces (`FW 103`). Fields beyond
the captured five still follow the normal authoring rules — merge in size,
schedule, etc. from the weld list afterwards by editing `pdf/weld.json`, and
let `save` re-derive pixels.

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
deliverable, and it always includes one data table per item type below the
map so nothing is hidden behind clicks. Use `view.py` instead when the user wants to explore the map
(pan/zoom, click items for their fields), `review.py` when they ask to
**review a map before uploading** it to a tracking system (tabbed layers,
data table, switchable label field — a deliberate throw-away file),
`print_pdf.py` when they ask for a printable/PDF copy, and `to_json.py`
when the destination is an API rather than a person.
