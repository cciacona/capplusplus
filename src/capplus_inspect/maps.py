from __future__ import annotations

from collections import Counter
from pathlib import Path
import struct
from typing import Any

from . import SCHEMA_VERSION
from .errors import FormatError
from .palette import palette_for_profile
from .png_writer import write_indexed_png
from .util import c_string, i16, require_range, sha256_bytes, u16, u32


MAP_LAYOUT_VERSION = 2
MAP_HEADER_SIZE = 55
MAP_WIDTH = 240
MAP_HEIGHT = 198
MAP_CELL_SIZE = 8
MAP_CELL_COUNT = MAP_WIDTH * MAP_HEIGHT
MAP_GRID_SIZE = MAP_CELL_COUNT * MAP_CELL_SIZE
MAP_FOOTER_SIZE = 29  # Legacy constant name: this is the city-array header.
MAP_CORE_SIZE = 380_244
CITY_RECORD_SIZE = 29
MAP_SETTINGS_SIZE = 737
MAX_MAP_CITIES = 16_384  # Inspection budget, not a claim about the original game limit.
MAP_OVERVIEW_PALETTE_OFFSET = 0  # Historical source-height-low-byte preview only.
CELL_FIELD_NAMES = (
    "terrain_height_low", "terrain_height_high", "unknown_02", "unknown_03",
    "derived_shade", "unknown_05", "unknown_06", "unknown_07",
)


def _initial_terrain_state(height: int) -> tuple[int, int | None]:
    if height < 100:
        # x86 signed division truncates toward zero, unlike Python's // for negatives.
        quotient = abs(height) // 10 * (-1 if height < 0 else 1)
        initial_height = 0
        water_shade = min((240 + quotient) & 0xFF, 249)
    else:
        initial_height = ((height - 100) * 2 // 3 + 1) if height < 215 else min(height, 255)
        water_shade = None
    return initial_height, water_shade


def decode_map_cell(data: bytes) -> dict[str, Any]:
    """Decode one stored cell; full-grid context is needed for its final shade."""
    if len(data) != MAP_CELL_SIZE:
        raise FormatError("map cell must contain exactly eight bytes")
    height = i16(data, 0)
    initial_height, water_shade = _initial_terrain_state(height)
    return {
        "terrain_height": height,
        "source_preview_index": data[0],
        "stored_derived_shade": data[4],
        "unknown_bytes": {str(i): data[i] for i in (2, 3, 5, 6, 7)},
        "initial_terrain_height": initial_height,
        "initial_water_shade": water_shade,
        "final_runtime_shade": None,  # Requires neighbors; use terrain.shade_terrain_grid.
    }


def _city_array_header(data: bytes, offset: int) -> dict[str, Any]:
    require_range(data, offset, MAP_FOOTER_SIZE, "map city-array header")
    capacity, growth, selected, count, size, sort_key = struct.unpack_from("<6i", data, offset)
    if capacity < 0 or growth <= 0 or count < 0 or count > capacity or count > MAX_MAP_CITIES:
        raise FormatError("map city-array count, capacity or growth is invalid", offset=offset)
    if not 0 <= selected <= count:
        raise FormatError("map city-array selected index is outside its records", offset=offset + 8)
    if size != CITY_RECORD_SIZE:
        raise FormatError("map city-array record size must be 29", offset=offset + 16)
    return {
        "offset": offset, "size": MAP_FOOTER_SIZE,
        "capacity": capacity, "growth": growth, "selected_index": selected,
        "record_count": count, "record_size": size, "sort_key_offset": sort_key,
        "unknown_control_byte": data[offset + 24],
        "transient_data_pointer": u32(data, offset + 25),
        "pointer_policy": "preserve_bytes_never_dereference_original_loader_replaces",
        "hex": data[offset:offset + MAP_FOOTER_SIZE].hex(),
    }


def inspect_map(data: bytes) -> dict[str, Any]:
    require_range(data, 0, MAP_HEADER_SIZE, "map header")
    has_terrain, has_settings = bool(data[53]), bool(data[54])
    grid_start = MAP_HEADER_SIZE
    grid_end = grid_start + MAP_GRID_SIZE
    if grid_end + MAP_FOOTER_SIZE != MAP_CORE_SIZE:
        raise AssertionError("map structure constants do not match the confirmed core size")
    array_header = None
    grid = b""
    offset = MAP_HEADER_SIZE
    if has_terrain:
        require_range(data, grid_start, MAP_GRID_SIZE, "map cell grid")
        grid = data[grid_start:grid_end]
        array_header = _city_array_header(data, grid_end)
        offset = MAP_CORE_SIZE
        require_range(data, offset, array_header["record_count"] * CITY_RECORD_SIZE, "map city records")
    core_size = offset
    field_summaries = []
    for field_offset in range(MAP_CELL_SIZE) if has_terrain else ():
        values = grid[field_offset::MAP_CELL_SIZE]
        field_summaries.append(
            {
                "offset": field_offset,
                "name": CELL_FIELD_NAMES[field_offset],
                "status": "unknown" if field_offset in (2, 3, 5, 6, 7) else "confirmed",
                "preservation": "exact",
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
    for index in range(array_header["record_count"] if array_header else 0):
        name = c_string(data[offset + 8 : offset + 29]).strip()
        x, y = u16(data, offset), u16(data, offset + 2)
        if x >= MAP_WIDTH or y >= MAP_HEIGHT:
            raise FormatError("map city coordinates are outside the 240x198 grid", offset=offset)
        cities.append(
            {
                "index": index,
                "offset": offset,
                "x": x,
                "y": y,
                "population": u32(data, offset + 4),
                "name": name,
            }
        )
        offset += CITY_RECORD_SIZE
    settings = None
    if has_settings:
        require_range(data, offset, MAP_SETTINGS_SIZE, "map settings block")
        settings = {"offset": offset, "size": MAP_SETTINGS_SIZE,
                    "sha256": sha256_bytes(data[offset:offset + MAP_SETTINGS_SIZE]),
                    "encoding": "unframed_configuration_record", "field_semantics": "not_decoded"}
        offset += MAP_SETTINGS_SIZE
    if offset != len(data):
        raise FormatError(f"map has {len(data) - offset} trailing bytes", offset=offset)
    heights = [i16(grid, index * MAP_CELL_SIZE) for index in range(MAP_CELL_COUNT)] if has_terrain else []

    return {
        "schema_version": SCHEMA_VERSION,
        "format": "capitalism_plus_map",
        "layout_version": MAP_LAYOUT_VERSION,
        "size": len(data),
        "sha256": sha256_bytes(data),
        "core_size": core_size,
        "core_sha256": sha256_bytes(data[:core_size]),
        "internal_path": c_string(data[:22]),
        "display_name": c_string(data[22:53]).strip(),
        "header_size": MAP_HEADER_SIZE,
        "flags": {"terrain_and_cities": data[53], "settings": data[54]},
        "has_terrain": has_terrain,
        "has_settings": has_settings,
        "grid": {
            "offset": grid_start,
            "width": MAP_WIDTH,
            "height": MAP_HEIGHT,
            "cell_count": MAP_CELL_COUNT,
            "cell_size": MAP_CELL_SIZE,
            "size": MAP_GRID_SIZE,
            "cell_fields": field_summaries,
            "overview_palette_index_offset": MAP_OVERVIEW_PALETTE_OFFSET,
            "overview_semantics": "source_height_low_byte_preview_not_runtime_palette",
            "overview_sha256": sha256_bytes(overview_pixels),
            "overview_histogram": histogram,
            "terrain_height": {"offset_within_cell": 0, "size": 2, "type": "i16le",
                               "minimum": min(heights), "maximum": max(heights),
                               "negative_count": sum(value < 0 for value in heights),
                               "below_water_threshold_count": sum(value < 100 for value in heights)},
        } if has_terrain else None,
        "footer": array_header,  # Retained JSON key; now correctly framed and named below.
        "city_array_header": array_header,
        "city_record_size": CITY_RECORD_SIZE,
        "city_count": len(cities),
        "cities": cities,
        "settings": settings,
    }


def _marked_overview(source_pixels: bytes, cities: list[dict[str, Any]]) -> bytes:
    pixels = bytearray(source_pixels)

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
    palette_profile: str = "source",
    terrain_profile: str | None = None,
    scale: int = 4,
    mark_cities: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    info = inspect_map(data)
    if not info["has_terrain"]:
        raise FormatError("map contains no terrain grid to preview")
    palette = palette_for_profile(palette_data, palette_profile)
    grid = data[MAP_HEADER_SIZE : MAP_HEADER_SIZE + MAP_GRID_SIZE]
    pixels = grid[MAP_OVERVIEW_PALETTE_OFFSET::MAP_CELL_SIZE]
    working_grid = None
    terrain_model_version = None
    semantics = "source_height_low_byte_preview_not_runtime_palette"
    if terrain_profile is not None:
        from .terrain import TERRAIN_MODEL_VERSION, shade_terrain_grid
        terrain_model_version = TERRAIN_MODEL_VERSION
        working_grid = shade_terrain_grid(grid, profile=terrain_profile)
        pixels = working_grid[4::MAP_CELL_SIZE]
        semantics = "derived_terrain_shade_preview_isolated_original_functions_checked"
    if mark_cities:
        pixels = _marked_overview(pixels, info["cities"])
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
        "map_layout_version": MAP_LAYOUT_VERSION,
        "render_semantics": semantics,
        "terrain_profile": terrain_profile,
        "terrain_model_version": terrain_model_version,
        "terrain_working_grid_sha256": sha256_bytes(working_grid) if working_grid is not None else None,
        "whole_game_rendering_validated": False,
        "palette_sha256": sha256_bytes(palette_data),
        "palette_profile": palette_profile,
        "output_palette_rgb_sha256": sha256_bytes(bytes(channel for color in palette for channel in color)),
        "display_name": info["display_name"],
        "width": MAP_WIDTH * scale,
        "height": MAP_HEIGHT * scale,
        "source_width": MAP_WIDTH,
        "source_height": MAP_HEIGHT,
        "scale": scale,
        "city_markers": len(info["cities"]) if mark_cities else 0,
        "output": str(output),
    }
