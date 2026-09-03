from __future__ import annotations

import struct
import unittest
from unittest import mock

import capplus_inspect.loader_analysis as loader_analysis
from capplus_inspect.errors import FormatError
from capplus_inspect.loader_analysis import (
    analyze_loader_boundaries,
    run_framed_record_probe,
)
from capplus_inspect.records import read_compatible_record
from capplus_inspect.util import sha256_bytes

from .helpers import make_le_executable, make_pe32_executable


class LoaderAnalysisTests(unittest.TestCase):
    def test_verifies_synthetic_direct_call_profile(self) -> None:
        data = bytearray(make_pe32_executable())
        call_address = 0x401020
        target = 0x401100
        data[0x220] = 0xE8
        struct.pack_into("<i", data, 0x221, target - call_address - 5)
        fixture = bytes(data)
        profile = {
            "function_style": "msvc_cc_padding",
            "routines": {"open": target},
            "runtime_routines": {"open": 0x401150},
            "expected_direct_calls": {"open": 1},
        }
        with (
            mock.patch.object(
                loader_analysis, "WINDOWS_EXECUTABLE_SHA256", sha256_bytes(fixture)
            ),
            mock.patch.object(loader_analysis, "WINDOWS_FILE_PROFILE", profile),
        ):
            result = analyze_loader_boundaries(fixture)
        routine = result["file_abstraction"]["routines"][0]
        self.assertTrue(result["profile_verified"])
        self.assertEqual(routine["direct_call_count"], 1)
        self.assertEqual(routine["direct_call_sites"][0]["address"], call_address)
        self.assertIn(
            "RESOURCE\\TEST.RES",
            routine["direct_call_sites"][0]["direct_file_references"],
        )

    def test_maps_pe_file_reference_to_virtual_address(self) -> None:
        result = analyze_loader_boundaries(make_pe32_executable())
        reference = next(
            item
            for item in result["observed_file_references"]
            if item["text"] == "RESOURCE\\TEST.RES"
        )
        self.assertEqual(reference["family"], "resource")
        self.assertEqual(reference["address"], 0x4021B0)
        self.assertEqual(reference["code_references"][0]["address"], 0x401010)
        self.assertFalse(result["profile_applied"])

    def test_maps_le_reference_as_object_relative_offset(self) -> None:
        result = analyze_loader_boundaries(make_le_executable())
        reference = next(
            item
            for item in result["observed_file_references"]
            if item["text"] == "GAMESET\\TEST.SET"
        )
        self.assertEqual(reference["family"], "game_set")
        self.assertEqual(reference["address"], 0x10100)
        self.assertEqual(reference["reference_value"], 0x100)
        self.assertEqual(reference["code_references"][0]["address"], 0x10000)

    def test_framed_record_probe_passes(self) -> None:
        result = run_framed_record_probe()
        self.assertTrue(result["passed"])
        self.assertTrue(result["checks"]["declared_truncation_rejected"])


class CompatibleRecordTests(unittest.TestCase):
    def test_zero_prefix_uses_expected_size(self) -> None:
        payload, next_offset, stored_size = read_compatible_record(
            b"\0\0abcdefgh", 0, expected_size=8
        )
        self.assertEqual(payload, b"abcdefgh")
        self.assertEqual(next_offset, 10)
        self.assertEqual(stored_size, 0)

    def test_zero_extends_short_record(self) -> None:
        payload, next_offset, stored_size = read_compatible_record(
            struct.pack("<H", 3) + b"abcNEXT", 0, expected_size=5
        )
        self.assertEqual(payload, b"abc\0\0")
        self.assertEqual(next_offset, 5)
        self.assertEqual(stored_size, 3)

    def test_skips_oversized_tail(self) -> None:
        payload, next_offset, stored_size = read_compatible_record(
            struct.pack("<H", 7) + b"abcdefgNEXT", 0, expected_size=4
        )
        self.assertEqual(payload, b"abcd")
        self.assertEqual(next_offset, 9)
        self.assertEqual(stored_size, 7)

    def test_rejects_declared_payload_truncation(self) -> None:
        with self.assertRaises(FormatError):
            read_compatible_record(
                struct.pack("<H", 8) + b"abcd", 0, expected_size=8
            )


if __name__ == "__main__":
    unittest.main()
