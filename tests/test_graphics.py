from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import zlib

from capplus_inspect.cli import main
from capplus_inspect.errors import FormatError
from capplus_inspect.graphics import catalog_graphics, catalog_graphics_files, compare_graphics
from capplus_inspect.images import export_indexed_images
from capplus_inspect.palette import palette_for_profile, parse_palette
from capplus_inspect.fuzzing import synthetic_fuzz_cases
from .helpers import make_named_container, make_palette
from .test_images import png_chunks
from .test_ui_resources import make_cursor_table, make_font, make_offset_container


def bitmap(width=2, height=3, pixels=None):
    return struct.pack("<HH", width, height) + (pixels if pixels is not None else bytes([245] * (width * height)))


def fixtures():
    image = bitmap()
    return {"RESOURCE/PAL_STD.RES": make_palette(),
            "RESOURCE/IFCOLOR.RES": make_palette(),
            "RESOURCE/I_TEST.RES": make_named_container([("OPAQUE", b"private metadata"), ("ICON", image)]),
            "RESOURCE/I_CURSOR.RES": struct.pack("<I", len(image)) + image,
            "RESOURCE/CURSOR.RES": make_cursor_table(),
            "RESOURCE/FNT_TEST.RES": make_font(),
            "GAMESET/TEST.PIC": image}


def write_installation(root, files):
    for name, raw in files.items():
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)


class GraphicsCatalogTests(unittest.TestCase):
    def test_ids_order_and_hash_ignore_path_case_and_mapping_order(self):
        source = fixtures()
        left = catalog_graphics_files(source)
        right = catalog_graphics_files({p.lower(): b for p, b in reversed(list(source.items()))})
        self.assertEqual(left, right)
        self.assertEqual(left["counts"]["entries"], 5)
        self.assertEqual(left["counts"]["indexed_images"], 3)
        self.assertEqual(len({e["id"] for e in left["entries"]}), 5)
        icon = next(e for e in left["entries"] if e.get("name") == "ICON")
        self.assertEqual(icon["id"], "resource/i_test.res#image:000001")
        self.assertEqual(icon["storage_index"], 1)  # Skipped metadata does not renumber images.
        group = next(g for g in left["groups"] if g["source"] == "resource/i_test.res")
        self.assertEqual(group["members"], [icon["id"]])

    def test_catalog_retains_opaque_members_without_payloads(self):
        report = catalog_graphics_files(fixtures())
        opaque = report["opaque_members"][0]
        self.assertEqual(opaque["name"], "OPAQUE")
        self.assertEqual(opaque["size"], len(b"private metadata"))
        serialized = json.dumps(report)
        for forbidden in ('"pixels":', '"sheet_pixels":', "private metadata", '"colors":'):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(report["counts"]["opaque_members"], 1)

    def test_cursor_zero_record_offset_resolves_and_blank_stays_explicit(self):
        report = catalog_graphics_files(fixtures())
        arrow, blank = report["cursor_bindings"]
        image = next(e for e in report["entries"] if e["id"] == arrow["image_id"])
        self.assertEqual(arrow["bitmap_record_offset"], 0)
        self.assertEqual(image["record_offset"], 0)
        self.assertEqual(image["payload_offset"], 4)
        self.assertEqual(arrow["hotspot"]["x"], 1)
        self.assertEqual(arrow["hotspot"]["y"], 2)
        self.assertEqual(blank["reference_status"], "blank_source_reference")
        self.assertIsNone(blank["image_id"])

    def test_cursor_dangling_offset_rejected_but_missing_source_reported(self):
        files = fixtures()
        data = bytearray(files["RESOURCE/CURSOR.RES"])
        offset = struct.unpack_from("<H", data, 8)[0] + 15
        struct.pack_into("<I", data, offset, 1)
        files["RESOURCE/CURSOR.RES"] = bytes(data)
        with self.assertRaises(FormatError):
            catalog_graphics_files(files)
        del files["RESOURCE/I_CURSOR.RES"]
        report = catalog_graphics_files(files)
        self.assertEqual(report["cursor_bindings"][0]["reference_status"], "missing_image_source")
        self.assertEqual(len(report["coverage"]["unresolved_cursor_bindings"]), 1)

    def test_font_empty_slot_and_bit_geometry_are_cataloged(self):
        glyphs = [e for e in catalog_graphics_files(fixtures())["entries"] if e["kind"] == "bitmap_glyph"]
        self.assertEqual([g["code"] for g in glyphs], [65, 66])
        self.assertEqual([g["width"] for g in glyphs], [2, 0])
        self.assertEqual(glyphs[0]["source_bits"], {"bitmap_offset": 94, "row_stride": 1, "left": 0, "right_exclusive": 2})
        self.assertIsNone(glyphs[0]["presentation"]["foreground"])

    def test_grouping_and_transparency_do_not_claim_animation_or_alpha(self):
        report = catalog_graphics_files(fixtures())
        self.assertFalse(report["coverage"]["animation_semantics_complete"])
        self.assertTrue(all(g["kind"] == "storage_order" and g["animation"]["frame_durations"] is None for g in report["groups"]))
        image = next(e for e in report["entries"] if e["kind"] == "indexed_image")
        self.assertEqual(image["presentation"]["candidate_pixel_count"], 6)
        self.assertEqual(image["presentation"]["original_transparency_mode"], "unverified")
        self.assertEqual(image["presentation"]["source_alpha_channel"], "absent")

    def test_source_family_selection_does_not_misclassify_sound_or_text(self):
        files = fixtures()
        files.update({"RESOURCE/SOUND.RES": bitmap(), "RESOURCE/TEXT.RES": bitmap(), "MAPS/WORLD.MAP": bitmap()})
        self.assertEqual(catalog_graphics_files(files), catalog_graphics_files(fixtures()))
        files["RESOURCE/I_BROKEN.RES"] = b"broken"
        with self.assertRaises(FormatError):
            catalog_graphics_files(files)

    def test_offset_sequences_and_direct_files_keep_their_storage_indexes(self):
        first, second = bitmap(1, 1), bitmap(2, 1)
        files = {"RESOURCE/PAL_STD.RES": make_palette(),
                 "RESOURCE/I_OFFSET.RES": make_offset_container([first, second]),
                 "RESOURCE/I_STREAM.RES": struct.pack("<I", len(first)) + first + struct.pack("<I", len(second)) + second,
                 "GAMESET/TEST.PIC": first}
        report = catalog_graphics_files(files)
        self.assertEqual(report["counts"]["indexed_images"], 5)
        for source in ("resource/i_offset.res", "resource/i_stream.res"):
            self.assertEqual([e["storage_index"] for e in report["entries"] if e["source"] == source], [0, 1])

    def test_path_collision_traversal_empty_and_byte_limits(self):
        for source in ({"RESOURCE/I_X.RES": bitmap(), "resource/i_x.res": bitmap()},
                       {"../RESOURCE/I_X.RES": bitmap()}, {"/RESOURCE/I_X.RES": bitmap()},
                       {"C:/RESOURCE/I_X.RES": bitmap()}, {"RESOURCE//I_X.RES": bitmap()}, {}):
            with self.subTest(paths=list(source)), self.assertRaises(FormatError):
                catalog_graphics_files(source)
        with patch("capplus_inspect.graphics.MAX_SOURCE_BYTES", 10), self.assertRaises(FormatError):
            catalog_graphics_files(fixtures())
        with patch("capplus_inspect.graphics.MAX_TOTAL_BYTES", 10), self.assertRaises(FormatError):
            catalog_graphics_files(fixtures())

    def test_sequential_record_limit_precedes_decoder_allocation(self):
        payload = bitmap(1, 1)
        raw = (struct.pack("<I", len(payload)) + payload) * 3
        with patch("capplus_inspect.graphics.MAX_ENTRIES", 2), patch("capplus_inspect.graphics.decode_indexed_images") as decoder:
            with self.assertRaises(FormatError):
                catalog_graphics_files({"RESOURCE/I_TEST.RES": raw})
            decoder.assert_not_called()

    def test_entry_budget_includes_opaque_members_across_sources(self):
        raw = make_offset_container([bitmap(1, 1), b"", b""])
        files = {"RESOURCE/I_A.RES": raw, "RESOURCE/I_B.RES": raw}
        with patch("capplus_inspect.graphics.MAX_ENTRIES", 6):
            report = catalog_graphics_files(files)
            self.assertEqual(report["counts"]["entries"], 2)
            self.assertEqual(report["counts"]["opaque_members"], 4)
        with patch("capplus_inspect.graphics.MAX_ENTRIES", 5), self.assertRaises(FormatError):
            catalog_graphics_files(files)
        # Opaque records from an earlier file also consume the stream preflight budget.
        payload = bitmap(1, 1)
        files["RESOURCE/I_B.RES"] = (struct.pack("<I", len(payload)) + payload) * 3
        with patch("capplus_inspect.graphics.MAX_ENTRIES", 5), self.assertRaises(FormatError):
            catalog_graphics_files(files)

    def test_entry_budget_includes_glyphs_and_cursor_bindings(self):
        files = fixtures()
        report = catalog_graphics_files(files)
        total = sum(report["counts"][key] for key in ("entries", "opaque_members", "cursor_bindings"))
        with patch("capplus_inspect.graphics.MAX_ENTRIES", total):
            self.assertEqual(catalog_graphics_files(files), report)
        with patch("capplus_inspect.graphics.MAX_ENTRIES", total - 1), self.assertRaises(FormatError):
            catalog_graphics_files(files)

    def test_zip_and_directory_catalogs_match_without_mutating_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / "game"
            files = fixtures()
            write_installation(folder, files)
            archive = root / "game.zip"
            with zipfile.ZipFile(archive, "w") as z:
                for name, data in reversed(list(files.items())):
                    z.writestr("Wrapped/" + name.lower(), data)
            before = {p: p.read_bytes() for p in folder.rglob("*") if p.is_file()}
            self.assertEqual(catalog_graphics(folder), catalog_graphics(archive))
            self.assertEqual(before, {p: p.read_bytes() for p in before})
            result = compare_graphics(folder, archive)
            self.assertTrue(result["catalogs_equal"])
            self.assertFalse(result["left_reference_complete"])

    def test_zip_rejects_collisions_ambiguous_roots_and_traversal(self):
        cases = [("RESOURCE/I_X.RES", "resource/i_x.res"),
                 ("One/RESOURCE/I_X.RES", "Two/RESOURCE/I_X.RES"),
                 ("../RESOURCE/I_X.RES",), ("C:/RESOURCE/I_X.RES",)]
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "game.zip"
            for names in cases:
                with zipfile.ZipFile(archive, "w") as z:
                    for name in names:
                        z.writestr(name, bitmap())
                with self.subTest(names=names), self.assertRaises(FormatError):
                    catalog_graphics(archive)
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("RESOURCE/I_X.RES", bitmap())
            with patch("capplus_inspect.graphics.MAX_SOURCE_BYTES", 1), self.assertRaises(FormatError):
                catalog_graphics(archive)
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr("RESOURCE/I_X.RES", bitmap())
            broken = bytearray(archive.read_bytes())
            filename_size, extra_size = struct.unpack_from("<HH", broken, 26)
            broken[30 + filename_size + extra_size] = 7  # Invalid DEFLATE block type.
            archive.write_bytes(broken)
            with self.assertRaises(FormatError):
                catalog_graphics(archive)

    def test_comparison_detects_pixels_palette_and_missing_entries(self):
        with tempfile.TemporaryDirectory() as temporary:
            left, right = Path(temporary) / "left", Path(temporary) / "right"
            write_installation(left, fixtures())
            write_installation(right, fixtures())
            changed = dict(fixtures())
            changed["GAMESET/TEST.PIC"] = bitmap(pixels=b"\x01" * 6)
            write_installation(right, changed)
            self.assertEqual(compare_graphics(left, right)["changed_entry_ids"], ["gameset/test.pic#image:000000"])
            write_installation(right, fixtures())
            palette = bytearray(make_palette())
            palette[8] = 99
            (right / "RESOURCE/PAL_STD.RES").write_bytes(palette)
            comparison = compare_graphics(left, right)
            self.assertFalse(comparison["catalogs_equal"])
            self.assertEqual(comparison["changed_entry_ids"], [])
            self.assertEqual(comparison["changed_source_paths"], ["resource/pal_std.res"])
            (right / "GAMESET/TEST.PIC").unlink()
            self.assertEqual(compare_graphics(left, right)["left_only_ids"], ["gameset/test.pic#image:000000"])

    def test_cli_catalog_and_comparison_exit_codes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_installation(root, fixtures())
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["catalog-graphics", str(root), "--json"]), 0)
                self.assertEqual(main(["catalog-graphics", str(root), "--require-reference"]), 3)
                self.assertEqual(main(["compare-graphics", str(root), str(root), "--json"]), 0)
            (root / "RESOURCE/I_BROKEN.RES").write_bytes(b"bad")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["catalog-graphics", str(root)]), 2)


class PaletteProfileTests(unittest.TestCase):
    def test_windows_conversion_and_source_profile_preservation(self):
        source = make_palette()
        self.assertEqual(palette_for_profile(source), parse_palette(source))
        windows = palette_for_profile(source, "windows")
        self.assertEqual(windows[7], (4, 248, 20))
        self.assertEqual(windows[255], (252, 0, 252))
        for before, after in zip(parse_palette(source), windows):
            for a, b in zip(before, after):
                self.assertEqual(b % 4, 0)
                self.assertTrue(0 <= a - b <= 3)
        with self.assertRaises(FormatError):
            palette_for_profile(source, "guess")

    def test_png_profiles_change_only_palette_and_keep_source_bytes(self):
        pixels = b"\x07\xf5"
        raw = bitmap(2, 1, pixels)
        source = make_palette()
        with tempfile.TemporaryDirectory() as temporary:
            outputs = []
            for profile in ("source", "windows"):
                result = export_indexed_images(raw, source, Path(temporary) / profile,
                                               source_name="TEST.PIC", palette_name="PAL_STD.RES", palette_profile=profile)
                parts = dict(png_chunks(Path(result["images"][0]["output"]).read_bytes()))
                self.assertEqual(zlib.decompress(parts[b"IDAT"]), b"\0" + pixels)
                self.assertEqual(result["palette_profile"], profile)
                outputs.append(parts)
            self.assertNotEqual(outputs[0][b"PLTE"], outputs[1][b"PLTE"])
            self.assertEqual(outputs[0][b"tRNS"], outputs[1][b"tRNS"])
            self.assertEqual(outputs[0][b"PLTE"], source[8:])

    def test_cli_threads_palette_profile_to_image_and_map_exports(self):
        map_data = next(c.data for c in synthetic_fuzz_cases() if c.name == "TEST.MAP")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image, palette, map_path = root / "TEST.PIC", root / "PAL_STD.RES", root / "TEST.MAP"
            image.write_bytes(bitmap())
            palette.write_bytes(make_palette())
            map_path.write_bytes(map_data)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["export-images", str(image), str(root / "out"), "--palette", str(palette), "--palette-profile", "windows"]), 0)
                self.assertEqual(main(["render-map", str(map_path), str(root / "map.png"), "--palette", str(palette), "--palette-profile", "windows", "--scale", "1"]), 0)
            expected = bytes(c for row in palette_for_profile(make_palette(), "windows") for c in row)
            self.assertEqual(dict(png_chunks((root / "map.png").read_bytes()))[b"PLTE"], expected)
            self.assertEqual(dict(png_chunks((root / "out/000.png").read_bytes()))[b"PLTE"], expected)


if __name__ == "__main__":
    unittest.main()
