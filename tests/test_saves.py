from __future__ import annotations

import unittest

from capplus_inspect.errors import FormatError
from capplus_inspect.saves import compare_saves, inspect_save

from .helpers import make_minimal_save


class SaveTests(unittest.TestCase):
    def test_resolves_full_marker_chain(self) -> None:
        result = inspect_save(make_minimal_save())
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["save_version"], 100)
        self.assertEqual(result["section_count"], 24)
        self.assertEqual(result["rng"]["state_hex"], "0x12345678")
        self.assertEqual(result["settings_references"], ["TEST.SCT"])
        self.assertTrue(result["town_array"]["parsed"])
        self.assertEqual(result["town_array"]["dynamic_array"]["element_count"], 0)

    def test_compares_rng_change(self) -> None:
        left = make_minimal_save(rng_state=1)
        right = make_minimal_save(rng_state=2)
        result = compare_saves(left, right)
        self.assertFalse(result["byte_identical"])
        rng = next(section for section in result["sections"] if section["marker"] == "1001")
        self.assertEqual(rng["differing_bytes_at_same_offsets"], 1)
        self.assertEqual(result["town_array"]["shared_town_item_keys"], 0)

    def test_rejects_truncated_save(self) -> None:
        with self.assertRaises(FormatError):
            inspect_save(make_minimal_save()[:-100])


if __name__ == "__main__":
    unittest.main()
