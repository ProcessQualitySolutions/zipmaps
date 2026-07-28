"""zipmap — transportable weld/flange/heat map archives.

A .zipmap is a plain zip archive:

    manifest.json           required, written by the save pipeline
    extracted_data.json     optional drawing extraction record (BOM, params)
    schemata/*.schema.json  JSON Schema per map-item type
    pdf/drawing.pdf         optional single-page PDF + PDF-space data files
    pdf/<type>.json
    img/drawing.png         required PNG + pixel-space data files
    img/<type>.json

A .zipmap.json is the same map flattened into one API-friendly JSON object
(base64 PNG, base64 single-page PDF, the extraction record, and pixel-space
items keyed by server-side schema id) — see jsonpack.py.

The library is pure stdlib except for PDF handling, which lazily imports
pymupdf. Image-only zipmaps need no third-party packages at all.
"""

from __future__ import annotations

FORMAT_VERSION = "1.1"
#: Archive format versions this library reads. 1.1 added the optional
#: root-level extracted_data.json; a 1.0 archive is still perfectly valid.
FORMAT_VERSIONS = ("1.0", "1.1")
DRAWING_PDF = "drawing.pdf"
DRAWING_PNG = "drawing.png"
EXTRACTED_DATA = "extracted_data.json"
SCHEMATA_DIR = "schemata"
PDF_DIR = "pdf"
IMG_DIR = "img"
MANIFEST = "manifest.json"
DEFAULT_DPI = 300
COORD_FIELDS = ("x", "y", "x2", "y2")
TEMPLATE_SUFFIX = ".zipmapt"
JSON_SUFFIX = ".zipmap.json"
JSON_FORMAT_VERSION = "1.1"
#: Interchange versions this library reads. 1.1 added the optional pdf_b64,
#: pdf, and extracted_data fields — all additive, so a 1.0 document is read
#: unchanged.
JSON_FORMAT_VERSIONS = ("1.0", "1.1")


class ZipmapError(Exception):
    """Fatal error working with a zipmap."""


from .pipeline import (  # noqa: E402
    Report,
    load_extracted_data,
    open_zipmap,
    save,
    save_template,
    summarize,
    validate_folder,
    validate_template_folder,
    write_extracted_data,
)
from .transform import convert_data_file, scale_for_dpi  # noqa: E402
from .jsonpack import (  # noqa: E402
    bind_schema_id,
    load_json_doc,
    schema_id_of,
    summarize_json,
    to_json,
    validate_json_doc,
    write_json,
)

__all__ = [
    "FORMAT_VERSION",
    "FORMAT_VERSIONS",
    "DRAWING_PDF",
    "DRAWING_PNG",
    "EXTRACTED_DATA",
    "SCHEMATA_DIR",
    "PDF_DIR",
    "IMG_DIR",
    "MANIFEST",
    "DEFAULT_DPI",
    "COORD_FIELDS",
    "TEMPLATE_SUFFIX",
    "JSON_SUFFIX",
    "JSON_FORMAT_VERSION",
    "JSON_FORMAT_VERSIONS",
    "ZipmapError",
    "Report",
    "save",
    "save_template",
    "open_zipmap",
    "validate_folder",
    "validate_template_folder",
    "summarize",
    "load_extracted_data",
    "write_extracted_data",
    "convert_data_file",
    "scale_for_dpi",
    "to_json",
    "write_json",
    "load_json_doc",
    "validate_json_doc",
    "summarize_json",
    "schema_id_of",
    "bind_schema_id",
]
