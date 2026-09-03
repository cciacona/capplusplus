#!/usr/bin/env python3
"""Write reproducible loader-boundary reports for user-supplied builds."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from capplus_inspect.errors import InspectError
from capplus_inspect.loader_analysis import (
    analyze_loader_boundaries,
    run_framed_record_probe,
)
from capplus_inspect.util import json_ready


REPORT_FILENAMES = (
    "dos-loaders.json",
    "windows-loaders.json",
    "cross-build-loaders.json",
    "framed-record-probe.json",
)


def _routine_map(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        item["name"]: item for item in report["file_abstraction"]["routines"]
    }


def _build_summary(
    dos: dict[str, Any], windows: dict[str, Any], probe: dict[str, Any]
) -> dict[str, Any]:
    dos_routines = _routine_map(dos)
    windows_routines = _routine_map(windows)
    shared_names = sorted(set(dos_routines) & set(windows_routines))
    return {
        "schema_version": 1,
        "format": "capitalism_plus_cross_build_loader_summary",
        "dos": {
            "sha256": dos["sha256"],
            "recognized_build": dos["recognized_build"],
            "profile_verified": dos["profile_verified"],
            "file_routine_count": len(dos_routines),
        },
        "windows": {
            "sha256": windows["sha256"],
            "recognized_build": windows["recognized_build"],
            "profile_verified": windows["profile_verified"],
            "file_routine_count": len(windows_routines),
            "operating_system_file_api_count": len(
                windows["operating_system_file_apis"]
            ),
        },
        "shared_contracts": [
            {
                "name": name,
                "dos_address": dos_routines[name]["address_hex"],
                "windows_address": windows_routines[name]["address_hex"],
                "same_contract": dos_routines[name]["contract"]
                == windows_routines[name]["contract"],
            }
            for name in shared_names
        ],
        "direct_open_call_counts": {
            "dos": dos_routines.get("open", {}).get("direct_call_count"),
            "windows": windows_routines.get("open", {}).get("direct_call_count"),
        },
        "direct_create_call_counts": {
            "dos": dos_routines.get("create", {}).get("direct_call_count"),
            "windows": windows_routines.get("create", {}).get("direct_call_count"),
        },
        "framed_record_probe_passed": probe["passed"],
        "all_known_profiles_verified": (
            dos["profile_verified"]
            and windows["profile_verified"]
            and probe["passed"]
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
        description=(
            "Locate file-loader boundaries in user-supplied Capitalism Plus DOS "
            "and Windows executables."
        )
    )
    parser.add_argument("--dos", type=Path, required=True, help="DOS CAPPLUS.EXE")
    parser.add_argument(
        "--windows", type=Path, required=True, help="Windows CapWin.exe"
    )
    parser.add_argument("--output", type=Path, required=True, help="report directory")
    parser.add_argument(
        "--allow-unknown",
        action="store_true",
        help="write generic reference reports for unrecognized builds",
    )
    parser.add_argument("--force", action="store_true", help="replace existing reports")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.dos.is_file() or not args.windows.is_file():
        parser.error("--dos and --windows must name readable files")

    outputs = [args.output / name for name in REPORT_FILENAMES]
    existing = [path for path in outputs if path.exists()]
    if existing and not args.force:
        parser.error(f"output already exists: {existing[0]} (use --force to replace)")

    try:
        dos = analyze_loader_boundaries(args.dos.read_bytes())
        windows = analyze_loader_boundaries(args.windows.read_bytes())
    except (InspectError, OSError) as error:
        parser.error(str(error))

    if dos["executable_format"] != "LE" or windows["executable_format"] != "PE":
        parser.error("expected a DOS LE build and a Windows PE build")
    if not args.allow_unknown and not (
        dos["profile_verified"] and windows["profile_verified"]
    ):
        details = dos["verification_errors"] + windows["verification_errors"]
        parser.error(
            "loader profiles did not verify"
            + (f": {details[0]}" if details else "; use --allow-unknown to inspect")
        )

    probe = run_framed_record_probe()
    summary = _build_summary(dos, windows, probe)
    args.output.mkdir(parents=True, exist_ok=True)
    for path, value in zip(outputs, (dos, windows, summary, probe), strict=True):
        _write_json(path, value)
    print(f"wrote {len(outputs)} reports to {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
