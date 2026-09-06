"""Deterministic graphics metadata from user-owned installations; no pixel export."""
from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path, PurePosixPath
from typing import Any
import zipfile
import zlib

from . import SCHEMA_VERSION
from .containers import parse_named_index, parse_offset_index
from .errors import FormatError
from .fonts import decode_font
from .images import decode_indexed_images
from .known import CORE_FILE_SHA256
from .palette import palette_for_profile, parse_palette
from .ui_resources import inspect_cursor_table
from .util import sha256_bytes, u16, u32


CATALOG_VERSION = 1
MAX_SOURCE_PATHS = 20000
MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_FONT_BYTES = 1024 * 1024
MAX_ENTRIES = 100000
PALETTE_PATH = "resource/pal_std.res"
CURSOR_PATH = "resource/cursor.res"
CURSOR_IMAGE_PATH = "resource/i_cursor.res"
IMAGE_SUFFIXES = {".ii", ".ii2", ".dfi", ".fi", ".ip", ".pic"}


def _canonical_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    parts = normalized.split("/")
    if not value or any(p in {"", ".", ".."} for p in parts) or ":" in normalized:
        raise FormatError("graphics paths must be relative without empty, drive or traversal components")
    return normalized.casefold()


def _source_kind(path: str) -> str | None:
    parts = path.split("/")
    if len(parts) != 2:
        return None
    directory, name = parts
    if directory == "resource":
        if name in {"pal_std.res", "ifcolor.res"}:
            return "palette"
        if name == "cursor.res":
            return "cursor_table"
        if name.startswith("fnt_") and name.endswith(".res"):
            return "font"
        if (name.startswith("i_") and name.endswith(".res")) or name == "language.res":
            return "indexed_images"
    if directory == "gameset" and PurePosixPath(name).suffix in IMAGE_SUFFIXES:
        return "indexed_images"
    return None


def _read_graphics_sources(path: Path) -> dict[str, bytes]:
    """Read only selected graphics, with identical path rules for ZIPs and folders."""
    archive = None
    try:
        if path.is_dir():
            candidates = ((p.relative_to(path).as_posix(), p) for p in path.rglob("*") if p.is_file())
        elif path.is_file():
            archive = zipfile.ZipFile(path)
            candidates = ((i.filename, i) for i in archive.infolist() if not i.is_dir())
        else:
            raise FormatError("graphics input must be an installation directory or ZIP")
        indexed: dict[str, Any] = {}
        for name, item in candidates:
            key = _canonical_path(name)
            if key in indexed:
                raise FormatError("duplicate or case-colliding graphics input paths")
            if len(indexed) >= MAX_SOURCE_PATHS:
                raise FormatError("graphics input has too many paths")
            indexed[key] = item
        roots = set()
        for key in indexed:
            parts = key.split("/")
            if _source_kind("/".join(parts[-2:])):
                roots.add("/".join(parts[:-2]))
        if len(roots) != 1:
            raise FormatError("graphics input needs exactly one installation root")
        root = roots.pop()
        prefix = root + "/" if root else ""
        files: dict[str, bytes] = {}
        total = 0
        for full_name, item in sorted(indexed.items()):
            if not full_name.startswith(prefix):
                continue
            name = full_name[len(prefix):]
            kind = _source_kind(name)
            if kind is None:
                continue
            limit = MAX_FONT_BYTES if kind == "font" else MAX_SOURCE_BYTES
            size = item.file_size if archive else item.stat().st_size
            if size > limit or total + size > MAX_TOTAL_BYTES:
                raise FormatError("graphics source exceeds the inspection byte budget")
            with (archive.open(item) if archive else item.open("rb")) as stream:
                raw = stream.read(limit + 1)
            if len(raw) != size or len(raw) > limit:
                raise FormatError("graphics source size changed or exceeds its limit")
            files[name] = raw
            total += len(raw)
        return files
    except (zipfile.BadZipFile, RuntimeError, EOFError, zlib.error) as error:
        raise FormatError(f"cannot read graphics ZIP: {error}") from error
    finally:
        if archive is not None:
            archive.close()


def _palette_record(path: str, raw: bytes) -> dict[str, Any]:
    colors = parse_palette(raw)
    rgb = bytes(c for color in colors for c in color)
    windows = bytes(c for color in palette_for_profile(raw, "windows") for c in color)
    return {"source": path, "source_sha256": sha256_bytes(raw), "color_count": 256,
            "source_rgb_sha256": sha256_bytes(rgb),
            "dos_dac6_sha256": sha256_bytes(bytes(c >> 2 for c in rgb)),
            "windows_rgb_sha256": sha256_bytes(windows),
            "windows_changed_colors": sum(any(c & 3 for c in color) for color in colors),
            "conversion_evidence": "docs/graphics.md#palette-loading",
            "original_selection": "not_assigned_per_image"}


def _check_sequential_budget(raw: bytes, existing_entries: int) -> None:
    # Count a possible sequential stream before its decoder allocates records.
    cursor, count = 0, 0
    while cursor + 8 <= len(raw):
        size = u32(raw, cursor)
        width, height = u16(raw, cursor + 4), u16(raw, cursor + 6)
        if not width or not height or size != 4 + width * height or cursor + 4 + size > len(raw):
            return
        count += 1
        if existing_entries + count > MAX_ENTRIES:
            raise FormatError("graphics catalog has too many entries")
        cursor += 4 + size


def catalog_graphics_files(files: Mapping[str, bytes]) -> dict[str, Any]:
    """Catalog relative installation paths without embedding bitmap/event payloads."""
    if len(files) > MAX_SOURCE_PATHS:
        raise FormatError("graphics input has too many paths")
    selected: dict[str, bytes] = {}
    seen = set()
    total = 0
    for path, raw in files.items():
        name = _canonical_path(path)
        if name in seen:
            raise FormatError("duplicate or case-colliding graphics input paths")
        seen.add(name)
        kind = _source_kind(name)
        if kind is None:
            continue
        limit = MAX_FONT_BYTES if kind == "font" else MAX_SOURCE_BYTES
        total += len(raw)
        if len(raw) > limit or total > MAX_TOTAL_BYTES:
            raise FormatError("graphics source exceeds the inspection byte budget")
        selected[name] = raw
    if not selected:
        raise FormatError("no supported graphics sources found")

    entries: list[dict[str, Any]] = []
    sources = []
    groups = []
    palettes = []
    opaque_members = []
    cursor_images = {}
    entry_count = 0

    def claim_entry() -> None:
        nonlocal entry_count
        if entry_count >= MAX_ENTRIES:
            raise FormatError("graphics catalog has too many entries")
        entry_count += 1

    for path, raw in sorted(selected.items()):
        kind = _source_kind(path)
        source = {"path": path, "size": len(raw), "sha256": sha256_bytes(raw), "kind": kind}
        sources.append(source)
        if kind == "palette":
            palettes.append(_palette_record(path, raw))
            continue
        if kind == "cursor_table":
            continue
        members = []
        if kind == "font":
            decoded = decode_font(raw)
            source["format"] = "capitalism_plus_bitmap_font"
            for glyph in decoded["glyphs"]:
                claim_entry()
                identifier = f"{path}#glyph:{glyph['code']:03d}"
                members.append(identifier)
                entries.append({"id": identifier, "kind": "bitmap_glyph", "source": path,
                                "storage_index": glyph["index"], "code": glyph["code"],
                                "width": glyph["width"], "height": glyph["height"],
                                "pixel_sha256": glyph["pixel_sha256"], "ink_pixels": glyph["ink_pixels"],
                                "source_bits": {"bitmap_offset": decoded["bitmap_offset"],
                                                "row_stride": decoded["row_stride"],
                                                "left": glyph["left_bit"], "right_exclusive": glyph["right_bit"]},
                                "presentation": {"encoding": "one_bit_mask", "foreground": None,
                                                 "background": None, "runtime_colors": "unverified"}})
        else:
            _check_sequential_budget(raw, entry_count)
            source_format, images = decode_indexed_images(raw)
            source["format"] = source_format
            decoded_indexes = set()
            for image in images:
                claim_entry()
                index = image["index"]
                decoded_indexes.add(index)
                identifier = f"{path}#image:{index:06d}"
                members.append(identifier)
                record_offset = image["offset"] - (4 if source_format == "sequential_images" else 0)
                entries.append({"id": identifier, "kind": "indexed_image", "source": path,
                                "storage_index": index, "name": image["name"],
                                "record_offset": record_offset, "payload_offset": image["offset"],
                                "source_size": image["source_size"],
                                "width": image["width"], "height": image["height"],
                                "pixel_sha256": image["pixel_sha256"],
                                "presentation": {"palette_reference": PALETTE_PATH if PALETTE_PATH in selected else None,
                                                 "palette_status": "preview_default_only",
                                                 "source_alpha_channel": "absent",
                                                 "candidate_transparent_index": 245,
                                                 "candidate_pixel_count": image["pixels"].count(245),
                                                 "original_transparency_mode": "unverified",
                                                 "drawing_origin": None}})
                if path == CURSOR_IMAGE_PATH:
                    cursor_images[index] = identifier
            directory = (parse_named_index(raw) if source_format == "named_container" else
                         parse_offset_index(raw) if source_format == "offset_container" else None)
            if directory is not None:
                for member in directory:
                    if member["index"] not in decoded_indexes:
                        claim_entry()
                        start = member["offset"]
                        opaque_members.append({"source": path, **member,
                                               "sha256": sha256_bytes(raw[start:start + member["size"]]),
                                               "meaning": "not_decoded_as_image"})
            source["opaque_member_count"] = 0 if directory is None else len(directory) - len(images)
        source["entry_count"] = len(members)
        groups.append({"id": f"{path}#storage", "source": path, "kind": "storage_order",
                       "members": members, "order_evidence": "directory, stream or glyph-code order",
                       "animation": {"status": "unverified", "frame_durations": None, "loop": None}})

    cursor_bindings = []
    if CURSOR_PATH in selected:
        decoded_cursors = inspect_cursor_table(selected[CURSOR_PATH], image_data=selected.get(CURSOR_IMAGE_PATH))
        for cursor in decoded_cursors["cursors"]:
            claim_entry()
            image_index = cursor.get("image", {}).get("index")
            image_id = cursor_images.get(image_index)
            resolution = "resolved" if image_id is not None else (
                "blank_source_reference" if cursor["bitmap_offset"] is None else "missing_image_source")
            cursor_bindings.append({"id": f"{CURSOR_PATH}#cursor:{cursor['record_number']:03d}",
                                    "identifier": cursor["identifier"], "deleted": cursor["deleted"],
                                    "record_number": cursor["record_number"],
                                    "bitmap_record_offset": cursor["bitmap_offset"],
                                    "image_id": image_id, "reference_status": resolution,
                                    "hotspot": {"x": cursor["hotspot_x"], "y": cursor["hotspot_y"],
                                                "status": "confirmed_source_fields"}})

    expected = {p for p in CORE_FILE_SHA256 if _source_kind(p)}
    missing = sorted(expected - selected.keys())
    changed = sorted(s["path"] for s in sources if s["path"] in expected
                     and s["sha256"] != CORE_FILE_SHA256[s["path"]])
    unresolved = [b["id"] for b in cursor_bindings if b["reference_status"] == "missing_image_source"]
    result = {"schema_version": SCHEMA_VERSION, "catalog_version": CATALOG_VERSION,
              "format": "capitalism_plus_graphics_catalog",
              "scope": "installation indexed images, font glyphs, palettes and cursor bindings",
              "sources": sources, "entries": entries, "groups": groups, "palettes": palettes,
              "cursor_bindings": cursor_bindings, "opaque_members": opaque_members,
              "counts": {"sources": len(sources), "entries": len(entries),
                         "indexed_images": sum(e["kind"] == "indexed_image" for e in entries),
                         "glyph_slots": sum(e["kind"] == "bitmap_glyph" for e in entries),
                         "storage_groups": len(groups), "palettes": len(palettes),
                         "cursor_bindings": len(cursor_bindings),
                         "resolved_cursor_bindings": sum(b["reference_status"] == "resolved" for b in cursor_bindings),
                         "opaque_members": len(opaque_members)},
              "coverage": {"expected_reference_sources": len(expected), "missing_reference_sources": missing,
                           "changed_reference_sources": changed,
                           "additional_sources": sorted(selected.keys() - expected),
                           "complete_reference_source_set": not missing and not changed,
                           "unresolved_cursor_bindings": unresolved,
                           "animation_semantics_complete": False, "original_presentation_validated": False},
              "evidence": "docs/graphics.md"}
    result["catalog_sha256"] = sha256_bytes(json.dumps(result, sort_keys=True, separators=(",", ":"),
                                                       ensure_ascii=True).encode("ascii"))
    return result


def catalog_graphics(path: str | Path) -> dict[str, Any]:
    return catalog_graphics_files(_read_graphics_sources(Path(path)))


def compare_graphics(left: str | Path, right: str | Path) -> dict[str, Any]:
    first, second = catalog_graphics(left), catalog_graphics(right)
    left_entries = {e["id"]: e for e in first["entries"]}
    right_entries = {e["id"]: e for e in second["entries"]}
    left_sources = {s["path"]: s for s in first["sources"]}
    right_sources = {s["path"]: s for s in second["sources"]}
    return {"schema_version": SCHEMA_VERSION, "format": "capitalism_plus_graphics_comparison",
            "catalog_version": CATALOG_VERSION,
            "left_catalog_sha256": first["catalog_sha256"], "right_catalog_sha256": second["catalog_sha256"],
            "catalogs_equal": first["catalog_sha256"] == second["catalog_sha256"],
            "left_counts": first["counts"], "right_counts": second["counts"],
            "left_reference_complete": first["coverage"]["complete_reference_source_set"],
            "right_reference_complete": second["coverage"]["complete_reference_source_set"],
            "left_only_sources": sorted(left_sources.keys() - right_sources.keys()),
            "right_only_sources": sorted(right_sources.keys() - left_sources.keys()),
            "changed_source_paths": sorted(key for key in left_sources.keys() & right_sources.keys()
                                           if left_sources[key] != right_sources[key]),
            "left_only_ids": sorted(left_entries.keys() - right_entries.keys()),
            "right_only_ids": sorted(right_entries.keys() - left_entries.keys()),
            "changed_entry_ids": sorted(key for key in left_entries.keys() & right_entries.keys()
                                        if left_entries[key] != right_entries[key])}
