#!/usr/bin/env python3
"""Build in a temporary tracked-only copy; verify wheel and sdist offline."""
from __future__ import annotations

import argparse
from email.parser import BytesParser
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile

if __package__:
    from .project_gates import ROOT, GateError, source_version
else:
    from project_gates import ROOT, GateError, source_version


def run(arguments: list[str], cwd: Path, env: dict[str, str]) -> str:
    completed = subprocess.run(arguments, cwd=cwd, env=env, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if completed.returncode:
        raise GateError(f"command failed: {arguments[:3]}\n{completed.stdout}")
    return completed.stdout


def wheel_contents(path: Path, expected_version: str) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise GateError(f"wheel CRC failed: {bad}")
        contents = {name: archive.read(name) for name in archive.namelist()}
    metadata_paths = [name for name in contents if name.endswith(".dist-info/METADATA")]
    if len(metadata_paths) != 1:
        raise GateError("wheel needs one metadata record")
    metadata = BytesParser().parsebytes(contents[metadata_paths[0]])
    if metadata["Name"] != "capplus-inspect" or metadata["Version"] != expected_version:
        raise GateError("wheel metadata and source version disagree")
    if metadata.get_all("Requires-Dist"):
        raise GateError("inspector unexpectedly gained runtime dependencies")
    if metadata["License-Expression"] != "MIT":
        raise GateError("wheel lost its SPDX license metadata")
    for name in ("format-catalog-v1.json", "format-catalog-v1.schema.json"):
        key = f"capplus_inspect/schemas/{name}"
        if key not in contents:
            raise GateError(f"wheel omitted bundled schema: {name}")
        json.loads(contents[key])
    if not any(name.endswith(".dist-info/licenses/LICENSE") for name in contents):
        raise GateError("wheel omitted the license file")
    return contents


def extract_sdist(path: Path, destination: Path) -> Path:
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        roots = set()
        for member in members:
            parts = PurePosixPath(member.name).parts
            if not parts or member.name.startswith("/") or ".." in parts or "\\" in member.name or ":" in member.name:
                raise GateError("unsafe source archive path")
            if not (member.isfile() or member.isdir()):
                raise GateError("source archive contains a link or special file")
            roots.add(parts[0])
        if len(roots) != 1:
            raise GateError("source archive needs a single root")
        # Never follow archive links or restore owner/mode metadata. The caller
        # supplies a new temporary destination, including on Python 3.10.
        if destination.exists():
            raise GateError("source extraction needs a fresh destination")
        destination.mkdir(parents=True)
        for member in members:
            target = destination.joinpath(*PurePosixPath(member.name).parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                stream = archive.extractfile(member)
                if stream is None:
                    raise GateError("source archive member has no data")
                with stream, target.open("xb") as output:
                    shutil.copyfileobj(stream, output)
    return destination / roots.pop()


def package_check() -> dict[str, object]:
    version = source_version()
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env.update(PIP_NO_INDEX="1", PIP_DISABLE_PIP_VERSION_CHECK="1", PYTHONNOUSERSITE="1")
    with tempfile.TemporaryDirectory(prefix="capplusplus-package-") as temporary:
        workspace = Path(temporary)
        staging = workspace / "source"
        staging.mkdir()
        paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).split(b"\0")
        for raw in paths:
            if not raw:
                continue
            relative = Path(raw.decode("utf-8"))
            source = ROOT / relative
            if source.is_symlink() or not source.is_file():
                raise GateError("package input must be a regular tracked file")
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        artifacts = workspace / "artifacts"
        artifacts.mkdir()
        # Build backends may mutate sys.argv/global setup state. Use independent
        # hook processes, as a normal PEP 517 frontend does.
        for hook in ("build_sdist", "build_wheel"):
            code = f"import sys; from setuptools.build_meta import {hook}; {hook}(sys.argv[1])"
            run([sys.executable, "-c", code, str(artifacts)], staging, env)
        wheels, sdists = list(artifacts.glob("*.whl")), list(artifacts.glob("*.tar.gz"))
        if len(wheels) != 1 or len(sdists) != 1:
            raise GateError("expected exactly one wheel and one sdist")
        original = wheel_contents(wheels[0], version)
        unpacked = extract_sdist(sdists[0], workspace / "unpacked")
        # Development specifications, scripts and fixtures must survive the sdist.
        for relative in ("scripts/project_gates.py", "specs/content-coverage-v1.json",
                         "specs/feature-parity-v1.json", "specs/experiment-v1.schema.json",
                         "tests/fixtures/experiments/synthetic-state-delta.json", "CLEAN_ROOM.md"):
            if not (unpacked / relative).is_file():
                raise GateError(f"sdist omitted required development file: {relative}")
        run([sys.executable, "scripts/project_gates.py", "ledgers"], unpacked, env)
        run([sys.executable, "scripts/project_gates.py", "version"], unpacked, env)
        test_env = {**env, "PYTHONPATH": str(unpacked / "src")}
        test_output = run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."], unpacked, test_env)
        test_count = re.search(r"^Ran (\d+) tests? in ", test_output, re.MULTILINE)
        if test_count is None:
            raise GateError("sdist test output has no test-count summary")
        rebuilt_dir = workspace / "rebuilt"
        rebuilt_dir.mkdir()
        run([sys.executable, "-c", "import sys; from setuptools.build_meta import build_wheel; build_wheel(sys.argv[1])", str(rebuilt_dir)], unpacked, env)
        rebuilt = list(rebuilt_dir.glob("*.whl"))
        if len(rebuilt) != 1 or wheel_contents(rebuilt[0], version) != original:
            raise GateError("wheel file contents differ when rebuilt from sdist")
        environment = workspace / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        bindir = environment / ("Scripts" if os.name == "nt" else "bin")
        python = bindir / ("python.exe" if os.name == "nt" else "python")
        cli = bindir / ("capplus-inspect.exe" if os.name == "nt" else "capplus-inspect")
        run([str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(rebuilt[0])], workspace, env)
        code = ("import capplus_inspect as p; from importlib.metadata import version; "
                "assert p.__version__ == version('capplus-inspect'); "
                "from capplus_inspect.schema_catalog import load_format_catalog, load_catalog_schema; "
                "assert load_format_catalog()['catalog_version'] == 1; assert load_catalog_schema()['type'] == 'object'; "
                "print(p.__version__)")
        if run([str(python), "-I", "-c", code], workspace, env).strip() != version:
            raise GateError("installed import version mismatch")
        if run([str(cli), "--version"], workspace, env).strip() != f"capplus-inspect {version}":
            raise GateError("installed CLI version mismatch")
        run([str(cli), "schema-catalog", "--json"], workspace, env)
        run([str(cli), "fuzz", "--iterations", "32", "--seed", "7", "--json"], workspace, env)
        return {"version": version, "wheel_and_sdist": "verified", "offline_install": "passed",
                "sdist_wheel_contents_equal": True, "sdist_tests": int(test_count.group(1))}


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        print(json.dumps(package_check(), indent=2, sort_keys=True))
        return 0
    except (GateError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"package check failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
