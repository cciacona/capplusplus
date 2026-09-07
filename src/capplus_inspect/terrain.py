"""Terrain height/shade reconstruction from the original DOS and Windows profiles."""
from __future__ import annotations

from functools import lru_cache
import struct

from .errors import FormatError
from .maps import MAP_CELL_COUNT, MAP_GRID_SIZE, MAP_HEIGHT, MAP_WIDTH, _initial_terrain_state


TERRAIN_PROFILES = ("dos", "windows")
TERRAIN_MODEL_VERSION = 1


def _trunc_div(numerator: int, denominator: int) -> int:
    return abs(numerator) // denominator * (-1 if numerator < 0 else 1)


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


def shade_terrain_grid(grid: bytes, *, profile: str = "dos") -> bytes:
    """Return a new eight-byte-cell working grid; preserve five opaque bytes/cell.

    This reconstructs the full-map terrain conversion and shade pass. It does
    not draw firms, city markers, isometric sprites, UI or camera projections.
    The bounded post-conversion heights make the original floating-point
    multiply/divide-and-truncate operations equivalent to the integer ratios
    below. Original function emulation checks both build profiles separately.
    """
    if len(grid) != MAP_GRID_SIZE:
        raise FormatError(f"terrain grid must contain exactly {MAP_GRID_SIZE} bytes")
    table = terrain_length_table(profile)
    output = bytearray(grid)
    heights = []
    for index in range(MAP_CELL_COUNT):
        offset = index * 8
        height = struct.unpack_from("<h", grid, offset)[0]
        height, water_shade = _initial_terrain_state(height)
        if water_shade is not None:
            output[offset + 4] = water_shade
        heights.append(height)
        struct.pack_into("<h", output, offset, height)

    lx, ly, lz = _normalize(9703, -64813, 65536, table)
    colors = tuple(80 + i // 2 for i in range(32)) + tuple(range(96, 112))
    for x in range(1, MAP_WIDTH - 1):
        for y in range(1, MAP_HEIGHT - 1):
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
    for x in range(MAP_WIDTH):
        output[x * 8 + 4] = output[(MAP_WIDTH + x) * 8 + 4]
        output[((MAP_HEIGHT - 1) * MAP_WIDTH + x) * 8 + 4] = output[((MAP_HEIGHT - 2) * MAP_WIDTH + x) * 8 + 4]
    for y in range(MAP_HEIGHT):
        output[y * MAP_WIDTH * 8 + 4] = output[(y * MAP_WIDTH + 1) * 8 + 4]
        output[(y * MAP_WIDTH + MAP_WIDTH - 1) * 8 + 4] = output[(y * MAP_WIDTH + MAP_WIDTH - 2) * 8 + 4]
    return bytes(output)
