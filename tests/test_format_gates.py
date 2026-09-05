from __future__ import annotations

import json
import io
import struct
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path

from capplus_inspect.errors import FormatError
from capplus_inspect.cli import main
from capplus_inspect.fuzzing import (
    MAX_FUZZ_ITERATIONS,
    run_synthetic_fuzz_campaign,
    synthetic_fuzz_cases,
)
from capplus_inspect.roundtrip import (
    RoundTripDocument,
    RoundTripRegion,
    build_roundtrip_document,
    validate_roundtrip_bytes,
    validate_roundtrip_corpus,
)
from capplus_inspect.saves import (
    FIXED_PAYLOAD_SIZES,
    SECTION_MARKERS,
    compare_saves,
)
from capplus_inspect.schema_catalog import (
    REQUIRED_FORMAT_IDS,
    load_catalog_schema,
    load_format_catalog,
    validate_format_catalog,
)


class SchemaCatalogTests(unittest.TestCase):
    def test_catalog_covers_every_supported_format_and_all_inferences(self) -> None:
        catalog = load_format_catalog()
        summary = validate_format_catalog(catalog)
        self.assertEqual(summary["format_count"], len(REQUIRED_FORMAT_IDS))
        self.assertGreater(summary["field_count"], 40)
        self.assertGreater(summary["inferred_field_count"], 0)
        self.assertEqual(
            {entry["id"] for entry in catalog["formats"]}, REQUIRED_FORMAT_IDS
        )
        for entry in catalog["formats"]:
            for field in entry["fields"]:
                if field["status"] == "inferred":
                    self.assertTrue(field["observation_methods"])
                    self.assertIn(field["confidence"], {"low", "medium", "high"})
                    self.assertTrue(field["notes"])

    def test_catalog_meta_schema_is_bundled_and_versioned(self) -> None:
        schema = load_catalog_schema()
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(schema["properties"]["catalog_version"]["const"], 1)
        json.dumps(schema)

    def test_catalog_rejects_missing_provenance(self) -> None:
        catalog = load_format_catalog()
        inferred = next(
            field
            for entry in catalog["formats"]
            for field in entry["fields"]
            if field["status"] == "inferred"
        )
        inferred.pop("confidence")
        with self.assertRaises(FormatError):
            validate_format_catalog(catalog)


class RoundTripTests(unittest.TestCase):
    def test_all_synthetic_non_save_formats_round_trip_exactly(self) -> None:
        formats = set()
        for case in synthetic_fuzz_cases():
            if case.name.lower().endswith(".sav"):
                continue
            result = validate_roundtrip_bytes(case.data, case.name)
            self.assertTrue(result["byte_identical"], case.name)
            self.assertEqual(result["source_sha256"], result["reconstructed_sha256"])
            formats.add(result["source_format"])
        self.assertIn("capitalism_plus_game_set", formats)
        self.assertIn("capitalism_plus_map", formats)
        self.assertIn("capitalism_plus_executable", formats)
        self.assertIn("direct_indexed_image", formats)

    def test_encoder_rejects_gap_between_regions(self) -> None:
        document = RoundTripDocument(
            source_format="test",
            coverage="structural",
            source_size=2,
            regions=(RoundTripRegion("late", 1, b"x"),),
        )
        with self.assertRaises(FormatError):
            document.encode()

    def test_regions_are_real_writer_inputs_not_a_whole_file_alias(self) -> None:
        case = next(case for case in synthetic_fuzz_cases() if case.name == "PAL_STD.RES")
        document = build_roundtrip_document(case.data, case.name)
        self.assertEqual([region.name for region in document.regions], ["header", "rgb_table"])
        changed_header = replace(document.regions[0], data=b"X" + document.regions[0].data[1:])
        changed_document = replace(
            document, regions=(changed_header, *document.regions[1:])
        )
        self.assertNotEqual(changed_document.encode(), case.data)

    def test_save_round_trip_writer_is_intentionally_disabled(self) -> None:
        case = next(case for case in synthetic_fuzz_cases() if case.name == "TEST.SAV")
        with self.assertRaisesRegex(FormatError, "normalization comparator"):
            build_roundtrip_document(case.data, case.name)

    def test_directory_corpus_report_is_exact_and_non_destructive(self) -> None:
        game_set = next(case for case in synthetic_fuzz_cases() if case.name == "TEST.SET")
        palette = next(case for case in synthetic_fuzz_cases() if case.name == "PAL_STD.RES")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "GAMESET").mkdir()
            (root / "RESOURCE").mkdir()
            (root / "GAMESET" / "1STD.SET").write_bytes(game_set.data)
            (root / "RESOURCE" / "PAL_STD.RES").write_bytes(palette.data)
            before = {
                path: path.read_bytes() for path in root.rglob("*") if path.is_file()
            }
            result = validate_roundtrip_corpus(root)
            after = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(result["file_count"], 2)
        self.assertEqual(result["byte_identical_count"], 2)
        self.assertTrue(result["all_byte_identical"])

    def test_zip_corpus_uses_the_same_selection_and_round_trip_gate(self) -> None:
        game_set = next(case for case in synthetic_fuzz_cases() if case.name == "TEST.SET")
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "installation.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("Wrapped/GAMESET/1STD.SET", game_set.data)
            result = validate_roundtrip_corpus(archive)
        self.assertEqual(result["source_kind"], "zip")
        self.assertEqual(result["detected_root"], "wrapped")
        self.assertEqual(result["file_count"], 1)
        self.assertTrue(result["all_byte_identical"])


class FuzzHarnessTests(unittest.TestCase):
    def test_fixed_campaign_is_reproducible(self) -> None:
        left = run_synthetic_fuzz_campaign(iterations=128, seed=0x1234)
        right = run_synthetic_fuzz_campaign(iterations=128, seed=0x1234)
        self.assertEqual(left, right)
        self.assertEqual(left["unexpected_failures"], 0)
        self.assertEqual(left["accepted"] + left["rejected"], 128)
        self.assertEqual(
            left["transcript_sha256"],
            "19e62090312d34d0fb464481a12192893562463fe28debf98537f97c1f476ff3",
        )

    def test_campaign_bounds_are_enforced(self) -> None:
        for iterations in (0, MAX_FUZZ_ITERATIONS + 1):
            with self.assertRaises(ValueError):
                run_synthetic_fuzz_campaign(iterations=iterations)
        with self.assertRaises(ValueError):
            run_synthetic_fuzz_campaign(iterations=1, seed=-1)


class GateCliTests(unittest.TestCase):
    def test_schema_and_fuzz_commands_emit_versioned_json(self) -> None:
        for arguments, expected_format in (
            (["schema-catalog", "--json"], "capitalism_plus_binary_format_catalog"),
            (
                ["fuzz", "--iterations", "8", "--seed", "7", "--json"],
                "capitalism_plus_fuzz_campaign",
            ),
        ):
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(arguments), 0)
            result = json.loads(output.getvalue())
            self.assertEqual(result["format"], expected_format)
            version_key = (
                "schema_version"
                if expected_format.endswith("campaign")
                else "report_schema_version"
            )
            self.assertEqual(result[version_key], 1)

    def test_roundtrip_command_routes_a_direct_file(self) -> None:
        palette = next(case for case in synthetic_fuzz_cases() if case.name == "PAL_STD.RES")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / palette.name
            path.write_bytes(palette.data)
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["roundtrip", str(path), "--json"]), 0)
        result = json.loads(output.getvalue())
        self.assertTrue(result["byte_identical"])
        self.assertEqual(result["source_format"], "capitalism_plus_palette")


def _normalization_save(*, pointer_a: int, pointer_b: int, float_ulps: tuple[int, ...]) -> bytes:
    metadata = bytearray(100)
    metadata[:12] = b"TEST_001.SAV"
    struct.pack_into("<I", metadata, 16, 2_447_893)
    metadata[20:32] = b"Test Company"
    metadata[68:81] = b"Test Scenario"
    settings = b"TEST.SCT\0"
    output = bytearray(struct.pack("<H", len(metadata)))
    output.extend(metadata)
    output.extend(struct.pack("<hH", 100, len(settings)))
    output.extend(settings)

    town = bytearray(371)
    town[2:11] = b"Test Town"
    struct.pack_into("<II", town, 0x4B, pointer_a, pointer_b)
    dynamic = bytearray(44)
    struct.pack_into("<IIIII", dynamic, 0, 1, 100, 0, 1, 238)
    market = bytearray(238)
    struct.pack_into("<HH", market, 0, 1, 2)
    for index, offset in enumerate((0x7C, 0x80, 0x84, 0x88)):
        struct.pack_into("<I", market, offset, 0x3F800000 + float_ulps[index])
    town_payload = (
        struct.pack("<HHIH", 100, 100, 2_447_893, 1)
        + struct.pack("<H", 371)
        + town
        + struct.pack("<H", 168)
        + bytes(168)
        + struct.pack("<H", 364)
        + bytes(364)
        + struct.pack("<H", 44)
        + dynamic
        + struct.pack("<H", 238)
        + market
    )

    for marker in SECTION_MARKERS:
        output.extend(struct.pack("<H", marker))
        if marker == 0x1001:
            payload = struct.pack("<I", 0x12345678)
        elif marker == 0x101B:
            payload = town_payload
        elif marker in FIXED_PAYLOAD_SIZES:
            payload = bytes(FIXED_PAYLOAD_SIZES[marker])
        elif marker == 0x101D:
            payload = bytes(6_613)
        else:
            payload = b""
        output.extend(payload)
    return bytes(output)


class SaveNormalizationTests(unittest.TestCase):
    def test_policy_classifies_only_registered_pointer_and_float_drift(self) -> None:
        left = _normalization_save(
            pointer_a=0x11223344,
            pointer_b=0x55667788,
            float_ulps=(0, 0, 0, 0),
        )
        right = _normalization_save(
            pointer_a=0xAABBCCDD,
            pointer_b=0xDDEEFF00,
            float_ulps=(1, 2, 3, 4),
        )
        result = compare_saves(left, right)
        normalization = result["normalization"]
        self.assertTrue(normalization["policy_applicable"])
        self.assertEqual(normalization["policy"]["version"], 1)
        self.assertEqual(len(normalization["policy"]["rules"]), 2)
        self.assertTrue(normalization["evaluation"]["all_differences_explained"])
        self.assertEqual(
            normalization["evaluation"]["unclassified_same_position_differing_bytes"], 0
        )
        self.assertEqual(result["town_array"]["transient_pointer_bytes_different"], 8)
        self.assertEqual(result["town_array"]["changed_known_float_fields"], 4)
        self.assertEqual(result["town_array"]["maximum_known_float_ulp_distance"], 4)
        self.assertTrue(result["town_array"]["known_float_drift_within_observed_tolerance"])

    def test_float_drift_over_observed_tolerance_is_not_permitted(self) -> None:
        left = _normalization_save(pointer_a=0, pointer_b=0, float_ulps=(0, 0, 0, 0))
        right = _normalization_save(pointer_a=0, pointer_b=0, float_ulps=(5, 0, 0, 0))
        result = compare_saves(left, right)
        self.assertTrue(result["normalization"]["policy_applicable"])
        self.assertFalse(
            result["normalization"]["evaluation"][
                "known_float_drift_within_observed_tolerance"
            ]
        )
        self.assertEqual(result["town_array"]["known_float_fields_over_observed_tolerance"], 1)


if __name__ == "__main__":
    unittest.main()
