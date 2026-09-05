"""Bounded audio framing; original samples and XMIDI events remain user-owned."""
from __future__ import annotations

import json
from pathlib import Path
import re
import struct
from typing import Any

from . import SCHEMA_VERSION
from .containers import inspect_resource, parse_named_index
from .errors import FormatError, InspectError
from .png_writer import write_new_file
from .util import sha256_bytes, u16, u32


MAX_AUDIO_BYTES = 64 * 1024 * 1024
MAX_AUDIO_MEMBERS = 4096
MAX_AUDIO_CHUNKS = 4096
SOUND_RATES = {"dos": 11000, "windows": 11127}


def _bounded(data: bytes) -> None:
    if len(data) > MAX_AUDIO_BYTES:
        raise FormatError("audio input exceeds the 64 MiB inspection limit")


def inspect_wave(data: bytes) -> dict[str, Any]:
    """Read PCM RIFF/WAVE, including the shipped missing-final-pad variant."""
    _bounded(data)
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise FormatError("expected RIFF/WAVE")
    if u32(data, 4) + 8 != len(data):
        raise FormatError("RIFF declared size does not match the complete input", offset=4)
    chunks = []
    cursor = 12
    missing_pad = False
    while cursor < len(data):
        if len(chunks) >= MAX_AUDIO_CHUNKS or cursor + 8 > len(data):
            raise FormatError("truncated or excessive WAVE chunks", offset=cursor)
        tag = data[cursor:cursor + 4]
        size = u32(data, cursor + 4)
        start, end = cursor + 8, cursor + 8 + size
        if end > len(data):
            raise FormatError("WAVE chunk exceeds RIFF bounds", offset=cursor)
        pad = size & 1
        # Several retail WAVs omit only the final data chunk's alignment byte.
        if pad and end == len(data) and tag == b"data":
            missing_pad, pad = True, 0
        if end + pad > len(data):
            raise FormatError("missing WAVE alignment byte", offset=end)
        chunks.append({"id": tag.decode("ascii", "replace"), "offset": cursor,
                       "data_offset": start, "size": size, "padding_size": pad,
                       "sha256": sha256_bytes(data[start:end])})
        cursor = end + pad
    formats = [c for c in chunks if c["id"] == "fmt "]
    samples = [c for c in chunks if c["id"] == "data"]
    if len(formats) != 1 or len(samples) != 1:
        raise FormatError("PCM WAVE requires exactly one fmt and one data chunk")
    fmt = formats[0]
    if fmt["size"] < 16:
        raise FormatError("truncated PCM format", offset=fmt["data_offset"])
    start = fmt["data_offset"]
    tag, channels, rate, byte_rate, align, bits = struct.unpack_from("<HHIIHH", data, start)
    if tag != 1:
        raise FormatError("only integer PCM WAVE is currently supported", offset=start)
    if not 1 <= channels <= 8 or not 1 <= rate <= 384000 or bits not in (8, 16, 24, 32):
        raise FormatError("unsupported PCM channel/rate/bit-depth combination", offset=start)
    if align != channels * (bits // 8) or byte_rate != rate * align:
        raise FormatError("inconsistent PCM block alignment or byte rate", offset=start)
    if fmt["size"] != 16:
        if fmt["size"] < 18 or 18 + u16(data, start + 16) != fmt["size"]:
            raise FormatError("inconsistent PCM format extension", offset=start + 16)
    sample = samples[0]
    if sample["size"] % align:
        raise FormatError("PCM data ends inside a sample frame", offset=sample["data_offset"])
    frames = sample["size"] // align
    return {"schema_version": SCHEMA_VERSION, "format": "capitalism_plus_pcm_wave",
            "size": len(data), "sha256": sha256_bytes(data), "chunks": chunks,
            "format_tag": tag, "channels": channels, "sample_rate": rate,
            "bits_per_sample": bits, "encoding": "unsigned" if bits == 8 else "signed_le",
            "block_align": align, "byte_rate": byte_rate, "frame_count": frames,
            "duration_seconds": frames / rate, "data_offset": sample["data_offset"],
            "data_size": sample["size"], "sample_sha256": sample["sha256"],
            "missing_terminal_padding": missing_pad}


def _audio_index(data: bytes) -> list[dict[str, Any]]:
    _bounded(data)
    entries = parse_named_index(data)
    if not entries or len(entries) > MAX_AUDIO_MEMBERS:
        raise FormatError("invalid or excessive named audio-bank directory")
    names = [e["name"].casefold() for e in entries]
    if len(names) != len(set(names)):
        raise FormatError("audio-bank names are duplicated or case-colliding")
    if any(e["size"] == 0 for e in entries):
        raise FormatError("audio-bank entries must not be empty")
    return entries


def inspect_sound_bank(data: bytes) -> dict[str, Any]:
    entries = _audio_index(data)
    # Retain the existing named-container JSON shape; audio metadata is additive.
    result = inspect_resource(data)
    result["audio_family"] = "sound_bank"
    result["sample_format"] = {"channels": 1, "bits_per_sample": 8, "encoding": "unsigned",
                               "rate_profiles": dict(SOUND_RATES),
                               "rate_provenance": "DOS requested rate and Windows WAV header; no rate is stored in the bank."}
    for member, entry in zip(result["members"], entries):
        member["audio"] = {"logical_id": entry["index"] + 1, "frame_count": entry["size"],
                           "duration_seconds_by_profile": {p: entry["size"] / rate for p, rate in SOUND_RATES.items()}}
    return result


def inspect_xmidi(data: bytes) -> dict[str, Any]:
    """Validate XDIR/CAT XMID framing without interpreting musical events."""
    _bounded(data)
    chunks: list[dict[str, Any]] = []

    def walk(start: int, end: int, parent: int | None, depth: int) -> list[int]:
        if depth > 8:
            raise FormatError("IFF nesting exceeds the inspection limit", offset=start)
        ids = []
        while start < end:
            if len(chunks) >= MAX_AUDIO_CHUNKS or start + 8 > end:
                raise FormatError("truncated or excessive IFF chunks", offset=start)
            tag = data[start:start + 4]
            size = int.from_bytes(data[start + 4:start + 8], "big")
            payload, finish = start + 8, start + 8 + size
            padded = finish + (size & 1)
            if padded > end:
                raise FormatError("IFF chunk or padding exceeds its parent", offset=start)
            index = len(chunks)
            node: dict[str, Any] = {"index": index, "id": tag.decode("ascii", "replace"),
                                   "parent": parent, "offset": start, "data_offset": payload,
                                   "size": size, "padding_size": size & 1}
            chunks.append(node)
            ids.append(index)
            if tag in (b"FORM", b"CAT ", b"LIST"):
                if size < 4:
                    raise FormatError("IFF group has no type", offset=payload)
                node["group_type"] = data[payload:payload + 4].decode("ascii", "replace")
                node["children"] = walk(payload + 4, finish, index, depth + 1)
            else:
                node["sha256"] = sha256_bytes(data[payload:finish])
            start = padded
        return ids

    roots = walk(0, len(data), None, 0)
    if len(roots) != 2:
        raise FormatError("expected one XDIR form followed by one XMID catalog")
    directory, catalog = (chunks[i] for i in roots)
    if (directory["id"], directory.get("group_type"), catalog["id"], catalog.get("group_type")) != ("FORM", "XDIR", "CAT ", "XMID"):
        raise FormatError("unsupported XMIDI root layout")
    info = [chunks[i] for i in directory["children"] if chunks[i]["id"] == "INFO"]
    if len(info) != 1 or info[0]["size"] != 2:
        raise FormatError("XDIR requires one two-byte sequence-count INFO chunk")
    count = u16(data, info[0]["data_offset"])
    forms = [chunks[i] for i in catalog["children"]]
    if not count or len(forms) != count or any((c["id"], c.get("group_type")) != ("FORM", "XMID") for c in forms):
        raise FormatError("XMIDI sequence count or FORM type mismatch")
    sequences = []
    for form in forms:
        children = [chunks[i] for i in form["children"]]
        events = [c for c in children if c["id"] == "EVNT"]
        timbres = [c for c in children if c["id"] == "TIMB"]
        if len(events) != 1 or not events[0]["size"] or len(timbres) > 1:
            raise FormatError("XMIDI sequence needs one nonempty EVNT and at most one TIMB")
        timbre_count = None
        if timbres:
            timbre = timbres[0]
            if timbre["size"] < 2:
                raise FormatError("truncated TIMB count", offset=timbre["data_offset"])
            timbre_count = u16(data, timbre["data_offset"])
            if 2 + timbre_count * 2 != timbre["size"]:
                raise FormatError("TIMB count does not bound its two-byte entries")
        event = events[0]
        sequences.append({"index": len(sequences), "form_offset": form["offset"],
                          "timbre_count": timbre_count, "event_offset": event["data_offset"],
                          "event_size": event["size"], "event_sha256": event["sha256"],
                          "event_semantics": "opaque",
                          "other_chunks": [c["id"] for c in children if c["id"] not in {"EVNT", "TIMB"}]})
    return {"schema_version": SCHEMA_VERSION, "format": "capitalism_plus_xmidi",
            "size": len(data), "sha256": sha256_bytes(data), "sequence_count": count,
            "chunks": chunks, "sequences": sequences, "playback_decoded": False}


def inspect_music_bank(data: bytes) -> dict[str, Any]:
    entries = _audio_index(data)
    result = inspect_resource(data)
    result["audio_family"] = "music_bank"
    for member, entry in zip(result["members"], entries):
        start = entry["offset"]
        member["audio"] = {"logical_id": entry["index"] + 1,
                           "xmidi": inspect_xmidi(data[start:start + entry["size"]]),
                           "cd_track": None}
    result["cd_mapping_status"] = "No mapping from these XMIDI entries to CD tracks is established."
    return result


def inspect_sound_settings(data: bytes) -> dict[str, Any]:
    if len(data) != 18:
        raise FormatError("CAPITAL.SND must contain nine unframed little-endian words")
    return {"schema_version": SCHEMA_VERSION, "format": "capitalism_plus_sound_settings",
            "size": len(data), "sha256": sha256_bytes(data),
            "slots": [{"index": i, "offset": i * 2, "value": u16(data, i * 2),
                       "meaning": "unassigned"} for i in range(9)]}


def inspect_known_audio(data: bytes, filename: str) -> dict[str, Any] | None:
    parts = filename.replace("\\", "/").split("/")
    name = parts[-1].upper()
    if len(parts) > 1 and parts[-2].lower() == "sounds":
        return inspect_wave(data)
    if name == "SOUND.RES":
        return inspect_sound_bank(data)
    if name == "MUSIC.RES":
        return inspect_music_bank(data)
    if name == "CAPITAL.SND":
        return inspect_sound_settings(data)
    if name.endswith(".WAV") or data[:4] == b"RIFF":
        if name.endswith(".WAV") or data[8:12] == b"WAVE":
            return inspect_wave(data)
    if name.endswith(".XMI") or data[:12] == b"FORM\0\0\0\x0eXDIR":
        return inspect_xmidi(data)
    return None


def encode_pcm_wave(samples: bytes, sample_rate: int) -> bytes:
    _bounded(samples)
    if type(sample_rate) is not int or not 1 <= sample_rate <= 384000:
        raise FormatError("PCM sample rate must be an integer from 1 to 384000")
    fmt = struct.pack("<HHIIHH", 1, 1, sample_rate, sample_rate, 1, 8)
    body = b"WAVEfmt " + struct.pack("<I", 16) + fmt
    body += b"data" + struct.pack("<I", len(samples)) + samples + (b"\0" if len(samples) & 1 else b"")
    return b"RIFF" + struct.pack("<I", len(body)) + body


def export_audio_bank(data: bytes, output_directory: Path, *, kind: str,
                      source_name: str, sound_profile: str = "windows", force: bool = False) -> dict[str, Any]:
    if kind not in {"sound", "music"} or sound_profile not in SOUND_RATES:
        raise FormatError("unknown audio kind or sound rate profile")
    info = inspect_sound_bank(data) if kind == "sound" else inspect_music_bank(data)
    directory = output_directory.resolve()
    if directory.exists() and not directory.is_dir():
        raise InspectError("audio output is not a directory")
    outputs = []
    for member in info["members"]:
        stem = re.sub(r"[^A-Za-z0-9_-]+", "_", member["name"])
        path = directory / f"{member['index'] + 1:03d}_{stem}.{ 'wav' if kind == 'sound' else 'xmi'}"
        outputs.append((path, member))
    manifest_path = directory / "manifest.json"
    paths = [p for p, _ in outputs] + [manifest_path]
    source_path = Path(source_name).resolve()
    for path in paths:
        if path.is_symlink() or path.is_dir() or path.resolve() == source_path:
            raise InspectError("audio destination aliases input or is not a regular output file")
        if path.exists() and not force:
            raise InspectError(f"output already exists: {path}; use --force to replace it")
    directory.mkdir(parents=True, exist_ok=True)
    records = []
    for path, member in outputs:
        raw = data[member["offset"]:member["offset"] + member["size"]]
        encoded = encode_pcm_wave(raw, SOUND_RATES[sound_profile]) if kind == "sound" else raw
        write_new_file(path, encoded, force=force)
        records.append({"logical_id": member["index"] + 1, "name": member["name"],
                        "offset": member["offset"], "source_size": member["size"],
                        "source_sha256": member["sha256"], "filename": path.name,
                        "output_sha256": sha256_bytes(encoded)})
    result = {"schema_version": SCHEMA_VERSION, "format": "capitalism_plus_audio_export",
              "source": source_name, "source_sha256": sha256_bytes(data), "kind": kind,
              "entry_count": len(records), "entries": records,
              "sound_profile": sound_profile if kind == "sound" else None,
              "sample_rate": SOUND_RATES[sound_profile] if kind == "sound" else None,
              "output_directory": str(directory), "manifest": str(manifest_path)}
    write_new_file(manifest_path, (json.dumps(result, indent=2, sort_keys=True) + "\n").encode(), force=force)
    return result


def compare_sound_bank(data: bytes, directory: Path) -> dict[str, Any]:
    bank = inspect_sound_bank(data)
    if not directory.is_dir():
        raise InspectError("sound comparison requires an extracted Sounds directory")
    files: dict[str, Path] = {}
    for path in directory.iterdir():
        if path.is_file():
            key = path.name.casefold()
            if key in files:
                raise FormatError("case-colliding loose sound filenames")
            files[key] = path
    rows = []
    for entry in bank["members"]:
        path = files.pop(entry["name"].casefold(), None)
        row: dict[str, Any] = {"logical_id": entry["index"] + 1, "name": entry["name"], "matched": False}
        if path is None:
            row["error"] = "missing loose WAV"
        else:
            try:
                if path.stat().st_size > MAX_AUDIO_BYTES:
                    raise FormatError("loose WAV exceeds inspection limit")
                wave = inspect_wave(path.read_bytes())
                row.update(sample_sha256=wave["sample_sha256"], sample_rate=wave["sample_rate"],
                           missing_terminal_padding=wave["missing_terminal_padding"],
                           matched=wave["sample_sha256"] == entry["sha256"] and wave["channels"] == 1
                           and wave["bits_per_sample"] == 8 and wave["sample_rate"] == SOUND_RATES["windows"])
            except (InspectError, OSError) as error:
                row["error"] = str(error)
        rows.append(row)
    return {"schema_version": SCHEMA_VERSION, "format": "capitalism_plus_audio_comparison",
            "bank_sha256": sha256_bytes(data), "entry_count": len(rows),
            "matched_count": sum(r["matched"] for r in rows), "entries": rows,
            "extra_files": sorted(files), "all_matched": all(r["matched"] for r in rows) and not files}
