# Authoring map-item schemas

Each map-item type in a zipmap is defined by one JSON Schema at
`schemata/<type>.schema.json`. The schema validates **one item object** from
the `items` array of the matching `<type>.json` data files — not the wrapper
(the wrapper's `space`/`width`/`height`/`schema`/`items` fields are enforced
by the format itself).

> **Not to be confused with the drawing's extraction record.** `schemata/`
> defines the things placed *on* the drawing — welds, flanges, heats, each
> with coordinates. `extracted_data.json` is what was read *off* the
> drawing — bill of materials, line number, title-block parameters — and it
> has **no schema in the zipmap at all**: the format requires only that it
> be a JSON object, because its fields belong to the receiving system's
> drawing-extraction schema. Do not write a `schemata/*.schema.json` for it.
> See `format_spec.md` → "extracted_data.json".

## Conventions

- Always require the base fields the format depends on:

  ```json
  "required": ["id", "x", "y", "x2", "y2"],
  "properties": {
    "id":  { "type": "string", "minLength": 1 },
    "x":   { "type": "number" },
    "y":   { "type": "number" },
    "x2":  { "type": "number" },
    "y2":  { "type": "number" }
  }
  ```

  (The pipeline checks coordinates and bounds even if a schema forgets them,
  but a schema that requires them gives clearer errors.)

- Add the type's real-world fields as properties — size, schedule, material,
  rating, heat number, whatever the discipline needs. Mark truly mandatory
  fields `required`; leave the rest optional.

- Keep `"additionalProperties": true` unless you specifically want to lock
  the type down — transportability favors tolerance of extra fields.

- **Do not** enforce `id` uniqueness in a schema; the format is deliberately
  unopinionated about numbering.

## The geometry hint

A schema may carry a top-level custom hint telling renderers how to draw the
item's two points:

```json
"zipmap": { "geometry": "flag" }
```

- `"flag"` (default) — `(x, y)` is the map point, `(x2, y2)` anchors the
  label flag; renderers draw a pin, a leader line, and the label.
- `"rect"` — `(x, y)` and `(x2, y2)` are opposite corners of a rectangular
  callout (e.g., a heat-number region); renderers draw the rectangle.

Unknown keywords are legal JSON Schema, so this hint never breaks a standard
validator.

## The schema id

The same `zipmap` object holds the type's **server-side schema id** — the
identifier of the matching map-item schema in the weld/flange/heat tracking
system:

```json
"zipmap": { "geometry": "flag", "schema_id": "wsc_01H2XYZ" }
```

This is what a `.zipmap.json` export carries *instead of* the schema itself
(see `zipmap_json_spec.md`), so **every type you intend to export needs
one**.
A plain `"$id"` at the schema's top level is used as a fallback when
`zipmap.schema_id` is absent.

Bind it once and it travels with the schema — into the `.zipmap`, and into
any `.zipmapt` template built from it, so a project's templates carry its
type↔schema bindings for everyone:

```bash
python scripts/to_json.py mymap --schema-id weld=wsc_01H2XYZ --bind
```

Starter schemas in `assets/schemas/` ship **without** ids: an id is specific
to your server and project, so `to_json.py` fails with a clear message until
you supply one. Get real ids from the tracking system's map-item schema
listing rather than inventing them.

## Starter schemas

`assets/schemas/` ships ready-to-copy schemas (`scripts/init.py --types`
copies them): `weld` (flag), `flange` (flag), `heat` (rect). Copy one as a
starting point for a new type and rename file + fields.

## Validator support

Validation uses the `jsonschema` package when installed; otherwise a bundled
fallback validator covers the common draft-07 subset: `type`, `enum`,
`const`, `required`, `properties`, `additionalProperties`, `pattern`,
`minimum`/`maximum`/`exclusive*`, `minLength`/`maxLength`, `items`,
`minItems`/`maxItems`, `allOf`/`anyOf`/`oneOf`. Stick to that subset and
schemas behave identically with or without `jsonschema`; exotic keywords
(`$ref`, `if/then`, `patternProperties`, …) require `pip install jsonschema`.
