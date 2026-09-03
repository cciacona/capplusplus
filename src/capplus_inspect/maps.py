from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION
from .errors import FormatError
from .palette import parse_palette
from .png_writer import write_indexed_png
from .util import c_string, sha256_bytes, u16, u32


MAP_HEADER_SIZE = 52
MAP_WIDTH = 240
MAP_HEIGHT = 198
MAP_CELL_SIZE = 8
MAP_CELL_COUNT = MAP_WIDTH * MAP_HEIGHT
MAP_GRID_SIZE = MAP_CELL_COUNT * MAP_CELL_SIZE
MAP_FOOTER_SIZE = 32
MAP_CORE_SIZE = 380_244
CITY_RECORD_SIZE = 29
MAP_OVERVIEW_PALETTE_OFFSET = 3


def inspect_map(data: bytes) -> dict[str, Any]:
    if len(data) < MAP_CORE_SIZE:
        raise FormatError(
            f"map is shorter than the confirmed {MAP_CORE_SIZE}-byte core"
        )
    tail_size = len(data) - MAP_CORE_SIZE
    if tail_size % CITY_RECORD_SIZE:
        raise FormatError(
            f"map tail is not divisible by the {CITY_RECORD_SIZE}-byte city record size",
            offset=MAP_CORE_SIZE,
        )

    grid_start = MAP_HEADER_SIZE
    grid_end = grid_start + MAP_GRID_SIZE
    if grid_end + MAP_FOOTER_SIZE != MAP_CORE_SIZE:
        raise AssertionError("map structure constants do not match the confirmed core size")
    grid = data[grid_start:grid_end]
    field_summaries = []
    for field_offset in range(MAP_CELL_SIZE):
        values = grid[field_offset::MAP_CELL_SIZE]
        field_summaries.append(
            {
                "offset": field_offset,
                "minimum": min(values),
                "maximum": max(values),
                "distinct_values": len(set(values)),
                "nonzero_count": len(values) - values.count(0),
            }
        )
    overview_pixels = grid[MAP_OVERVIEW_PALETTE_OFFSET::MAP_CELL_SIZE]
    histogram = {
        str(value): count for value, count in sorted(Counter(overview_pixels).items())
    }

    cities: list[dict[str, Any]] = []
    for index in range(tail_size // CITY_RECORD_SIZE):
        offset = MAP_CORE_SIZE + index * CITY_RECORD_SIZE
        name = c_string(data[offset + 8 : offset + 29]).strip()
        cities.append(
            {
                "index": index,
                "offset": offset,
                "x": u16(data, offset),
                "y": u16(data, offset + 2),
                "population": u32(data, offset + 4),
                "name": name,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "format": "capitalism_plus_map",
        "size": len(data),
        "sha256": sha256_bytes(data),
        "core_size": MAP_CORE_SIZE,
        "core_sha256": sha256_bytes(data[:MAP_CORE_SIZE]),
        "internal_path": c_string(data[:22]),
        "display_name": c_string(data[22:MAP_HEADER_SIZE]).strip(),
        "header_size": MAP_HEADER_SIZE,
        "grid": {
            "offset": grid_start,
            "width": MAP_WIDTH,
            "height": MAP_HEIGHT,
            "cell_count": MAP_CELL_COUNT,
            "cell_size": MAP_CELL_SIZE,
            "size": MAP_GRID_SIZE,
            "cell_fields": field_summaries,
            "overview_palette_index_offset": MAP_OVERVIEW_PALETTE_OFFSET,
            "overview_sha256": sha256_bytes(overview_pixels),
            "overview_histogram": histogram,
        },
        "footer": {
            "offset": grid_end,
            "size": MAP_FOOTER_SIZE,
            "hex": data[grid_end:MAP_CORE_SIZE].hex(),
        },
        "city_record_size": CITY_RECORD_SIZE,
        "city_count": len(cities),
        "cities": cities,
    }


def _marked_overview(data: bytes, cities: list[dict[str, Any]]) -> bytes:
    grid = data[MAP_HEADER_SIZE : MAP_HEADER_SIZE + MAP_GRID_SIZE]
    pixels = bytearray(grid[MAP_OVERVIEW_PALETTE_OFFSET::MAP_CELL_SIZE])

    def set_pixel(x: int, y: int, value: int) -> None:
        if 0 <= x < MAP_WIDTH and 0 <= y < MAP_HEIGHT:
            pixels[y * MAP_WIDTH + x] = value

    for city in cities:
        x, y = city["x"], city["y"]
        for delta_y in range(-2, 3):
            for delta_x in range(-2, 3):
                if abs(delta_x) + abs(delta_y) <= 2:
                    set_pixel(x + delta_x, y + delta_y, 0)
        set_pixel(x, y, 255)
        set_pixel(x - 1, y, 255)
        set_pixel(x + 1, y, 255)
        set_pixel(x, y - 1, 255)
        set_pixel(x, y + 1, 255)
    return bytes(pixels)


def render_map(
    data: bytes,
    palette_data: bytes,
    output: Path,
    *,
    scale: int = 4,
    mark_cities: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    info = inspect_map(data)
    palette = parse_palette(palette_data)
    grid = data[MAP_HEADER_SIZE : MAP_HEADER_SIZE + MAP_GRID_SIZE]
    pixels = grid[MAP_OVERVIEW_PALETTE_OFFSET::MAP_CELL_SIZE]
    if mark_cities:
        pixels = _marked_overview(data, info["cities"])
    output = output.resolve()
    write_indexed_png(
        output,
        MAP_WIDTH,
        MAP_HEIGHT,
        pixels,
        palette,
        scale=scale,
        force=force,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "format": "capitalism_plus_map_render",
        "map_sha256": info["sha256"],
        "palette_sha256": sha256_bytes(palette_data),
        "display_name": info["display_name"],
        "width": MAP_WIDTH * scale,
        "height": MAP_HEIGHT * scale,
        "source_width": MAP_WIDTH,
        "source_height": MAP_HEIGHT,
        "scale": scale,
        "city_markers": len(info["cities"]) if mark_cities else 0,
        "output": str(output),
    }
