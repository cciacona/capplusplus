#!/usr/bin/env python3
"""Repository-only coverage, provenance, content-boundary and version gates."""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import fnmatch
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MAX_TRACKED_BYTES = 1024 * 1024
PRIVATE_DIRS = {
    "original-data", "private-corpus", "analysis", "reports", "exports",
    "executable-reports", "loader-reports",
}
FORBIDDEN_SUFFIXES = set(
    ".exe .dll .sav .bin .cue .iso .gam .res .set .map .pla .plo .plp "
    ".ii .ii2 .dfi .fi .ip .pic .rti .rtp .rtx .sct .scn .scp .scs "
    ".tut .hin .sam .sph .cfg .hof .snd .ogg .flac .wav .voc .mp3 "
    ".com .sys .zip .7z .whl .gz .xz .pdf".split()
)
DIMENSIONS = {"data", "simulation", "ui", "persistence", "ai", "multiplayer"}


class GateError(ValueError):
    pass


def load_json(path: Path) -> Any:
    def reject_constant(value: str) -> None:
        raise GateError(f"non-finite JSON number: {value}")
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise GateError(f"duplicate JSON object key: {key}")
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant,
                      object_pairs_hook=unique_object)


def validate_schema(value: Any, schema: dict[str, Any], path: str = "$") -> None:
    """Validate the explicit JSON Schema subset used by specs, not general JSON Schema.

    Unsupported validation keywords fail closed. Schemas intentionally contain no
    external references, conditional evaluation, defaults, or code execution.
    """
    supported = {
        "$schema", "title", "description", "type", "const", "enum", "required",
        "properties", "additionalProperties", "items", "minItems", "uniqueItems",
        "minLength", "pattern", "minimum", "maximum",
    }
    if set(schema) - supported:
        raise GateError(f"{path}: unsupported schema keywords {sorted(set(schema) - supported)}")
    types = schema.get("type", [])
    if isinstance(types, str):
        types = [types]
    checks = {
        "object": isinstance(value, dict), "array": isinstance(value, list),
        "string": isinstance(value, str), "null": value is None,
        "boolean": isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
    }
    if types and not any(checks.get(kind, False) for kind in types):
        raise GateError(f"{path}: expected {types}")
    if "const" in schema and (type(value) is not type(schema["const"]) or value != schema["const"]):
        raise GateError(f"{path}: wrong constant")
    if "enum" in schema and value not in schema["enum"]:
        raise GateError(f"{path}: invalid enum value")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and not math.isfinite(value):
            raise GateError(f"{path}: non-finite number")
        if "minimum" in schema and value < schema["minimum"]:
            raise GateError(f"{path}: below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise GateError(f"{path}: above maximum")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise GateError(f"{path}: empty string")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            raise GateError(f"{path}: invalid string pattern")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            raise GateError(f"{path}: too few items")
        if schema.get("uniqueItems"):
            keys = [json.dumps(item, sort_keys=True) for item in value]
            if len(set(keys)) != len(keys):
                raise GateError(f"{path}: duplicate items")
        for index, item in enumerate(value):
            if "items" in schema:
                validate_schema(item, schema["items"], f"{path}[{index}]")
    if isinstance(value, dict):
        missing = set(schema.get("required", [])) - set(value)
        if missing:
            raise GateError(f"{path}: missing keys {sorted(missing)}")
        properties = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for key, item in value.items():
            if key in properties:
                validate_schema(item, properties[key], f"{path}.{key}")
            elif extra is False:
                raise GateError(f"{path}: unexpected key {key!r}")
            elif isinstance(extra, dict):
                validate_schema(item, extra, f"{path}.{key}")


def unique_ids(entries: list[dict[str, Any]]) -> set[str]:
    ids = [entry["id"] for entry in entries]
    if len(ids) != len(set(ids)):
        raise GateError("duplicate identifiers")
    return set(ids)


def normalized_path(path: str) -> str:
    normalized = path.replace("\\", "/").lower()
    parts = normalized.split("/")
    if not normalized or any(part in {"", ".", ".."} for part in parts) or ":" in normalized:
        raise GateError("inventory paths must be nonempty relative paths without traversal")
    return normalized


def classify_path(path: str, families: list[dict[str, Any]]) -> list[str]:
    path = normalized_path(path)
    matches = []
    for family in families:
        if family.get("extensionless") and PurePosixPath(path).suffix:
            continue
        if any(fnmatch.fnmatchcase(path, pattern) for pattern in family.get("exclude", [])):
            continue
        if any(fnmatch.fnmatchcase(path, pattern) for pattern in family["patterns"]):
            matches.append(family["id"])
    return matches


def inventory_report(paths: list[str], content: dict[str, Any], source: str) -> dict[str, Any]:
    """Classify caller-provided paths without reading or publishing their payloads."""
    if source not in content["sources"]:
        raise GateError(f"unknown inventory source: {source}")
    seen: set[str] = set()
    counts: Counter[str] = Counter()
    unknown = 0
    for raw in paths:
        path = normalized_path(raw)
        if path in seen:
            raise GateError("duplicate or case-colliding inventory path")
        seen.add(path)
        matches = classify_path(path, content["families"])
        if len(matches) > 1:
            raise GateError(f"ambiguous family selectors: {matches}")
        if not matches:
            unknown += 1
        else:
            counts[matches[0]] += 1
    differences = []
    for family in content["families"]:
        expected = family["observed_counts"].get(source, 0)
        actual = counts[family["id"]]
        if actual != expected:
            differences.append({"family": family["id"], "expected": expected, "actual": actual})
    return {
        "source": source, "file_count": len(paths), "unclassified_count": unknown,
        "family_counts": dict(sorted(counts.items())), "count_differences": differences,
        "complete_inventory": not unknown and not differences and len(paths) == content["sources"][source]["expected_files"],
    }


def validate_experiment(vector: dict[str, Any], root: Path = ROOT) -> None:
    validate_schema(vector, load_json(root / "specs/experiment-v1.schema.json"))
    participants = unique_ids(vector["participants"])
    if vector["kind"] == "original_observation":
        if vector["profile"] != "classic" or not vector["private_artifacts"]["required"]:
            raise GateError("original observations require a Classic profile and private artifacts")
        if vector["provenance"]["method"] == "synthetic_fixture":
            raise GateError("original observations cannot use synthetic provenance")
        for participant in vector["participants"]:
            if not participant["executable_sha256"] or not participant["initial_save_sha256"]:
                raise GateError("original observations require exact build and initial-save hashes")
    elif vector["profile"] != "synthetic" or vector["provenance"]["method"] != "synthetic_fixture":
        raise GateError("synthetic examples must not masquerade as original evidence")
    ordering = [(action["day_offset"], action["sequence"]) for action in vector["actions"]]
    if ordering != sorted(set(ordering)):
        raise GateError("actions must be ordered with unique day/sequence keys")
    if any(action["day_offset"] >= vector["duration_days"] for action in vector["actions"]):
        raise GateError("actions must precede the final checkpoint day")
    for row in vector["actions"] + vector["observations"]:
        if row["day_offset"] > vector["duration_days"]:
            raise GateError("event lies beyond experiment duration")
    keys = set()
    fields = set()
    endpoints: dict[str, set[int]] = {participant: set() for participant in participants}
    for observation in vector["observations"]:
        participant = observation["participant"]
        if participant not in participants:
            raise GateError("observation references an unknown participant")
        key = (participant, observation["day_offset"])
        if key in keys:
            raise GateError("duplicate participant checkpoint")
        keys.add(key)
        endpoints[participant].add(observation["day_offset"])
        fields.update(observation["values"])
        if vector["kind"] == "original_observation" and not observation["save_sha256"]:
            raise GateError("original checkpoints require private save hashes")
        if observation["day_offset"] == 0:
            initial = next(p for p in vector["participants"] if p["id"] == participant)
            if observation["rng_state"] != initial["initial_rng"] or observation["save_sha256"] != initial["initial_save_sha256"]:
                raise GateError("initial checkpoint disagrees with participant state")
    for checkpoints in endpoints.values():
        if not {0, vector["duration_days"]} <= checkpoints:
            raise GateError("every participant needs initial and final checkpoints")
    for comparison in vector["comparisons"]:
        if comparison["field"] not in fields and comparison["field"] != "rng_state":
            raise GateError("comparison references an unobserved field")
        if comparison["kind"] == "exact" and comparison["max_error"] != 0:
            raise GateError("exact comparisons require zero tolerance")
        if comparison["kind"] == "ulp" and not float(comparison["max_error"]).is_integer():
            raise GateError("ULP tolerance must be an integer")


def ledger_gate(root: Path = ROOT) -> dict[str, Any]:
    content = load_json(root / "specs/content-coverage-v1.json")
    parity = load_json(root / "specs/feature-parity-v1.json")
    validate_schema(content, load_json(root / "specs/content-coverage-v1.schema.json"))
    validate_schema(parity, load_json(root / "specs/feature-parity-v1.schema.json"))
    families = unique_ids(content["families"] + content["non_file_content"])
    unique_ids(parity["features"])
    totals: Counter[str] = Counter()
    for family in content["families"]:
        for source, count in family["observed_counts"].items():
            if source not in content["sources"]:
                raise GateError("family references an unknown inventory source")
            totals[source] += count
    for source, metadata in content["sources"].items():
        if totals[source] != metadata["expected_files"]:
            raise GateError(f"{source}: family totals do not reconcile")
    retail = content["retail_reconciliation"]
    if any(source not in totals for source in retail["enumerated_sources"]):
        raise GateError("retail reconciliation references an unknown source")
    if sum(totals[source] for source in retail["enumerated_sources"]) + retail["unclassified_files"] != retail["expected_files"]:
        raise GateError("retail file-count reconciliation failed")
    if (retail["status"] == "enumerated") != (retail["unclassified_files"] == 0):
        raise GateError("retail completion status contradicts unresolved coverage")
    if set(parity["dimensions"]) != DIMENSIONS:
        raise GateError("parity ledger must expose every independent dimension")
    for feature in parity["features"]:
        if set(feature["content_families"]) - families:
            raise GateError(f"{feature['id']}: unknown content family")
        if "validated" in feature["status"].values():
            if not feature["tests"] or feature["reference_status"] == "needs_reference_check":
                raise GateError("validated parity requires reference evidence and tests")
        if parity["manual_crosswalk_status"] == "complete" and feature["reference_status"] == "needs_reference_check":
            raise GateError("complete manual crosswalk still contains unchecked references")
    for record in content["families"] + content["non_file_content"] + parity["features"]:
        for reference in record["evidence"] + record.get("tests", []):
            if reference.startswith("https://"):
                continue
            relative = reference.split("#", 1)[0]
            normalized_path(relative)
            if not (root / relative).is_file():
                raise GateError(f"missing evidence/test reference: {relative}")
    examples = sorted((root / "tests/fixtures/experiments").glob("*.json"))
    if not examples:
        raise GateError("experiment specification needs a synthetic fixture")
    for example in examples:
        validate_experiment(load_json(example), root)
    return {"families": len(content["families"]), "non_file_categories": len(content["non_file_content"]),
            "enumerated_sources": dict(totals), "retail_unclassified_files": retail["unclassified_files"],
            "features": len(parity["features"]), "manual_crosswalk": parity["manual_crosswalk_status"],
            "synthetic_experiments": len(examples)}


def boundary_reasons(path: str, data: bytes, known_hashes: set[str]) -> list[str]:
    normalized = normalized_path(path)
    reasons = []
    if set(PurePosixPath(normalized).parts) & PRIVATE_DIRS:
        reasons.append("private/generated directory")
    if PurePosixPath(normalized).suffix in FORBIDDEN_SUFFIXES:
        reasons.append("original-game or binary/archive extension")
    if len(data) > MAX_TRACKED_BYTES:
        reasons.append("file exceeds one MiB review limit")
    if hashlib.sha256(data).hexdigest() in known_hashes:
        reasons.append("known original-file hash")
    signatures = (b"MZ", b"\x7fELF", b"PK\x03\x04", b"PK\x05\x06", b"7z\xbc\xaf\x27\x1c",
                  b"OggS", b"fLaC", b"\x89PNG\r\n\x1a\n", b"GIF87a", b"GIF89a", b"\xff\xd8\xff",
                  b"\x1f\x8b", b"\xfd7zXZ\0", b"%PDF-")
    if data.startswith(signatures) or (data[:4] == b"RIFF" and data[8:12] in {b"WAVE", b"AVI "}):
        reasons.append("binary/media signature")
    if data[32769:32774] == b"CD001" or data.startswith(b"\0" + b"\xff" * 10 + b"\0"):
        reasons.append("disc-image signature")
    try:
        text = data.decode("utf-8")
        if "\0" in text:
            reasons.append("NUL-containing payload")
    except UnicodeDecodeError:
        reasons.append("non-UTF-8 payload")
    return reasons


def boundary_gate(root: Path = ROOT) -> dict[str, int]:
    """Inspect Git index blobs, not unstaged replacements that might hide a payload."""
    indexed = subprocess.check_output(["git", "ls-files", "--stage", "-z"], cwd=root)
    entries = [entry for entry in indexed.split(b"\0") if entry]
    if not entries:
        raise GateError("empty Git index; boundary gate cannot run on an unpacked source archive")
    known_source = subprocess.check_output(["git", "show", ":src/capplus_inspect/known.py"], cwd=root)
    known = set(re.findall(r"\b[0-9a-f]{64}\b", known_source.decode("utf-8")))
    total = 0
    for entry in entries:
        metadata, raw_path = entry.split(b"\t", 1)
        mode, oid, stage = metadata.split()
        path = raw_path.decode("utf-8")
        if mode not in {b"100644", b"100755"} or stage != b"0":
            raise GateError(f"{path}: symlink, submodule, or unresolved Git entry is not allowed")
        size = int(subprocess.check_output(["git", "cat-file", "-s", oid.decode()], cwd=root))
        if size > MAX_TRACKED_BYTES:
            raise GateError(f"{path}: file exceeds one MiB review limit")
        data = subprocess.check_output(["git", "cat-file", "blob", oid.decode()], cwd=root)
        reasons = boundary_reasons(path, data, known)
        if reasons:
            raise GateError(f"{path}: {', '.join(reasons)}")
        total += size
    return {"tracked_files": len(entries), "tracked_bytes": total}


def source_version(root: Path = ROOT) -> str:
    config = (root / "pyproject.toml").read_text(encoding="utf-8")
    sections = config.split("[project]")
    if len(sections) != 2:
        raise GateError("configuration needs exactly one project section")
    project = sections[1].split("\n[", 1)[0]
    matches = re.findall(r'^version\s*=\s*"([^"\n]+)"\s*$', project, re.MULTILINE)
    if len(matches) != 1:
        raise GateError("project needs one literal version")
    version = matches[0]
    tree = ast.parse((root / "src/capplus_inspect/__init__.py").read_text(encoding="utf-8"))
    versions = [ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets)]
    if versions != [version]:
        raise GateError("pyproject and package versions disagree")
    return version


def version_gate(root: Path = ROOT, tag: str | None = None) -> dict[str, str]:
    version = source_version(root)
    if tag is not None and tag != f"v{version}":
        raise GateError("release tag and package version disagree")
    if tag is not None:
        changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
        if not re.search(r"^## " + re.escape(version) + r"(?:\s|$)", changelog, re.MULTILINE):
            raise GateError("release tag has no matching changelog section")
    return {"version": version, "tag": tag or "not a release build"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gate", choices=["all", "ledgers", "boundary", "version", "inventory", "experiment"])
    parser.add_argument("--tag")
    parser.add_argument("--input", type=Path, help="JSON path array for inventory, or experiment record")
    parser.add_argument("--source", choices=["shared_core", "gam_image"])
    args = parser.parse_args(argv)
    try:
        result = {}
        if args.gate in {"all", "ledgers"}:
            result["ledgers"] = ledger_gate()
        if args.gate in {"all", "boundary"}:
            result["boundary"] = boundary_gate()
        if args.gate in {"all", "version"}:
            result["version"] = version_gate(tag=args.tag)
        if args.gate in {"inventory", "experiment"}:
            if args.input is None or (args.gate == "inventory" and args.source is None):
                raise GateError("--input and, for inventory, --source are required")
            value = load_json(args.input)
            if args.gate == "inventory":
                if not isinstance(value, list) or not all(isinstance(p, str) for p in value):
                    raise GateError("inventory input must be a JSON array of relative paths")
                result = inventory_report(value, load_json(ROOT / "specs/content-coverage-v1.json"), args.source)
                print(json.dumps(result, indent=2, sort_keys=True))
                return 0 if result["complete_inventory"] else 1
            validate_experiment(value)
            result = {"experiment": value["id"], "valid": True}
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (GateError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"project gate failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
