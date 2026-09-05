from __future__ import annotations

import contextlib
from dataclasses import replace
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import wave

from capplus_inspect.audio import (
    compare_sound_bank, encode_pcm_wave, export_audio_bank, inspect_music_bank,
    inspect_sound_bank, inspect_sound_settings, inspect_wave, inspect_xmidi,
)
from capplus_inspect.cd_audio import inspect_cue
from capplus_inspect.cli import main
from capplus_inspect.errors import FormatError, InspectError
from capplus_inspect.file_formats import inspect_file_bytes
from capplus_inspect.fuzzing import _named_container, synthetic_fuzz_cases
from capplus_inspect.roundtrip import build_roundtrip_document
from scripts.audio_survey import playback_reference


def iff(tag: bytes, payload: bytes) -> bytes:
    return tag + struct.pack(">I", len(payload)) + payload + (b"\0" if len(payload) & 1 else b"")


def xmidi(*, events: bytes = b"\xff\x2f\0", timbres: bytes = b"\0\0", extra: bytes = b"", count: int = 1) -> bytes:
    sequence = iff(b"FORM", b"XMID" + iff(b"TIMB", timbres) + iff(b"EVNT", events) + extra)
    return iff(b"FORM", b"XDIR" + iff(b"INFO", struct.pack("<H", count))) + iff(b"CAT ", b"XMID" + sequence)


class WaveTests(unittest.TestCase):
    def test_generated_wave_matches_independent_standard_library_decoder(self):
        samples = bytes((0, 127, 128, 255, 1))
        for rate in (11000, 11127):
            encoded = encode_pcm_wave(samples, rate)
            with wave.open(io.BytesIO(encoded), "rb") as reader:
                self.assertEqual(reader.getparams()[:4], (1, 1, rate, len(samples)))
                self.assertEqual(reader.readframes(20), samples)
            info = inspect_wave(encoded)
            self.assertFalse(info["missing_terminal_padding"])
            self.assertEqual(info["frame_count"], len(samples))

    def test_original_terminal_pad_quirk_is_explicit_and_preserved(self):
        encoded = bytearray(encode_pcm_wave(b"\x01\x02\x03", 11127)[:-1])
        struct.pack_into("<I", encoded, 4, len(encoded) - 8)
        info = inspect_wave(bytes(encoded))
        self.assertTrue(info["missing_terminal_padding"])
        self.assertEqual(build_roundtrip_document(bytes(encoded), "EFFECT").encode(), encoded)

    def test_unknown_chunk_and_nonzero_padding_survive_roundtrip(self):
        encoded = encode_pcm_wave(b"\x01\x02", 11127)
        extra = b"JUNK" + struct.pack("<I", 1) + b"X\x7f"
        body = encoded[8:36] + extra + encoded[36:]
        raw = b"RIFF" + struct.pack("<I", len(body)) + body
        self.assertEqual(inspect_wave(raw)["chunks"][1]["id"], "JUNK")
        document = build_roundtrip_document(raw, "EFFECT")
        self.assertEqual(document.encode(), raw)
        self.assertGreater(len(document.regions), 3)
        part = document.regions[-1]
        altered = replace(document, regions=(*document.regions[:-1], replace(part, data=b"Z" * len(part.data))))
        self.assertNotEqual(altered.encode(), raw)

    def test_wave_rejects_inconsistent_lengths_format_and_alignment(self):
        raw = encode_pcm_wave(b"\x01\x02\x03", 11127)
        variants = [raw[:-2], raw + b"tail", raw[:12], raw[:20]]
        for offset, format_, value in ((4, "<I", 0xFFFFFFFF), (16, "<I", 0xFFFFFFFF),
                                      (20, "<H", 3), (22, "<H", 0), (24, "<I", 0),
                                      (28, "<I", 1), (32, "<H", 2), (34, "<H", 7)):
            changed = bytearray(raw)
            struct.pack_into(format_, changed, offset, value)
            variants.append(bytes(changed))
        for candidate in variants:
            with self.subTest(size=len(candidate)), self.assertRaises(FormatError):
                inspect_wave(candidate)

    def test_wave_requires_unique_format_and_data_chunks(self):
        raw = encode_pcm_wave(b"\x80", 11127)
        for extra in (raw[12:36], raw[36:]):
            body = raw[8:] + extra
            with self.assertRaises(FormatError):
                inspect_wave(b"RIFF" + struct.pack("<I", len(body)) + body)

    def test_limits_and_invalid_encoding_rate(self):
        with patch("capplus_inspect.audio.MAX_AUDIO_BYTES", 8), self.assertRaises(FormatError):
            inspect_wave(b"x" * 9)
        for rate in (0, True, 384001, 1.5):
            with self.assertRaises(FormatError):
                encode_pcm_wave(b"x", rate)


class BankAndXmidiTests(unittest.TestCase):
    def test_audio_bank_metadata_is_additive_and_ordered(self):
        raw = _named_container([("FIRST", b"\0\x80\xff"), ("SECOND", b"\x80")])
        info = inspect_sound_bank(raw)
        self.assertEqual(info["format"], "named_container")
        self.assertEqual([r["name"] for r in info["members"]], ["FIRST", "SECOND"])
        self.assertEqual([r["audio"]["logical_id"] for r in info["members"]], [1, 2])
        self.assertEqual(info["sample_format"]["rate_profiles"], {"dos": 11000, "windows": 11127})

    def test_audio_bank_rejects_collisions_empty_and_truncated_entries(self):
        for raw in (_named_container([("a", b"x"), ("A", b"y")]), _named_container([("A", b"")]),
                    _named_container([("A", b"x")])[:-1], b"\xff\xff"):
            with self.assertRaises(FormatError):
                inspect_sound_bank(raw)

    def test_xmidi_framing_and_unknown_event_semantics(self):
        raw = xmidi(extra=iff(b"TEST", b"abc"))
        info = inspect_xmidi(raw)
        self.assertEqual(info["sequence_count"], 1)
        self.assertEqual(info["sequences"][0]["timbre_count"], 0)
        self.assertEqual(info["sequences"][0]["other_chunks"], ["TEST"])
        self.assertFalse(info["playback_decoded"])
        self.assertEqual(info["sequences"][0]["event_semantics"], "opaque")
        self.assertEqual(build_roundtrip_document(raw, "TEST.XMI").encode(), raw)

    def test_music_bank_preserves_members_without_inventing_cd_mapping(self):
        raw = _named_container([("A", xmidi()), ("B", xmidi(events=b"different"))])
        info = inspect_music_bank(raw)
        self.assertEqual(info["member_count"], 2)
        self.assertTrue(all(m["audio"]["cd_track"] is None for m in info["members"]))
        document = build_roundtrip_document(raw, "MUSIC.RES")
        self.assertEqual(document.encode(), raw)
        self.assertGreater(len(document.regions), 10)

    def test_xmidi_rejects_wrong_counts_truncation_duplicate_events_and_timbres(self):
        variants = [xmidi(count=2), xmidi(events=b""), xmidi(timbres=b"\x01\0"),
                    xmidi(extra=iff(b"EVNT", b"x")), xmidi(extra=iff(b"TIMB", b"\0\0")),
                    xmidi()[:-1], xmidi() + b"tail"]
        broken = bytearray(xmidi())
        struct.pack_into(">I", broken, 4, 0xFFFFFFFF)
        variants.append(bytes(broken))
        for raw in variants:
            with self.subTest(size=len(raw)), self.assertRaises(FormatError):
                inspect_xmidi(raw)

    def test_xmidi_bounded_recursion_and_chunk_count(self):
        group = iff(b"EVNT", b"x")
        for _ in range(10):
            group = iff(b"FORM", b"XMID" + group)
        with self.assertRaises(FormatError):
            inspect_xmidi(group)
        with patch("capplus_inspect.audio.MAX_AUDIO_CHUNKS", 2), self.assertRaises(FormatError):
            inspect_xmidi(xmidi())

    def test_sound_settings_have_no_speculative_names_or_flag_restrictions(self):
        raw = struct.pack("<9H", *range(9))
        info = inspect_sound_settings(raw)
        self.assertEqual([s["value"] for s in info["slots"]], list(range(9)))
        self.assertTrue(all(s["meaning"] == "unassigned" for s in info["slots"]))
        self.assertEqual(build_roundtrip_document(raw, "CAPITAL.SND").encode(), raw)
        with self.assertRaises(FormatError):
            inspect_sound_settings(raw[:-1])

    def test_audio_filename_dispatch_and_unknown_executable_rejection(self):
        for case in synthetic_fuzz_cases():
            if case.name in {"SOUND.RES", "MUSIC.RES", "TEST.XMI", "TEST.WAV", "CAPITAL.SND"}:
                self.assertIn("format", inspect_file_bytes(case.data, case.name.lower()))
        with self.assertRaises(InspectError):
            playback_reference(b"MZ" + bytes(62), "windows")
        # A broken extensionless effect must not silently fall back to raw data.
        for reader in (inspect_file_bytes, build_roundtrip_document):
            with self.assertRaises(FormatError):
                reader(b"broken WAV header", "Sounds/EFFECT")


class AudioExportTests(unittest.TestCase):
    def test_sound_and_music_exports_preserve_payloads(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            samples = b"\0\x80\xff"
            for profile, rate in (("windows", 11127), ("dos", 11000)):
                result = export_audio_bank(_named_container([("TEST", samples)]), root / profile,
                                           kind="sound", source_name="SOUND.RES", sound_profile=profile)
                decoded = inspect_wave((root / profile / result["entries"][0]["filename"]).read_bytes())
                self.assertEqual(decoded["sample_rate"], rate)
                self.assertEqual(decoded["sample_sha256"], result["entries"][0]["source_sha256"])
            music = xmidi()
            result = export_audio_bank(_named_container([("TEST", music)]), root / "music", kind="music", source_name="MUSIC.RES")
            self.assertEqual((root / "music" / result["entries"][0]["filename"]).read_bytes(), music)
            self.assertEqual(json.loads(Path(result["manifest"]).read_text())["entry_count"], 1)

    def test_export_preflight_protects_existing_files_and_source(self):
        bank = _named_container([("A", b"x"), ("B", b"y")])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            conflict = root / "002_B.wav"
            conflict.write_bytes(b"keep")
            with self.assertRaises(InspectError):
                export_audio_bank(bank, root, kind="sound", source_name="SOUND.RES")
            self.assertFalse((root / "001_A.wav").exists())
            self.assertEqual(conflict.read_bytes(), b"keep")
            with self.assertRaises(InspectError):
                export_audio_bank(bank, root, kind="sound", source_name=str(conflict), force=True)
            export_audio_bank(bank, root, kind="sound", source_name="SOUND.RES", force=True)
            self.assertTrue(conflict.read_bytes().startswith(b"RIFF"))

    def test_export_names_cannot_traverse_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = export_audio_bank(_named_container([("../evil", b"x")]), root, kind="sound", source_name="SOUND.RES")
            self.assertEqual((root / result["entries"][0]["filename"]).parent, root)
            self.assertNotIn("/", result["entries"][0]["filename"])

    def test_comparison_detects_missing_extra_mismatched_and_bad_format(self):
        bank = _named_container([("ONE", b"a"), ("TWO", b"b")])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "one").write_bytes(encode_pcm_wave(b"a", 11127))
            self.assertEqual(compare_sound_bank(bank, root)["matched_count"], 1)
            (root / "TWO").write_bytes(encode_pcm_wave(b"b", 11127))
            self.assertTrue(compare_sound_bank(bank, root)["all_matched"])
            (root / "EXTRA").write_bytes(b"extra")
            self.assertFalse(compare_sound_bank(bank, root)["all_matched"])
            for content in (b"malformed", encode_pcm_wave(b"wrong", 11127), encode_pcm_wave(b"b", 11000)):
                (root / "TWO").write_bytes(content)
                self.assertEqual(compare_sound_bank(bank, root)["matched_count"], 1)

    def test_cli_audio_commands_and_exit_codes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bank = root / "SOUND.RES"
            bank.write_bytes(_named_container([("TEST", b"\x80")]))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["inspect", str(bank), "--json"]), 0)
                self.assertEqual(main(["export-audio", str(bank), str(root / "out"), "--kind", "sound", "--json"]), 0)
                # Export filenames carry numeric prefixes; the comparison expects original extensionless names.
                self.assertEqual(main(["compare-audio", str(bank), str(root / "out"), "--json"]), 3)


class CueTests(unittest.TestCase):
    CUE = 'FILE "disc.bin" BINARY\n TRACK 01 MODE1/2352\n INDEX 01 00:00:00\n TRACK 02 AUDIO\n INDEX 01 00:02:00\n TRACK 03 AUDIO\n INDEX 01 00:03:00\n'

    def test_cue_geometry_and_last_track_require_explicit_bin_length(self):
        info = inspect_cue(self.CUE)
        self.assertFalse(info["geometry_complete"])
        self.assertIsNone(info["tracks"][-1]["sector_count"])
        info = inspect_cue(self.CUE, bin_size=300 * 2352)
        self.assertEqual([t["sector_count"] for t in info["tracks"]], [150, 75, 75])
        self.assertEqual(info["tracks"][-1]["stereo_pcm_frames"], 44100)
        self.assertEqual(info["payload_validation"], "not_performed")

    def test_cue_stored_index00_excludes_pregap_from_program_range(self):
        raw = self.CUE.replace("INDEX 01 00:03:00", "INDEX 00 00:02:50\n INDEX 01 00:03:00")
        info = inspect_cue(raw, bin_size=300 * 2352)
        self.assertEqual(info["tracks"][1]["sector_count"], 50)

    def test_cue_rejects_unsupported_directives_invalid_indexes_and_truncation(self):
        variants = [self.CUE.replace("00:03:00", "00:02:00"), self.CUE.replace("00:03:00", "00:60:00"),
                    self.CUE.replace("TRACK 03", "TRACK 04"), self.CUE + 'FILE "two.bin" BINARY\n',
                    self.CUE + "PREGAP 00:02:00\n", self.CUE.replace(" INDEX 01 00:03:00", ""),
                    self.CUE + "INDEX 01 00:04:00\n"]
        for value in variants:
            with self.subTest(cue=value), self.assertRaises(FormatError):
                inspect_cue(value)
        for size in (1, 0, -2352, 225 * 2352, True):
            with self.assertRaises(FormatError):
                inspect_cue(self.CUE, bin_size=size)

    def test_cue_filename_is_metadata_not_a_file_to_open(self):
        raw = self.CUE.replace("disc.bin", "../../not-opened.bin")
        info = inspect_cue(raw)
        self.assertEqual(info["bin_filename"], "../../not-opened.bin")

    def test_cue_cli_handles_invalid_text_without_traceback(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "test.cue"
            path.write_bytes(b"\xff")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["inspect-cue", str(path)]), 2)


if __name__ == "__main__":
    unittest.main()
