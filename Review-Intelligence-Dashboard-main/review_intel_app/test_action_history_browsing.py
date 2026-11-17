"""Read-only browsing checks with large, disposable synthetic action logs."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from streamlit.testing.v1 import AppTest

import action_tracker as A
from action_edit_history_ui import SAVES_PER_PAGE


class ActionHistoryBrowsingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "actions.json"
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.action = {
            "action_id": "synthetic-action", "dataset_tag": "synthetic-dataset",
            "baseline": {"mentions": 123, "share": 45},
            "unknown_legacy_evidence": {"preserve": [1, 2]},
            "edit_history": [{
                "saved_at": (start + timedelta(minutes=i)).isoformat(),
                **({"saved_by": "synthetic-manager"} if i % 2 else {}),
                "changes": {} if i % 7 == 0 else {
                    field: {"before": f"before-{i}", "after": f"after-{i}"}
                    for field in A.EDITABLE_FIELDS},
            } for i in range(1003)],
        }
        A.save_actions(self.path, [self.action])
        self.before = self.path.read_bytes()
        self.app = AppTest.from_string(f"""
import json
from pathlib import Path
from action_edit_history_ui import show_action_edit_history
for action in json.loads(Path({str(self.path)!r}).read_text()):
    show_action_edit_history(action)
""").run()

    def test_every_save_is_reachable_newest_first_without_changing_records(self):
        expected = list(reversed(self.action["edit_history"]))
        seen = []
        pages = (len(expected) + SAVES_PER_PAGE - 1) // SAVES_PER_PAGE
        for page in range(1, pages + 1):
            if page > 1:
                self.app.number_input[0].set_value(page).run()
            self.assertFalse(self.app.exception)
            rows = self.app.dataframe[0].value
            entries = expected[(page - 1) * SAVES_PER_PAGE:page * SAVES_PER_PAGE]
            timestamps = list(dict.fromkeys(rows["Saved at (UTC)"]))
            self.assertEqual(timestamps, [e["saved_at"] for e in entries])
            self.assertLessEqual(len(rows), SAVES_PER_PAGE * len(A.EDITABLE_FIELDS))
            for entry in entries:
                save_rows = rows[rows["Saved at (UTC)"] == entry["saved_at"]]
                self.assertEqual(len(save_rows), max(1, len(entry["changes"])))
                self.assertEqual(set(save_rows["Saved by"]),
                                 {entry.get("saved_by", "Unknown")})
                if not entry["changes"]:
                    self.assertEqual(list(save_rows["Field"]),
                                     ["Saved without field changes"])
                self.assertTrue(entry["saved_at"].endswith("+00:00"))
            self.assertIn(f"Page {page} of {pages}", self.app.caption[-1].value)
            seen.extend(timestamps)
        self.assertEqual(seen, [entry["saved_at"] for entry in expected])
        self.app.number_input[0].set_value(1).run()
        self.assertEqual(self.app.dataframe[0].value.iloc[0]["Saved at (UTC)"],
                         expected[0]["saved_at"])
        self.assertEqual(self.path.read_bytes(), self.before)
        self.assertEqual(A.load_actions(self.path), [self.action])

    def test_page_bounds_shrink_safely_and_empty_legacy_histories_still_work(self):
        self.app.number_input[0].set_value(51).run()
        shorter = deepcopy(self.action)
        shorter["edit_history"] = shorter["edit_history"][:21]
        A.save_actions(self.path, [shorter], expected_actions=A.load_actions(self.path))
        self.app.run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.number_input[0].value, 2)
        self.assertEqual(len(self.app.dataframe[0].value), 1)
        self.assertEqual(self.app.dataframe[0].value.iloc[0]["Field"],
                         "Saved without field changes")
        shorter["edit_history"] = shorter["edit_history"][:20]
        A.save_actions(self.path, [shorter], expected_actions=A.load_actions(self.path))
        self.app.run()
        self.assertFalse(self.app.number_input)
        self.assertIn("Page 1 of 1", self.app.caption[-1].value)
        del shorter["edit_history"]
        A.save_actions(self.path, [shorter], expected_actions=A.load_actions(self.path))
        self.app.run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.info[0].value, "No recorded action edits yet.")
        self.assertFalse(self.app.dataframe)

    def test_actions_have_independent_page_controls(self):
        other = deepcopy(self.action)
        other["action_id"] = "other-synthetic-action"
        A.save_actions(self.path, [self.action, other],
                       expected_actions=A.load_actions(self.path))
        self.app.run()
        self.assertFalse(self.app.exception)
        self.app.number_input[0].set_value(2).run()
        self.assertEqual([w.value for w in self.app.number_input], [2, 1])
        self.assertNotEqual(self.app.dataframe[0].value.iloc[0]["Saved at (UTC)"],
                            self.app.dataframe[1].value.iloc[0]["Saved at (UTC)"])


if __name__ == "__main__":
    unittest.main()
