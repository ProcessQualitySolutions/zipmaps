"""The `.zipmap.json` interchange document — the API-facing face of a zipmap.

A `.zipmap` is a file: a zip of a drawing, pixel/PDF data files, and the
JSON Schemas that define each item type. A `.zipmap.json` is the same map
flattened into **one JSON object** that can be POSTed to an endpoint:

    {
      "zipmap_json": "1.1",
      "image": {"format": "png", "width": 800, "height": 600},
      "pdf": {"format": "pdf", "width": 792, "height": 612, "pages": 1},
      "extracted_data": {"bill_of_materials": [...], "line_number": "..."},
      "b64": "<base64 of img/drawing.png>",
      "pdf_b64": "<base64 of pdf/drawing.pdf>",
      "map_item_datasets": [
        {"schema_id": "...", "map_items": [{...}, {...}]}
      ]
    }

Three deliberate differences from the archive format:

1. **Only the pixel layer travels.** Coordinates are always `img`-space
   pixels against the embedded PNG, so a consumer needs no PDF math. The
   PDF may still ride along as `pdf_b64`, but it is the *print master* for
   high-fidelity turnover, never a coordinate space: nothing in the
   document is measured against it.
2. **Schemas are replaced by a schema id.** The document carries no JSON
   Schema; each dataset names a `schema_id` that resolves to a schema held
   server-side (the weld/flange/heat tracking system's map-item schema).
   A `schema_id` is therefore **required** for every dataset — a zipmap
   whose types have no ids cannot be exported.
3. **`extracted_data` is opaque.** The drawing's own extraction record (bill
   of materials, line number, title-block parameters) travels verbatim. The
   format requires it to be a JSON object and requires nothing else of it —
   its fields are defined by the receiving system's drawing-extraction
   schema, exactly as map-item fields are defined by `schema_id`.

Ids are resolved per type, first match wins:

1. an explicit override (`schema_ids={"weld": "..."}`, CLI `--schema-id`),
2. `schemata/<type>.schema.json` -> `"zipmap": {"schema_id": "..."}`,
3. `schemata/<type>.schema.json` -> `"$id"`.

`bind_schema_id()` writes an id into a schema file so step 2 answers on
every later export.

The normative document specification — every field, the receiver-side
validation order, an envelope JSON Schema, and reference decoders — lives
in references/zipmap_json_spec.md.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

_WS = re.compile(r"\s")

from . import (
    COORD_FIELDS,
    DRAWING_PDF,
    DRAWING_PNG,
    EXTRACTED_DATA,
    IMG_DIR,
    JSON_FORMAT_VERSION,
    JSON_FORMAT_VERSIONS,
    JSON_SUFFIX,
    MANIFEST,
    PDF_DIR,
    SCHEMATA_DIR,
    ZipmapError,
)
from .imaging import png_size_bytes
from .pdfio import check_pdf_bytes
from .pipeline import Report, _extracted_summary, validate_folder

META_FIELDS = ("title", "drawing_number", "revision")


# --------------------------------------------------------------------------
# schema ids


def schema_id_of(schema: dict) -> str | None:
    """Read a map-item schema's server-side id, or None if it declares none."""
    hint = schema.get("zipmap")
    if isinstance(hint, dict):
        sid = hint.get("schema_id")
        if isinstance(sid, str) and sid.strip():
            return sid.strip()
    sid = schema.get("$id")
    if isinstance(sid, str) and sid.strip():
        return sid.strip()
    return None


def bind_schema_id(root: str | Path, type_name: str, schema_id: str) -> Path:
    """Write `zipmap.schema_id` into schemata/<type>.schema.json in place."""
    path = Path(root) / SCHEMATA_DIR / f"{type_name}.schema.json"
    if not path.is_file():
        raise FileNotFoundError(f"{SCHEMATA_DIR}/{type_name}.schema.json not found")
    schema = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(schema, dict):
        raise ValueError(f"{path.name}: schema must be a JSON object")
    hint = schema.get("zipmap")
    schema["zipmap"] = {**hint, "schema_id": schema_id} if isinstance(hint, dict) else {
        "schema_id": schema_id
    }
    path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# export


def _wanted(name: str) -> bool:
    """Is this archive member needed to build a .zipmap.json?

    The manifest (for title/drawing_number/revision and the PDF's page
    size), extracted_data.json, the schemata (for schema_id resolution), and
    the whole img/ layer. Everything under pdf/ is excluded: no coordinate in
    the document derives from it, and drawing.pdf is usually the largest
    member in the archive. `pdf_b64` needs the PDF's *bytes*, not a
    validatable pdf/ layer, so `_pdf_bytes()` reads that one member straight
    out of the zip instead — which also keeps the extracted folder honestly
    image-only, so validate_folder is not asked to check a pdf/ layer that
    was deliberately left behind.
    """
    return name in (MANIFEST, EXTRACTED_DATA) or name.startswith(
        (f"{SCHEMATA_DIR}/", f"{IMG_DIR}/")
    )


@contextmanager
def as_folder(target: str | Path) -> Iterator[tuple[Path, Path | None]]:
    """Yield a working folder for a folder path or a .zipmap archive.

    A folder is used in place. An archive is *partially* extracted to a
    temporary directory — only the members `_wanted()` keeps — which is
    removed on exit. Yields (path, archive), where archive is the source
    .zipmap when one was extracted and None for a plain folder.
    """
    target = Path(target)
    if target.is_dir():
        yield target, None
        return

    import zipfile

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / target.stem
        dest.mkdir(parents=True, exist_ok=True)
        base = dest.resolve()
        with zipfile.ZipFile(target) as zf:
            members = [m for m in zf.namelist() if _wanted(m)]
            for member in members:
                if not (dest / member).resolve().is_relative_to(base):
                    raise ZipmapError(f"unsafe path in archive: {member}")
            zf.extractall(dest, members=members)
        yield dest, target


def _pdf_bytes(root: Path, archive: Path | None) -> bytes | None:
    """The single-page drawing PDF's raw bytes, or None when there is none.

    From a working folder that is pdf/drawing.pdf; from an archive it is the
    one member `_wanted()` skipped, read directly rather than extracted.
    """
    if archive is None:
        path = root / PDF_DIR / DRAWING_PDF
        return path.read_bytes() if path.is_file() else None

    import zipfile

    with zipfile.ZipFile(archive) as zf:
        try:
            return zf.read(f"{PDF_DIR}/{DRAWING_PDF}")
        except KeyError:
            return None


def to_json(
    target: str | Path,
    schema_ids: dict[str, str] | None = None,
    validate: bool = True,
    include_meta: bool = True,
    include_pdf: bool = True,
    include_extracted_data: bool = True,
    extracted_data: dict[str, Any] | None = None,
) -> tuple[Report, dict[str, Any] | None]:
    """Build the `.zipmap.json` document for a working folder or a .zipmap.

    Returns (report, document). The document is None when anything blocked
    the export — a failed validation, a missing PNG, or a type with no
    `schema_id`. `validate=False` demotes zipmap validation errors to
    warnings (the structural essentials are still required).

    `include_pdf` embeds pdf/drawing.pdf as `pdf_b64` when the map has one:
    the PNG is what a browser draws, the PDF is the print master a turnover
    package needs at full fidelity, and a receiver that requires both wants
    them in the same request. It is a no-op on an image-only map.

    `include_extracted_data` carries extracted_data.json through as the
    document's `extracted_data`; `extracted_data=` supplies or overrides that
    record without touching the source (it must be a JSON object — nothing
    else about its shape is this format's business).
    """
    if extracted_data is not None and not isinstance(extracted_data, dict):
        raise ValueError(
            f"extracted_data must be a JSON object, got {type(extracted_data).__name__}"
        )
    with as_folder(target) as (root, archive):
        return _to_json_folder(
            root, schema_ids or {}, validate, include_meta,
            include_pdf, include_extracted_data, extracted_data, archive,
        )


def _to_json_folder(
    root: Path,
    schema_ids: dict[str, str],
    validate: bool,
    include_meta: bool,
    include_pdf: bool = True,
    include_extracted_data: bool = True,
    extracted_override: dict[str, Any] | None = None,
    archive: Path | None = None,
) -> tuple[Report, dict[str, Any] | None]:
    from_archive = archive is not None
    if from_archive:
        # Only the img/ layer was extracted, so pdf/ checks and the manifest's
        # cross-checks against pdf/ have nothing to run against. The img/ layer
        # itself — wrapper, bounds, and schema — is still fully validated, as is
        # extracted_data.json, and the archive passed the save gate when it was
        # written. Use validate.py on the .zipmap when you want the
        # whole-archive verdict.
        report, info = validate_folder(
            root, require_manifest=False, check_manifest=False, pdf_checks=False
        )
    else:
        # only the img/ layer is exported, so a PDF-backed map still converts on
        # a machine without pymupdf — the pdf/ layer just goes unverified
        from .pdfio import have_pymupdf

        pdf_checks = not (root / PDF_DIR / DRAWING_PDF).is_file() or have_pymupdf()
        report, info = validate_folder(root, require_manifest=False, pdf_checks=pdf_checks)
        if not pdf_checks:
            report.warn(
                f"pymupdf not installed — {PDF_DIR}/ was not verified; only the "
                f"{IMG_DIR}/ layer (which is what the document carries) was checked"
            )
    if report.errors:
        if validate:
            return report, None
        report.warnings.extend(f"(--no-validate) {e}" for e in report.errors)
        report.errors.clear()

    png = root / IMG_DIR / DRAWING_PNG
    if not png.is_file():
        report.error(f"{IMG_DIR}/{DRAWING_PNG} is missing — nothing to encode")
        return report, None
    raw = png.read_bytes()
    try:
        width, height = png_size_bytes(raw[:26], f"{IMG_DIR}/{DRAWING_PNG}")
    except ValueError as exc:
        report.error(str(exc))
        return report, None

    datasets = []
    for dpath in sorted((root / IMG_DIR).glob("*.json")):
        stem = dpath.stem
        try:
            data = json.loads(dpath.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            report.error(f"{IMG_DIR}/{dpath.name}: cannot parse JSON ({exc})")
            continue
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            report.error(f"{IMG_DIR}/{dpath.name}: \"items\" must be an array")
            continue

        schema_id = schema_ids.get(stem)
        if not schema_id:
            spath = root / SCHEMATA_DIR / f"{stem}.schema.json"
            if spath.is_file():
                try:
                    schema = json.loads(spath.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    report.error(f"{SCHEMATA_DIR}/{spath.name}: cannot parse JSON ({exc})")
                    continue
                if isinstance(schema, dict):
                    schema_id = schema_id_of(schema)
        if not schema_id:
            report.error(
                f"{stem}: no schema_id — a .zipmap.json dataset must name the "
                f"server-side schema. Add \"zipmap\": {{\"schema_id\": \"...\"}} to "
                f"{SCHEMATA_DIR}/{stem}.schema.json (or pass --schema-id {stem}=<id>)"
            )
            continue
        datasets.append({"schema_id": schema_id, "map_items": items})

    if report.errors:
        return report, None
    if not datasets:
        report.warn("no map-item datasets — exporting the drawing alone")

    manifest = info.get("manifest") or {}
    if not isinstance(manifest, dict):
        manifest = {}

    pdf_raw = _pdf_bytes(root, archive) if include_pdf else None
    if pdf_raw is not None:
        try:
            check_pdf_bytes(pdf_raw, f"{PDF_DIR}/{DRAWING_PDF}")
        except ValueError as exc:
            report.error(str(exc))
            return report, None

    extracted = extracted_override
    if extracted is None and include_extracted_data:
        got = info.get("extracted_data")
        if isinstance(got, dict):
            extracted = got

    doc: dict[str, Any] = {"zipmap_json": JSON_FORMAT_VERSION}
    if include_meta:
        for f in META_FIELDS:
            if manifest.get(f):
                doc[f] = manifest[f]
    doc["image"] = {"format": "png", "width": width, "height": height}
    if pdf_raw is not None:
        doc["pdf"] = _pdf_block(info, manifest, from_archive, report)
    if extracted is not None:
        doc["extracted_data"] = extracted
    # the base64 blobs sit last but one: each is a single enormous line, and
    # everything worth reading by eye belongs above them. JSON object order
    # carries no meaning to consumers.
    doc["b64"] = base64.b64encode(raw).decode("ascii")
    if pdf_raw is not None:
        doc["pdf_b64"] = base64.b64encode(pdf_raw).decode("ascii")
    doc["map_item_datasets"] = datasets
    return report, doc


def _pdf_block(
    info: dict[str, Any], manifest: dict[str, Any], from_archive: bool, report: Report
) -> dict[str, Any]:
    """Describe the embedded PDF the way `image` describes the embedded PNG.

    Page size in points comes from pymupdf when the export ran against a
    working folder, and from the manifest when it ran against an archive
    (where pdf/ was deliberately not extracted). `pages` is emitted only when
    something actually established the count: the save gate for an archive,
    pymupdf for a folder. Claiming `"pages": 1` on an unverified PDF would be
    the one lie a receiver cannot cheaply catch.
    """
    block: dict[str, Any] = {"format": "pdf"}
    dims = info.get("pdf")
    verified = isinstance(dims, dict)  # only pdf_info() populates info["pdf"]
    if not verified:
        recorded = manifest.get("pdf")
        dims = recorded if isinstance(recorded, dict) else None
    if isinstance(dims, dict):
        for f in ("width", "height"):
            if isinstance(dims.get(f), (int, float)):
                block[f] = dims[f]
    if verified or from_archive:
        # a .zipmap only exists because save.py proved the PDF single-page
        block["pages"] = 1
    else:
        report.warn(
            f"{PDF_DIR}/{DRAWING_PDF} embedded without pymupdf — page count and page "
            f'size unverified, so "pages" is omitted from the pdf block'
        )
    return block


def write_json(
    target: str | Path,
    output: str | Path | None = None,
    schema_ids: dict[str, str] | None = None,
    validate: bool = True,
    include_meta: bool = True,
    indent: int | None = 2,
    include_pdf: bool = True,
    include_extracted_data: bool = True,
    extracted_data: dict[str, Any] | None = None,
) -> tuple[Report, Path | None]:
    """Export a zipmap and write `<name>.zipmap.json`.

    Returns (report, output_path); output_path is None when nothing was
    written. The default output sits beside the source: a `mymap/` folder
    and a `mymap.zipmap` archive both produce `mymap.zipmap.json`.
    """
    target = Path(target)
    report, doc = to_json(
        target, schema_ids=schema_ids, validate=validate, include_meta=include_meta,
        include_pdf=include_pdf, include_extracted_data=include_extracted_data,
        extracted_data=extracted_data,
    )
    if doc is None:
        return report, None
    if output:
        out = Path(output)
    else:
        stem = target.name[: -len(".zipmap")] if target.name.endswith(".zipmap") else target.name
        out = target.parent / f"{stem}{JSON_SUFFIX}"
    text = json.dumps(doc, indent=indent) if indent else json.dumps(doc, separators=(",", ":"))
    out.write_text(text + "\n", encoding="utf-8")
    return report, out


# --------------------------------------------------------------------------
# reading back


def _check_pdf(doc: dict[str, Any], report: Report, info: dict[str, Any]) -> None:
    """Validate the optional `pdf_b64` payload and its `pdf` descriptor.

    The PDF is the turnover print master, not a coordinate space, so the
    checks stop at "these bytes are a whole PDF": header, `%%EOF`, and a
    declared page count of exactly 1. Page *size* is not cross-checked
    against the bytes — that needs a PDF parser, and nothing in the document
    is measured in points, so a disagreement misplaces nothing.
    """
    b64 = doc.get("pdf_b64")
    declared = doc.get("pdf")

    if b64 is None:
        if declared is not None:
            report.error('"pdf" is declared but "pdf_b64" is absent — nothing to describe')
        return
    if not isinstance(b64, str) or not b64.strip():
        report.error('"pdf_b64", when present, must be a non-empty base64 string')
        return

    clean = b64 if _WS.search(b64) is None else "".join(b64.split())
    try:
        raw = base64.b64decode(clean, validate=True)
    except (binascii.Error, ValueError) as exc:
        report.error(f'"pdf_b64" is not valid base64 ({exc})')
        return
    try:
        check_pdf_bytes(raw, '"pdf_b64"')
    except ValueError as exc:
        report.error(str(exc))
        return
    info["pdf"] = {"bytes": len(raw)}

    if declared is None:
        return
    if not isinstance(declared, dict):
        report.error('"pdf", when present, must be an object')
        return
    fmt = declared.get("format", "pdf")
    if fmt != "pdf":
        report.error(f'pdf.format must be "pdf", got {fmt!r}')
    pages = declared.get("pages")
    if pages is not None and pages != 1:
        report.error(
            f"pdf.pages is {pages!r} — a zipmap carries exactly one drawing, so the "
            f"embedded PDF must be single-page"
        )
    for f in ("width", "height"):
        v = declared.get(f)
        if v is not None and (not isinstance(v, (int, float)) or isinstance(v, bool) or v <= 0):
            report.error(f"pdf.{f} must be a positive number of points, got {v!r}")
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            info["pdf"][f] = v


def _check_extracted_data(doc: dict[str, Any], report: Report, info: dict[str, Any]) -> None:
    """Check the optional `extracted_data` record — object-ness, and no more.

    This is the whole contract. The keys inside belong to the receiving
    system's drawing-extraction schema (bill of materials, line number,
    title-block parameters, whatever that system extracts), which versions
    independently of this format. Validating them here would make every
    schema change a breaking change to the interchange document.
    """
    extracted = doc.get("extracted_data")
    if extracted is None:
        return
    if not isinstance(extracted, dict):
        report.error(
            f'"extracted_data", when present, must be a JSON object (one extraction '
            f"record for the drawing), got {type(extracted).__name__}"
        )
        return
    info["extracted_data"] = extracted


def validate_json_doc(doc: Any, report: Report | None = None) -> tuple[Report, dict[str, Any]]:
    """Check a decoded `.zipmap.json` document against the interchange rules.

    Returns (report, info) where info carries the image dimensions, the
    embedded PDF's size, the extraction record, and the per-schema_id item
    counts for summaries.
    """
    report = report or Report()
    info: dict[str, Any] = {"json": True, "counts": {}}
    if not isinstance(doc, dict):
        report.error("top level must be a JSON object")
        return report, info

    version = doc.get("zipmap_json")
    if version is not None and version not in JSON_FORMAT_VERSIONS:
        report.error(
            f"unsupported zipmap_json version {version!r} "
            f"(this library reads {', '.join(JSON_FORMAT_VERSIONS)})"
        )

    width = height = None
    b64 = doc.get("b64")
    if not isinstance(b64, str) or not b64.strip():
        report.error('"b64" must be a non-empty base64 string')
    else:
        # Line-wrapped base64 from other producers is tolerated, but ours is a
        # single line — so only pay for the whitespace-stripped copy (a full
        # duplicate of a possibly multi-megabyte string) when there is actually
        # whitespace to strip. The decode itself stays: catching a truncated or
        # corrupt payload is the point of this function.
        clean = b64 if _WS.search(b64) is None else "".join(b64.split())
        try:
            raw = base64.b64decode(clean, validate=True)
        except (binascii.Error, ValueError) as exc:
            report.error(f'"b64" is not valid base64 ({exc})')
        else:
            try:
                width, height = png_size_bytes(raw[:26], '"b64"')
            except ValueError as exc:
                report.error(str(exc))
            else:
                info["image"] = {"width": width, "height": height, "bytes": len(raw)}

    declared = doc.get("image")
    if isinstance(declared, dict):
        fmt = declared.get("format", "png")
        if fmt != "png":
            report.error(f'image.format must be "png", got {fmt!r}')
        if width is not None and (declared.get("width"), declared.get("height")) != (width, height):
            report.error(
                f"image {declared.get('width')}x{declared.get('height')} does not match "
                f"the decoded PNG ({width}x{height})"
            )

    _check_pdf(doc, report, info)
    _check_extracted_data(doc, report, info)

    datasets = doc.get("map_item_datasets")
    if not isinstance(datasets, list):
        report.error('"map_item_datasets" must be an array')
        return report, info

    for di, ds in enumerate(datasets):
        label = f"map_item_datasets[{di}]"
        if not isinstance(ds, dict):
            report.error(f"{label}: must be an object")
            continue
        sid = ds.get("schema_id")
        if not isinstance(sid, str) or not sid.strip():
            report.error(f'{label}: "schema_id" is required and must be a non-empty string')
            sid = None
        items = ds.get("map_items")
        if not isinstance(items, list):
            report.error(f'{label}: "map_items" must be an array')
            continue
        if sid:
            label = f"{label} (schema_id={sid})"
            info["counts"][sid] = info["counts"].get(sid, 0) + len(items)
        for i, item in enumerate(items):
            where = f"{label} map_items[{i}]"
            if not isinstance(item, dict):
                report.error(f"{where}: must be an object")
                continue
            if item.get("id") is not None:
                where = f"{where} (id={item['id']})"
            bad = False
            for cf in COORD_FIELDS:
                v = item.get(cf)
                if not isinstance(v, (int, float)) or isinstance(v, bool):
                    report.error(f"{where}: coordinate \"{cf}\" missing or not a number")
                    bad = True
            if bad or width is None:
                continue
            for xf in ("x", "x2"):
                if not (0 <= item[xf] <= width):
                    report.error(f"{where}: {xf}={item[xf]} outside image width 0..{width}")
            for yf in ("y", "y2"):
                if not (0 <= item[yf] <= height):
                    report.error(f"{where}: {yf}={item[yf]} outside image height 0..{height}")
    return report, info


def load_json_doc(path: str | Path) -> tuple[Report, dict[str, Any], dict[str, Any]]:
    """Read and validate a `.zipmap.json` file. Returns (report, doc, info)."""
    path = Path(path)
    report = Report()
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        report.error(f"{path.name}: cannot parse JSON ({exc})")
        return report, {}, {}
    report, info = validate_json_doc(doc, report)
    return report, doc if isinstance(doc, dict) else {}, info


def summarize_json(doc: dict[str, Any], info: dict[str, Any]) -> str:
    """Human-readable summary of a validated `.zipmap.json` document."""
    lines = []
    head = " - ".join(x for x in (doc.get("drawing_number"), doc.get("title")) if x)
    if head:
        rev = doc.get("revision")
        lines.append(head + (f" (rev {rev})" if rev else ""))
    img = info.get("image")
    if img:
        lines.append(f"image: {img['width']}x{img['height']} px ({img['bytes'] / 1024:.1f} KiB png)")
    pdf = info.get("pdf")
    if pdf:
        dims = f"{pdf['width']:g}x{pdf['height']:g} pt " if "width" in pdf and "height" in pdf else ""
        lines.append(f"pdf: {dims}({pdf['bytes'] / 1024:.1f} KiB)")
    extracted = info.get("extracted_data")
    if extracted is not None:
        lines.append(f"extracted data: {_extracted_summary(extracted)}")
    for sid, count in info.get("counts", {}).items():
        lines.append(f"{sid}: {count} item(s)")
    return "\n".join(lines) or "empty document"
