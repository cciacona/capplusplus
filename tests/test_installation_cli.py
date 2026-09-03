from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from capplus_inspect.cli import main
from capplus_inspect.installation import inspect_installation


class InstallationTests(unittest.TestCase):
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
