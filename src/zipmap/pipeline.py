"""The zipmap validate/save/open pipeline.

Save is a normalize-and-validate gate, never a plain zip:

1. Enforce single-page PDF (when a PDF is present).
2. Regenerate the img/ layer: render pdf/drawing.pdf -> img/drawing.png at
   the requested DPI, always overwriting. Without a PDF, img/drawing.png
   must already exist. PNG is the only accepted image format.
3. Derive pixel-space data: every pdf/<type>.json regenerates
   img/<type>.json (pdf/ is authoritative; stale img data files whose pdf
   counterpart is gone are deleted).
4. Bounds-check every item against its drawing's bounding box.
5. Schema-check every data file against schemata/<type>.schema.json.
6. Write manifest.json from actual archive contents.
7. Zip to <name>.zipmap.

The optional root-level extracted_data.json rides along untouched: the
format requires it to be a JSON object and requires nothing else of it (see
`load_extracted_data`), because its shape belongs to the receiving system's
drawing-extraction schema, not to this format.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# zipfile is imported inside save/save_template/open_zipmap rather than here:
# it costs ~20 ms to import (it pulls in bz2/lzma/zstd) and the validate,
# render, and export paths never need it.

from . import (
    COORD_FIELDS,
    DEFAULT_DPI,
    DRAWING_PDF,
    DRAWING_PNG,
    EXTRACTED_DATA,
    FORMAT_VERSION,
    FORMAT_VERSIONS,
    IMG_DIR,
    MANIFEST,
    PDF_DIR,
    SCHEMATA_DIR,
    TEMPLATE_SUFFIX,
    ZipmapError,
)
from .imaging import png_size
from .schema import validate_instance
from .transform import convert_data_file

META_FIELDS = ("title", "drawing_number", "revision")
_PT_TOL = 0.51  # tolerance when comparing declared PDF dims to the page rect


class Report:
    """Accumulated errors and warnings from a validation run.

    A plain class rather than a dataclass: importing ``dataclasses`` drags in
    ``shutil`` and ``inspect`` for ~9 ms, on every single CLI invocation.
    """

    __slots__ = ("errors", "warnings", "notes")

    def __init__(self, errors: list[str] | None = None, warnings: list[str] | None = None):
        self.errors = [] if errors is None else errors
        self.warnings = [] if warnings is None else warnings
        self.notes: list[str] = []

    def __repr__(self) -> str:
        return f"Report(errors={self.errors!r}, warnings={self.warnings!r})"

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def note(self, msg: str) -> None:
        """Record something the run did that is neither a problem nor silent."""
        self.notes.append(msg)

    def render(self) -> str:
        lines = list(self.notes)
        lines += [f"ERROR: {e}" for e in self.errors] + [f"warning: {w}" for w in self.warnings]
        lines.append("OK" if self.ok else f"FAILED: {len(self.errors)} error(s)")
        return "\n".join(lines)


def _load_json(path: Path, report: Report, preparsed: dict[str, Any] | None = None) -> Any:
    """Parse a JSON file, or return the already-parsed value for it.

    `preparsed` lets save() hand back the dicts it just derived and wrote,
    instead of this re-reading and re-parsing them off disk.
    """
    if preparsed is not None:
        hit = preparsed.get(str(path))
        if hit is not None:
            return hit
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        report.error(f"{path.name}: cannot parse JSON ({exc})")
        return None


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------
# drawing extraction data


def load_extracted_data(root: str | Path) -> dict[str, Any] | None:
    """Read the drawing extraction record, or None when the map carries none.

    `extracted_data.json` is the drawing's own extracted content — bill of
    materials, line number, revision, tagged items, title-block parameters —
    as opposed to the map items placed *on* the drawing, which live in
    img/<type>.json and are governed by schemata/.

    **The zipmap format imposes no structure on it beyond "a JSON object".**
    Its fields are defined by the receiving system's drawing-extraction
    schema (in QC Database terms, a document folder's extraction schema), and
    those fields evolve independently of this format. Do not validate it
    here, and do not invent keys for it — copy through whatever the extractor
    produced.

    Raises ValueError if the file exists but is not a JSON object.
    """
    path = Path(root) / EXTRACTED_DATA
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"{EXTRACTED_DATA}: cannot parse JSON ({exc})") from exc
    if not isinstance(loaded, dict):
        raise ValueError(
            f"{EXTRACTED_DATA}: must be a JSON object (a single extraction record), "
            f"got {type(loaded).__name__}"
        )
    return loaded


def write_extracted_data(root: str | Path, data: dict[str, Any]) -> Path:
    """Write the drawing extraction record to <root>/extracted_data.json."""
    if not isinstance(data, dict):
        raise ValueError(
            f"{EXTRACTED_DATA} must be a JSON object, got {type(data).__name__}"
        )
    path = Path(root) / EXTRACTED_DATA
    _write_json(path, data)
    return path


#: Members that are already compressed internally. Deflating a PNG or a PDF
#: again costs ~20 ms per MB and returns essentially nothing — an 8 MB drawing
#: spends 158 ms to save 0.00 MB — so those members are stored, and only the
#: JSON (which genuinely compresses) is deflated.
_STORED_SUFFIXES = frozenset({".png", ".pdf"})


def _compression(path: Path) -> int:
    import zipfile

    return zipfile.ZIP_STORED if path.suffix.lower() in _STORED_SUFFIXES else zipfile.ZIP_DEFLATED


def _schema_stems(root: Path) -> dict[str, Path]:
    d = root / SCHEMATA_DIR
    if not d.is_dir():
        return {}
    return {p.name[: -len(".schema.json")]: p for p in sorted(d.glob("*.schema.json"))}


def _data_files(root: Path, sub: str) -> list[Path]:
    d = root / sub
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob("*.json"))


def _validate_data_file(
    path: Path,
    space: str,
    width: float,
    height: float,
    schema: dict | None,
    report: Report,
    preparsed: dict[str, Any] | None = None,
) -> int:
    """Validate one data file (wrapper, bounds, schema). Returns item count.

    `schema=None` runs the wrapper and bounds checks only — used for the
    derived img/ layer of a PDF-backed map, whose items are a coordinate
    transform of pdf/ items that were already schema-checked.
    """
    label = f"{space}/{path.name}"
    data = _load_json(path, report, preparsed)
    if data is None:
        return 0
    if not isinstance(data, dict):
        report.error(f"{label}: top level must be an object")
        return 0

    stem = path.stem
    if data.get("space") != space:
        report.error(f"{label}: \"space\" must be \"{space}\", got {data.get('space')!r}")
    if data.get("schema") != stem:
        report.error(f"{label}: \"schema\" must be \"{stem}\", got {data.get('schema')!r}")
    for dim, expect in (("width", width), ("height", height)):
        got = data.get(dim)
        if not isinstance(got, (int, float)) or isinstance(got, bool):
            report.error(f"{label}: \"{dim}\" must be a number")
        elif abs(got - expect) > (_PT_TOL if space == PDF_DIR else 0):
            report.error(f"{label}: {dim} {got} does not match drawing {dim} {expect}")

    items = data.get("items")
    if not isinstance(items, list):
        report.error(f"{label}: \"items\" must be an array")
        return 0

    for i, item in enumerate(items):
        where = f"{label} item[{i}]"
        if not isinstance(item, dict):
            report.error(f"{where}: must be an object")
            continue
        ident = item.get("id")
        if ident is not None:
            where = f"{label} item[{i}] (id={ident})"
        bad_coords = False
        for cf in COORD_FIELDS:
            v = item.get(cf)
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                report.error(f"{where}: coordinate \"{cf}\" missing or not a number")
                bad_coords = True
        if not bad_coords:
            for xf in ("x", "x2"):
                if not (0 <= item[xf] <= width):
                    report.error(f"{where}: {xf}={item[xf]} outside drawing width 0..{width}")
            for yf in ("y", "y2"):
                if not (0 <= item[yf] <= height):
                    report.error(f"{where}: {yf}={item[yf]} outside drawing height 0..{height}")
        if schema is not None:
            for err in validate_instance(item, schema):
                report.error(f"{where}: schema violation at {err}")
    return len(items)


def validate_folder(
    root: str | Path,
    report: Report | None = None,
    require_manifest: bool = False,
    check_manifest: bool = True,
    pdf_checks: bool = True,
    preparsed: dict[str, Any] | None = None,
) -> tuple[Report, dict[str, Any]]:
    """Run every structural, bounds, and schema check on a working folder.

    Returns (report, info). info holds image/pdf dimensions and per-type
    item counts for summaries and manifest generation.

    `pdf_checks=False` skips opening the PDF (page count, page size, and
    therefore PDF-space bounds) — for callers that consume only the img/
    layer and must work without pymupdf. Every img/ check still runs, as
    does the pdf/img data-file pairing check.

    `preparsed` maps a data file's path (as a string) to its already-parsed
    contents, so save() need not write a derived file and immediately read
    it back.
    """
    root = Path(root)
    report = report or Report()
    info: dict[str, Any] = {"root": root, "counts": {}}

    if not root.is_dir():
        report.error(f"{root} is not a directory")
        return report, info

    # drawing image (mandatory, PNG only)
    png = root / IMG_DIR / DRAWING_PNG
    img_w = img_h = None
    if not png.is_file():
        report.error(f"{IMG_DIR}/{DRAWING_PNG} is missing — a zipmap without an image is invalid")
    else:
        try:
            img_w, img_h = png_size(png)
            info["image"] = {"file": DRAWING_PNG, "width": img_w, "height": img_h}
        except ValueError as exc:
            report.error(str(exc))
    for p in sorted((root / IMG_DIR).glob("*")) if (root / IMG_DIR).is_dir() else []:
        if p.name != DRAWING_PNG and p.suffix != ".json":
            report.warn(f"{IMG_DIR}/{p.name}: unexpected file (PNG drawing and .json data only)")

    # drawing PDF (optional, single canonical file, single page)
    pdf = root / PDF_DIR / DRAWING_PDF
    has_pdf = pdf.is_file()
    pdf_w = pdf_h = None
    if (root / PDF_DIR).is_dir():
        for p in sorted((root / PDF_DIR).glob("*.pdf")):
            if p.name != DRAWING_PDF:
                report.error(f"{PDF_DIR}/{p.name}: the PDF must be named {DRAWING_PDF}")
    if has_pdf and pdf_checks:
        from .pdfio import pdf_info

        try:
            pages, pdf_w, pdf_h = pdf_info(pdf)
            if pages != 1:
                report.error(f"{PDF_DIR}/{DRAWING_PDF} has {pages} pages — PDFs must be single-page")
            info["pdf"] = {"file": DRAWING_PDF, "width": round(pdf_w, 2), "height": round(pdf_h, 2)}
        except ZipmapError as exc:
            report.error(str(exc))
        except Exception as exc:  # corrupt PDF
            report.error(f"{PDF_DIR}/{DRAWING_PDF}: cannot read ({exc})")
    info["source"] = "pdf" if has_pdf else "img"

    # schemas
    schemas: dict[str, dict] = {}
    if not (root / SCHEMATA_DIR).is_dir():
        report.error(f"{SCHEMATA_DIR}/ directory is missing")
    for stem, spath in _schema_stems(root).items():
        loaded = _load_json(spath, report)
        if isinstance(loaded, dict):
            schemas[stem] = loaded
        elif loaded is not None:
            report.error(f"{SCHEMATA_DIR}/{spath.name}: schema must be a JSON object")
    info["types"] = sorted(schemas)

    # drawing extraction record (optional). Presence and JSON-object-ness are
    # all this format checks — the fields inside belong to the receiving
    # system's extraction schema. See load_extracted_data().
    try:
        extracted = load_extracted_data(root)
    except ValueError as exc:
        report.error(str(exc))
    else:
        if extracted is not None:
            info["extracted_data"] = extracted

    # Data files, both spaces. On a PDF-backed map the img/ layer is derived
    # from pdf/ by a pure coordinate transform, so schema-checking both spaces
    # validates the same items twice over. Schema-check the authoritative space
    # only; wrapper and bounds run on both, since their bounds genuinely differ.
    # (This is also the more correct reading: a schema constraining a coordinate
    # range describes the space its author wrote items in, not our transform of it.)
    schema_space = PDF_DIR if (has_pdf and pdf_w is not None and pdf_h is not None) else IMG_DIR
    used_schemas: set[str] = set()
    for space, w, h in ((PDF_DIR, pdf_w, pdf_h), (IMG_DIR, img_w, img_h)):
        for dpath in _data_files(root, space):
            stem = dpath.stem
            schema = schemas.get(stem)
            if schema is None:
                report.error(
                    f"{space}/{dpath.name}: no matching schema "
                    f"({SCHEMATA_DIR}/{stem}.schema.json not found)"
                )
            used_schemas.add(stem)
            if space == PDF_DIR and not has_pdf:
                report.error(f"{space}/{dpath.name}: PDF-space data present but no {DRAWING_PDF}")
                continue
            if w is None or h is None:
                continue  # drawing itself already failed; skip bounds
            count = _validate_data_file(
                dpath, space, w, h,
                schema if space == schema_space else None,
                report, preparsed,
            )
            if space == IMG_DIR:
                info["counts"][stem] = count
    for stem in schemas:
        if stem not in used_schemas:
            report.warn(f"{SCHEMATA_DIR}/{stem}.schema.json has no data file using it")

    # data-file pairing on PDF-backed maps: img/ must mirror pdf/
    if has_pdf:
        pdf_stems = {p.stem for p in _data_files(root, PDF_DIR)}
        img_stems = {p.stem for p in _data_files(root, IMG_DIR)}
        for stem in sorted(pdf_stems - img_stems):
            report.error(f"{IMG_DIR}/{stem}.json missing — run save to regenerate the img layer")
        for stem in sorted(img_stems - pdf_stems):
            report.error(
                f"{IMG_DIR}/{stem}.json has no {PDF_DIR}/ counterpart — on a PDF-backed "
                f"zipmap pdf/ is authoritative; run save to regenerate the img layer"
            )

    # manifest (check_manifest=False during save: it is about to be regenerated,
    # so a stale one is loaded for its meta fields but not validated)
    mpath = root / MANIFEST
    if mpath.is_file():
        if check_manifest:
            manifest = _load_json(mpath, report)
        else:
            try:
                manifest = json.loads(mpath.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                manifest = None
        if isinstance(manifest, dict):
            info["manifest"] = manifest
            if check_manifest:
                _check_manifest(manifest, info, report, strict=require_manifest)
    elif require_manifest:
        report.error(f"{MANIFEST} is missing")

    return report, info


def _check_manifest(manifest: dict, info: dict, report: Report, strict: bool) -> None:
    """Cross-check a manifest against archive contents.

    A working folder may hold a seeded pre-save manifest carrying only meta
    fields, so derived fields are checked only when present; strict mode
    (opened archives) additionally requires them to exist.
    """
    version = manifest.get("zipmap")
    if version not in FORMAT_VERSIONS:
        report.error(
            f"{MANIFEST}: unsupported format version {version!r} "
            f"(this library reads {', '.join(FORMAT_VERSIONS)})"
        )
    if strict:
        for key in ("created", "source", "image", "types"):
            if key not in manifest:
                report.error(f"{MANIFEST}: missing required field {key!r}")
    img = manifest.get("image")
    have = info.get("image")
    if have and isinstance(img, dict):
        if (img.get("width"), img.get("height")) != (have["width"], have["height"]):
            report.error(
                f"{MANIFEST}: image dimensions {img.get('width')}x{img.get('height')} "
                f"do not match {DRAWING_PNG} ({have['width']}x{have['height']})"
            )
    declared = manifest.get("types")
    if isinstance(declared, list) and sorted(declared) != info.get("types", []):
        report.error(
            f"{MANIFEST}: types {sorted(declared)} do not match schemata/ {info.get('types')}"
        )
    if "source" in manifest and manifest["source"] != info.get("source"):
        report.error(
            f"{MANIFEST}: source {manifest['source']!r} does not match archive "
            f"contents ({info.get('source')!r})"
        )
    if "extracted_data" in manifest and bool(manifest["extracted_data"]) != (
        "extracted_data" in info
    ):
        report.error(
            f"{MANIFEST}: extracted_data {manifest['extracted_data']!r} does not match "
            f"archive contents ({EXTRACTED_DATA} is "
            f"{'present' if 'extracted_data' in info else 'absent'})"
        )


def _sha256_file(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_manifest(root: Path) -> dict:
    """Best-effort read of an existing manifest; {} if absent or unreadable."""
    try:
        loaded = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _reusable_render(root: Path, pdf_sha: str, dpi: int) -> tuple[int, int] | None:
    """Dimensions of an existing PNG that this exact PDF+DPI already produced.

    Keyed on the PDF's content hash, not its mtime, so it cannot go stale when
    a file is copied, restored, or touched. Returns None whenever anything is
    unproven — the caller then renders normally.
    """
    png = root / IMG_DIR / DRAWING_PNG
    if not png.is_file():
        return None
    manifest = _read_manifest(root)
    if manifest.get("render_dpi") != dpi:
        return None
    recorded = manifest.get("pdf")
    if not isinstance(recorded, dict) or recorded.get("sha256") != pdf_sha:
        return None
    try:
        return png_size(png)
    except ValueError:
        return None


def _build_manifest(
    info: dict, dpi: int | None, existing: dict, meta: dict | None, pdf_sha: str | None = None
) -> dict:
    manifest: dict[str, Any] = {"zipmap": FORMAT_VERSION}
    meta = meta or {}
    for f in META_FIELDS:
        value = meta.get(f, existing.get(f))
        if value:
            manifest[f] = value
    manifest["created"] = existing.get("created") or (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    manifest["source"] = info["source"]
    if info["source"] == "pdf":
        manifest["render_dpi"] = dpi
        # copied, not aliased: info["pdf"] must not gain a field from this
        manifest["pdf"] = {**info["pdf"], "sha256": pdf_sha} if pdf_sha else info["pdf"]
    manifest["image"] = info["image"]
    manifest["types"] = info["types"]
    # a presence flag only: the record itself stays in extracted_data.json, so
    # a reader can decide whether to fetch it without parsing a BOM it may not want
    if "extracted_data" in info:
        manifest["extracted_data"] = True
    return manifest


def save(
    root: str | Path,
    output: str | Path | None = None,
    dpi: int = DEFAULT_DPI,
    meta: dict | None = None,
    reuse_render: bool = False,
) -> tuple[Report, Path | None]:
    """Run the full save pipeline on a working folder; write <name>.zipmap.

    Returns (report, output_path). output_path is None when validation
    failed and nothing was written.

    `reuse_render=True` skips the PDF->PNG rasterization when the PDF's
    content hash and the requested DPI both match what the existing manifest
    records and img/drawing.png is present — for the edit-save-edit loop where
    only the item data changes. Off by default: a plain save always
    regenerates the img/ layer, as the format spec promises.
    """
    root = Path(root)
    report = Report()
    preparsed: dict[str, Any] = {}
    pdf_sha: str | None = None
    if not root.is_dir():
        report.error(f"{root} is not a directory")
        return report, None

    pdf = root / PDF_DIR / DRAWING_PDF
    if pdf.is_file():
        from .pdfio import pdf_info, render_png

        try:
            pages, _pw, pdf_h = pdf_info(pdf)
        except ZipmapError as exc:
            report.error(str(exc))
            return report, None
        except Exception as exc:
            report.error(f"{PDF_DIR}/{DRAWING_PDF}: cannot read ({exc})")
            return report, None
        if pages != 1:
            report.error(f"{PDF_DIR}/{DRAWING_PDF} has {pages} pages — PDFs must be single-page")
            return report, None

        # recorded in the manifest on every save, so a later --reuse-render has
        # something to compare against
        pdf_sha = _sha256_file(pdf)
        reused = _reusable_render(root, pdf_sha, dpi) if reuse_render else None
        if reused is not None:
            img_w, img_h = reused
            report.note(f"reused existing render ({DRAWING_PDF} unchanged, {dpi} dpi)")
        else:
            img_w, img_h = render_png(pdf, root / IMG_DIR / DRAWING_PNG, dpi)

        # pdf/ is authoritative: rebuild every img data file, drop strays
        pdf_stems = {p.stem for p in _data_files(root, PDF_DIR)}
        for stale in _data_files(root, IMG_DIR):
            if stale.stem not in pdf_stems:
                stale.unlink()
        for dpath in _data_files(root, PDF_DIR):
            data = _load_json(dpath, report)
            if not isinstance(data, dict) or not isinstance(data.get("items"), list):
                report.error(f"{PDF_DIR}/{dpath.name}: not a valid data file; cannot derive img data")
                continue
            derived = convert_data_file(data, pdf_h, dpi, img_w, img_h)
            target = root / IMG_DIR / dpath.name
            _write_json(target, derived)
            # hand both layers to validate_folder so it need not read back
            # what we just parsed (pdf/) and wrote (img/)
            preparsed[str(dpath)] = data
            preparsed[str(target)] = derived
    else:
        if not (root / IMG_DIR / DRAWING_PNG).is_file():
            report.error(
                f"no {PDF_DIR}/{DRAWING_PDF} and no {IMG_DIR}/{DRAWING_PNG} — "
                "a zipmap without an image is invalid"
            )
            return report, None
        dpi = None  # type: ignore[assignment]

    report, info = validate_folder(
        root, report=report, require_manifest=False, check_manifest=False, preparsed=preparsed
    )
    if not report.ok:
        return report, None

    existing = info.get("manifest", {})
    manifest = _build_manifest(
        info, dpi, existing if isinstance(existing, dict) else {}, meta, pdf_sha
    )
    _write_json(root / MANIFEST, manifest)

    output = Path(output) if output else root.parent / f"{root.name}.zipmap"
    import zipfile

    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(root / MANIFEST, MANIFEST)
        if (root / EXTRACTED_DATA).is_file():
            zf.write(root / EXTRACTED_DATA, EXTRACTED_DATA)
        for sub in (SCHEMATA_DIR, PDF_DIR, IMG_DIR):
            d = root / sub
            if d.is_dir():
                for p in sorted(d.rglob("*")):
                    if p.is_file():
                        zf.write(p, f"{sub}/{p.relative_to(d).as_posix()}",
                                 compress_type=_compression(p))
    return report, output


def validate_template_folder(
    root: str | Path, report: Report | None = None
) -> tuple[Report, dict[str, Any]]:
    """Validate a template working folder: schemata only, no drawing required."""
    root = Path(root)
    report = report or Report()
    info: dict[str, Any] = {"root": root, "template": True}
    if not root.is_dir():
        report.error(f"{root} is not a directory")
        return report, info
    if not (root / SCHEMATA_DIR).is_dir():
        report.error(f"{SCHEMATA_DIR}/ directory is missing")
        return report, info
    schemas: dict[str, dict] = {}
    stems = _schema_stems(root)
    if not stems:
        report.error(f"template has no *.schema.json files in {SCHEMATA_DIR}/")
    for stem, spath in stems.items():
        loaded = _load_json(spath, report)
        if isinstance(loaded, dict):
            schemas[stem] = loaded
        elif loaded is not None:
            report.error(f"{SCHEMATA_DIR}/{spath.name}: schema must be a JSON object")
    info["types"] = sorted(schemas)
    for sub in (PDF_DIR, IMG_DIR):
        d = root / sub
        if d.is_dir() and any(p.is_file() for p in d.rglob("*")):
            report.warn(
                f"{sub}/ contains files — a template carries schemata only; "
                f"they will not be packed into a .zipmapt"
            )
    if (root / EXTRACTED_DATA).is_file():
        report.warn(
            f"{EXTRACTED_DATA} is present — an extraction record describes one "
            f"specific drawing, so it will not be packed into a .zipmapt"
        )
    return report, info


def save_template(
    root: str | Path, output: str | Path | None = None
) -> tuple[Report, Path | None]:
    """Pack a working folder's schemata/ into a <name>.zipmapt template."""
    root = Path(root)
    report, _info = validate_template_folder(root)
    if not report.ok:
        return report, None
    output = Path(output) if output else root.parent / f"{root.name}{TEMPLATE_SUFFIX}"
    import zipfile

    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        for _stem, spath in _schema_stems(root).items():
            zf.write(spath, f"{SCHEMATA_DIR}/{spath.name}")
    return report, output


def open_zipmap(
    path: str | Path, dest: str | Path | None = None, validate: bool = True
) -> tuple[Report, Path, dict[str, Any]]:
    """Extract a .zipmap or .zipmapt to a working folder (safely) and validate it.

    Templates additionally get empty pdf/ and img/ dirs created, so the
    extraction is immediately usable as the starting point of a real zipmap.
    """
    import zipfile

    path = Path(path)
    is_template = path.suffix.lower() == TEMPLATE_SUFFIX
    dest = Path(dest) if dest else path.parent / path.stem
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as zf:
        base = dest.resolve()
        for member in zf.infolist():
            target = (dest / member.filename).resolve()
            if not target.is_relative_to(base):
                raise ZipmapError(f"unsafe path in archive: {member.filename}")
        zf.extractall(dest)
    if is_template:
        for sub in (PDF_DIR, IMG_DIR):
            (dest / sub).mkdir(exist_ok=True)
    report = Report()
    info: dict[str, Any] = {}
    if validate:
        if is_template:
            report, info = validate_template_folder(dest)
        else:
            report, info = validate_folder(dest, require_manifest=True)
    return report, dest, info


def summarize(info: dict[str, Any]) -> str:
    """Human-readable one-screen summary of a validated zipmap or template."""
    if info.get("template"):
        types = ", ".join(info.get("types", [])) or "none"
        return f"zipmap template (schemata only)\ntypes: {types}"
    lines = []
    manifest = info.get("manifest", {})
    title = manifest.get("title")
    number = manifest.get("drawing_number")
    rev = manifest.get("revision")
    head = " - ".join(x for x in (number, title) if x)
    if head:
        lines.append(head + (f" (rev {rev})" if rev else ""))
    img = info.get("image")
    if img:
        lines.append(f"image: {img['width']}x{img['height']} px")
    pdf = info.get("pdf")
    if pdf:
        dpi = manifest.get("render_dpi")
        lines.append(
            f"pdf: {pdf['width']}x{pdf['height']} pt" + (f" (rendered at {dpi} dpi)" if dpi else "")
        )
    lines.append(f"source: {info.get('source')}")
    counts = info.get("counts", {})
    for stem in info.get("types", []):
        lines.append(f"{stem}: {counts.get(stem, 0)} item(s)")
    extracted = info.get("extracted_data")
    if extracted is not None:
        lines.append(f"extracted data: {_extracted_summary(extracted)}")
    return "\n".join(lines)


def _extracted_summary(extracted: dict[str, Any]) -> str:
    """One-line shape summary of an opaque extraction record.

    Names the top-level keys and sizes the arrays (a bill of materials is
    almost always the largest of them) without asserting anything about what
    those keys mean — the format does not define them.
    """
    if not extracted:
        return "empty object"
    lists = [f"{k}[{len(v)}]" for k, v in extracted.items() if isinstance(v, list)]
    scalars = [k for k, v in extracted.items() if not isinstance(v, list)]
    parts = lists + scalars
    shown = ", ".join(parts[:8]) + (f", +{len(parts) - 8} more" if len(parts) > 8 else "")
    return f"{len(extracted)} field(s) — {shown}"
