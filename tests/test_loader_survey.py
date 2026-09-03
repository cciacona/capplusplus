from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.loader_survey import REPORT_FILENAMES, main

from .helpers import make_le_executable, make_pe32_executable


class LoaderSurveyTests(unittest.TestCase):
    def test_writes_four_reports_for_synthetic_unknown_builds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dos = root / "CAPPLUS.EXE"
            windows = root / "CapWin.exe"
            output = root / "reports"
            dos.write_bytes(make_le_executable())
            windows.write_bytes(make_pe32_executable())

            status = main(
                [
                    "--dos",
                    str(dos),
                    "--windows",
                    str(windows),
                    "--output",
                    str(output),
                    "--allow-unknown",
                ]
            )

            self.assertEqual(status, 0)
            self.assertEqual(
                sorted(path.name for path in output.iterdir()),
                sorted(REPORT_FILENAMES),
            )
            probe = json.loads((output / REPORT_FILENAMES[3]).read_text())
            summary = json.loads((output / REPORT_FILENAMES[2]).read_text())
            self.assertTrue(probe["passed"])
            self.assertFalse(summary["all_known_profiles_verified"])


if __name__ == "__main__":
    unittest.main()
