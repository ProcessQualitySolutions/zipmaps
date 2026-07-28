# zipmap format specification (v1.1)

A **zipmap** (`.zipmap`) is a plain zip archive that packages one construction
drawing with its map-item data (welds, flanges, heat numbers, or any other
point/region data type) and the JSON Schemas that define that data. It is
self-contained, self-describing, and web-ready by construction.

## Archive layout

```
example.zipmap
├── manifest.json               REQUIRED — written by the save pipeline
├── extracted_data.json         OPTIONAL — the drawing's extraction record
├── schemata/
│   └── <type>.schema.json      one JSON Schema per map-item type
├── pdf/                        OPTIONAL — ignored by web readers
│   ├── drawing.pdf             single-page PDF, this exact name
│   └── <type>.json             map items, PDF-space coordinates
└── img/                        REQUIRED — the web-displayable layer
    ├── drawing.png             PNG only, this exact name
    └── <type>.json             map items, pixel-space coordinates
```

### Rules

1. `manifest.json` is mandatory at the archive root.
2. `img/drawing.png` is mandatory — *a zipmap without an image is invalid*.
   A zipmap without a PDF is valid. PNG is the only accepted image format.
3. A PDF, when present, must be named `pdf/drawing.pdf` and must be
   **single-page**. One drawing per zipmap.
4. **Name coupling:** a data file `<type>.json` (in either `pdf/` or `img/`)
   is validated against `schemata/<type>.schema.json`. A data file with no
   matching schema is a validation error.
5. **`pdf/` is authoritative when present.** The entire `img/` layer (PNG and
   all data files) is regenerated from `pdf/` on every save; direct edits to
   `img/` on a PDF-backed zipmap are discarded. On an image-only zipmap,
   `img/` is authored directly.
6. Web readers consume only `manifest.json`, `schemata/`, and `img/`.
7. Map-item `id` uniqueness is **not enforced** — zipmaps are transportable
   files and the format is not opinionated about numbering.
8. `extracted_data.json`, when present, must parse as a **JSON object**. The
   format constrains nothing else about it — see below.
9. Compression is per member and carries no meaning: the JSON is deflated,
   while `drawing.png` and `drawing.pdf` are stored, since both are already
   compressed internally and re-deflating them costs ~20 ms per megabyte for
   no size gain. Readers must accept either method — every zip tool does.

### Version history

| Version | Change |
|---------|--------|
| 1.0 | Initial format. |
| 1.1 | Added the optional root-level `extracted_data.json` and the matching `extracted_data` presence flag in the manifest. Purely additive: **every 1.0 archive is a valid 1.1 archive**, and readers accept both. |

## manifest.json

Written by the save pipeline from actual archive contents (never authored by
hand; `init.py` may pre-seed the meta fields, which save preserves).

```json
{
  "zipmap": "1.1",
  "title": "Unit 3 Cooling Water Isometric",
  "drawing_number": "ISO-CW-3041",
  "revision": "B",
  "created": "2026-07-21T14:30:00Z",
  "source": "pdf",
  "render_dpi": 300,
  "pdf": { "file": "drawing.pdf", "width": 792, "height": 612,
           "sha256": "3d9f8374da15d2978ce293aa6435260e632a98ed7b06b6860e955d73a0b76065" },
  "image": { "file": "drawing.png", "width": 3300, "height": 2550 },
  "types": ["flange", "weld"],
  "extracted_data": true
}
```

| Field | Req | Meaning |
|-------|-----|---------|
| `zipmap` | yes | Format version. Readers reject versions they don't understand. |
| `title`, `drawing_number`, `revision` | no | Drawing metadata, preserved across saves. |
| `created` | yes | UTC ISO-8601, set on first save and preserved after. |
| `source` | yes | `"pdf"` (img layer derived) or `"img"` (img layer authoritative). |
| `render_dpi` | pdf only | DPI used to render the PNG. `pixels = points × dpi / 72`. |
| `pdf` | pdf only | PDF filename, page size in points, and `sha256` of the PDF's bytes. |
| `image` | yes | PNG filename and size in pixels. |
| `types` | yes | Sorted map-item type names (schema stems) in the archive. |
| `extracted_data` | no | `true` when `extracted_data.json` is present; omitted when it is not. A **presence flag only** — the record itself stays in its own file, so a reader can see that extraction data exists without parsing a bill of materials it may not want. Save writes it from actual contents; a flag disagreeing with the archive is an error. |

## extracted_data.json

Optional, at the archive root. This is the **drawing's own extracted
content** — bill of materials, line number, revision, tagged items,
title-block parameters, whatever an extractor pulled off the sheet — as
distinct from the map items placed *on* the drawing, which live in
`img/<type>.json` and are governed by `schemata/`.

```json
{
  "line_number": "116-A9000-SOLVENT-SKID",
  "drawing_number": "116-A9000-SOLVENT-SKID",
  "revision_number": "0",
  "welded": true,
  "tagged_items": ["1", "2", "3"],
  "bill_of_materials": [
    { "item_number": "1", "nps": "1-1/2\"", "quantity": "1",
      "description": "Lapped Flange (STD) #150", "flange_rating": "150",
      "connection_types": "FLG", "unit_of_measurement": "EA" }
  ],
  "title_block_summary": "JOB …, DRAWING NO. …, REV 0, NOTES NOT TO SCALE"
}
```

**One rule: it must be a JSON object.** The format defines no keys, requires
no keys, and validates nothing inside it. That is deliberate and it mirrors
how map items already work:

| | Defined by | Enforced by the zipmap format |
|---|---|---|
| Map-item fields | the type's `schemata/<type>.schema.json`, or server-side `schema_id` | coordinates only |
| Extraction fields | the **receiving system's drawing-extraction schema** | nothing but object-ness |

Each drawing carries **exactly one** extraction record, as a single object —
not an array, not one file per extractor. A receiving system (QC Database,
for instance) holds its own extraction schema per document folder, versions
it independently, and validates the record against that on ingest. Binding
those field names into this format would make every schema change upstream a
breaking change here.

So: do not invent keys, do not normalize, do not reshape. Copy through what
the extractor produced. The example above happens to be QC Database's
isometric shape; a different system's is equally valid.

The library reads and writes it with `load_extracted_data(root)` /
`write_extracted_data(root, data)`; both refuse anything that is not an
object.

## Data files

Each `<type>.json` is a wrapper object plus an item array. The wrapper is
fixed by the format; the **items** are what the type's schema validates.

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

Wrapper rules (format-enforced):

- `space` — `"pdf"` or `"img"`, matching the directory the file lives in.
- `width` / `height` — the drawing's reference dimensions in that space
  (PDF page points, or PNG pixels). Must match the actual drawing.
- `schema` — the type name; must equal the file's own stem.
- `items` — array of item objects.

Item rules (format-enforced, before the schema runs):

- `x`, `y`, `x2`, `y2` are required numbers on every item. `(x, y)` is the
  map point; `(x2, y2)` is the label-flag anchor or the opposite corner of a
  rectangular callout.
- **Bounds:** all four coordinates must fall inside the drawing's bounding
  box: `0 ≤ x, x2 ≤ width` and `0 ≤ y, y2 ≤ height`.

Everything else on an item is schema territory — see
`schema_authoring.md`.

## Coordinate systems

| Space | Units | Origin | Y direction |
|-------|-------|--------|-------------|
| `pdf` | points (1/72 in), page as displayed (CropBox + rotation) | bottom-left | up |
| `img` | pixels of `drawing.png` | top-left | down |

Conversion (save derives `img/` from `pdf/` with this):

```
scale = render_dpi / 72          (pixels per point)
x_px  = x_pt * scale
y_px  = (pdf_height_pt - y_pt) * scale
```

Both points of an item are transformed independently; nothing requires
`x ≤ x2` or `y ≤ y2` in either space.

## The save pipeline

Saving is a normalize-and-validate gate, never a plain zip. In order:

1. **Single-page PDF check** (when a PDF is present); fail otherwise.
2. **Regenerate the `img/` layer.** With a PDF: render `img/drawing.png` at
   the requested DPI (default 300), always overwriting. Without a PDF:
   `img/drawing.png` must already exist or the save fails.

   The one exception is opt-in: `save.py --reuse-render` keeps the existing
   PNG when `pdf.sha256` and `render_dpi` in the current manifest both still
   match. It is keyed on the PDF's content, never its timestamp, so copying,
   restoring, or touching the file cannot produce a stale render. A plain
   save always re-rasterizes.
3. **Derive pixel-space data.** Every `pdf/<type>.json` regenerates
   `img/<type>.json`; stale `img/` data files with no `pdf/` counterpart are
   deleted.
4. **Bounds check** every item in every data file, both spaces.
5. **Schema check** every data file against its same-named schema.
6. **Object check** `extracted_data.json`, if present — it must parse and be
   a JSON object. Nothing inside it is inspected.
7. **Write `manifest.json`** from actual archive contents (meta fields
   preserved from the existing manifest or CLI flags).
8. **Zip** to `<name>.zipmap` — only if steps 1–6 produced zero errors.
   `extracted_data.json` is packed verbatim.

A `.zipmap` that exists is therefore a `.zipmap` that validated. Readers may
cheaply re-verify (open with validation) before trusting a file.

## Templates (.zipmapt)

A **zipmap template** is a `.zipmapt` file: a zip archive with the same
layout as a zipmap but containing **only `schemata/`** — no drawing, no
data, no manifest. It carries the map-item schemas a project or company has
standardized on.

```
company_std.zipmapt
└── schemata/
    ├── weld.schema.json
    └── flange.schema.json
```

Rules:

1. A template contains only `schemata/*.schema.json`; every schema must be a
   valid JSON object and at least one must be present. In particular a
   template carries **no** `extracted_data.json` — an extraction record
   describes one specific drawing, so it is not a project-wide standard.
2. Because the folder structure is identical, an opened template **is** the
   starting point of a real zipmap: extract it (readers create empty `pdf/`
   and `img/` dirs), drop in the drawing and data files, and save. The
   normal save pipeline then validates the map data against the template's
   schemata with no extra machinery.
3. When a `.zipmapt` is present in a working directory or project folder,
   tools and agents creating a new zipmap should open it and use its
   schemata as the authority for item types and fields — instead of
   inventing schemas or falling back to generic starters.

## The `.zipmap.json` interchange document

A `.zipmap` is a **file**; a `.zipmap.json` is the same map as **one JSON
object**, so it can be POSTed to an API without unzipping anything. It is
the bridge between local zipmap files and a weld/flange/heat tracking
system's HTTP endpoints.

> This section is the summary. **`zipmap_json_spec.md` is the full
> normative specification** — field-by-field rules, the ordered receiver
> validation checklist, a JSON Schema for the envelope, reference decoders
> in Python and TypeScript, and sizing/security guidance. Read that one
> when building an endpoint.

```json
{
  "zipmap_json": "1.1",
  "title": "Unit 3 Cooling Water Isometric",
  "drawing_number": "ISO-CW-3041",
  "revision": "B",
  "image": { "format": "png", "width": 3300, "height": 2550 },
  "pdf": { "format": "pdf", "width": 792, "height": 612, "pages": 1 },
  "extracted_data": { "line_number": "…", "bill_of_materials": [ { "…": "…" } ] },
  "b64": "iVBORw0KGgoAAAANSUhEUgAA...",
  "pdf_b64": "JVBERi0xLjcKJeLjz9MK...",
  "map_item_datasets": [
    { "schema_id": "wsc_01H2XYZ", "map_items": [ { "id": "W-101", "x": 1120,
      "y": 840, "x2": 1250, "y2": 760, "size": "2\"", "schedule": "80" } ] },
    { "schema_id": "hsc_9KQ", "map_items": [ { "id": "H-1", "x": 260,
      "y": 1180, "x2": 1080, "y2": 1330, "heat_number": "7Y4412" } ] }
  ]
}
```

| Field | Req | Meaning |
|-------|-----|---------|
| `b64` | yes | Base64 of `img/drawing.png`, raw — **no `data:` URI prefix**. PNG only. |
| `map_item_datasets` | yes | One entry per map-item type. May be empty. |
| `map_item_datasets[].schema_id` | yes | Id of the **server-side** map-item schema this dataset's items conform to. |
| `map_item_datasets[].map_items` | yes | The type's items, verbatim, in **pixel coordinates**. |
| `zipmap_json` | no | Interchange format version. Absent means "1.0". |
| `image` | no | `format`/`width`/`height` of the encoded PNG, so a consumer can scale coordinates without decoding it. Must agree with `b64` when present. |
| `pdf_b64` | no | Base64 of `pdf/drawing.pdf` — the single-page **print master**. Present whenever the source zipmap has a PDF. |
| `pdf` | no | `format`/`width`/`height`/`pages` of the encoded PDF. Only meaningful with `pdf_b64`. |
| `extracted_data` | no | The drawing's extraction record, verbatim from `extracted_data.json`. An opaque JSON object. |
| `title`, `drawing_number`, `revision` | no | Carried over from `manifest.json`. |

Three rules distinguish it from the archive format:

1. **Only the pixel layer travels.** Every coordinate is `img`-space:
   pixels against the embedded PNG, origin top-left, y down. The PDF-space
   data files are never exported — a consumer needs no point math. The PDF
   *file* may still ride along as `pdf_b64`, but it is a print master, never
   a coordinate space: nothing in the document is measured against it.
2. **Schemas are replaced by a schema id.** The document carries no JSON
   Schema. Each dataset instead names a `schema_id` that resolves to a
   schema held **server-side**, so the receiving system validates items
   against its own authoritative definition of a weld, a flange, or a heat.
   A `schema_id` is therefore **required on every dataset**; a zipmap whose
   types have no ids cannot be exported.
3. **`extracted_data` is opaque, exactly like item fields.** It travels
   verbatim; the format requires only that it be a JSON object. Its shape
   belongs to the receiving system's drawing-extraction schema.

### Why both a PNG and a PDF

They answer different questions and a turnover system needs both:

| | `b64` (PNG) | `pdf_b64` (PDF) |
|---|---|---|
| For | web views, canvas overlays, thumbnails | high-fidelity turnover, printing, archival |
| Fidelity | fixed at the render DPI | vector, resolution-independent, text selectable |
| Coordinates | **the** coordinate space — every item is pixels into it | none; carries no coordinate meaning |
| Required | yes | no — image-only maps have no PDF to send |

`--no-pdf` omits it when the payload matters more than the print master.

Where ids come from, first match wins:

1. an explicit override — `--schema-id weld=<id>`, or `schema_ids={...}`;
2. `schemata/<type>.schema.json` → `"zipmap": { "schema_id": "..." }`;
3. `schemata/<type>.schema.json` → `"$id"`.

`to_json.py --bind` writes an id into the schema file (rule 2), so the
binding survives in the `.zipmap` and every later export resolves it with
no flags. Because ids live in the schemata, a `.zipmapt` template can ship
a whole project's type↔schema bindings.

Key order is not significant. `b64` is emitted second-to-last so the
readable fields sit above the one enormous line.

### Validation of a document

`b64` must be a decodable base64 PNG; `map_item_datasets` must be an array
of objects each carrying a non-empty `schema_id` and a `map_items` array;
every item needs numeric `x`, `y`, `x2`, `y2` inside the decoded image's
bounds; a present `image` must match the decoded PNG; a present `pdf_b64`
must decode to a whole PDF (`%PDF-` header, `%%EOF` near the end) and a
present `pdf.pages` must be `1`; a present `extracted_data` must be a JSON
object; a present `zipmap_json` must be a supported version. Item **fields**
and extraction **fields** are *not* checked locally — that is the server's
job, against `schema_id` and its own extraction schema respectively.

### Direction

Export is one-way by design. A `.zipmap.json` cannot be turned back into a
valid `.zipmap` on its own: the schemata it dropped are exactly what the
archive format requires. Round-tripping means fetching the schemas for each
`schema_id` from the system that issued them. (`pdf_b64` closes one gap the
1.0 document had — the original PDF now survives the trip — but the schemas
still do not.)

## Validation summary

Errors (block save / fail validation): missing image; non-PNG image;
multi-page or mis-named PDF; data file without a schema; PDF-space data with
no PDF; wrapper mismatch (`space`, `schema`, `width`, `height`); missing or
non-numeric coordinates; out-of-bounds coordinates; schema violations;
`extracted_data.json` that is unparseable or not a JSON object; manifest
missing (in archives), version/dimension/types/source/`extracted_data`
mismatch; on PDF-backed maps, `img/` data not mirroring `pdf/`.

Warnings (allowed): a schema with no data file using it; unexpected extra
files in `img/`; `extracted_data.json` in a template folder.

For `.zipmap.json`: missing/undecodable `b64`; `b64` that is not a PNG;
missing or non-array `map_item_datasets`; a dataset without a non-empty
`schema_id` or without a `map_items` array; missing, non-numeric, or
out-of-bounds item coordinates; a declared `image` that disagrees with the
decoded PNG; `pdf_b64` that is undecodable, is not a PDF, or is truncated;
a `pdf` block with no `pdf_b64`, a `format` other than `"pdf"`, `pages`
other than `1`, or a non-positive dimension; `extracted_data` that is not a
JSON object; an unsupported `zipmap_json` version.
