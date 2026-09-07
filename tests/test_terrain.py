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
from capplus_inspect.terrain import (
    TERRAIN_FULL_BOUNDS, TERRAIN_HILL_BASE, TERRAIN_LAND_BASE,
    TERRAIN_WATER_BASE, TerrainInitializationResult, apply_water_transitions,
    classify_terrain_tiles, initialize_runtime_terrain, initialize_terrain_cell_fields,
    parse_terrain_resource, shade_terrain_grid, terrain_length_table,
    update_terrain_rectangle,
)
from scripts.terrain_survey import (
    PARTIAL_BOUNDS, OriginalTerrainOracle, compare_result, compare_runtime_result,
    main as survey_main, partial_grids, read_bounded, survey, synthetic_grids,
)
from .helpers import make_dbf, make_map, make_palette, make_terrain_resource
from .test_images import png_chunks


GOLDENS = json.loads((Path(__file__).parent / "fixtures" / "terrain-v1.json").read_text())
RUNTIME_GOLDENS = json.loads(
    (Path(__file__).parent / "fixtures" / "terrain-runtime-v1.json").read_text()
)


def map_with_grid(grid: bytes, cities=()) -> bytes:
    raw = make_map(cities)
    return raw[:55] + grid + raw[380215:]


def png_pixels(path: Path) -> bytes:
    chunks = dict(png_chunks(path.read_bytes()))
    raw = zlib.decompress(chunks[b"IDAT"])
    return b"".join(raw[y * 241 + 1:(y + 1) * 241] for y in range(198))


def copied_rectangle(source: bytes, working: bytes, bounds: tuple[int, int, int, int]) -> bytes:
    left, top, right, bottom = bounds
    result = bytearray(working)
    for y in range(top, bottom + 1):
        start = (y * 240 + left) * 8
        end = (y * 240 + right + 1) * 8
        result[start:end] = source[start:end]
    return bytes(result)


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

    def test_partial_rectangles_match_both_original_functions(self):
        self.assertEqual([tuple(record["bounds"]) for record in GOLDENS["partial_rectangles"]],
                         list(PARTIAL_BOUNDS))
        for build in ("dos", "windows"):
            source = self.inputs["checker"]
            working = self.outputs[build, "ramp"]
            for record in GOLDENS["partial_rectangles"]:
                bounds = tuple(record["bounds"])
                with self.subTest(build=build, bounds=bounds):
                    prepared = copied_rectangle(source, working, bounds)
                    self.assertEqual(hashlib.sha256(prepared).hexdigest(),
                                     record["prepared_grid_sha256"])
                    actual = update_terrain_rectangle(source, working, bounds, profile=build)
                    self.assertEqual(hashlib.sha256(actual).hexdigest(),
                                     record["original_working_grid_sha256"])

    def test_partial_update_preserves_both_inputs_and_all_outside_bytes(self):
        bounds = (117, 96, 123, 102)
        source = bytearray(self.inputs["checker"])
        working = bytearray(self.outputs["dos", "ramp"])
        source_before, working_before = bytes(source), bytes(working)
        result = update_terrain_rectangle(source, working, bounds)
        self.assertEqual(source, source_before)
        self.assertEqual(working, working_before)
        left, top, right, bottom = bounds
        for index in range(47520):
            x, y = index % 240, index // 240
            cell = slice(index * 8, index * 8 + 8)
            if left <= x <= right and top <= y <= bottom:
                for offset in (2, 3, 5, 6, 7):
                    self.assertEqual(result[index * 8 + offset], source[index * 8 + offset])
            else:
                self.assertEqual(result[cell], working[cell])

    def test_full_bounds_partial_update_equals_full_reconstruction(self):
        source = self.inputs["signed_limits"]
        for build in ("dos", "windows"):
            with self.subTest(build=build):
                actual = update_terrain_rectangle(source, bytes(MAP_GRID_SIZE),
                                                  TERRAIN_FULL_BOUNDS, profile=build)
                self.assertEqual(actual, self.outputs[build, "signed_limits"])

    def test_partial_update_requires_preconverted_outside_heights(self):
        working = bytearray(self.outputs["dos", "ramp"])
        struct.pack_into("<h", working, 0, 256)
        with self.assertRaisesRegex(FormatError, "outside.*converted"):
            update_terrain_rectangle(self.inputs["checker"], working, (120, 99, 120, 99))

    def test_partial_update_rejects_bad_lengths_bounds_and_profile(self):
        source, working = self.inputs["checker"], self.outputs["dos", "ramp"]
        for bad in ((), (0, 0, 1), [0, 0, 1, 1], (False, 0, 1, 1),
                    (-1, 0, 1, 1), (0, -1, 1, 1), (2, 0, 1, 1),
                    (0, 2, 1, 1), (0, 0, 240, 1), (0, 0, 1, 198)):
            with self.subTest(bounds=bad), self.assertRaises(FormatError):
                update_terrain_rectangle(source, working, bad)  # type: ignore[arg-type]
        for bad_source, bad_working in ((source[:-1], working), (source, working + b"\0")):
            with self.assertRaises(FormatError):
                update_terrain_rectangle(bad_source, bad_working, (0, 0, 1, 1))
        with self.assertRaises(FormatError):
            update_terrain_rectangle(source, working, (0, 0, 1, 1), profile="unknown")

    def test_partial_probe_inputs_are_stable_and_complete(self):
        for build in ("dos", "windows"):
            probes = list(partial_grids(build))
            self.assertEqual([record[3] for record in probes], list(PARTIAL_BOUNDS))
            self.assertEqual(len({record[0] for record in probes}), len(PARTIAL_BOUNDS))
            self.assertTrue(all(record[1] == self.inputs["checker"] for record in probes))
            self.assertTrue(all(record[2] == self.outputs[build, "ramp"] for record in probes))

    def test_grid_size_and_profile_fail_explicitly(self):
        for size in (0, 8, MAP_GRID_SIZE - 1, MAP_GRID_SIZE + 1):
            with self.subTest(size=size), self.assertRaises(FormatError):
                shade_terrain_grid(bytes(size))
        for profile in ("", "DOS", "unknown"):
            with self.subTest(profile=profile), self.assertRaises(FormatError):
                shade_terrain_grid(self.inputs["flat_water"], profile=profile)


class RuntimeTerrainInitializationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resource = make_terrain_resource()
        cls.patterns = parse_terrain_resource(cls.resource)
        cls.source_grids = dict(synthetic_grids())

    def test_synthetic_resource_normalizes_groups_and_base_ids(self):
        self.assertEqual(len(self.patterns), 49)
        self.assertEqual(self.patterns[0].corners, (71, 71, 71, 71))
        self.assertEqual(self.patterns[0].additional_variants, 4)
        self.assertEqual(self.patterns[19].corners, (72, 72, 72, 72))
        self.assertEqual(self.patterns[19].additional_variants, 11)
        self.assertEqual(self.patterns[45].corners, (83, 83, 83, 83))
        self.assertEqual(self.patterns[45].additional_variants, 3)
        self.assertEqual(self.patterns[1].probability, 5)
        self.assertEqual(self.patterns[1].filename, "SYN0001")

    def test_classification_thresholds_replace_only_word_zero(self):
        values = (-32768, 0, 1, 214, 215, 32767)
        source = bytearray(struct.pack("<h6B", 1, 2, 3, 4, 5, 6, 7) * 47520)
        for index, value in enumerate(values):
            struct.pack_into("<h", source, index * 8, value)
        before = bytes(source)
        result = classify_terrain_tiles(source)
        self.assertEqual(source, before)
        expected = (TERRAIN_WATER_BASE, TERRAIN_WATER_BASE,
                    TERRAIN_LAND_BASE, TERRAIN_LAND_BASE,
                    TERRAIN_HILL_BASE, TERRAIN_HILL_BASE)
        self.assertEqual(tuple(struct.unpack_from("<H", result, i * 8)[0]
                               for i in range(len(values))), expected)
        for offset in range(2, 8):
            self.assertEqual(result[offset::8], before[offset::8])

    def test_single_water_cell_builds_all_eight_corner_transitions(self):
        grid = bytearray(struct.pack("<H6B", TERRAIN_LAND_BASE, 2, 3, 4, 5, 6, 7) * 47520)
        cx, cy = 120, 99
        struct.pack_into("<H", grid, (cy * 240 + cx) * 8, TERRAIN_WATER_BASE)
        result = apply_water_transitions(grid, self.patterns)
        expected = {
            (-1, 0): "GSGS", (1, 0): "SGSG", (0, -1): "GGSS", (0, 1): "SSGG",
            (-1, -1): "GGGS", (1, -1): "GGSG", (-1, 1): "GSGG", (1, 1): "SGGG",
        }
        for (dx, dy), corners in expected.items():
            offset = ((cy + dy) * 240 + cx + dx) * 8
            tile = struct.unpack_from("<H", result, offset)[0]
            self.assertEqual(bytes(self.patterns[tile - 0x2000].corners).decode(), corners)
            self.assertEqual(result[offset + 2:offset + 8], grid[offset + 2:offset + 8])

    def test_runtime_outputs_match_original_function_hashes(self):
        self.assertEqual(RUNTIME_GOLDENS["terrain_resource_sha256"],
                         hashlib.sha256(self.resource).hexdigest())
        self.assertEqual(len(RUNTIME_GOLDENS["grids"]), 12)
        for record in RUNTIME_GOLDENS["grids"]:
            build, name, seed = record["build"], record["name"], record["initial_rng_state"]
            working = shade_terrain_grid(self.source_grids[name], profile=build)
            with self.subTest(build=build, name=name):
                self.assertEqual(hashlib.sha256(working).hexdigest(),
                                 record["source_working_grid_sha256"])
                result = initialize_runtime_terrain(working, self.resource, seed, profile=build)
                self.assertEqual(hashlib.sha256(result.grid).hexdigest(),
                                 record["original_runtime_grid_sha256"])
                self.assertEqual(result.rng_state, record["final_rng_state"])
                self.assertEqual(result.climate_center_row, record["climate_center_row"])
                self.assertEqual(result.random_calls, record["random_calls"])

    def test_generated_field_ranges_and_preservation(self):
        working = shade_terrain_grid(self.source_grids["checker"])
        classified = classify_terrain_tiles(working)
        transitioned = apply_water_transitions(classified, self.patterns)
        mutable = bytearray(transitioned)
        before = bytes(mutable)
        result = initialize_terrain_cell_fields(mutable, 0x12345678)
        self.assertEqual(mutable, before)
        for offset in (0, 1, 2, 3, 4):
            self.assertEqual(result.grid[offset::8], before[offset::8])
        self.assertLessEqual(max(result.grid[5::8]), 4)
        self.assertLessEqual(max(result.grid[6::8]), 3)
        water = [index for index in range(47520)
                 if struct.unpack_from("<H", transitioned, index * 8)[0] == TERRAIN_WATER_BASE]
        self.assertTrue(water)
        self.assertTrue(all(result.grid[index * 8 + 7] == before[index * 8 + 7]
                            for index in water))
        self.assertEqual(result.field_random_calls, 52_273 + 47_520 - len(water))

    def test_profiles_retain_the_compiler_signed_char_difference(self):
        working = shade_terrain_grid(self.source_grids["flat_land"])
        dos = initialize_runtime_terrain(working, self.resource, 0, profile="dos")
        windows = initialize_runtime_terrain(working, self.resource, 0, profile="windows")
        differences = [index for index, pair in enumerate(zip(dos.grid, windows.grid))
                       if pair[0] != pair[1]]
        self.assertTrue(differences)
        self.assertEqual({index % 8 for index in differences}, {7})
        self.assertEqual(dos.rng_state, windows.rng_state)

    def test_malformed_resources_and_runtime_inputs_fail_explicitly(self):
        wrong = make_dbf([("OTHER", "C", 1, 0)], [["X"]])
        with self.assertRaisesRegex(FormatError, "field layout"):
            parse_terrain_resource(wrong)
        deleted = bytearray(self.resource)
        header_length = struct.unpack_from("<H", deleted, 8)[0]
        deleted[header_length] = ord("*")
        with self.assertRaisesRegex(FormatError, "deleted"):
            parse_terrain_resource(bytes(deleted))
        for bad in (b"", bytes(8), bytes(380159), bytes(380161), "bad"):
            with self.subTest(grid=type(bad).__name__, size=len(bad)), self.assertRaises(FormatError):
                classify_terrain_tiles(bad)  # type: ignore[arg-type]
        grid = bytes(380160)
        for state in (-1, 0x100000000, True, "0"):
            with self.subTest(state=state), self.assertRaises(FormatError):
                initialize_terrain_cell_fields(grid, state)  # type: ignore[arg-type]
        with self.assertRaises(FormatError):
            initialize_terrain_cell_fields(grid, 0, profile="unknown")


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
        runtime = TerrainInitializationResult(raw, 1, 2, 3, 4)
        expected = {"grid": raw, "rng_state": 1, "climate_center_row": 2}
        self.assertTrue(compare_runtime_result(raw, expected, runtime)["passed"])
        expected["rng_state"] = 2
        self.assertFalse(compare_runtime_result(raw, expected, runtime)["passed"])
        expected["grid"] = raw[:-1]
        with self.assertRaises(InspectError):
            compare_runtime_result(raw, expected, runtime)

    def test_bounded_reads_and_map_count(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bounded"
            path.write_bytes(bytes(9))
            self.assertEqual(read_bounded(path, 9), bytes(9))
            with self.assertRaises(InspectError):
                read_bounded(path, 8)
        for executables, paths in (({"dos": b""}, []), ({"dos": b"", "windows": b""}, [Path("unused")] * 65)):
            with self.assertRaises(InspectError):
                survey(executables, paths, make_terrain_resource())

    def test_invalid_or_duplicate_maps_fail_before_emulation(self):
        with tempfile.TemporaryDirectory() as directory, patch("scripts.terrain_survey.OriginalTerrainOracle") as oracle:
            path = Path(directory) / "TEST.MAP"
            path.write_bytes(make_map())
            with self.assertRaisesRegex(InspectError, "collide"):
                survey({"dos": b"", "windows": b""}, [path, path], make_terrain_resource())
            path.write_bytes(make_map(terrain=False))
            with self.assertRaisesRegex(InspectError, "no terrain"):
                survey({"dos": b"", "windows": b""}, [path], make_terrain_resource())
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
