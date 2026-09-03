from __future__ import annotations

import os
import struct
import tempfile
import zlib
from pathlib import Path
from typing import Iterable

from .errors import FormatError, InspectError


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _chunk(kind: bytes, payload: bytes) -> bytes:
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))


def encode_indexed_png(
    width: int,
    height: int,
    pixels: bytes,
    palette: Iterable[tuple[int, int, int]],
    *,
    transparent_index: int | None = None,
    scale: int = 1,
) -> bytes:
    colors = tuple(palette)
    if width <= 0 or height <= 0:
        raise FormatError("PNG dimensions must be positive")
    if len(pixels) != width * height:
        raise FormatError(
            f"indexed image has {len(pixels)} pixels; expected {width * height}"
        )
    if not 1 <= len(colors) <= 256:
        raise FormatError("indexed PNG palette must contain 1 through 256 colors")
    if any(len(color) != 3 or any(not 0 <= channel <= 255 for channel in color) for color in colors):
        raise FormatError("indexed PNG palette contains an invalid RGB color")
    if not 1 <= scale <= 32:
        raise FormatError("PNG scale must be from 1 through 32")
    if transparent_index is not None and not 0 <= transparent_index < len(colors):
        raise FormatError("transparent palette index is out of range")

    scaled_width = width * scale
    scaled_height = height * scale
    scanlines = bytearray()
    for y in range(height):
        source = pixels[y * width : (y + 1) * width]
        expanded = bytes(value for value in source for _ in range(scale))
        row = b"\0" + expanded
        for _ in range(scale):
            scanlines.extend(row)

    header = struct.pack(">IIBBBBB", scaled_width, scaled_height, 8, 3, 0, 0, 0)
    palette_bytes = bytes(channel for color in colors for channel in color)
    chunks = [_chunk(b"IHDR", header), _chunk(b"PLTE", palette_bytes)]
    if transparent_index is not None:
        alpha = bytearray(b"\xff" * (transparent_index + 1))
        alpha[transparent_index] = 0
        chunks.append(_chunk(b"tRNS", bytes(alpha)))
    chunks.extend(
        [
            _chunk(b"tEXt", b"Software\0capplus-inspect"),
            _chunk(b"IDAT", zlib.compress(bytes(scanlines), level=9)),
            _chunk(b"IEND", b""),
        ]
    )
    return PNG_SIGNATURE + b"".join(chunks)


def write_new_file(path: Path, data: bytes, *, force: bool = False) -> None:
    path = path.resolve()
    if path.exists() and not force:
        raise InspectError(f"output already exists: {path}; use --force to replace it")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
            if hasattr(os, "fchmod"):
                os.fchmod(stream.fileno(), 0o644)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_indexed_png(
    path: Path,
    width: int,
    height: int,
    pixels: bytes,
    palette: Iterable[tuple[int, int, int]],
    *,
    transparent_index: int | None = None,
    scale: int = 1,
    force: bool = False,
) -> None:
    write_new_file(
        path,
        encode_indexed_png(
            width,
            height,
            pixels,
            palette,
            transparent_index=transparent_index,
            scale=scale,
        ),
        force=force,
    )
