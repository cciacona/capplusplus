from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .audio import compare_sound_bank, export_audio_bank
from .cd_audio import inspect_cue
from .errors import InspectError
from .file_formats import inspect_file_bytes
from .fonts import export_font
from .fuzzing import MAX_FUZZ_ITERATIONS, run_synthetic_fuzz_campaign
from .images import export_indexed_images
from .installation import inspect_installation
from .maps import render_map
from .roundtrip import validate_roundtrip_bytes, validate_roundtrip_corpus
from .schema_catalog import inspect_format_catalog
from .saves import compare_saves
from .util import json_ready


def _inspect_path(
    path: Path,
    *,
    deep: bool,
    rows: int,
    include_strings: bool,
    minimum_string_length: int,
) -> dict[str, Any]:
    if not path.exists():
        raise InspectError("input path does not exist")
    if path.is_dir() or (path.is_file() and zipfile.is_zipfile(path)):
        return inspect_installation(path, deep=deep)
    data = path.read_bytes()
    cursor_image_data = None
    if path.name.upper() == "CURSOR.RES":
        sibling = next(
            (
                candidate
                for candidate in path.parent.iterdir()
                if candidate.is_file() and candidate.name.upper() == "I_CURSOR.RES"
            ),
            None,
        )
        if sibling is not None:
            cursor_image_data = sibling.read_bytes()
    result = inspect_file_bytes(
        data,
        path.name,
        rows=rows,
        include_strings=include_strings,
        minimum_string_length=minimum_string_length,
        cursor_image_data=cursor_image_data,
    )
    result["input"] = str(path.resolve())
    return result


def _render_installation(result: dict[str, Any]) -> list[str]:
    assets = result["core_assets"]
    lines = [
        "Capitalism Plus installation",
        f"  input: {result['input']}",
        f"  source: {result['source_kind']}",
        f"  build: {result['variant']}",
        f"  files: {result['file_count']}",
        f"  core assets: {assets['matched']}/{assets['expected']} recognized",
        f"  complete and unmodified: {'yes' if assets['complete_and_unmodified'] else 'no'}",
    ]
    for executable in result["executables"]:
        status = "recognized" if executable["recognized_unmodified"] else "unknown/modified"
        lines.append(f"  {executable['variant']} executable: {status}")
    if assets["modified"]:
        lines.append(f"  modified core files: {len(assets['modified'])}")
    if assets["missing"]:
        lines.append(f"  missing core files: {len(assets['missing'])}")
    if "deep" in result:
        deep = result["deep"]
        lines.extend(
            [
                "  deep inspection:",
                f"    game sets: {len(deep['game_sets'])}",
                f"    layout-plan files: {len(deep['layout_plans'])}",
                f"    maps: {len(deep['maps'])}",
                f"    resources: {len(deep['resources'])}",
                f"    support files: {len(deep['support_files'])}",
                f"    saves: {len(deep['saves'])}",
                f"    errors: {len(deep['errors'])}",
            ]
        )
    return lines


def _render_save(result: dict[str, Any]) -> list[str]:
    lines = [
        "Capitalism Plus save",
        f"  input: {result['input']}",
        f"  internal name: {result['internal_filename']}",
        f"  version: {result['save_version']}",
        f"  date: {result['current_date']} (JDN {result['current_date_jdn']})",
        f"  company: {result['company_name']}",
        f"  scenario: {result['scenario_title']}",
        f"  settings: {', '.join(result['settings_references']) or '<none found>'}",
        f"  sections: {result['section_count']}/24",
    ]
    if result.get("rng"):
        lines.append(f"  RNG state: {result['rng']['state_hex']}")
    town = result.get("town_array", {})
    if town.get("parsed"):
        names = ", ".join(item["name"] for item in town["towns"])
        dynamic = town["dynamic_array"]
        lines.extend(
            [
                f"  towns: {len(town['towns'])} ({names})",
                f"  town/item records: {dynamic['element_count']} x {dynamic['element_size']} bytes",
                f"  item IDs represented: {dynamic['item_id_count']}",
            ]
        )
    else:
        lines.append(f"  town array: not decoded ({town.get('error', 'unknown error')})")
    return lines


def _render_set(result: dict[str, Any]) -> list[str]:
    lines = [
        "Capitalism Plus game set",
        f"  input: {result['input']}",
        f"  tables: {result['table_count']}",
    ]
    lines.extend(
        f"  {table['name']:<9} records={table['record_count']:<4} fields={table['field_count']}"
        for table in result["tables"]
    )
    return lines


def _render_map(result: dict[str, Any]) -> list[str]:
    lines = [
        "Capitalism Plus map",
        f"  input: {result['input']}",
        f"  bytes: {result['size']}",
        f"  name: {result['display_name']}",
        f"  grid: {result['grid']['width']}x{result['grid']['height']} "
        f"({result['grid']['cell_size']}-byte cells)",
        f"  cities: {result['city_count']}",
    ]
    lines.extend(
        f"  {city['name']:<21} x={city['x']:<3} y={city['y']:<3} population={city['population']}"
        for city in result["cities"]
    )
    return lines


def _render_palette(result: dict[str, Any]) -> list[str]:
    return [
        "Capitalism Plus palette",
        f"  input: {result['input']}",
        f"  bytes: {result['size']}",
        f"  colors: {result['color_count']}",
        f"  channel range: {result['channel_minimum']}..{result['channel_maximum']}",
    ]


def _render_image_export(result: dict[str, Any]) -> list[str]:
    return [
        "Capitalism Plus image export",
        f"  source: {result['source']}",
        f"  source format: {result['source_format']}",
        f"  images written: {result['image_count']}",
        f"  output: {result['output_directory']}",
        f"  manifest: {result['manifest']}",
    ]


def _render_map_render(result: dict[str, Any]) -> list[str]:
    return [
        "Capitalism Plus map render",
        f"  map: {result['display_name']}",
        f"  dimensions: {result['width']}x{result['height']}",
        f"  city markers: {result['city_markers']}",
        f"  output: {result['output']}",
    ]


def _render_font_export(result: dict[str, Any]) -> list[str]:
    return [
        "Capitalism Plus font export",
        f"  source: {result['source']}",
        f"  glyphs: {result['glyph_count']}",
        f"  range: {result['first_code']}..{result['last_code']}",
        f"  atlas: {result['atlas']}",
        f"  manifest: {result['manifest']}",
    ]


def _render_special_resource(result: dict[str, Any]) -> list[str]:
    lines = [
        "Capitalism Plus structured resource",
        f"  input: {result['input']}",
        f"  format: {result['format']}",
        f"  bytes: {result['size']}",
    ]
    format_name = result["format"]
    if format_name == "capitalism_plus_bitmap_font":
        lines.extend(
            [
                f"  character range: {result['first_code']}..{result['last_code']}",
                f"  glyphs: {result['glyph_count']}",
                f"  bitmap: {result['used_width']}x{result['height']} "
                f"({result['row_stride']} bytes per row)",
            ]
        )
    elif format_name == "capitalism_plus_text_screens":
        lines.append(f"  screens: {result['screen_count']} (80x25 text cells)")
    elif format_name == "capitalism_plus_language_glyphs":
        lines.append(f"  supplemental glyphs: {result['glyph_count']}")
    elif format_name == "capitalism_plus_cursor_images":
        lines.append(f"  cursor images: {result['image_count']}")
    elif format_name == "capitalism_plus_cursor_table":
        lines.append(f"  cursors: {result['cursor_count']}")
        lines.append(
            "  image references resolved: "
            + ("yes" if result["image_cross_references_resolved"] else "no")
        )
    elif format_name == "capitalism_plus_context_help":
        lines.append(f"  topics: {result['topic_count']}")
        lines.extend(
            f"  {topic['identifier']}: {topic['region_count']} regions"
            for topic in result["topics"]
        )
    elif format_name == "capitalism_plus_layout_plans":
        lines.extend(
            [
                f"  categories: {result['category_count']}",
                f"  plans: {result['record_count']}",
            ]
        )
        lines.extend(
            f"  {category['identifier']}: {category['array_header']['record_count']} plans"
            for category in result["categories"]
        )
    elif format_name == "capitalism_plus_configuration":
        lines.append(f"  candidate text fields: {len(result['candidate_text_fields'])}")
        lines.append(
            f"  scenario references: {', '.join(result['scenario_references']) or '<none>'}"
        )
    elif format_name == "capitalism_plus_hall_of_fame":
        lines.append(f"  leaderboard slots: {result['leaderboard']['slot_count']}")
        lines.append(
            f"  save filename: {result['save_filename_record']['filename'] or '<none>'}"
        )
    return lines


def _render_executable(result: dict[str, Any]) -> list[str]:
    recognized = result.get("recognized_build") or "unknown or modified build"
    lines = [
        "Capitalism Plus executable",
        f"  input: {result['input']}",
        f"  bytes: {result['size']}",
        f"  SHA-256: {result['sha256']}",
        f"  recognized build: {recognized}",
        f"  executable format: {result['executable_format']}",
    ]
    if result["recognized_new_header"]:
        lines.append(
            f"  new header offset: 0x{result['dos_header']['new_header_offset']:X}"
        )
    else:
        lines.append("  new-format header: none recognized")
    if "pe" in result:
        pe = result["pe"]
        optional = pe["optional_header"]
        lines.extend(
            [
                f"  machine: {pe['machine_name']} (0x{pe['machine']:04X})",
                f"  entry point RVA: 0x{optional['entry_point_rva']:X}",
                f"  image base: 0x{optional['image_base']:X}",
                f"  subsystem: {optional['subsystem_name']}",
                f"  sections: {pe['section_count']}",
                f"  imported libraries: {pe['imported_library_count']}",
                f"  imported symbols: {pe['imported_symbol_count']}",
            ]
        )
        lines.extend(
            f"    {section['name']:<8} RVA=0x{section['virtual_address']:08X} "
            f"raw=0x{section['raw_offset']:08X}+0x{section['raw_size']:X}"
            for section in pe["sections"]
        )
        lines.extend(
            f"    {library['library']}: {len(library['symbols'])} symbols"
            for library in pe["imports"]
        )
    elif "le" in result:
        le = result["le"]
        lines.extend(
            [
                f"  CPU: {le['cpu_name']} ({le['cpu']})",
                f"  target OS: {le['target_os_name']} ({le['target_os']})",
                f"  entry point: object {le['entry_object']} + 0x{le['entry_offset']:X}",
                f"  page size: {le['page_size']}",
                f"  objects: {le['object_count']}",
                f"  imported modules: {', '.join(le['imported_modules']) or '<none>'}",
            ]
        )
        lines.extend(
            f"    object {item['index']}: base=0x{item['base_address']:08X} "
            f"size=0x{item['virtual_size']:X} pages={item['page_count']} "
            f"flags={','.join(item['flag_names']) or 'none'}"
            for item in le["objects"]
        )
    summary = result["string_summary"]
    lines.append(
        f"  strings (minimum {summary['minimum_length']}): "
        f"{summary['ascii_count']} ASCII, {summary['utf16le_count']} UTF-16LE"
    )
    if "strings" in result:
        lines.append(f"  included strings: {len(result['strings'])}")
    return lines


def _render_resource(result: dict[str, Any]) -> list[str]:
    lines = [
        "Capitalism Plus resource",
        f"  input: {result['input']}",
        f"  format: {result['format']}",
        f"  bytes: {result['size']}",
    ]
    if "member_count" in result:
        lines.append(f"  members: {result['member_count']}")
        for member in result["members"]:
            label = member.get("name") or f"#{member['index']}"
            detail = ""
            if member["kind"] == "indexed_image":
                detail = f" {member['width']}x{member['height']}"
            elif member["kind"] == "dbase":
                detail = f" records={member['record_count']} fields={member['field_count']}"
            lines.append(f"  {label:<12} {member['kind']}{detail} ({member['size']} bytes)")
    elif "image_count" in result:
        lines.append(f"  images: {result['image_count']}")
    return lines


def _render_comparison(result: dict[str, Any]) -> list[str]:
    agreement = result["agreement_against_larger_file"] * 100
    lines = [
        "Capitalism Plus save comparison",
        f"  left: {result['left']['filename']} ({result['left']['date']})",
        f"  right: {result['right']['filename']} ({result['right']['date']})",
        f"  same size: {'yes' if result['same_size'] else 'no'}",
        f"  byte-identical: {'yes' if result['byte_identical'] else 'no'}",
        f"  same-position agreement: {agreement:.4f}%",
        f"  equal bytes: {result['equal_bytes_at_same_offsets']}",
    ]
    changed = [section for section in result["sections"] if not section["byte_identical"]]
    lines.append(f"  non-identical sections: {len(changed)}")
    for section in changed:
        lines.append(
            f"    {section['marker']}: {section['left_size']} -> {section['right_size']} bytes; "
            f"{section['differing_bytes_at_same_offsets']} same-offset byte differences"
        )
    town = result.get("town_array")
    if town:
        lines.extend(
            [
                "  known transient pointer-byte differences: "
                f"{town['transient_pointer_bytes_different']}",
                f"  changed known market floats: {town['changed_known_float_fields']}",
                f"  maximum known float drift: {town['maximum_known_float_ulp_distance']} ULP",
            ]
        )
    normalization = result["normalization"]
    evaluation = normalization["evaluation"]
    lines.extend(
        [
            f"  normalization policy: {normalization['policy']['id']} "
            f"v{normalization['policy']['version']}",
            f"  normalization applicable: {'yes' if normalization['policy_applicable'] else 'no'}",
            "  classified same-position differences: "
            + (
                str(evaluation["classified_same_position_differing_bytes"])
                if evaluation["classified_same_position_differing_bytes"] is not None
                else "not evaluated"
            ),
            "  unclassified same-position differences: "
            + (
                str(evaluation["unclassified_same_position_differing_bytes"])
                if evaluation["unclassified_same_position_differing_bytes"] is not None
                else "not evaluated"
            ),
        ]
    )
    return lines


def _render_roundtrip(result: dict[str, Any]) -> list[str]:
    if result["format"] == "capitalism_plus_roundtrip_corpus":
        return [
            "Capitalism Plus round-trip corpus validation",
            f"  input: {result['input']}",
            f"  files: {result['byte_identical_count']}/{result['file_count']} byte-identical",
            f"  structural: {result['structural_count']}",
            f"  opaque passthrough: {result['opaque_count']}",
            f"  formats: {len(result['formats'])}",
        ]
    return [
        "Capitalism Plus round-trip validation",
        f"  input: {result.get('input', result['filename'])}",
        f"  source format: {result['source_format']}",
        f"  coverage: {result['coverage']}",
        f"  regions: {result['region_count']}",
        f"  byte-identical: {'yes' if result['byte_identical'] else 'no'}",
    ]


def _render_catalog(result: dict[str, Any]) -> list[str]:
    validation = result["validation"]
    return [
        "Cap++ binary format catalog",
        f"  catalog version: {result['catalog_version']}",
        f"  formats: {validation['format_count']}",
        f"  documented fields: {validation['field_count']}",
        f"  inferred fields with provenance: {validation['inferred_field_count']}",
        "  valid: yes",
    ]


def _render_fuzz(result: dict[str, Any]) -> list[str]:
    return [
        "Cap++ deterministic parser fuzz campaign",
        f"  generator: {result['generator']}",
        f"  seed: {result['seed_hex']}",
        f"  cases: {result['case_count']}",
        f"  iterations: {result['iterations']}",
        f"  accepted mutations: {result['accepted']}",
        f"  rejected mutations: {result['rejected']}",
        f"  unexpected failures: {result['unexpected_failures']}",
        f"  transcript SHA-256: {result['transcript_sha256']}",
    ]


def _render_text(result: dict[str, Any]) -> str:
    format_name = result.get("format")
    if result.get("audio_family"):
        lines = ["Capitalism Plus audio bank", f"  kind: {result['audio_family']}",
                 f"  entries: {result['member_count']}", f"  bytes: {result['size']}"]
    elif format_name == "capitalism_plus_audio_export":
        lines = ["Capitalism Plus audio export", f"  kind: {result['kind']}",
                 f"  entries written: {result['entry_count']}", f"  manifest: {result['manifest']}"]
    elif format_name == "capitalism_plus_audio_comparison":
        lines = ["Capitalism Plus audio comparison",
                 f"  matched WAV samples/format: {result['matched_count']}/{result['entry_count']}",
                 f"  extra files: {len(result['extra_files'])}"]
    elif format_name == "capitalism_plus_cd_cue":
        lines = ["Capitalism Plus CUE geometry", f"  audio tracks: {result['audio_track_count']}",
                 f"  complete geometry: {result['geometry_complete']}", "  BIN payload validation: not performed"]
    elif format_name == "capitalism_plus_pcm_wave":
        lines = ["PCM WAVE", f"  channels: {result['channels']}",
                 f"  sample rate: {result['sample_rate']} Hz", f"  bits: {result['bits_per_sample']}",
                 f"  frames: {result['frame_count']}",
                 f"  missing terminal padding: {result['missing_terminal_padding']}"]
    elif format_name == "capitalism_plus_xmidi":
        lines = ["XMIDI framing", f"  sequences: {result['sequence_count']}",
                 f"  chunks: {len(result['chunks'])}", "  event playback: not decoded"]
    elif format_name == "capitalism_plus_sound_settings":
        lines = ["Capitalism Plus sound settings", "  slots: 9 little-endian words",
                 "  meanings: unassigned"]
    elif format_name == "capitalism_plus_installation":
        lines = _render_installation(result)
    elif format_name == "capitalism_plus_save":
        lines = _render_save(result)
    elif format_name == "capitalism_plus_game_set":
        lines = _render_set(result)
    elif format_name == "capitalism_plus_map":
        lines = _render_map(result)
    elif format_name == "capitalism_plus_palette":
        lines = _render_palette(result)
    elif format_name == "capitalism_plus_image_export":
        lines = _render_image_export(result)
    elif format_name == "capitalism_plus_font_export":
        lines = _render_font_export(result)
    elif format_name == "capitalism_plus_map_render":
        lines = _render_map_render(result)
    elif format_name == "capitalism_plus_executable":
        lines = _render_executable(result)
    elif format_name == "capitalism_plus_save_comparison":
        lines = _render_comparison(result)
    elif format_name in {
        "capitalism_plus_roundtrip_validation",
        "capitalism_plus_roundtrip_corpus",
    }:
        lines = _render_roundtrip(result)
    elif format_name == "capitalism_plus_binary_format_catalog":
        lines = _render_catalog(result)
    elif format_name == "capitalism_plus_fuzz_campaign":
        lines = _render_fuzz(result)
    elif format_name in {
        "capitalism_plus_bitmap_font",
        "capitalism_plus_text_screens",
        "capitalism_plus_language_glyphs",
        "capitalism_plus_cursor_images",
        "capitalism_plus_cursor_table",
        "capitalism_plus_context_help",
        "capitalism_plus_layout_plans",
        "capitalism_plus_configuration",
        "capitalism_plus_hall_of_fame",
    }:
        lines = _render_special_resource(result)
    else:
        lines = _render_resource(result)
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="capplus-inspect",
        description="Non-destructive inspection and export of user-supplied Capitalism Plus files.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="inspect a game directory, ZIP, executable, save, map, game set, or resource",
    )
    inspect_parser.add_argument("path", type=Path)
    inspect_parser.add_argument(
        "--deep",
        action="store_true",
        help="parse all core formats when inspecting an installation",
    )
    inspect_parser.add_argument(
        "--rows",
        type=int,
        default=0,
        metavar="N",
        help="include the first N rows of each DBF table for direct .SET inspection",
    )
    inspect_parser.add_argument(
        "--include-strings",
        action="store_true",
        help="include printable strings when inspecting an executable",
    )
    inspect_parser.add_argument(
        "--minimum-string-length",
        type=int,
        default=5,
        metavar="N",
        help="minimum executable string length (default: 5)",
    )
    inspect_parser.add_argument("--json", action="store_true", help="emit stable JSON")
    inspect_parser.add_argument(
        "--require-clean",
        action="store_true",
        help="return exit status 3 unless all 72 known core files are unmodified",
    )

    compare_parser = subparsers.add_parser(
        "compare-saves", help="compare two save files section-by-section"
    )
    compare_parser.add_argument("left", type=Path)
    compare_parser.add_argument("right", type=Path)
    compare_parser.add_argument("--json", action="store_true", help="emit stable JSON")

    export_parser = subparsers.add_parser(
        "export-images",
        help="export supported indexed images to lossless palette PNG files",
    )
    export_parser.add_argument("input", type=Path)
    export_parser.add_argument("output_directory", type=Path)
    export_parser.add_argument(
        "--palette", type=Path, required=True, help="PAL_STD.RES or compatible palette"
    )
    export_parser.add_argument(
        "--transparent-index",
        default="245",
        metavar="N|none",
        help="transparent palette index (default: 245), or 'none' for opaque output",
    )
    export_parser.add_argument("--scale", type=int, default=1, help="integer scale 1..32")
    export_parser.add_argument("--force", action="store_true", help="replace existing outputs")
    export_parser.add_argument("--json", action="store_true", help="emit stable JSON")

    font_parser = subparsers.add_parser(
        "export-font", help="export an original bitmap font to a lossless monochrome PNG atlas"
    )
    font_parser.add_argument("input", type=Path)
    font_parser.add_argument("output_directory", type=Path)
    font_parser.add_argument("--scale", type=int, default=4, help="integer scale 1..32")
    font_parser.add_argument("--force", action="store_true", help="replace existing outputs")
    font_parser.add_argument("--json", action="store_true", help="emit stable JSON")

    audio_parser = subparsers.add_parser("export-audio", help="export PCM WAV effects or unchanged XMIDI members")
    audio_parser.add_argument("input", type=Path)
    audio_parser.add_argument("output_directory", type=Path)
    audio_parser.add_argument("--kind", choices=["sound", "music"], required=True)
    audio_parser.add_argument("--sound-profile", choices=["dos", "windows"], default="windows",
                              help="WAV rate: DOS requested 11000 Hz or Windows header 11127 Hz (default)")
    audio_parser.add_argument("--force", action="store_true")
    audio_parser.add_argument("--json", action="store_true")

    comparison_parser = subparsers.add_parser("compare-audio", help="compare a sound bank with extensionless Windows WAVs")
    comparison_parser.add_argument("bank", type=Path)
    comparison_parser.add_argument("sounds_directory", type=Path)
    comparison_parser.add_argument("--json", action="store_true")

    cue_parser = subparsers.add_parser("inspect-cue", help="inspect single-BIN mixed-mode CUE geometry without opening its FILE path")
    cue_parser.add_argument("input", type=Path)
    cue_parser.add_argument("--bin-size", type=int, help="optional BIN byte length; size checks do not validate audio")
    cue_parser.add_argument("--json", action="store_true")

    render_parser = subparsers.add_parser(
        "render-map", help="render the decoded 240x198 map overview to a palette PNG"
    )
    render_parser.add_argument("input", type=Path)
    render_parser.add_argument("output", type=Path)
    render_parser.add_argument(
        "--palette", type=Path, required=True, help="PAL_STD.RES or compatible palette"
    )
    render_parser.add_argument("--scale", type=int, default=4, help="integer scale 1..32")
    render_parser.add_argument(
        "--no-cities", action="store_true", help="do not overlay city position markers"
    )
    render_parser.add_argument("--force", action="store_true", help="replace an existing output")
    render_parser.add_argument("--json", action="store_true", help="emit stable JSON")

    roundtrip_parser = subparsers.add_parser(
        "roundtrip",
        help="prove byte-exact reconstruction of one non-save file or an installation corpus",
    )
    roundtrip_parser.add_argument("path", type=Path)
    roundtrip_parser.add_argument("--json", action="store_true", help="emit stable JSON")

    schema_parser = subparsers.add_parser(
        "schema-catalog",
        help="show the versioned machine-readable binary-format and provenance catalog",
    )
    schema_parser.add_argument("--json", action="store_true", help="emit the complete catalog")

    fuzz_parser = subparsers.add_parser(
        "fuzz",
        help="run deterministic bounded mutations against synthetic parser fixtures",
    )
    fuzz_parser.add_argument(
        "--iterations",
        type=int,
        default=512,
        metavar="N",
        help="total mutations to run (default: 512)",
    )
    fuzz_parser.add_argument(
        "--seed",
        default="0x4341502B2B",
        metavar="N",
        help="non-negative integer seed, decimal or 0x-prefixed",
    )
    fuzz_parser.add_argument("--json", action="store_true", help="emit stable JSON")
    return parser


def _parse_transparent_index(value: str) -> int | None:
    if value.lower() == "none":
        return None
    try:
        result = int(value, 0)
    except ValueError as error:
        raise InspectError("--transparent-index must be 0..255 or 'none'") from error
    if not 0 <= result <= 255:
        raise InspectError("--transparent-index must be 0..255 or 'none'")
    return result


def _parse_seed(value: str) -> int:
    try:
        result = int(value, 0)
    except ValueError as error:
        raise InspectError("--seed must be a non-negative integer") from error
    if result < 0:
        raise InspectError("--seed must be a non-negative integer")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            if args.rows < 0:
                parser.error("--rows must be non-negative")
            if not 1 <= args.minimum_string_length <= 1024:
                parser.error("--minimum-string-length must be between 1 and 1024")
            result = _inspect_path(
                args.path,
                deep=args.deep,
                rows=args.rows,
                include_strings=args.include_strings,
                minimum_string_length=args.minimum_string_length,
            )
            require_clean_failed = bool(
                args.require_clean
                and result.get("format") == "capitalism_plus_installation"
                and not result["core_assets"]["complete_and_unmodified"]
            )
            as_json = args.json
        elif args.command == "compare-saves":
            result = compare_saves(args.left.read_bytes(), args.right.read_bytes())
            result["inputs"] = [str(args.left.resolve()), str(args.right.resolve())]
            require_clean_failed = False
            as_json = args.json
        elif args.command == "export-images":
            result = export_indexed_images(
                args.input.read_bytes(),
                args.palette.read_bytes(),
                args.output_directory,
                source_name=str(args.input.resolve()),
                palette_name=str(args.palette.resolve()),
                transparent_index=_parse_transparent_index(args.transparent_index),
                scale=args.scale,
                force=args.force,
            )
            require_clean_failed = False
            as_json = args.json
        elif args.command == "export-audio":
            result = export_audio_bank(args.input.read_bytes(), args.output_directory,
                                       kind=args.kind, source_name=str(args.input.resolve()),
                                       sound_profile=args.sound_profile, force=args.force)
            require_clean_failed = False
            as_json = args.json
        elif args.command == "compare-audio":
            result = compare_sound_bank(args.bank.read_bytes(), args.sounds_directory)
            require_clean_failed = not result["all_matched"]
            as_json = args.json
        elif args.command == "inspect-cue":
            result = inspect_cue(args.input.read_text(encoding="utf-8-sig"), bin_size=args.bin_size)
            require_clean_failed = False
            as_json = args.json
        elif args.command == "export-font":
            result = export_font(
                args.input.read_bytes(),
                args.output_directory,
                source_name=str(args.input.resolve()),
                scale=args.scale,
                force=args.force,
            )
            require_clean_failed = False
            as_json = args.json
        elif args.command == "render-map":
            result = render_map(
                args.input.read_bytes(),
                args.palette.read_bytes(),
                args.output,
                scale=args.scale,
                mark_cities=not args.no_cities,
                force=args.force,
            )
            result["input"] = str(args.input.resolve())
            result["palette"] = str(args.palette.resolve())
            require_clean_failed = False
            as_json = args.json
        elif args.command == "roundtrip":
            if args.path.is_dir() or (
                args.path.is_file()
                and (args.path.suffix.lower() == ".zip" or zipfile.is_zipfile(args.path))
            ):
                result = validate_roundtrip_corpus(args.path)
            else:
                result = validate_roundtrip_bytes(args.path.read_bytes(), args.path.name)
                result["input"] = str(args.path.resolve())
            require_clean_failed = False
            as_json = args.json
        elif args.command == "schema-catalog":
            result = inspect_format_catalog()
            require_clean_failed = False
            as_json = args.json
        else:
            if not 1 <= args.iterations <= MAX_FUZZ_ITERATIONS:
                parser.error(f"--iterations must be between 1 and {MAX_FUZZ_ITERATIONS}")
            result = run_synthetic_fuzz_campaign(
                iterations=args.iterations,
                seed=_parse_seed(args.seed),
            )
            require_clean_failed = False
            as_json = args.json
    except (InspectError, OSError, UnicodeError) as error:
        print(f"capplus-inspect: {error}", file=sys.stderr)
        return 2

    if as_json:
        print(json.dumps(json_ready(result), indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print(_render_text(result))
    return 3 if require_clean_failed else 0
