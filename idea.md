# zipmap — A Transportable File Format for Weld / Flange / Heat Maps

## Concept

A **zipmap** is a single zipped file (`.zipmap`) that packages a construction drawing
together with its map-item data (welds, flanges, heat numbers, or any other point/region
data type) and the JSON schemas that define that data. The idea deliberately mimics the
`.skill` file concept: a plain zip archive containing markdown/JSON/scripts/assets laid
out to a fixed standard, so any tool that understands the standard can open, render,
validate, and edit the file — no database, no proprietary software.

A zipmap is:

- **Self-contained** — drawing, data, and schema travel together in one file.
- **Self-describing** — every data file is validated against a schema shipped inside the
  same archive.
- **Web-ready by construction** — a valid zipmap always contains a raster image of the
  drawing, so a browser can display it without any server-side conversion.
- **Fast** — all creation, conversion, and validation work is done by Python scripts in
  the companion skill, not by model inference. Inference is reserved for judgment calls
  (e.g., extracting weld locations from a drawing); the mechanical pipeline is pure code.

## Archive Structure

```
example.zipmap  (a standard zip file)
├── manifest.json               # REQUIRED — format version, drawing info, render DPI
├── schemata/
│   ├── weld.schema.json        # JSON Schema for weld map items
│   ├── flange.schema.json      # JSON Schema for flange map items
│   └── ...                     # one schema per map-item type in this zipmap
├── pdf/                        # OPTIONAL — may be empty; ignored by web readers
│   ├── drawing.pdf             # single-page PDF only
│   ├── weld.json               # weld items, PDF-space coordinates
│   └── flange.json             # flange items, PDF-space coordinates
└── img/                        # REQUIRED — the web-displayable layer
    ├── drawing.png             # raster version of the drawing
    ├── weld.json               # weld items, pixel-space coordinates
    └── flange.json             # flange items, pixel-space coordinates
```

Rules:

1. **`manifest.json` is mandatory** at the archive root. See "The Manifest" below.
2. **`img/` is mandatory.** A zipmap without an image is invalid. A zipmap without a PDF
   is valid (image-only zipmaps are first-class). Images are **PNG only**.
3. **PDFs are single-page.** Multi-page PDFs are rejected at save time. (A multi-page
   drawing set is multiple zipmaps.)
4. **Name coupling.** A data file's name (minus extension) must match a schema file's
   name in `schemata/` — `pdf/weld.json` and `img/weld.json` are both validated against
   `schemata/weld.schema.json`.
5. **`pdf/` is authoritative when present.** `pdf/` and `img/` data files describe the
   same items in two coordinate spaces. When a PDF exists, the entire `img/` layer
   (drawing PNG and all data files) is **regenerated from `pdf/` on every save** —
   direct edits to `img/` on a PDF-backed zipmap are discarded. When there is no PDF,
   `img/` is the only copy and is authored directly in pixels.
6. Web-based readers read only `manifest.json`, `schemata/`, and `img/`. Desktop/print
   tools may prefer `pdf/` when present.

## The Manifest

`manifest.json` makes the archive self-describing at a glance and future-proofs the
format. It records what the zipmap is and exactly how the `img/` layer was produced:

```json
{
  "zipmap": "1.0",
  "title": "Unit 3 Cooling Water Isometric",
  "drawing_number": "ISO-CW-3041",
  "revision": "B",
  "created": "2026-07-21T14:30:00Z",
  "source": "pdf",
  "render_dpi": 300,
  "image": { "file": "drawing.png", "width": 3300, "height": 2550 },
  "pdf": { "file": "drawing.pdf", "width": 792, "height": 612 },
  "types": ["weld", "flange"]
}
```

- `zipmap` — format version; readers reject versions they don't understand.
- `source` — `"pdf"` or `"img"`: whether the drawing originated as a PDF (so `img/` is
  derived) or as an image (so `img/` is authoritative).
- `render_dpi` — the DPI used to render the PDF to PNG. Configurable at save time
  (default 300) and always recorded here, so any reader can recompute the exact
  PDF-space ↔ pixel-space scale (`pixels = points × dpi / 72`).
- `pdf` — present only when the archive contains a PDF; omitted otherwise.
- `types` — the map-item types (schema names) contained in this zipmap.

The manifest is written by the save pipeline, never authored by hand.

## Map Items

Map items are simple. Every item has, at minimum:

| Field       | Meaning                                                                 |
|-------------|-------------------------------------------------------------------------|
| `id`        | Identifier for the item (e.g., weld number `W-101`). Uniqueness is **not enforced** — zipmaps are transportable files and the format is not opinionated about map-item numbering. |
| `x`, `y`    | Location of the map item on the drawing                                 |
| `x2`, `y2`  | Second point: the label-flag anchor, or the opposite corner of a rectangular callout |

Everything else is schema-defined per item type. Typical additional fields:

- **Weld:** size, schedule, material, weld type, welder ID, WPS, NDE status, date
- **Flange:** size, rating/class, gasket, torque spec, bolt-up status
- **Heat:** heat number, material spec, MTR reference

The point of `schemata/` is that these extra fields are *not* fixed by the format —
each zipmap declares its own item types and their required/optional fields via standard
JSON Schema. New data types (supports, tie-ins, insulation, punch items…) require no
change to the zipmap standard, only a new schema file.

### Coordinate Systems

- **`pdf/*.json`** — coordinates in PDF user space (points, origin per PDF convention),
  matching the PDF's MediaBox dimensions.
- **`img/*.json`** — coordinates in pixels, top-left origin, matching the actual pixel
  dimensions of `img/drawing.png`.
- Each data file records its space and reference dimensions in a small header block so
  a reader never has to guess:

```json
{
  "space": "img",
  "width": 3300,
  "height": 2550,
  "schema": "weld",
  "items": [
    { "id": "W-101", "x": 1120, "y": 840, "x2": 1250, "y2": 760,
      "size": "2\"", "schedule": "80", "material": "A106-B" }
  ]
}
```

## The Save Pipeline

Saving (zipping) a zipmap is not a plain zip — it is a **normalize-and-validate**
pipeline. The save function always performs these steps, in order:

1. **Enforce single-page PDF.** If a PDF is present and has more than one page, fail.
2. **Regenerate the `img/` layer.** If a PDF is present, render it to `img/drawing.png`
   at the requested DPI (default 300) — **always**, overwriting whatever is in `img/`.
   If there is no PDF, `img/drawing.png` must already exist; if it doesn't, fail:
   *a zipmap without an image is invalid*. PNG is the only accepted image format.
3. **Derive pixel-space data.** For every `pdf/<name>.json`, regenerate `img/<name>.json`
   by transforming coordinates from PDF space to pixel space using the render scale
   (`dpi / 72` pixels-per-point) and Y-axis flip. On a PDF-backed zipmap, `pdf/` is
   authoritative and the `img/` data files are always overwritten. If the user authored
   image-space data directly (no PDF), it passes through untouched.
4. **Bounds check.** Every item's `(x, y)` and `(x2, y2)` must fall within the bounding
   box of its drawing (PDF MediaBox for `pdf/` data, image dimensions for `img/` data).
   Out-of-bounds items fail validation with a report listing the offending IDs.
5. **Schema check.** Validate every data file in `pdf/` and `img/` against its
   same-named schema in `schemata/`. A data file with no matching schema, or one that
   fails validation, blocks the save.
6. **Write the manifest.** Generate `manifest.json` from the actual archive contents
   (source, dimensions, render DPI, item types).
7. **Zip.** Only after all checks pass is the archive written as `<name>.zipmap`.

The inverse also holds on open: a reader may cheaply re-verify steps 2, 4, and 5 to
decide whether a zipmap is trustworthy before rendering it.

## The Skill

The `zipmaps` skill packages this standard as scripts plus a thin instruction layer.
Speed is the priority: **every deterministic operation is a Python script; inference is
never in the hot path.**

Proposed scripts:

| Script                  | Purpose                                                              |
|-------------------------|----------------------------------------------------------------------|
| `scripts/init.py`       | Scaffold a new zipmap working folder (`schemata/`, `pdf/`, `img/`) with starter schemas |
| `scripts/save.py`       | The full save pipeline above → emits `<name>.zipmap`                 |
| `scripts/open.py`       | Unzip to a working folder; quick-validate; print a summary (item counts per type, drawing dims) |
| `scripts/validate.py`   | Run checks 1–5 without zipping; machine-readable pass/fail report    |
| `scripts/pdf2img.py`    | Render single-page PDF → PNG at a given DPI (used by save, callable standalone) |
| `scripts/transform.py`  | PDF-space ↔ pixel-space coordinate conversion for data files         |
| `scripts/render.py`     | (Optional) Burn map-item markers/flags onto the image for a quick visual proof |

Likely dependencies: `pypdf` (page count, MediaBox), `pymupdf` (fast PDF→PNG render),
`jsonschema` (validation), `Pillow` (image dims). All are pip-installable and fast.

Division of labor:

- **Scripts do:** scaffolding, rendering, coordinate math, bounds checks, schema
  validation, zipping/unzipping, summaries.
- **Inference does:** authoring schemas for a new item type on request, reading a
  drawing to extract weld/flange locations into JSON, answering questions about a map.

## Why This Wins

- **Transportable:** email a `.zipmap`, drop it in SharePoint, attach it to a package —
  the receiver has everything needed to view and verify it.
- **Toolable:** because the format is dumb (zip + JSON Schema + PNG), anything can read
  it — a web viewer, a Python script, QC Database import, or Claude itself.
- **Extensible:** new map-item types are just new schema files; no format revision.
- **Verifiable:** the save gate means a `.zipmap` that exists is a `.zipmap` that
  validates — consumers can trust the contract.

## Templates (.zipmapt)

A **zipmap template** is a `.zipmapt` file containing **only schemata** — the
same archive layout with no drawing, data, or manifest. It is how a project or
company standardizes its map-item types:

- AI agents using the skill **keep an eye out for `.zipmapt` files** in the
  working directory or project folder. When one is found, they open it and use
  its map-item schemas as the guide for creating zipmaps — not the generic
  starters.
- Because the folder structure is identical, an opened template is also the
  **starting point of the final zipmap**: insert the PDF or image plus map
  data, and on save the normal validation runs against the template's schemata.

## Resolved Decisions

1. **Manifest:** yes — required `manifest.json` at the archive root, written by the
   save pipeline.
2. **Image format:** PNG only.
3. **Render DPI:** configurable at save time (default 300), always recorded in the
   manifest so readers can recompute the PDF↔pixel scale.
4. **Multiple drawings per zipmap:** no — one drawing per zipmap (mirrors "PDFs must
   be single page").
5. **Round-tripping edits:** `pdf/` is authoritative when a PDF exists; the entire
   `img/` layer is regenerated from `pdf/` on every save. Edits made to `img/` files
   on a PDF-backed zipmap are discarded, not back-propagated.
6. **ID uniqueness:** not enforced. Zipmaps are transportable files; the format is not
   opinionated about map-item numbering.
