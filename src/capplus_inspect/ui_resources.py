from __future__ import annotations

import re
from typing import Any

from . import SCHEMA_VERSION
from .containers import parse_named_index, parse_offset_index, parse_sequential_images
from .dbf import inspect_dbf, looks_like_dbf
from .errors import FormatError
from .fonts import inspect_font
from .util import c_string, sha256_bytes, u16, u32


TEXT_SCREEN_WIDTH = 80
TEXT_SCREEN_HEIGHT = 25
TEXT_CELL_SIZE = 2
CURSOR_FIELDS = (
    ("FILENAME", "C", 8),
    ("HOTSPOT_X", "N", 3),
    ("HOTSPOT_Y", "N", 3),
    ("BITMAPPTR", "C", 4),
)
_RECTANGLE = re.compile(
    r"^\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*$"
)


def inspect_text_screens(data: bytes) -> dict[str, Any]:
    entries = parse_offset_index(data)
    if entries is None:
        raise FormatError("TEXT.RES is not a valid offset-indexed container")

    expected_size = TEXT_SCREEN_WIDTH * TEXT_SCREEN_HEIGHT * TEXT_CELL_SIZE
    screens: list[dict[str, Any]] = []
    for entry in entries:
        payload = data[entry["offset"] : entry["offset"] + entry["size"]]
        if len(payload) != expected_size:
            raise FormatError(
                f"text screen #{entry['index']} has {len(payload)} bytes; expected {expected_size}",
                offset=entry["offset"],
            )
        text_rows: list[str] = []
        character_code_rows: list[str] = []
        attribute_rows: list[str] = []
        attributes: set[int] = set()
        for y in range(TEXT_SCREEN_HEIGHT):
            row = payload[y * TEXT_SCREEN_WIDTH * 2 : (y + 1) * TEXT_SCREEN_WIDTH * 2]
            characters = row[0::2]
            cell_attributes = row[1::2]
            text_rows.append(characters.decode("cp437"))
            character_code_rows.append(characters.hex())
            attribute_rows.append(cell_attributes.hex())
            attributes.update(cell_attributes)
        screens.append(
            {
                **entry,
                "width": TEXT_SCREEN_WIDTH,
                "height": TEXT_SCREEN_HEIGHT,
                "cell_size": TEXT_CELL_SIZE,
                "encoding": "cp437",
                "text_rows": text_rows,
                "character_code_rows": character_code_rows,
                "attribute_rows": attribute_rows,
                "attribute_values": sorted(attributes),
                "sha256": sha256_bytes(payload),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "format": "capitalism_plus_text_screens",
        "size": len(data),
        "sha256": sha256_bytes(data),
        "screen_count": len(screens),
        "screens": screens,
    }


def inspect_language_glyphs(data: bytes) -> dict[str, Any]:
    entries = parse_offset_index(data)
    if entries is None:
        raise FormatError("LANGUAGE.RES is not a valid offset-indexed container")
    glyphs: list[dict[str, Any]] = []
    for entry in entries:
        payload = data[entry["offset"] : entry["offset"] + entry["size"]]
        if len(payload) < 4:
            raise FormatError(
                "language glyph is missing its dimensions", offset=entry["offset"]
            )
        width, height = u16(payload, 0), u16(payload, 2)
        if width == 0 or height == 0 or 4 + width * height != len(payload):
            raise FormatError(
                "language glyph dimensions do not match its payload",
                offset=entry["offset"],
            )
        pixels = payload[4:]
        glyphs.append(
            {
                **entry,
                "width": width,
                "height": height,
                "pixel_bytes": len(pixels),
                "pixel_sha256": sha256_bytes(pixels),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "format": "capitalism_plus_language_glyphs",
        "size": len(data),
        "sha256": sha256_bytes(data),
        "glyph_count": len(glyphs),
        "glyphs": glyphs,
    }


def inspect_cursor_images(data: bytes) -> dict[str, Any]:
    images = parse_sequential_images(data)
    if images is None:
        raise FormatError("I_CURSOR.RES is not a valid sequential image stream")
    return {
        "schema_version": SCHEMA_VERSION,
        "format": "capitalism_plus_cursor_images",
        "size": len(data),
        "sha256": sha256_bytes(data),
        "image_count": len(images),
        "images": images,
    }


def _numeric_ascii(raw: bytes, *, label: str, offset: int) -> int:
    try:
        text = raw.decode("ascii", "strict").strip()
        return int(text)
    except (UnicodeDecodeError, ValueError) as error:
        raise FormatError(f"cursor {label} is not an integer", offset=offset) from error


def inspect_cursor_table(
    data: bytes, *, image_data: bytes | None = None
) -> dict[str, Any]:
    if not looks_like_dbf(data):
        raise FormatError("CURSOR.RES is not a valid dBASE stream")
    dbf = inspect_dbf(data)
    actual_fields = tuple(
        (field["name"], field["type"], field["length"]) for field in dbf["fields"]
    )
    if actual_fields != CURSOR_FIELDS:
        raise FormatError("CURSOR.RES has an unsupported field schema")

    image_by_offset: dict[int, dict[str, Any]] = {}
    image_info = None
    if image_data is not None:
        image_info = inspect_cursor_images(image_data)
        image_by_offset = {image["offset"]: image for image in image_info["images"]}

    cursors: list[dict[str, Any]] = []
    header_length = dbf["header_length"]
    record_length = dbf["record_length"]
    for index in range(dbf["record_count"]):
        record_offset = header_length + index * record_length
        record = data[record_offset : record_offset + record_length]
        pointer_raw = record[15:19]
        bitmap_offset = None if pointer_raw == b"    " else u32(pointer_raw, 0)
        cursor: dict[str, Any] = {
            "index": index,
            "record_number": index + 1,
            "record_offset": record_offset,
            "deleted": record[0:1] == b"*",
            "identifier": c_string(record[1:9], "ascii"),
            "hotspot_x": _numeric_ascii(
                record[9:12], label="HOTSPOT_X", offset=record_offset + 9
            ),
            "hotspot_y": _numeric_ascii(
                record[12:15], label="HOTSPOT_Y", offset=record_offset + 12
            ),
            "bitmap_reference": "blank" if bitmap_offset is None else "file_offset",
            "bitmap_offset": bitmap_offset,
            "bitmap_pointer_bytes": pointer_raw.hex(),
        }
        if image_data is not None and bitmap_offset is not None:
            image = image_by_offset.get(bitmap_offset)
            if image is None:
                raise FormatError(
                    f"cursor {cursor['identifier']!r} references unknown image "
                    f"offset {bitmap_offset}",
                    offset=record_offset + 15,
                )
            cursor["image"] = {
                "index": image["index"],
                "width": image["width"],
                "height": image["height"],
            }
        cursors.append(cursor)

    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "format": "capitalism_plus_cursor_table",
        "size": len(data),
        "sha256": sha256_bytes(data),
        "dbase": dbf,
        "cursor_count": len(cursors),
        "cursors": cursors,
        "image_cross_references_resolved": image_data is not None,
    }
    if image_info is not None:
        result["cursor_image_sha256"] = image_info["sha256"]
        result["cursor_image_count"] = image_info["image_count"]
    return result


def _parse_help_topic(identifier: str, payload: bytes, offset: int) -> dict[str, Any]:
    content = payload.rstrip(b"\x1a")
    try:
        text = content.decode("cp1252")
    except UnicodeDecodeError as error:
        raise FormatError("help topic is not valid CP1252 text", offset=offset) from error
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")

    title = lines[0] if lines and lines[0] else ""
    underline = lines[1] if len(lines) > 1 else ""
    remainder = "\n".join(lines[2:]).lstrip("\n")
    regions: list[dict[str, Any]] = []
    for block_index, block in enumerate(remainder.split("\f")):
        block_lines = block.strip("\n").split("\n") if block.strip("\n") else []
        if not block_lines:
            continue
        match = _RECTANGLE.fullmatch(block_lines[0])
        if match is None:
            raise FormatError("help region does not begin with four coordinates", offset=offset)
        if len(block_lines) < 2:
            raise FormatError("help region is missing its label", offset=offset)
        left, top, right, bottom = (int(value) for value in match.groups())
        if right < left or bottom < top:
            raise FormatError("help region rectangle is reversed", offset=offset)
        description_lines = block_lines[2:]
        regions.append(
            {
                "index": len(regions),
                "source_block_index": block_index,
                "rectangle": {
                    "left": left,
                    "top": top,
                    "right": right,
                    "bottom": bottom,
                },
                "label": block_lines[1],
                "description_lines": description_lines,
                "description": "\n".join(description_lines),
            }
        )
    return {
        "identifier": identifier,
        "offset": offset,
        "size": len(payload),
        "sha256": sha256_bytes(payload),
        "encoding": "cp1252",
        "line_endings": "crlf" if b"\r\n" in content else "other",
        "dos_eof_marker": payload.endswith(b"\x1a"),
        "title": title,
        "underline": underline,
        "region_count": len(regions),
        "regions": regions,
    }


def inspect_help(data: bytes) -> dict[str, Any]:
    entries = parse_named_index(data)
    if entries is None:
        raise FormatError("HELP.RES is not a valid named container")
    topics = [
        _parse_help_topic(
            entry["name"],
            data[entry["offset"] : entry["offset"] + entry["size"]],
            entry["offset"],
        )
        for entry in entries
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "format": "capitalism_plus_context_help",
        "size": len(data),
        "sha256": sha256_bytes(data),
        "topic_count": len(topics),
        "topics": topics,
    }


def inspect_known_ui_resource(
    data: bytes,
    filename: str,
    *,
    cursor_image_data: bytes | None = None,
) -> dict[str, Any] | None:
    name = filename.replace("\\", "/").rsplit("/", 1)[-1].upper()
    if name.startswith("FNT_") and name.endswith(".RES"):
        return inspect_font(data)
    if name == "TEXT.RES":
        return inspect_text_screens(data)
    if name == "LANGUAGE.RES":
        return inspect_language_glyphs(data)
    if name == "CURSOR.RES":
        return inspect_cursor_table(data, image_data=cursor_image_data)
    if name == "I_CURSOR.RES":
        return inspect_cursor_images(data)
    if name == "HELP.RES":
        return inspect_help(data)
    return None
