from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from capplus_inspect.cli import main
from capplus_inspect.errors import FormatError
from capplus_inspect.executables import extract_executable_strings, inspect_executable

from .helpers import make_le_executable, make_pe32_executable


class ExecutableTests(unittest.TestCase):
    def test_parses_pe32_sections_and_imports(self) -> None:
        result = inspect_executable(make_pe32_executable())
        self.assertEqual(result["executable_format"], "PE")
        self.assertEqual(result["pe"]["format"], "PE32")
        self.assertEqual(result["pe"]["machine_name"], "i386")
        self.assertEqual(result["pe"]["optional_header"]["entry_point_rva"], 0x1000)
        self.assertEqual([item["name"] for item in result["pe"]["sections"]], [".text", ".idata"])
        self.assertEqual(result["pe"]["imports"][0]["library"], "KERNEL32.dll")
        self.assertEqual(result["pe"]["imports"][0]["symbols"][0]["name"], "ExitProcess")
        self.assertEqual(
            result["pe"]["imports"][0]["symbols"][0]["iat_address"], 0x402050
        )
        self.assertNotIn("strings", result)

    def test_parses_le_objects_and_imported_modules(self) -> None:
        result = inspect_executable(make_le_executable())
        le = result["le"]
        self.assertEqual(result["executable_format"], "LE")
        self.assertEqual(le["cpu_name"], "80386")
        self.assertEqual(le["target_os_name"], "DOS 4.x")
        self.assertEqual(le["imported_modules"], ["DOSCALLS"])
        self.assertEqual(le["resident_names"], [{"name": "CAPPLUS", "ordinal": 1}])
        self.assertEqual(le["objects"][0]["flag_names"], ["read", "write", "execute", "big_default"])
        self.assertEqual(le["objects"][0]["raw_offset"], 0x1000)
        self.assertEqual(le["pages"][0]["stored_size"], 0x200)

    def test_rejects_le_pages_with_zero_page_size(self) -> None:
        data = bytearray(make_le_executable())
        data[0xA8:0xAC] = bytes(4)
        with self.assertRaises(FormatError):
            inspect_executable(data)

    def test_rejects_out_of_range_le_data_page(self) -> None:
        data = bytearray(make_le_executable())
        data[0x170:0x173] = b"\0\0\2"
        with self.assertRaises(FormatError):
            inspect_executable(data)

    def test_string_extraction_is_opt_in(self) -> None:
        result = inspect_executable(make_pe32_executable(), include_strings=True)
        values = {(item["encoding"], item["text"]) for item in result["strings"]}
        self.assertIn(("ascii", "ASCII_TEST"), values)
        self.assertIn(("utf-16le", "WIDE_TEST"), values)
        self.assertGreater(result["string_summary"]["ascii_count"], 0)
        self.assertGreater(result["string_summary"]["utf16le_count"], 0)

    def test_rejects_non_executable(self) -> None:
        with self.assertRaises(FormatError):
            inspect_executable(b"not an executable")

    def test_plain_mz_does_not_claim_a_new_format_header(self) -> None:
        data = bytearray(64)
        data[:2] = b"MZ"
        data[0x3C:0x40] = (0x09B40000).to_bytes(4, "little")
        result = inspect_executable(data)
        self.assertEqual(result["executable_format"], "MZ")
        self.assertFalse(result["recognized_new_header"])
        self.assertIsNone(result["new_header_signature"])

    def test_string_minimum_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            extract_executable_strings(b"example", minimum_length=0)

    def test_cli_routes_exe_to_executable_inspector(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.exe"
            path.write_bytes(make_pe32_executable())
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = main(["inspect", str(path), "--json"])
        self.assertEqual(status, 0)
        result = json.loads(stdout.getvalue())
        self.assertEqual(result["format"], "capitalism_plus_executable")
        self.assertEqual(result["pe"]["imported_symbol_count"], 1)


if __name__ == "__main__":
    unittest.main()
