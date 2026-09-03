#!/usr/bin/env python3
"""Write reproducible structural reports for user-supplied DOS and Windows builds."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from capplus_inspect.errors import InspectError
from capplus_inspect.executables import inspect_executable
from capplus_inspect.util import json_ready


REPORT_FILENAMES = (
    "dos-executable.json",
    "windows-executable.json",
    "cross-build-summary.json",
)


def _build_summary(dos: dict[str, Any], windows: dict[str, Any]) -> dict[str, Any]:
    dos_le = dos.get("le", {})
    windows_pe = windows.get("pe", {})
    windows_optional = windows_pe.get("optional_header", {})
    return {
        "schema_version": 1,
        "format": "capitalism_plus_cross_build_executable_summary",
        "dos": {
            "sha256": dos["sha256"],
            "recognized_build": dos.get("recognized_build"),
            "executable_format": dos["executable_format"],
            "machine": dos_le.get("cpu_name"),
            "header_offset": dos_le.get("header_offset"),
            "target_os_field": dos_le.get("target_os"),
            "object_count": dos_le.get("object_count"),
            "imported_module_count": dos_le.get("imported_module_count"),
        },
        "windows": {
            "sha256": windows["sha256"],
            "recognized_build": windows.get("recognized_build"),
            "executable_format": windows["executable_format"],
            "machine": windows_pe.get("machine_name"),
            "header_offset": windows_pe.get("header_offset"),
            "subsystem": windows_optional.get("subsystem_name"),
            "section_count": windows_pe.get("section_count"),
            "imported_library_count": windows_pe.get("imported_library_count"),
            "imported_symbol_count": windows_pe.get("imported_symbol_count"),
        },
        "same_machine_family": (
            dos_le.get("cpu_name") == "80386"
            and windows_pe.get("machine_name") == "i386"
        ),
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(json_ready(value), indent=2, sort_keys=True, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Survey user-supplied Capitalism Plus DOS and Windows executables."
    )
    parser.add_argument("--dos", type=Path, required=True, help="DOS CAPPLUS.EXE")
    parser.add_argument("--windows", type=Path, required=True, help="Windows CapWin.exe")
    parser.add_argument("--output", type=Path, required=True, help="report directory")
    parser.add_argument(
        "--include-strings",
        action="store_true",
        help="include printable strings in the two detailed reports",
    )
    parser.add_argument(
        "--minimum-string-length", type=int, default=5, metavar="N"
    )
    parser.add_argument("--force", action="store_true", help="replace existing reports")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not 1 <= args.minimum_string_length <= 1024:
        parser.error("--minimum-string-length must be between 1 and 1024")
    if not args.dos.is_file() or not args.windows.is_file():
        parser.error("--dos and --windows must name readable files")

    outputs = [args.output / name for name in REPORT_FILENAMES]
    existing = [path for path in outputs if path.exists()]
    if existing and not args.force:
        parser.error(f"output already exists: {existing[0]} (use --force to replace)")

    try:
        dos = inspect_executable(
            args.dos.read_bytes(),
            include_strings=args.include_strings,
            minimum_string_length=args.minimum_string_length,
        )
        windows = inspect_executable(
            args.windows.read_bytes(),
            include_strings=args.include_strings,
            minimum_string_length=args.minimum_string_length,
        )
    except (InspectError, OSError) as error:
        parser.error(str(error))

    args.output.mkdir(parents=True, exist_ok=True)
    _write_json(outputs[0], dos)
    _write_json(outputs[1], windows)
    _write_json(outputs[2], _build_summary(dos, windows))
    print(f"wrote {len(outputs)} reports to {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
