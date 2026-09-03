from __future__ import annotations

import struct
from datetime import datetime, timezone
from typing import Any

from .errors import FormatError
from .known import DOS_EXECUTABLE_SHA256, WINDOWS_EXECUTABLE_SHA256
from .util import require_range, sha256_bytes, u16, u32


PE_MACHINE_NAMES = {
    0x014C: "i386",
    0x8664: "x86-64",
    0x01C0: "ARM",
    0x01C4: "ARM Thumb-2",
    0xAA64: "ARM64",
}

PE_SUBSYSTEM_NAMES = {
    0: "unknown",
    1: "native",
    2: "Windows GUI",
    3: "Windows console",
    5: "OS/2 console",
    7: "POSIX console",
    9: "Windows CE GUI",
    10: "EFI application",
    11: "EFI boot service driver",
    12: "EFI runtime driver",
    13: "EFI ROM",
    14: "Xbox",
    16: "Windows boot application",
}

PE_CHARACTERISTICS = {
    0x0001: "relocations_stripped",
    0x0002: "executable_image",
    0x0004: "line_numbers_stripped",
    0x0008: "local_symbols_stripped",
    0x0020: "large_address_aware",
    0x0100: "machine_32bit",
    0x0200: "debug_stripped",
    0x1000: "system",
    0x2000: "dll",
}

PE_SECTION_CHARACTERISTICS = {
    0x00000020: "code",
    0x00000040: "initialized_data",
    0x00000080: "uninitialized_data",
    0x02000000: "discardable",
    0x10000000: "shared",
    0x20000000: "execute",
    0x40000000: "read",
    0x80000000: "write",
}

PE_DIRECTORY_NAMES = (
    "export",
    "import",
    "resource",
    "exception",
    "certificate",
    "base_relocation",
    "debug",
    "architecture",
    "global_pointer",
    "thread_local_storage",
    "load_configuration",
    "bound_import",
    "import_address_table",
    "delay_import",
    "clr_runtime",
    "reserved",
)

LE_CPU_NAMES = {
    1: "80286",
    2: "80386",
    3: "80486",
    4: "Pentium",
    0x20: "Intel i860",
    0x21: "Intel N11",
    0x40: "MIPS R2000",
    0x41: "MIPS R6000",
    0x42: "MIPS R4000",
}

LE_OS_NAMES = {
    1: "OS/2",
    2: "Windows",
    3: "DOS 4.x",
    4: "Windows 386",
}

LE_OBJECT_FLAGS = {
    0x0001: "read",
    0x0002: "write",
    0x0004: "execute",
    0x0008: "resource",
    0x0010: "discardable",
    0x0020: "shared",
    0x0040: "preload",
    0x0080: "invalid",
    0x1000: "alias_16_16",
    0x2000: "big_default",
    0x4000: "conforming",
    0x8000: "io_privilege",
}

KNOWN_EXECUTABLES = {
    DOS_EXECUTABLE_SHA256: "Capitalism Plus DOS CAPPLUS.EXE",
    WINDOWS_EXECUTABLE_SHA256: "Capitalism Plus Windows CapWin.exe",
}


def _u8(data: bytes | memoryview, offset: int) -> int:
    require_range(data, offset, 1, "uint8")
    return data[offset]


def _u64(data: bytes | memoryview, offset: int) -> int:
    require_range(data, offset, 8, "uint64")
    return struct.unpack_from("<Q", data, offset)[0]


def _flag_names(value: int, definitions: dict[int, str]) -> list[str]:
    return [name for flag, name in definitions.items() if value & flag]


def _declared_dos_size(pages: int, last_page_bytes: int) -> int:
    if pages == 0:
        return 0
    return pages * 512 if last_page_bytes == 0 else (pages - 1) * 512 + last_page_bytes


def _read_ascii_z(
    data: bytes | memoryview, offset: int, label: str, *, maximum: int = 4096
) -> str:
    require_range(data, offset, 1, label)
    end_limit = min(len(data), offset + maximum)
    end = bytes(data).find(b"\0", offset, end_limit)
    if end < 0:
        raise FormatError(f"unterminated {label}", offset=offset)
    return bytes(data[offset:end]).decode("ascii", "replace")


def _timestamp_iso(value: int) -> str | None:
    if value in {0, 0xFFFFFFFF}:
        return None
    try:
        return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")
    except (OverflowError, OSError, ValueError):
        return None


def _dos_header(data: bytes | memoryview) -> dict[str, Any]:
    require_range(data, 0, 28, "DOS executable header")
    if bytes(data[:2]) not in {b"MZ", b"ZM"}:
        raise FormatError("not an MZ executable", offset=0)
    last_page_bytes = u16(data, 2)
    pages = u16(data, 4)
    result: dict[str, Any] = {
        "signature": bytes(data[:2]).decode("ascii"),
        "bytes_on_last_page": last_page_bytes,
        "pages_in_file": pages,
        "declared_file_size": _declared_dos_size(pages, last_page_bytes),
        "relocation_count": u16(data, 6),
        "header_paragraphs": u16(data, 8),
        "minimum_extra_paragraphs": u16(data, 10),
        "maximum_extra_paragraphs": u16(data, 12),
        "initial_ss": u16(data, 14),
        "initial_sp": u16(data, 16),
        "checksum": u16(data, 18),
        "initial_ip": u16(data, 20),
        "initial_cs": u16(data, 22),
        "relocation_table_offset": u16(data, 24),
        "overlay_number": u16(data, 26),
    }
    if len(data) >= 64:
        result["new_header_offset"] = u32(data, 0x3C)
    return result


def _rva_to_offset(
    rva: int, sections: list[dict[str, Any]], size_of_headers: int, file_size: int
) -> int:
    if rva < size_of_headers:
        if rva >= file_size:
            raise FormatError("header RVA is outside the file", offset=rva)
        return rva
    for section in sections:
        start = section["virtual_address"]
        span = max(section["virtual_size"], section["raw_size"])
        if start <= rva < start + span:
            offset = section["raw_offset"] + (rva - start)
            if offset >= file_size:
                raise FormatError("RVA maps outside the file", offset=offset)
            return offset
    raise FormatError(f"RVA 0x{rva:X} does not map to a section")


def _parse_pe_imports(
    data: bytes | memoryview,
    directory: dict[str, Any] | None,
    sections: list[dict[str, Any]],
    size_of_headers: int,
    *,
    image_base: int,
    pe32_plus: bool,
) -> list[dict[str, Any]]:
    if not directory or directory["rva"] == 0 or directory["size"] == 0:
        return []
    descriptor_offset = _rva_to_offset(
        directory["rva"], sections, size_of_headers, len(data)
    )
    maximum_descriptors = min(4096, max(1, directory["size"] // 20))
    imports: list[dict[str, Any]] = []
    thunk_size = 8 if pe32_plus else 4
    ordinal_mask = 1 << (63 if pe32_plus else 31)
    for descriptor_index in range(maximum_descriptors):
        offset = descriptor_offset + descriptor_index * 20
        require_range(data, offset, 20, "PE import descriptor")
        original_thunk, stamp, forwarder, name_rva, first_thunk = struct.unpack_from(
            "<IIIII", data, offset
        )
        if not any((original_thunk, stamp, forwarder, name_rva, first_thunk)):
            break
        name_offset = _rva_to_offset(name_rva, sections, size_of_headers, len(data))
        library_name = _read_ascii_z(data, name_offset, "PE imported library name", maximum=512)
        thunk_rva = original_thunk or first_thunk
        symbols: list[dict[str, Any]] = []
        if thunk_rva:
            thunk_offset = _rva_to_offset(thunk_rva, sections, size_of_headers, len(data))
            for thunk_index in range(65536):
                entry_offset = thunk_offset + thunk_index * thunk_size
                require_range(data, entry_offset, thunk_size, "PE import thunk")
                value = _u64(data, entry_offset) if pe32_plus else u32(data, entry_offset)
                if value == 0:
                    break
                symbol: dict[str, Any] = {
                    "lookup_table_rva": thunk_rva + thunk_index * thunk_size,
                    "iat_rva": first_thunk + thunk_index * thunk_size,
                    "iat_address": image_base + first_thunk + thunk_index * thunk_size,
                }
                if value & ordinal_mask:
                    symbol["ordinal"] = value & 0xFFFF
                else:
                    hint_name_offset = _rva_to_offset(
                        value, sections, size_of_headers, len(data)
                    )
                    hint = u16(data, hint_name_offset)
                    name = _read_ascii_z(
                        data,
                        hint_name_offset + 2,
                        "PE imported symbol name",
                        maximum=2048,
                    )
                    symbol.update({"name": name, "hint": hint})
                symbols.append(symbol)
            else:
                raise FormatError("PE import thunk table is unreasonably large")
        imports.append(
            {
                "library": library_name,
                "timestamp": stamp,
                "forwarder_chain": forwarder,
                "name_rva": name_rva,
                "original_first_thunk_rva": original_thunk,
                "first_thunk_rva": first_thunk,
                "symbols": symbols,
            }
        )
    else:
        raise FormatError("PE import descriptor table is unreasonably large")
    return imports


def _parse_pe(data: bytes | memoryview, header_offset: int) -> dict[str, Any]:
    require_range(data, header_offset, 24, "PE signature and COFF header")
    if bytes(data[header_offset : header_offset + 4]) != b"PE\0\0":
        raise FormatError("invalid PE signature", offset=header_offset)
    coff_offset = header_offset + 4
    machine, section_count, stamp, symbol_offset, symbol_count, optional_size, flags = (
        struct.unpack_from("<HHIIIHH", data, coff_offset)
    )
    if section_count > 96:
        raise FormatError("PE has more than 96 sections", offset=coff_offset + 2)
    optional_offset = coff_offset + 20
    require_range(data, optional_offset, optional_size, "PE optional header")
    if optional_size < 2:
        raise FormatError("PE optional header is too short", offset=optional_offset)
    optional_magic = u16(data, optional_offset)
    if optional_magic == 0x10B:
        pe32_plus = False
        minimum_optional_size = 96
        directory_offset = optional_offset + 96
        directory_count_offset = optional_offset + 92
        image_base = u32(data, optional_offset + 28)
        base_of_data: int | None = u32(data, optional_offset + 24)
        format_name = "PE32"
    elif optional_magic == 0x20B:
        pe32_plus = True
        minimum_optional_size = 112
        directory_offset = optional_offset + 112
        directory_count_offset = optional_offset + 108
        image_base = _u64(data, optional_offset + 24)
        base_of_data = None
        format_name = "PE32+"
    else:
        raise FormatError(
            f"unsupported PE optional-header magic 0x{optional_magic:04X}",
            offset=optional_offset,
        )
    if optional_size < minimum_optional_size:
        raise FormatError("PE optional header is truncated", offset=optional_offset)

    number_of_directories = u32(data, directory_count_offset)
    available_directories = max(0, (optional_size - (directory_offset - optional_offset)) // 8)
    parsed_directory_count = min(number_of_directories, available_directories, 4096)
    directories: list[dict[str, Any]] = []
    for index in range(parsed_directory_count):
        rva, size = struct.unpack_from("<II", data, directory_offset + index * 8)
        directories.append(
            {
                "index": index,
                "name": PE_DIRECTORY_NAMES[index]
                if index < len(PE_DIRECTORY_NAMES)
                else f"directory_{index}",
                "rva": rva,
                "size": size,
            }
        )

    section_table_offset = optional_offset + optional_size
    require_range(data, section_table_offset, section_count * 40, "PE section table")
    sections: list[dict[str, Any]] = []
    for index in range(section_count):
        offset = section_table_offset + index * 40
        raw_name = bytes(data[offset : offset + 8]).split(b"\0", 1)[0]
        name = raw_name.decode("ascii", "replace")
        virtual_size, virtual_address, raw_size, raw_offset = struct.unpack_from(
            "<IIII", data, offset + 8
        )
        characteristics = u32(data, offset + 36)
        if raw_size:
            require_range(data, raw_offset, raw_size, f"PE section {name!r} raw data")
        sections.append(
            {
                "index": index,
                "name": name,
                "virtual_size": virtual_size,
                "virtual_address": virtual_address,
                "raw_size": raw_size,
                "raw_offset": raw_offset,
                "characteristics": characteristics,
                "characteristic_names": _flag_names(
                    characteristics, PE_SECTION_CHARACTERISTICS
                ),
            }
        )

    size_of_headers = u32(data, optional_offset + 60)
    import_directory = directories[1] if len(directories) > 1 else None
    imports = _parse_pe_imports(
        data,
        import_directory,
        sections,
        size_of_headers,
        image_base=image_base,
        pe32_plus=pe32_plus,
    )
    optional: dict[str, Any] = {
        "magic": optional_magic,
        "linker_version": f"{_u8(data, optional_offset + 2)}.{_u8(data, optional_offset + 3)}",
        "size_of_code": u32(data, optional_offset + 4),
        "size_of_initialized_data": u32(data, optional_offset + 8),
        "size_of_uninitialized_data": u32(data, optional_offset + 12),
        "entry_point_rva": u32(data, optional_offset + 16),
        "base_of_code": u32(data, optional_offset + 20),
        "image_base": image_base,
        "section_alignment": u32(data, optional_offset + 32),
        "file_alignment": u32(data, optional_offset + 36),
        "operating_system_version": f"{u16(data, optional_offset + 40)}.{u16(data, optional_offset + 42)}",
        "image_version": f"{u16(data, optional_offset + 44)}.{u16(data, optional_offset + 46)}",
        "subsystem_version": f"{u16(data, optional_offset + 48)}.{u16(data, optional_offset + 50)}",
        "size_of_image": u32(data, optional_offset + 56),
        "size_of_headers": size_of_headers,
        "checksum": u32(data, optional_offset + 64),
        "subsystem": u16(data, optional_offset + 68),
        "subsystem_name": PE_SUBSYSTEM_NAMES.get(
            u16(data, optional_offset + 68), "unrecognized"
        ),
        "dll_characteristics": u16(data, optional_offset + 70),
        "declared_data_directory_count": number_of_directories,
    }
    if base_of_data is not None:
        optional["base_of_data"] = base_of_data

    return {
        "format": format_name,
        "header_offset": header_offset,
        "machine": machine,
        "machine_name": PE_MACHINE_NAMES.get(machine, "unrecognized"),
        "section_count": section_count,
        "timestamp": stamp,
        "timestamp_iso_utc": _timestamp_iso(stamp),
        "symbol_table_offset": symbol_offset,
        "symbol_count": symbol_count,
        "optional_header_size": optional_size,
        "characteristics": flags,
        "characteristic_names": _flag_names(flags, PE_CHARACTERISTICS),
        "optional_header": optional,
        "data_directories": directories,
        "sections": sections,
        "imports": imports,
        "imported_library_count": len(imports),
        "imported_symbol_count": sum(len(item["symbols"]) for item in imports),
    }


def _parse_length_prefixed_names(
    data: bytes | memoryview,
    offset: int,
    count: int,
    label: str,
) -> list[str]:
    if count > 65535:
        raise FormatError(f"{label} count is unreasonable")
    names: list[str] = []
    cursor = offset
    for _ in range(count):
        length = _u8(data, cursor)
        cursor += 1
        require_range(data, cursor, length, label)
        names.append(bytes(data[cursor : cursor + length]).decode("ascii", "replace"))
        cursor += length
    return names


def _parse_le_name_table(
    data: bytes | memoryview, offset: int, label: str, *, maximum_size: int | None = None
) -> list[dict[str, Any]]:
    if offset == 0:
        return []
    require_range(data, offset, 1, label)
    limit = len(data) if maximum_size is None else min(len(data), offset + maximum_size)
    entries: list[dict[str, Any]] = []
    cursor = offset
    for _ in range(65536):
        if cursor >= limit:
            break
        length = _u8(data, cursor)
        cursor += 1
        if length == 0:
            return entries
        if cursor + length + 2 > limit:
            raise FormatError(f"truncated {label}", offset=cursor - 1)
        name = bytes(data[cursor : cursor + length]).decode("ascii", "replace")
        cursor += length
        ordinal = u16(data, cursor)
        cursor += 2
        entries.append({"name": name, "ordinal": ordinal})
    if len(entries) == 65536:
        raise FormatError(f"{label} is unreasonably large")
    return entries


def _parse_le(data: bytes | memoryview, header_offset: int) -> dict[str, Any]:
    require_range(data, header_offset, 0xC4, "LE header")
    if bytes(data[header_offset : header_offset + 2]) != b"LE":
        raise FormatError("invalid LE signature", offset=header_offset)

    def field(relative_offset: int) -> int:
        return u32(data, header_offset + relative_offset)

    cpu = u16(data, header_offset + 8)
    target_os = u16(data, header_offset + 10)
    object_table_offset = field(0x40)
    object_count = field(0x44)
    if object_count > 65535:
        raise FormatError("LE object count is unreasonable", offset=header_offset + 0x44)
    object_table_file_offset = header_offset + object_table_offset
    require_range(data, object_table_file_offset, object_count * 24, "LE object table")
    objects: list[dict[str, Any]] = []
    for index in range(object_count):
        offset = object_table_file_offset + index * 24
        virtual_size, base_address, flags, page_map_index, page_count, reserved = (
            struct.unpack_from("<IIIIII", data, offset)
        )
        objects.append(
            {
                "index": index + 1,
                "virtual_size": virtual_size,
                "base_address": base_address,
                "flags": flags,
                "flag_names": _flag_names(flags, LE_OBJECT_FLAGS),
                "page_map_index": page_map_index,
                "page_count": page_count,
                "reserved": reserved,
            }
        )

    module_page_count = field(0x14)
    page_size = field(0x28)
    last_page_size = field(0x2C)
    page_map_offset = field(0x48)
    data_pages_offset = field(0x80)
    if module_page_count > 1_000_000:
        raise FormatError("LE page count is unreasonable", offset=header_offset + 0x14)
    if module_page_count and page_size == 0:
        raise FormatError("LE page size is zero", offset=header_offset + 0x28)
    if page_size and last_page_size > page_size:
        raise FormatError(
            "LE last-page size exceeds the page size", offset=header_offset + 0x2C
        )
    page_map_file_offset = header_offset + page_map_offset
    require_range(
        data,
        page_map_file_offset,
        module_page_count * 4,
        "LE object page map",
    )
    pages: list[dict[str, Any]] = []
    for index in range(module_page_count):
        offset = page_map_file_offset + index * 4
        data_page_number = int.from_bytes(bytes(data[offset : offset + 3]), "big")
        if data_page_number > module_page_count:
            raise FormatError("LE data-page number is out of range", offset=offset)
        flags = _u8(data, offset + 3)
        file_offset = (
            data_pages_offset + (data_page_number - 1) * page_size
            if data_page_number
            else None
        )
        stored_size = (
            last_page_size
            if data_page_number == module_page_count and last_page_size
            else page_size
        )
        if file_offset is not None:
            require_range(data, file_offset, stored_size, "LE data page")
        pages.append(
            {
                "index": index + 1,
                "data_page_number": data_page_number,
                "flags": flags,
                "file_offset": file_offset,
                "stored_size": stored_size if file_offset is not None else 0,
            }
        )

    for item in objects:
        if item["page_count"] == 0:
            item["pages"] = []
            item["raw_offset"] = None
            item["stored_size"] = 0
            continue
        first = item["page_map_index"] - 1
        count = item["page_count"]
        if first < 0 or first + count > len(pages):
            raise FormatError("LE object page range is invalid")
        object_pages = pages[first : first + count]
        item["pages"] = object_pages
        offsets = [page["file_offset"] for page in object_pages]
        item["raw_offset"] = offsets[0] if offsets and offsets[0] is not None else None
        item["stored_size"] = sum(page["stored_size"] for page in object_pages)

    imported_module_offset = field(0x70)
    imported_module_count = field(0x74)
    imported_modules = (
        _parse_length_prefixed_names(
            data,
            header_offset + imported_module_offset,
            imported_module_count,
            "LE imported module table",
        )
        if imported_module_count
        else []
    )
    resident_offset = field(0x58)
    resident_names = (
        _parse_le_name_table(
            data, header_offset + resident_offset, "LE resident name table"
        )
        if resident_offset
        else []
    )
    nonresident_offset = field(0x88)
    nonresident_size = field(0x8C)
    nonresident_names = (
        _parse_le_name_table(
            data,
            nonresident_offset,
            "LE non-resident name table",
            maximum_size=nonresident_size,
        )
        if nonresident_offset and nonresident_size
        else []
    )

    return {
        "format": "LE",
        "header_offset": header_offset,
        "byte_order": _u8(data, header_offset + 2),
        "word_order": _u8(data, header_offset + 3),
        "format_level": field(0x04),
        "cpu": cpu,
        "cpu_name": LE_CPU_NAMES.get(cpu, "unrecognized"),
        "target_os": target_os,
        "target_os_name": LE_OS_NAMES.get(target_os, "unrecognized"),
        "module_version": field(0x0C),
        "module_flags": field(0x10),
        "module_page_count": module_page_count,
        "entry_object": field(0x18),
        "entry_offset": field(0x1C),
        "stack_object": field(0x20),
        "initial_stack_pointer": field(0x24),
        "page_size": page_size,
        "bytes_on_last_page": last_page_size,
        "fixup_section_size": field(0x30),
        "loader_section_size": field(0x38),
        "object_table_offset": object_table_offset,
        "object_page_map_offset": page_map_offset,
        "resource_table_offset": field(0x50),
        "resource_count": field(0x54),
        "resident_name_table_offset": resident_offset,
        "entry_table_offset": field(0x5C),
        "fixup_page_table_offset": field(0x68),
        "fixup_record_table_offset": field(0x6C),
        "imported_module_table_offset": imported_module_offset,
        "imported_module_count": imported_module_count,
        "imported_procedure_table_offset": field(0x78),
        "data_pages_offset": data_pages_offset,
        "preload_page_count": field(0x84),
        "nonresident_name_table_offset": nonresident_offset,
        "nonresident_name_table_size": nonresident_size,
        "automatic_data_object": field(0x94),
        "debug_info_offset": field(0x98),
        "debug_info_size": field(0x9C),
        "extra_heap_allocation": field(0xA8),
        "object_count": object_count,
        "objects": objects,
        "pages": pages,
        "imported_modules": imported_modules,
        "resident_names": resident_names,
        "nonresident_names": nonresident_names,
    }


def extract_executable_strings(
    data: bytes | memoryview, *, minimum_length: int = 5
) -> list[dict[str, Any]]:
    if minimum_length < 1:
        raise ValueError("minimum string length must be positive")
    raw = bytes(data)
    strings: list[dict[str, Any]] = []

    start: int | None = None
    for offset, value in enumerate(raw + b"\0"):
        if 32 <= value <= 126:
            if start is None:
                start = offset
        elif start is not None:
            if offset - start >= minimum_length:
                strings.append(
                    {
                        "offset": start,
                        "encoding": "ascii",
                        "text": raw[start:offset].decode("ascii"),
                    }
                )
            start = None

    for parity in (0, 1):
        cursor = parity
        while cursor + 1 < len(raw):
            start = cursor
            chars = bytearray()
            while cursor + 1 < len(raw) and 32 <= raw[cursor] <= 126 and raw[cursor + 1] == 0:
                chars.append(raw[cursor])
                cursor += 2
            if len(chars) >= minimum_length:
                strings.append(
                    {
                        "offset": start,
                        "encoding": "utf-16le",
                        "text": chars.decode("ascii"),
                    }
                )
            cursor = max(cursor + 2, start + 2)

    strings.sort(key=lambda item: (item["offset"], item["encoding"], item["text"]))
    return strings


def inspect_executable(
    data: bytes | memoryview,
    *,
    include_strings: bool = False,
    minimum_string_length: int = 5,
) -> dict[str, Any]:
    if minimum_string_length < 1:
        raise FormatError("minimum string length must be positive")
    digest = sha256_bytes(data)
    dos = _dos_header(data)
    new_header_offset = dos.get("new_header_offset", 0)
    signature = b""
    if new_header_offset and new_header_offset < len(data):
        signature = bytes(data[new_header_offset : new_header_offset + 4])

    result: dict[str, Any] = {
        "schema_version": 1,
        "format": "capitalism_plus_executable",
        "size": len(data),
        "sha256": digest,
        "recognized_unmodified": digest in KNOWN_EXECUTABLES,
        "recognized_build": KNOWN_EXECUTABLES.get(digest),
        "dos_header": dos,
    }
    if signature == b"PE\0\0":
        result["executable_format"] = "PE"
        result["pe"] = _parse_pe(data, new_header_offset)
    elif signature[:2] == b"LE":
        result["executable_format"] = "LE"
        result["le"] = _parse_le(data, new_header_offset)
    elif signature[:2] == b"LX":
        result["executable_format"] = "LX"
        result["new_header_signature"] = "LX"
    elif signature[:2] == b"NE":
        result["executable_format"] = "NE"
        result["new_header_signature"] = "NE"
    else:
        result["executable_format"] = "MZ"
        result["new_header_signature"] = signature[:4].hex() if signature else None

    result["recognized_new_header"] = result["executable_format"] in {
        "PE",
        "LE",
        "LX",
        "NE",
    }

    strings = extract_executable_strings(data, minimum_length=minimum_string_length)
    result["string_summary"] = {
        "minimum_length": minimum_string_length,
        "ascii_count": sum(item["encoding"] == "ascii" for item in strings),
        "utf16le_count": sum(item["encoding"] == "utf-16le" for item in strings),
    }
    if include_strings:
        result["strings"] = strings
    return result
