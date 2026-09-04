from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION
from .errors import FormatError, InspectError
from .png_writer import write_indexed_png, write_new_file
from .util import sha256_bytes, u16


FONT_HEADER_SIZE = 88
MAX_GLYPHS = 1024


def _font_layout(data: bytes) -> tuple[int, int, int, int, tuple[int, ...], int]:
    if len(data) < FONT_HEADER_SIZE:
        raise FormatError("font is shorter than its 88-byte header")

    first_code = u16(data, 0x24)
    last_code = u16(data, 0x26)
    row_stride = u16(data, 0x50)
    height = u16(data, 0x52)
    if last_code < first_code:
        raise FormatError("font character range is reversed", offset=0x24)
    if last_code > 255:
        raise FormatError("font character codes exceed the original 8-bit range", offset=0x26)
    glyph_count = last_code - first_code + 1
    if glyph_count == 0 or glyph_count > MAX_GLYPHS:
        raise FormatError("font glyph count is outside the supported range", offset=0x24)
    if row_stride == 0 or height == 0:
        raise FormatError("font bitmap dimensions must be non-zero", offset=0x50)

    boundary_offset = FONT_HEADER_SIZE
    bitmap_offset = boundary_offset + (glyph_count + 1) * 2
    expected_size = bitmap_offset + row_stride * height
    if len(data) != expected_size:
        raise FormatError(
            f"font has {len(data)} bytes; header and bitmap declare {expected_size}"
        )

    boundaries = tuple(u16(data, boundary_offset + index * 2) for index in range(glyph_count + 1))
    if boundaries[0] != 0:
        raise FormatError("font boundary table must begin at bit zero", offset=boundary_offset)
    if any(left > right for left, right in zip(boundaries, boundaries[1:])):
        raise FormatError("font boundary table is not monotonic", offset=boundary_offset)
    if boundaries[-1] > row_stride * 8:
        raise FormatError("font boundary table exceeds bitmap row stride", offset=boundary_offset)
    return first_code, last_code, row_stride, height, boundaries, bitmap_offset


def decode_font(data: bytes) -> dict[str, Any]:
    """Decode the original MSB-first, one-bit horizontal font sheet."""

    first_code, last_code, row_stride, height, boundaries, bitmap_offset = _font_layout(data)
    bitmap = data[bitmap_offset:]
    sheet_width = row_stride * 8
    sheet_pixels = bytearray(sheet_width * height)
    for y in range(height):
        row = bitmap[y * row_stride : (y + 1) * row_stride]
        for x in range(sheet_width):
            sheet_pixels[y * sheet_width + x] = (row[x // 8] >> (7 - (x % 8))) & 1

    glyphs: list[dict[str, Any]] = []
    for index, code in enumerate(range(first_code, last_code + 1)):
        left, right = boundaries[index], boundaries[index + 1]
        width = right - left
        pixels = bytes(
            sheet_pixels[y * sheet_width + x]
            for y in range(height)
            for x in range(left, right)
        )
        glyphs.append(
            {
                "index": index,
                "code": code,
                "character": bytes((code,)).decode("cp437") if code >= 32 else None,
                "left_bit": left,
                "right_bit": right,
                "width": width,
                "height": height,
                "ink_pixels": sum(pixels),
                "pixel_sha256": sha256_bytes(pixels),
                "pixels": pixels,
            }
        )

    return {
        "first_code": first_code,
        "last_code": last_code,
        "glyph_count": len(glyphs),
        "row_stride": row_stride,
        "height": height,
        "sheet_width": sheet_width,
        "used_width": boundaries[-1],
        "boundaries": list(boundaries),
        "bitmap_offset": bitmap_offset,
        "bitmap_size": len(bitmap),
        "bitmap_sha256": sha256_bytes(bitmap),
        "sheet_pixels": bytes(sheet_pixels),
        "glyphs": glyphs,
    }


def inspect_font(data: bytes) -> dict[str, Any]:
    decoded = decode_font(data)
    glyphs = [
        {key: value for key, value in glyph.items() if key != "pixels"}
        for glyph in decoded["glyphs"]
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "format": "capitalism_plus_bitmap_font",
        "size": len(data),
        "sha256": sha256_bytes(data),
        "header_size": FONT_HEADER_SIZE,
        "header_sha256": sha256_bytes(data[:FONT_HEADER_SIZE]),
        **{
            key: value
            for key, value in decoded.items()
            if key not in {"sheet_pixels", "glyphs"}
        },
        "bit_order": "most_significant_bit_first",
        "glyphs": glyphs,
    }


def export_font(
    data: bytes,
    output_directory: Path,
    *,
    source_name: str,
    scale: int = 4,
    force: bool = False,
) -> dict[str, Any]:
    decoded = decode_font(data)
    output_directory = output_directory.resolve()
    image_path = output_directory / "font-atlas.png"
    manifest_path = output_directory / "manifest.json"
    conflicts = [path for path in (image_path, manifest_path) if path.exists()]
    if conflicts and not force:
        raise InspectError(
            f"{len(conflicts)} output file(s) already exist in {output_directory}; "
            "use --force to replace them"
        )

    output_directory.mkdir(parents=True, exist_ok=True)
    width = decoded["used_width"] or decoded["sheet_width"]
    pixels = bytearray(width * decoded["height"])
    sheet = decoded["sheet_pixels"]
    for y in range(decoded["height"]):
        start = y * decoded["sheet_width"]
        pixels[y * width : (y + 1) * width] = sheet[start : start + width]
    write_indexed_png(
        image_path,
        width,
        decoded["height"],
        bytes(pixels),
        ((255, 255, 255), (0, 0, 0)),
        scale=scale,
        force=force,
    )

    result = inspect_font(data)
    result.update(
        {
            "format": "capitalism_plus_font_export",
            "source": source_name,
            "scale": scale,
            "output_directory": str(output_directory),
            "atlas": str(image_path),
        }
    )
    manifest = (
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")
        + b"\n"
    )
    write_new_file(manifest_path, manifest, force=force)
    result["manifest"] = str(manifest_path)
    return result
