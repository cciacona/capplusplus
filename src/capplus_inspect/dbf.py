from __future__ import annotations

from typing import Any

from .errors import FormatError
from .util import c_string, sha256_bytes, u16, u32


SUPPORTED_VERSIONS = {0x02, 0x03, 0x04, 0x30, 0x31, 0x32, 0x43, 0x63, 0x83, 0x8B, 0xCB}


def looks_like_dbf(data: bytes | memoryview) -> bool:
    if len(data) < 33 or data[0] not in SUPPORTED_VERSIONS:
        return False
    header_length = u16(data, 8)
    record_length = u16(data, 10)
    record_count = u32(data, 4)
    return (
        33 <= header_length <= len(data)
        and record_length >= 1
        and header_length + record_length * record_count <= len(data)
        and data[header_length - 1] == 0x0D
    )


def _decode_field(raw: bytes, field_type: str, decimals: int) -> Any:
    if field_type in {"C", "M", "G"}:
        return raw.rstrip(b" \0").decode("cp1252", "replace")
    text = raw.decode("ascii", "replace").strip(" \0")
    if not text:
        return None
    if field_type in {"N", "F", "B", "Y"}:
        try:
            return float(text) if decimals or "." in text or "e" in text.lower() else int(text)
        except ValueError:
            return text
    if field_type == "L":
        if text[:1].upper() in {"Y", "T"}:
            return True
        if text[:1].upper() in {"N", "F"}:
            return False
        return None
    if field_type == "D" and len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text


def inspect_dbf(data: bytes, *, include_rows: int = 0) -> dict[str, Any]:
    if not looks_like_dbf(data):
        raise FormatError("not a supported or internally consistent DBF stream")

    version = data[0]
    record_count = u32(data, 4)
    header_length = u16(data, 8)
    record_length = u16(data, 10)
    year, month, day = data[1] + 1900, data[2], data[3]
    last_update = None
    if 1 <= month <= 12 and 1 <= day <= 31:
        last_update = f"{year:04d}-{month:02d}-{day:02d}"

    descriptors: list[dict[str, Any]] = []
    position = 32
    row_offset = 1
    while position < header_length - 1:
        if data[position] == 0x0D:
            break
        if position + 32 > header_length:
            raise FormatError("truncated DBF field descriptor", offset=position)
        descriptor = data[position : position + 32]
        name = c_string(descriptor[:11], "ascii")
        field_type = chr(descriptor[11])
        length = descriptor[16]
        decimals = descriptor[17]
        if not name or length == 0:
            raise FormatError("invalid DBF field descriptor", offset=position)
        descriptors.append(
            {
                "name": name,
                "type": field_type,
                "length": length,
                "decimals": decimals,
                "record_offset": row_offset,
            }
        )
        row_offset += length
        position += 32

    if position >= header_length or data[position] != 0x0D:
        raise FormatError("DBF field descriptor terminator is missing", offset=position)
    if row_offset > record_length:
        raise FormatError("DBF fields exceed declared record length")

    deleted_count = 0
    rows: list[dict[str, Any]] = []
    for index in range(record_count):
        start = header_length + index * record_length
        raw_record = data[start : start + record_length]
        deleted = raw_record[:1] == b"*"
        deleted_count += int(deleted)
        if index >= include_rows:
            continue
        row: dict[str, Any] = {"_record": index + 1, "_deleted": deleted}
        for descriptor in descriptors:
            field_start = descriptor["record_offset"]
            field_end = field_start + descriptor["length"]
            row[descriptor["name"]] = _decode_field(
                raw_record[field_start:field_end],
                descriptor["type"],
                descriptor["decimals"],
            )
        rows.append(row)

    trailing = len(data) - (header_length + record_count * record_length)
    result: dict[str, Any] = {
        "format": "dbase",
        "version_byte": version,
        "last_update": last_update,
        "record_count": record_count,
        "deleted_record_count": deleted_count,
        "header_length": header_length,
        "record_length": record_length,
        "field_count": len(descriptors),
        "fields": descriptors,
        "trailing_bytes": trailing,
        "sha256": sha256_bytes(data),
    }
    if include_rows:
        result["rows"] = rows
        result["rows_included"] = len(rows)
    return result
