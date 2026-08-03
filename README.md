# zipmaps

A skill for **`.zipmap`** files — transportable weld/flange/heat maps.

A `.zipmap` is a plain zip archive packaging one construction drawing
(single-page PDF and/or PNG), JSON map-item data (`x/y` map point +
`x2/y2` flag anchor or rectangle corner, plus discipline fields like size,
schedule, material), the JSON Schemas defining each item type, and
optionally the drawing's extraction record (bill of materials, line number,
title-block parameters — an opaque JSON object the format does not
constrain). Every valid zipmap contains a PNG of the drawing, so web readers
display it with zero conversion.

## Flexible on purpose

zipmaps standardizes **the container, not the content**. Fixed: the archive
layout, the data-file wrapper (`space`, `width`, `height`, `schema`, `items`),
and five item fields — `id`, `x`, `y`, `x2`, `y2`. Open: which item types exist,
and every other field on them. `weld`, `flange`, `heat` are examples that ship
in `assets/starter_schemas/`, not a vocabulary the format endorses; `support`,
`tie_in`, `punch`, or a type named in another language works identically the
moment a schema sits beside the data.

The schemas inside a zipmap are **documentation that travels**, not a gate.
Keep `additionalProperties` open, require little, and carry a source system's
field names through verbatim.

That is what makes it a translation target: point an AI at a map living in one
system's format — a vendor JSON export, a CSV, a marked-up drawing — have it
author matching schemas and coordinate data, run it through `save` and
`to_json`, and the result is a single JSON object ready to POST straight to the
*target* system's API, where that system validates the fields against its own
schema via `schema_id`. The mapping is judgment work; the coordinate math,
bounds checks, rendering, and packaging are scripts.

- Concept: `idea.md`
- Normative spec: `references/format_spec.md`
- API interchange spec: `references/zipmap_json_spec.md`
- Agent instructions: `SKILL.md`
- Library: `src/zipmap/` (stdlib-only; `pymupdf` needed for PDF-backed maps)
- CLI: `scripts/` (`init`, `save`, `open`, `validate`, `to_json`, `render`, `view`, `print_pdf`, `make_template`, `pdf2img`, `transform`)
- Bundled runner: `scripts/zm.py` — every command above as a subcommand, chained
  with `::` in a single process (`zm.py save m :: validate m :: render m`), plus
  job files and `--json` output. ~3.4x faster than the same steps as separate
  processes.

A **`.zipmapt`** template is the same archive with only `schemata/` inside —
it standardizes a project's item types and doubles as the starting folder of
a new zipmap.

A **`.zipmap.json`** is the interchange document: the same map flattened
into one API-friendly JSON object — base64 PNG for web views, base64
single-page PDF for high-fidelity turnover, the drawing's extraction record,
and pixel-space items grouped by a server-side `schema_id` in place of the
bundled schemas. `python scripts/to_json.py mymap` → `mymap.zipmap.json`.
Building the endpoint that receives one? `references/zipmap_json_spec.md` is
written for exactly that.
- Example: `examples/simple_weld_map/`

Both formats are at **v1.1**. The bump is purely additive — every 1.0
archive and every 1.0 document is still valid, and readers accept both. See
the version-history tables in `references/format_spec.md` and
`references/zipmap_json_spec.md` §14.1.

Package for distribution with `python package.py` → `zipmaps.skill`.

MIT license. Developed by the [qcdatabase.ai](https://qcdatabase.ai) team.
