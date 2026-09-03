from __future__ import annotations

import re
from bisect import bisect_right
from collections import Counter
from typing import Any

from . import SCHEMA_VERSION
from .errors import FormatError
from .util import (
    c_string,
    f32,
    float32_ulp_distance,
    i16,
    jdn_to_iso,
    printable_strings,
    require_range,
    sha256_bytes,
    u16,
    u32,
)


SAVE_VERSION = 100
SECTION_MARKERS = [
    0x100B,
    0x100C,
    0x100D,
    0x100E,
    0x100F,
    0x1010,
    0x1011,
    0x1001,
    0x1002,
    0x1003,
    0x1004,
    0x1005,
    0x1006,
    0x1007,
    0x1008,
    0x1015,
    0x1016,
    0x1017,
    0x1018,
    0x1019,
    0x101A,
    0x101B,
    0x101C,
    0x101D,
]

# Payload sizes independently observed in all compatible version-100 saves.
# Variable-length sections are deliberately omitted.
FIXED_PAYLOAD_SIZES = {
    0x100B: 28_884,
    0x100C: 0,
    0x100D: 152,
    0x100E: 0,
    0x100F: 9_684,
    0x1010: 2,
    0x1011: 223,
    0x1001: 4,
    0x1002: 46,
    0x1005: 67,
    0x1006: 380_174,
    0x1007: 182,
    0x1008: 31,
    0x101C: 78,
    0x101D: 6_613,
}

TOWN_MARKER = 0x101B
RNG_MARKER = 0x1001
TOWN_RECORD_EXPECTED = 371
ITEM_INDEX_EXPECTED = 168
FIRM_INDEX_EXPECTED = 364
MARKET_FLOAT_OFFSETS = (0x7C, 0x80, 0x84, 0x88)


def _marker_occurrences(data: bytes, marker: int, start: int) -> list[int]:
    pattern = marker.to_bytes(2, "little")
    result: list[int] = []
    offset = data.find(pattern, start)
    while offset >= 0:
        result.append(offset)
        offset = data.find(pattern, offset + 1)
    return result


def _resolve_section_offsets(data: bytes, first_offset: int) -> tuple[list[int], int]:
    if u16(data, first_offset) != SECTION_MARKERS[0]:
        raise FormatError("first save-section marker is not 0x100B", offset=first_offset)

    occurrences = {
        marker: _marker_occurrences(data, marker, first_offset)
        for marker in SECTION_MARKERS
    }
    solutions: list[list[int]] = []

    def visit(index: int, current: int, path: list[int]) -> None:
        if len(solutions) > 256:
            return
        if index == len(SECTION_MARKERS) - 1:
            solutions.append(path.copy())
            return

        marker = SECTION_MARKERS[index]
        next_marker = SECTION_MARKERS[index + 1]
        fixed_size = FIXED_PAYLOAD_SIZES.get(marker)
        if fixed_size is not None:
            candidate = current + 2 + fixed_size
            if candidate + 2 <= len(data) and u16(data, candidate) == next_marker:
                visit(index + 1, candidate, [*path, candidate])
            return

        candidates = occurrences[next_marker]
        position = bisect_right(candidates, current + 1)
        for candidate in candidates[position:]:
            visit(index + 1, candidate, [*path, candidate])

    visit(0, first_offset, [first_offset])
    if not solutions:
        raise FormatError("could not resolve the complete 24-marker save-section chain")

    def score(path: list[int]) -> tuple[int, int, int]:
        final_payload = len(data) - (path[-1] + 2)
        return (
            int(final_payload == 6_613),
            -abs(final_payload - 6_613),
            -sum(path),
        )

    solutions.sort(key=score, reverse=True)
    best = solutions[0]
    equally_ranked = sum(score(candidate) == score(best) for candidate in solutions)
    if equally_ranked > 1:
        raise FormatError("save-section marker chain is ambiguous")
    return best, len(solutions)


def _read_framed_record(
    data: bytes,
    offset: int,
    *,
    expected_size: int | None = None,
    limit: int | None = None,
) -> tuple[bytes, int, int]:
    saved_size = u16(data, offset)
    size = expected_size if saved_size == 0 else saved_size
    if size is None:
        raise FormatError("zero-sized record prefix requires an expected size", offset=offset)
    start = offset + 2
    end = start + size
    if limit is not None and end > limit:
        raise FormatError("framed record crosses its section boundary", offset=offset)
    require_range(data, start, size, "framed record")
    return data[start:end], end, saved_size


def _decode_town_array(
    data: bytes, start: int, end: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    if end - start < 10:
        raise FormatError("town-array section is too short", offset=start)
    header = {
        "word_0": u16(data, start),
        "word_1": u16(data, start + 2),
        "date_jdn": u32(data, start + 4),
        "date": jdn_to_iso(u32(data, start + 4)),
        "town_count": u16(data, start + 8),
    }
    if header["town_count"] > 1_000:
        raise FormatError("implausible town count", offset=start + 8)

    offset = start + 10
    towns: list[dict[str, Any]] = []
    town_raw_records: list[bytes] = []
    town_raw_offsets: list[int] = []
    for index in range(header["town_count"]):
        record_prefix = offset
        raw, offset, saved_size = _read_framed_record(
            data,
            offset,
            expected_size=TOWN_RECORD_EXPECTED,
            limit=end,
        )
        if len(raw) < 23:
            raise FormatError("town record is too short", offset=record_prefix)
        name = c_string(raw[2:23]).strip()
        town_raw_records.append(raw)
        town_raw_offsets.append(record_prefix + 2)

        item_data, offset, item_saved = _read_framed_record(
            data,
            offset,
            expected_size=ITEM_INDEX_EXPECTED,
            limit=end,
        )
        firm_data, offset, firm_saved = _read_framed_record(
            data,
            offset,
            expected_size=FIRM_INDEX_EXPECTED,
            limit=end,
        )
        pointer_fields = []
        if len(raw) >= 0x53:
            pointer_fields = [
                {"offset": 0x4B, "value": f"0x{u32(raw, 0x4B):08X}"},
                {"offset": 0x4F, "value": f"0x{u32(raw, 0x4F):08X}"},
            ]
        normalized = bytearray(raw)
        for pointer_offset in (0x4B, 0x4F):
            if pointer_offset + 4 <= len(normalized):
                normalized[pointer_offset : pointer_offset + 4] = b"\0" * 4
        towns.append(
            {
                "index": index + 1,
                "name": name,
                "record_offset": record_prefix,
                "record_saved_size": saved_size,
                "record_effective_size": len(raw),
                "record_sha256": sha256_bytes(raw),
                "record_normalized_sha256": sha256_bytes(normalized),
                "transient_pointer_fields": pointer_fields,
                "item_indexed_saved_size": item_saved,
                "item_indexed_effective_size": len(item_data),
                "item_indexed_sha256": sha256_bytes(item_data),
                "firm_indexed_saved_size": firm_saved,
                "firm_indexed_effective_size": len(firm_data),
                "firm_indexed_sha256": sha256_bytes(firm_data),
            }
        )

    dynamic_header_offset = offset
    dynamic_raw, offset, dynamic_saved_size = _read_framed_record(
        data,
        offset,
        expected_size=44,
        limit=end,
    )
    if len(dynamic_raw) < 20:
        raise FormatError("town dynamic-array header is too short", offset=dynamic_header_offset)
    capacity = u32(dynamic_raw, 0)
    block_size = u32(dynamic_raw, 4)
    active_record = u32(dynamic_raw, 8)
    element_count = u32(dynamic_raw, 12)
    element_size = u32(dynamic_raw, 16)
    if element_count > 1_000_000 or element_size > 1_000_000:
        raise FormatError("implausible town dynamic-array dimensions", offset=dynamic_header_offset)
    expected_data_size = element_count * element_size
    market_data_offset = offset
    market_data, offset, market_saved_size = _read_framed_record(
        data,
        offset,
        expected_size=expected_data_size,
        limit=end,
    )

    market_records: list[bytes] = []
    keys: list[tuple[int, int]] = []
    item_ids: set[int] = set()
    town_ids: set[int] = set()
    float_ranges: dict[str, dict[str, float | int | None]] = {}
    for element_offset in MARKET_FLOAT_OFFSETS:
        float_ranges[f"0x{element_offset:02X}"] = {
            "finite_count": 0,
            "minimum": None,
            "maximum": None,
        }

    for index in range(element_count):
        element = market_data[index * element_size : (index + 1) * element_size]
        market_records.append(element)
        if element_size >= 4:
            key = (u16(element, 0), u16(element, 2))
            keys.append(key)
            town_ids.add(key[0])
            item_ids.add(key[1])
        for element_offset in MARKET_FLOAT_OFFSETS:
            if element_offset + 4 > element_size:
                continue
            value = f32(element, element_offset)
            if value != value or value in (float("inf"), float("-inf")):
                continue
            entry = float_ranges[f"0x{element_offset:02X}"]
            entry["finite_count"] = int(entry["finite_count"]) + 1
            entry["minimum"] = value if entry["minimum"] is None else min(float(entry["minimum"]), value)
            entry["maximum"] = value if entry["maximum"] is None else max(float(entry["maximum"]), value)

    public = {
        "parsed": True,
        "offset": start,
        "size": end - start,
        "header": header,
        "towns": towns,
        "dynamic_array": {
            "header_offset": dynamic_header_offset,
            "header_saved_size": dynamic_saved_size,
            "capacity": capacity,
            "block_size": block_size,
            "active_record": active_record,
            "element_count": element_count,
            "element_size": element_size,
            "data_offset": market_data_offset,
            "data_saved_size": market_saved_size,
            "data_effective_size": len(market_data),
            "town_ids": sorted(town_ids),
            "item_ids": sorted(item_ids),
            "item_id_count": len(item_ids),
            "float_ranges": float_ranges,
        },
        "trailing_bytes": end - offset,
    }
    internal = {
        "town_records": town_raw_records,
        "town_record_offsets": town_raw_offsets,
        "dynamic_header": dynamic_raw,
        "market_records": market_records,
        "market_keys": keys,
    }
    return public, internal


def _parse_save(data: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    if len(data) < 120:
        raise FormatError("save is too short")
    metadata_size = u16(data, 0)
    metadata_start = 2
    metadata_end = metadata_start + metadata_size
    require_range(data, metadata_start, metadata_size, "save metadata")
    version = i16(data, metadata_end)
    settings_size = u16(data, metadata_end + 2)
    settings_start = metadata_end + 4
    settings_end = settings_start + settings_size
    require_range(data, settings_start, settings_size, "save settings")

    metadata = data[metadata_start:metadata_end]
    settings = data[settings_start:settings_end]
    offsets, solution_count = _resolve_section_offsets(data, settings_end)
    bounds = offsets[1:] + [len(data)]
    sections: list[dict[str, Any]] = []
    section_map: dict[int, tuple[int, int]] = {}
    for marker, offset, next_offset in zip(SECTION_MARKERS, offsets, bounds):
        payload_start = offset + 2
        payload_size = next_offset - payload_start
        expected_size = FIXED_PAYLOAD_SIZES.get(marker)
        if expected_size is not None and payload_size != expected_size:
            raise FormatError(
                f"section 0x{marker:04X} has {payload_size} payload bytes; "
                f"expected {expected_size}",
                offset=payload_start,
            )
        payload = data[payload_start:next_offset]
        sections.append(
            {
                "marker": f"{marker:04X}",
                "offset": offset,
                "payload_offset": payload_start,
                "payload_size": payload_size,
                "sha256": sha256_bytes(payload),
                "fixed_size_confirmed": True if marker in FIXED_PAYLOAD_SIZES else None,
            }
        )
        section_map[marker] = (payload_start, next_offset)

    settings_refs = sorted(
        {
            match.group().decode("ascii", "replace").upper()
            for match in re.finditer(rb"[A-Za-z0-9_]{1,16}\.SCT", settings, re.IGNORECASE)
        }
    )
    current_jdn = u32(metadata, 16) if len(metadata) >= 20 else None
    metadata_strings = printable_strings(metadata)
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "format": "capitalism_plus_save",
        "size": len(data),
        "sha256": sha256_bytes(data),
        "metadata_size": metadata_size,
        "internal_filename": c_string(metadata[:13]),
        "save_version": version,
        "supported_save_version": version == SAVE_VERSION,
        "current_date_jdn": current_jdn,
        "current_date": jdn_to_iso(current_jdn) if current_jdn is not None else None,
        "company_name": c_string(metadata[20:51]) if len(metadata) >= 51 else None,
        "scenario_title": c_string(metadata[68:100]) if len(metadata) >= 100 else None,
        "metadata_strings": metadata_strings,
        "settings_size": settings_size,
        "settings_references": settings_refs,
        "section_count": len(sections),
        "marker_chain_candidates": solution_count,
        "sections": sections,
    }

    rng_start, rng_end = section_map[RNG_MARKER]
    if rng_end - rng_start == 4:
        rng_state = u32(data, rng_start)
        result["rng"] = {"state": rng_state, "state_hex": f"0x{rng_state:08X}"}

    town_start, town_end = section_map[TOWN_MARKER]
    try:
        town_public, town_internal = _decode_town_array(data, town_start, town_end)
        result["town_array"] = town_public
    except FormatError as error:
        town_internal = {}
        result["town_array"] = {"parsed": False, "error": str(error)}

    internal = {
        "section_map": section_map,
        "town": town_internal,
    }
    return result, internal


def inspect_save(data: bytes) -> dict[str, Any]:
    result, _ = _parse_save(data)
    return result


def _compare_town_arrays(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any] | None:
    if not left or not right:
        return None
    left_towns = left["town_records"]
    right_towns = right["town_records"]
    pointer_bytes_different = 0
    comparable_towns = min(len(left_towns), len(right_towns))
    for index in range(comparable_towns):
        a, b = left_towns[index], right_towns[index]
        for offset in range(0x4B, 0x53):
            if offset < len(a) and offset < len(b) and a[offset] != b[offset]:
                pointer_bytes_different += 1

    left_market = dict(zip(left["market_keys"], left["market_records"]))
    right_market = dict(zip(right["market_keys"], right["market_records"]))
    shared_keys = sorted(set(left_market) & set(right_market))
    ulp_distribution: Counter[int] = Counter()
    changed_float_fields = 0
    maximum_ulp = 0
    for key in shared_keys:
        a, b = left_market[key], right_market[key]
        for offset in MARKET_FLOAT_OFFSETS:
            if offset + 4 > min(len(a), len(b)):
                continue
            left_value, right_value = f32(a, offset), f32(b, offset)
            if left_value == right_value:
                continue
            distance = float32_ulp_distance(left_value, right_value)
            if distance is not None:
                changed_float_fields += 1
                ulp_distribution[distance] += 1
                maximum_ulp = max(maximum_ulp, distance)

    return {
        "comparable_town_records": comparable_towns,
        "transient_pointer_bytes_different": pointer_bytes_different,
        "shared_town_item_keys": len(shared_keys),
        "changed_known_float_fields": changed_float_fields,
        "maximum_known_float_ulp_distance": maximum_ulp,
        "known_float_ulp_distribution": {
            str(distance): count for distance, count in sorted(ulp_distribution.items())
        },
    }


def compare_saves(left_data: bytes, right_data: bytes) -> dict[str, Any]:
    left, left_internal = _parse_save(left_data)
    right, right_internal = _parse_save(right_data)
    same_position_equal = sum(a == b for a, b in zip(left_data, right_data))
    denominator = max(len(left_data), len(right_data)) or 1

    left_sections = {section["marker"]: section for section in left["sections"]}
    right_sections = {section["marker"]: section for section in right["sections"]}
    section_results: list[dict[str, Any]] = []
    for marker in (f"{value:04X}" for value in SECTION_MARKERS):
        a = left_sections[marker]
        b = right_sections[marker]
        a_start, a_end = a["payload_offset"], a["payload_offset"] + a["payload_size"]
        b_start, b_end = b["payload_offset"], b["payload_offset"] + b["payload_size"]
        a_payload, b_payload = left_data[a_start:a_end], right_data[b_start:b_end]
        equal_bytes = sum(x == y for x, y in zip(a_payload, b_payload))
        section_results.append(
            {
                "marker": marker,
                "left_size": len(a_payload),
                "right_size": len(b_payload),
                "size_delta": len(b_payload) - len(a_payload),
                "byte_identical": a_payload == b_payload,
                "equal_bytes_at_same_offsets": equal_bytes,
                "differing_bytes_at_same_offsets": min(len(a_payload), len(b_payload)) - equal_bytes,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "format": "capitalism_plus_save_comparison",
        "left": {
            "size": left["size"],
            "sha256": left["sha256"],
            "filename": left["internal_filename"],
            "date": left["current_date"],
            "scenario": left["scenario_title"],
            "settings_references": left["settings_references"],
            "rng": left.get("rng"),
        },
        "right": {
            "size": right["size"],
            "sha256": right["sha256"],
            "filename": right["internal_filename"],
            "date": right["current_date"],
            "scenario": right["scenario_title"],
            "settings_references": right["settings_references"],
            "rng": right.get("rng"),
        },
        "same_size": len(left_data) == len(right_data),
        "byte_identical": left_data == right_data,
        "equal_bytes_at_same_offsets": same_position_equal,
        "agreement_against_larger_file": same_position_equal / denominator,
        "sections": section_results,
        "town_array": _compare_town_arrays(
            left_internal.get("town", {}), right_internal.get("town", {})
        ),
    }
