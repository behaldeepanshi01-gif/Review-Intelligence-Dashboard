"""Two manager sessions sharing a registry and log, with isolated synthetic data."""

from datetime import date
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import action_tracker as A
import dataset_store as D
import engine as E
from legacy_history_ui import history_changed
from calendar_test_support import manager_session


DAY = date(2026, 1, 1)


class HistoryRefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "data").mkdir()
        sample = self.root / "data/sample_reviews.csv"
        shutil.copyfile(Path(__file__).parent / "data/sample_reviews.csv", sample)
        self.store = D.DatasetStore(self.root / "data/uploads", sample)
        self.target = self.store.save_snapshot("destination.csv", sample.read_bytes())
        location = E.load_reviews(sample).iloc[0]["location"]
        self.legacy = A.create_action(
            "old.csv", dict(location=location, theme="Service speed",
                            recent_share=40, recent_mentions=4),
            "service_speed", "Original legacy plan", "", DAY, DAY, DAY, today=DAY)
        self.native = dict(self.legacy, action_id="native", dataset_tag=D.SAMPLE_ID,
                           theme="Price", theme_key="price", action_text="Native plan")
        self.log = str(self.root / "data/action_log.json")
        A.save_actions(self.log, [self.legacy, self.native])
        self.source = self.store.claim_legacy_history(
            D.SAMPLE_ID, "old.csv", A.load_actions(self.log))
        source = (Path(__file__).parent / "app.py").read_text().replace(
            "BASE_DIR = os.path.dirname(os.path.abspath(__file__))",
            f"BASE_DIR = {str(self.root)!r}")
        self.app = AppTest.from_string(source, default_timeout=30)
        self.app.session_state["data_source"] = "Sample data (synthetic)"
        self.app.session_state["_manager_report_grant"] = manager_session(
            self, self.root, {D.SAMPLE_ID: list(E.load_reviews(sample)["location"].unique())})
        self.app.run()
        self.assertFalse(self.app.exception)

    def button(self, label, action=None):
        return next(b for b in self.app.button if b.label == label and (
            action is None or f"update_action_{action['action_id']}_" in b.key))

    def text(self, action):
        return next(t for t in self.app.text_area
                    if t.key and t.key.startswith(f"update_text_{action['action_id']}_"))

    def transfer(self):
        # A separate Streamlit session performs the actual manager correction.
        other = AppTest.from_string("""
import streamlit as st
from legacy_history_ui import show_history_controls
store = st.session_state["store"]
show_history_controls(store, store.get(st.session_state["id"]), st.session_state["actions"])
""")
        other.session_state["store"] = self.store
        other.session_state["id"] = D.SAMPLE_ID
        other.session_state["actions"] = A.load_actions(self.log)
        other.session_state["_manager_report_grant"] = self.app.session_state[
            "_manager_report_grant"]
        other.run()
        other.radio[0].set_value("Reassign to another dataset").run()
        other.selectbox[0].set_value(self.target["dataset_id"]).run()
        other.checkbox[0].check().run()
        next(b for b in other.button if b.label == "Confirm history correction").click().run()
        self.assertFalse(other.exception)
        self.assertTrue(history_changed(self.store, self.source))

    def test_two_sessions_transfer_keeps_form_draft_and_blocks_former_owner(self):
        self.text(self.legacy).set_value("Unsaved former-owner draft")
        before = Path(self.log).read_bytes()
        self.transfer()
        self.button("Save updates", self.legacy).click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual(Path(self.log).read_bytes(), before)
        self.assertEqual(self.text(self.legacy).value, "Unsaved former-owner draft")
        self.assertTrue(self.button("Save updates", self.legacy).disabled)
        self.assertFalse(self.button("Save updates", self.native).disabled)
        self.assertTrue(any("history link changed" in w.value for w in self.app.warning))
        self.assertTrue(any("Showing 1 of 1" in c.value for c in self.app.caption))
        self.button("Keep draft and refresh editor").click().run()
        self.assertFalse(self.app.exception)
        self.assertFalse(any(t.key and t.key.startswith(f"update_text_{self.legacy['action_id']}_")
                             for t in self.app.text_area))
        draft = self.app.session_state[f"history_drafts_{D.SAMPLE_ID}"]
        self.assertEqual(draft[self.legacy["action_id"]]["draft"]["action_text"],
                         "Unsaved former-owner draft")
        self.text(self.native).set_value("Native save after transfer")
        self.button("Save updates", self.native).click().run()
        self.assertFalse(self.app.exception)
        saved = A.load_actions(self.log)
        self.assertEqual(saved[0], self.legacy)
        self.assertEqual(saved[1]["action_text"], "Native save after transfer")

    def test_transfer_at_save_time_is_rejected_and_draft_retained(self):
        self.text(self.legacy).set_value("Race draft")
        real_edit = A.edit_saved_action

        def transfer_then_save(*args, **kwargs):
            self.store.correct_legacy_history(
                D.SAMPLE_ID, "old.csv",
                expected_source_revision=self.source["history_revision"],
                target_id=self.target["dataset_id"],
                expected_target_revision=self.target["history_revision"])
            return real_edit(*args, **kwargs)

        with patch.object(A, "edit_saved_action", side_effect=transfer_then_save):
            self.button("Save updates", self.legacy).click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual(A.load_actions(self.log)[0], self.legacy)
        self.assertEqual(self.text(self.legacy).value, "Race draft")
        self.assertEqual(
            self.app.session_state[f"history_drafts_{D.SAMPLE_ID}"]
            [self.legacy["action_id"]]["draft"]["action_text"], "Race draft")

    def test_unlink_relink_requires_new_approval_but_native_save_is_unaffected(self):
        self.store.correct_legacy_history(
            D.SAMPLE_ID, "old.csv", expected_source_revision=self.source["history_revision"])
        self.store.claim_legacy_history(D.SAMPLE_ID, "old.csv", A.load_actions(self.log))
        with self.assertRaises(D.HistoryAssociationError):
            A.edit_saved_action(
                self.log, self.legacy, "Stale", "", "Done", DAY, DAY,
                history_store=self.store, dataset_id=D.SAMPLE_ID,
                session=self.app.session_state["_manager_report_grant"],
                expected_history_revision=self.source["history_revision"])
        saved = A.edit_saved_action(
            self.log, self.native, "Native okay", "", "Done", DAY, DAY,
            history_store=self.store, dataset_id=D.SAMPLE_ID,
            session=self.app.session_state["_manager_report_grant"],
            expected_history_revision=self.source["history_revision"])
        self.assertEqual(saved["action_text"], "Native okay")
        fresh = self.store.get(D.SAMPLE_ID)
        saved = A.edit_saved_action(
            self.log, self.legacy, "Reviewed current ownership", "", "Done", DAY, DAY,
            history_store=self.store, dataset_id=D.SAMPLE_ID,
            session=self.app.session_state["_manager_report_grant"],
            expected_history_revision=fresh["history_revision"])
        self.assertEqual(saved["action_text"], "Reviewed current ownership")


if __name__ == "__main__":
    unittest.main()
