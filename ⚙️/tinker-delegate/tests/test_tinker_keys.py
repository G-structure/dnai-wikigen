"""Unit tests for the pure key-table parsing / matching logic in tinker_keys.

The CDP driving itself needs a live console DOM to validate; these cover the
deterministic core that turns scraped rows into bounded records and matches a
delete target — the parts that must be correct regardless of markup drift.
"""
from __future__ import annotations

import unittest

from tinker_delegate.automation_receipts import (
    AutomationOutcome,
    AutomationStage,
    AutomationSurface,
)
from tinker_delegate.tinker_keys import (
    ApiKeyRecord,
    find_key_by_ref,
    parse_keys_table,
    _delete_receipt,
    _looks_like_date,
    _looks_like_prefix,
)


class TestParseKeysTable(unittest.TestCase):
    def test_basic_named_row(self):
        rows = [["prod-key", "tml-UgYm…DAAAA", "Jul 9, 2026", "2 hours ago"]]
        keys = parse_keys_table(rows)
        self.assertEqual(len(keys), 1)
        k = keys[0]
        self.assertEqual(k.name, "prod-key")
        self.assertEqual(k.key_prefix, "tml-UgYm…DAAAA")
        self.assertEqual(k.created, "Jul 9, 2026")
        self.assertEqual(k.last_used, "2 hours ago")

    def test_column_reorder_tolerant(self):
        rows = [["tml-abcd…wxyz", "dev-key", "2026-07-01"]]
        keys = parse_keys_table(rows)
        self.assertEqual(keys[0].name, "dev-key")
        self.assertEqual(keys[0].key_prefix, "tml-abcd…wxyz")
        self.assertEqual(keys[0].created, "2026-07-01")
        self.assertEqual(keys[0].last_used, "")

    def test_strips_action_cells(self):
        rows = [["my-key", "tml-zzzz…0000", "Delete", "Copy"]]
        keys = parse_keys_table(rows)
        self.assertEqual(len(keys), 1)
        self.assertEqual(keys[0].name, "my-key")

    def test_never_captures_full_secret_as_prefix(self):
        full = "tml-UgYm0AVq2rgNwipFsFJrgzluHFfHtzNgyu23D9iOJBHcIyTMhTLGGcQ4onJmRdhfDAAAA"
        self.assertFalse(_looks_like_prefix(full))
        rows = [["leaky", full]]
        keys = parse_keys_table(rows)
        self.assertEqual(keys[0].key_prefix, "")

    def test_empty_and_blank_rows_skipped(self):
        rows = [[], ["", "  "], ["real", "tml-aa…bb"]]
        keys = parse_keys_table(rows)
        self.assertEqual(len(keys), 1)
        self.assertEqual(keys[0].name, "real")

    def test_multiple_rows(self):
        rows = [
            ["alpha", "tml-a…1", "Jan 1, 2026"],
            ["beta", "tml-b…2", "Feb 2, 2026"],
        ]
        keys = parse_keys_table(rows)
        self.assertEqual([k.name for k in keys], ["alpha", "beta"])


class TestLooksLikeHelpers(unittest.TestCase):
    def test_prefix_detection(self):
        self.assertTrue(_looks_like_prefix("tml-abcd…wxyz"))
        self.assertTrue(_looks_like_prefix("tml-abcd..."))
        self.assertTrue(_looks_like_prefix("tml-abcd****"))
        self.assertTrue(_looks_like_prefix("tml-short"))
        self.assertFalse(_looks_like_prefix("prod-key"))

    def test_date_detection(self):
        self.assertTrue(_looks_like_date("Jul 9, 2026"))
        self.assertTrue(_looks_like_date("2026-07-09"))
        self.assertTrue(_looks_like_date("2 hours ago"))
        self.assertTrue(_looks_like_date("never"))
        self.assertFalse(_looks_like_date("prod-key"))


class TestFindKeyByRef(unittest.TestCase):
    keys = (
        ApiKeyRecord(name="prod", key_id="k_123", key_prefix="tml-aaaa…"),
        ApiKeyRecord(name="dev", key_id="k_456", key_prefix="tml-bbbb…"),
    )

    def test_match_by_name(self):
        self.assertEqual(find_key_by_ref(self.keys, "dev").key_id, "k_456")

    def test_match_by_name_case_insensitive(self):
        self.assertEqual(find_key_by_ref(self.keys, "PROD").name, "prod")

    def test_match_by_id(self):
        self.assertEqual(find_key_by_ref(self.keys, "k_456").name, "dev")

    def test_match_by_prefix(self):
        self.assertEqual(find_key_by_ref(self.keys, "tml-aaaa").name, "prod")

    def test_no_match(self):
        self.assertIsNone(find_key_by_ref(self.keys, "nonexistent"))

    def test_empty_ref(self):
        self.assertIsNone(find_key_by_ref(self.keys, ""))


class TestDeleteReceipt(unittest.TestCase):
    def test_bounded_and_no_raw_ref(self):
        r = _delete_receipt("prod-key", AutomationOutcome.SUCCESS, AutomationStage.API_KEY_DELETED)
        self.assertTrue(r["success"])
        self.assertEqual(r["operation"], "delete")
        self.assertEqual(r["surface"], AutomationSurface.API_KEY_MANAGEMENT.value)
        self.assertFalse(r["raw_secret_egress"])
        self.assertNotIn("prod-key", str(r))
        self.assertEqual(len(r["ref_hash"]), 64)

    def test_not_found_receipt(self):
        r = _delete_receipt("ghost", AutomationOutcome.KEY_NOT_FOUND, AutomationStage.API_KEY_LIST_READ)
        self.assertFalse(r["success"])
        self.assertEqual(r["outcome"], "key_not_found")


if __name__ == "__main__":
    unittest.main()
