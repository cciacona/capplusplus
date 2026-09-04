from __future__ import annotations

import struct
from typing import Any

from . import SCHEMA_VERSION
from .errors import FormatError
from .util import c_string, require_range, sha256_bytes, u16, u32


PLAN_ARRAY_HEADER_SIZE = 29
PLAN_RECORD_SIZE = 127
PLAN_REFERENCE_SIZE = 72
PLAN_CELL_COUNT = 9
MAX_PLAN_CATEGORIES = 256
MAX_PLAN_RECORDS = 16_384


def _i32(data: bytes, offset: int) -> int:
    require_range(data, offset, 4, "int32")
    return struct.unpack_from("<i", data, offset)[0]


def _identifier(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("cp1252", "replace").rstrip()


def _inspect_plan_record(
    record: bytes,
    stable_references: bytes,
    *,
    index: int,
    offset: int,
    reference_offset: int,
) -> dict[str, Any]:
    if len(record) != PLAN_RECORD_SIZE or len(stable_references) != PLAN_REFERENCE_SIZE:
        raise FormatError("internal plan-record framing error", offset=offset)

    cells: list[dict[str, Any]] = []
    for cell_index in range(PLAN_CELL_COUNT):
        identifier_raw = stable_references[cell_index * 8 : (cell_index + 1) * 8]
        cells.append(
            {
                "index": cell_index,
                "row": cell_index // 3,
                "column": cell_index % 3,
                "functional_unit_id": u16(record, 37 + cell_index * 2),
                "item_id": u16(record, 55 + cell_index * 2),
                "stable_item_identifier": _identifier(identifier_raw),
                "stable_item_identifier_bytes": identifier_raw.hex(),
            }
        )

    return {
        "index": index,
        "offset": offset,
        "size": len(record),
        "sha256": sha256_bytes(record),
        "name": c_string(record[:29], "cp1252"),
        "record_number": u16(record, 29),
        "unknown_byte_31": record[31],
        "unknown_byte_32": record[32],
        "unknown_bytes_33_36": record[33:37].hex(),
        "grid_width": 3,
        "grid_height": 3,
        "cells": cells,
        "transient_pointer_region": {
            "offset_within_record": 73,
            "size": 36,
            "sha256": sha256_bytes(record[73:109]),
        },
        "opaque_tail": {
            "offset_within_record": 109,
            "size": 18,
            "sha256": sha256_bytes(record[109:127]),
        },
        "stable_reference_offset": reference_offset,
        "stable_reference_size": len(stable_references),
        "stable_reference_sha256": sha256_bytes(stable_references),
    }


def inspect_layout_plan(data: bytes) -> dict[str, Any]:
    if len(data) < 2:
        raise FormatError("layout-plan file is missing its category count")
    category_count = u16(data, 0)
    if category_count > MAX_PLAN_CATEGORIES:
        raise FormatError("layout-plan category count is unreasonable")

    categories: list[dict[str, Any]] = []
    offset = 2
    total_records = 0
    for category_index in range(category_count):
        category_offset = offset
        require_range(data, offset, 4 + PLAN_ARRAY_HEADER_SIZE, "layout-plan category header")
        raw_identifier = data[offset : offset + 4]
        identifier = _identifier(raw_identifier)
        if not identifier:
            raise FormatError("layout-plan category identifier is empty", offset=offset)
        offset += 4

        header_offset = offset
        capacity = _i32(data, offset)
        growth = _i32(data, offset + 4)
        selected_index = _i32(data, offset + 8)
        record_count = _i32(data, offset + 12)
        record_size = _i32(data, offset + 16)
        sort_key_offset = _i32(data, offset + 20)
        control_byte = data[offset + 24]
        transient_pointer = u32(data, offset + 25)
        offset += PLAN_ARRAY_HEADER_SIZE

        if capacity < 0 or growth <= 0 or record_count < 0:
            raise FormatError(
                "layout-plan array header has a negative count or invalid growth",
                offset=header_offset,
            )
        if record_count > capacity or record_count > MAX_PLAN_RECORDS:
            raise FormatError(
                "layout-plan record count exceeds its declared capacity",
                offset=header_offset,
            )
        if selected_index < 0 or selected_index > record_count:
            raise FormatError(
                "layout-plan selected index is outside its record range",
                offset=header_offset + 8,
            )
        if record_size != PLAN_RECORD_SIZE:
            raise FormatError(
                f"layout-plan record size is {record_size}; expected {PLAN_RECORD_SIZE}",
                offset=header_offset + 16,
            )

        raw_records_offset = offset
        raw_records_size = record_count * record_size
        require_range(data, raw_records_offset, raw_records_size, "layout-plan records")
        offset += raw_records_size
        stable_references_offset = offset
        stable_references_size = record_count * PLAN_REFERENCE_SIZE
        require_range(
            data,
            stable_references_offset,
            stable_references_size,
            "layout-plan stable references",
        )
        offset += stable_references_size

        records = []
        for record_index in range(record_count):
            record_offset = raw_records_offset + record_index * record_size
            reference_offset = stable_references_offset + record_index * PLAN_REFERENCE_SIZE
            records.append(
                _inspect_plan_record(
                    data[record_offset : record_offset + record_size],
                    data[reference_offset : reference_offset + PLAN_REFERENCE_SIZE],
                    index=record_index,
                    offset=record_offset,
                    reference_offset=reference_offset,
                )
            )

        total_records += record_count
        categories.append(
            {
                "index": category_index,
                "offset": category_offset,
                "identifier": identifier,
                "identifier_bytes": raw_identifier.hex(),
                "array_header": {
                    "offset": header_offset,
                    "size": PLAN_ARRAY_HEADER_SIZE,
                    "capacity": capacity,
                    "growth": growth,
                    "selected_index": selected_index,
                    "record_count": record_count,
                    "record_size": record_size,
                    "sort_key_offset": sort_key_offset,
                    "unknown_control_byte": control_byte,
                    "transient_data_pointer": transient_pointer,
                },
                "raw_records_offset": raw_records_offset,
                "stable_references_offset": stable_references_offset,
                "records": records,
            }
        )

    if offset != len(data):
        raise FormatError(
            f"layout-plan file has {len(data) - offset} trailing bytes",
            offset=offset,
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "format": "capitalism_plus_layout_plans",
        "size": len(data),
        "sha256": sha256_bytes(data),
        "category_count": category_count,
        "record_count": total_records,
        "array_header_size": PLAN_ARRAY_HEADER_SIZE,
        "record_size": PLAN_RECORD_SIZE,
        "stable_reference_size": PLAN_REFERENCE_SIZE,
        "categories": categories,
    }
