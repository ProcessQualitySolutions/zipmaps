"""PDF page inspection and rendering via pymupdf (lazy import).

pymupdf is only needed for PDF-backed zipmaps; image-only zipmaps never
touch this module — except for `check_pdf_bytes`, which is deliberately
stdlib-only so a receiver (or a machine without pymupdf) can sanity-check
an embedded `pdf_b64` payload before handing it to a real PDF library.
"""

from __future__ import annotations

from pathlib import Path

from . import ZipmapError

PDF_MAGIC = b"%PDF-"
#: How far back from the end of the file to look for the %%EOF marker. The
#: spec says it is the last line, but writers append newlines, and some
#: append a small amount of trailing junk; 2 KiB is the usual tolerance.
_EOF_WINDOW = 2048


def check_pdf_bytes(data: bytes, label: str = "data") -> None:
    """Cheap, dependency-free sanity check on in-memory PDF bytes.

    Verifies the `%PDF-` header and that a `%%EOF` marker sits near the end
    — the standard tell for a payload truncated in transit. It does *not*
    parse the file, count pages, or prove the PDF renders; those need a real
    PDF library (`pdf_info`). Raises ValueError describing the failure.
    """
    if len(data) < len(PDF_MAGIC) + 1 or not data.startswith(PDF_MAGIC):
        raise ValueError(f"{label} is not a PDF file (no %PDF- header)")
    if b"%%EOF" not in data[-_EOF_WINDOW:]:
        raise ValueError(f"{label} has no %%EOF marker near the end — truncated PDF?")


def _fitz():
    try:
        import fitz  # type: ignore  # pymupdf
    except ImportError as exc:
        raise ZipmapError(
            "pymupdf is required to work with PDF-backed zipmaps: pip install pymupdf"
        ) from exc
    return fitz


def have_pymupdf() -> bool:
    """True when PDF inspection/rendering is available in this environment."""
    try:
        _fitz()
    except ZipmapError:
        return False
    return True


def pdf_info(path: str | Path) -> tuple[int, float, float]:
    """Return (page_count, width_pt, height_pt) of the first page.

    Dimensions come from page.rect — the page as displayed (CropBox with
    rotation applied) — which is also the box pymupdf renders, so PDF-space
    data coordinates and the rendered PNG always agree.
    """
    fitz = _fitz()
    with fitz.open(str(path)) as doc:
        page = doc[0]
        return doc.page_count, float(page.rect.width), float(page.rect.height)


def render_png(pdf_path: str | Path, png_path: str | Path, dpi: int) -> tuple[int, int]:
    """Render page 1 of pdf_path to png_path at dpi; return (width_px, height_px)."""
    fitz = _fitz()
    png_path = Path(png_path)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    with fitz.open(str(pdf_path)) as doc:
        pix = doc[0].get_pixmap(dpi=dpi, alpha=False)
        pix.save(str(png_path))
        # the pixmap already knows its size; re-reading the file we just wrote
        # only to parse its IHDR back out would be a wasted round trip
        return pix.width, pix.height
