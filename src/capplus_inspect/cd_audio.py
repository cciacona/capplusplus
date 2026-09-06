"""Metadata-only geometry for the original single-BIN mixed-mode CUE layout."""
from __future__ import annotations

import re
from typing import Any

from . import SCHEMA_VERSION
from .errors import FormatError


SECTOR_BYTES = 2352
FRAMES_PER_SECTOR = 588


def _sector(value: str) -> int:
    minutes, seconds, frames = (int(part) for part in value.split(":"))
    if seconds >= 60 or frames >= 75:
        raise FormatError("CUE time has invalid seconds or frames")
    return (minutes * 60 + seconds) * 75 + frames


def inspect_cue(text: str, *, bin_size: int | None = None) -> dict[str, Any]:
    if len(text) > 65536 or len(text.encode("utf-8")) > 65536:
        raise FormatError("CUE exceeds the 64 KiB metadata limit")
    if bin_size is not None and (type(bin_size) is not int or bin_size <= 0 or bin_size % SECTOR_BYTES):
        raise FormatError("BIN size must be a positive multiple of 2352 bytes")
    filename = None
    tracks: list[dict[str, Any]] = []
    for raw in text.lstrip("\ufeff").splitlines():
        line = raw.strip()
        if not line or re.match(r"^(REM|TITLE|PERFORMER)(\s|$)", line, re.I):
            continue
        match = re.fullmatch(r'FILE\s+(?:"([^"\r\n]+)"|(\S+))\s+BINARY', line, re.I)
        if match:
            if filename is not None or tracks:
                raise FormatError("only a single-BIN CUE is currently supported")
            # The filename is descriptive metadata; never resolve or open it.
            filename = match[1] or match[2]
            continue
        match = re.fullmatch(r"TRACK\s+(\d{1,2})\s+(MODE1/2352|AUDIO)", line, re.I)
        if match:
            number, mode = int(match[1]), match[2].upper()
            if filename is None or number != len(tracks) + 1 or number > 99:
                raise FormatError("CUE tracks must follow FILE and be consecutive from one")
            if (number == 1 and mode != "MODE1/2352") or (number > 1 and mode != "AUDIO"):
                raise FormatError("expected one MODE1/2352 track followed by audio tracks")
            tracks.append({"number": number, "mode": mode, "indexes": {}})
            continue
        match = re.fullmatch(r"INDEX\s+(00|01)\s+(\d{1,3}:\d{2}:\d{2})", line, re.I)
        if match and tracks:
            index = match[1]
            indexes = tracks[-1]["indexes"]
            if index in indexes or (index == "00" and "01" in indexes):
                raise FormatError("duplicate or unordered CUE index")
            indexes[index] = _sector(match[2])
            continue
        raise FormatError("unsupported CUE directive; no layout is guessed")
    if filename is None or len(tracks) < 2:
        raise FormatError("mixed-mode CUE requires one data track and at least one audio track")
    total_sectors = None if bin_size is None else bin_size // SECTOR_BYTES
    previous = -1
    for track in tracks:
        indexes = track["indexes"]
        if "01" not in indexes:
            raise FormatError("every CUE track requires INDEX 01")
        for value in indexes.values():
            if value <= previous:
                raise FormatError("CUE index positions must increase strictly")
            previous = value
        if total_sectors is not None and indexes["01"] >= total_sectors:
            raise FormatError("CUE track begins outside the supplied BIN size")
    if tracks[0]["indexes"] != {"01": 0}:
        raise FormatError("the data track must begin at sector zero without INDEX 00")
    for i, track in enumerate(tracks):
        start = track["indexes"]["01"]
        following = tracks[i + 1]["indexes"] if i + 1 < len(tracks) else None
        end = (following.get("00", following["01"]) if following is not None else total_sectors)
        if end is not None and end <= start:
            raise FormatError("CUE track has no program sectors")
        sectors = None if end is None else end - start
        track.update(start_sector=start, end_sector_exclusive=end, sector_count=sectors,
                     byte_offset=start * SECTOR_BYTES,
                     byte_length=None if sectors is None else sectors * SECTOR_BYTES,
                     duration_seconds=None if sectors is None else sectors / 75,
                     stereo_pcm_frames=sectors * FRAMES_PER_SECTOR if sectors is not None and track["mode"] == "AUDIO" else None)
    return {"schema_version": SCHEMA_VERSION, "format": "capitalism_plus_cd_cue",
            "bin_filename": filename, "bin_size": bin_size, "sector_size": SECTOR_BYTES,
            "track_count": len(tracks), "audio_track_count": len(tracks) - 1, "tracks": tracks,
            "payload_validation": "not_performed", "geometry_complete": bin_size is not None,
            "notes": "CUE geometry does not authenticate BIN bytes or detect unlabelled stored pregaps."}
