from __future__ import annotations

import struct
from collections.abc import Iterable

from capplus_inspect.saves import FIXED_PAYLOAD_SIZES, SECTION_MARKERS


def make_dbf(
    fields: list[tuple[str, str, int, int]], rows: Iterable[list[str]]
) -> bytes:
    materialized_rows = list(rows)
    header_length = 32 + len(fields) * 32 + 1
    record_length = 1 + sum(field[2] for field in fields)
    header = bytearray(32)
    header[0:4] = bytes((0x03, 97, 4, 11))
    struct.pack_into("<IHH", header, 4, len(materialized_rows), header_length, record_length)

    descriptors = bytearray()
    for name, field_type, length, decimals in fields:
        descriptor = bytearray(32)
        encoded_name = name.encode("ascii")[:11]
        descriptor[: len(encoded_name)] = encoded_name
        descriptor[11] = ord(field_type)
        descriptor[16] = length
        descriptor[17] = decimals
        descriptors.extend(descriptor)

    records = bytearray()
    for values in materialized_rows:
        record = bytearray(b" ")
        for value, (_, field_type, length, _) in zip(values, fields, strict=True):
            encoded = value.encode("ascii")
            if field_type in {"N", "F"}:
                encoded = encoded.rjust(length)
            else:
                encoded = encoded.ljust(length)
            record.extend(encoded[:length])
        records.extend(record)
    return bytes(header + descriptors + b"\r" + records + b"\x1a")


def make_named_container(members: list[tuple[str, bytes]]) -> bytes:
    header_size = 2 + (len(members) + 1) * 13
    offsets: list[int] = []
    position = header_size
    for _, payload in members:
        offsets.append(position)
        position += len(payload)
    offsets.append(position)

    result = bytearray(struct.pack("<H", len(members)))
    for (name, _), offset in zip(members, offsets, strict=False):
        encoded = name.encode("ascii")[:8]
        result.extend(encoded + b"\0" * (9 - len(encoded)))
        result.extend(struct.pack("<I", offset))
    result.extend(b"\0" * 9 + struct.pack("<I", offsets[-1]))
    for _, payload in members:
        result.extend(payload)
    return bytes(result)


def make_palette() -> bytes:
    colors = bytes(
        channel
        for index in range(256)
        for channel in (index, 255 - index, (index * 3) & 0xFF)
    )
    return struct.pack("<II", 776, 0x12345678) + colors


def make_minimal_save(*, rng_state: int = 0x12345678) -> bytes:
    metadata = bytearray(100)
    metadata[:12] = b"TEST_001.SAV"
    struct.pack_into("<I", metadata, 16, 2_447_893)
    metadata[20:32] = b"Test Company"
    metadata[68:81] = b"Test Scenario"
    settings = b"TEST.SCT\0"

    result = bytearray(struct.pack("<H", len(metadata)))
    result.extend(metadata)
    result.extend(struct.pack("<hH", 100, len(settings)))
    result.extend(settings)

    for marker in SECTION_MARKERS:
        result.extend(struct.pack("<H", marker))
        if marker == 0x1001:
            payload = struct.pack("<I", rng_state)
        elif marker == 0x101B:
            dynamic = bytearray(44)
            struct.pack_into("<IIIII", dynamic, 0, 0, 100, 0, 0, 238)
            payload = (
                struct.pack("<HHIH", 100, 100, 2_447_893, 0)
                + struct.pack("<H", len(dynamic))
                + dynamic
                + b"\0\0"
            )
        elif marker in FIXED_PAYLOAD_SIZES:
            payload = bytes(FIXED_PAYLOAD_SIZES[marker])
        elif marker == 0x101D:
            payload = bytes(6_613)
        else:
            payload = b""
        result.extend(payload)
    return bytes(result)
