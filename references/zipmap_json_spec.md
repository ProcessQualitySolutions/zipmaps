# `.zipmap.json` — interchange format specification (v1.1)

This document defines the **`.zipmap.json`** interchange document in full,
for implementers building an HTTP endpoint that accepts it. It is written to
be sufficient on its own: you should not need to read the `.zipmap` archive
spec (`format_spec.md`) to build a correct receiver, though it is the
authority on where the data comes from.

**Normative sections** (2–9) use MUST / MUST NOT / SHOULD / MAY in the
RFC 2119 sense. **Advisory sections** (10–15) are recommendations for your
endpoint, not requirements of the format; they are marked as such.

---

## 1. What this format is

A `.zipmap` is a **file**: a zip archive holding one construction drawing,
its map-item data in two coordinate spaces, the JSON Schemas that define
each item type, and optionally the drawing's extraction record. It is built
for humans and filesystems.

A `.zipmap.json` is the **same map flattened into a single JSON object**,
built for APIs. It carries:

- the drawing twice — as a base64 PNG for web views, and (when the source
  has one) as a base64 **single-page PDF** for high-fidelity turnover;
- every map item, in pixel coordinates against that PNG;
- for each group of items, the **id of a schema your server already holds**;
- optionally, the drawing's **extraction record** — bill of materials and
  drawing parameters — as one opaque object.

It is the bridge between local zipmap files and a weld/flange/heat tracking
system's endpoints. One `POST` body, no multipart, no unzipping, no PDF
rendering, no coordinate math.

### 1.1 Three deliberate differences from the archive

**(a) Only the pixel layer travels.** A `.zipmap` may contain a `pdf/` layer
whose coordinates are PDF points with a bottom-left origin. None of *that*
is exported. Every coordinate in a `.zipmap.json` is a **pixel offset into
the embedded PNG**, origin top-left. A receiver never needs a PDF library
and never converts anything.

The PDF **file** is a separate matter, added in 1.1: `pdf_b64` carries the
original single-page PDF so a turnover package can hold the real,
vector-fidelity drawing rather than a raster of it. It is a print master,
not a coordinate space — §5.4.

**(b) Schemas are replaced by a schema id.** A `.zipmap` bundles a JSON
Schema per item type. A `.zipmap.json` bundles **none**. Each dataset
instead names a `schema_id` that resolves, on your server, to that system's
own authoritative definition of a weld, a flange, a heat, a support. This is
the whole point of the format: the receiving system validates incoming items
against *its* schema, not against a schema the sender chose. A dataset
without a `schema_id` is meaningless and MUST be rejected.

**(c) The extraction record is opaque.** `extracted_data` (§8) is the
drawing's own extracted content, and this format defines exactly one thing
about it: it is a JSON object. Its fields belong to *your* drawing-extraction
schema, on the same principle as (b).

### 1.2 What this format is not

- It is **not** a container for multiple drawings. One document = one
  drawing = one image = at most one PDF. Send several documents for several
  drawings.
- It is **not** self-validating for item *content*. Coordinates and
  structure are checkable locally; every other field on an item is opaque
  until your server resolves `schema_id`. The same is true of every field
  inside `extracted_data`.
- It is **not** reversible into a `.zipmap` on its own — see §15.
- It carries **no** rendering hints. How to draw an item (pin-and-flag vs.
  rectangle) is a property of the server-side schema, not of the document.
  See §6.4.

---

## 2. Encoding, naming, and media type

| Aspect | Rule |
|--------|------|
| Serialization | JSON, per RFC 8259. |
| Character encoding | UTF-8. A receiver MUST accept UTF-8 and MAY reject anything else. |
| Byte-order mark | Producers MUST NOT emit one. Receivers SHOULD tolerate and strip a leading BOM. |
| File extension | `.zipmap.json` — the full double extension. `mymap.zipmap` exports to `mymap.zipmap.json`. |
| Media type | `application/json`. A vendor type such as `application/vnd.zipmap+json` MAY be used by agreement; it is not part of this specification. |
| Non-finite numbers | `NaN`, `Infinity`, and `-Infinity` are not JSON. Producers MUST NOT emit them; receivers MUST reject a document containing them. |
| Key order | Not significant. The reference producer emits `b64` and `pdf_b64` last but one, so that the human-readable fields precede the two enormous lines, but a receiver MUST NOT depend on ordering. |
| Duplicate keys | Undefined behavior; producers MUST NOT emit them. |
| Whitespace | Insignificant. Documents may be pretty-printed or minified. |

---

## 3. At a glance

A complete, valid, minimal-but-realistic document:

```json
{
  "zipmap_json": "1.1",
  "title": "Unit 3 Cooling Water Isometric",
  "drawing_number": "ISO-CW-3041",
  "revision": "B",
  "image": {
    "format": "png",
    "width": 3300,
    "height": 2550
  },
  "pdf": {
    "format": "pdf",
    "width": 792,
    "height": 612,
    "pages": 1
  },
  "extracted_data": {
    "line_number": "116-A9000-SOLVENT-SKID",
    "revision_number": "0",
    "welded": true,
    "bill_of_materials": [
      { "item_number": "1", "nps": "1-1/2\"", "quantity": "1",
        "description": "Lapped Flange (STD) #150", "flange_rating": "150",
        "connection_types": "FLG", "unit_of_measurement": "EA" }
    ],
    "title_block_summary": "JOB …, DRAWING NO. …, REV 0, NOT TO SCALE"
  },
  "b64": "iVBORw0KGgoAAAANSUhEUgAADOQAAAn+CAIAAAD...",
  "pdf_b64": "JVBERi0xLjcKJeLjz9MKMSAwIG9iago8PC9UeXBl...",
  "map_item_datasets": [
    {
      "schema_id": "wsc_01H2XYZ",
      "map_items": [
        {
          "id": "W-101",
          "x": 1120, "y": 840, "x2": 1250, "y2": 760,
          "size": "2\"",
          "schedule": "80",
          "material": "A106-B",
          "weld_type": "BW",
          "welder": "J.RUIZ",
          "wps": "WPS-1-1-A",
          "nde": "RT",
          "date": "2026-07-14"
        },
        {
          "id": "W-102",
          "x": 1980, "y": 840, "x2": 2110, "y2": 920,
          "size": "2\"",
          "schedule": "80",
          "material": "A106-B",
          "weld_type": "SW"
        }
      ]
    },
    {
      "schema_id": "hsc_9KQ",
      "map_items": [
        {
          "id": "H-1",
          "x": 260, "y": 1180, "x2": 1080, "y2": 1330,
          "heat_number": "7Y4412",
          "material_spec": "SA-106 Gr B",
          "mtr": "MTR-2026-0142"
        }
      ]
    }
  ]
}
```

The absolute minimum a receiver must accept — everything else is optional:

```json
{
  "b64": "iVBORw0KGgoAAAANSUhEUgAA...",
  "map_item_datasets": [
    { "schema_id": "wsc_01H2XYZ",
      "map_items": [ { "x": 10, "y": 20, "x2": 30, "y2": 40 } ] }
  ]
}
```

---

## 4. The top-level object

The document root MUST be a JSON object. Any other root (array, string,
number, `null`) is invalid.

| Field | Type | Req | Summary |
|-------|------|-----|---------|
| `b64` | string | **yes** | The drawing: base64 of a PNG file. §5 |
| `map_item_datasets` | array | **yes** | Items, grouped by server-side schema. §6 |
| `zipmap_json` | string | no | Format version. Absent ⇒ `"1.0"`. §4.1 |
| `image` | object | no | Declared dimensions of the encoded PNG. §5.3 |
| `pdf_b64` | string | no | The drawing again: base64 of a single-page PDF. §5.4 |
| `pdf` | object | no | Declared page size and page count of that PDF. §5.5 |
| `extracted_data` | object | no | The drawing's opaque extraction record. §8 |
| `title` | string | no | Drawing title. §4.2 |
| `drawing_number` | string | no | Drawing number. §4.2 |
| `revision` | string | no | Drawing revision. §4.2 |

Unknown top-level fields MUST be ignored by a receiver, not rejected. See
§14 on forward compatibility.

### 4.1 `zipmap_json`

The interchange format version, as a string. Two versions are defined:

| Version | Adds |
|---------|------|
| `"1.0"` | The original document: `b64` + `map_item_datasets`. |
| `"1.1"` | `pdf_b64`, `pdf`, and `extracted_data` — all **optional**. No 1.0 field changed meaning, and no 1.0 field was removed. |

- When **present**, a receiver MUST reject any value it does not implement.
- When **absent**, a receiver MUST assume `"1.0"`. (Absence is legal so that
  a hand-rolled minimal document is valid; producers SHOULD always emit it.)

Because 1.1 is purely additive, **every 1.0 document is a valid 1.1
document**, and a 1.1 receiver needs no version branching: the three new
fields are absent-by-default and each is checked only when present. Build
your receiver to accept both.

The reference producer emits `"1.1"` unconditionally — including when the
map is image-only and carries no extraction record, so the document happens
to contain nothing a 1.0 receiver would not understand. It does not
downgrade the version string to match the fields it used, because a
sender's version must describe the contract it was built against, not the
accident of one document's contents. If you have a deployed 1.0-only
receiver, §14 is the compatibility path: accept `"1.1"` on the strength of
ignoring unknown fields, or update it.

This is *not* the same version as the archive's `manifest.json` `zipmap`
field. The two version independently — the archive is separately at 1.1,
for a different reason (it gained `extracted_data.json`).

### 4.2 Drawing metadata

`title`, `drawing_number`, and `revision` are free-form strings copied from
the source archive's `manifest.json`. Any of them may be absent (the source
zipmap need not have set them, and the producer's `--no-meta` flag omits
them deliberately).

They are **descriptive, not identifying**. Do not key records on them, do
not require them, and do not assume `drawing_number` is unique or even
well-formed — it is whatever the person who built the map typed. If your
system needs a stable identity for the drawing, carry your own id in the
request path, query string, or a wrapper object (§12.2).

---

## 5. The drawing — `b64`, and optionally `pdf_b64`

A document carries the drawing **as a PNG always, and as a PDF when it can**.
They are not alternatives and a receiver should not treat them as such:

| | `b64` — PNG | `pdf_b64` — PDF |
|---|---|---|
| Required | **yes** | no |
| For | web views, canvas overlays, thumbnails, anything a browser draws | high-fidelity turnover, printing, archival, plan-room delivery |
| Fidelity | raster, fixed at whatever DPI the sender rendered | vector, resolution-independent, text selectable and searchable |
| Coordinates | **the** coordinate space — every item is a pixel offset into it | none whatsoever |
| Absent when | never | the source map is image-only, or the sender passed `--no-pdf` |

The split exists because one file cannot do both jobs. A PNG is what a
browser can put on a canvas with no plugin and no conversion, which is why
the coordinates are pixels into it. A PDF is what a client, an inspector, or
an archive actually wants when the drawing is printed at D size — and
rasterizing it away at upload time destroys that permanently.

If your system needs both — QC Database does, one for its web viewer and one
for turnover packages — require `pdf_b64` at your endpoint. This
specification cannot require it, because image-only zipmaps legitimately
have no PDF to send; making it mandatory here would make those maps
unsendable. Requiring it is a policy your API states, and §12 is where to
state it.

```json
"b64": "iVBORw0KGgoAAAANSUhEUgAADOQAAAn+CAIAAAD..."
```

### 5.1 `b64` rules

1. `b64` MUST be present and MUST be a non-empty string.
2. It MUST be **standard** base64 (RFC 4648 §4, alphabet `A–Z a–z 0–9 + /`,
   `=` padding). It MUST NOT be base64url (`-`/`_`).
3. It MUST NOT carry a data-URI prefix. `data:image/png;base64,` is **not**
   part of the value. A receiver MAY strip such a prefix defensively, but a
   producer that emits one is non-conformant.
4. The reference producer emits one unbroken line with no whitespace.
   Receivers SHOULD strip ASCII whitespace before decoding, so that
   line-wrapped documents from other producers still work.
5. The decoded bytes MUST be a **PNG file** — they MUST begin with the
   8-byte signature `89 50 4E 47 0D 0A 1A 0A`, immediately followed by a
   valid `IHDR` chunk (bytes 12–15 are the ASCII `IHDR`). No other image
   format is permitted in v1.0; JPEG, WebP, PDF, and SVG are all invalid.

### 5.2 Reading the dimensions without a decoder

You do not need an image library to learn the drawing's size. A PNG's IHDR
puts width and height at fixed offsets in the first 26 bytes:

```
offset  0..7   PNG signature   89 50 4E 47 0D 0A 1A 0A
offset  8..11  IHDR length     00 00 00 0D
offset 12..15  chunk type      "IHDR"
offset 16..19  width           uint32, big-endian
offset 20..23  height          uint32, big-endian
offset 24      bit depth
offset 25      color type
```

So base64-decoding the first 36 characters (which yields at least 26 bytes)
is enough to validate the signature and read both dimensions — useful when
you want to reject an oversized drawing before buffering the whole payload.

### 5.3 `image` — the declared dimensions

```json
"image": { "format": "png", "width": 3300, "height": 2550 }
```

Optional. It exists so a consumer can lay out, scale, or sanity-check
coordinates **without decoding a multi-megabyte base64 string**.

| Field | Type | Rule |
|-------|------|------|
| `width` | integer | Pixel width of the encoded PNG. |
| `height` | integer | Pixel height of the encoded PNG. |
| `format` | string | Always `"png"` in v1.0. |

- When `image` is present, its `width` and `height` MUST equal the decoded
  PNG's actual dimensions. A mismatch is an error, not a warning — it means
  the coordinates were computed against a different image than the one
  attached, so every item may be misplaced.
- When `image` is present, a receiver SHOULD reject a `format` other than
  `"png"`, since `b64` must be a PNG regardless.
- When `image` is **absent**, the decoded PNG is the sole authority; a
  receiver MUST derive the dimensions from it (§5.2) in order to run the
  bounds checks in §6.3.

The dimensions are always in **image pixels**, never in points, inches, or
CSS pixels, and they have no bearing on the drawing's physical scale. The
document carries no DPI: once rendered, the pixel grid *is* the coordinate
system, and the original render DPI is not needed to place an item. (It
stays behind in the archive's `manifest.json` if anyone needs it.)

### 5.4 `pdf_b64` — the print master *(1.1)*

```json
"pdf_b64": "JVBERi0xLjcKJeLjz9MKMSAwIG9iago8PC9UeXBl..."
```

Optional. The drawing's original **single-page PDF**, base64-encoded — the
same bytes as `pdf/drawing.pdf` in the source archive, unmodified.

1. When present, `pdf_b64` MUST be a non-empty string.
2. It MUST be **standard** base64 (RFC 4648 §4), not base64url, with no
   `data:` URI prefix — the same encoding rules as `b64` (§5.1, items 2–4).
3. The decoded bytes MUST be a PDF file: they MUST begin with the ASCII
   header `%PDF-` (hex `25 50 44 46 2D`), and a `%%EOF` marker MUST appear
   near the end. Both checks are cheap, need no PDF library, and together
   catch the overwhelmingly common failure — a payload truncated in transit.
4. The PDF MUST have **exactly one page**. A `.zipmap` is one drawing, and
   the save pipeline enforces single-page before an archive can exist. The
   document itself cannot prove this to you without a PDF parser; if you
   care, verify it server-side when you parse the file (§11 item 10).
5. `pdf_b64` is **not a coordinate space**. No coordinate anywhere in the
   document is measured against it, in points or otherwise. Do not try to
   place map items on it, and do not treat a mismatch between the PDF's page
   size and the PNG's pixel size as an error — a PNG rendered at 300 DPI
   from a 792×612 pt page is *supposed* to be 3300×2550 px.
6. A document MUST NOT be rejected merely for lacking `pdf_b64`. An
   image-only zipmap has no PDF to send. (Your *endpoint* may require one —
   §5, §12.6 — but that is your policy, not this format's rule.)

**Storage.** Store the PDF; do not regenerate it from the PNG, which is not
possible in any meaningful sense. If you re-render the PNG for display at a
different size, the PDF is unaffected: it is the archival original and
should be served untouched.

### 5.5 `pdf` — the declared page geometry *(1.1)*

```json
"pdf": { "format": "pdf", "width": 792, "height": 612, "pages": 1 }
```

Optional, and meaningful only alongside `pdf_b64`. It mirrors `image`
(§5.3): metadata a consumer can read without decoding a multi-megabyte
base64 string.

| Field | Type | Rule |
|-------|------|------|
| `width` | number | Page width in **points** (1/72 inch), as displayed — CropBox with rotation applied. |
| `height` | number | Page height in points, same basis. |
| `format` | string | Always `"pdf"` in 1.1. |
| `pages` | integer | Always `1` when present. |

- A `pdf` block present **without** `pdf_b64` is an error: it describes
  something that is not there.
- A receiver SHOULD reject a `format` other than `"pdf"` and a `pages` other
  than `1`.
- `width` and `height`, when present, MUST be positive numbers.
- Unlike `image`, these dimensions are **not** cross-checked against the
  encoded bytes by this specification, because doing so requires a PDF
  parser and nothing in the document depends on the answer. A receiver that
  parses the PDF anyway MAY compare them, and SHOULD prefer the parsed value
  on disagreement.
- The producer omits `pages` when it could not establish the page count —
  exporting a working folder on a machine without a PDF library. An absent
  `pages` therefore means "unverified", not "zero"; treat it as a reason to
  check server-side, not as a rejection.

Points are the PDF's own unit and have no relationship to the pixel
coordinates in §6.3. The two are different measurements of the same drawing
and are never mixed.

---

## 6. `map_item_datasets` — the items

```json
"map_item_datasets": [
  { "schema_id": "wsc_01H2XYZ", "map_items": [ … ] },
  { "schema_id": "hsc_9KQ",     "map_items": [ … ] }
]
```

`map_item_datasets` MUST be present and MUST be an array. Each element MUST
be an object with exactly two meaningful fields: `schema_id` and
`map_items`. Both are required.

The array MAY be empty — a document with a drawing and no items is valid,
and represents a map that has been created but not yet populated. Decide
deliberately whether your endpoint accepts that (it is a reasonable way to
register a drawing) or rejects it as a likely mistake.

### 6.1 `schema_id`

```json
"schema_id": "wsc_01H2XYZ"
```

The identifier of the map-item schema, **on the receiving server**, that
these items conform to. It answers "what kind of thing are these?" — welds,
flanges, heats, supports, hangers.

1. `schema_id` MUST be present, MUST be a string, and MUST NOT be empty or
   whitespace-only.
2. Its **format is entirely yours**. The interchange format treats it as an
   opaque token and imposes no pattern, length, or character set. It may be
   a ULID, a UUID, an integer rendered as a string, a slug like `"weld"`, or
   a URI. Publish whatever shape your system issues; senders will echo it
   back verbatim.
3. A receiver MUST reject a document naming a `schema_id` it cannot resolve.
   This is the single most important check in the whole format — an
   unresolvable id means you have no definition to validate items against,
   and silently accepting them stores unvalidated data.
4. Resolution SHOULD be scoped the way your system scopes schemas. If ids
   are per-project or per-tenant, an id valid in project A MUST NOT resolve
   in project B; treat it as unresolvable there. This matters: the sender is
   a file that may have been mailed between projects.

**Duplicate ids.** The reference producer emits exactly one dataset per
item type, so ids are distinct in practice. The format does not forbid two
datasets sharing an id. A receiver SHOULD treat that as **additive** —
concatenate the `map_items` — rather than as an error or as a
last-one-wins overwrite.

### 6.2 `map_items`

`map_items` MUST be present and MUST be an array. Each element MUST be a
JSON object. The array MAY be empty.

An item is an **open** object: the four coordinates below are fixed by this
format, and *every other field belongs to the schema* named by
`schema_id`. The interchange format neither knows nor checks them. A
receiver MUST NOT reject an item for carrying fields it does not recognize
at the interchange layer — that judgment belongs to schema validation (§8,
stage 5), where your own schema decides whether extras are permitted.

Fields you will see in practice, none of them required by *this* format:

| Field | Typical type | Notes |
|-------|--------------|-------|
| `id` | string | The item's human-facing tag: `"W-101"`, `"H-1"`, `"FL-22"`. Effectively always present, because the archive's own schemas require it — but the interchange format does not, so do not assume it. |
| discipline fields | any | `size`, `schedule`, `material`, `weld_type`, `welder`, `wps`, `nde`, `date`, `heat_number`, `material_spec`, `mtr`, `rating`, … — whatever your schema defines. |

**`id` is not unique and is not a key.** The zipmap format deliberately does
not enforce uniqueness of `id`, within a dataset or across datasets — maps
are transportable files and the format is unopinionated about numbering.
Two items may legitimately share `"W-101"` (a revised drawing, a duplicated
callout, an honest mistake). Do not use `id` as a primary key, a dedup key,
or an upsert key without your own additional scoping, and do not silently
drop duplicates. If uniqueness matters to your system, enforce it yourself
and report the conflict — do not assume the sender did.

### 6.3 The coordinate contract

Every item MUST carry four coordinates: **`x`, `y`, `x2`, `y2`**.

1. All four MUST be present on every item.
2. All four MUST be JSON numbers. Integers and reals are both fine.
   Coordinates derived from a PDF are rounded to 2 decimal places
   (`683.33`); coordinates authored directly against an image are usually
   whole numbers. A receiver MUST NOT require integers.
3. A JSON boolean MUST NOT be accepted as a number, even in languages where
   `true` coerces to `1`. Neither MUST a numeric string: `"120"` is invalid,
   `120` is valid.
4. Non-finite values are invalid (§2).
5. **Bounds, inclusive:** given the image's `width` and `height`,

   ```
   0 ≤ x  ≤ width        0 ≤ y  ≤ height
   0 ≤ x2 ≤ width        0 ≤ y2 ≤ height
   ```

   An out-of-bounds coordinate MUST be rejected. `0` and `width` are both
   legal — an item pinned exactly to an edge is fine.
6. **No ordering is implied.** `x2 < x` and `y2 < y` are entirely normal.
   Nothing normalizes the pair into a min/max box; a flag anchor sits
   wherever there was room on the drawing, which is frequently up and to the
   left. Do not "correct" the order.

#### The coordinate system, precisely

```
 (0,0)                                    (width, 0)
   ┌──────────────────────────────────────────┐
   │                                          │
   │        ● (x, y)          ← the map point │   x increases →
   │         ╲                                │
   │          ╲                               │   y increases ↓
   │           □ (x2, y2)     ← flag anchor   │
   │                                          │
   └──────────────────────────────────────────┘
 (0, height)                       (width, height)
```

- Units: **pixels of the embedded PNG**. Not points, not millimetres, not
  fractions.
- Origin: **top-left**. `y` increases **downward** — the raster/canvas/CSS
  convention, and the opposite of the PDF convention. If your stored
  representation uses a bottom-left origin, convert on ingest with
  `y_stored = height − y_doc`; nothing in the document is bottom-left.
- The values are absolute pixel offsets into a specific rendering of the
  drawing. They are meaningful **only** against the PNG in the same
  document. Never mix coordinates from one document with the image of
  another; if you re-render or re-scale the image, you MUST scale the
  coordinates by the same factor.

For reference, the producer derives these from a PDF-backed source as:

```
scale = render_dpi / 72
x_px  = x_pt * scale
y_px  = (pdf_height_pt − y_pt) * scale
```

You never perform this conversion — it happened before the document was
built. It is documented here only so the numbers are explicable: a weld at
`y = 300 pt` on a 792 pt page rendered at 100 DPI arrives as
`y = (792 − 300) × 100/72 = 683.33`.

### 6.4 What the two points mean

Both points are always present, but their *meaning* depends on the item
type — and that meaning lives in your **server-side schema**, not in this
document. There is no geometry field in a `.zipmap.json` to read.

| Geometry | `(x, y)` | `(x2, y2)` | Rendering |
|----------|----------|------------|-----------|
| **flag** (default) | The map point — where the weld/flange actually is. | The label-flag anchor. | A pin at `(x, y)`, a leader line to `(x2, y2)`, the label drawn there. |
| **rect** | One corner of a rectangular region. | The opposite corner. | A rectangle, e.g. a heat-number region covering a spool. |

In the source archive this is declared as `"zipmap": {"geometry": "flag"}`
or `"rect"` in the item type's schema. Since schemas do not travel, your
server-side schema for each `schema_id` MUST carry the equivalent, or your
renderer will draw heats as pins and welds as boxes. If your schema
registry has no such notion, add one — it is a one-word field and there is
no other way to recover it.

Nothing in validation depends on geometry: both shapes have identical
coordinate rules.

---

## 7. `extracted_data` — the drawing's extraction record *(1.1)*

```json
"extracted_data": {
  "line_number": "116-A9000-SOLVENT-SKID",
  "drawing_number": "116-A9000-SOLVENT-SKID",
  "revision_number": "0",
  "welded": true,
  "tagged_items": ["1", "2", "3"],
  "bill_of_materials": [
    { "item_number": "1", "nps": "1-1/2\"", "quantity": "1",
      "description": "Lapped Flange (STD) #150", "flange_rating": "150",
      "material_code": "316SS", "connection_types": "FLG",
      "unit_of_measurement": "EA", "is_linear_qty": false }
  ],
  "line_specifications": [],
  "title_block_summary": "JOB …, DRAWING NO. …, REV 0, NOT TO SCALE"
}
```

Optional. This is what was extracted **from** the drawing — its bill of
materials, line number, revision, tagged items, fluid service, title-block
parameters, reference drawings — as opposed to the map items placed **on**
the drawing, which are §6.

### 7.1 The entire contract

1. When present, `extracted_data` MUST be a **JSON object**. An array, a
   string, a number, or `true` is invalid. `null` is treated as absent.
2. It MAY be empty (`{}`).
3. **There is no third rule.** This specification defines no keys inside it,
   requires no keys inside it, reserves no keys inside it, and validates
   nothing inside it. Nesting, arrays, types, and depth are all unconstrained.
4. A receiver MUST NOT reject a document because `extracted_data` carries
   fields it does not recognize, and MUST NOT reject one because a field it
   *expects* is missing — not at the interchange layer. That judgment belongs
   to your extraction schema (§7.2), the way item fields belong to
   `schema_id`.
5. There is exactly **one** record per document, because there is exactly
   one drawing per document. It is an object, never an array of records.

### 7.2 Why it is opaque

This is the same design decision as `schema_id` (§6.1), applied to the
drawing instead of the items:

| | Fields defined by | Checked at the interchange layer |
|---|---|---|
| Map item | the schema your server resolves from `schema_id` | the four coordinates, nothing else |
| Extraction record | **your drawing-extraction schema** | that it is an object, nothing else |

A drawing-extraction schema is a live thing. It gains a field when someone
notices the title block also carries a fluid service; it splits one when
`quantity` turns out to need a unit; it differs between isometrics, P&IDs,
and vessel drawings. In QC Database terms it is configured per document
folder and evolves with the project.

If this specification enumerated those fields, every one of those ordinary
changes would become a breaking change to the interchange format, and every
sender would need a new release to carry a field the receiver just added.
Making the record opaque means the extractor and the receiving system can
agree on a shape between themselves, and the document just carries it.

So: **copy it through verbatim.** Do not normalize keys, coerce types,
reshape arrays, drop empty values, or reorder. A sender that "helpfully"
renames `nps` to `size` has silently corrupted the record for a receiver
whose schema says `nps`. The example above is QC Database's isometric shape
and is illustrative only — another system's is equally valid.

### 7.3 What a receiver does with it

1. Check it is an object (§7.1). That is the interchange layer's whole job.
2. Resolve **your** extraction schema for this drawing — by document folder,
   drawing type, project, however your system scopes it. Scope it to the
   authenticated caller's tenant, for the same reason `schema_id` is scoped
   (§11 item 5).
3. Validate the record against that schema and apply your business rules —
   in the same late stage as item validation (§8, stage 5), and *after* the
   cheap structural checks.
4. Store it. `set_document_extracted_data` in the QC Database API is the
   equivalent single-object write; an ingesting endpoint does the same thing
   with the record that arrived in the document.

Treat every string in it as hostile (§11 item 4) — a BOM description is free text
that came from an OCR pass over an untrusted file, and it will end up in
HTML, CSV exports, and PDF reports.

**Absence is not emptiness.** A document with no `extracted_data` means "no
extraction record travelled", which is not the same as "this drawing has no
bill of materials". Do not overwrite a stored record with nothing on
re-submission unless the caller explicitly asked you to (§12.4).

---

## 8. Validation — the receiver's checklist

Run these in order. Stages 1–4 are decidable from the document alone and
constitute conformance to *this* specification; stage 5 is your system's
own business logic and is where the real work happens.

**Stage 1 — envelope.**
1. Body parses as JSON; root is an object.
2. `zipmap_json`, if present, is a supported version. → else `400`
3. `b64` is present and is a non-empty string. → else `400`
4. `map_item_datasets` is present and is an array. → else `400`

**Stage 2 — image.**
5. `b64` decodes as standard base64. → else `400`
6. Decoded bytes start with the PNG signature and a valid `IHDR`. → else
   `400`
7. Read `width`/`height` from IHDR. Apply your size limits (§11).
8. If `image` is present, its `width`/`height` equal the IHDR values, and
   its `format` is `"png"`. → else `400`

**Stage 2b — PDF, when `pdf_b64` is present.** Skip entirely when it is
absent, unless your endpoint requires it (§12.6).
9. `pdf_b64` is a non-empty string that decodes as standard base64.
   → else `400`
10. Decoded bytes begin with `%PDF-` and carry `%%EOF` near the end. → else
    `400`
11. If `pdf` is present: `format` is `"pdf"`, `pages` (if present) is `1`,
    and `width`/`height` (if present) are positive. → else `400`
12. If `pdf` is present but `pdf_b64` is not → `400`.

**Stage 3 — dataset and record structure.**
13. `extracted_data`, if present and non-`null`, is an object (§7.1) — and
    nothing further at this stage.
14. Each element of `map_item_datasets` is an object.
15. Its `schema_id` is a present, non-empty string.
16. Its `map_items` is an array, and every element of it is an object.

**Stage 4 — coordinates.** For each item:
17. `x`, `y`, `x2`, `y2` are all present, all JSON numbers (not booleans,
    not strings), all finite.
18. Each falls within the inclusive bounds of §6.3.

**Stage 5 — schema resolution, item validation, extraction validation.** Now
leave this specification behind:
19. Resolve every `schema_id` against your registry, in the correct
    project/tenant scope. Unresolvable ⇒ reject (`422` is apt). Resolve
    **all** ids before validating any items, so a document naming one bad id
    fails fast and cheaply.
20. Validate each item object against the resolved schema — required
    fields, types, enumerations, whether extra properties are allowed.
21. Validate `extracted_data` against **your** drawing-extraction schema
    (§7.3), scoped the same way.
22. Parse the PDF if you intend to store or render it, and confirm it really
    is single-page (§5.4 rule 4) — the cheap checks in stage 2b cannot.
23. Apply your own business rules: id uniqueness if you require it,
    referential integrity against jobs/packages/line specs, permissions,
    duplicate-submission detection.

**Rejection is all-or-nothing by default.** Because the drawing and its
items are one payload, a partial write leaves a map whose pins do not match
its drawing. Import inside a transaction and roll back on any failure,
unless you have deliberately designed a partial-acceptance response (§12.4).

### 8.1 Reporting errors

*Advisory.* Senders are often building maps by hand, so precise errors save
real time. The reference implementation's local validator reports every
failure with a full path and both values, and accumulates them rather than
stopping at the first:

```
map_item_datasets[0] (schema_id=hsc_9KQ) map_items[1] (id=H-2): coordinate "y2" missing or not a number
map_item_datasets[0] (schema_id=hsc_9KQ) map_items[0] (id=H-1): x=99999 outside image width 0..800
image 1234x600 does not match the decoded PNG (800x600)
```

A JSON equivalent that pairs well with an HTTP `422`:

```json
{
  "error": "validation_failed",
  "errors": [
    { "pointer": "/map_item_datasets/0/map_items/1/y2",
      "code": "coordinate_missing",
      "message": "coordinate \"y2\" missing or not a number",
      "item_id": "H-2", "schema_id": "hsc_9KQ" },
    { "pointer": "/map_item_datasets/0/map_items/0/x",
      "code": "coordinate_out_of_bounds",
      "message": "x=99999 outside image width 0..800",
      "item_id": "H-1", "schema_id": "hsc_9KQ" }
  ]
}
```

`pointer` is an RFC 6901 JSON Pointer into the submitted document, which
lets a client highlight the exact offending value. Never echo `b64` back in
an error response.

---

## 9. Formal JSON Schema for the envelope

Draft 2020-12. This captures everything decidable without decoding the
image — stages 1 and 3–4 above, minus the bounds check (which needs the
image dimensions) and minus the base64/PNG checks (stage 2). Use it as a
first-pass filter, then run stages 2, 4-bounds, and 5 in code.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.invalid/schemas/zipmap.json/1.1",
  "title": "zipmap.json interchange document",
  "type": "object",
  "required": ["b64", "map_item_datasets"],
  "dependentRequired": { "pdf": ["pdf_b64"] },
  "properties": {
    "zipmap_json": { "type": "string", "enum": ["1.0", "1.1"] },
    "title": { "type": "string" },
    "drawing_number": { "type": "string" },
    "revision": { "type": "string" },
    "image": {
      "type": "object",
      "properties": {
        "format": { "type": "string", "const": "png" },
        "width": { "type": "integer", "minimum": 1 },
        "height": { "type": "integer", "minimum": 1 }
      },
      "additionalProperties": true
    },
    "pdf": {
      "type": "object",
      "properties": {
        "format": { "type": "string", "const": "pdf" },
        "width": { "type": "number", "exclusiveMinimum": 0 },
        "height": { "type": "number", "exclusiveMinimum": 0 },
        "pages": { "type": "integer", "const": 1 }
      },
      "additionalProperties": true
    },
    "extracted_data": {
      "comment": "Opaque by design — see §7. Object-ness is the whole rule; do NOT add properties/required here, or you will make every upstream extraction-schema change a breaking change.",
      "type": ["object", "null"]
    },
    "b64": {
      "type": "string",
      "minLength": 24,
      "pattern": "^[A-Za-z0-9+/\\s]+={0,2}\\s*$"
    },
    "pdf_b64": {
      "type": "string",
      "minLength": 24,
      "pattern": "^[A-Za-z0-9+/\\s]+={0,2}\\s*$"
    },
    "map_item_datasets": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["schema_id", "map_items"],
        "properties": {
          "schema_id": { "type": "string", "minLength": 1 },
          "map_items": {
            "type": "array",
            "items": {
              "type": "object",
              "required": ["x", "y", "x2", "y2"],
              "properties": {
                "x":  { "type": "number" },
                "y":  { "type": "number" },
                "x2": { "type": "number" },
                "y2": { "type": "number" },
                "id": { "type": "string" }
              },
              "additionalProperties": true
            }
          }
        },
        "additionalProperties": true
      }
    }
  },
  "additionalProperties": true
}
```

Three cautions about relying on this schema alone:

- `"type": "number"` in JSON Schema already excludes booleans, but many
  hand-written validators do not. Check your library.
- The `b64` and `pdf_b64` `pattern`s are cheap shape checks, not validity
  checks. Neither verifies padding, length divisibility, or that the payload
  is really a PNG or a PDF. Run stages 2 and 2b regardless.
- `dependentRequired` is draft 2019-09 and later. On draft-07 write it as
  `"dependencies": { "pdf": ["pdf_b64"] }`.

---

## 10. Size and transport

*Advisory.*

Base64 inflates by exactly 4/3, plus the JSON overhead of the items. The
drawing dominates the payload; the items rarely exceed a few hundred KB, and
an extraction record with a long bill of materials rarely exceeds a few tens
of KB.

| Drawing | Typical PNG | `b64` | Body, PNG only | + `pdf_b64` |
|---------|-------------|-------|----------------|-------------|
| Small image-only map, 800×600 | 4 KB | 5 KB | ~10 KB | n/a — no PDF |
| Letter sheet @ 150 DPI, 1275×1650 | 250 KB | 340 KB | ~360 KB | ~500 KB |
| Letter sheet @ 300 DPI, 2550×3300 | 900 KB | 1.2 MB | ~1.3 MB | ~1.5 MB |
| ANSI D iso @ 300 DPI, 10200×6600 | 6 MB | 8 MB | ~8.2 MB | ~8.7 MB |
| ANSI E @ 400 DPI | 20 MB | 27 MB | ~27 MB | ~28 MB |

**The PDF costs far less than the PNG it duplicates.** A CAD-generated
isometric is vector line work: a few hundred KB whatever the sheet size,
because a PDF has no pixels to pay for. The 300-DPI raster of that same
sheet is 6 MB. So carrying both typically adds 5–15%, not 100% — an ANSI D
iso goes from ~8.2 MB to ~8.7 MB. Sizing your endpoint for the PNG alone
already sizes it for both.

The exception is a **scanned** drawing, where the PDF wraps a raster image
of its own and can rival or exceed the PNG. If your senders scan paper, size
for roughly double.

Consequences worth designing for:

- **Raise your body limit deliberately.** Frameworks commonly default to
  1 MB (Express) or 2.5 MB (PHP), which rejects any real 300-DPI drawing.
  Pick a ceiling — 32 MB is generous — and document it, so senders can
  re-render at a lower DPI rather than guess. (QC Database's deployed
  limits are in §12.1: 413 at ~32 MB on the wire, 40 MB base64 aggregate
  via gzipped JSON, 30 MB raw multipart aggregate, 40-megapixel PNG cap.)
- **Accept gzip.** `Content-Encoding: gzip` on the request typically halves
  a base64 PNG payload, because base64 of compressed data still has
  exploitable redundancy at the character level. Advertise support.
- **Stream if you can.** A 27 MB body parsed by a naive JSON library
  materializes the base64 string and then the decoded bytes, so peak memory
  can reach 3–4× the body size. Under concurrency that adds up.
- **Set a generous timeout.** Uploads from a jobsite over LTE are slow, and
  a client that times out at 30 s will retry the whole 27 MB.
- **Compare against multipart.** If you control both ends and payloads run
  large, `multipart/form-data` with the PNG as a binary part avoids the 33%
  inflation entirely. The single-JSON-object shape is a deliberate trade of
  bytes for simplicity — it is what makes the document pasteable, loggable,
  queueable, and trivially storable as a single row or blob. Take the trade
  knowingly.

---

## 11. Security considerations

*Advisory, but do not skip it.* You are accepting a file that arrived from
outside your system.

1. **Cap the encoded size before decoding.** Check `Content-Length` and the
   length of the `b64` string first. Decoding an unbounded base64 string is
   an easy memory exhaustion.
2. **Cap the decoded pixel dimensions.** Read width and height from the
   IHDR (§5.2) *before* handing the bytes to an image library. A PNG
   declaring 60000×60000 is 3.6 gigapixels — a decompression bomb that costs
   ~14 GB of RAM to rasterize while occupying only a few KB on the wire.
   Reject anything beyond a sane maximum (say 20000 px per side, or a total
   pixel budget of 150 MP).
3. **Never trust the extension or the declared `format`.** Validate the
   PNG signature in the decoded bytes.
4. **Treat every string as hostile.** `title`, `drawing_number`, `id`, every
   schema-defined item field, **and every string inside `extracted_data`**
   are attacker-controlled free text. BOM descriptions are the worst of them:
   they typically came from an OCR or LLM pass over an uploaded file, so they
   are untrusted twice over. Escape on output; they will end up in HTML
   overlays, PDF reports, CSV exports, and filenames. Watch for
   CSV-injection leaders (`=`, `+`, `-`, `@`) and path separators in
   anything you use to build a filename.
5. **Scope `schema_id` resolution — and extraction-schema resolution — to
   the authenticated caller's tenant and project.** An id is an opaque token
   supplied by the client; resolving it globally is a cross-tenant data
   leak, and the document format gives you no other guard.
6. **Store the PNG outside your web root**, and serve it with an explicit
   `Content-Type: image/png` and `X-Content-Type-Options: nosniff`.
7. **Re-encode the image if you will display it.** Passing the original
   bytes straight through preserves any exotic ancillary chunks; a
   re-encode normalizes them away. Strip metadata chunks (`tEXt`, `iTXt`,
   `eXIf`) — drawings sometimes carry surprising things in them.
8. **Rate-limit by payload size, not just request count.** One endpoint
   accepting 27 MB bodies is a cheap amplification target.
9. **Do not log the body.** A single request would put megabytes of base64
   into your log pipeline. Log the metadata, the dataset ids, and the item
   counts. Do not log `extracted_data` wholesale either — a bill of
   materials is unbounded.
10. **A PDF is a bigger attack surface than a PNG.** `pdf_b64` decodes to a
    file format with an embedded scripting engine, external references, and
    a long CVE history in every parser that reads it. Treat it accordingly:
    - Cap the encoded length before decoding, exactly as for `b64` (item 1).
    - **Confirm it is single-page** when you parse it (§5.4 rule 4). A
      thousand-page PDF is a cheap resource attack, and the format promises
      you one drawing.
    - Parse it out-of-process or in a sandbox, with a wall-clock and memory
      limit. Never shell out to a converter with a client-controlled
      filename.
    - Strip or refuse JavaScript (`/JS`, `/JavaScript`), embedded files
      (`/EmbeddedFile`), launch actions (`/Launch`), and remote references
      (`/URI`, XFA) before storing or serving it. A drawing needs none of
      them.
    - Serve it with `Content-Type: application/pdf`,
      `X-Content-Type-Options: nosniff`, and
      `Content-Disposition: attachment` unless you deliberately want it
      rendered inline, from a domain that is not your application's origin.
    - Prefer generating your own preview from the PNG that already arrived,
      rather than rasterizing the PDF on demand.

---

## 12. Designing the endpoint

*Advisory — a sketch that works, not a requirement.*

### 12.1 Shape

```http
POST /api/mapping/projects/{project_id}/zipmaps/
Content-Type: application/json
Content-Encoding: gzip
Authorization: Bearer …

{ "package_id": "…", "mode": "append",
  "document": { "zipmap_json": "1.0", "b64": "…", "map_item_datasets": [ … ] } }
```

This is the endpoint as **deployed in QC Database** (there is no `/v1/`
segment in this path). Two wire-level details matter as much as the body:

- **The trailing slash is mandatory.** A slashless POST is answered by
  Django's `APPEND_SLASH` redirect instead of the view — the redirect
  drops the request body and bypasses the gzip-decoding middleware, so
  the upload silently dies.
- **The body is an envelope, not a bare document** — see §12.2. A raw
  `.zipmap.json` posted as the body is rejected with **422**.

Concrete limits for this deployment: the edge returns **413** at roughly
**32 MB on the wire**, so send `Content-Encoding: gzip`; the gzipped JSON
path accepts up to a **40 MB aggregate of base64 payloads** (`b64` +
`pdf_b64`, measured pre-gzip); the multipart path caps at a **30 MB raw
aggregate**; and the embedded PNG is capped at **40 megapixels**
(width × height) — pick the render DPI accordingly.

Put the drawing's identity in the **path**, not in the body. The document's
`drawing_number` is descriptive text (§4.2) and unsuited to routing.

### 12.2 Wrapping vs. extending

If you need extra request-level context — a job number, a package id, an
uploader note, a "replace vs. append" mode — you have two options:

**Wrap** (recommended): keep the document intact under a key.

```json
{ "job_id": "J-4471", "mode": "replace",
  "document": { "zipmap_json": "1.0", "b64": "…", "map_item_datasets": [ … ] } }
```

**Extend**: add fields alongside the document's own. This is legal — §14
requires receivers to ignore unknown top-level fields — but it blurs the
line between the standard document and your API, and a client can no longer
hand you a `.zipmap.json` file unmodified.

Wrapping keeps the file a file. Prefer it.

QC Database wraps. Its envelope is **required**, with exactly this shape:

```json
{ "package_id": "<uuid>", "mode": "append",
  "document": { "zipmap_json": "1.1", "b64": "…", "map_item_datasets": [ … ] } }
```

`package_id` is the UUID of the package the drawing belongs to; `mode` is
`"append"` or `"replace"` (§12.4); `document` is the unmodified
`.zipmap.json`. A bare document with no envelope is a guaranteed **422**.
Each dataset's `schema_id` inside the document must be the server's
**MapItemSchema UUID** — the server resolves nothing else (no slug, no
name), and an exporter-side fallback to a schema's `$id` URI produces an
id the server cannot resolve (§15).

### 12.3 Response

Return what the caller cannot compute: the ids you assigned.

```json
{ "drawing_id": "drw_01J8ZP",
  "image": { "width": 3300, "height": 2550, "url": "https://…/drw_01J8ZP.png" },
  "pdf": { "pages": 1, "url": "https://…/drw_01J8ZP.pdf" },
  "extracted_data": { "stored": true, "schema_id": "des_01H9" },
  "datasets": [
    { "schema_id": "wsc_01H2XYZ", "created": 2, "map_item_ids": ["mi_01J8ZQ", "mi_01J8ZR"] },
    { "schema_id": "hsc_9KQ",     "created": 1, "map_item_ids": ["mi_01J8ZS"] }
  ] }
```

`201 Created` with a `Location` header for a new drawing; `200 OK` for an
update. Echoing which extraction schema you validated the record against is
worth the two fields — it is the sender's only way to find out that their
extractor and your schema have drifted apart.

### 12.4 Idempotency and re-submission

Sending the same map twice is normal — a flaky upload, a retried job, a
corrected revision. Since `id` is not unique (§6.2) you cannot dedup on item
content. Options, roughly in order of robustness:

- **`Idempotency-Key` header**, client-generated per logical submission,
  stored with the result. The standard answer; use it.
- **Content hash** of the canonicalized document, rejecting or short-
  circuiting an exact repeat.
- **Explicit `mode`** — `replace` (delete this drawing's existing items for
  the given `schema_id`s, then insert) versus `append`. Make it explicit
  rather than inferred; the two are impossible to distinguish by looking at
  the payload, and guessing wrong either duplicates every weld on the
  drawing or silently discards field data.

### 12.5 Async ingestion

For large drawings, accept and defer: validate stages 1–4 synchronously
(they are fast and need no database), persist the raw body, return `202
Accepted` with a status URL, then run schema resolution, item validation,
extraction validation, and PDF parsing in a worker. The split falls
naturally, because stages 1–4 are exactly the checks that require nothing
but the document itself — and PDF parsing (§5.4 rule 4) is exactly the kind
of slow, sandboxable work that belongs on the far side of it.

### 12.6 Requiring `pdf_b64`

This specification cannot make `pdf_b64` mandatory (§5): an image-only
zipmap has no PDF, and requiring one would make those documents unsendable
by anyone. Your endpoint is a different matter. If your system stores a
single-page PDF for turnover — QC Database does — then say so explicitly:

```json
{ "error": "pdf_required",
  "message": "This endpoint stores a print-fidelity drawing for turnover. Send pdf_b64: export a PDF-backed zipmap without --no-pdf, or POST to /drawings/web-only instead.",
  "docs": "https://…/api/zipmaps#pdf_required" }
```

Three things make that a good rejection rather than a frustrating one:

- **`422`, not `400`.** The document is well-formed and conformant; it just
  does not satisfy your policy. The distinction tells the sender whether to
  fix their file or their workflow.
- **Name the fix.** The sender's map is either image-only (they need to
  rebuild it from a PDF — the PNG cannot be turned back into one) or they
  passed `--no-pdf`. Those need different answers, and the error text costs
  nothing.
- **Do not silently accept and store a raster instead.** Discovering at
  turnover that a year of drawings are 300-DPI PNGs is the failure this
  field exists to prevent.

If both kinds of map are legitimate in your system, prefer two endpoints or
an explicit mode over inferring intent from what happens to be present.

---

## 13. Reference decoders

*Advisory.* Both examples implement stages 1–4 (including 2b) of §8 and stop
where your system begins. Neither parses the PDF — that is deliberate, and
§5.4 explains why the cheap checks are the right ones to run inline.

### 13.1 Python

```python
import base64, binascii, struct

PNG_SIG = b"\x89PNG\r\n\x1a\n"
PDF_MAGIC = b"%PDF-"
MAX_PIXELS = 150_000_000
MAX_PDF_BYTES = 64 * 1024 * 1024
SUPPORTED = {"1.0", "1.1"}

class Invalid(ValueError):
    pass

def parse_zipmap_json(doc):
    """Validate a decoded .zipmap.json.

    Returns (png_bytes, width, height, datasets, pdf_bytes, extracted_data);
    pdf_bytes and extracted_data are None when the document omits them.
    """
    if not isinstance(doc, dict):
        raise Invalid("top level must be an object")

    version = doc.get("zipmap_json", "1.0")
    if version not in SUPPORTED:
        raise Invalid(f"unsupported zipmap_json version {version!r}")

    b64 = doc.get("b64")
    if not isinstance(b64, str) or not b64.strip():
        raise Invalid('"b64" must be a non-empty base64 string')
    try:
        raw = base64.b64decode("".join(b64.split()), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise Invalid(f'"b64" is not valid base64 ({exc})') from exc
    if len(raw) < 26 or raw[:8] != PNG_SIG or raw[12:16] != b"IHDR":
        raise Invalid('"b64" does not decode to a PNG')
    width, height = struct.unpack(">II", raw[16:24])
    if width * height > MAX_PIXELS:
        raise Invalid(f"image too large: {width}x{height}")

    declared = doc.get("image")
    if isinstance(declared, dict):
        if declared.get("format", "png") != "png":
            raise Invalid("image.format must be \"png\"")
        if (declared.get("width"), declared.get("height")) != (width, height):
            raise Invalid(
                f"image {declared.get('width')}x{declared.get('height')} "
                f"does not match the decoded PNG ({width}x{height})"
            )

    # --- stage 2b: the optional PDF print master -------------------------
    pdf_b64 = doc.get("pdf_b64")
    pdf_meta = doc.get("pdf")
    pdf = None
    if pdf_b64 is None:
        if pdf_meta is not None:
            raise Invalid('"pdf" is declared but "pdf_b64" is absent')
    else:
        if not isinstance(pdf_b64, str) or not pdf_b64.strip():
            raise Invalid('"pdf_b64" must be a non-empty base64 string')
        if len(pdf_b64) > MAX_PDF_BYTES * 4 // 3 + 16:   # cap BEFORE decoding
            raise Invalid("pdf_b64 too large")
        try:
            pdf = base64.b64decode("".join(pdf_b64.split()), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise Invalid(f'"pdf_b64" is not valid base64 ({exc})') from exc
        if not pdf.startswith(PDF_MAGIC):
            raise Invalid('"pdf_b64" does not decode to a PDF')
        if b"%%EOF" not in pdf[-2048:]:
            raise Invalid('"pdf_b64" has no %%EOF marker near the end (truncated?)')
        if isinstance(pdf_meta, dict):
            if pdf_meta.get("format", "pdf") != "pdf":
                raise Invalid('pdf.format must be "pdf"')
            if pdf_meta.get("pages", 1) != 1:
                raise Invalid("the embedded PDF must be single-page")
        elif pdf_meta is not None:
            raise Invalid('"pdf" must be an object')
        # NOTE: single-page is only *asserted* here. Confirm it with a real
        # PDF parser, sandboxed, before you store or render this (§11 item 10).

    # --- the opaque extraction record ------------------------------------
    extracted = doc.get("extracted_data")
    if extracted is not None and not isinstance(extracted, dict):
        raise Invalid('"extracted_data" must be a JSON object')
    # Nothing else. Its fields belong to your extraction schema (§7) —
    # validate them there, not here.

    datasets = doc.get("map_item_datasets")
    if not isinstance(datasets, list):
        raise Invalid('"map_item_datasets" must be an array')

    def number(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v \
            and v not in (float("inf"), float("-inf"))

    out = []
    for di, ds in enumerate(datasets):
        if not isinstance(ds, dict):
            raise Invalid(f"map_item_datasets[{di}]: must be an object")
        sid = ds.get("schema_id")
        if not isinstance(sid, str) or not sid.strip():
            raise Invalid(f'map_item_datasets[{di}]: "schema_id" is required')
        items = ds.get("map_items")
        if not isinstance(items, list):
            raise Invalid(f'map_item_datasets[{di}]: "map_items" must be an array')
        for i, item in enumerate(items):
            where = f"map_item_datasets[{di}] (schema_id={sid}) map_items[{i}]"
            if not isinstance(item, dict):
                raise Invalid(f"{where}: must be an object")
            for f in ("x", "y", "x2", "y2"):
                if not number(item.get(f)):
                    raise Invalid(f'{where}: coordinate "{f}" missing or not a number')
            for f, limit in (("x", width), ("x2", width), ("y", height), ("y2", height)):
                if not 0 <= item[f] <= limit:
                    raise Invalid(f"{where}: {f}={item[f]} outside 0..{limit}")
        out.append((sid.strip(), items))

    return raw, width, height, out, pdf, extracted
```

### 13.2 TypeScript / Node

```ts
const PNG_SIG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
const PDF_MAGIC = Buffer.from("%PDF-", "ascii");
const MAX_PIXELS = 150_000_000;
const MAX_PDF_BYTES = 64 * 1024 * 1024;
const SUPPORTED = new Set(["1.0", "1.1"]);

export interface Dataset { schema_id: string; map_items: Record<string, unknown>[]; }
export interface Parsed {
  png: Buffer; width: number; height: number; datasets: Dataset[];
  pdf?: Buffer;
  /** Opaque by design — validate against YOUR extraction schema, not here. */
  extractedData?: Record<string, unknown>;
}

const isNum = (v: unknown): v is number =>
  typeof v === "number" && Number.isFinite(v);

const isPlainObject = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

export function parseZipmapJson(doc: any): Parsed {
  if (!isPlainObject(doc)) throw new Error("top level must be an object");

  const version = doc.zipmap_json ?? "1.0";
  if (!SUPPORTED.has(version)) throw new Error(`unsupported zipmap_json version ${version}`);

  if (typeof doc.b64 !== "string" || !doc.b64.trim())
    throw new Error('"b64" must be a non-empty base64 string');
  const png = Buffer.from(doc.b64.replace(/\s+/g, ""), "base64");
  if (png.length < 26 || !png.subarray(0, 8).equals(PNG_SIG) ||
      png.subarray(12, 16).toString("ascii") !== "IHDR")
    throw new Error('"b64" does not decode to a PNG');
  const width = png.readUInt32BE(16);
  const height = png.readUInt32BE(20);
  if (width * height > MAX_PIXELS) throw new Error(`image too large: ${width}x${height}`);

  if (doc.image && typeof doc.image === "object") {
    if ((doc.image.format ?? "png") !== "png")
      throw new Error('image.format must be "png"');
    if (doc.image.width !== width || doc.image.height !== height)
      throw new Error(
        `image ${doc.image.width}x${doc.image.height} does not match the decoded PNG (${width}x${height})`);
  }

  // --- stage 2b: the optional PDF print master ---------------------------
  let pdf: Buffer | undefined;
  if (doc.pdf_b64 === undefined || doc.pdf_b64 === null) {
    if (doc.pdf !== undefined && doc.pdf !== null)
      throw new Error('"pdf" is declared but "pdf_b64" is absent');
  } else {
    if (typeof doc.pdf_b64 !== "string" || !doc.pdf_b64.trim())
      throw new Error('"pdf_b64" must be a non-empty base64 string');
    if (doc.pdf_b64.length > (MAX_PDF_BYTES * 4) / 3 + 16)  // cap BEFORE decoding
      throw new Error("pdf_b64 too large");
    pdf = Buffer.from(doc.pdf_b64.replace(/\s+/g, ""), "base64");
    if (!pdf.subarray(0, 5).equals(PDF_MAGIC))
      throw new Error('"pdf_b64" does not decode to a PDF');
    if (!pdf.subarray(-2048).includes("%%EOF"))
      throw new Error('"pdf_b64" has no %%EOF marker near the end (truncated?)');
    if (doc.pdf !== undefined && doc.pdf !== null) {
      if (!isPlainObject(doc.pdf)) throw new Error('"pdf" must be an object');
      if ((doc.pdf.format ?? "pdf") !== "pdf") throw new Error('pdf.format must be "pdf"');
      if ((doc.pdf.pages ?? 1) !== 1) throw new Error("the embedded PDF must be single-page");
    }
    // NOTE: single-page is only *asserted* here. Confirm it with a real PDF
    // parser, sandboxed, before you store or render this (§11 item 10).
  }

  // --- the opaque extraction record --------------------------------------
  let extractedData: Record<string, unknown> | undefined;
  if (doc.extracted_data !== undefined && doc.extracted_data !== null) {
    if (!isPlainObject(doc.extracted_data))
      throw new Error('"extracted_data" must be a JSON object');
    extractedData = doc.extracted_data;
    // Nothing else. Its fields belong to your extraction schema (§7).
  }

  if (!Array.isArray(doc.map_item_datasets))
    throw new Error('"map_item_datasets" must be an array');

  const datasets: Dataset[] = doc.map_item_datasets.map((ds: any, di: number) => {
    if (typeof ds !== "object" || ds === null || Array.isArray(ds))
      throw new Error(`map_item_datasets[${di}]: must be an object`);
    if (typeof ds.schema_id !== "string" || !ds.schema_id.trim())
      throw new Error(`map_item_datasets[${di}]: "schema_id" is required`);
    if (!Array.isArray(ds.map_items))
      throw new Error(`map_item_datasets[${di}]: "map_items" must be an array`);
    ds.map_items.forEach((item: any, i: number) => {
      const where = `map_item_datasets[${di}] (schema_id=${ds.schema_id}) map_items[${i}]`;
      if (typeof item !== "object" || item === null || Array.isArray(item))
        throw new Error(`${where}: must be an object`);
      for (const f of ["x", "y", "x2", "y2"] as const)
        if (!isNum(item[f])) throw new Error(`${where}: coordinate "${f}" missing or not a number`);
      for (const [f, limit] of [["x", width], ["x2", width], ["y", height], ["y2", height]] as const)
        if (!(item[f] >= 0 && item[f] <= limit))
          throw new Error(`${where}: ${f}=${item[f]} outside 0..${limit}`);
    });
    return { schema_id: ds.schema_id.trim(), map_items: ds.map_items };
  });

  return { png, width, height, datasets, pdf, extractedData };
}
```

Note the JavaScript specifics: `Buffer.from(s, "base64")` is permissive —
it silently ignores invalid characters rather than throwing — so the PNG and
PDF magic-byte checks are doing real work, not merely confirming the format.
`Number.isFinite` already excludes booleans, `NaN`, and `Infinity`, which
`typeof v === "number"` alone would not fully cover. And `extracted_data`
needs the `Array.isArray` guard that `typeof x === "object"` does not give
you — a JSON array would otherwise sail through as an object.

---

## 14. Versioning and forward compatibility

- The version lives in `zipmap_json`. `"1.0"` and `"1.1"` are defined.
- **Receivers MUST ignore unknown fields**, at every level: top level,
  inside `image`, inside `pdf`, inside a dataset object, inside an item
  (where unknown fields are the norm, since items are schema territory), and
  everywhere inside `extracted_data` (which is *entirely* unknown fields by
  construction). This is what lets a document gain optional fields without a
  version bump.
- A **minor** version only adds optional fields. A receiver that implements
  1.0 and ignores unknown fields will read a 1.1 document correctly, and MAY
  choose to accept it on that basis.
- A **major** version (`"2.0"`) may change or remove required fields.
  Reject versions you do not implement rather than guessing.
- If you version your API path (`/api/v1/…`), keep that version independent
  of `zipmap_json`. They answer different questions: yours describes your
  endpoint's contract, this one describes the document's shape.

### 14.1 What 1.1 changed, exactly

Three optional top-level fields: `pdf_b64`, `pdf`, `extracted_data`. Nothing
else. No 1.0 field changed meaning, moved, or became optional or required.

Consequences, spelled out because they are the questions people ask:

| Question | Answer |
|----------|--------|
| Is a 1.0 document still valid? | Yes, unchanged, forever. |
| Must a 1.1 document carry the new fields? | No. A 1.1 document with none of them is byte-identical in shape to a 1.0 one. |
| Will a 1.0-only receiver break on 1.1? | Only on the version string, if it hard-compares to `"1.0"`. The document body is safe — §13 already required ignoring unknown fields. |
| Then why bump the version at all? | So a receiver can tell whether the *absence* of `pdf_b64` means "the sender had no PDF" or "the sender predates the field". Silently adding fields under `"1.0"` destroys that distinction permanently. |
| What is the minimum upgrade? | Accept `{"1.0", "1.1"}` instead of `{"1.0"}`. That alone makes a conformant 1.0 receiver a conformant 1.1 receiver for everything except the new fields, which it will ignore. |

If you consume the new fields, add stage 2b (§8) and the `extracted_data`
object check. Both are ~15 lines; §13 has them written out.

---

## 15. Relationship to `.zipmap` and `.zipmapt`

| | `.zipmap` | `.zipmapt` | `.zipmap.json` |
|---|---|---|---|
| Container | zip archive | zip archive | one JSON object |
| Drawing PNG | `img/drawing.png` | — | `b64` |
| Source PDF | `pdf/drawing.pdf`, optional | — | `pdf_b64`, optional *(1.1)* |
| Extraction record | `extracted_data.json`, optional | — | `extracted_data`, optional *(1.1)* |
| Item data | `img/*.json` + `pdf/*.json` | — | `map_item_datasets[].map_items` |
| Coordinate spaces | pixels *and* PDF points | — | pixels only |
| Item schemas | `schemata/*.schema.json`, bundled | bundled | **not included** — `schema_id` instead |
| Manifest | `manifest.json` | — | a few optional top-level fields |
| Audience | humans, filesystems | project standardization | APIs |

### 15.1 What the export drops

The **PDF-space data files** (`pdf/*.json`), all bundled JSON Schemas, the
manifest's `created` / `source` / `render_dpi` / `pdf` fields, and the
`zipmap.geometry` rendering hint.

Note what it no longer drops: as of 1.1 the PDF *file* and the extraction
record both travel. The `pdf/` **layer** in the archive sense — the
point-coordinate data files — is still never exported, and never will be:
the whole design keeps coordinate math on the sending side.

### 15.2 Export is one-way

A `.zipmap.json` cannot be turned back into a valid `.zipmap` on its own:
the archive format *requires* a `schemata/<type>.schema.json` for every data
file, and those schemas are exactly what the document dropped. Round-
tripping means fetching each `schema_id`'s schema from the system that
issued it.

1.1 narrows the loss but does not close it. With `pdf_b64` the original
vector drawing now survives the trip — before, a `.zipmap.json` could only
ever be rebuilt as an image-only map, because a rendered PNG cannot become
a PDF again. The schemas, the PDF-space item coordinates, and the manifest's
provenance fields are still gone.

Plan accordingly: **the `.zipmap` is the archival artifact**, and the
`.zipmap.json` is a projection of it for transport. Keep the archive.

### 15.3 Where `schema_id` comes from on the sending side

Ids are bound into the source archive's schemas, so they travel with the
file and survive every later export:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Weld map item",
  "zipmap": { "geometry": "flag", "schema_id": "wsc_01H2XYZ" },
  "required": ["id", "x", "y", "x2", "y2"],
  "properties": { "…": {} }
}
```

The exporter resolves an id for each type in this order, first match wins:

1. an explicit override — `--schema-id weld=<id>` on the CLI, or
   `schema_ids={"weld": "<id>"}` in the library;
2. `schemata/<type>.schema.json` → `zipmap.schema_id`;
3. `schemata/<type>.schema.json` → `$id`.

If no id resolves, **the export fails** — there is no default, no
auto-generated id, and no way to emit a dataset without one.

Beware step 3: a schema's `$id` is usually a URI
(`https://example.com/weld.schema.json`), which is a syntactically valid
`schema_id` but resolvable by no server. QC Database in particular accepts
**only its MapItemSchema UUIDs** — no slug or name fallback — so an
export that fell through to `$id` validates locally and then fails at
stage 5 on the server. Fetch the real UUID from the schema list endpoint
and bind it explicitly (`--schema-id <type>=<uuid> --bind`) so steps 1–2
always answer first.

**Publish your ids.** The single most useful thing you can do for senders is
expose a list endpoint (`GET /map-item-schemas`) returning each schema's id,
name, geometry, and field definitions. Otherwise every sender is guessing at
opaque tokens, and every guess becomes a stage-5 rejection.

---

## 16. Producing a document

For reference, from the skill that defines this format:

```bash
# bind ids into the schemas once — they then travel inside the .zipmap
python scripts/to_json.py mymap --schema-id weld=wsc_01H2XYZ --bind

python scripts/to_json.py mymap                     # -> mymap.zipmap.json
python scripts/to_json.py mymap.zipmap -o body.json # from an archive
python scripts/to_json.py mymap --compact           # minified, for the wire
python scripts/to_json.py mymap --stdout --compact \
  | jq -c '{package_id: "<package-uuid>", mode: "append", document: .}' \
  | gzip \
  | curl -X POST "https://…/api/mapping/projects/<project-uuid>/zipmaps/" \
         -H 'Content-Type: application/json' -H 'Content-Encoding: gzip' \
         --data-binary @-   # envelope + trailing slash: both mandatory (§12.1–12.2)

python scripts/validate.py mymap.zipmap.json        # verify before sending
```

`pdf_b64` and `extracted_data` are included **by default** whenever the
source map has them — a receiver that requires the print master gets it
without the sender opting in. To leave them out:

```bash
python scripts/to_json.py mymap --no-pdf              # PNG only, smaller body
python scripts/to_json.py mymap --no-extracted-data   # omit the record
python scripts/to_json.py mymap --extracted-data bom.json   # or supply/override it
```

The extraction record comes from `extracted_data.json` at the archive root;
`--extracted-data` reads it from a file instead, which is the path for an
extractor that writes its output beside the map rather than into it. Either
way it must be a JSON **object** — that is the only check made.

```python
from zipmap import to_json, write_json, validate_json_doc, write_extracted_data

write_extracted_data("mymap", extractor_output)   # -> mymap/extracted_data.json

report, doc = to_json("mymap", schema_ids={"weld": "wsc_01H2XYZ"})
if report.ok:
    requests.post(url, json=doc)

report, path = write_json("mymap.zipmap")       # -> mymap.zipmap.json
report, doc = to_json("mymap", include_pdf=False)          # PNG only
report, doc = to_json("mymap", extracted_data=record)      # override the record
report, info = validate_json_doc(doc)           # the stage 1–4 checks
```

---

## 17. Conformance summary

A receiver conforms to this specification if it:

1. accepts a UTF-8 JSON object body;
2. requires `b64` and `map_item_datasets`, and nothing else;
3. rejects a `zipmap_json` version it does not implement, accepts both
   `"1.0"` and `"1.1"`, and assumes `"1.0"` when the field is absent;
4. decodes `b64` as standard base64 and requires the result to be a PNG;
5. requires a present `image` to agree with the decoded PNG;
6. requires a present `pdf_b64` to decode to a PDF (`%PDF-` header, `%%EOF`
   near the end), requires a present `pdf` to accompany it and to declare
   `format` `"pdf"` and `pages` `1` if it declares them at all, and accepts
   a document that carries neither;
7. requires a present `extracted_data` to be a JSON object, and validates
   nothing inside it at the interchange layer;
8. requires every dataset to carry a non-empty `schema_id` and an array
   `map_items`;
9. requires every item to carry four finite numeric coordinates within the
   image's inclusive bounds;
10. treats `(x, y)`/`(x2, y2)` as top-left-origin pixel offsets, imposing no
    ordering between the two points, and never treats the PDF as a
    coordinate space;
11. rejects any `schema_id` it cannot resolve in the caller's scope, and
    validates item fields against the resolved schema — and
    `extracted_data` against its own extraction schema — rather than
    against anything in the document;
12. makes no assumption that `id` is present or unique; and
13. ignores unknown fields at every level.

An endpoint MAY additionally require `pdf_b64` as a matter of policy
(§12.6); doing so does not affect conformance.
