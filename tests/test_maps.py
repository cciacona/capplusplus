from __future__ import annotations

import contextlib
import io
import struct
from pathlib import Path
import tempfile
import unittest
import zlib

from capplus_inspect.cli import main
from capplus_inspect.errors import FormatError
from capplus_inspect.maps import decode_map_cell, inspect_map, render_map
from capplus_inspect.roundtrip import build_roundtrip_document
from .helpers import make_map, make_palette
from .test_images import png_chunks


def city(x=17, y=23):
    return struct.pack("<HHI21s", x, y, 123456, b"Synthetic Town")


class MapContractTests(unittest.TestCase):
    def test_corrected_header_and_array_boundaries(self):
        raw = bytearray(make_map((city(),)))
        raw[22:53] = b"X" * 30 + b"\0"
        raw[55:63] = struct.pack("<h6B", -1, 2, 3, 4, 5, 6, 7)
        result = inspect_map(bytes(raw))
        self.assertEqual(result["layout_version"], 2)
        self.assertEqual(result["header_size"], 55)
        self.assertEqual(result["display_name"], "X" * 30)
        self.assertEqual(result["grid"]["offset"], 55)
        self.assertEqual(result["city_array_header"]["offset"], 380215)
        self.assertEqual(result["city_array_header"]["size"], 29)
        self.assertEqual(result["cities"][0]["offset"], 380244)
        self.assertEqual(result["grid"]["terrain_height"]["minimum"], -1)
        self.assertEqual(result["grid"]["terrain_height"]["negative_count"], 1)
        self.assertEqual(result["grid"]["cell_fields"][4]["maximum"], 4)

    def test_all_four_header_flag_combinations_roundtrip(self):
        for terrain in (False, True):
            for settings in (None, bytes(range(256)) * 2 + bytes(225)):
                with self.subTest(terrain=terrain, settings=settings is not None):
                    raw = make_map((city(),), terrain=terrain, settings=settings)
                    result = inspect_map(raw)
                    self.assertEqual(result["has_terrain"], terrain)
                    self.assertEqual(result["has_settings"], settings is not None)
                    self.assertEqual(result["city_count"], int(terrain))
                    if not terrain:
                        self.assertIsNone(result["grid"])
                        self.assertIsNone(result["city_array_header"])
                    if settings is not None:
                        self.assertEqual(result["settings"]["offset"], len(raw) - 737)
                        self.assertEqual(result["settings"]["size"], 737)
                    self.assertEqual(build_roundtrip_document(raw, "TEST.MAP").encode(), raw)

    def test_nonzero_flag_bytes_follow_original_presence_tests(self):
        raw = bytearray(make_map(settings=bytes(737)))
        raw[53:55] = b"\xff\x02"
        result = inspect_map(bytes(raw))
        self.assertEqual(result["flags"], {"terrain_and_cities": 255, "settings": 2})
        self.assertTrue(result["has_terrain"] and result["has_settings"])

    def test_rejects_truncation_at_each_region(self):
        raw = make_map((city(),), settings=bytes(737))
        for end in (0, 54, 55, 380214, 380215, 380243, 380244, 380272, len(raw) - 1):
            with self.subTest(end=end), self.assertRaises(FormatError):
                inspect_map(raw[:end])

    def test_rejects_count_mismatch_and_unclaimed_trailing_data(self):
        for raw in (make_map() + city(), make_map((city(),))[:-29],
                    make_map() + b"\0", make_map(terrain=False) + bytes(737),
                    make_map(settings=bytes(737)) + b"\0"):
            with self.subTest(size=len(raw)), self.assertRaises(FormatError):
                inspect_map(raw)

    def test_array_bounds_and_record_size_are_validated(self):
        for field, value in ((0, -1), (4, 0), (4, -1), (8, -1), (8, 2),
                             (12, -1), (12, 16), (16, 0), (16, 28), (16, 30)):
            raw = bytearray(make_map((city(),)))
            struct.pack_into("<i", raw, 380215 + field, value)
            with self.subTest(field=field, value=value), self.assertRaises(FormatError):
                inspect_map(bytes(raw))
        raw = bytearray(make_map())
        struct.pack_into("<i", raw, 380215, 0x7FFFFFFF)
        struct.pack_into("<i", raw, 380227, 16385)
        with self.assertRaises(FormatError):
            inspect_map(bytes(raw))

    def test_capacity_does_not_drive_allocation_and_pointer_is_preserved(self):
        raw = bytearray(make_map((city(),)))
        struct.pack_into("<i", raw, 380215, 0x7FFFFFFF)
        struct.pack_into("<i", raw, 380235, -123456)
        raw[380239] = 231
        struct.pack_into("<I", raw, 380240, 0xFFFFFFFF)
        result = inspect_map(bytes(raw))["city_array_header"]
        self.assertEqual(result["capacity"], 0x7FFFFFFF)
        self.assertEqual(result["sort_key_offset"], -123456)
        self.assertEqual(result["unknown_control_byte"], 231)
        self.assertEqual(result["transient_data_pointer"], 0xFFFFFFFF)
        self.assertEqual(build_roundtrip_document(bytes(raw), "TEST.MAP").encode(), raw)

    def test_city_coordinates_include_edges_but_not_outside_grid(self):
        self.assertEqual(inspect_map(make_map((city(239, 197),)))["city_count"], 1)
        for x, y in ((240, 0), (0, 198), (65535, 0), (0, 65535)):
            with self.subTest(x=x, y=y), self.assertRaises(FormatError):
                inspect_map(make_map((city(x, y),)))

    def test_cell_signed_height_and_bounded_unknowns(self):
        for height in (-32768, -1, 0, 255, 32767):
            raw = struct.pack("<h6B", height, 2, 3, 4, 5, 6, 7)
            result = decode_map_cell(raw)
            self.assertEqual(result["terrain_height"], height)
            self.assertEqual(result["source_preview_index"], height & 255)
            self.assertEqual(result["stored_derived_shade"], 4)
            self.assertEqual(result["unknown_bytes"], {"2": 2, "3": 3, "5": 5, "6": 6, "7": 7})
        for index in (2, 3, 5, 6, 7):
            for value in range(256):
                raw = bytearray(8)
                raw[index] = value
                self.assertEqual(decode_map_cell(bytes(raw))["unknown_bytes"][str(index)], value)
        for size in (0, 7, 9):
            with self.subTest(size=size), self.assertRaises(FormatError):
                decode_map_cell(bytes(size))

    def test_initial_height_conversion_thresholds_and_signed_division(self):
        cases = [(-11, 0, 239), (-1, 0, 240), (0, 0, 240), (99, 0, 249),
                 (100, 1, None), (101, 1, None), (102, 2, None), (214, 77, None),
                 (215, 215, None), (254, 254, None), (255, 255, None), (32767, 255, None)]
        for height, converted, shade in cases:
            with self.subTest(height=height):
                result = decode_map_cell(struct.pack("<h6x", height))
                self.assertEqual(result["initial_terrain_height"], converted)
                self.assertEqual(result["initial_water_shade"], shade)
                self.assertIsNone(result["final_runtime_shade"])

    def test_unknown_cells_and_header_residue_roundtrip_without_normalization(self):
        raw = bytearray(make_map((city(),)))
        raw[14:22] = bytes(range(1, 9))
        for i in range(2, 8):
            raw[55 + i:380215:8] = bytes([i * 31]) * 47520
        document = build_roundtrip_document(bytes(raw), "TEST.MAP")
        self.assertEqual([r.name for r in document.regions],
                         ["header", "cell_grid", "city_array_header", "city[0]"])
        self.assertEqual(document.encode(), raw)

    def test_source_preview_pixels_unchanged_by_boundary_correction(self):
        raw = bytearray(make_map())
        for i in range(47520):
            raw[55 + i * 8] = i % 256
        old_pixels = raw[52:380212][3::8]
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "map.png"
            result = render_map(bytes(raw), make_palette(), target, scale=1, mark_cities=False)
            parts = dict(png_chunks(target.read_bytes()))
            decoded = zlib.decompress(parts[b"IDAT"])
            self.assertEqual(decoded, b"".join(b"\0" + old_pixels[y * 240:(y + 1) * 240] for y in range(198)))
            self.assertEqual(result["render_semantics"], "source_height_low_byte_preview_not_runtime_palette")

    def test_settings_only_cli_inspection_roundtrip_and_render_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "SETTINGS.MAP"
            path.write_bytes(make_map(terrain=False, settings=bytes(737)))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["inspect", str(path)]), 0)
                self.assertEqual(main(["inspect", str(path), "--json"]), 0)
                self.assertEqual(main(["roundtrip", str(path), "--json"]), 0)
            with self.assertRaises(FormatError):
                render_map(path.read_bytes(), make_palette(), Path(temporary) / "no-map.png")
            self.assertFalse((Path(temporary) / "no-map.png").exists())


if __name__ == "__main__":
    unittest.main()
