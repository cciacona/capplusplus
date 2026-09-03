from __future__ import annotations

from typing import Any

from . import SCHEMA_VERSION
from .dbf import inspect_dbf, looks_like_dbf
from .errors import FormatError
from .palette import inspect_palette, looks_like_palette
from .util import c_string, sha256_bytes, u16, u32


MAX_MEMBERS = 16_384


def _printable_name(raw: bytes) -> bool:
    value = raw.split(b"\0", 1)[0]
    return bool(value) and all(32 <= byte < 127 for byte in value)


def parse_named_index(data: bytes) -> list[dict[str, Any]] | None:
    if len(data) < 15:
        return None
    count = u16(data, 0)
    if count == 0 or count > MAX_MEMBERS:
        return None
    header_size = 2 + (count + 1) * 13
    if header_size > len(data):
        return None

    entries: list[tuple[str, int]] = []
    for index in range(count + 1):
        offset = 2 + index * 13
        raw_name = data[offset : offset + 9]
        member_offset = u32(data, offset + 9)
        entries.append((c_string(raw_name, "ascii"), member_offset))

    if entries[-1][0] or entries[-1][1] != len(data):
        return None
    if any(not _printable_name(data[2 + i * 13 : 11 + i * 13]) for i in range(count)):
        return None
    offsets = [offset for _, offset in entries]
    if offsets[0] < header_size or any(left > right for left, right in zip(offsets, offsets[1:])):
        return None

    return [
        {
            "index": index,
            "name": entries[index][0],
            "offset": entries[index][1],
            "size": entries[index + 1][1] - entries[index][1],
        }
        for index in range(count)
    ]


def parse_offset_index(data: bytes) -> list[dict[str, Any]] | None:
    if len(data) < 10:
        return None
    count = u16(data, 0)
    if count == 0 or count > MAX_MEMBERS:
        return None
    header_size = 2 + (count + 1) * 4
    if header_size > len(data):
        return None
    offsets = [u32(data, 2 + index * 4) for index in range(count + 1)]
    if offsets[-1] != len(data) or offsets[0] < header_size:
        return None
    if any(left > right for left, right in zip(offsets, offsets[1:])):
        return None
    return [
        {
            "index": index,
            "offset": offsets[index],
            "size": offsets[index + 1] - offsets[index],
        }
        for index in range(count)
    ]


def parse_sequential_images(data: bytes) -> list[dict[str, Any]] | None:
    images: list[dict[str, Any]] = []
    offset = 0
    while offset < len(data):
        if len(images) >= MAX_MEMBERS or offset + 8 > len(data):
            return None
        record_size = u32(data, offset)
        if record_size < 4 or offset + 4 + record_size > len(data):
            return None
        width = u16(data, offset + 4)
        height = u16(data, offset + 6)
        if width == 0 or height == 0 or record_size != 4 + width * height:
            return None
        images.append(
            {
                "index": len(images),
                "offset": offset,
                "record_size": record_size,
                "width": width,
                "height": height,
                "pixel_bytes": width * height,
            }
        )
        offset += 4 + record_size
    return images or None


def classify_payload(data: bytes) -> dict[str, Any]:
    if looks_like_dbf(data):
        info = inspect_dbf(data)
        return {
            "kind": "dbase",
            "record_count": info["record_count"],
            "field_count": info["field_count"],
        }
    if len(data) >= 4:
        width, height = u16(data, 0), u16(data, 2)
        if width and height and 4 + width * height == len(data):
            return {"kind": "indexed_image", "width": width, "height": height}
    signatures = (
        (b"GIF87a", "gif87a"),
        (b"GIF89a", "gif89a"),
        (b"RIFF", "riff"),
        (b"FORM", "iff_form"),
        (b"OggS", "ogg"),
        (b"%PDF", "pdf"),
        (b"MZ", "mz_executable"),
    )
    for signature, kind in signatures:
        if data.startswith(signature):
            return {"kind": kind}
    return {"kind": "binary"}


def _indexed_members(data: bytes, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for entry in entries:
        start = entry["offset"]
        payload = data[start : start + entry["size"]]
        result.append(
            {
                **entry,
                "sha256": sha256_bytes(payload),
                **classify_payload(payload),
            }
        )
    return result


def inspect_resource(data: bytes) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "size": len(data),
        "sha256": sha256_bytes(data),
    }

    if looks_like_palette(data):
        return inspect_palette(data)

    named = parse_named_index(data)
    if named is not None:
        return {
            **base,
            "format": "named_container",
            "member_count": len(named),
            "members": _indexed_members(data, named),
        }

    offset_only = parse_offset_index(data)
    if offset_only is not None:
        return {
            **base,
            "format": "offset_container",
            "member_count": len(offset_only),
            "members": _indexed_members(data, offset_only),
        }

    images = parse_sequential_images(data)
    if images is not None:
        return {
            **base,
            "format": "sequential_images",
            "image_count": len(images),
            "images": images,
        }

    return {**base, "format": "raw", **classify_payload(data)}


def inspect_set(data: bytes, *, include_rows: int = 0) -> dict[str, Any]:
    entries = parse_named_index(data)
    if entries is None:
        raise FormatError("game-set file is not a valid named container")

    tables: list[dict[str, Any]] = []
    for entry in entries:
        start = entry["offset"]
        payload = data[start : start + entry["size"]]
        if not looks_like_dbf(payload):
            raise FormatError(f"game-set member {entry['name']!r} is not a DBF stream", offset=start)
        tables.append(
            {
                "name": entry["name"],
                "offset": start,
                "size": entry["size"],
                **inspect_dbf(payload, include_rows=include_rows),
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "format": "capitalism_plus_game_set",
        "size": len(data),
        "sha256": sha256_bytes(data),
        "table_count": len(tables),
        "tables": tables,
    }
