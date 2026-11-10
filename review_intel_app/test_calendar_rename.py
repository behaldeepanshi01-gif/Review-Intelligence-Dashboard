"""Calendar rename confirmation, snapshot races and dataset isolation."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from dataset_store import DatasetStore
from location_settings import LocationSettings, SettingsConflictError
from calendar_test_support import manager_session
import manager_identity as identity


def reviews(location):
    return (f"location,date,rating,text\n{location},2026-01-01,4,Good food\n"
            f"{location},2026-01-02,3,Slow service\n").encode()


class CalendarRenameTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.store = DatasetStore(root / "uploads", root / "sample.csv")
        self.dataset = self.store.save_snapshot("reviews.csv", reviews("Old"))
        self.id = self.dataset["dataset_id"]
        self.session = manager_session(self, root, {self.id: ["Old", "New", "Third", "Fourth"]})
        self.calendars = LocationSettings(root / "calendars.sqlite", session=self.session)
        self.calendars.save(self.id, "Old", "Asia/Kolkata", expected_revision=0)
        self.dataset = self.store.save_snapshot("reviews.csv", reviews("New"), self.id)

    def rename(self, **overrides):
        args = dict(expected_path=self.dataset["path"], expected_revision=1, confirmed=True)
        args.update(overrides)
        self.store.rename_location_calendar(self.calendars, self.id, "Old", "New", **args)

    def test_confirmation_and_restart_and_stale_old_editor(self):
        with self.assertRaisesRegex(ValueError, "Confirm"):
            self.rename(confirmed=False)
        self.assertEqual(set(self.calendars.load(self.id)), {"Old"})
        self.rename()
        reopened = LocationSettings(self.calendars.path, session=self.session)
        self.assertEqual(reopened.load(self.id), {"New": {"timezone": "Asia/Kolkata", "revision": 2}})
        with self.assertRaises(SettingsConflictError):
            reopened.save(self.id, "Old", "UTC", expected_revision=0)
        with self.assertRaises(SettingsConflictError):
            reopened.save(self.id, "New", "UTC", expected_revision=0)
        reopened.save(self.id, "New", "UTC", expected_revision=2)

    def test_collision_never_overwrites_even_same_timezone(self):
        self.calendars.save(self.id, "New", "Asia/Kolkata", expected_revision=0)
        before = self.calendars.load(self.id)
        with self.assertRaises(SettingsConflictError):
            self.rename()
        self.assertEqual(self.calendars.load(self.id), before)

    def test_stale_source_and_snapshot_rejected(self):
        self.calendars.save(self.id, "Old", "UTC", expected_revision=1)
        with self.assertRaises(SettingsConflictError):
            self.rename()
        self.store.save_snapshot("reviews.csv", reviews("Other"), self.id)
        with self.assertRaisesRegex(ValueError, "snapshot changed"):
            self.rename(expected_revision=2)
        self.assertEqual(self.calendars.load(self.id)["Old"]["timezone"], "UTC")

    def test_independent_datasets_with_identical_names_and_files(self):
        other = self.store.save_snapshot("reviews.csv", reviews("New"))
        other_id = other["dataset_id"]
        identity.set_account("test-manager", "synthetic-calendar-password",
                             {self.id: ["Old", "New", "Third"], other_id: ["Old", "New"]})
        self.session = identity.authenticate("test-manager", "synthetic-calendar-password")
        self.calendars.session = self.session
        self.calendars.save(other_id, "Old", "UTC", expected_revision=0)
        before = self.calendars.load(other_id)
        self.rename()
        self.assertEqual(self.calendars.load(other_id), before)
        with self.assertRaisesRegex(ValueError, "snapshot changed"):
            self.store.rename_location_calendar(
                self.calendars, other_id, "Old", "New",
                expected_path=self.dataset["path"], expected_revision=1, confirmed=True)

    def test_present_source_missing_target_and_unknown_dataset_rejected(self):
        for content in (reviews("Old"), reviews("Other")):
            self.dataset = self.store.save_snapshot("reviews.csv", content, self.id)
            with self.assertRaisesRegex(ValueError, "old name must be absent"):
                self.rename()
        with self.assertRaises(ValueError):
            self.store.rename_location_calendar(
                self.calendars, "unknown", "Old", "New", expected_path="unknown",
                expected_revision=1, confirmed=True)

    def test_chained_renames_cannot_reuse_old_owned_name(self):
        self.rename()
        self.dataset = self.store.save_snapshot("reviews.csv", reviews("Third"), self.id)
        self.store.rename_location_calendar(
            self.calendars, self.id, "New", "Third", expected_path=self.dataset["path"],
            expected_revision=2, confirmed=True)
        self.dataset = self.store.save_snapshot("reviews.csv", reviews("Old"), self.id)
        with self.assertRaises(SettingsConflictError):
            self.store.rename_location_calendar(
                self.calendars, self.id, "Third", "Old", expected_path=self.dataset["path"],
                expected_revision=3, confirmed=True)
        self.assertEqual(set(self.calendars.load(self.id)), {"Third"})

    def test_confirmation_ui_moves_calendar_and_survives_rerun(self):
        # Exercise real widgets and persistence without accessing project data.
        import calendar_rename_ui
        script = """
import streamlit as st
import calendar_rename_ui as ui
store, dataset, calendars = ui.test_fixture()
if notice := st.session_state.pop("calendar_rename_notice", None):
    st.success(notice)
ui.show_calendar_rename(store, dataset, calendars, calendars.load(dataset["dataset_id"]), ["New"])
"""
        with patch.object(calendar_rename_ui, "test_fixture",
                          return_value=(self.store, self.dataset, self.calendars), create=True):
            app = AppTest.from_string(script).run()
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any("Confirm" in e.value for e in app.error))
            app.checkbox[0].check()
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any("Timezone kept: Asia/Kolkata" in e.value for e in app.success))
            self.assertTrue(any(b.label == "Correct calendar link" for b in app.button))
            app.run()
            self.assertFalse(app.exception)
            self.assertEqual(self.calendars.load(self.id)["New"]["timezone"], "Asia/Kolkata")

    def correct(self, old="New", new="Old", revision=2, **overrides):
        args = dict(expected_path=self.dataset["path"], expected_revision=revision,
                    confirmed=True)
        args.update(overrides)
        self.store.correct_calendar_link(self.calendars, self.id, old, new, **args)

    def test_reversal_keeps_reservations_and_rejects_aba_editor(self):
        self.rename()
        with self.assertRaisesRegex(ValueError, "Confirm"):
            self.correct(confirmed=False)
        self.correct()
        self.assertEqual(self.calendars.load(self.id),
                         {"Old": {"timezone": "Asia/Kolkata", "revision": 3}})
        self.assertEqual(self.calendars.ownership(self.id), {"New": "Old"})
        for name, revision in (("New", 0), ("New", 2), ("Old", 1)):
            with self.assertRaises(SettingsConflictError):
                self.calendars.save(self.id, name, "UTC", expected_revision=revision)
        with self.assertRaises(SettingsConflictError):
            self.rename()
        self.correct("Old", "New", 3)
        with self.assertRaises(SettingsConflictError):
            self.correct()  # Same names, but an earlier ownership generation.
        self.assertEqual(self.calendars.load(self.id)["New"]["revision"], 4)

    def test_chain_reversal_and_correction_to_current_review_location(self):
        self.rename()
        self.dataset = self.store.save_snapshot("reviews.csv", reviews("Third"), self.id)
        self.store.rename_location_calendar(
            self.calendars, self.id, "New", "Third", expected_path=self.dataset["path"],
            expected_revision=2, confirmed=True)
        self.assertEqual(self.calendars.ownership(self.id), {"Old": "Third", "New": "Third"})
        self.correct("Third", "Old", 3)
        self.assertEqual(self.calendars.ownership(self.id), {"New": "Old", "Third": "Old"})
        self.correct("Old", "New", 4)
        self.assertEqual(self.calendars.ownership(self.id), {"Old": "New", "Third": "New"})
        self.correct("New", "Third", 5)
        self.assertEqual(self.calendars.load(self.id)["Third"]["timezone"], "Asia/Kolkata")

    def test_correction_to_new_name_and_collision(self):
        self.rename()
        self.dataset = self.store.save_snapshot("reviews.csv", reviews("Third"), self.id)
        self.correct("New", "Third", 2)
        self.assertEqual(self.calendars.ownership(self.id), {"Old": "Third", "New": "Third"})
        self.correct("Third", "Old", 3)
        with self.assertRaisesRegex(ValueError, "current review location"):
            self.correct("Old", "Fourth", 4)

    def test_other_calendar_reservation_and_other_dataset_unchanged(self):
        self.rename()
        self.calendars.save(self.id, "Third", "UTC", expected_revision=0)
        self.calendars.rename(self.id, "Third", "Fourth", expected_revision=1, confirmed=True)
        self.dataset = self.store.save_snapshot("reviews.csv", reviews("Third"), self.id)
        before = self.calendars.load(self.id)
        with self.assertRaises(SettingsConflictError):
            self.correct("New", "Third", 2)
        self.assertEqual(before, self.calendars.load(self.id))
        with self.assertRaisesRegex(ValueError, "snapshot changed"):
            self.store.correct_calendar_link(
                self.calendars, "another-dataset", "New", "Old",
                expected_path=self.dataset["path"], expected_revision=2, confirmed=True)

    def test_history_and_review_files_not_modified(self):
        self.rename()
        history = Path(self.calendars.path).parent / "actions.json"
        original = b'[{"location":"Old","baseline":{"count":9},"due_date":"2026-11-10"}]'
        history.write_bytes(original)
        source = Path(self.dataset["path"]).read_bytes()
        self.correct()
        self.assertEqual(history.read_bytes(), original)
        self.assertEqual(Path(self.dataset["path"]).read_bytes(), source)

    def test_live_collision_stale_timezone_dataset_and_permissions(self):
        self.rename()
        self.dataset = self.store.save_snapshot("reviews.csv", reviews("Third"), self.id)
        self.calendars.save(self.id, "Third", "UTC", expected_revision=0)
        before = self.calendars.load(self.id)
        with self.assertRaises(SettingsConflictError):
            self.correct("New", "Third", 2)
        self.assertEqual(before, self.calendars.load(self.id))
        self.calendars.save(self.id, "New", "UTC", expected_revision=2)
        with self.assertRaises(SettingsConflictError):
            self.correct()
        self.store.save_snapshot("reviews.csv", reviews("Old"), self.id)
        with self.assertRaisesRegex(ValueError, "snapshot changed"):
            self.correct(revision=3)
        identity.set_account("test-manager", "synthetic-calendar-password", {self.id: ["New"]})
        with self.assertRaises(PermissionError):
            self.calendars.correct_link(self.id, "New", "Old",
                                        expected_revision=3, confirmed=True)

    def test_two_concurrent_corrections_have_one_winner(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        self.rename()
        self.dataset = self.store.save_snapshot("reviews.csv", reviews("Third"), self.id)
        barrier = Barrier(2)

        def attempt(target):
            barrier.wait(timeout=10)
            try:
                self.correct(new=target)
                return "saved"
            except SettingsConflictError:
                return "conflict"

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(attempt, ["Old", "Third"])),
                                  ["saved", "conflict"])
        self.assertEqual(len(self.calendars.load(self.id)), 1)
        self.assertEqual(next(iter(self.calendars.load(self.id).values()))["revision"], 3)

    def test_correction_ui_requires_confirmation_and_reverses(self):
        import calendar_rename_ui
        self.rename()
        script = """
import streamlit as st
import calendar_rename_ui as ui
store, dataset, calendars = ui.test_fixture()
if notice := st.session_state.pop("calendar_rename_notice", None):
    st.success(notice)
ui.show_calendar_rename(store, dataset, calendars, calendars.load(dataset["dataset_id"]), ["New"])
"""
        with patch.object(calendar_rename_ui, "test_fixture",
                          return_value=(self.store, self.dataset, self.calendars), create=True):
            app = AppTest.from_string(script).run()
            self.assertFalse(app.exception)
            app.button[0].click().run()
            self.assertTrue(any("Confirm" in e.value for e in app.error))
            app.checkbox[0].check()
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any("Calendar corrected" in e.value for e in app.success))
            app.run()
            self.assertEqual(self.calendars.load(self.id)["Old"]["revision"], 3)

    def test_open_confirmation_does_not_approve_newer_timezone(self):
        import calendar_rename_ui
        self.rename()
        script = """
import streamlit as st
import calendar_rename_ui as ui
store, dataset, calendars = ui.test_fixture()
with st.sidebar.expander("Location calendars"):
    ui.show_calendar_rename(store, dataset, calendars, calendars.load(dataset["dataset_id"]), ["New"])
"""
        with patch.object(calendar_rename_ui, "test_fixture",
                          return_value=(self.store, self.dataset, self.calendars), create=True):
            app = AppTest.from_string(script).run()
            app.checkbox[0].check()
            self.calendars.save(self.id, "New", "UTC", expected_revision=2)
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertEqual(self.calendars.load(self.id),
                             {"New": {"timezone": "UTC", "revision": 3}})
            self.assertFalse(app.checkbox[0].value)


if __name__ == "__main__":
    unittest.main()
