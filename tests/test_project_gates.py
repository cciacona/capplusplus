from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

from capplus_inspect.known import CORE_FILE_SHA256
from scripts.package_check import extract_sdist
from scripts.project_gates import (
    ROOT, MAX_TRACKED_BYTES, GateError, boundary_gate, boundary_reasons,
    classify_path, inventory_report, ledger_gate, load_json, normalized_path,
    source_version, validate_experiment, validate_schema, version_gate,
)


class SpecificationTests(unittest.TestCase):
    def setUp(self):
        self.content = load_json(ROOT / "specs/content-coverage-v1.json")
        self.vector = load_json(ROOT / "tests/fixtures/experiments/synthetic-state-delta.json")

    def test_ledgers_reconcile_without_claiming_completion(self):
        result = ledger_gate()
        self.assertEqual(result["enumerated_sources"], {"shared_core": 72, "gam_image": 1001})
        self.assertEqual(result["retail_unclassified_files"], 531)
        self.assertEqual(result["families"], 36)
        self.assertEqual(result["features"], 43)
        self.assertEqual(result["manual_crosswalk"], "pending")

    def test_every_known_core_path_has_one_family(self):
        report = inventory_report(list(CORE_FILE_SHA256), self.content, "shared_core")
        self.assertTrue(report["complete_inventory"])
        self.assertEqual(report["unclassified_count"], 0)

    def test_nested_extensionless_and_case_normalization(self):
        families = self.content["families"]
        self.assertEqual(classify_path("TUTORIAL\\LESSON\\PAGE1", families), ["tutorial_extensionless"])
        self.assertEqual(classify_path("RESOURCE/I_CURSOR.RES", families), ["cursor_images"])
        self.assertEqual(classify_path("scenario/test.scp", families), ["scenario_scp"])

    def test_inventory_missing_extra_and_unknown_fail_completeness(self):
        paths = list(CORE_FILE_SHA256)
        for candidate in (paths[1:], paths + ["new/content.xyz"], paths + ["maps/extra.map"]):
            with self.subTest(paths=len(candidate)):
                self.assertFalse(inventory_report(candidate, self.content, "shared_core")["complete_inventory"])

    def test_inventory_rejects_duplicate_collision_and_ambiguity(self):
        for candidate in (["maps/a.map", "maps/a.map"], ["maps/a.map", "MAPS/A.MAP"]):
            with self.assertRaises(GateError):
                inventory_report(candidate, self.content, "shared_core")
        self.content["families"].append({**self.content["families"][0], "id": "duplicate_selector"})
        with self.assertRaises(GateError):
            inventory_report(["gameset/a.set"], self.content, "shared_core")

    def test_paths_reject_traversal_absolute_and_empty(self):
        for value in ("", "/data", "../data", "a/../b", "a//b", "C:\\data", "a/./b"):
            with self.subTest(value=value), self.assertRaises(GateError):
                normalized_path(value)

    def test_schema_rejects_wrong_enum_extra_key_and_type(self):
        schema = load_json(ROOT / "specs/experiment-v1.schema.json")
        for patch in ({"kind": "replay"}, {"schema_version": True}, {"extra": 1}):
            with self.subTest(patch=patch), self.assertRaises(GateError):
                validate_schema({**self.vector, **patch}, schema)
        with self.assertRaises(GateError):
            validate_schema(1, {"type": "integer", "multipleOf": 2})

    def test_json_rejects_duplicate_keys_and_nonfinite_numbers(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "test.json"
            for value in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}'):
                path.write_text(value, encoding="utf-8")
                with self.subTest(value=value), self.assertRaises(GateError):
                    load_json(path)

    def test_ledger_rejects_false_completion_missing_evidence_and_bad_refs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for directory in ("specs", "docs", "tests/fixtures"):
                shutil.copytree(ROOT / directory, root / directory)
            for name in ("ROADMAP.md", "CLEAN_ROOM.md"):
                shutil.copy2(ROOT / name, root / name)
            content_path = root / "specs/content-coverage-v1.json"
            parity_path = root / "specs/feature-parity-v1.json"
            content = load_json(content_path)
            parity = load_json(parity_path)
            mutations = []
            changed = copy.deepcopy(content)
            changed["retail_reconciliation"]["status"] = "enumerated"
            mutations.append((content_path, changed))
            changed = copy.deepcopy(content)
            changed["families"][0]["observed_counts"]["shared_core"] += 1
            mutations.append((content_path, changed))
            for key, value in (("evidence", ["docs/nonexistent.md"]),
                               ("content_families", ["nonexistent"]),
                               ("status", {**parity["features"][0]["status"], "simulation": "validated"})):
                changed = copy.deepcopy(parity)
                changed["features"][0][key] = value
                mutations.append((parity_path, changed))
            changed = copy.deepcopy(parity)
            changed["manual_crosswalk_status"] = "complete"
            mutations.append((parity_path, changed))
            for path, value in mutations:
                with self.subTest(file=path.name):
                    content_path.write_text(json.dumps(content), encoding="utf-8")
                    parity_path.write_text(json.dumps(parity), encoding="utf-8")
                    path.write_text(json.dumps(value), encoding="utf-8")
                    with self.assertRaises(GateError):
                        ledger_gate(root)

    def test_synthetic_vector_is_consistent(self):
        validate_experiment(self.vector)

    def test_original_observation_requires_hashes_and_provenance(self):
        self.vector.update(kind="original_observation", profile="classic")
        self.vector["private_artifacts"]["required"] = True
        with self.assertRaises(GateError):
            validate_experiment(self.vector)
        self.vector["provenance"]["method"] = "controlled_game_experiment"
        with self.assertRaises(GateError):
            validate_experiment(self.vector)
        # Hash-shaped invented values test consistency, not original evidence.
        participant = self.vector["participants"][0]
        participant.update(executable_sha256="a" * 64, initial_save_sha256="b" * 64)
        self.vector["observations"][0]["save_sha256"] = "b" * 64
        self.vector["observations"][1]["save_sha256"] = "c" * 64
        validate_experiment(self.vector)
        self.vector["observations"][1]["save_sha256"] = None
        with self.assertRaises(GateError):
            validate_experiment(self.vector)

    def test_synthetic_cannot_claim_classic_observation(self):
        self.vector["profile"] = "classic"
        with self.assertRaises(GateError):
            validate_experiment(self.vector)

    def test_action_order_duplicates_and_duration(self):
        original = copy.deepcopy(self.vector)
        for actions in ([original["actions"][0]] * 2,
                        [{**original["actions"][0], "sequence": 1}, original["actions"][0]],
                        [{**original["actions"][0], "day_offset": 2}],
                        [{**original["actions"][0], "day_offset": 1}]):
            self.vector["actions"] = actions
            with self.subTest(actions=actions), self.assertRaises(GateError):
                validate_experiment(self.vector)

    def test_checkpoints_require_known_participants_and_endpoints(self):
        original = copy.deepcopy(self.vector)
        for observations in (original["observations"][:1],
                             [original["observations"][0]] * 2,
                             [{**original["observations"][0], "participant": "missing"}],
                             [{**original["observations"][0], "rng_state": 9}, original["observations"][1]]):
            self.vector["observations"] = observations
            with self.subTest(observations=observations), self.assertRaises(GateError):
                validate_experiment(self.vector)

    def test_comparisons_require_observed_fields_and_valid_tolerances(self):
        comparison = self.vector["comparisons"][0]
        for patch in ({"field": "missing"}, {"max_error": 1}, {"kind": "ulp", "max_error": 0.5}):
            self.vector["comparisons"] = [{**comparison, **patch}]
            with self.subTest(patch=patch), self.assertRaises(GateError):
                validate_experiment(self.vector)

    def test_experiment_rejects_nonfinite_binary_strings_and_bool_integer(self):
        for value in (float("nan"), float("inf"), "encoded-original-payload"):
            self.vector["actions"][0]["parameters"]["value"] = value
            with self.subTest(value=value), self.assertRaises(GateError):
                validate_experiment(self.vector)
        self.vector["actions"][0]["parameters"]["value"] = 3
        self.vector["participants"][0]["initial_rng"] = True
        with self.assertRaises(GateError):
            validate_experiment(self.vector)


class RepositoryBoundaryTests(unittest.TestCase):
    def test_plain_source_and_synthetic_json_allowed(self):
        self.assertEqual(boundary_reasons("specs/test.json", b'{"synthetic": true}', set()), [])
        self.assertEqual(boundary_reasons("tests/test.py", b"# newly written test\n", set()), [])

    def test_private_paths_and_original_extensions_rejected(self):
        for path in ("analysis/result.json", "nested/private-corpus/example.txt", "data.SaV", "fake.RES", "disc.CUE"):
            with self.subTest(path=path):
                self.assertTrue(boundary_reasons(path, b"synthetic", set()))

    def test_known_hash_rejected_under_innocent_name(self):
        data = b"invented fixture for hash matching"
        self.assertIn("known original-file hash", boundary_reasons("example.txt", data, {hashlib.sha256(data).hexdigest()}))

    def test_renamed_binary_media_and_disc_signatures_rejected(self):
        signatures = (b"MZsynthetic", b"PK\x03\x04", b"RIFF1234WAVE", b"fLaC", b"OggS", b"%PDF-1.0",
                      b"\0" * 32769 + b"CD001", b"\0" + b"\xff" * 10 + b"\0")
        for data in signatures:
            with self.subTest(data=data[:12]):
                self.assertTrue(boundary_reasons("example.txt", data, set()))

    def test_nontext_and_oversized_payloads_rejected(self):
        for data in (b"a\0b", b"\xff", b"x" * (MAX_TRACKED_BYTES + 1)):
            self.assertTrue(boundary_reasons("example.txt", data, set()))

    def test_boundary_reads_index_not_working_tree(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            known = root / "src/capplus_inspect/known.py"
            known.parent.mkdir(parents=True)
            known.write_text("# synthetic empty hash catalog\n", encoding="utf-8")
            payload = root / "example.txt"
            payload.write_text("safe source\n", encoding="utf-8")
            subprocess.run(["git", "add", "src/capplus_inspect/known.py", "example.txt"], cwd=root, check=True)
            payload.write_bytes(b"MZsynthetic")
            self.assertEqual(boundary_gate(root)["tracked_files"], 2)
            subprocess.run(["git", "add", "example.txt"], cwd=root, check=True)
            payload.write_text("safe replacement\n", encoding="utf-8")
            with self.assertRaises(GateError):
                boundary_gate(root)

    def test_boundary_rejects_symlink_index_mode(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            known = root / "src/capplus_inspect/known.py"
            known.parent.mkdir(parents=True)
            known.write_text("# synthetic\n", encoding="utf-8")
            subprocess.run(["git", "add", "src/capplus_inspect/known.py"], cwd=root, check=True)
            oid = subprocess.check_output(["git", "hash-object", "-w", "--stdin"], input=b"target", cwd=root).decode().strip()
            subprocess.run(["git", "update-index", "--add", "--cacheinfo", f"120000,{oid},link"], cwd=root, check=True)
            with self.assertRaises(GateError):
                boundary_gate(root)


class PackageContractTests(unittest.TestCase):
    def test_current_version_and_tag(self):
        version = source_version()
        self.assertEqual(version_gate(tag=f"v{version}")["version"], version)
        with self.assertRaises(GateError):
            version_gate(tag="v99.0.0")

    def test_version_mismatches_and_missing_release_notes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init = root / "src/capplus_inspect/__init__.py"
            init.parent.mkdir(parents=True)
            init.write_text('__version__ = "1.0.0"\n', encoding="utf-8")
            config = root / "pyproject.toml"
            for text in ('[project]\nversion = "2.0.0"\n', '[build-system]\n',
                         '[project]\nversion = "1.0.0"\nversion = "1.0.0"\n'):
                config.write_text(text, encoding="utf-8")
                with self.subTest(config=text), self.assertRaises(GateError):
                    source_version(root)
            config.write_text('[project]\nversion = "1.0.0"\n', encoding="utf-8")
            (root / "CHANGELOG.md").write_text("## Unreleased\n", encoding="utf-8")
            with self.assertRaises(GateError):
                version_gate(root, "v1.0.0")

    def test_sdist_extracts_only_safe_regular_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "test.tar.gz"
            with tarfile.open(archive, "w:gz") as stream:
                item = tarfile.TarInfo("source/test.txt")
                item.size = 4
                stream.addfile(item, io.BytesIO(b"test"))
            unpacked = extract_sdist(archive, root / "out")
            self.assertEqual((unpacked / "test.txt").read_bytes(), b"test")
            with self.assertRaises(GateError):
                extract_sdist(archive, root / "out")

    def test_sdist_rejects_traversal_links_and_multiple_roots(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "test.tar.gz"
            for names in (["../escape"], ["/absolute"], ["C:/drive"], ["source\\bad"], ["one/file", "two/file"], ["link"]):
                with tarfile.open(archive, "w:gz") as stream:
                    for name in names:
                        item = tarfile.TarInfo(name)
                        if name == "link":
                            item.type, item.linkname = tarfile.SYMTYPE, "target"
                        stream.addfile(item)
                with self.subTest(names=names), self.assertRaises(GateError):
                    extract_sdist(archive, root / "out")


if __name__ == "__main__":
    unittest.main()
