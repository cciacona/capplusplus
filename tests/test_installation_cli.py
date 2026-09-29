from __future__ import annotations

import contextlib
import hashlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from capplus_inspect.cli import main
from capplus_inspect.installation import inspect_installation

from .helpers import make_le_executable, make_pe32_executable


class InstallationTests(unittest.TestCase):
    def test_target_requires_exact_executable_and_target_data(self) -> None:
        executable = make_pe32_executable()
        core = {
            "gameset/1std.set": b"synthetic data",
            "resource/i_scen.res": b"synthetic revised menu",
        }
        expected = {path: hashlib.sha256(data).hexdigest() for path, data in core.items()}
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "target.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("CapPlus.exe", executable)
                for path, data in core.items():
                    archive.writestr(path, data)
            with (mock.patch("capplus_inspect.installation.STEAM_101_EXECUTABLE_SHA256",
                             hashlib.sha256(executable).hexdigest()),
                  mock.patch("capplus_inspect.installation.STEAM_101_CORE_FILE_SHA256", expected)):
                result = inspect_installation(archive_path)
                self.assertEqual(result["variant"], "steam-1.01")
                self.assertTrue(result["supported_release"])
                self.assertEqual(result["core_assets"]["reference"], "steam-1.01")
                self.assertEqual(result["core_assets"]["matched"], 2)
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["inspect", str(archive_path), "--require-clean"]), 0)

                with zipfile.ZipFile(archive_path, "w") as archive:
                    archive.writestr("CapPlus.exe", executable)
                    archive.writestr("GAMESET/1STD.SET", core["gameset/1std.set"])
                    archive.writestr("RESOURCE/I_SCEN.RES", b"modified")
                modified = inspect_installation(archive_path)
                self.assertEqual(modified["variant"], "steam-1.01")
                self.assertFalse(modified["supported_release"])
                self.assertEqual(modified["core_assets"]["modified"][0]["path"],
                                 "resource/i_scen.res")

    def test_historical_build_can_be_identified_but_is_not_supported(self) -> None:
        executable = make_le_executable()
        core = {"gameset/1std.set": hashlib.sha256(b"synthetic").hexdigest()}
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "historical.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("CapPlus.exe", executable)
                archive.writestr("GAMESET/1STD.SET", b"synthetic")
            with (mock.patch("capplus_inspect.installation.DOS_EXECUTABLE_SHA256",
                             hashlib.sha256(executable).hexdigest()),
                  mock.patch("capplus_inspect.installation.CORE_FILE_SHA256", core)):
                result = inspect_installation(archive_path)
                self.assertEqual(result["variant"], "dos")
                self.assertEqual(result["support_status"], "historical")
                self.assertEqual(result["core_assets"]["reference"], "retail-1.0")
                self.assertTrue(result["core_assets"]["complete_and_unmodified"])
                self.assertFalse(result["supported_release"])
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["inspect", str(archive_path), "--require-clean"]), 3)

    def test_unrecognized_pe_named_like_dos_build_is_not_labeled_dos(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "ported-game.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("CapPlus.exe", make_pe32_executable())
                archive.writestr("GAMESET/1STD.SET", b"synthetic")
                archive.writestr("MAPS/WORLD.MAP", b"synthetic")
                archive.writestr("RESOURCE/TEXT.RES", b"synthetic")
            result = inspect_installation(archive_path)
        self.assertEqual(result["variant"], "unknown")
        self.assertEqual(result["executables"][0]["variant"], "unknown")
        self.assertEqual(result["executables"][0]["executable_format"], "PE")
        self.assertFalse(result["executables"][0]["recognized_unmodified"])

    def test_finds_wrapped_installation_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "game.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("wrapper/GAMESET/1STD.SET", b"not-real-data")
                archive.writestr("wrapper/MAPS/WORLD.MAP", b"not-real-data")
                archive.writestr("wrapper/RESOURCE/TEXT.RES", b"not-real-data")
            result = inspect_installation(archive_path)
        self.assertEqual(result["installation_root"], "wrapper")
        self.assertEqual(result["file_count"], 3)
        self.assertEqual(result["core_assets"]["present"], 3)
        self.assertEqual(result["core_assets"]["matched"], 0)
        self.assertFalse(result["core_assets"]["complete_and_unmodified"])

    def test_require_clean_exit_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "GAMESET").mkdir()
            (root / "GAMESET" / "1STD.SET").write_bytes(b"modified")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = main(["inspect", str(root), "--require-clean"])
        self.assertEqual(status, 3)
        self.assertIn("complete and unmodified: no", stdout.getvalue())

    def test_missing_path_is_expected_error(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            status = main(["inspect", "/definitely/not/a/real/path"])
        self.assertEqual(status, 2)
        self.assertIn("does not exist", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
