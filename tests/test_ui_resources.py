from __future__ import annotations

import contextlib
import io
import json
import struct
import tempfile
import unittest
from pathlib import Path

from capplus_inspect.cli import main
from capplus_inspect.errors import FormatError
from capplus_inspect.fonts import decode_font, export_font, inspect_font
from capplus_inspect.plans import inspect_layout_plan
from capplus_inspect.support_files import inspect_configuration, inspect_hall_of_fame
from capplus_inspect.ui_resources import (
    inspect_cursor_table,
    inspect_help,
    inspect_language_glyphs,
    inspect_text_screens,
)

from .helpers import make_dbf, make_named_container


def make_offset_container(payloads: list[bytes]) -> bytes:
    header_size = 2 + (len(payloads) + 1) * 4
    offsets = [header_size]
    for payload in payloads:
        offsets.append(offsets[-1] + len(payload))
    return struct.pack("<H", len(payloads)) + struct.pack(
        "<" + "I" * len(offsets), *offsets
    ) + b"".join(payloads)


def make_font() -> bytes:
    header = bytearray(88)
    struct.pack_into("<HH", header, 0x24, 65, 66)
    struct.pack_into("<HH", header, 0x50, 1, 2)
    boundaries = struct.pack("<3H", 0, 2, 2)
    bitmap = bytes((0b10000000, 0b01000000))
    return bytes(header) + boundaries + bitmap


def make_cursor_table() -> bytes:
    data = bytearray(
        make_dbf(
            [
                ("FILENAME", "C", 8, 0),
                ("HOTSPOT_X", "N", 3, 0),
                ("HOTSPOT_Y", "N", 3, 0),
                ("BITMAPPTR", "C", 4, 0),
            ],
            [["ARROW", "1", "2", "xxxx"], ["EDIT", "3", "4", "    "]],
        )
    )
    header_length = struct.unpack_from("<H", data, 8)[0]
    data[header_length + 15 : header_length + 19] = struct.pack("<I", 0)
    return bytes(data)


def make_plan() -> bytes:
    record = bytearray(127)
    record[:15] = b"Synthetic plan\0"
    struct.pack_into("<H", record, 29, 1)
    record[31:33] = bytes((2, 1))
    for index in range(9):
        struct.pack_into("<H", record, 37 + index * 2, index + 1)
        struct.pack_into("<H", record, 55 + index * 2, index + 101)
    references = b"".join(f"ID{index:06d}".encode("ascii") for index in range(9))

    populated_header = struct.pack("<iiiiiiBI", 1, 1, 1, 1, 127, -1, 0, 0x12345678)
    empty_header = struct.pack("<iiiiiiBI", 1, 1, 0, 0, 127, -1, 0, 0)
    return (
        struct.pack("<H", 2)
        + b"FACT"
        + populated_header
        + record
        + references
        + b"FARM"
        + empty_header
    )


class FontTests(unittest.TestCase):
    def test_decodes_msb_first_glyphs_and_empty_slot(self) -> None:
        result = inspect_font(make_font())
        decoded = decode_font(make_font())
        self.assertEqual(result["format"], "capitalism_plus_bitmap_font")
        self.assertEqual(result["boundaries"], [0, 2, 2])
        self.assertEqual(result["glyphs"][0]["width"], 2)
        self.assertEqual(decoded["glyphs"][0]["pixels"], bytes((1, 0, 0, 1)))
        self.assertEqual(result["glyphs"][1]["width"], 0)

    def test_rejects_bad_boundaries_and_truncated_bitmap(self) -> None:
        broken = bytearray(make_font())
        struct.pack_into("<H", broken, 90, 9)
        with self.assertRaises(FormatError):
            inspect_font(bytes(broken))
        with self.assertRaises(FormatError):
            inspect_font(make_font()[:-1])

    def test_exports_atlas_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = export_font(
                make_font(), Path(directory), source_name="synthetic-font.res", scale=2
            )
            manifest = json.loads(Path(result["manifest"]).read_text())
            self.assertTrue(Path(result["atlas"]).read_bytes().startswith(b"\x89PNG"))
            self.assertEqual(manifest["glyph_count"], 2)


class TextAndLanguageTests(unittest.TestCase):
    def test_decodes_ordered_text_cells_and_attributes(self) -> None:
        screen = bytearray()
        for index in range(80 * 25):
            screen.extend((ord("A") if index == 0 else ord(" "), 0x1E))
        result = inspect_text_screens(make_offset_container([bytes(screen)]))
        self.assertEqual(result["screen_count"], 1)
        self.assertTrue(result["screens"][0]["text_rows"][0].startswith("A"))
        self.assertEqual(result["screens"][0]["attribute_values"], [0x1E])

    def test_rejects_malformed_text_offset(self) -> None:
        data = bytearray(make_offset_container([bytes(4000)]))
        struct.pack_into("<I", data, 6, len(data) + 1)
        with self.assertRaises(FormatError):
            inspect_text_screens(bytes(data))

    def test_decodes_language_glyph_geometry(self) -> None:
        glyph = struct.pack("<HH", 2, 1) + bytes((4, 5))
        result = inspect_language_glyphs(make_offset_container([glyph]))
        self.assertEqual(result["glyphs"][0]["width"], 2)
        self.assertEqual(result["glyphs"][0]["pixel_bytes"], 2)


class CursorTests(unittest.TestCase):
    def test_resolves_binary_dbf_offsets_to_cursor_images(self) -> None:
        image = struct.pack("<IHH", 5, 1, 1) + b"\x07"
        result = inspect_cursor_table(make_cursor_table(), image_data=image)
        self.assertEqual(result["cursor_count"], 2)
        self.assertEqual(result["cursors"][0]["image"]["index"], 0)
        self.assertEqual(result["cursors"][1]["bitmap_reference"], "blank")

    def test_rejects_unresolved_cursor_offset(self) -> None:
        table = bytearray(make_cursor_table())
        header_length = struct.unpack_from("<H", table, 8)[0]
        table[header_length + 15 : header_length + 19] = struct.pack("<I", 12)
        image = struct.pack("<IHH", 5, 1, 1) + b"\x07"
        with self.assertRaises(FormatError):
            inspect_cursor_table(bytes(table), image_data=image)


class UiCliTests(unittest.TestCase):
    def test_filename_routing_and_cursor_sibling_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            table_path = root / "CURSOR.RES"
            table_path.write_bytes(make_cursor_table())
            (root / "I_CURSOR.RES").write_bytes(
                struct.pack("<IHH", 5, 1, 1) + b"\x07"
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = main(["inspect", str(table_path), "--json"])
            result = json.loads(stdout.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(result["format"], "capitalism_plus_cursor_table")
        self.assertTrue(result["image_cross_references_resolved"])


class HelpTests(unittest.TestCase):
    def test_preserves_topic_region_order_and_geometry(self) -> None:
        topic = (
            b"Synthetic Help\r\n--------------\r\n\r\n"
            b"1, 2, 30, 40\r\nButton\r\nFirst line\r\nSecond line\r\n\x1a"
        )
        result = inspect_help(make_named_container([("TOPIC", topic), ("EMPTY", b"")]))
        self.assertEqual(result["topic_count"], 2)
        region = result["topics"][0]["regions"][0]
        self.assertEqual(region["rectangle"]["bottom"], 40)
        self.assertEqual(region["description_lines"], ["First line", "Second line"])
        self.assertEqual(result["topics"][1]["region_count"], 0)

    def test_rejects_malformed_named_offsets(self) -> None:
        data = bytearray(make_named_container([("TOPIC", b"Title\r\n-----\r\n")]))
        struct.pack_into("<I", data, 2 + 13 + 9, len(data) + 1)
        with self.assertRaises(FormatError):
            inspect_help(bytes(data))


class LayoutPlanTests(unittest.TestCase):
    def test_decodes_categories_records_and_nine_cell_grid(self) -> None:
        result = inspect_layout_plan(make_plan())
        self.assertEqual(result["category_count"], 2)
        self.assertEqual(result["record_count"], 1)
        record = result["categories"][0]["records"][0]
        self.assertEqual(record["name"], "Synthetic plan")
        self.assertEqual(record["cells"][8]["row"], 2)
        self.assertEqual(record["cells"][8]["column"], 2)
        self.assertEqual(record["cells"][8]["functional_unit_id"], 9)
        self.assertEqual(record["cells"][8]["stable_item_identifier"], "ID000008")
        self.assertEqual(result["categories"][1]["records"], [])

    def test_accepts_empty_plan_and_rejects_truncation(self) -> None:
        self.assertEqual(inspect_layout_plan(b"\0\0")["category_count"], 0)
        with self.assertRaises(FormatError):
            inspect_layout_plan(make_plan()[:-1])


class SupportFileTests(unittest.TestCase):
    def test_configuration_frame_and_text_candidates(self) -> None:
        payload = bytearray(737)
        payload[20:29] = b"TEST.SCT\0"
        result = inspect_configuration(struct.pack("<H", 737) + payload)
        self.assertEqual(result["record"]["logical_size"], 737)
        self.assertEqual(result["scenario_references"], ["TEST.SCT"])

    def test_hall_of_fame_slots_and_save_filename(self) -> None:
        leaderboard = bytes(580)
        filename = b"SAVE001.SAV\0\0"
        data = struct.pack("<H", 580) + leaderboard + struct.pack("<H", 13) + filename
        result = inspect_hall_of_fame(data)
        self.assertEqual(len(result["leaderboard"]["slots"]), 10)
        self.assertEqual(result["save_filename_record"]["filename"], "SAVE001.SAV")

    def test_rejects_trailing_support_data(self) -> None:
        with self.assertRaises(FormatError):
            inspect_configuration(struct.pack("<H", 737) + bytes(737) + b"x")


if __name__ == "__main__":
    unittest.main()
