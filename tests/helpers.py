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


def make_pe32_executable() -> bytes:
    data = bytearray(0x600)
    data[:2] = b"MZ"
    struct.pack_into("<HHHHHHHHHHHHH", data, 2, 0, 3, 0, 4, 0, 0xFFFF, 0, 0x100, 0, 0, 0, 0x40, 0)
    struct.pack_into("<I", data, 0x3C, 0x80)

    pe_offset = 0x80
    data[pe_offset : pe_offset + 4] = b"PE\0\0"
    struct.pack_into(
        "<HHIIIHH",
        data,
        pe_offset + 4,
        0x014C,
        2,
        946_684_800,
        0,
        0,
        224,
        0x0102,
    )
    optional = pe_offset + 24
    struct.pack_into("<HBB", data, optional, 0x10B, 3, 0)
    struct.pack_into("<III", data, optional + 4, 0x200, 0x200, 0)
    struct.pack_into("<III", data, optional + 16, 0x1000, 0x1000, 0x2000)
    struct.pack_into("<III", data, optional + 28, 0x400000, 0x1000, 0x200)
    struct.pack_into("<HHHHHH", data, optional + 40, 4, 0, 1, 0, 4, 0)
    struct.pack_into("<III", data, optional + 56, 0x3000, 0x200, 0)
    struct.pack_into("<HH", data, optional + 68, 2, 0)
    struct.pack_into("<IIIIII", data, optional + 72, 0x100000, 0x1000, 0x100000, 0x1000, 0, 16)
    struct.pack_into("<II", data, optional + 104, 0x2000, 40)
    struct.pack_into("<II", data, optional + 192, 0x2050, 8)

    section_table = optional + 224
    struct.pack_into(
        "<8sIIIIIIHHI",
        data,
        section_table,
        b".text\0\0\0",
        0x180,
        0x1000,
        0x200,
        0x200,
        0,
        0,
        0,
        0,
        0x60000020,
    )
    struct.pack_into(
        "<8sIIIIIIHHI",
        data,
        section_table + 40,
        b".idata\0\0",
        0x180,
        0x2000,
        0x200,
        0x400,
        0,
        0,
        0,
        0,
        0xC0000040,
    )

    struct.pack_into("<IIIII", data, 0x400, 0x2040, 0, 0, 0x2060, 0x2050)
    struct.pack_into("<II", data, 0x440, 0x2070, 0)
    struct.pack_into("<II", data, 0x450, 0x2070, 0)
    data[0x460 : 0x460 + 13] = b"KERNEL32.dll\0"
    data[0x470 : 0x470 + 14] = b"\0\0ExitProcess\0"
    data[0x580 : 0x58B] = b"ASCII_TEST\0"
    data[0x590 : 0x5A4] = "WIDE_TEST\0".encode("utf-16le")
    data[0x5B0 : 0x5C2] = b"RESOURCE\\TEST.RES\0"
    struct.pack_into("<I", data, 0x210, 0x4021B0)
    return bytes(data)


def make_le_executable() -> bytes:
    data = bytearray(0x1200)
    data[:2] = b"MZ"
    struct.pack_into("<HHHHHHHHHHHHH", data, 2, 0x180, 1, 0, 4, 0, 0xFFFF, 0, 0x100, 0, 0, 0, 0x40, 0)
    struct.pack_into("<I", data, 0x3C, 0x80)

    le = 0x80
    data[le : le + 2] = b"LE"
    data[le + 2] = 0
    data[le + 3] = 0
    struct.pack_into("<I", data, le + 0x04, 0)
    struct.pack_into("<HH", data, le + 0x08, 2, 3)
    struct.pack_into("<III", data, le + 0x0C, 0, 0, 1)
    struct.pack_into("<IIII", data, le + 0x18, 1, 0x1234, 1, 0x8000)
    struct.pack_into("<II", data, le + 0x28, 4096, 512)
    struct.pack_into("<II", data, le + 0x40, 0xC4, 1)
    struct.pack_into("<I", data, le + 0x48, 0xF0)
    struct.pack_into("<I", data, le + 0x58, 0xE5)
    struct.pack_into("<II", data, le + 0x70, 0xDC, 1)
    struct.pack_into("<I", data, le + 0x80, 0x1000)

    struct.pack_into("<IIIIII", data, le + 0xC4, 0x200, 0x10000, 0x2007, 1, 1, 0)
    data[le + 0xDC : le + 0xE5] = b"\x08DOSCALLS"
    data[le + 0xE5 : le + 0xF0] = b"\x07CAPPLUS\x01\x00\x00"
    data[le + 0xF0 : le + 0xF4] = b"\x00\x00\x01\x00"
    data[0x1000:0x1200] = bytes((index & 0xFF for index in range(0x200)))
    struct.pack_into("<I", data, 0x1000, 0x100)
    data[0x1100 : 0x1111] = b"GAMESET\\TEST.SET\0"
    return bytes(data)


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
