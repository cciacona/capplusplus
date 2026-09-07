from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

from capplus_inspect.cli import main
from capplus_inspect.errors import FormatError, InspectError
from capplus_inspect.maps import MAP_GRID_SIZE, render_map
from capplus_inspect.palette import palette_for_profile
from capplus_inspect.terrain import shade_terrain_grid, terrain_length_table
from scripts.terrain_survey import (
    OriginalTerrainOracle, compare_result, main as survey_main, read_bounded,
    survey, synthetic_grids,
)
from .helpers import make_map, make_palette
from .test_images import png_chunks


GOLDENS = json.loads((Path(__file__).parent / "fixtures" / "terrain-v1.json").read_text())


def map_with_grid(grid: bytes, cities=()) -> bytes:
    raw = make_map(cities)
    return raw[:55] + grid + raw[380215:]


def png_pixels(path: Path) -> bytes:
    chunks = dict(png_chunks(path.read_bytes()))
    raw = zlib.decompress(chunks[b"IDAT"])
    return b"".join(raw[y * 241 + 1:(y + 1) * 241] for y in range(198))


class TerrainReconstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = dict(synthetic_grids())
        cls.outputs = {(build, name): shade_terrain_grid(grid, profile=build)
                       for build in ("dos", "windows") for name, grid in cls.inputs.items()}

    def test_length_tables_match_original_function_hashes(self):
        for build, expected in GOLDENS["table_sha256"].items():
            table = terrain_length_table(build)
            self.assertEqual(len(table), 1025)
            self.assertEqual(hashlib.sha256(struct.pack("<1025h", *table)).hexdigest(), expected)
        dos, windows = terrain_length_table("dos"), terrain_length_table("windows")
        self.assertEqual([i for i, pair in enumerate(zip(dos, windows)) if pair[0] != pair[1]],
                         [16, 225, 241, 400, 416, 800, 816, 869, 972, 997])

    def test_six_procedural_grids_match_original_code_in_both_profiles(self):
        self.assertEqual({r["name"] for r in GOLDENS["grids"]}, set(self.inputs))
        self.assertEqual(len(GOLDENS["grids"]), 12)
        for record in GOLDENS["grids"]:
            name, build = record["name"], record["build"]
            with self.subTest(name=name, build=build):
                self.assertEqual(hashlib.sha256(self.inputs[name]).hexdigest(), record["source_grid_sha256"])
                self.assertEqual(hashlib.sha256(self.outputs[build, name]).hexdigest(),
                                 record["original_working_grid_sha256"])

    def test_flat_water_land_and_peak_have_verified_height_and_shade(self):
        for build in ("dos", "windows"):
            for name, height, shade in (("flat_water", 0, 240), ("flat_land", 19, 91),
                                        ("flat_peak", 255, 110)):
                with self.subTest(name=name, build=build):
                    self.assertEqual(self.outputs[build, name],
                                     struct.pack("<h6B", height, 2, 3, shade, 5, 6, 7) * 47520)

    def test_opaque_bytes_and_mutable_caller_input_are_preserved(self):
        source = bytearray(self.inputs["ramp"])
        # Each opaque field exercises all 256 values, including nonzero corners.
        for offset in (2, 3, 5, 6, 7):
            source[offset::8] = bytes(i % 256 for i in range(47520))
        before = bytes(source)
        result = shade_terrain_grid(source)
        self.assertEqual(source, before)
        for offset in (2, 3, 5, 6, 7):
            self.assertEqual(result[offset::8], source[offset::8])

    def test_full_rectangle_corners_copy_diagonal_shades_only(self):
        result = self.outputs["dos", "ramp"]
        for border, interior in ((0, 241), (239, 478), (47280, 47041), (47519, 47278)):
            self.assertEqual(result[border * 8 + 4], result[interior * 8 + 4])
            self.assertEqual(result[border * 8 + 2:border * 8 + 4],
                             self.inputs["ramp"][border * 8 + 2:border * 8 + 4])

    def test_grid_size_and_profile_fail_explicitly(self):
        for size in (0, 8, MAP_GRID_SIZE - 1, MAP_GRID_SIZE + 1):
            with self.subTest(size=size), self.assertRaises(FormatError):
                shade_terrain_grid(bytes(size))
        for profile in ("", "DOS", "unknown"):
            with self.subTest(profile=profile), self.assertRaises(FormatError):
                shade_terrain_grid(self.inputs["flat_water"], profile=profile)


class TerrainPreviewTests(unittest.TestCase):
    def setUp(self):
        self.grid = struct.pack("<h6B", 128, 2, 3, 4, 5, 6, 7) * 47520

    def test_terrain_and_palette_profiles_are_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            for profile in ("source", "windows"):
                output = Path(directory) / f"{profile}.png"
                result = render_map(map_with_grid(self.grid), make_palette(), output, scale=1,
                                    mark_cities=False, terrain_profile="windows", palette_profile=profile)
                self.assertEqual(png_pixels(output), bytes([91]) * 47520)
                colors = bytes(c for color in palette_for_profile(make_palette(), profile) for c in color)
                self.assertEqual(dict(png_chunks(output.read_bytes()))[b"PLTE"], colors)
                self.assertEqual(result["terrain_profile"], "windows")
                self.assertEqual(result["terrain_model_version"], 1)
                self.assertFalse(result["whole_game_rendering_validated"])
                expected = next(r for r in GOLDENS["grids"] if r["build"] == "windows" and r["name"] == "flat_land")
                self.assertEqual(result["terrain_working_grid_sha256"], expected["original_working_grid_sha256"])

    def test_source_preview_default_stays_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "source.png"
            result = render_map(map_with_grid(self.grid), make_palette(), output, scale=1, mark_cities=False)
            self.assertEqual(png_pixels(output), bytes([128]) * 47520)
            self.assertIsNone(result["terrain_profile"])
            self.assertIsNone(result["terrain_model_version"])
            self.assertIsNone(result["terrain_working_grid_sha256"])

    def test_city_overlay_is_applied_to_derived_pixels(self):
        city = struct.pack("<HHI21s", 120, 99, 12345, b"Synthetic Town")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "cities.png"
            result = render_map(map_with_grid(self.grid, (city,)), make_palette(), output,
                                scale=1, terrain_profile="dos")
            pixels = png_pixels(output)
            self.assertEqual(pixels[99 * 240 + 120], 255)
            self.assertEqual(pixels[99 * 240 + 122], 0)
            self.assertEqual(pixels[0], 91)
            self.assertEqual(result["city_markers"], 1)

    def test_cli_text_and_json_route_profiles_and_protect_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, palette, output = root / "TEST.MAP", root / "PAL.RES", root / "map.png"
            source.write_bytes(map_with_grid(self.grid))
            palette.write_bytes(make_palette())
            args = ["render-map", str(source), str(output), "--palette", str(palette),
                    "--terrain-profile", "dos", "--palette-profile", "windows", "--scale", "1", "--no-cities"]
            with contextlib.redirect_stdout(io.StringIO()) as capture:
                self.assertEqual(main(args + ["--json"]), 0)
            report = json.loads(capture.getvalue())
            self.assertEqual(report["terrain_profile"], "dos")
            self.assertEqual(report["palette_profile"], "windows")
            before = output.read_bytes()
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertNotEqual(main(args), 0)
            self.assertEqual(output.read_bytes(), before)
            with contextlib.redirect_stdout(io.StringIO()) as capture:
                self.assertEqual(main(args + ["--force"]), 0)
            self.assertIn("derived terrain preview (dos)", capture.getvalue())
            source.write_bytes(make_map(terrain=False))
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertNotEqual(main(args + ["--force"]), 0)
            self.assertEqual(output.read_bytes(), before)


class TerrainSurveyTests(unittest.TestCase):
    def test_unknown_executables_are_rejected_before_optional_import(self):
        with patch.dict("sys.modules", {"unicorn": None}):
            for build in ("dos", "windows", "other"):
                with self.subTest(build=build), self.assertRaisesRegex(InspectError, "exact unmodified"):
                    OriginalTerrainOracle(b"synthetic", build)

    def test_unsupported_control_word_is_rejected_before_emulation(self):
        with patch("scripts.terrain_survey.REFERENCE_HASHES", {"dos": hashlib.sha256(b"synthetic").hexdigest()}):
            with self.assertRaisesRegex(InspectError, "control word"):
                OriginalTerrainOracle(b"synthetic", "dos", control_word=0)

    def test_comparison_distinguishes_mismatch_from_opaque_corruption(self):
        raw = bytes(MAP_GRID_SIZE)
        changed = bytearray(raw)
        changed[4] = 1
        result = compare_result(raw, raw, bytes(changed))
        self.assertFalse(result["passed"])
        self.assertEqual(result["differing_bytes"], 1)
        self.assertEqual(result["first_differing_offset"], 4)
        changed[2] = 1
        result = compare_result(raw, bytes(changed), bytes(changed))
        self.assertEqual(result["differing_bytes"], 0)
        self.assertFalse(result["opaque_bytes_preserved"])
        self.assertFalse(result["passed"])
        with self.assertRaises(InspectError):
            compare_result(raw, raw, raw[:-1])

    def test_bounded_reads_and_map_count(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bounded"
            path.write_bytes(bytes(9))
            self.assertEqual(read_bounded(path, 9), bytes(9))
            with self.assertRaises(InspectError):
                read_bounded(path, 8)
        for executables, paths in (({"dos": b""}, []), ({"dos": b"", "windows": b""}, [Path("unused")] * 65)):
            with self.assertRaises(InspectError):
                survey(executables, paths)

    def test_invalid_or_duplicate_maps_fail_before_emulation(self):
        with tempfile.TemporaryDirectory() as directory, patch("scripts.terrain_survey.OriginalTerrainOracle") as oracle:
            path = Path(directory) / "TEST.MAP"
            path.write_bytes(make_map())
            with self.assertRaisesRegex(InspectError, "collide"):
                survey({"dos": b"", "windows": b""}, [path, path])
            path.write_bytes(make_map(terrain=False))
            with self.assertRaisesRegex(InspectError, "no terrain"):
                survey({"dos": b"", "windows": b""}, [path])
            oracle.assert_not_called()

    def test_survey_refuses_existing_output_before_reading_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            output.write_text("keep")
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                survey_main(["--dos-exe", "missing", "--windows-exe", "missing", "--output", str(output)])
            self.assertEqual(error.exception.code, 2)
            self.assertEqual(output.read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
