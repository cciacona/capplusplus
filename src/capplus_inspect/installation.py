from __future__ import annotations

import hashlib
import zipfile
from abc import ABC, abstractmethod
from collections import Counter
from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION
from .containers import inspect_set
from .errors import FormatError, InspectError
from .file_formats import inspect_auxiliary_file
from .known import CORE_FILE_SHA256, DOS_EXECUTABLE_SHA256, WINDOWS_EXECUTABLE_SHA256
from .maps import inspect_map
from .saves import inspect_save
from .util import sha256_file


def _normalize(path: str) -> str:
    value = path.replace("\\", "/").lstrip("/")
    while value.startswith("./"):
        value = value[2:]
    return value.rstrip("/").lower()


class _Source(ABC):
    kind: str

    @abstractmethod
    def names(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def read(self, name: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def sha256(self, name: str) -> str:
        raise NotImplementedError

    def close(self) -> None:
        pass


class _DirectorySource(_Source):
    kind = "directory"

    def __init__(self, root: Path) -> None:
        self.root = root
        self._files = {
            _normalize(path.relative_to(root).as_posix()): path
            for path in root.rglob("*")
            if path.is_file()
        }

    def names(self) -> list[str]:
        return list(self._files)

    def read(self, name: str) -> bytes:
        return self._files[name].read_bytes()

    def sha256(self, name: str) -> str:
        return sha256_file(self._files[name])


class _ZipSource(_Source):
    kind = "zip"

    def __init__(self, path: Path) -> None:
        try:
            self.archive = zipfile.ZipFile(path)
        except (OSError, zipfile.BadZipFile) as error:
            raise FormatError(f"cannot open ZIP archive: {error}") from error
        self._infos: dict[str, zipfile.ZipInfo] = {}
        for info in self.archive.infolist():
            if not info.is_dir():
                self._infos[_normalize(info.filename)] = info

    def names(self) -> list[str]:
        return list(self._infos)

    def read(self, name: str) -> bytes:
        return self.archive.read(self._infos[name])

    def sha256(self, name: str) -> str:
        digest = hashlib.sha256()
        with self.archive.open(self._infos[name]) as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    def close(self) -> None:
        self.archive.close()


def _find_root(names: list[str]) -> str:
    anchors = ("gameset/1std.set", "maps/world.map", "resource/text.res")
    candidates: set[str] = {""}
    for name in names:
        for anchor in anchors:
            if name == anchor:
                candidates.add("")
            elif name.endswith("/" + anchor):
                candidates.add(name[: -len(anchor)].rstrip("/"))

    name_set = set(names)

    def score(prefix: str) -> tuple[int, int]:
        stem = f"{prefix}/" if prefix else ""
        matches = sum(stem + anchor in name_set for anchor in anchors)
        matches += sum(stem + executable in name_set for executable in ("capplus.exe", "capwin.exe"))
        return matches, -len(prefix)

    return max(candidates, key=score)


def _canonical_files(source: _Source) -> tuple[str, dict[str, str]]:
    names = source.names()
    root = _find_root(names)
    prefix = f"{root}/" if root else ""
    files: dict[str, str] = {}
    for actual in names:
        if prefix and not actual.startswith(prefix):
            continue
        canonical = actual[len(prefix) :] if prefix else actual
        files[canonical] = actual
    return root, files


def _inspect_deep(source: _Source, files: dict[str, str]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "game_sets": [],
        "layout_plans": [],
        "maps": [],
        "resources": [],
        "support_files": [],
        "saves": [],
    }
    errors: list[dict[str, str]] = []

    for canonical in sorted(files):
        actual = files[canonical]
        try:
            if canonical.startswith("gameset/") and canonical.endswith(".set"):
                info = inspect_set(source.read(actual))
                result["game_sets"].append(
                    {
                        "path": canonical,
                        "table_count": info["table_count"],
                        "tables": [
                            {
                                "name": table["name"],
                                "record_count": table["record_count"],
                                "field_count": table["field_count"],
                            }
                            for table in info["tables"]
                        ],
                    }
                )
            elif canonical.startswith("gameset/") and canonical.endswith(
                (".pla", ".plo", ".plp")
            ):
                info = inspect_auxiliary_file(source.read(actual), canonical)
                result["layout_plans"].append(
                    {
                        "path": canonical,
                        "format": info["format"],
                        "size": info["size"],
                        "sha256": info["sha256"],
                        "category_count": info["category_count"],
                        "record_count": info["record_count"],
                        "categories": [
                            {
                                "identifier": category["identifier"],
                                "record_count": category["array_header"]["record_count"],
                            }
                            for category in info["categories"]
                        ],
                    }
                )
            elif canonical.startswith("maps/") and canonical.endswith(".map"):
                info = inspect_map(source.read(actual))
                result["maps"].append(
                    {
                        "path": canonical,
                        "city_count": info["city_count"],
                        "cities": info["cities"],
                        "sha256": info["sha256"],
                    }
                )
            elif canonical.startswith("resource/"):
                cursor_image_data = None
                if canonical == "resource/cursor.res" and "resource/i_cursor.res" in files:
                    cursor_image_data = source.read(files["resource/i_cursor.res"])
                info = inspect_auxiliary_file(
                    source.read(actual),
                    canonical,
                    cursor_image_data=cursor_image_data,
                )
                summary = {
                    "path": canonical,
                    "format": info["format"],
                    "size": info["size"],
                    "sha256": info["sha256"],
                }
                if "member_count" in info:
                    summary["member_count"] = info["member_count"]
                    summary["member_kinds"] = dict(
                        sorted(Counter(member["kind"] for member in info["members"]).items())
                    )
                if "image_count" in info:
                    summary["image_count"] = info["image_count"]
                for count_name in ("glyph_count", "screen_count", "cursor_count", "topic_count"):
                    if count_name in info:
                        summary[count_name] = info[count_name]
                result["resources"].append(summary)
            elif canonical in {"capital.cfg", "capital.hof"}:
                info = inspect_auxiliary_file(source.read(actual), canonical)
                result["support_files"].append(
                    {
                        "path": canonical,
                        "format": info["format"],
                        "size": info["size"],
                        "sha256": info["sha256"],
                    }
                )
            elif canonical.endswith(".sav"):
                info = inspect_save(source.read(actual))
                result["saves"].append(
                    {
                        "path": canonical,
                        "internal_filename": info["internal_filename"],
                        "date": info["current_date"],
                        "settings_references": info["settings_references"],
                        "section_count": info["section_count"],
                        "rng": info.get("rng"),
                    }
                )
        except (InspectError, OSError, ValueError) as error:
            errors.append({"path": canonical, "error": str(error)})
    result["errors"] = errors
    return result


def inspect_installation(path: str | Path, *, deep: bool = False) -> dict[str, Any]:
    input_path = Path(path)
    if input_path.is_dir():
        source: _Source = _DirectorySource(input_path)
    elif input_path.is_file() and zipfile.is_zipfile(input_path):
        source = _ZipSource(input_path)
    elif input_path.is_file():
        raise FormatError("installation input must be a directory or ZIP archive")
    else:
        raise FormatError("installation path does not exist")

    try:
        root, files = _canonical_files(source)
        if not files:
            raise FormatError("installation contains no files")

        executables: list[dict[str, Any]] = []
        variants: list[str] = []
        for name, variant, expected in (
            ("capplus.exe", "dos", DOS_EXECUTABLE_SHA256),
            ("capwin.exe", "windows", WINDOWS_EXECUTABLE_SHA256),
        ):
            if name not in files:
                continue
            digest = source.sha256(files[name])
            recognized = digest == expected
            executables.append(
                {
                    "path": name,
                    "variant": variant,
                    "sha256": digest,
                    "recognized_unmodified": recognized,
                }
            )
            variants.append(variant)

        matched: list[str] = []
        modified: list[dict[str, str]] = []
        missing: list[str] = []
        for canonical, expected in sorted(CORE_FILE_SHA256.items()):
            actual = files.get(canonical)
            if actual is None:
                missing.append(canonical)
                continue
            digest = source.sha256(actual)
            if digest == expected:
                matched.append(canonical)
            else:
                modified.append(
                    {"path": canonical, "expected_sha256": expected, "actual_sha256": digest}
                )

        extension_counts = Counter(
            Path(name).suffix.lower() or "<none>" for name in files
        )
        result: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "format": "capitalism_plus_installation",
            "input": str(input_path.resolve()),
            "source_kind": source.kind,
            "installation_root": root,
            "variant": "+".join(variants) if variants else "unknown",
            "file_count": len(files),
            "extension_counts": dict(sorted(extension_counts.items())),
            "executables": executables,
            "core_assets": {
                "expected": len(CORE_FILE_SHA256),
                "present": len(matched) + len(modified),
                "matched": len(matched),
                "modified": modified,
                "missing": missing,
                "complete_and_unmodified": len(matched) == len(CORE_FILE_SHA256),
            },
            "counts": {
                "game_set_files": sum(name.startswith("gameset/") for name in files),
                "layout_plan_files": sum(
                    name.startswith("gameset/")
                    and name.endswith((".pla", ".plo", ".plp"))
                    for name in files
                ),
                "map_files": sum(name.startswith("maps/") for name in files),
                "resource_files": sum(name.startswith("resource/") for name in files),
                "support_files": sum(name in {"capital.cfg", "capital.hof"} for name in files),
                "save_files": sum(name.endswith(".sav") for name in files),
            },
        }
        if deep:
            result["deep"] = _inspect_deep(source, files)
        return result
    finally:
        source.close()
