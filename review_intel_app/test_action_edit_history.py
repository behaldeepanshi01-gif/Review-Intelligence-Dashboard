"""Action edit audits use only temporary synthetic logs, never manager data."""

from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import action_tracker as A


DAY = date(2026, 1, 1)


class ActionEditHistoryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = str(Path(temp.name) / "actions.json")
        self.original = A.create_action(
            "synthetic", {"location": "Synthetic Cafe", "theme": "Service speed",
                          "recent_share": 60, "recent_mentions": 6},
            "service_speed", "Check handoffs.", "Manager", DAY, DAY, DAY,
            today=DAY, source_reviews=[],
        )
        self.original["unknown_legacy_data"] = {"keep": [1, 2]}
        A.save_actions(self.path, [self.original])

    def edit(self, snapshot, **overrides):
        values = dict(action_text=snapshot["action_text"], owner=snapshot["owner"],
                      status=snapshot["status"],
                      start_date=A.parse_date(snapshot["start_date"]),
                      due_date=A.parse_date(snapshot["due_date"]))
        values.update(overrides)
        return A.edit_saved_action(self.path, snapshot, **values)

    def test_all_editable_fields_and_utc_time_persist_without_changing_baselines(self):
        snapshot = deepcopy(self.original)
        saved = self.edit(
            snapshot, action_text=" New step. ", owner=" New owner ",
            status="Done", start_date=DAY + timedelta(days=1),
            due_date=DAY + timedelta(days=3))
        entry = saved["edit_history"][0]
        self.assertEqual(set(entry["changes"]), set(A.EDITABLE_FIELDS))
        for field in A.EDITABLE_FIELDS:
            self.assertEqual(entry["changes"][field],
                             {"before": self.original[field], "after": saved[field]})
        instant = datetime.fromisoformat(entry["saved_at"])
        self.assertEqual(instant.utcoffset(), timedelta(0))
        self.assertEqual(A.load_actions(self.path), [saved])
        self.assertEqual(snapshot, self.original)
        for field in self.original.keys() - set(A.EDITABLE_FIELDS):
            self.assertEqual(saved[field], self.original[field])

    def test_sequential_edits_keep_prior_entries_and_only_changed_fields(self):
        first = self.edit(self.original, owner="New owner")
        prior = deepcopy(first)
        second = self.edit(A.load_actions(self.path)[0], status="In progress")
        self.assertEqual(first, prior)
        self.assertEqual(second["edit_history"][0], prior["edit_history"][0])
        self.assertEqual(second["edit_history"][1]["changes"], {
            "status": {"before": "Planned", "after": "In progress"}})
        self.assertEqual(len(A.load_actions(self.path)[0]["edit_history"]), 2)

    def test_successful_unchanged_save_is_explicit_not_a_fabricated_edit(self):
        saved = self.edit(self.original, action_text=" Check handoffs. ")
        self.assertEqual(saved["edit_history"][0]["changes"], {})
        self.assertIn("saved_at", saved["edit_history"][0])

    def test_conflict_validation_and_write_failures_add_no_history(self):
        saved = self.edit(self.original, owner="New owner")
        before = Path(self.path).read_bytes()
        with self.assertRaises(A.ActionConflictError):
            self.edit(self.original, status="Done")
        for changes in ({"action_text": " "}, {"status": "Invalid"},
                        {"due_date": DAY - timedelta(days=1)}):
            with self.assertRaises(ValueError):
                self.edit(saved, **changes)
        with patch.object(A.os, "replace", side_effect=OSError("Synthetic failure")):
            with self.assertRaises(OSError):
                self.edit(saved, status="Done")
        self.assertEqual(Path(self.path).read_bytes(), before)
        self.assertEqual(list(Path(self.path).parent.glob(".actions-*.tmp")), [])
        self.assertEqual(A.load_actions(self.path), [saved])

    def test_legacy_action_does_not_invent_earlier_history(self):
        self.assertNotIn("edit_history", A.load_actions(self.path)[0])
        saved = self.edit(self.original, owner="")
        self.assertEqual(len(saved["edit_history"]), 1)
        self.assertEqual(saved["edit_history"][0]["changes"], {
            "owner": {"before": "Manager", "after": ""}})


if __name__ == "__main__":
    unittest.main()
