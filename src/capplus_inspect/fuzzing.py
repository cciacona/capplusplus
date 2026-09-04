from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from typing import Any

from . import SCHEMA_VERSION
from .errors import InspectError
from .file_formats import inspect_file_bytes
from .roundtrip import validate_roundtrip_bytes
from .saves import FIXED_PAYLOAD_SIZES, SECTION_MARKERS


DEFAULT_FUZZ_SEED = 0x4341502B2B
DEFAULT_FUZZ_ITERATIONS = 512
MAX_FUZZ_ITERATIONS = 1_000_000
MAX_FUZZ_INPUT_SIZE = 2 * 1024 * 1024


@dataclass(frozen=True)
class FuzzCase:
    name: str
    data: bytes


class FuzzFailure(InspectError):
    pass


def _named_container(members: list[tuple[str, bytes]]) -> bytes:
    header_size = 2 + (len(members) + 1) * 13
    offsets = []
    current = header_size
    for _, payload in members:
        offsets.append(current)
        current += len(payload)
    offsets.append(current)
    output = bytearray(struct.pack("<H", len(members)))
    for index, (name, _) in enumerate(members):
        encoded = name.encode("ascii")[:8]
        output.extend(encoded + bytes(9 - len(encoded)))
        output.extend(struct.pack("<I", offsets[index]))
    output.extend(bytes(9) + struct.pack("<I", offsets[-1]))
    output.extend(b"".join(payload for _, payload in members))
    return bytes(output)


def _offset_container(members: list[bytes]) -> bytes:
    header_size = 2 + (len(members) + 1) * 4
    offsets = []
    current = header_size
    for payload in members:
        offsets.append(current)
        current += len(payload)
    offsets.append(current)
    return (
        struct.pack("<H", len(members))
        + b"".join(struct.pack("<I", offset) for offset in offsets)
        + b"".join(members)
    )


def _dbf() -> bytes:
    header_length = 65
    record_length = 5
    header = bytearray(32)
    header[0:4] = bytes((0x03, 97, 4, 11))
    struct.pack_into("<IHH", header, 4, 1, header_length, record_length)
    descriptor = bytearray(32)
    descriptor[:5] = b"VALUE"
    descriptor[11] = ord("C")
    descriptor[16] = 4
    return bytes(header + descriptor + b"\r" + b" TEST" + b"\x1a")


def _palette() -> bytes:
    colors = bytes(value for index in range(256) for value in (index, index, index))
    return struct.pack("<II", 776, 0) + colors


def _font() -> bytes:
    header = bytearray(88)
    struct.pack_into("<HH", header, 0x24, 65, 65)
    struct.pack_into("<HH", header, 0x50, 1, 1)
    return bytes(header + struct.pack("<HH", 0, 1) + b"\x80")


def _layout_plan() -> bytes:
    array_header = bytearray(29)
    struct.pack_into("<iiiiii", array_header, 0, 1, 1, 0, 1, 127, 0)
    record = bytearray(127)
    record[:10] = b"Test Plan\0"
    struct.pack_into("<H", record, 29, 1)
    references = b"ITEM\0\0\0\0" * 9
    return struct.pack("<H", 1) + b"SHOP" + bytes(array_header + record + references)


def _minimal_save() -> bytes:
    metadata = bytearray(100)
    metadata[:12] = b"TEST_001.SAV"
    struct.pack_into("<I", metadata, 16, 2_447_893)
    metadata[20:32] = b"Test Company"
    metadata[68:81] = b"Test Scenario"
    settings = b"TEST.SCT\0"
    output = bytearray(struct.pack("<H", len(metadata)))
    output.extend(metadata)
    output.extend(struct.pack("<hH", 100, len(settings)))
    output.extend(settings)
    for marker in SECTION_MARKERS:
        output.extend(struct.pack("<H", marker))
        if marker == 0x1001:
            payload = struct.pack("<I", 0x12345678)
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
        output.extend(payload)
    return bytes(output)


def synthetic_fuzz_cases() -> tuple[FuzzCase, ...]:
    """Return small redistributable inputs that exercise every parser family."""

    direct_image = struct.pack("<HH", 1, 1) + b"\x07"
    sequential_image = struct.pack("<I", len(direct_image)) + direct_image
    text_screen = bytes((32, 0x07)) * (80 * 25)
    cursor_dbf = _cursor_dbf()
    return (
        FuzzCase("TEST.SET", _named_container([("TABLE", _dbf())])),
        FuzzCase("TEST.MAP", bytes(380_244)),
        FuzzCase("PAL_STD.RES", _palette()),
        FuzzCase("FNT_STD.RES", _font()),
        FuzzCase("TEXT.RES", _offset_container([text_screen])),
        FuzzCase("LANGUAGE.RES", _offset_container([direct_image])),
        FuzzCase("I_CURSOR.RES", sequential_image),
        FuzzCase("CURSOR.RES", cursor_dbf),
        FuzzCase(
            "HELP.RES",
            _named_container([("MAIN", b"Title\r\n-----\r\n0,0,1,1\r\nLabel\r\nText\x1a")]),
        ),
        FuzzCase("TEST.PLA", _layout_plan()),
        FuzzCase("CAPITAL.CFG", struct.pack("<H", 737) + bytes(737)),
        FuzzCase(
            "CAPITAL.HOF",
            struct.pack("<H", 580) + bytes(580) + struct.pack("<H", 13) + bytes(13),
        ),
        FuzzCase("IMAGE.PIC", direct_image),
        FuzzCase("GENERIC.RES", _named_container([("IMAGE", direct_image)])),
        FuzzCase("TEST.SAV", _minimal_save()),
        FuzzCase("TEST.EXE", b"MZ" + bytes(62)),
    )


def _cursor_dbf() -> bytes:
    fields = (
        ("FILENAME", "C", 8),
        ("HOTSPOT_X", "N", 3),
        ("HOTSPOT_Y", "N", 3),
        ("BITMAPPTR", "C", 4),
    )
    header_length = 32 + len(fields) * 32 + 1
    record_length = 1 + sum(field[2] for field in fields)
    header = bytearray(32)
    header[0:4] = bytes((0x03, 97, 4, 11))
    struct.pack_into("<IHH", header, 4, 1, header_length, record_length)
    descriptors = bytearray()
    for name, field_type, length in fields:
        descriptor = bytearray(32)
        encoded = name.encode("ascii")
        descriptor[: len(encoded)] = encoded
        descriptor[11] = ord(field_type)
        descriptor[16] = length
        descriptors.extend(descriptor)
    record = b" " + b"ARROW   " + b"  0" + b"  0" + b"    "
    return bytes(header + descriptors + b"\r" + record + b"\x1a")


def _mutation_material(seed: int, case_name: str, iteration: int) -> bytes:
    return hashlib.sha256(f"{seed}:{case_name}:{iteration}".encode("ascii")).digest()


def mutate_bytes(data: bytes, *, seed: int, case_name: str, iteration: int) -> tuple[str, bytes]:
    """Apply one bounded mutation chosen entirely from a stable SHA-256 digest."""

    material = _mutation_material(seed, case_name, iteration)
    operation = material[0] % 7
    position = int.from_bytes(material[1:9], "little") % max(1, len(data))
    span = 1 + material[9] % 16
    value = material[10]
    mutated = bytearray(data)

    if operation == 0:
        if mutated:
            mutated[position] ^= 1 << (material[11] % 8)
        else:
            mutated.append(value)
        name = "bit_flip"
    elif operation == 1:
        del mutated[position:]
        name = "truncate"
    elif operation == 2:
        end = min(len(mutated), position + span)
        mutated[position:end] = bytes((value,)) * (end - position)
        name = "fill_span"
    elif operation == 3:
        del mutated[position : min(len(mutated), position + span)]
        name = "delete_span"
    elif operation == 4:
        payload = material[12 : 12 + min(span, 16)]
        if len(mutated) + len(payload) <= MAX_FUZZ_INPUT_SIZE:
            mutated[position:position] = payload
        name = "insert_span"
    elif operation == 5:
        end = min(len(mutated), position + 4)
        mutated[position:end] = b"\xff" * (end - position)
        name = "max_length_word"
    else:
        end = min(len(mutated), position + span)
        chunk = bytes(mutated[position:end])
        if len(mutated) + len(chunk) <= MAX_FUZZ_INPUT_SIZE:
            mutated[end:end] = chunk
        name = "duplicate_span"
    return name, bytes(mutated)


def run_synthetic_fuzz_campaign(
    *,
    iterations: int = DEFAULT_FUZZ_ITERATIONS,
    seed: int = DEFAULT_FUZZ_SEED,
) -> dict[str, Any]:
    if not 1 <= iterations <= MAX_FUZZ_ITERATIONS:
        raise ValueError(f"iterations must be between 1 and {MAX_FUZZ_ITERATIONS}")
    if seed < 0:
        raise ValueError("seed must be non-negative")

    cases = synthetic_fuzz_cases()
    for case in cases:
        inspect_file_bytes(case.data, case.name)
        if not case.name.lower().endswith(".sav"):
            validate_roundtrip_bytes(case.data, case.name)

    stats = {
        case.name: {"iterations": 0, "accepted": 0, "rejected": 0}
        for case in cases
    }
    transcript = hashlib.sha256()
    accepted = 0
    rejected = 0
    for iteration in range(iterations):
        case = cases[iteration % len(cases)]
        mutation_name, mutated = mutate_bytes(
            case.data,
            seed=seed,
            case_name=case.name,
            iteration=iteration,
        )
        outcome = "accepted"
        try:
            inspect_file_bytes(mutated, case.name)
            if not case.name.lower().endswith(".sav"):
                validate_roundtrip_bytes(mutated, case.name)
        except InspectError:
            outcome = "rejected"
        except Exception as error:
            raise FuzzFailure(
                f"unexpected {type(error).__name__} for case {case.name}, seed {seed}, "
                f"iteration {iteration}, mutation {mutation_name}: {error}"
            ) from error

        case_stats = stats[case.name]
        case_stats["iterations"] += 1
        case_stats[outcome] += 1
        accepted += outcome == "accepted"
        rejected += outcome == "rejected"
        transcript.update(
            f"{iteration}:{case.name}:{mutation_name}:{len(mutated)}:{outcome}\n".encode("ascii")
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "format": "capitalism_plus_fuzz_campaign",
        "generator": "sha256_bounded_mutations_v1",
        "seed": seed,
        "seed_hex": f"0x{seed:X}",
        "iterations": iterations,
        "case_count": len(cases),
        "accepted": accepted,
        "rejected": rejected,
        "unexpected_failures": 0,
        "transcript_sha256": transcript.hexdigest(),
        "cases": [
            {"filename": case.name, "source_size": len(case.data), **stats[case.name]}
            for case in cases
        ],
    }
