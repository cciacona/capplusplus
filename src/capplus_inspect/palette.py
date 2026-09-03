from __future__ import annotations

from typing import Any

from . import SCHEMA_VERSION
from .errors import FormatError
from .util import sha256_bytes, u32


PALETTE_HEADER_SIZE = 8
PALETTE_COLOR_COUNT = 256
PALETTE_DATA_SIZE = PALETTE_COLOR_COUNT * 3
PALETTE_FILE_SIZE = PALETTE_HEADER_SIZE + PALETTE_DATA_SIZE


def looks_like_palette(data: bytes | memoryview) -> bool:
    return len(data) == PALETTE_FILE_SIZE and u32(data, 0) == len(data)


def parse_palette(data: bytes) -> tuple[tuple[int, int, int], ...]:
    if not looks_like_palette(data):
        raise FormatError(
            "palette must be an 8-byte header followed by 256 RGB triples"
        )
    raw = data[PALETTE_HEADER_SIZE:]
    return tuple(tuple(raw[offset : offset + 3]) for offset in range(0, len(raw), 3))


def inspect_palette(data: bytes) -> dict[str, Any]:
    colors = parse_palette(data)
    return {
        "schema_version": SCHEMA_VERSION,
        "format": "capitalism_plus_palette",
        "size": len(data),
        "sha256": sha256_bytes(data),
        "declared_size": u32(data, 0),
        "header_word_1": u32(data, 4),
        "color_count": len(colors),
        "channel_minimum": min(min(color) for color in colors),
        "channel_maximum": max(max(color) for color in colors),
        "colors": [
            {"index": index, "r": color[0], "g": color[1], "b": color[2]}
            for index, color in enumerate(colors)
        ],
    }
