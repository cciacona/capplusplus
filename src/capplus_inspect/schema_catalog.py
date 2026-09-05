from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

from . import SCHEMA_VERSION
from .errors import FormatError


CATALOG_VERSION = 1
FORMAT_CATALOG_RESOURCE = "schemas/format-catalog-v1.json"
CATALOG_SCHEMA_RESOURCE = "schemas/format-catalog-v1.schema.json"

OBSERVATION_METHODS = {
    "black_box_observation",
    "controlled_game_experiment",
    "cross_build_comparison",
    "executable_analysis",
    "public_documentation",
    "static_file_comparison",
    "structural_validation",
    "visual_validation",
}
CONFIDENCE_LEVELS = {"low", "medium", "high"}
FIELD_STATUSES = {"confirmed", "inferred", "unknown"}
ROUNDTRIP_MODES = {
    "exact_structural",
    "exact_opaque",
    "normalized_comparison",
    "inspect_only",
}

# These are the original on-disk structures that the public inspector currently
# recognizes intentionally. Generated PNGs and JSON reports are not original
# formats and therefore do not belong in this catalog.
REQUIRED_FORMAT_IDS = {
    "dbase",
    "named_container",
    "offset_container",
    "sequential_images",
    "direct_indexed_image",
    "raw_binary",
    "capitalism_plus_game_set",
    "capitalism_plus_palette",
    "capitalism_plus_map",
    "capitalism_plus_save_v100",
    "capitalism_plus_executable",
    "capitalism_plus_bitmap_font",
    "capitalism_plus_text_screens",
    "capitalism_plus_language_glyphs",
    "capitalism_plus_cursor_images",
    "capitalism_plus_cursor_table",
    "capitalism_plus_context_help",
    "capitalism_plus_layout_plans",
    "capitalism_plus_configuration",
    "capitalism_plus_hall_of_fame",
    "capitalism_plus_sound_bank",
    "capitalism_plus_music_bank",
    "capitalism_plus_pcm_wave",
    "capitalism_plus_xmidi",
    "capitalism_plus_sound_settings",
    "capitalism_plus_cd_cue",
}


def _load_json_resource(name: str) -> dict[str, Any]:
    resource = files("capplus_inspect").joinpath(name)
    try:
        value = json.loads(resource.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FormatError(f"cannot load bundled schema resource {name}: {error}") from error
    if not isinstance(value, dict):
        raise FormatError(f"bundled schema resource {name} is not a JSON object")
    return value


def load_format_catalog() -> dict[str, Any]:
    """Load and validate the bundled machine-readable binary-format catalog."""

    catalog = _load_json_resource(FORMAT_CATALOG_RESOURCE)
    validate_format_catalog(catalog)
    return catalog


def load_catalog_schema() -> dict[str, Any]:
    """Return the JSON Schema that describes the catalog document itself."""

    return _load_json_resource(CATALOG_SCHEMA_RESOURCE)


def validate_format_catalog(catalog: dict[str, Any]) -> dict[str, int]:
    """Apply dependency-free completeness and provenance gates to a catalog."""

    if catalog.get("format") != "capitalism_plus_binary_format_catalog":
        raise FormatError("format catalog has an unexpected format identifier")
    if catalog.get("catalog_version") != CATALOG_VERSION:
        raise FormatError(
            f"format catalog version must be {CATALOG_VERSION}"
        )
    if catalog.get("report_schema_version") != SCHEMA_VERSION:
        raise FormatError(
            f"format catalog report schema must be {SCHEMA_VERSION}"
        )
    entries = catalog.get("formats")
    if not isinstance(entries, list) or not entries:
        raise FormatError("format catalog must contain a non-empty formats array")

    format_ids: set[str] = set()
    field_count = 0
    inferred_count = 0
    for entry_index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise FormatError(f"catalog format #{entry_index} is not an object")
        format_id = entry.get("id")
        if not isinstance(format_id, str) or not format_id:
            raise FormatError(f"catalog format #{entry_index} has no identifier")
        if format_id in format_ids:
            raise FormatError(f"duplicate catalog format identifier {format_id!r}")
        format_ids.add(format_id)
        if not isinstance(entry.get("description"), str) or not entry["description"]:
            raise FormatError(f"catalog format {format_id!r} has no description")
        if not isinstance(entry.get("parser"), str) or not entry["parser"]:
            raise FormatError(f"catalog format {format_id!r} has no parser reference")
        patterns = entry.get("file_patterns")
        if not isinstance(patterns, list) or not patterns or not all(
            isinstance(pattern, str) and pattern for pattern in patterns
        ):
            raise FormatError(f"catalog format {format_id!r} has invalid file patterns")
        roundtrip = entry.get("roundtrip")
        if not isinstance(roundtrip, dict) or roundtrip.get("mode") not in ROUNDTRIP_MODES:
            raise FormatError(f"catalog format {format_id!r} has an invalid round-trip mode")
        if not isinstance(roundtrip.get("scope"), str) or not roundtrip["scope"]:
            raise FormatError(f"catalog format {format_id!r} has no round-trip scope")

        fields = entry.get("fields")
        if not isinstance(fields, list) or not fields:
            raise FormatError(f"catalog format {format_id!r} has no field records")
        field_paths: set[str] = set()
        for field_index, field in enumerate(fields):
            if not isinstance(field, dict):
                raise FormatError(
                    f"catalog field {format_id}[{field_index}] is not an object"
                )
            path = field.get("path")
            if not isinstance(path, str) or not path:
                raise FormatError(f"catalog format {format_id!r} has an unnamed field")
            if path in field_paths:
                raise FormatError(f"catalog format {format_id!r} repeats field {path!r}")
            field_paths.add(path)
            if not isinstance(field.get("binary_type"), str) or not field["binary_type"]:
                raise FormatError(f"catalog field {format_id}.{path} has no binary type")
            for key in ("offset", "size"):
                if not isinstance(field.get(key), (int, str)):
                    raise FormatError(f"catalog field {format_id}.{path} has invalid {key}")
            status = field.get("status")
            if status not in FIELD_STATUSES:
                raise FormatError(f"catalog field {format_id}.{path} has invalid status")
            methods = field.get("observation_methods")
            if not isinstance(methods, list) or not methods or not all(
                method in OBSERVATION_METHODS for method in methods
            ):
                raise FormatError(
                    f"catalog field {format_id}.{path} has invalid observation methods"
                )
            if field.get("confidence") not in CONFIDENCE_LEVELS:
                raise FormatError(f"catalog field {format_id}.{path} has invalid confidence")
            if not isinstance(field.get("notes"), str) or not field["notes"]:
                raise FormatError(f"catalog field {format_id}.{path} has no provenance note")
            if status == "inferred":
                inferred_count += 1
            field_count += 1

    missing = REQUIRED_FORMAT_IDS - format_ids
    extra = format_ids - REQUIRED_FORMAT_IDS
    if missing or extra:
        details = []
        if missing:
            details.append("missing " + ", ".join(sorted(missing)))
        if extra:
            details.append("unexpected " + ", ".join(sorted(extra)))
        raise FormatError("format catalog coverage mismatch: " + "; ".join(details))

    return {
        "format_count": len(entries),
        "field_count": field_count,
        "inferred_field_count": inferred_count,
    }


def inspect_format_catalog() -> dict[str, Any]:
    catalog = load_format_catalog()
    summary = validate_format_catalog(catalog)
    return {**catalog, "validation": {"valid": True, **summary}}
