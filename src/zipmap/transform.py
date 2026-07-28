"""PDF-space <-> pixel-space coordinate conversion.

PDF space: points (1/72 in), origin bottom-left, y increases upward.
Image space: pixels, origin top-left, y increases downward.

scale = dpi / 72 (pixels per point)
x_px = x_pt * scale
y_px = (pdf_height_pt - y_pt) * scale
"""

from __future__ import annotations

from typing import Any

from . import COORD_FIELDS


def scale_for_dpi(dpi: float) -> float:
    return dpi / 72.0


def pdf_point_to_px(x: float, y: float, pdf_height_pt: float, scale: float) -> tuple[float, float]:
    return round(x * scale, 2), round((pdf_height_pt - y) * scale, 2)


def px_point_to_pdf(x: float, y: float, pdf_height_pt: float, scale: float) -> tuple[float, float]:
    return round(x / scale, 2), round(pdf_height_pt - (y / scale), 2)


def convert_data_file(
    data: dict[str, Any],
    pdf_height_pt: float,
    dpi: float,
    img_width: int,
    img_height: int,
) -> dict[str, Any]:
    """Convert a PDF-space data file dict to its pixel-space equivalent.

    Non-coordinate item fields are copied through untouched. The input dict
    is not modified.
    """
    scale = scale_for_dpi(dpi)
    out = dict(data)
    out["space"] = "img"
    out["width"] = img_width
    out["height"] = img_height
    items = []
    for item in data.get("items", []):
        new = dict(item)
        for xf, yf in (("x", "y"), ("x2", "y2")):
            if xf in item and yf in item:
                new[xf], new[yf] = pdf_point_to_px(item[xf], item[yf], pdf_height_pt, scale)
        items.append(new)
    out["items"] = items
    return out
