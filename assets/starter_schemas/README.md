# Starter schemas — examples, not a standard

**Nothing in this directory is part of the zipmap format.** These three files
(`weld`, `flange`, `heat`) exist only so `init.py --types` and
`make_template.py --types` have something to copy when you don't already have
schemas of your own. They are a convenience, and they are disposable.

The zipmap format standardizes exactly two things about an item type:

1. the **wrapper** of a data file (`space`, `width`, `height`, `schema`, `items`), and
2. five **item fields** — `id`, `x`, `y`, `x2`, `y2`.

Every other field on a map item is yours. `weld_type`, `torque_spec`,
`heat_number` are what one team happened to call things; a schema with
`joint_no`, `couche`, `bolt_torque_nm`, or a nested `inspection: {...}` object
is equally valid and needs no change to the format. Type *names* are open too:
`support.json`, `tie_in.json`, `punch.json`, `insulation.json` all work the
moment `schemata/<name>.schema.json` exists beside them.

So:

- **Copy and gut these freely** — rename the file, delete fields you don't
  have, add the ones you do.
- **Prefer a `.zipmapt` template** when the project has one. A template is the
  project's real standard; these starters are the fallback for when there
  isn't one.
- **Don't treat a missing starter field as missing data**, and don't bend
  someone else's field names to match these. When translating a map out of
  another system, keep that system's vocabulary and write a schema that
  describes it.

See `references/schema_authoring.md` for how to write one.
