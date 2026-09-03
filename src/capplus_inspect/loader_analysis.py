from __future__ import annotations

import bisect
import re
import struct
from collections import defaultdict
from typing import Any, Iterable

from . import SCHEMA_VERSION
from .errors import FormatError
from .executables import extract_executable_strings, inspect_executable
from .known import DOS_EXECUTABLE_SHA256, WINDOWS_EXECUTABLE_SHA256
from .records import read_compatible_record


WINDOWS_FILE_PROFILE = {
    "sha256": WINDOWS_EXECUTABLE_SHA256,
    "function_style": "msvc_cc_padding",
    "routines": {
        "open": 0x0044B590,
        "create": 0x0044B640,
        "close": 0x0044B6F0,
        "write": 0x0044B750,
        "read_compatible_record": 0x0044B7E0,
        "seek": 0x0044BB90,
        "size": 0x0044BBB0,
    },
    "runtime_routines": {
        "open": 0x004904C0,
        "read": 0x00490250,
        "write": 0x0048D300,
        "seek": 0x0048D530,
        "close": 0x0048F900,
        "size": 0x00490920,
    },
    "expected_direct_calls": {"open": 23, "create": 6},
}

DOS_FILE_PROFILE = {
    "sha256": DOS_EXECUTABLE_SHA256,
    "function_style": "watcom_stack_check",
    "stack_check_address": 0x00096017,
    "routines": {
        "open": 0x0008F398,
        "create": 0x0008F41A,
        "close": 0x0008F47B,
        "write": 0x0008F505,
        "read_compatible_record": 0x0008F58F,
        "seek": 0x0008F910,
        "position": 0x0008F929,
        "size": 0x0008F994,
    },
    "runtime_routines": {
        "open": 0x00097151,
        "read": 0x000969D4,
        "write": 0x000973B3,
        "seek": 0x00097686,
        "close": 0x00097380,
        "size": 0x000976C8,
    },
    "expected_direct_calls": {"open": 24, "create": 6},
}

FILE_CONTRACTS = {
    "open": {
        "inputs": ["path", "report-errors flag", "framed-record flag"],
        "output": "true when a binary read handle is opened; false on failure",
        "behavior": "closes an existing handle, stores the path, then opens read-only",
    },
    "create": {
        "inputs": ["path", "report-errors flag", "framed-record flag"],
        "output": "true when a binary read/write file is created; false on failure",
        "behavior": "creates or truncates the destination and stores the resulting handle",
    },
    "close": {
        "inputs": ["open file object"],
        "output": "success flag",
        "behavior": "closes a valid handle and resets it to the closed sentinel",
    },
    "write": {
        "inputs": ["source buffer", "byte count"],
        "output": "true only when the requested byte count is written",
        "behavior": "optionally emits a 16-bit size prefix before the payload",
    },
    "read_compatible_record": {
        "inputs": ["destination buffer", "expected byte count"],
        "output": "true only when the selected payload bytes are read",
        "behavior": (
            "with framing enabled, a smaller stored record is zero-extended and a "
            "larger stored record is clipped while its tail is skipped"
        ),
    },
    "seek": {
        "inputs": ["signed displacement", "origin"],
        "output": "resulting file position or an error value",
        "behavior": "maps the engine's origin value to the platform seek primitive",
    },
    "position": {
        "inputs": ["open file object"],
        "output": "current file position",
        "behavior": "queries the current position without changing it",
    },
    "size": {
        "inputs": ["open file object"],
        "output": "file length or a negative error value",
        "behavior": "queries length through the platform runtime",
    },
}

WINDOWS_FILE_APIS = {
    "CreateFileA",
    "ReadFile",
    "WriteFile",
    "SetFilePointer",
    "CloseHandle",
    "DeleteFileA",
}

MAX_FILE_REFERENCES = 4096

_OPERATION_RUNTIME = {
    "open": "open",
    "create": "open",
    "close": "close",
    "write": "write",
    "read_compatible_record": "read",
    "seek": "seek",
    "position": "seek",
    "size": "size",
}

_WINDOWS_RUNTIME_API = {
    "open": "CreateFileA",
    "read": "ReadFile",
    "write": "WriteFile",
    "seek": "SetFilePointer",
    "close": "CloseHandle",
    "size": "SetFilePointer",
}

_FILE_SUFFIXES = {
    ".CFG",
    ".DFI",
    ".FI",
    ".HIN",
    ".HOF",
    ".II",
    ".II2",
    ".IL",
    ".IP",
    ".MAP",
    ".PIC",
    ".PLA",
    ".PLO",
    ".PLP",
    ".RES",
    ".RTI",
    ".RTP",
    ".RTX",
    ".SAM",
    ".SAV",
    ".SCN",
    ".SCP",
    ".SCS",
    ".SCT",
    ".SET",
    ".SND",
    ".SPH",
    ".TUT",
}


def _hex(value: int) -> str:
    return f"0x{value:08X}"


def _classify_file_reference(text: str) -> str | None:
    normalized = text.replace("/", "\\").upper()
    if "\\MSDEV\\" in normalized or normalized.endswith(".CPP"):
        return None
    if normalized.startswith("RESOURCE\\"):
        return "resource"
    if normalized.startswith("GAMESET\\"):
        return "game_set"
    if normalized.startswith("MAPS\\"):
        return "map"

    name = normalized.rsplit("\\", 1)[-1]
    suffix_match = re.search(r"(\.[A-Z0-9]+)$", name)
    suffix = suffix_match.group(1) if suffix_match else ""
    if suffix not in _FILE_SUFFIXES:
        return None
    if suffix in {".SAV"}:
        return "save"
    if suffix in {".SCN", ".SCP", ".SCS", ".SCT", ".HIN", ".SPH", ".TUT"}:
        return "scenario"
    if suffix == ".MAP":
        return "map"
    if suffix in {".SET", ".DFI", ".FI", ".II", ".II2", ".IP", ".PIC", ".PLA", ".PLO", ".PLP"}:
        return "game_set"
    if suffix in {".RES", ".RTI", ".RTP", ".RTX", ".IL", ".SAM"}:
        return "resource"
    return "support"


def _regions(
    data: bytes, executable: dict[str, Any], *, executable_only: bool
) -> list[dict[str, Any]]:
    regions: list[dict[str, Any]] = []
    if executable["executable_format"] == "PE":
        pe = executable["pe"]
        image_base = pe["optional_header"]["image_base"]
        for section in pe["sections"]:
            if executable_only and "execute" not in section["characteristic_names"]:
                continue
            if not section["raw_size"]:
                continue
            start = section["raw_offset"]
            end = start + section["raw_size"]
            regions.append(
                {
                    "name": section["name"],
                    "file_offset": start,
                    "address": image_base + section["virtual_address"],
                    "object_base": image_base,
                    "data": data[start:end],
                }
            )
    elif executable["executable_format"] == "LE":
        for item in executable["le"]["objects"]:
            if executable_only and "execute" not in item["flag_names"]:
                continue
            pages = item.get("pages", [])
            offsets = [page["file_offset"] for page in pages]
            if not offsets or any(offset is None for offset in offsets):
                continue
            page_size = executable["le"]["page_size"]
            if any(
                right != left + page_size
                for left, right in zip(offsets, offsets[1:])
            ):
                continue
            raw_offset = offsets[0]
            stored_size = min(item["stored_size"], item["virtual_size"])
            regions.append(
                {
                    "name": f"object_{item['index']}",
                    "file_offset": raw_offset,
                    "address": item["base_address"],
                    "object_base": item["base_address"],
                    "data": data[raw_offset : raw_offset + stored_size],
                }
            )
    return regions


def _region_for_file_offset(
    regions: Iterable[dict[str, Any]], file_offset: int
) -> tuple[dict[str, Any], int] | None:
    for region in regions:
        delta = file_offset - region["file_offset"]
        if 0 <= delta < len(region["data"]):
            return region, delta
    return None


def _scan_value_references(
    regions: Iterable[dict[str, Any]], value: int
) -> list[dict[str, Any]]:
    needle = struct.pack("<I", value)
    sites: list[dict[str, Any]] = []
    for region in regions:
        position = 0
        while True:
            position = region["data"].find(needle, position)
            if position < 0:
                break
            sites.append(
                {
                    "address": region["address"] + position,
                    "address_hex": _hex(region["address"] + position),
                    "file_offset": region["file_offset"] + position,
                }
            )
            position += 1
    return sites


def _scan_direct_calls(
    regions: Iterable[dict[str, Any]], target: int
) -> list[dict[str, Any]]:
    sites: list[dict[str, Any]] = []
    for region in regions:
        code = region["data"]
        for position in range(max(0, len(code) - 4)):
            if code[position] != 0xE8:
                continue
            address = region["address"] + position
            displacement = struct.unpack_from("<i", code, position + 1)[0]
            if address + 5 + displacement == target:
                sites.append(
                    {
                        "address": address,
                        "address_hex": _hex(address),
                        "file_offset": region["file_offset"] + position,
                    }
                )
    return sites


def _msvc_function_spans(region: dict[str, Any]) -> list[tuple[int, int]]:
    code = region["data"]
    spans: list[tuple[int, int]] = []
    position = 0
    while position < len(code):
        while position < len(code) and code[position] == 0xCC:
            position += 1
        start = position
        while position < len(code) and code[position] != 0xCC:
            position += 1
        if position - start >= 3:
            spans.append((region["address"] + start, region["address"] + position))
    return spans


def _watcom_function_spans(
    region: dict[str, Any], stack_check_address: int
) -> list[tuple[int, int]]:
    code = region["data"]
    starts: list[int] = []
    for position in range(max(0, len(code) - 9)):
        if code[position] != 0x68 or code[position + 5] != 0xE8:
            continue
        call_address = region["address"] + position + 5
        displacement = struct.unpack_from("<i", code, position + 6)[0]
        if call_address + 5 + displacement == stack_check_address:
            starts.append(region["address"] + position)
    starts = sorted(set(starts))
    return [
        (start, starts[index + 1] if index + 1 < len(starts) else region["address"] + len(code))
        for index, start in enumerate(starts)
    ]


def _find_span(
    spans: list[tuple[int, int]], starts: list[int], address: int
) -> tuple[int, int] | None:
    index = bisect.bisect_right(starts, address) - 1
    if index >= 0 and spans[index][0] <= address < spans[index][1]:
        return spans[index]
    return None


def _file_references(
    data: bytes,
    executable: dict[str, Any],
    all_regions: list[dict[str, Any]],
    code_regions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in extract_executable_strings(data, minimum_length=3):
        if item["encoding"] != "ascii":
            continue
        family = _classify_file_reference(item["text"])
        if family is None:
            continue
        mapped = _region_for_file_offset(all_regions, item["offset"])
        if mapped is None:
            continue
        region, delta = mapped
        address = region["address"] + delta
        if executable["executable_format"] == "PE":
            reference_value = address
        else:
            reference_value = address - region["object_base"]
        xrefs = _scan_value_references(code_regions, reference_value)
        results.append(
            {
                "text": item["text"],
                "family": family,
                "file_offset": item["offset"],
                "address": address,
                "address_hex": _hex(address),
                "reference_value": reference_value,
                "reference_value_hex": _hex(reference_value),
                "code_references": xrefs,
            }
        )
        if len(results) > MAX_FILE_REFERENCES:
            raise FormatError("executable contains too many file-like string references")
    results.sort(key=lambda item: (item["family"], item["text"], item["file_offset"]))
    return results


def _function_index(
    code_regions: list[dict[str, Any]], profile: dict[str, Any] | None
) -> tuple[list[tuple[int, int]], list[int]]:
    if profile is None:
        return [], []
    spans: list[tuple[int, int]] = []
    for region in code_regions:
        if profile["function_style"] == "msvc_cc_padding":
            spans.extend(_msvc_function_spans(region))
        else:
            spans.extend(
                _watcom_function_spans(region, profile["stack_check_address"])
            )
    spans.sort()
    return spans, [span[0] for span in spans]


def _associate_calls(
    code_regions: list[dict[str, Any]],
    references: list[dict[str, Any]],
    spans: list[tuple[int, int]],
    starts: list[int],
    call_sites: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    references_by_function: dict[int, set[str]] = defaultdict(set)
    for reference in references:
        for site in reference["code_references"]:
            span = _find_span(spans, starts, site["address"])
            if span is not None:
                references_by_function[span[0]].add(reference["text"])

    incoming: dict[int, set[int]] = defaultdict(set)
    for region in code_regions:
        code = region["data"]
        for position in range(max(0, len(code) - 4)):
            if code[position] != 0xE8:
                continue
            address = region["address"] + position
            source_span = _find_span(spans, starts, address)
            if source_span is None:
                continue
            displacement = struct.unpack_from("<i", code, position + 1)[0]
            destination = address + 5 + displacement
            if destination in starts:
                incoming[destination].add(source_span[0])

    associated: list[dict[str, Any]] = []
    for site in call_sites:
        span = _find_span(spans, starts, site["address"])
        function_start = span[0] if span is not None else None
        direct = sorted(references_by_function.get(function_start, set()))
        one_level: set[str] = set()
        if function_start is not None:
            for caller in incoming.get(function_start, set()):
                one_level.update(references_by_function.get(caller, set()))
        associated.append(
            {
                **site,
                "function_start": function_start,
                "function_start_hex": _hex(function_start) if function_start is not None else None,
                "direct_file_references": direct,
                "immediate_caller_file_references": sorted(one_level - set(direct)),
            }
        )
    return associated


def _windows_api_references(
    executable: dict[str, Any], code_regions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if executable["executable_format"] != "PE":
        return []
    results: list[dict[str, Any]] = []
    for library in executable["pe"]["imports"]:
        for symbol in library["symbols"]:
            name = symbol.get("name")
            if name not in WINDOWS_FILE_APIS:
                continue
            results.append(
                {
                    "library": library["library"],
                    "symbol": name,
                    "iat_rva": symbol["iat_rva"],
                    "iat_address": symbol["iat_address"],
                    "iat_address_hex": _hex(symbol["iat_address"]),
                    "code_references": _scan_value_references(
                        code_regions, symbol["iat_address"]
                    ),
                }
            )
    results.sort(key=lambda item: (item["library"].upper(), item["symbol"]))
    return results


def analyze_loader_boundaries(data: bytes) -> dict[str, Any]:
    """Locate reproducible file-loading boundaries without decompiling code."""

    executable = inspect_executable(data)
    profile = None
    if executable["sha256"] == WINDOWS_EXECUTABLE_SHA256:
        profile = WINDOWS_FILE_PROFILE
    elif executable["sha256"] == DOS_EXECUTABLE_SHA256:
        profile = DOS_FILE_PROFILE

    all_regions = _regions(data, executable, executable_only=False)
    code_regions = _regions(data, executable, executable_only=True)
    references = _file_references(data, executable, all_regions, code_regions)
    spans, starts = _function_index(code_regions, profile)

    routines: list[dict[str, Any]] = []
    verification_errors: list[str] = []
    if profile is not None:
        for name, address in profile["routines"].items():
            calls = _scan_direct_calls(code_regions, address)
            expected = profile["expected_direct_calls"].get(name)
            if expected is not None and len(calls) != expected:
                verification_errors.append(
                    f"{name} direct-call count is {len(calls)}, expected {expected}"
                )
            location = next(
                (
                    {
                        "file_offset": region["file_offset"] + address - region["address"],
                        "region": region["name"],
                    }
                    for region in code_regions
                    if region["address"] <= address < region["address"] + len(region["data"])
                ),
                None,
            )
            routines.append(
                {
                    "name": name,
                    "address": address,
                    "address_hex": _hex(address),
                    "file_offset": location["file_offset"] if location else None,
                    "region": location["region"] if location else None,
                    "contract": FILE_CONTRACTS[name],
                    "direct_call_count": len(calls),
                    "direct_call_sites": _associate_calls(
                        code_regions, references, spans, starts, calls
                    ),
                }
            )

    families: dict[str, set[str]] = defaultdict(set)
    for reference in references:
        if reference["code_references"]:
            families[reference["family"]].add(reference["text"])

    operating_system_file_apis = _windows_api_references(executable, code_regions)
    operation_chains: list[dict[str, Any]] = []
    if profile is not None:
        api_by_name = {
            item["symbol"]: item for item in operating_system_file_apis
        }
        for operation, address in profile["routines"].items():
            runtime_name = _OPERATION_RUNTIME[operation]
            runtime_address = profile["runtime_routines"][runtime_name]
            api_name = (
                _WINDOWS_RUNTIME_API.get(runtime_name)
                if executable["executable_format"] == "PE"
                else None
            )
            operation_chains.append(
                {
                    "operation": operation,
                    "file_routine_address": address,
                    "file_routine_address_hex": _hex(address),
                    "runtime_routine": runtime_name,
                    "runtime_address": runtime_address,
                    "runtime_address_hex": _hex(runtime_address),
                    "operating_system_api": api_name,
                    "operating_system_iat_address": (
                        api_by_name[api_name]["iat_address"]
                        if api_name in api_by_name
                        else None
                    ),
                }
            )

    return {
        "schema_version": SCHEMA_VERSION,
        "format": "capitalism_plus_loader_boundaries",
        "sha256": executable["sha256"],
        "recognized_build": executable.get("recognized_build"),
        "executable_format": executable["executable_format"],
        "method": {
            "direct_calls": "x86 E8 relative-call candidates checked against exact targets",
            "data_references": "32-bit immediate-value candidates in executable regions",
            "function_boundaries": profile.get("function_style") if profile else None,
            "limitations": (
                "candidate scans are deterministic but are not a full instruction decoder; "
                "known-build counts and cross-build agreement provide the verification gate"
            ),
        },
        "profile_applied": profile is not None,
        "profile_verified": profile is not None and not verification_errors,
        "verification_errors": verification_errors,
        "operating_system_file_apis": operating_system_file_apis,
        "file_abstraction": {
            "routines": routines,
            "runtime_routines": [
                {
                    "name": name,
                    "address": address,
                    "address_hex": _hex(address),
                }
                for name, address in (profile or {}).get("runtime_routines", {}).items()
            ],
            "operation_chains": operation_chains,
        },
        "observed_file_references": references,
        "loader_families": [
            {"family": family, "observed_references": sorted(values)}
            for family, values in sorted(families.items())
        ],
        "summary": {
            "observed_file_reference_count": len(references),
            "referenced_file_reference_count": sum(
                bool(item["code_references"]) for item in references
            ),
            "loader_family_count": len(families),
            "file_routine_count": len(routines),
        },
    }


def run_framed_record_probe() -> dict[str, Any]:
    """Exercise exact, short, oversized, and malformed synthetic records."""

    expected = 8
    exact = struct.pack("<H", expected) + b"ABCDEFGH"
    short = struct.pack("<H", 4) + b"ABCD"
    oversized = struct.pack("<H", 12) + b"ABCDEFGHIJKL" + b"NEXT"
    malformed = struct.pack("<H", expected) + b"ABCD"

    exact_payload, exact_next, _ = read_compatible_record(
        exact, 0, expected_size=expected
    )
    short_payload, short_next, _ = read_compatible_record(
        short, 0, expected_size=expected
    )
    large_payload, large_next, _ = read_compatible_record(
        oversized, 0, expected_size=expected
    )

    malformed_error: str | None = None
    try:
        read_compatible_record(malformed, 0, expected_size=expected)
    except FormatError as error:
        malformed_error = str(error)

    checks = {
        "exact_payload_preserved": exact_payload == b"ABCDEFGH" and exact_next == 10,
        "short_payload_zero_extended": short_payload == b"ABCD\0\0\0\0" and short_next == 6,
        "oversized_tail_skipped": large_payload == b"ABCDEFGH" and large_next == 14,
        "declared_truncation_rejected": malformed_error is not None,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "format": "capitalism_plus_framed_record_contract_probe",
        "fixture": "synthetic; contains no game data",
        "expected_size": expected,
        "checks": checks,
        "passed": all(checks.values()),
        "malformed_error": malformed_error,
    }
