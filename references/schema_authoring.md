# Authoring map-item schemas

Each map-item type in a zipmap is defined by one JSON Schema at
`schemata/<type>.schema.json`. The schema validates **one item object** from
the `items` array of the matching `<type>.json` data files — not the wrapper
(the wrapper's `space`/`width`/`height`/`schema`/`items` fields are enforced
by the format itself).

## The schema is yours

zipmaps has **no standard item schema and no field dictionary**, deliberately.
The format fixes five item fields — `id`, `x`, `y`, `x2`, `y2` — and stops.
Type names are open (`weld`, `support`, `tie_in`, `punch`, `insulation`,
`valve`, `soudure` — whatever the project calls them), and every other field is
whatever the source system, the discipline, or the user says it is: flat or
nested, imperial or metric, English or not.

Write the schema **to describe the data you actually have**, not to make the
data conform to somebody else's idea of a weld. That is what makes a zipmap a
translation target: a map exported from one tracking system keeps that system's
vocabulary inside a container any other tool can open, and the receiving
system's `schema_id` — not this file — decides whether the fields are
acceptable there. A schema here documents and sanity-checks; it is not a
gatekeeper.

Practical consequences: prefer permissive types, mark almost nothing
`required`, keep `additionalProperties` open, and never drop a source field
because you couldn't classify it.

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
  rating, heat number, whatever the discipline (or the source system) actually
  uses, under the names it actually uses. Mark truly mandatory fields
  `required`; leave the rest optional. When in doubt, optional.

- Keep `"additionalProperties": true` unless you specifically want to lock
  the type down — transportability favors tolerance of extra fields. A strict
  schema makes a map that only your system can accept, which is the opposite
  of the point.

- Nested objects and arrays are fine (`"inspection": {"type": "object"}`,
  `"repairs": {"type": "array"}`). Only the five coordinate/id fields have to
  be flat scalars.

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

Starter schemas in `assets/starter_schemas/` ship **without** ids: an id is specific
to your server and project, so `to_json.py` fails with a clear message until
you supply one. Get real ids from the tracking system's map-item schema
listing rather than inventing them.

## Starter schemas

`assets/starter_schemas/` ships three ready-to-copy examples
(`scripts/init.py --types` copies them): `weld` (flag), `flange` (flag),
`heat` (rect). Copy one as a starting point for a new type and rename file +
fields — or ignore them entirely and write your own; they carry no authority.
Their field names (`weld_type`, `torque_spec`, `mtr`) are one team's
vocabulary, not the format's. See `assets/starter_schemas/README.md`.

When the project has a `.zipmapt` template, **that** is its standard — open it
and build on its schemata instead of the starters.

## Translating another system's map

Authoring a schema for data that came out of some other tracker, CSV, or
marked-up drawing:

1. Sample the source and list the fields it really has.
2. Name the type after what the source calls it.
3. Map only the geometry: source location → `x`/`y`, label/leader anchor or
   opposite corner → `x2`/`y2` (duplicate `x`/`y` when there is no second
   point). `id` is the source's own identifier, as a string.
4. Declare every remaining field permissively, in the source's own names.
   Fields you can't interpret still go in — loosely typed or left to
   `additionalProperties`.
5. Bind the target system's `schema_id` last, once you know it.

Any renaming the destination demands happens explicitly at export time, not
quietly while authoring.

## Validator support

Validation uses the `jsonschema` package when installed; otherwise a bundled
fallback validator covers the common draft-07 subset: `type`, `enum`,
`const`, `required`, `properties`, `additionalProperties`, `pattern`,
`minimum`/`maximum`/`exclusive*`, `minLength`/`maxLength`, `items`,
`minItems`/`maxItems`, `allOf`/`anyOf`/`oneOf`. Stick to that subset and
schemas behave identically with or without `jsonschema`; exotic keywords
(`$ref`, `if/then`, `patternProperties`, …) require `pip install jsonschema`.
