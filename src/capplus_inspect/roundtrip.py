from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from . import SCHEMA_VERSION
from .containers import (
    inspect_set,
    parse_named_index,
    parse_offset_index,
    parse_sequential_images,
)
from .dbf import inspect_dbf
from .errors import FormatError
from .executables import inspect_executable
from .file_formats import inspect_auxiliary_file
from .fonts import FONT_HEADER_SIZE, inspect_font
from .installation import _DirectorySource, _Source, _ZipSource, _canonical_files
from .known import CORE_FILE_SHA256
from .maps import (
    CITY_RECORD_SIZE,
    MAP_CORE_SIZE,
    MAP_FOOTER_SIZE,
    MAP_GRID_SIZE,
    MAP_HEADER_SIZE,
    inspect_map,
)
from .palette import PALETTE_HEADER_SIZE, inspect_palette
from .plans import (
    PLAN_ARRAY_HEADER_SIZE,
    PLAN_RECORD_SIZE,
    PLAN_REFERENCE_SIZE,
    inspect_layout_plan,
)
from .support_files import inspect_configuration, inspect_hall_of_fame
from .ui_resources import (
    inspect_cursor_images,
    inspect_cursor_table,
    inspect_help,
    inspect_language_glyphs,
    inspect_text_screens,
)
from .util import sha256_bytes, u16


@dataclass(frozen=True)
class RoundTripRegion:
    name: str
    offset: int
    data: bytes

    def report(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "offset": self.offset,
            "size": len(self.data),
            "sha256": sha256_bytes(self.data),
        }


@dataclass(frozen=True)
class RoundTripDocument:
    source_format: str
    coverage: str
    source_size: int
    regions: tuple[RoundTripRegion, ...]

    def encode(self) -> bytes:
        expected_offset = 0
        output = bytearray()
        for region in self.regions:
            if region.offset != expected_offset:
                raise FormatError(
                    f"round-trip region {region.name!r} starts at {region.offset}; "
                    f"expected {expected_offset}",
                    offset=region.offset,
                )
            output.extend(region.data)
            expected_offset += len(region.data)
        if expected_offset != self.source_size:
            raise FormatError(
                f"round-trip regions cover {expected_offset} of {self.source_size} bytes",
                offset=expected_offset,
            )
        return bytes(output)


def _region(data: bytes, name: str, start: int, end: int) -> RoundTripRegion:
    if not 0 <= start <= end <= len(data):
        raise FormatError(f"round-trip region {name!r} is outside the input", offset=start)
    return RoundTripRegion(name=name, offset=start, data=data[start:end])


def _document(
    data: bytes,
    source_format: str,
    regions: Iterable[RoundTripRegion],
    *,
    coverage: str = "structural",
) -> RoundTripDocument:
    document = RoundTripDocument(source_format, coverage, len(data), tuple(regions))
    document.encode()
    return document


def _indexed_document(
    data: bytes,
    source_format: str,
    entries: list[dict[str, Any]],
    *,
    named: bool,
) -> RoundTripDocument:
    first_offset = entries[0]["offset"]
    regions = [_region(data, "directory", 0, first_offset)]
    for entry in entries:
        label = entry.get("name") if named else None
        name = f"member[{entry['index']}]" + (f":{label}" if label else "")
        start = entry["offset"]
        regions.append(_region(data, name, start, start + entry["size"]))
    return _document(data, source_format, regions)


def _sequential_document(
    data: bytes, source_format: str, entries: list[dict[str, Any]]
) -> RoundTripDocument:
    return _document(
        data,
        source_format,
        (
            _region(
                data,
                f"image[{entry['index']}]",
                entry["offset"],
                entry["offset"] + 4 + entry["record_size"],
            )
            for entry in entries
        ),
    )


def _dbf_document(data: bytes, source_format: str = "dbase") -> RoundTripDocument:
    info = inspect_dbf(data)
    header_end = info["header_length"]
    record_size = info["record_length"]
    regions = [_region(data, "header_and_descriptors", 0, header_end)]
    for index in range(info["record_count"]):
        start = header_end + index * record_size
        regions.append(_region(data, f"record[{index}]", start, start + record_size))
    records_end = header_end + info["record_count"] * record_size
    if records_end < len(data):
        regions.append(_region(data, "trailing_bytes", records_end, len(data)))
    return _document(data, source_format, regions)


def _resource_document(data: bytes, filename: str) -> RoundTripDocument:
    result = inspect_auxiliary_file(data, filename)
    source_format = result["format"]
    audio_family = result.get("audio_family")
    if audio_family or source_format in {"capitalism_plus_pcm_wave", "capitalism_plus_xmidi", "capitalism_plus_sound_settings"}:
        boundaries = {0, len(data)}

        def chunk_boundaries(chunks: list[dict[str, Any]], base: int = 0) -> None:
            for chunk in chunks:
                start, end = base + chunk["data_offset"], base + chunk["data_offset"] + chunk["size"]
                boundaries.update((base + chunk["offset"], start, end, end + chunk["padding_size"]))
                if "group_type" in chunk:
                    boundaries.add(start + 4)

        if audio_family:
            source_format = "capitalism_plus_" + audio_family
            for member in result["members"]:
                boundaries.update((member["offset"], member["offset"] + member["size"]))
                if audio_family == "music_bank":
                    chunk_boundaries(member["audio"]["xmidi"]["chunks"], member["offset"])
        elif source_format in {"capitalism_plus_pcm_wave", "capitalism_plus_xmidi"}:
            if source_format == "capitalism_plus_pcm_wave":
                boundaries.add(12)
            chunk_boundaries(result["chunks"])
        else:
            boundaries.update(range(0, 19, 2))
        ordered = sorted(boundaries)
        return _document(data, source_format, (_region(data, f"audio_part[{i}]", start, end)
                         for i, (start, end) in enumerate(zip(ordered, ordered[1:]))))
    if source_format == "capitalism_plus_palette":
        inspect_palette(data)
        return _document(
            data,
            source_format,
            (
                _region(data, "header", 0, PALETTE_HEADER_SIZE),
                _region(data, "rgb_table", PALETTE_HEADER_SIZE, len(data)),
            ),
        )
    if source_format == "capitalism_plus_bitmap_font":
        info = inspect_font(data)
        bitmap_offset = info["bitmap_offset"]
        return _document(
            data,
            source_format,
            (
                _region(data, "header", 0, FONT_HEADER_SIZE),
                _region(data, "glyph_boundaries", FONT_HEADER_SIZE, bitmap_offset),
                _region(data, "packed_bitmap", bitmap_offset, len(data)),
            ),
        )
    if source_format == "capitalism_plus_text_screens":
        inspect_text_screens(data)
        entries = parse_offset_index(data)
        assert entries is not None
        return _indexed_document(data, source_format, entries, named=False)
    if source_format == "capitalism_plus_language_glyphs":
        inspect_language_glyphs(data)
        entries = parse_offset_index(data)
        assert entries is not None
        return _indexed_document(data, source_format, entries, named=False)
    if source_format == "capitalism_plus_cursor_images":
        inspect_cursor_images(data)
        entries = parse_sequential_images(data)
        assert entries is not None
        return _sequential_document(data, source_format, entries)
    if source_format == "capitalism_plus_cursor_table":
        inspect_cursor_table(data)
        return _dbf_document(data, source_format)
    if source_format == "capitalism_plus_context_help":
        inspect_help(data)
        entries = parse_named_index(data)
        assert entries is not None
        return _indexed_document(data, source_format, entries, named=True)
    if source_format == "capitalism_plus_layout_plans":
        return _layout_plan_document(data)
    if source_format == "capitalism_plus_configuration":
        info = inspect_configuration(data)
        physical_size = info["record"]["physical_size"]
        return _document(
            data,
            source_format,
            (
                _region(data, "record_size", 0, 2),
                _region(data, "record_payload", 2, 2 + physical_size),
            ),
        )
    if source_format == "capitalism_plus_hall_of_fame":
        inspect_hall_of_fame(data)
        first_size = u16(data, 0) or 580
        first_end = 2 + first_size
        second_size = u16(data, first_end) or 13
        return _document(
            data,
            source_format,
            (
                _region(data, "leaderboard_size", 0, 2),
                _region(data, "leaderboard_payload", 2, first_end),
                _region(data, "save_name_size", first_end, first_end + 2),
                _region(data, "save_name_payload", first_end + 2, first_end + 2 + second_size),
            ),
        )
    if source_format == "named_container":
        entries = parse_named_index(data)
        assert entries is not None
        return _indexed_document(data, source_format, entries, named=True)
    if source_format == "offset_container":
        entries = parse_offset_index(data)
        assert entries is not None
        return _indexed_document(data, source_format, entries, named=False)
    if source_format == "sequential_images":
        entries = parse_sequential_images(data)
        assert entries is not None
        return _sequential_document(data, source_format, entries)
    if source_format == "raw":
        kind = result.get("kind")
        if kind == "dbase":
            return _dbf_document(data)
        if kind == "indexed_image":
            return _document(
                data,
                "direct_indexed_image",
                (
                    _region(data, "dimensions", 0, 4),
                    _region(data, "pixels", 4, len(data)),
                ),
            )
        return _document(
            data,
            "raw_binary",
            (_region(data, "opaque_bytes", 0, len(data)),),
            coverage="opaque",
        )
    raise FormatError(f"round-trip support is missing for {source_format!r}")


def _layout_plan_document(data: bytes) -> RoundTripDocument:
    info = inspect_layout_plan(data)
    regions = [_region(data, "category_count", 0, 2)]
    for category in info["categories"]:
        index = category["index"]
        start = category["offset"]
        records_start = category["raw_records_offset"]
        references_start = category["stable_references_offset"]
        record_count = category["array_header"]["record_count"]
        end = references_start + record_count * PLAN_REFERENCE_SIZE
        if records_start - start != 4 + PLAN_ARRAY_HEADER_SIZE:
            raise FormatError("layout-plan category header has an unexpected size", offset=start)
        if references_start - records_start != record_count * PLAN_RECORD_SIZE:
            raise FormatError(
                "layout-plan record block has an unexpected size", offset=records_start
            )
        regions.append(_region(data, f"category[{index}].header", start, records_start))
        if records_start < references_start:
            regions.append(
                _region(data, f"category[{index}].records", records_start, references_start)
            )
        if references_start < end:
            regions.append(
                _region(data, f"category[{index}].stable_references", references_start, end)
            )
    return _document(data, "capitalism_plus_layout_plans", regions)


def build_roundtrip_document(data: bytes, filename: str) -> RoundTripDocument:
    """Parse an original file into exhaustive immutable structural regions."""

    normalized = filename.replace("\\", "/")
    basename = normalized.rsplit("/", 1)[-1]
    suffix = Path(basename).suffix.lower()
    if suffix == ".sav":
        raise FormatError(
            "save files use the normalization comparator and have no original-format writer"
        )
    if suffix == ".exe":
        info = inspect_executable(data)
        new_offset = info["dos_header"].get("new_header_offset", 0)
        if info["recognized_new_header"] and 0 < new_offset < len(data):
            return _document(
                data,
                "capitalism_plus_executable",
                (
                    _region(data, "mz_header_and_stub", 0, new_offset),
                    _region(data, "new_format_image", new_offset, len(data)),
                ),
            )
        return _document(
            data,
            "capitalism_plus_executable",
            (_region(data, "mz_image", 0, len(data)),),
        )
    if suffix == ".set":
        inspect_set(data)
        entries = parse_named_index(data)
        assert entries is not None
        return _indexed_document(data, "capitalism_plus_game_set", entries, named=True)
    if suffix == ".map":
        info = inspect_map(data)
        grid_end = MAP_HEADER_SIZE + MAP_GRID_SIZE
        regions = [
            _region(data, "header", 0, MAP_HEADER_SIZE),
            _region(data, "cell_grid", MAP_HEADER_SIZE, grid_end),
            _region(data, "footer", grid_end, MAP_CORE_SIZE),
        ]
        if MAP_CORE_SIZE - grid_end != MAP_FOOTER_SIZE:
            raise AssertionError("map region constants disagree")
        for city in info["cities"]:
            start = city["offset"]
            regions.append(
                _region(data, f"city[{city['index']}]", start, start + CITY_RECORD_SIZE)
            )
        return _document(data, "capitalism_plus_map", regions)
    return _resource_document(data, normalized)


def validate_roundtrip_bytes(data: bytes, filename: str) -> dict[str, Any]:
    document = build_roundtrip_document(data, filename)
    rebuilt = document.encode()
    source_digest = sha256_bytes(data)
    rebuilt_digest = sha256_bytes(rebuilt)
    exact = rebuilt == data
    if not exact:
        mismatch = next(
            (index for index, (left, right) in enumerate(zip(data, rebuilt)) if left != right),
            min(len(data), len(rebuilt)),
        )
        raise FormatError("round-trip reconstruction differs from input", offset=mismatch)
    return {
        "schema_version": SCHEMA_VERSION,
        "format": "capitalism_plus_roundtrip_validation",
        "filename": filename,
        "source_format": document.source_format,
        "coverage": document.coverage,
        "size": len(data),
        "source_sha256": source_digest,
        "reconstructed_sha256": rebuilt_digest,
        "byte_identical": exact,
        "region_count": len(document.regions),
        "regions": [region.report() for region in document.regions],
    }


def _open_source(path: Path) -> _Source:
    if path.is_dir():
        return _DirectorySource(path)
    if path.is_file() and zipfile.is_zipfile(path):
        return _ZipSource(path)
    if path.is_file():
        raise FormatError("round-trip corpus input must be a directory or ZIP archive")
    raise FormatError("round-trip corpus path does not exist")


def _corpus_paths(files: dict[str, str]) -> list[str]:
    paths = set(CORE_FILE_SHA256) & set(files)
    paths.update(
        name
        for name in ("capplus.exe", "capwin.exe", "capital.cfg", "capital.hof", "capital.snd")
        if name in files
    )
    paths.update(name for name in files if name.startswith("sounds/"))
    return sorted(paths)


def validate_roundtrip_corpus(path: str | Path) -> dict[str, Any]:
    """Round-trip all currently supported non-save files in an installation."""

    input_path = Path(path)
    source = _open_source(input_path)
    try:
        root, files = _canonical_files(source)
        selected = _corpus_paths(files)
        if not selected:
            raise FormatError("installation contains no supported round-trip files")
        reports = [
            validate_roundtrip_bytes(source.read(files[canonical]), canonical)
            for canonical in selected
        ]
    finally:
        source.close()

    return {
        "schema_version": SCHEMA_VERSION,
        "format": "capitalism_plus_roundtrip_corpus",
        "input": str(input_path.resolve()),
        "source_kind": source.kind,
        "detected_root": root,
        "file_count": len(reports),
        "structural_count": sum(report["coverage"] == "structural" for report in reports),
        "opaque_count": sum(report["coverage"] == "opaque" for report in reports),
        "byte_identical_count": sum(report["byte_identical"] for report in reports),
        "all_byte_identical": all(report["byte_identical"] for report in reports),
        "formats": sorted({report["source_format"] for report in reports}),
        "files": [
            {
                key: report[key]
                for key in (
                    "filename",
                    "source_format",
                    "coverage",
                    "size",
                    "source_sha256",
                    "reconstructed_sha256",
                    "byte_identical",
                    "region_count",
                )
            }
            for report in reports
        ],
    }
