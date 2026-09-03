from __future__ import annotations

import hashlib
import math
import struct
from datetime import date
from pathlib import Path
from typing import Any

from .errors import FormatError


def require_range(data: bytes | memoryview, offset: int, size: int, label: str) -> None:
    if offset < 0 or size < 0 or offset + size > len(data):
        raise FormatError(
            f"{label} extends past end of file (need {size} bytes, have {max(0, len(data) - offset)})",
            offset=offset,
        )


def u16(data: bytes | memoryview, offset: int) -> int:
    require_range(data, offset, 2, "uint16")
    return struct.unpack_from("<H", data, offset)[0]


def i16(data: bytes | memoryview, offset: int) -> int:
    require_range(data, offset, 2, "int16")
    return struct.unpack_from("<h", data, offset)[0]


def u32(data: bytes | memoryview, offset: int) -> int:
    require_range(data, offset, 4, "uint32")
    return struct.unpack_from("<I", data, offset)[0]


def f32(data: bytes | memoryview, offset: int) -> float:
    require_range(data, offset, 4, "float32")
    return struct.unpack_from("<f", data, offset)[0]


def c_string(raw: bytes | memoryview, encoding: str = "cp1252") -> str:
    value = bytes(raw).split(b"\0", 1)[0]
    return value.decode(encoding, "replace").rstrip()


def printable_strings(raw: bytes | memoryview, minimum: int = 4) -> list[str]:
    result: list[str] = []
    current = bytearray()
    for value in bytes(raw) + b"\0":
        if 32 <= value < 127:
            current.append(value)
        else:
            if len(current) >= minimum:
                result.append(current.decode("ascii"))
            current.clear()
    return result


def sha256_bytes(data: bytes | memoryview) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def jdn_to_iso(value: int) -> str | None:
    try:
        return date.fromordinal(value - 1_721_425).isoformat()
    except (ValueError, OverflowError):
        return None


def _ordered_float_bits(value: int) -> int:
    # Convert IEEE-754 bits to an integer whose ordering follows float ordering.
    return (~value & 0xFFFFFFFF) if value & 0x80000000 else value | 0x80000000


def float32_ulp_distance(left: float, right: float) -> int | None:
    if not math.isfinite(left) or not math.isfinite(right):
        return None
    left_bits = struct.unpack("<I", struct.pack("<f", left))[0]
    right_bits = struct.unpack("<I", struct.pack("<f", right))[0]
    return abs(_ordered_float_bits(left_bits) - _ordered_float_bits(right_bits))


def json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    return value
