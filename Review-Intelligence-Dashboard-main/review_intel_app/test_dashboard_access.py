"""Synthetic scopes: no private workspace files or real accounts are used."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

import action_tracker as A
import dataset_store as D
import manager_identity as identity
import manager_corrections as corrections
from calendar_test_support import manager_session
from dashboard_access import DashboardAccess
from location_settings import LocationSettings


class DashboardAccessTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.sample = self.root / "sample.csv"
        self.content = (
            "location,date,rating,text,review_id\n"
            "Allowed,2026-10-01,5,Good food,one\n"
            "Allowed,2026-10-02,4,Great food,two\n"
            "Hidden,2020-01-01,1,SECRET REVIEW,secret\n"
        ).encode()
        self.sample.write_bytes(self.content)
        self.store = D.DatasetStore(self.root / "uploads", self.sample)
        self.other = self.store.save_snapshot("SECRET DATASET.csv", self.content)
        self.session = manager_session(self, temp.name, {D.SAMPLE_ID: ["Allowed"]})
        self.access = DashboardAccess(self.session)

    def test_scoped_reads_and_exact_denials(self):
        self.assertEqual([r["dataset_id"] for r in self.access.datasets(
            self.store, True)], [D.SAMPLE_ID])
        self.assertEqual(set(self.access.reviews(self.store.get(D.SAMPLE_ID))["location"]),
                         {"Allowed"})
        with patch.object(A, "load_actions", return_value=[
            {"dataset_tag": D.SAMPLE_ID, "location": "Allowed"},
            {"dataset_tag": D.SAMPLE_ID, "location": "Hidden"},
            {"dataset_tag": self.other["dataset_id"], "location": "Allowed"},
        ]):
            self.assertEqual(len(self.access.actions("unused", self.store.get(D.SAMPLE_ID))), 1)
        for dataset, locations in [(self.other["dataset_id"], ["Allowed"]),
                                   (D.SAMPLE_ID, ["Hidden"]), (D.SAMPLE_ID, []),
                                   (D.SAMPLE_ID, ["Allowed", "Hidden"]),
                                   (D.SAMPLE_ID, ["allowed"]), (None, ["Allowed"])]:
            with self.assertRaises(PermissionError):
                self.access.require(dataset, locations)

    def test_replacement_cannot_delete_or_add_unassigned_rows(self):
        target = self.other["dataset_id"]
        identity.set_account("test-manager", "synthetic-calendar-password", {target: ["Allowed"]})
        access = DashboardAccess(identity.authenticate("test-manager", "synthetic-calendar-password"))
        before = self.store.get(target)
        with self.assertRaises(PermissionError):
            access.save_snapshot(self.store, "same.csv", self.content, target)
        self.assertEqual(self.store.get(target), before)
        with self.assertRaises(PermissionError):
            access.save_snapshot(self.store, "new.csv", self.content, None)
        identity.set_account("test-manager", "synthetic-calendar-password",
                             {target: ["Allowed", "Hidden"]})
        access = DashboardAccess(identity.authenticate("test-manager", "synthetic-calendar-password"))
        updated = access.save_snapshot(self.store, "same.csv", self.content, target)
        self.assertNotEqual(updated["path"], before["path"])
        self.assertEqual(Path(before["path"]).read_bytes(), self.content)
        with self.assertRaises(PermissionError):
            access.save_snapshot(self.store, "same.csv",
                                 self.content.replace(b"Hidden", b"Forbidden"), target)

    def test_revoked_and_expired_sessions_fail_closed(self):
        for invalidate in [lambda: self.session.update(expires=0),
                           lambda: identity.remove_account("test-manager")]:
            self.session["expires"] = identity.time.time() + 1800
            invalidate()
            for operation in [
                lambda: self.access.datasets(self.store),
                lambda: self.access.reviews(self.store.get(D.SAMPLE_ID)),
                lambda: self.access.actions("unused", self.store.get(D.SAMPLE_ID)),
                lambda: self.access.require(D.SAMPLE_ID, ["Allowed"]),
            ]:
                with self.assertRaises(PermissionError):
                    operation()

    def test_concurrent_replacement_cannot_remove_newly_added_unassigned_location(self):
        only_allowed = b"location,date,rating,text\nAllowed,2026-10-01,5,Good\n"
        dataset = self.store.save_snapshot("race.csv", only_allowed)
        target = dataset["dataset_id"]
        identity.set_account("partial-manager", "synthetic-partial-password",
                             {target: ["Allowed"]})
        identity.set_account("full-manager", "synthetic-full-password",
                             {target: ["Allowed", "Hidden"]})
        partial = DashboardAccess(identity.authenticate(
            "partial-manager", "synthetic-partial-password"))
        full = DashboardAccess(identity.authenticate(
            "full-manager", "synthetic-full-password"))
        # A second connection publishes A+B after A's permission check but before
        # A attempts publication. Only a conditional write can reject this race.
        second_store = D.DatasetStore(self.root / "uploads", self.sample)
        validate = partial.validate_replacement
        published = {}

        def interleave(*args):
            checked_path = validate(*args)
            published.update(full.save_snapshot(
                second_store, "race.csv", self.content, target))
            return checked_path

        with patch.object(partial, "validate_replacement", side_effect=interleave):
            with self.assertRaisesRegex(ValueError, "snapshot changed"):
                partial.save_snapshot(self.store, "race.csv", only_allowed, target)
        self.assertEqual(self.store.get(target), published)
        self.assertEqual(Path(published["path"]).read_bytes(), self.content)
        self.assertEqual(Path(dataset["path"]).read_bytes(), only_allowed)
        # The failed candidate file is removed; only the original and winner
        # were added for this dataset (plus the other fixture snapshot).
        self.assertEqual(len(list((self.root / "uploads/snapshots").glob("*.csv"))), 3)
        with self.assertRaises(PermissionError):
            partial.save_snapshot(self.store, "race.csv", only_allowed, target)

    def test_dashboard_denies_before_loading_and_scopes_every_view(self):
        self.store.claim_legacy_history(
            D.SAMPLE_ID, "synthetic-old.csv",
            [{"dataset_tag": "synthetic-old.csv"}])
        original_settings = LocationSettings
        with patch.object(D, "DatasetStore", return_value=self.store), patch.object(
            A, "load_actions", return_value=[]
        ), patch("location_settings.LocationSettings", side_effect=lambda path, **kw:
                 original_settings(self.root / "calendar.sqlite", **kw)) as settings, patch(
                     "dashboard_export_ui.secure_export",
                     return_value=False) as downloads:
            settings.default.side_effect = original_settings.default
            app = AppTest.from_file(str(Path(__file__).with_name("app.py")), default_timeout=30)
            with patch("engine.load_reviews", side_effect=AssertionError("unsigned read")):
                app.run()
            self.assertFalse(app.exception)
            self.assertFalse(app.sidebar.radio)
            app.text_input(key="_manager_username").set_value("test-manager")
            app.text_input(key="_manager_report_password").set_value("synthetic-calendar-password")
            next(b for b in app.button if b.label == "Unlock restaurant dashboard").click().run()
            self.assertFalse(app.exception)
            self.assertIn("History-link corrections", [e.label for e in app.expander])
            audit = next(frame.value for frame in app.dataframe
                         if "Changed by" in frame.value.columns)
            self.assertEqual(audit["Changed by"].tolist(), ["Unknown"])
            self.assertFalse(any(b.label in {"Link older history", "Confirm history correction"}
                                 for b in app.button))
            self.assertEqual(next(s for s in app.selectbox if s.label == "Calendar location").options,
                             ["Allowed"])
            self.assertEqual(next(s for s in app.multiselect if s.label == "Locations").options,
                             ["Allowed"])
            rendered = str(app)
            for forbidden in ["SECRET REVIEW", "SECRET DATASET", "Hidden", "2020-01-01"]:
                self.assertNotIn(forbidden, rendered)
            csv_export = next(call.args[1] for call in downloads.call_args_list
                              if call.args[0] == "Download analyzed reviews (CSV)")
            self.assertIn("Allowed", csv_export)
            self.assertNotIn("Hidden", csv_export)
            self.assertNotIn("SECRET REVIEW", csv_export)
            # Expiry/revocation must clear retained replies and old editors too.
            app.session_state["approved"] = {"one": "private draft"}
            save = next(b for b in app.button if b.label == "Save manager decision")
            identity.remove_account("test-manager")
            with patch.object(corrections, "save_correction") as mutation:
                save.click().run()
                mutation.assert_not_called()
            self.assertFalse(app.exception)
            self.assertFalse(app.sidebar.radio)
            self.assertNotIn("approved", app.session_state)


if __name__ == "__main__":
    unittest.main()
