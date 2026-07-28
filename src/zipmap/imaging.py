"""PNG helpers with no third-party dependencies.

Reads PNG dimensions straight from the IHDR chunk and can write a simple
placeholder "drawing" PNG for demos/tests, so image-only zipmaps never need
Pillow.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

PNG_SIG = b"\x89PNG\r\n\x1a\n"


def png_size_bytes(data: bytes, label: str = "data") -> tuple[int, int]:
    """Return (width, height) of in-memory PNG bytes by reading the IHDR chunk."""
    if len(data) < 26 or data[:8] != PNG_SIG or data[12:16] != b"IHDR":
        raise ValueError(f"{label} is not a valid PNG file")
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def png_size(path: str | Path) -> tuple[int, int]:
    """Return (width, height) of a PNG file by reading its IHDR chunk."""
    with open(path, "rb") as f:
        header = f.read(26)
    return png_size_bytes(header, str(path))


class Canvas:
    """Minimal RGB raster for generating placeholder drawings."""

    def __init__(self, width: int, height: int, bg: tuple[int, int, int] = (250, 250, 248)):
        self.width = width
        self.height = height
        self.px = bytearray(bg * (width * height))

    def rect(self, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
        x0, x1 = max(0, min(x0, x1)), min(self.width, max(x0, x1))
        y0, y1 = max(0, min(y0, y1)), min(self.height, max(y0, y1))
        row = bytes(color) * (x1 - x0)
        for y in range(y0, y1):
            start = (y * self.width + x0) * 3
            self.px[start : start + len(row)] = row

    def hline(self, x0: int, x1: int, y: int, thickness: int = 2, color=(40, 40, 40)) -> None:
        self.rect(x0, y, x1, y + thickness, color)

    def vline(self, x: int, y0: int, y1: int, thickness: int = 2, color=(40, 40, 40)) -> None:
        self.rect(x, y0, x + thickness, y1, color)

    def frame(self, x0: int, y0: int, x1: int, y1: int, thickness: int = 2, color=(40, 40, 40)) -> None:
        self.hline(x0, x1, y0, thickness, color)
        self.hline(x0, x1, y1 - thickness, thickness, color)
        self.vline(x0, y0, y1, thickness, color)
        self.vline(x1 - thickness, y0, y1, thickness, color)

    def write(self, path: str | Path) -> None:
        raw = b"".join(
            b"\x00" + bytes(self.px[y * self.width * 3 : (y + 1) * self.width * 3])
            for y in range(self.height)
        )

        def chunk(ctype: bytes, data: bytes) -> bytes:
            return (
                struct.pack(">I", len(data))
                + ctype
                + data
                + struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF)
            )

        ihdr = struct.pack(">IIBBBBB", self.width, self.height, 8, 2, 0, 0, 0)
        Path(path).write_bytes(
            PNG_SIG
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 6))
            + chunk(b"IEND", b"")
        )


def make_demo_drawing(path: str | Path, width: int = 800, height: int = 600) -> tuple[int, int]:
    """Write a placeholder piping-drawing PNG: border, title block, and a pipe run."""
    c = Canvas(width, height)
    c.frame(10, 10, width - 10, height - 10, 3)
    # title block, bottom-right
    c.frame(width - 260, height - 70, width - 10, height - 10, 2)
    c.hline(width - 260, width - 10, height - 40, 1)
    # horizontal pipe run (two parallel lines)
    y = height // 2
    c.hline(60, width - 120, y - 8, 3)
    c.hline(60, width - 120, y + 8, 3)
    # vertical branch off the run
    x = width // 3
    c.vline(x - 8, 90, y - 8, 3)
    c.vline(x + 8, 90, y - 8, 3)
    c.hline(x - 8, x + 8, 90, 3)
    # end caps
    c.vline(60, y - 14, y + 17, 3)
    c.vline(width - 120, y - 14, y + 17, 3)
    c.write(path)
    return width, height
