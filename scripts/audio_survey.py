#!/usr/bin/env python3
"""Reproduce audio-bank comparisons and known-build playback reference reports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from capplus_inspect.audio import (
    compare_sound_bank, inspect_music_bank, inspect_sound_bank,
)
from capplus_inspect.cd_audio import inspect_cue
from capplus_inspect.errors import InspectError
from capplus_inspect.executables import inspect_executable
from capplus_inspect.known import DOS_EXECUTABLE_SHA256, WINDOWS_EXECUTABLE_SHA256
from capplus_inspect.loader_analysis import _regions, _scan_direct_calls
from capplus_inspect.png_writer import write_new_file


PLAYBACK_ROUTINES = {
    "windows": {
        "poll_and_restart": 0x410230, "select_cd_music": 0x410290,
        "open_cd_and_set_tmsf": 0x4423F0, "play_cd_selection": 0x442480,
        "stop_cd": 0x442510, "play_cd_wrapper": 0x46AA10,
        "start_looping_effect": 0x46AA70, "cd_playing_flag": 0x46ACD0,
        "randomize_misc": 0x47C530,
    },
    "dos": {
        "initialize_effect_bank": 0x90C19, "choose_cd_track": 0x90D42,
        "play_cd_track": 0x90DAA, "play_effect": 0x90E69,
        "play_streamed_audio": 0x90F0E, "poll_cd_position": 0x910AF,
    },
}


def playback_reference(data: bytes, build: str) -> dict:
    expected = {"dos": DOS_EXECUTABLE_SHA256, "windows": WINDOWS_EXECUTABLE_SHA256}
    if build not in expected:
        raise InspectError("unknown playback reference build")
    executable = inspect_executable(data)
    if executable["sha256"] != expected[build]:
        raise InspectError("playback claims require the exact documented original executable hash")
    regions = _regions(data, executable, executable_only=True)
    routines = []
    for name, address in PLAYBACK_ROUTINES[build].items():
        region = next((r for r in regions if r["address"] <= address < r["address"] + len(r["data"])), None)
        if region is None:
            raise InspectError("documented playback routine falls outside executable code")
        routines.append({"name": name, "address": f"0x{address:08X}",
                         "file_offset": region["file_offset"] + address - region["address"],
                         "direct_call_sites": _scan_direct_calls(regions, address)})
    return {"build": build, "sha256": executable["sha256"], "exact_profile": True,
            "evidence": "docs/audio.md; manually audited static call paths for this exact hash",
            "routines": routines,
            "runtime_validated": False,
            "limits": "Direct-call scans are byte-pattern candidates, not reachability proof. This tool does not execute or decompile the game."}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dos", required=True, type=Path)
    parser.add_argument("--windows", required=True, type=Path)
    parser.add_argument("--sound-bank", required=True, type=Path)
    parser.add_argument("--music-bank", required=True, type=Path)
    parser.add_argument("--sounds", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="private JSON report destination")
    parser.add_argument("--cue", type=Path)
    parser.add_argument("--bin-size", type=int)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    try:
        inputs = [args.dos, args.windows, args.sound_bank, args.music_bank]
        if args.cue:
            inputs.append(args.cue)
        if args.output.resolve() in {p.resolve() for p in inputs} or args.output.resolve().is_relative_to(args.sounds.resolve()):
            raise InspectError("report destination must not overwrite any audio input")
        if args.output.is_symlink():
            raise InspectError("report destination must not be a symlink")
        sound = args.sound_bank.read_bytes()
        result = {"schema_version": 1, "format": "capitalism_plus_audio_survey",
                  "dos": playback_reference(args.dos.read_bytes(), "dos"),
                  "windows": playback_reference(args.windows.read_bytes(), "windows"),
                  "sound_bank": inspect_sound_bank(sound),
                  "music_bank": inspect_music_bank(args.music_bank.read_bytes()),
                  "loose_sound_comparison": compare_sound_bank(sound, args.sounds),
                  "cd_selections": [{"logical_selection": i, "physical_track": i + 1,
                                     "proposed_replacements": [f"music/track{i+1:02d}.ogg", f"music/track{i+1:02d}.flac"]}
                                    for i in range(1, 9)],
                  "replacement_policy": "Filename convention for a future engine; not a decoder or original feature.",
                  "xmidi_to_cd_mapping": "not_established"}
        if args.cue:
            result["cue"] = inspect_cue(args.cue.read_text(encoding="utf-8-sig"), bin_size=args.bin_size)
        elif args.bin_size is not None:
            raise InspectError("--bin-size needs --cue")
        write_new_file(args.output, (json.dumps(result, indent=2, sort_keys=True) + "\n").encode(), force=args.force)
        print(f"wrote audio survey to {args.output}")
        return 0 if result["loose_sound_comparison"]["all_matched"] else 3
    except (InspectError, OSError, UnicodeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
