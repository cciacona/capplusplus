"""Terrain height/shade reconstruction from the original DOS and Windows profiles."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import struct

from .dbf import inspect_dbf
from .errors import FormatError
from .maps import MAP_CELL_COUNT, MAP_GRID_SIZE, MAP_HEIGHT, MAP_WIDTH, _initial_terrain_state


TERRAIN_PROFILES = ("dos", "windows")
TERRAIN_MODEL_VERSION = 1
RUNTIME_TERRAIN_MODEL_VERSION = 1
TERRAIN_FULL_BOUNDS = (0, 0, MAP_WIDTH - 1, MAP_HEIGHT - 1)
TERRAIN_TILE_BASE = 0x2000
TERRAIN_LAND_BASE = 0x2000
TERRAIN_HILL_BASE = 0x2013
TERRAIN_WATER_BASE = 0x202D
MAX_TERRAIN_PATTERNS = 0x6000
_RNG_MULTIPLIER = 0x015A4E35


@dataclass(frozen=True)
class TerrainPattern:
    """One normalized row from ``TERRAIN.RES``'s dBASE table."""

    corners: tuple[int, int, int, int]
    probability: int
    filename: str
    additional_variants: int


@dataclass(frozen=True)
class TerrainInitializationResult:
    """Immutable output and RNG bookkeeping for a runtime initialization stage."""

    grid: bytes
    rng_state: int
    climate_center_row: int
    field_random_calls: int
    variant_random_calls: int = 0

    @property
    def random_calls(self) -> int:
        return self.field_random_calls + self.variant_random_calls


def _validated_grid(grid: bytes | bytearray) -> None:
    if not isinstance(grid, (bytes, bytearray)):
        raise FormatError("terrain grid must be bytes or bytearray")
    if len(grid) != MAP_GRID_SIZE:
        raise FormatError(f"terrain grid must contain exactly {MAP_GRID_SIZE} bytes")


def _validated_profile(profile: str) -> None:
    if profile not in TERRAIN_PROFILES:
        raise FormatError("terrain profile must be dos or windows")


def _validated_rng_state(state: int) -> None:
    if isinstance(state, bool) or not isinstance(state, int) or not 0 <= state <= 0xFFFFFFFF:
        raise FormatError("terrain RNG state must be an unsigned 32-bit integer")


def _random(state: int, maximum: int) -> tuple[int, int]:
    state = (state * _RNG_MULTIPLIER + 1) & 0xFFFFFFFF
    raw = (state >> 16) & 0x7FFF
    return state, (raw * maximum) >> 15


def _signed_byte(value: int) -> int:
    return value - 256 if value & 0x80 else value


def _trunc_div(numerator: int, denominator: int) -> int:
    return abs(numerator) // denominator * (-1 if numerator < 0 else 1)


def parse_terrain_resource(data: bytes) -> tuple[TerrainPattern, ...]:
    """Normalize the corner-pattern rows used by the runtime terrain routines."""
    info = inspect_dbf(data, include_rows=0)
    expected = (
        ("NW_TYPE", "C", 1), ("NE_TYPE", "C", 1),
        ("SW_TYPE", "C", 1), ("SE_TYPE", "C", 1),
        ("PROBABILTY", "C", 1), ("FILENAME", "C", 8),
        ("BITMAPPTR", "C", 4),
    )
    actual = tuple((field["name"], field["type"], field["length"])
                   for field in info["fields"])
    if actual != expected:
        raise FormatError("TERRAIN.RES has an unsupported dBASE field layout")
    count = info["record_count"]
    if not 1 <= count <= MAX_TERRAIN_PATTERNS:
        raise FormatError("TERRAIN.RES pattern count is outside the supported tile-ID range")

    header_length, record_length = info["header_length"], info["record_length"]
    raw_patterns: list[tuple[tuple[int, int, int, int], int, str]] = []
    for index in range(count):
        record = data[header_length + index * record_length:
                      header_length + (index + 1) * record_length]
        if record[:1] != b" ":
            raise FormatError("TERRAIN.RES contains a deleted or invalid row")
        corners = tuple(record[1:5])
        probability = 5 if record[5] == 0x20 else (record[5] - 0x30) & 0xFF
        filename = record[6:14].rstrip(b" \0").decode("cp1252", "replace")
        raw_patterns.append((corners, probability, filename))

    additional = [0] * count
    group_start = 0
    for index in range(1, count + 1):
        if index == count or raw_patterns[index][0] != raw_patterns[group_start][0]:
            additional[group_start] = (index - group_start - 1) & 0xFF
            group_start = index
    return tuple(
        TerrainPattern(corners, probability, filename, additional[index])
        for index, (corners, probability, filename) in enumerate(raw_patterns)
    )


def classify_terrain_tiles(grid: bytes | bytearray) -> bytes:
    """Replace converted working heights with the three base terrain tile IDs."""
    _validated_grid(grid)
    output = bytearray(grid)
    for index in range(MAP_CELL_COUNT):
        offset = index * 8
        height = struct.unpack_from("<h", output, offset)[0]
        tile = TERRAIN_HILL_BASE if height >= 215 else (
            TERRAIN_LAND_BASE if height > 0 else TERRAIN_WATER_BASE
        )
        struct.pack_into("<H", output, offset, tile)
    return bytes(output)


def _pattern_for(tile: int, patterns: tuple[TerrainPattern, ...]) -> TerrainPattern:
    index = tile - TERRAIN_TILE_BASE
    if not 0 <= index < len(patterns):
        raise FormatError(f"terrain tile ID 0x{tile:04X} has no TERRAIN.RES record")
    return patterns[index]


_WATER_NEIGHBORS = (
    (-1, 0, (False, True, False, True)),
    (1, 0, (True, False, True, False)),
    (0, -1, (False, False, True, True)),
    (0, 1, (True, True, False, False)),
    (-1, -1, (False, False, False, True)),
    (1, -1, (False, False, True, False)),
    (-1, 1, (False, True, False, False)),
    (1, 1, (True, False, False, False)),
)


def apply_water_transitions(
    grid: bytes | bytearray, patterns: tuple[TerrainPattern, ...]
) -> bytes:
    """Apply the original ordered shoreline-corner transition pass."""
    _validated_grid(grid)
    if not patterns:
        raise FormatError("terrain pattern table must not be empty")
    output = bytearray(grid)
    for y in range(MAP_HEIGHT):
        for x in range(MAP_WIDTH):
            offset = (y * MAP_WIDTH + x) * 8
            if struct.unpack_from("<H", output, offset)[0] != TERRAIN_WATER_BASE:
                continue
            for dx, dy, sea_corners in _WATER_NEIGHBORS:
                nx, ny = x + dx, y + dy
                if not (0 <= nx < MAP_WIDTH and 0 <= ny < MAP_HEIGHT):
                    continue
                neighbor_offset = (ny * MAP_WIDTH + nx) * 8
                tile = struct.unpack_from("<H", output, neighbor_offset)[0]
                if tile == TERRAIN_WATER_BASE:
                    continue
                current = _pattern_for(tile, patterns)
                corners = tuple(
                    ord("S") if sea else ord("G") if value == ord("H") else value
                    for value, sea in zip(current.corners, sea_corners)
                )
                replacement = next(
                    (TERRAIN_TILE_BASE + index for index, pattern in enumerate(patterns)
                     if pattern.corners == corners),
                    0,
                )
                if not replacement:
                    raise FormatError(
                        f"TERRAIN.RES has no shoreline pattern for cell ({nx}, {ny})"
                    )
                struct.pack_into("<H", output, neighbor_offset, replacement)
    return bytes(output)


def initialize_terrain_cell_fields(
    grid: bytes | bytearray, rng_state: int, *, profile: str = "dos"
) -> TerrainInitializationResult:
    """Generate climate, rainfall and soil-fertility bytes on a private grid copy."""
    _validated_grid(grid)
    _validated_rng_state(rng_state)
    _validated_profile(profile)
    output = bytearray(grid)
    calls = 0

    rng_state, climate_offset = _random(rng_state, 130)
    calls += 1
    climate_center = climate_offset + 34
    for y in range(MAP_HEIGHT):
        jitter = 0
        for x in range(MAP_WIDTH):
            offset = (y * MAP_WIDTH + x) * 8
            if x % 10 == 0:
                rng_state, jitter_value = _random(rng_state, 11)
                calls += 1
                jitter = jitter_value - 5

            climate = 4 - abs(y - climate_center) // 34
            output[offset + 5] = max(climate, 0) & 0xFF

            if x > 0 and y > 0:
                left, above = output[offset - 2], output[offset - MAP_WIDTH * 8 + 6]
                if profile == "windows":
                    left, above = _signed_byte(left), _signed_byte(above)
                rainfall = _trunc_div(left + above, 2)
                rng_state, variation = _random(rng_state, 5)
                calls += 1
                rainfall = (rainfall + variation + jitter - 2) & 0xFF
            else:
                rng_state, rainfall = _random(rng_state, 63)
                calls += 1
            tile = struct.unpack_from("<H", output, offset)[0]
            rainfall_compare = (
                _signed_byte(rainfall) if profile == "windows" else rainfall
            )
            if tile == TERRAIN_WATER_BASE and rainfall_compare < 32:
                rainfall |= 0x10
            rainfall_compare = (
                _signed_byte(rainfall) if profile == "windows" else rainfall
            )
            if rainfall_compare < 10:
                rainfall = 10
            rainfall_compare = (
                _signed_byte(rainfall) if profile == "windows" else rainfall
            )
            if rainfall_compare > 63:
                rainfall = 63
            output[offset + 6] = rainfall

            if tile != TERRAIN_WATER_BASE:
                if x > 0 and y > 0:
                    left, above = output[offset - 1], output[offset - MAP_WIDTH * 8 + 7]
                    if profile == "windows":
                        left, above = _signed_byte(left), _signed_byte(above)
                    fertility = _trunc_div(left + above, 2)
                    rng_state, variation = _random(rng_state, 5)
                    calls += 1
                    fertility = (fertility + variation + jitter - 2) & 0xFF
                    if tile != TERRAIN_LAND_BASE:
                        fertility &= 0x1F
                    fertility_compare = (
                        _signed_byte(fertility) if profile == "windows" else fertility
                    )
                    if fertility_compare < 0:
                        fertility = 0
                    fertility_compare = (
                        _signed_byte(fertility) if profile == "windows" else fertility
                    )
                    if fertility_compare > 100:
                        fertility = 100
                else:
                    rng_state, fertility = _random(rng_state, 100)
                    calls += 1
                output[offset + 7] = fertility

    for offset in range(6, MAP_GRID_SIZE, 8):
        output[offset] = (_signed_byte(output[offset]) >> 4) & 0xFF
    return TerrainInitializationResult(bytes(output), rng_state, climate_center, calls)


def randomize_terrain_variants(
    grid: bytes | bytearray,
    patterns: tuple[TerrainPattern, ...],
    rng_state: int,
    *,
    profile: str = "dos",
    climate_center_row: int = 0,
    field_random_calls: int = 0,
) -> TerrainInitializationResult:
    """Select a variant within each consecutive equal-corner terrain group."""
    _validated_grid(grid)
    _validated_rng_state(rng_state)
    _validated_profile(profile)
    output = bytearray(grid)
    calls = 0
    for index in range(MAP_CELL_COUNT):
        offset = index * 8
        tile = struct.unpack_from("<H", output, offset)[0]
        additional = _pattern_for(tile, patterns).additional_variants
        should_randomize = additional > 0 if profile == "dos" else 0 < additional < 0x80
        if should_randomize:
            rng_state, variant = _random(rng_state, additional + 1)
            calls += 1
            struct.pack_into("<H", output, offset, (tile + variant) & 0xFFFF)
    return TerrainInitializationResult(
        bytes(output), rng_state, climate_center_row, field_random_calls, calls
    )


def initialize_runtime_terrain(
    shaded_grid: bytes | bytearray,
    terrain_resource: bytes,
    rng_state: int,
    *,
    profile: str = "dos",
) -> TerrainInitializationResult:
    """Reproduce all four post-shading working-grid initialization passes."""
    patterns = parse_terrain_resource(terrain_resource)
    classified = classify_terrain_tiles(shaded_grid)
    transitioned = apply_water_transitions(classified, patterns)
    fields = initialize_terrain_cell_fields(transitioned, rng_state, profile=profile)
    return randomize_terrain_variants(
        fields.grid,
        patterns,
        fields.rng_state,
        profile=profile,
        climate_center_row=fields.climate_center_row,
        field_random_calls=fields.field_random_calls,
    )


def _f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


@lru_cache(maxsize=2)
def terrain_length_table(profile: str) -> tuple[int, ...]:
    """Generate the 1,025-word table; neither profile uses a square-root function."""
    if profile not in TERRAIN_PROFILES:
        raise FormatError("terrain profile must be dos or windows")
    value, step, delta = 0.0, _f32(0.2), _f32(0.015)
    result = []
    for _ in range(1025):
        result.append(int(value))
        value += step
        step += delta
        if profile == "dos":
            value, step = _f32(value), _f32(step)
    # Windows' additions of these dyadic constants are exact in binary64 here;
    # DOS explicitly rounds both accumulators to binary32 after each addition.
    return tuple(result)


def _pair_length(a: int, b: int, table: tuple[int, ...]) -> int:
    high, low = max(abs(a), abs(b)), min(abs(a), abs(b))
    if not high:
        return 0
    index = (low * 65536 // high) // 64
    return high * (65536 + table[index]) // 65536


def _normalize(x: int, y: int, z: int, table: tuple[int, ...]) -> tuple[int, int, int]:
    length = _pair_length(_pair_length(x, y, table), z, table)
    # All caller vectors have positive Z; arbitrary zero vectors are not an API.
    return tuple(_trunc_div(v * 65536, length) for v in (x, y, z))


def _shade_index(height: int, intensity: int) -> int:
    if height < 100:
        return min(intensity, 31)
    if height < 235:
        if 16 < intensity < 32:
            intensity = (intensity - 16) // 2 + 32
        return min(intensity, 38)
    if height < 251:
        if 16 < intensity < 39:
            intensity = (intensity - 16) // 4 + 39
        return min(intensity, 44)
    if 16 < intensity < 44:
        intensity = (intensity - 16) // 5 + 45
    return min(intensity, 47)


def _validated_bounds(bounds: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    if (not isinstance(bounds, tuple) or len(bounds) != 4
            or any(isinstance(value, bool) or not isinstance(value, int) for value in bounds)):
        raise FormatError("terrain bounds must be a four-integer tuple")
    left, top, right, bottom = bounds
    if not (0 <= left <= right < MAP_WIDTH and 0 <= top <= bottom < MAP_HEIGHT):
        raise FormatError("terrain bounds must be an inclusive rectangle within 240x198")
    return bounds


def _convert_and_shade_rectangle(
    grid: bytes | bytearray,
    bounds: tuple[int, int, int, int],
    *,
    profile: str,
    require_prepared_outside: bool,
) -> bytes:
    """Mirror the original mixed-state rectangle routine on a private copy."""
    if len(grid) != MAP_GRID_SIZE:
        raise FormatError(f"terrain grid must contain exactly {MAP_GRID_SIZE} bytes")
    left, top, right, bottom = _validated_bounds(bounds)
    table = terrain_length_table(profile)
    output = bytearray(grid)
    heights = [struct.unpack_from("<h", grid, index * 8)[0] for index in range(MAP_CELL_COUNT)]
    if require_prepared_outside:
        for y in range(MAP_HEIGHT):
            for x in range(MAP_WIDTH):
                if not (left <= x <= right and top <= y <= bottom):
                    height = heights[y * MAP_WIDTH + x]
                    if not 0 <= height <= 255:
                        raise FormatError(
                            "terrain working-grid heights outside the update rectangle must be converted"
                        )

    for y in range(top, bottom + 1):
        for x in range(left, right + 1):
            index = y * MAP_WIDTH + x
            offset = index * 8
            height, water_shade = _initial_terrain_state(heights[index])
            if water_shade is not None:
                output[offset + 4] = water_shade
            heights[index] = height
            struct.pack_into("<h", output, offset, height)

    lx, ly, lz = _normalize(9703, -64813, 65536, table)
    colors = tuple(80 + i // 2 for i in range(32)) + tuple(range(96, 112))
    for x in range(max(left, 1), min(right, MAP_WIDTH - 2) + 1):
        for y in range(max(top, 1), min(bottom, MAP_HEIGHT - 2) + 1):
            index = y * MAP_WIDTH + x
            height = heights[index]
            if not height:
                continue
            nw, ne = heights[index - MAP_WIDTH - 1], heights[index - MAP_WIDTH + 1]
            sw, se = heights[index + MAP_WIDTH - 1], heights[index + MAP_WIDTH + 1]
            dx = 256 * (heights[index - 1] - heights[index + 1]) + 128 * (nw + sw - ne - se)
            dy = 256 * (heights[index - MAP_WIDTH] - heights[index + MAP_WIDTH]) + 128 * (nw + ne - sw - se)
            nx, ny, nz = _normalize(dx, dy, 21845, table)
            dot = _trunc_div(nx * lx, 65536) + _trunc_div(ny * ly, 65536) + _trunc_div(nz * lz, 65536)
            intensity = max(_trunc_div(dot - 35000, 1000), 0)
            output[index * 8 + 4] = colors[_shade_index(height, intensity)]

    # Original full-rectangle edge order: top, bottom, left, right. Only shade
    # bytes are copied; border heights and opaque bytes retain their own cells.
    if top == 0:
        for x in range(left, right + 1):
            output[x * 8 + 4] = output[(MAP_WIDTH + x) * 8 + 4]
    if bottom == MAP_HEIGHT - 1:
        for x in range(left, right + 1):
            output[((MAP_HEIGHT - 1) * MAP_WIDTH + x) * 8 + 4] = output[((MAP_HEIGHT - 2) * MAP_WIDTH + x) * 8 + 4]
    if left == 0:
        for y in range(top, bottom + 1):
            output[y * MAP_WIDTH * 8 + 4] = output[(y * MAP_WIDTH + 1) * 8 + 4]
    if right == MAP_WIDTH - 1:
        for y in range(top, bottom + 1):
            output[(y * MAP_WIDTH + MAP_WIDTH - 1) * 8 + 4] = output[(y * MAP_WIDTH + MAP_WIDTH - 2) * 8 + 4]
    return bytes(output)


def update_terrain_rectangle(
    source_grid: bytes | bytearray,
    working_grid: bytes | bytearray,
    bounds: tuple[int, int, int, int],
    *,
    profile: str = "dos",
) -> bytes:
    """Copy a source rectangle into a converted working grid, then recompute it.

    This is the map editor's two-grid contract. Bounds are inclusive. Cells
    outside the rectangle stay byte-identical and must already contain converted
    heights in 0..255; cells inside are copied in full before conversion.
    """
    if len(source_grid) != MAP_GRID_SIZE or len(working_grid) != MAP_GRID_SIZE:
        raise FormatError(f"terrain grids must contain exactly {MAP_GRID_SIZE} bytes each")
    left, top, right, bottom = _validated_bounds(bounds)
    prepared = bytearray(working_grid)
    row_size = (right - left + 1) * 8
    for y in range(top, bottom + 1):
        start = (y * MAP_WIDTH + left) * 8
        prepared[start:start + row_size] = source_grid[start:start + row_size]
    return _convert_and_shade_rectangle(
        prepared, bounds, profile=profile, require_prepared_outside=True
    )


def shade_terrain_grid(grid: bytes, *, profile: str = "dos") -> bytes:
    """Return a new full-map working grid; preserve five opaque bytes/cell.

    This reconstructs the full-map terrain conversion and shade pass. It does
    not draw firms, city markers, isometric sprites, UI or camera projections.
    The bounded post-conversion heights make the original floating-point
    multiply/divide-and-truncate operations equivalent to the integer ratios
    below. Original function emulation checks both build profiles separately.
    """
    return _convert_and_shade_rectangle(
        grid, TERRAIN_FULL_BOUNDS, profile=profile, require_prepared_outside=False
    )
