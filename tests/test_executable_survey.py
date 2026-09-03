from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.executable_survey import REPORT_FILENAMES, main

from .helpers import make_le_executable, make_pe32_executable


class ExecutableSurveyTests(unittest.TestCase):
    def test_writes_three_reports_without_original_data(self) -> None:
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
                ]
            )

            self.assertEqual(status, 0)
            self.assertEqual(
                sorted(path.name for path in output.iterdir()),
                sorted(REPORT_FILENAMES),
            )
            summary = json.loads((output / REPORT_FILENAMES[2]).read_text())
            self.assertTrue(summary["same_machine_family"])
            self.assertEqual(summary["dos"]["executable_format"], "LE")
            self.assertEqual(summary["windows"]["imported_symbol_count"], 1)


if __name__ == "__main__":
    unittest.main()
