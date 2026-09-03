from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from capplus_inspect.containers import inspect_resource, inspect_set
from capplus_inspect.dbf import inspect_dbf, looks_like_dbf
from capplus_inspect.errors import FormatError
from capplus_inspect.maps import (
    MAP_CORE_SIZE,
    MAP_GRID_SIZE,
    MAP_HEADER_SIZE,
    MAP_HEIGHT,
    MAP_WIDTH,
    inspect_map,
    render_map,
)
from capplus_inspect.util import float32_ulp_distance, jdn_to_iso

from .helpers import make_dbf, make_named_container, make_palette


class DbfTests(unittest.TestCase):
    def test_reads_schema_and_rows(self) -> None:
        data = make_dbf(
            [("NAME", "C", 8, 0), ("VALUE", "N", 4, 0), ("LIVE", "L", 1, 0)],
            [["Widget", "42", "T"], ["Other", "7", "F"]],
        )
        self.assertTrue(looks_like_dbf(data))
        result = inspect_dbf(data, include_rows=2)
        self.assertEqual(result["record_count"], 2)
        self.assertEqual(result["field_count"], 3)
        self.assertEqual(result["rows"][0]["NAME"], "Widget")
        self.assertEqual(result["rows"][0]["VALUE"], 42)
        self.assertIs(result["rows"][1]["LIVE"], False)

    def test_rejects_truncated_data(self) -> None:
        data = make_dbf([("NAME", "C", 8, 0)], [["Widget"]])
        with self.assertRaises(FormatError):
            inspect_dbf(data[:-4])


class ContainerTests(unittest.TestCase):
    def test_game_set_is_named_dbf_container(self) -> None:
        table = make_dbf([("CODE", "C", 8, 0)], [["APPLE"]])
        result = inspect_set(make_named_container([("PRODUCT", table)]), include_rows=1)
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["table_count"], 1)
        self.assertEqual(result["tables"][0]["name"], "PRODUCT")
        self.assertEqual(result["tables"][0]["rows"][0]["CODE"], "APPLE")

    def test_offset_container_classifies_images(self) -> None:
        image = struct.pack("<HH", 2, 2) + bytes((1, 2, 3, 4))
        data = struct.pack("<HII", 1, 10, 18) + image
        result = inspect_resource(data)
        self.assertEqual(result["format"], "offset_container")
        self.assertEqual(result["members"][0]["kind"], "indexed_image")
        self.assertEqual(result["members"][0]["width"], 2)

    def test_sequential_images(self) -> None:
        one = struct.pack("<IHH", 8, 2, 2) + bytes((1, 2, 3, 4))
        two = struct.pack("<IHH", 6, 1, 2) + bytes((5, 6))
        result = inspect_resource(one + two)
        self.assertEqual(result["format"], "sequential_images")
        self.assertEqual(result["image_count"], 2)


class MapTests(unittest.TestCase):
    def test_city_tail(self) -> None:
        map_data = bytearray(MAP_CORE_SIZE)
        internal_name = b"MAPS\\TEST.MAP\0"
        map_data[: len(internal_name)] = internal_name
        map_data[22:31] = b"Test Map\0"
        for index in range(MAP_WIDTH * MAP_HEIGHT):
            map_data[MAP_HEADER_SIZE + index * 8 + 3] = index & 0xFF
        city = bytearray(29)
        struct.pack_into("<HHI", city, 0, 17, 23, 1_250_000)
        city[8:15] = b"Teston\0"
        result = inspect_map(bytes(map_data) + city)
        self.assertEqual(result["city_count"], 1)
        self.assertEqual(result["display_name"], "Test Map")
        self.assertEqual(result["grid"]["width"], 240)
        self.assertEqual(result["grid"]["height"], 198)
        self.assertEqual(result["grid"]["size"], MAP_GRID_SIZE)
        self.assertEqual(result["grid"]["overview_palette_index_offset"], 3)
        self.assertEqual(result["cities"][0]["name"], "Teston")
        self.assertEqual(result["cities"][0]["population"], 1_250_000)

    def test_rejects_partial_city_record(self) -> None:
        with self.assertRaises(FormatError):
            inspect_map(bytes(MAP_CORE_SIZE + 1))

    def test_renders_scaled_overview_with_city_marker(self) -> None:
        map_data = bytearray(MAP_CORE_SIZE)
        map_data[22:31] = b"Test Map\0"
        city = bytearray(29)
        struct.pack_into("<HHI", city, 0, 2, 3, 1000)
        city[8:13] = b"City\0"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "map.png"
            result = render_map(bytes(map_data + city), make_palette(), output, scale=2)
            png = output.read_bytes()
        self.assertEqual((result["width"], result["height"]), (480, 396))
        self.assertEqual(result["city_markers"], 1)
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))


class UtilityTests(unittest.TestCase):
    def test_julian_day_conversion(self) -> None:
        self.assertEqual(jdn_to_iso(2_447_893), "1990-01-01")

    def test_float_ulp_distance(self) -> None:
        next_float = struct.unpack("<f", struct.pack("<I", 0x3F800001))[0]
        self.assertEqual(float32_ulp_distance(1.0, next_float), 1)


if __name__ == "__main__":
    unittest.main()
