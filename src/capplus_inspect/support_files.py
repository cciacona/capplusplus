from __future__ import annotations

from typing import Any

from . import SCHEMA_VERSION
from .errors import FormatError
from .records import read_compatible_record
from .util import c_string, sha256_bytes


CONFIGURATION_RECORD_SIZE = 737
HALL_OF_FAME_RECORD_SIZE = 580
HALL_OF_FAME_SLOT_COUNT = 10
HALL_OF_FAME_SLOT_SIZE = 58
SAVE_FILENAME_RECORD_SIZE = 13


def _candidate_text_fields(data: bytes) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    start = 0
    while start < len(data):
        while start < len(data) and not 32 <= data[start] <= 126:
            start += 1
        end = start
        while end < len(data) and 32 <= data[end] <= 126:
            end += 1
        raw = data[start:end]
        value = raw.decode("ascii").rstrip()
        if len(value) >= 2 and any(character.isalnum() for character in value):
            fields.append(
                {
                    "index": len(fields),
                    "offset": start,
                    "stored_length": len(raw),
                    "text": value,
                }
            )
        start = end + 1
    return fields


def inspect_configuration(data: bytes) -> dict[str, Any]:
    logical, end, saved_size = read_compatible_record(
        data, 0, expected_size=CONFIGURATION_RECORD_SIZE
    )
    if end != len(data):
        raise FormatError(f"configuration file has {len(data) - end} trailing bytes", offset=end)
    physical_size = CONFIGURATION_RECORD_SIZE if saved_size == 0 else saved_size
    physical = data[2 : 2 + physical_size]
    candidates = _candidate_text_fields(logical)
    scenario_references = [
        field["text"] for field in candidates if field["text"].upper().endswith(".SCT")
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "format": "capitalism_plus_configuration",
        "size": len(data),
        "sha256": sha256_bytes(data),
        "record": {
            "offset": 2,
            "expected_size": CONFIGURATION_RECORD_SIZE,
            "saved_size_prefix": saved_size,
            "physical_size": physical_size,
            "physical_sha256": sha256_bytes(physical),
            "logical_size": len(logical),
            "logical_sha256": sha256_bytes(logical),
        },
        "candidate_text_fields": candidates,
        "scenario_references": scenario_references,
    }


def inspect_hall_of_fame(data: bytes) -> dict[str, Any]:
    leaderboard, first_end, leaderboard_saved_size = read_compatible_record(
        data, 0, expected_size=HALL_OF_FAME_RECORD_SIZE
    )
    save_filename, end, filename_saved_size = read_compatible_record(
        data,
        first_end,
        expected_size=SAVE_FILENAME_RECORD_SIZE,
    )
    if end != len(data):
        raise FormatError(f"hall-of-fame file has {len(data) - end} trailing bytes", offset=end)

    slots: list[dict[str, Any]] = []
    for index in range(HALL_OF_FAME_SLOT_COUNT):
        offset = index * HALL_OF_FAME_SLOT_SIZE
        slot = leaderboard[offset : offset + HALL_OF_FAME_SLOT_SIZE]
        slots.append(
            {
                "index": index,
                "offset_within_record": offset,
                "size": len(slot),
                "nonzero_bytes": sum(value != 0 for value in slot),
                "sha256": sha256_bytes(slot),
                "candidate_text_fields": _candidate_text_fields(slot),
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "format": "capitalism_plus_hall_of_fame",
        "size": len(data),
        "sha256": sha256_bytes(data),
        "leaderboard": {
            "offset": 2,
            "expected_size": HALL_OF_FAME_RECORD_SIZE,
            "saved_size_prefix": leaderboard_saved_size,
            "logical_size": len(leaderboard),
            "slot_count": HALL_OF_FAME_SLOT_COUNT,
            "slot_size": HALL_OF_FAME_SLOT_SIZE,
            "slots": slots,
        },
        "save_filename_record": {
            "offset": first_end + 2,
            "expected_size": SAVE_FILENAME_RECORD_SIZE,
            "saved_size_prefix": filename_saved_size,
            "logical_size": len(save_filename),
            "filename": c_string(save_filename, "cp1252"),
            "bytes": save_filename.hex(),
        },
    }


def inspect_known_support_file(data: bytes, filename: str) -> dict[str, Any] | None:
    name = filename.replace("\\", "/").rsplit("/", 1)[-1].upper()
    if name == "CAPITAL.CFG":
        return inspect_configuration(data)
    if name == "CAPITAL.HOF":
        return inspect_hall_of_fame(data)
    return None
