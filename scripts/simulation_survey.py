#!/usr/bin/env python3
"""Compare clock/RNG models with isolated functions in user-owned executables.

Optional research dependency: Unicorn 2.1.4. The installed inspector does not
import it. Exact executable hashes are checked before the dependency is loaded,
and emulation is restricted to manually audited code ranges and explicit stubs.
"""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import struct
from typing import Any

from capplus_inspect.errors import InspectError
from capplus_inspect.executables import inspect_executable
from capplus_inspect.known import DOS_EXECUTABLE_SHA256, WINDOWS_EXECUTABLE_SHA256
from capplus_inspect.loader_analysis import _regions
from capplus_inspect.png_writer import write_new_file
from capplus_inspect.simulation import (
    CLOCK_MODEL_VERSION,
    RNG_MODEL_VERSION,
    ClockState,
    advance_clock_days,
    advance_clock_loops,
    clock_state_for_date,
    decode_clock_state,
    original_playing_time_display,
    rng_bounded,
)


REFERENCE_HASHES = {
    "dos": DOS_EXECUTABLE_SHA256,
    "windows": WINDOWS_EXECUTABLE_SHA256,
}
MAX_EXECUTABLE_BYTES = 1024 * 1024
RNG_SEEDS = (0, 1, 0x12345678, 0x47A28C03, 0x89ABCDEF, 0xFFFFFFFF)
RNG_MAXIMA = (0, 1, 8, 100, 32767, 8, 8, 8)
FIXED_WALLCLOCK_SEED = 0x65432100
SIMULATION_SENTINEL_SEED = 0x13579BDF

PROFILES: dict[str, dict[str, Any]] = {
    "windows": {
        "base": 0,
        "simulation_rng_object": 0x004A4948,
        "presentation_rng_object": 0x004A6180,
        "rng_state_offset": 0x79,
        "rng_bounded": 0x0047C560,
        "rng_time_seed": 0x0047C530,
        "clock_object": 0x004A7850,
        "clock_daily": 0x00476FA0,
        "clock_month": 0x00477060,
        "clock_year": 0x00477120,
        "clock_loop": 0x00476F80,
        "clock_playing_time": 0x00477250,
        "clock_save_writer": 0x00446E10,
        "clock_save_reader": 0x00446E20,
        "music_selector": 0x00410290,
        "save_rng_writer": 0x00446CF0,
        "save_rng_reader": 0x00446D10,
        "allowed": (
            (0x00476F80, 0x00476F9B),
            (0x00476FA0, 0x00477171),
            (0x0047C530, 0x0047C5A6),
            (0x00410290, 0x004102B5),
        ),
        "stubs": {
            0x00427010: "date_part",
            0x00421FF0: "event",
            0x00477180: "event",
            0x00423210: "return",
            0x004338F0: "return",
            0x00485330: "return",
            0x004694E0: "return",
            0x004172B0: "return",
            0x00435CE0: "return",
            0x00425720: "return",
            0x0041DD60: "return_arg",
            0x00423220: "return",
            0x0042C2D0: "return",
            0x00469520: "return",
            0x004172F0: "return",
            0x004888A0: "wallclock",
            0x0046AA10: "cd_selection",
        },
    },
    "dos": {
        "base": 0x000A0000,
        "simulation_rng_object": 0x0000F710,
        "presentation_rng_object": 0x0000F78D,
        "rng_state_offset": 0x79,
        "rng_bounded": 0x000907A3,
        "rng_time_seed": 0x00090772,
        "clock_object": 0x0001255C,
        "clock_daily": 0x0002755A,
        "clock_month": 0x0002762F,
        "clock_year": 0x000276F8,
        "clock_loop": 0x00027530,
        "clock_playing_time": 0x00027839,
        "clock_save_writer": 0x0001EAC2,
        "clock_save_reader": 0x0001EADD,
        "presentation_seed_call_site": 0x00011158,
        "save_rng_writer": 0x0001E99A,
        "save_rng_reader": 0x0001E9BC,
        "allowed": (
            (0x00027530, 0x0002755A),
            (0x0002755A, 0x00027758),
            (0x00090772, 0x00090817),
        ),
        "stubs": {
            0x00096017: "stack_check",
            0x0008EEC6: "date_part",
            0x00027758: "event",
            0x00027910: "event",
            0x00026D6B: "return",
            0x0006F074: "return",
            0x0004DAA3: "return",
            0x00034F54: "return",
            0x00067A69: "return",
            0x0005E5A7: "return",
            0x0006DFA1: "return",
            0x00020000: "return",
            0x00026D90: "return",
            0x0001AC07: "return",
            0x00034F95: "return",
            0x00067AAA: "return",
            0x00096607: "wallclock",
        },
    },
}


def read_bounded(path: Path, maximum: int = MAX_EXECUTABLE_BYTES) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise InspectError("simulation survey input exceeds its byte limit")
    return data


def _descriptor(base: int, access: int) -> bytes:
    return struct.pack(
        "<HHBBBB",
        0xFFFF,
        base & 0xFFFF,
        (base >> 16) & 0xFF,
        access,
        0xCF,
        (base >> 24) & 0xFF,
    )


def _hex(value: int) -> str:
    return f"0x{value:08X}"


class OriginalSimulationOracle:
    """Execute only the audited RNG, clock and selector slices."""

    def __init__(self, data: bytes, build: str):
        if (
            build not in REFERENCE_HASHES
            or hashlib.sha256(data).hexdigest() != REFERENCE_HASHES[build]
        ):
            raise InspectError(
                "simulation oracle requires the exact unmodified reference executable"
            )
        try:
            import unicorn
            from unicorn import x86_const as registers
        except ImportError as error:
            raise InspectError(
                "simulation survey needs the optional research dependency unicorn==2.1.4"
            ) from error
        if unicorn.__version__ != "2.1.4":
            raise InspectError(
                "simulation survey requires unicorn==2.1.4 for reproducible emulation"
            )

        self.unicorn = unicorn
        self.registers = registers
        self.build = build
        self.profile = PROFILES[build]
        self.base = self.profile["base"]
        self.uc = u = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_32)
        u.mem_map(0, 0xC00000, unicorn.UC_PROT_READ | unicorn.UC_PROT_WRITE)
        for region in _regions(data, inspect_executable(data), executable_only=False):
            u.mem_write(region["address"], region["data"])

        gdt = 0xB00000
        u.mem_write(
            gdt,
            bytes(8) + _descriptor(0, 0x9B) + _descriptor(self.base, 0x93),
        )
        u.reg_write(registers.UC_X86_REG_GDTR, (0, gdt, 23, 0))
        u.reg_write(registers.UC_X86_REG_CS, 8)
        for register in (
            registers.UC_X86_REG_DS,
            registers.UC_X86_REG_ES,
            registers.UC_X86_REG_SS,
        ):
            u.reg_write(register, 16)

        self.stop = 0x00A00000
        self.stack = 0x00900000 - self.base
        self.allowed = tuple(self.profile["allowed"])
        self.stubs = dict(self.profile["stubs"])
        self.fixed_wallclock = FIXED_WALLCLOCK_SEED
        self.events: list[int] = []
        self.calendar_entries = {"month": 0, "year": 0}
        self.cd_selections: list[int] = []

        pages: set[int] = set()
        for start, end in self.allowed:
            pages.update(range(start & ~0xFFF, (end + 0xFFF) & ~0xFFF, 0x1000))
        for address in self.stubs:
            page = address & ~0xFFF
            pages.update((page, page + 0x1000))
        for page in sorted(pages):
            u.mem_protect(
                page,
                0x1000,
                unicorn.UC_PROT_READ | unicorn.UC_PROT_EXEC,
            )
        u.hook_add(unicorn.UC_HOOK_BLOCK, self._guard)

        # Keep optional alert paths inactive. Event dispatch itself is an
        # explicit stub because its game-speed/UI behavior is outside this probe.
        if build == "windows":
            u.mem_write(0x004A6CDF, b"\0")
        else:
            u.mem_write(self.base + 0x00011468, b"\0")

    def _physical(self, logical: int) -> int:
        return self.base + logical

    def _stack_u32(self, stack_pointer: int, offset: int) -> int:
        return struct.unpack(
            "<I", self.uc.mem_read(self._physical(stack_pointer + offset), 4)
        )[0]

    def _return_from_stub(self, stack_pointer: int, cleanup: int = 0) -> None:
        return_address = self._stack_u32(stack_pointer, 0)
        self.uc.reg_write(
            self.registers.UC_X86_REG_ESP, stack_pointer + 4 + cleanup
        )
        self.uc.reg_write(self.registers.UC_X86_REG_EIP, return_address)

    def _handle_stub(self, address: int) -> None:
        r = self.registers
        stack_pointer = self.uc.reg_read(r.UC_X86_REG_ESP)
        if not self.stack - 0x10000 <= stack_pointer < self.stack:
            raise InspectError("simulation oracle stub stack is outside its fixed bounds")
        kind = self.stubs[address]
        cleanup = 0
        if kind == "stack_check":
            cleanup = 4
        elif kind == "date_part":
            if self.build == "windows":
                jdn = self._stack_u32(stack_pointer, 4)
                selector = self._stack_u32(stack_pointer, 8)
                cleanup = 8
            else:
                jdn = self.uc.reg_read(r.UC_X86_REG_EDX)
                selector = self.uc.reg_read(r.UC_X86_REG_EBX)
            try:
                current = date.fromordinal(jdn - 1_721_425)
            except (ValueError, OverflowError) as error:
                raise InspectError("simulation oracle received an invalid JDN") from error
            if selector == ord("M"):
                value = current.month
            elif selector == ord("Y"):
                value = current.year
            else:
                raise InspectError("simulation oracle received an unknown date selector")
            self.uc.reg_write(r.UC_X86_REG_EAX, value)
        elif kind == "event":
            value = (
                self._stack_u32(stack_pointer, 4)
                if self.build == "windows"
                else self.uc.reg_read(r.UC_X86_REG_EDX)
            )
            self.events.append(value)
            cleanup = 4 if self.build == "windows" else 0
        elif kind == "return_arg":
            cleanup = 4
        elif kind == "wallclock":
            self.uc.reg_write(r.UC_X86_REG_EAX, self.fixed_wallclock)
        elif kind == "cd_selection":
            if self.build != "windows":
                raise InspectError("unexpected DOS CD-selection stub")
            self.cd_selections.append(self._stack_u32(stack_pointer, 4))
            cleanup = 4
        elif kind != "return":
            raise InspectError("simulation oracle has an unknown stub kind")
        self._return_from_stub(stack_pointer, cleanup)

    def _guard(self, unused_uc, address: int, size: int, unused_data) -> None:
        if address in self.stubs:
            self._handle_stub(address)
            return
        if address == self.profile["clock_month"]:
            self.calendar_entries["month"] += 1
        elif address == self.profile["clock_year"]:
            self.calendar_entries["year"] += 1
        if not any(start <= address and address + size <= end for start, end in self.allowed):
            raise InspectError(
                f"simulation oracle reached an unaudited code block at 0x{address:X}"
            )

    def _call(
        self,
        address: int,
        args: tuple[int, ...] = (),
        registers: dict[int, int] | None = None,
        *,
        count: int = 1_000_000,
    ) -> int:
        r = self.registers
        stack_pointer = self.stack - 4 * (1 + len(args))
        words = (self.stop, *(value & 0xFFFFFFFF for value in args))
        self.uc.mem_write(
            self._physical(stack_pointer),
            struct.pack("<" + "I" * len(words), *words),
        )
        self.uc.reg_write(r.UC_X86_REG_ESP, stack_pointer)
        for register, value in (registers or {}).items():
            self.uc.reg_write(register, value & 0xFFFFFFFF)
        try:
            self.uc.emu_start(address, self.stop, timeout=5_000_000, count=count)
        except self.unicorn.UcError as error:
            current = self.uc.reg_read(r.UC_X86_REG_EIP)
            raise InspectError(
                f"simulation oracle emulation failed at 0x{current:X}: {error}"
            ) from error
        if self.uc.reg_read(r.UC_X86_REG_EIP) != self.stop:
            raise InspectError("simulation oracle exhausted its time/instruction bound")
        if self.uc.reg_read(r.UC_X86_REG_ESP) != self.stack:
            raise InspectError("simulation oracle did not restore its caller stack")
        return self.uc.reg_read(r.UC_X86_REG_EAX) & 0xFFFFFFFF

    def _rng_address(self, kind: str) -> int:
        key = f"{kind}_rng_object"
        return self._physical(self.profile[key])

    def write_rng(self, kind: str, value: int) -> None:
        self.uc.mem_write(
            self._rng_address(kind) + self.profile["rng_state_offset"],
            struct.pack("<I", value),
        )

    def read_rng(self, kind: str) -> int:
        return struct.unpack(
            "<I",
            self.uc.mem_read(
                self._rng_address(kind) + self.profile["rng_state_offset"], 4
            ),
        )[0]

    def rng_sequence(self, seed: int, maxima: tuple[int, ...]) -> tuple[int, list[int]]:
        self.write_rng("simulation", seed)
        r = self.registers
        values = []
        for maximum in maxima:
            if self.build == "windows":
                value = self._call(
                    self.profile["rng_bounded"],
                    (maximum,),
                    {r.UC_X86_REG_ECX: self.profile["simulation_rng_object"]},
                )
            else:
                value = self._call(
                    self.profile["rng_bounded"],
                    registers={
                        r.UC_X86_REG_EAX: self.profile["simulation_rng_object"],
                        r.UC_X86_REG_EDX: maximum,
                    },
                )
            values.append(value)
        return self.read_rng("simulation"), values

    def run_clock_days(
        self, state: ClockState, count: int
    ) -> tuple[ClockState, dict[str, int]]:
        self.uc.mem_write(self._physical(self.profile["clock_object"]), state.to_bytes())
        self.events.clear()
        self.calendar_entries = {"month": 0, "year": 0}
        r = self.registers
        for _ in range(count):
            registers = {
                r.UC_X86_REG_ECX: self.profile["clock_object"]
            } if self.build == "windows" else {
                r.UC_X86_REG_EAX: self.profile["clock_object"]
            }
            self._call(self.profile["clock_daily"], registers=registers)
        final = ClockState.from_bytes(
            bytes(
                self.uc.mem_read(
                    self._physical(self.profile["clock_object"]), 65
                )
            )
        )
        callbacks = {
            "day": sum(value == 11 for value in self.events),
            "month": self.calendar_entries["month"],
            "year": self.calendar_entries["year"],
        }
        return final, callbacks

    def run_clock_loops(self, state: ClockState, count: int) -> tuple[ClockState, int]:
        self.uc.mem_write(self._physical(self.profile["clock_object"]), state.to_bytes())
        self.events.clear()
        r = self.registers
        for _ in range(count):
            registers = {
                r.UC_X86_REG_ECX: self.profile["clock_object"]
            } if self.build == "windows" else {
                r.UC_X86_REG_EAX: self.profile["clock_object"]
            }
            self._call(self.profile["clock_loop"], registers=registers)
        final = ClockState.from_bytes(
            bytes(
                self.uc.mem_read(
                    self._physical(self.profile["clock_object"]), 65
                )
            )
        )
        return final, sum(value == 11 for value in self.events)

    def presentation_probe(self) -> dict[str, Any]:
        """Use the exact selector where known and prove RNG-object isolation."""

        self.write_rng("simulation", SIMULATION_SENTINEL_SEED)
        self.write_rng("presentation", 0xFFFFFFFF)
        self.fixed_wallclock = FIXED_WALLCLOCK_SEED
        self.cd_selections.clear()
        r = self.registers
        if self.build == "windows":
            self._call(self.profile["music_selector"], (0,))
            selection = self.cd_selections[-1] if self.cd_selections else None
            selector_executed = True
            reachability = "isolated_windows_selector_executed"
        else:
            self._call(
                self.profile["rng_time_seed"],
                registers={r.UC_X86_REG_EAX: self.profile["presentation_rng_object"]},
            )
            selection = self._call(
                self.profile["rng_bounded"],
                registers={
                    r.UC_X86_REG_EAX: self.profile["presentation_rng_object"],
                    r.UC_X86_REG_EDX: 8,
                },
            ) + 1
            selector_executed = False
            reachability = "dos_presentation_rng_pipeline_only_selector_reachability_unresolved"
        expected_state, expected_value = rng_bounded(FIXED_WALLCLOCK_SEED, 8)
        return {
            "fixed_wallclock_seed": _hex(FIXED_WALLCLOCK_SEED),
            "simulation_initial_state": _hex(SIMULATION_SENTINEL_SEED),
            "simulation_final_state": _hex(self.read_rng("simulation")),
            "presentation_final_state": _hex(self.read_rng("presentation")),
            "selection": selection,
            "expected_selection": expected_value + 1,
            "selector_executed": selector_executed,
            "reachability": reachability,
            "simulation_rng_unchanged": self.read_rng("simulation")
            == SIMULATION_SENTINEL_SEED,
            "presentation_rng_matches_model": self.read_rng("presentation")
            == expected_state,
            "passed": (
                self.read_rng("simulation") == SIMULATION_SENTINEL_SEED
                and self.read_rng("presentation") == expected_state
                and selection == expected_value + 1
            ),
        }


def _clock_cases() -> list[dict[str, Any]]:
    return [
        {
            "name": "month_and_day_cap",
            "state": clock_state_for_date(
                date(1990, 1, 29),
                initial_date=date(1990, 1, 1),
                counters=(29, 29, 0, 0, 5, 11, 9),
            ),
            "days": 4,
        },
        {
            "name": "leap_day",
            "state": clock_state_for_date(
                date(1992, 2, 27), initial_date=date(1990, 1, 1)
            ),
            "days": 3,
        },
        {
            "name": "year_and_counter_wrap",
            "state": clock_state_for_date(
                date(1990, 12, 30),
                initial_date=date(1990, 1, 1),
                counters=(28, 29, 29, 9, 5, 11, 9),
            ),
            "days": 3,
        },
    ]


def _profile_report(build: str) -> dict[str, Any]:
    profile = PROFILES[build]
    keys = (
        "simulation_rng_object",
        "presentation_rng_object",
        "rng_bounded",
        "rng_time_seed",
        "clock_object",
        "clock_daily",
        "clock_month",
        "clock_year",
        "clock_loop",
        "clock_playing_time",
        "clock_save_writer",
        "clock_save_reader",
        "save_rng_writer",
        "save_rng_reader",
    )
    addresses = {key: _hex(profile[key]) for key in keys}
    if build == "windows":
        addresses["music_selector"] = _hex(profile["music_selector"])
    else:
        addresses["presentation_seed_call_site"] = _hex(
            profile["presentation_seed_call_site"]
        )
    return {
        "build": build,
        "addresses": addresses,
        "rng_objects_are_distinct": (
            profile["simulation_rng_object"] != profile["presentation_rng_object"]
        ),
    }


def survey(executables: dict[str, bytes]) -> dict[str, Any]:
    if set(executables) != set(REFERENCE_HASHES):
        raise InspectError("simulation survey requires both DOS and Windows builds")

    rng_results: list[dict[str, Any]] = []
    clock_results: list[dict[str, Any]] = []
    loop_results: list[dict[str, Any]] = []
    presentation_results: list[dict[str, Any]] = []
    for build in sorted(executables):
        oracle = OriginalSimulationOracle(executables[build], build)
        for seed in RNG_SEEDS:
            expected_state = seed
            expected_values = []
            for maximum in RNG_MAXIMA:
                expected_state, value = rng_bounded(expected_state, maximum)
                expected_values.append(value)
            original_state, original_values = oracle.rng_sequence(seed, RNG_MAXIMA)
            rng_results.append(
                {
                    "build": build,
                    "initial_state": _hex(seed),
                    "maxima": list(RNG_MAXIMA),
                    "original_values": original_values,
                    "model_values": expected_values,
                    "original_final_state": _hex(original_state),
                    "model_final_state": _hex(expected_state),
                    "integer_tolerance": 0,
                    "passed": (
                        original_state == expected_state
                        and original_values == expected_values
                    ),
                }
            )

        for case in _clock_cases():
            expected_state, expected_callbacks = advance_clock_days(
                case["state"], case["days"]
            )
            original_state, original_callbacks = oracle.run_clock_days(
                case["state"], case["days"]
            )
            clock_results.append(
                {
                    "build": build,
                    "name": case["name"],
                    "duration_days": case["days"],
                    "initial": decode_clock_state(case["state"]),
                    "final": decode_clock_state(original_state),
                    "original_callbacks": original_callbacks,
                    "model_callbacks": expected_callbacks,
                    "differing_state_bytes": sum(
                        left != right
                        for left, right in zip(
                            original_state.to_bytes(), expected_state.to_bytes()
                        )
                    ),
                    "integer_tolerance": 0,
                    "passed": (
                        original_state == expected_state
                        and original_callbacks == expected_callbacks
                    ),
                }
            )

        loop_start = clock_state_for_date(
            date(1990, 1, 1), counters=(0, 0, 0, 0, 0, 0, 9)
        )
        expected_loop, expected_dispatches = advance_clock_loops(loop_start, 25)
        original_loop, original_dispatches = oracle.run_clock_loops(loop_start, 25)
        loop_results.append(
            {
                "build": build,
                "iterations": 25,
                "initial_counter": 9,
                "original_final_counter": original_loop.loop_10_counter,
                "model_final_counter": expected_loop.loop_10_counter,
                "original_event_11_dispatches": original_dispatches,
                "model_event_11_dispatches": expected_dispatches,
                "other_clock_bytes_unchanged": (
                    original_loop.to_bytes()[:60] == loop_start.to_bytes()[:60]
                    and original_loop.to_bytes()[64:] == loop_start.to_bytes()[64:]
                ),
                "integer_tolerance": 0,
                "passed": (
                    original_loop == expected_loop
                    and original_dispatches == expected_dispatches
                ),
            }
        )
        presentation_results.append(
            {"build": build, **oracle.presentation_probe()}
        )

    all_records = rng_results + clock_results + loop_results + presentation_results
    return {
        "schema_version": 1,
        "format": "capitalism_plus_simulation_clock_rng_survey",
        "method": "isolated_original_function_emulation",
        "whole_game_validation": False,
        "emulator": "unicorn 2.1.4",
        "clock_model_version": CLOCK_MODEL_VERSION,
        "rng_model_version": RNG_MODEL_VERSION,
        "executable_sha256": {
            build: hashlib.sha256(data).hexdigest()
            for build, data in sorted(executables.items())
        },
        "profiles": [_profile_report(build) for build in sorted(executables)],
        "numeric_policy": {
            "integer_tolerance": 0,
            "clock_state_byte_tolerance": 0,
            "float_tolerance": "not_applicable",
        },
        "stubs": {
            "calendar_conversion": "Gregorian month/year returned for the supplied JDN",
            "calendar_callbacks": "subsystem work returns without side effects",
            "event_dispatch": "event number recorded without game-speed or UI work",
            "wallclock": f"fixed deterministic seed {_hex(FIXED_WALLCLOCK_SEED)}",
            "windows_cd_wrapper": "selection recorded without platform playback",
            "dos_stack_check": "returns with the Watcom argument removed",
        },
        "rng_vectors": rng_results,
        "clock_vectors": clock_results,
        "loop_vectors": loop_results,
        "presentation_rng_isolation": presentation_results,
        "playing_time_display": {
            "formula": "hours=seconds//3720; minutes=(seconds//62)%60",
            "vectors": [
                {"seconds": value, "display": list(original_playing_time_display(value))}
                for value in (0, 61, 62, 3719, 3720, 3721, 7440)
            ],
            "original_function_emulated": False,
            "status": "statically_confirmed_in_both_builds",
        },
        "passed": all(record["passed"] for record in all_records),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dos-exe", type=Path, required=True)
    parser.add_argument("--windows-exe", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="new sanitized JSON report; never overwritten without --force",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.output.is_symlink():
            raise InspectError("simulation survey output must not be a symlink")
        input_paths = {args.dos_exe.resolve(), args.windows_exe.resolve()}
        if args.output.resolve() in input_paths:
            raise InspectError("simulation survey output must not replace an executable")
        if args.output.exists() and not args.force:
            raise InspectError("simulation survey output already exists")
        result = survey(
            {
                "dos": read_bounded(args.dos_exe),
                "windows": read_bounded(args.windows_exe),
            }
        )
        write_new_file(
            args.output,
            (json.dumps(result, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            force=args.force,
        )
        print(
            f"Simulation checks: {len(result['rng_vectors'])} RNG, "
            f"{len(result['clock_vectors'])} clock, "
            f"{len(result['loop_vectors'])} loop, "
            f"{len(result['presentation_rng_isolation'])} isolation; "
            f"passed={result['passed']}"
        )
        return 0 if result["passed"] else 3
    except (InspectError, OSError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
