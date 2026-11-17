"""Explicit snapshot removal and authorized history use only synthetic local data."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import action_tracker as A
import dataset_store as D
import engine as E
import manager_identity as identity
from calendar_test_support import manager_session
from dashboard_access import DashboardAccess
from location_settings import LocationSettings


class SavedActionHistoryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        data = self.root / "data"
        data.mkdir()
        self.original_csv = (
            b"location,date,rating,text\n"
            b"Removed,2026-10-01,1,Slow service\n"
            b"Removed,2026-10-02,2,Waited too long\n"
            b"Remaining,2026-10-01,4,Good food\n"
            b"Remaining,2026-10-02,5,Great food\n")
        sample = data / "sample_reviews.csv"
        sample.write_bytes(self.original_csv)
        self.store = D.DatasetStore(data / "uploads", sample)
        self.dataset = self.store.save_snapshot("restaurants.csv", self.original_csv)
        self.tag = self.dataset["dataset_id"]
        self.other = self.store.save_snapshot("other.csv", self.original_csv)["dataset_id"]
        self.session = manager_session(self, self.root, {
            self.tag: ["Removed", "Remaining"], self.other: ["Removed", "Remaining"]})
        self.access = DashboardAccess(self.session)
        day = date(2026, 10, 2)
        self.action = A.create_action(
            self.tag, {"location": "Removed", "theme": "Service speed",
                       "recent_share": 100, "recent_mentions": 2},
            "service_speed", "Restore service handoffs", "Original owner",
            day, day, day, today=day,
            source_reviews=E.load_reviews(self.dataset["path"]).to_dict("records"))
        self.action["extra_legacy_evidence"] = {"preserve": True}
        hidden = deepcopy(self.action)
        hidden.update(action_id="hidden-action", location="Forbidden",
                      action_text="SECRET UNASSIGNED PLAN")
        other = deepcopy(self.action)
        other.update(action_id="other-action", dataset_tag=self.other,
                     action_text="SECRET OTHER DATASET PLAN")
        self.log = data / "action_log.json"
        A.save_actions(self.log, [self.action, hidden, other])
        self.before = self.log.read_bytes()
        # This is an explicit update of the stable dataset, not a new CSV identity.
        remaining = (
            b"location,date,rating,text\n"
            b"Remaining,2026-10-01,4,Good food\n"
            b"Remaining,2026-10-02,5,Great food\n")
        self.updated = self.access.save_snapshot(
            self.store, "restaurants.csv", remaining, self.tag)
        source = Path(__file__).with_name("app.py").read_text().replace(
            "BASE_DIR = os.path.dirname(os.path.abspath(__file__))",
            f"BASE_DIR = {str(self.root)!r}")
        self.app = AppTest.from_string(source, default_timeout=30)
        self.app.session_state["_manager_report_grant"] = self.session
        self.app.session_state["data_source"] = "Saved file"
        self.app.run()
        # Select the stable dataset explicitly, regardless of registry sort order.
        next(w for w in self.app.selectbox if w.label == "Dataset").set_value(self.tag).run()
        self.assertFalse(self.app.exception)

    def history(self):
        next(w for w in self.app.radio if w.label == "Dashboard view").set_value(
            "Saved actions for absent locations").run()
        self.assertFalse(self.app.exception)

    def widget(self, kind, label):
        return next(w for w in getattr(self.app, kind) if w.label == label)

    def rendered(self):
        return "\n".join(str(w.value) for kind in
                         ("warning", "caption", "info", "markdown", "subheader", "json")
                         for w in self.app.get(kind))

    def test_explicit_removal_preserves_baseline_and_separates_current_reviews(self):
        self.assertEqual(set(E.load_reviews(self.updated["path"])["location"]), {"Remaining"})
        self.assertEqual(Path(self.dataset["path"]).read_bytes(), self.original_csv)
        self.assertEqual(self.log.read_bytes(), self.before)
        self.assertEqual(self.widget("multiselect", "Locations").options, ["Remaining"])
        self.widget("multiselect", "Locations").set_value([]).run()
        self.history()  # Not blocked by an empty current-review filter.
        self.assertEqual(self.widget("selectbox", "Saved-action location").options, ["Removed"])
        self.assertFalse(any(w.label in ("Locations", "Date range")
                             for w in list(self.app.multiselect) + list(self.app.slider)))
        rendered = self.rendered()
        self.assertIn("Restore service handoffs", rendered)
        self.assertIn("Source data changed", rendered)
        self.assertIn("Missing baseline reviews: 2", rendered)
        self.assertIn("Follow-up trends are unavailable", rendered)
        self.assertNotIn("SECRET UNASSIGNED PLAN", rendered)
        self.assertNotIn("SECRET OTHER DATASET PLAN", rendered)
        self.assertNotIn("Waiting for at least", rendered)
        self.widget("text_area", "Manager action").set_value("New saved plan").run()
        self.widget("text_input", "Owner (optional)").set_value("New owner").run()
        self.widget("selectbox", "Status").set_value("Done").run()
        self.widget("button", "Save updates").click().run()
        self.assertFalse(self.app.exception)
        saved = A.load_actions(self.log)
        self.assertEqual(saved[0]["action_text"], "New saved plan")
        self.assertEqual(saved[0]["owner"], "New owner")
        self.assertEqual(saved[0]["status"], "Done")
        for field in self.action.keys() - set(A.EDITABLE_FIELDS):
            self.assertEqual(saved[0][field], self.action[field], field)
        self.assertEqual(saved[1:], json.loads(self.before)[1:])
        self.assertEqual(len(saved[0]["edit_history"]), 1)
        self.assertEqual(saved[0]["edit_history"][0]["saved_by"], "test-manager")
        history = next(t.value for t in self.app.dataframe
                       if "Saved at (UTC)" in t.value.columns)
        self.assertEqual(set(history["Saved by"]), {"test-manager"})
        self.widget("radio", "Saved-history status").set_value("Active plans").run()
        self.assertFalse(self.app.text_area)
        self.widget("radio", "Saved-history status").set_value("Completed plans").run()
        self.assertEqual(self.widget("text_area", "Manager action").value, "New saved plan")
        self.widget("radio", "Dashboard view").set_value("Current reviews").run()
        self.assertEqual(self.widget("multiselect", "Locations").options, ["Remaining"])

    def test_history_only_manager_and_revocation(self):
        identity.set_account("test-manager", "synthetic-calendar-password",
                             {self.tag: ["Removed"]})
        self.app.session_state["_manager_report_grant"] = identity.authenticate(
            "test-manager", "synthetic-calendar-password")
        self.app.run()
        self.assertIn("No current reviews", self.rendered())
        self.history()
        self.assertEqual(self.widget("selectbox", "Saved-action location").options, ["Removed"])
        self.widget("text_area", "Manager action").set_value("Private draft").run()
        identity.set_account("test-manager", "synthetic-calendar-password",
                             {self.tag: ["Remaining"]})
        with patch.object(A, "edit_saved_action") as mutation:
            self.widget("button", "Save updates").click().run()
            mutation.assert_not_called()
        self.assertFalse(self.app.exception)
        self.assertNotIn("Private draft", self.rendered())
        self.assertEqual(self.log.read_bytes(), self.before)

    def test_conflict_keeps_draft_and_does_not_overwrite(self):
        self.history()
        self.widget("text_area", "Manager action").set_value("Private draft").run()
        A.edit_saved_action(self.log, self.action, "Other manager save", "Other owner",
                            "In progress", date(2026, 10, 2), date(2026, 10, 3),
                            session=self.session)
        self.widget("button", "Save updates").click().run()
        self.assertFalse(self.app.exception)
        self.assertIn("Another manager changed", self.rendered())
        self.assertEqual(self.widget("text_area", "Manager action").value, "Private draft")
        self.assertEqual(A.load_actions(self.log)[0]["action_text"], "Other manager save")
        self.widget("button", "Reload latest saved plan").click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.widget("text_area", "Manager action").value, "Other manager save")

    def test_history_hides_unassigned_absent_location_and_other_dataset(self):
        identity.set_account("test-manager", "synthetic-calendar-password",
                             {self.tag: ["Remaining"], self.other: ["Remaining"]})
        self.app.session_state["_manager_report_grant"] = identity.authenticate(
            "test-manager", "synthetic-calendar-password")
        self.app.run()
        self.history()
        self.assertFalse(any(w.label == "Saved-action location" for w in self.app.selectbox))
        self.assertNotIn("Restore service handoffs", self.rendered())
        self.assertEqual(self.log.read_bytes(), self.before)

    def test_linked_legacy_history_requires_reload_after_link_changes(self):
        actions = A.load_actions(self.log)
        actions[0]["dataset_tag"] = "legacy-restaurants.csv"
        A.save_actions(self.log, actions, expected_actions=A.load_actions(self.log))
        linked = self.store.claim_legacy_history(
            self.tag, "legacy-restaurants.csv", actions, expected_revision=0)
        self.history()
        self.assertIn("Restore service handoffs", self.rendered())
        self.widget("text_area", "Manager action").set_value("Legacy private draft").run()
        self.store.correct_legacy_history(
            self.tag, "legacy-restaurants.csv",
            expected_source_revision=linked["history_revision"])
        unlinked = self.store.get(self.tag)
        self.store.claim_legacy_history(
            self.tag, "legacy-restaurants.csv", actions,
            expected_revision=unlinked["history_revision"])
        before = self.log.read_bytes()
        self.widget("button", "Save updates").click().run()
        self.assertFalse(self.app.exception)
        self.assertIn("older-history link changed", self.rendered())
        self.assertEqual(self.widget("text_area", "Manager action").value, "Legacy private draft")
        self.assertTrue(self.widget("button", "Save updates").disabled)
        self.assertEqual(self.log.read_bytes(), before)
        self.widget("button", "Reload latest saved plan").click().run()
        self.widget("text_area", "Manager action").set_value("Authorized legacy update").run()
        self.widget("button", "Save updates").click().run()
        self.assertFalse(self.app.exception)
        saved = A.load_actions(self.log)[0]
        self.assertEqual(saved["action_text"], "Authorized legacy update")
        self.assertEqual(saved["baseline_source"], self.action["baseline_source"])
        self.assertEqual(saved["dataset_tag"], "legacy-restaurants.csv")

    def test_absent_location_calendar_and_draft_navigation(self):
        LocationSettings(self.root / "data/location_settings.sqlite",
                         session=self.session).save(
                             self.tag, "Removed", "Pacific/Honolulu", expected_revision=0)
        self.history()
        self.assertIn("Pacific/Honolulu", self.rendered())
        self.widget("text_area", "Manager action").set_value("Unsaved history draft").run()
        self.widget("radio", "Dashboard view").set_value("Current reviews").run()
        self.app.run()
        self.history()
        self.assertEqual(self.widget("text_area", "Manager action").value,
                         "Unsaved history draft")
        self.assertEqual(self.log.read_bytes(), self.before)
        self.widget("button", "Reload latest saved plan").click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.widget("text_area", "Manager action").value,
                         "Restore service handoffs")


if __name__ == "__main__":
    unittest.main()
