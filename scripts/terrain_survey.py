#!/usr/bin/env python3
"""Compare terrain reconstruction with isolated functions in user-owned executables.

Optional research dependency: Unicorn 2.1.4. The installed inspector does not
import it. This is CPU-function emulation with explicit stubs, not a game session.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
from typing import Iterator

from capplus_inspect.errors import InspectError
from capplus_inspect.executables import inspect_executable
from capplus_inspect.known import DOS_EXECUTABLE_SHA256, WINDOWS_EXECUTABLE_SHA256
from capplus_inspect.loader_analysis import _regions
from capplus_inspect.maps import MAP_GRID_SIZE, MAP_HEADER_SIZE, inspect_map
from capplus_inspect.png_writer import write_new_file
from capplus_inspect.terrain import (
    TERRAIN_FULL_BOUNDS, TERRAIN_MODEL_VERSION, shade_terrain_grid,
    terrain_length_table, update_terrain_rectangle,
)


REFERENCE_HASHES = {"dos": DOS_EXECUTABLE_SHA256, "windows": WINDOWS_EXECUTABLE_SHA256}
CONTROL_WORDS = (0x027F, 0x037F)
MAX_MAP_FILES = 64
MAX_MAP_BYTES = 1024 * 1024


def read_bounded(path: Path, maximum: int) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise InspectError("terrain survey input exceeds its byte limit")
    return data


def _descriptor(base: int, access: int) -> bytes:
    return struct.pack("<HHBBBB", 0xFFFF, base & 0xFFFF, (base >> 16) & 255,
                       access, 0xCF, (base >> 24) & 255)


class OriginalTerrainOracle:
    """Run only audited code ranges after exact executable-identity validation."""
    def __init__(self, data: bytes, build: str, *, control_word: int = 0x037F):
        if build not in REFERENCE_HASHES or hashlib.sha256(data).hexdigest() != REFERENCE_HASHES[build]:
            raise InspectError("terrain oracle requires the exact unmodified reference executable")
        if control_word not in CONTROL_WORDS:
            raise InspectError("unsupported terrain oracle x87 control word")
        try:
            import unicorn
            from unicorn import x86_const as registers
        except ImportError as error:
            raise InspectError("terrain survey needs the optional research dependency unicorn==2.1.4") from error
        if unicorn.__version__ != "2.1.4":
            raise InspectError("terrain survey requires unicorn==2.1.4 for reproducible emulation")
        self.unicorn, self.registers = unicorn, registers
        self.build = build
        self.control_word = control_word
        self.base = 0 if build == "windows" else 0xA0000
        self.uc = u = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_32)
        u.mem_map(0, 0xC00000, unicorn.UC_PROT_READ | unicorn.UC_PROT_WRITE)
        for region in _regions(data, inspect_executable(data), executable_only=False):
            u.mem_write(region["address"], region["data"])
        gdt = 0xB00000
        u.mem_write(gdt, bytes(8) + _descriptor(0, 0x9B) + _descriptor(self.base, 0x93))
        u.reg_write(registers.UC_X86_REG_GDTR, (0, gdt, 23, 0))
        u.reg_write(registers.UC_X86_REG_CS, 8)
        for reg in (registers.UC_X86_REG_DS, registers.UC_X86_REG_ES, registers.UC_X86_REG_SS):
            u.reg_write(reg, 16)
        self.stop = 0xA00000
        self.stack = 0x900000 - self.base
        self.world = 0x700000 - self.base
        self.grid = 0x600000 - self.base
        self.allowed = (
            ((0x43CAC0, 0x43D1EE), (0x487590, 0x4875B7), (0x423AB0, 0x423BA3))
            if build == "windows" else
            ((0x48384, 0x48B32), (0x964FC, 0x9651B), (0x47519, 0x47606), (0x47486, 0x4748C))
        )
        # Windows event/message polling has no platform here. DOS stack checking
        # returns with its 4-byte argument removed; emulated stack space is fixed.
        self.stubs = {0x41CE40: 0} if build == "windows" else {0x96017: 4}
        for start, end in (*self.allowed, *((address, address + 1) for address in self.stubs)):
            page = start & ~4095
            u.mem_protect(page, ((end + 4095) & ~4095) - page,
                          unicorn.UC_PROT_READ | unicorn.UC_PROT_EXEC)
        self.stub_calls = 0
        u.hook_add(unicorn.UC_HOOK_BLOCK, self._guard)
        u.reg_write(registers.UC_X86_REG_FPCW, control_word)
        # Reference initialized data leaves the Windows FDIV-workaround flag off.
        # No platform initializers or CPU-detection routines are executed.

    def _guard(self, u, address: int, size: int, unused) -> None:
        regs = self.registers
        if address in self.stubs:
            sp = u.reg_read(regs.UC_X86_REG_ESP)
            if not self.stack - 65536 <= sp < self.stack:
                raise InspectError("terrain oracle stub stack is outside its fixed bounds")
            ret, = struct.unpack("<I", u.mem_read(self.base + sp, 4))
            u.reg_write(regs.UC_X86_REG_ESP, sp + 4 + self.stubs[address])
            u.reg_write(regs.UC_X86_REG_EIP, ret)
            self.stub_calls += 1
        elif not any(start <= address and address + size <= end for start, end in self.allowed):
            raise InspectError(f"terrain oracle reached an unaudited code block at 0x{address:X}")

    def _call(self, address: int, args=(), registers=None, *, count: int = 40_000_000) -> None:
        regs = self.registers
        sp = self.stack - 4 * (1 + len(args))
        self.uc.mem_write(self.base + sp, struct.pack("<" + "I" * (len(args) + 1),
                                                    self.stop, *(value & 0xFFFFFFFF for value in args)))
        self.uc.reg_write(regs.UC_X86_REG_ESP, sp)
        for reg, value in (registers or {}).items():
            self.uc.reg_write(reg, value & 0xFFFFFFFF)
        try:
            self.uc.emu_start(address, self.stop, timeout=30_000_000, count=count)
        except self.unicorn.UcError as error:
            raise InspectError(f"terrain oracle emulation failed: {error}") from error
        if self.uc.reg_read(regs.UC_X86_REG_EIP) != self.stop:
            raise InspectError("terrain oracle exhausted its time/instruction bound")
        if self.uc.reg_read(regs.UC_X86_REG_ESP) != self.stack:
            raise InspectError("terrain oracle did not restore its caller stack")

    def initialize(self) -> bytes:
        self._call(0x43CAC0 if self.build == "windows" else 0x48384, count=100_000)
        address = 0x4A3690 if self.build == "windows" else self.base + 0x164E8
        return bytes(self.uc.mem_read(address, 2050))

    def terrain(self, grid: bytes, bounds: tuple[int, int, int, int] = TERRAIN_FULL_BOUNDS) -> bytes:
        if len(grid) != MAP_GRID_SIZE:
            raise InspectError("terrain oracle requires one complete fixed-size source grid")
        left, top, right, bottom = bounds
        if not (0 <= left <= right < 240 and 0 <= top <= bottom < 198):
            raise InspectError("terrain oracle bounds are invalid")
        self.uc.mem_write(0x600000, grid)
        self.uc.mem_write(0x700008, struct.pack("<I", self.grid))
        r = self.registers
        if self.build == "windows":
            self._call(0x423AB0, bounds, {r.UC_X86_REG_ECX: self.world})
        else:
            self._call(0x47519, (bottom,), {r.UC_X86_REG_EAX: self.world,
                                           r.UC_X86_REG_EDX: left, r.UC_X86_REG_EBX: top,
                                           r.UC_X86_REG_ECX: right})
        return bytes(self.uc.mem_read(0x600000, MAP_GRID_SIZE))


def synthetic_grids() -> Iterator[tuple[str, bytes]]:
    """Procedural redistributable probes; no reference asset bytes or save data."""
    for name, value in (("flat_water", -1), ("flat_land", 128), ("flat_peak", 255)):
        yield name, struct.pack("<h6B", value, 2, 3, 4, 5, 6, 7) * 47520
    for name in ("ramp", "checker", "signed_limits"):
        grid = bytearray(MAP_GRID_SIZE)
        for i in range(47520):
            x, y = i % 240, i // 240
            if name == "ramp":
                value = (x * 17 + y * 31) % 257 - 1
            elif name == "checker":
                value = (99, 100, 214, 215, 234, 235, 250, 251, 255)[(x + y) % 9]
            else:
                value = (i * 1103 + 65521) % 65536 - 32768
            struct.pack_into("<h6B", grid, i * 8, value, i % 256, 255, 19, 53, 79, 101)
        yield name, bytes(grid)


PARTIAL_BOUNDS = (
    (120, 99, 120, 99), (117, 96, 123, 102),
    (37, 0, 43, 3), (37, 194, 43, 197),
    (0, 80, 3, 86), (236, 80, 239, 86),
    (0, 0, 3, 3), (236, 0, 239, 3),
    (0, 194, 3, 197), (236, 194, 239, 197),
    (0, 99, 239, 99), (120, 0, 120, 197),
)


def _copy_rectangle(source: bytes, working: bytes, bounds: tuple[int, int, int, int]) -> bytes:
    left, top, right, bottom = bounds
    output = bytearray(working)
    size = (right - left + 1) * 8
    for y in range(top, bottom + 1):
        start = (y * 240 + left) * 8
        output[start:start + size] = source[start:start + size]
    return bytes(output)


def partial_grids(profile: str) -> Iterator[tuple[str, bytes, bytes, tuple[int, int, int, int]]]:
    """Two-grid editor probes: changed source plus an already-converted working grid."""
    inputs = dict(synthetic_grids())
    source = inputs["checker"]
    working = shade_terrain_grid(inputs["ramp"], profile=profile)
    for bounds in PARTIAL_BOUNDS:
        yield "rect_" + "_".join(map(str, bounds)), source, working, bounds


def compare_result(source: bytes, expected: bytes, actual: bytes) -> dict:
    if any(len(data) != MAP_GRID_SIZE for data in (source, expected, actual)):
        raise InspectError("terrain comparison requires complete grids")
    differences = [i for i, (a, b) in enumerate(zip(expected, actual)) if a != b]
    preserved = all(source[offset::8] == actual[offset::8] == expected[offset::8]
                    for offset in (2, 3, 5, 6, 7))
    return {"source_grid_sha256": hashlib.sha256(source).hexdigest(),
            "original_working_grid_sha256": hashlib.sha256(expected).hexdigest(),
            "model_working_grid_sha256": hashlib.sha256(actual).hexdigest(),
            "shade_sha256": hashlib.sha256(actual[4::8]).hexdigest(),
            "differing_bytes": len(differences),
            "first_differing_offset": differences[0] if differences else None,
            "opaque_bytes_preserved": preserved,
            "passed": not differences and preserved}


def survey(executables: dict[str, bytes], maps: list[Path]) -> dict:
    if set(executables) != set(REFERENCE_HASHES) or len(maps) > MAX_MAP_FILES:
        raise InspectError("terrain survey requires both builds and at most 64 maps")
    map_grids = []
    seen = set()
    for path in maps:
        if path.name.casefold() in seen:
            raise InspectError("terrain survey map names collide")
        seen.add(path.name.casefold())
        raw = read_bounded(path, MAX_MAP_BYTES)
        info = inspect_map(raw)
        if not info["has_terrain"]:
            raise InspectError("terrain survey map has no terrain block")
        map_grids.append((path.name, raw[MAP_HEADER_SIZE:MAP_HEADER_SIZE + MAP_GRID_SIZE]))
    results, tables = [], []
    for build, executable in sorted(executables.items()):
        for control_word in CONTROL_WORDS:
            oracle = OriginalTerrainOracle(executable, build, control_word=control_word)
            expected = oracle.initialize()
            actual = struct.pack("<1025h", *terrain_length_table(build))
            tables.append({"build": build, "control_word": hex(control_word),
                           "original_sha256": hashlib.sha256(expected).hexdigest(),
                           "model_sha256": hashlib.sha256(actual).hexdigest(), "passed": actual == expected})
            for kind, cases in (("synthetic", synthetic_grids()), ("user_map", map_grids)):
                for name, grid in cases:
                    expected = oracle.terrain(grid)
                    actual = shade_terrain_grid(grid, profile=build)
                    results.append({"build": build, "control_word": hex(control_word),
                                    "kind": kind, "name": name, **compare_result(grid, expected, actual)})
            for name, source, working, bounds in partial_grids(build):
                prepared = _copy_rectangle(source, working, bounds)
                expected = oracle.terrain(prepared, bounds)
                actual = update_terrain_rectangle(source, working, bounds, profile=build)
                results.append({"build": build, "control_word": hex(control_word),
                                "kind": "partial_rectangle", "name": name,
                                "bounds": list(bounds), **compare_result(prepared, expected, actual)})
    return {"schema_version": 1, "format": "capitalism_plus_terrain_function_survey",
            "terrain_model_version": TERRAIN_MODEL_VERSION, "emulator": "unicorn 2.1.4",
            "method": "isolated_original_function_emulation", "whole_game_validation": False,
            "executable_sha256": {build: hashlib.sha256(data).hexdigest() for build, data in executables.items()},
            "stubs": {"windows": "message/event polling returns without platform work",
                      "dos": "Watcom stack-availability check returns with argument cleanup"},
            "windows_fdiv_workaround": False, "tables": tables, "grids": results,
            "passed": all(record["passed"] for record in tables + results)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dos-exe", type=Path, required=True)
    parser.add_argument("--windows-exe", type=Path, required=True)
    parser.add_argument("--maps", type=Path, help="optional directory of MAP files; six synthetic probes always run")
    parser.add_argument("--output", type=Path, required=True, help="new sanitized JSON report; never overwritten")
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise InspectError("terrain survey output already exists")
        paths = []
        if args.maps is not None:
            if not args.maps.is_dir():
                raise InspectError("terrain survey maps input must be a directory")
            for path in args.maps.iterdir():
                if path.is_file() and path.suffix.lower() == ".map":
                    paths.append(path)
                    if len(paths) > MAX_MAP_FILES:
                        raise InspectError("terrain survey exceeds its 64-map budget")
            if not paths:
                raise InspectError("terrain survey maps directory contains no MAP files")
        result = survey({"dos": read_bounded(args.dos_exe, 1024 * 1024),
                         "windows": read_bounded(args.windows_exe, 1024 * 1024)},
                        sorted(paths, key=lambda p: p.name.casefold()))
        write_new_file(args.output, (json.dumps(result, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        print(f"Terrain function checks: {len(result['tables'])} tables, {len(result['grids'])} grids; passed={result['passed']}")
        return 0 if result["passed"] else 3
    except (InspectError, OSError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
