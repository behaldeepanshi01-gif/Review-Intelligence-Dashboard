"""Synthetic two-session checks: stale tags must never overwrite newer decisions."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import engine as E
import manager_corrections as C
from correction_test_support import revision


class CorrectionConcurrencyTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = str(Path(directory.name) / "tags.sqlite")
        self.key = "synthetic-review"
        self.version = E.LOCAL_ANALYZER_VERSION

    def save(self, expected, pos=None, neg=None, key=None, version=None):
        C.save_correction(self.path, key or self.key, pos or [], neg or [],
                          version or self.version, expected_revision=expected)
        return revision(self.path, key or self.key, version or self.version)

    def undo(self, expected):
        C.undo_correction(self.path, self.key, self.version, expected_revision=expected)

    def snapshot(self):
        return (C.load_corrections(self.path, self.version),
                C.load_correction_revisions(self.path, self.key))

    def test_two_creates_and_stale_edit_or_undo_leave_saved_history_unchanged(self):
        # Both managers opened local rules (no decision).
        first = self.save(None, neg=["cleanliness"])
        saved = self.snapshot()
        for operation in (lambda: self.save(None, pos=["staff"]),
                          lambda: self.undo(None)):
            with self.assertRaises(C.CorrectionConflictError):
                operation()
            self.assertEqual(self.snapshot(), saved)
        # Both managers opened first; the winner's identical tags are still a
        # new revision and must invalidate the other open editor.
        second = self.save(first, neg=["cleanliness"])
        self.assertNotEqual(first, second)
        saved = self.snapshot()
        for operation in (lambda: self.save(first, pos=["staff"]),
                          lambda: self.undo(first)):
            with self.assertRaises(C.CorrectionConflictError):
                operation()
            self.assertEqual(self.snapshot(), saved)
        self.undo(second)
        self.assertEqual(C.load_corrections(self.path, self.version), {})
        self.assertEqual(len(C.load_correction_revisions(self.path, self.key)), 2)

    def test_delete_recreate_and_unrelated_keys_and_rules(self):
        first = self.save(None, pos=["staff"])
        self.save(None, neg=["cleanliness"], key="another-review")
        self.save(None, neg=["cleanliness"], version="old-rules")
        second = self.save(first, neg=["service_speed"])
        self.undo(second)
        for operation in (lambda: self.save(second), lambda: self.undo(second)):
            with self.assertRaises(C.CorrectionConflictError):
                operation()
        recreated = self.save(None, pos=["staff"])
        self.assertNotIn(recreated, (first, second))
        with self.assertRaises(C.CorrectionConflictError):
            self.undo(first)
        self.assertEqual(set(C.load_corrections(self.path, self.version)),
                         {self.key, "another-review"})
        self.assertIn(self.key, C.load_corrections(self.path, "old-rules"))

    def test_true_simultaneous_writes_have_only_one_winner(self):
        for initial in (None, "saved"):
            with self.subTest(initial=initial):
                key = f"thread-{initial}"
                expected = self.save(None, key=key) if initial else None
                gate = threading.Barrier(2)

                def writer(theme):
                    gate.wait(timeout=10)
                    try:
                        self.save(expected, neg=[theme], key=key)
                        return "saved"
                    except C.CorrectionConflictError:
                        return "conflict"

                with ThreadPoolExecutor(max_workers=2) as pool:
                    outcomes = list(pool.map(writer, ["staff", "cleanliness"]))
                self.assertCountEqual(outcomes, ["saved", "conflict"])
                self.assertEqual(len(C.load_correction_revisions(self.path, key)),
                                 2 if initial else 1)

    def app(self):
        # Exercise the actual form component with two independent Streamlit
        # sessions sharing only persistence, not session/widget state.
        return AppTest.from_string(f"""
import streamlit as st
import manager_corrections as C
import manager_correction_editor as editor
import engine as E
path = {self.path!r}
key = st.selectbox("Synthetic review", ["synthetic-review", "other-review"])
current = C.load_corrections(path, E.LOCAL_ANALYZER_VERSION).get(key)
row = dict(manager_correction=current, themes_pos=current["themes_pos"] if current else [],
           themes_neg=current["themes_neg"] if current else ["service_speed"],
           rule_output=dict(themes_pos=[], themes_neg=["service_speed"]))
# Match the dashboard's widget cleanup protection across navigation.
for name in list(st.session_state):
    if name.startswith("tag-editor-"):
        st.session_state[name] = st.session_state[name]
editor.render(path, key, row, lambda: None)
""").run()

    def click(self, app, label):
        next(b for b in app.button if b.label == label).click().run()
        self.assertFalse(app.exception)

    def themes(self, app, polarity="complaint"):
        return next(w for w in app.multiselect
                    if w.label == f"Confirmed {polarity} themes")

    def assert_conflict(self, app, draft):
        self.assertFalse(app.exception)
        self.assertTrue(any("Nothing was overwritten" in w.value for w in app.warning))
        self.assertEqual(self.themes(app).value, draft)
        self.assertTrue(next(b for b in app.button
                             if b.label == "Save manager decision").disabled)

    def test_two_forms_keep_draft_until_explicit_review_then_save(self):
        first, second = self.app(), self.app()
        self.themes(first).set_value(["cleanliness"])
        self.click(first, "Save manager decision")
        saved = self.snapshot()
        self.themes(second).set_value(["staff"])
        self.click(second, "Save manager decision")
        self.assert_conflict(second, ["staff"])
        self.assertEqual(self.snapshot(), saved)
        self.assertTrue(any('"cleanliness"' in j.value for j in second.json))
        # Repeated reruns and edits do not clear the draft or accept the latest.
        second.run()
        self.assert_conflict(second, ["staff"])
        self.themes(second, "praise").set_value(["price"])
        self.click(second, "Review latest and keep my draft")
        self.assertEqual(self.themes(second).value, ["staff"])
        self.assertEqual(self.themes(second, "praise").value, ["price"])
        self.assertEqual(self.snapshot(), saved)
        self.click(second, "Save manager decision")
        latest = C.load_corrections(self.path, self.version)[self.key]
        self.assertEqual(latest["themes_pos"], ["price"])
        self.assertEqual(latest["themes_neg"], ["staff"])

    def test_stale_undo_submits_draft_and_discard_loads_latest(self):
        original = self.save(None, neg=["cleanliness"])
        first, second = self.app(), self.app()
        self.themes(first).set_value(["price"])
        self.click(first, "Save manager decision")
        saved = self.snapshot()
        self.themes(second).set_value(["staff"])
        self.click(second, "Undo manager decision")
        self.assert_conflict(second, ["staff"])
        self.assertEqual(self.snapshot(), saved)
        self.click(second, "Discard my draft and load latest tags")
        self.assertEqual(self.themes(second).value, ["price"])
        self.assertEqual(self.snapshot(), saved)
        self.click(second, "Undo manager decision")
        self.assertEqual(C.load_corrections(self.path, self.version), {})
        self.assertEqual(len(C.load_correction_revisions(self.path, self.key)), 2)
        self.assertEqual(self.themes(second).value, ["service_speed"])
        self.assertIsNotNone(original)

    def test_deleted_decision_and_change_during_acknowledgment_remain_protected(self):
        self.save(None, neg=["cleanliness"])
        first, second = self.app(), self.app()
        self.click(first, "Undo manager decision")
        self.themes(second).set_value(["staff"])
        self.click(second, "Save manager decision")
        self.assert_conflict(second, ["staff"])
        self.assertTrue(any("local rules apply" in i.value for i in second.info))
        # Another write after the comparison was rendered must not be silently
        # acknowledged by the stale 'keep' button.
        self.save(None, neg=["price"])
        self.click(second, "Review latest and keep my draft")
        self.assert_conflict(second, ["staff"])
        self.click(second, "Review latest and keep my draft")
        self.click(second, "Save manager decision")
        self.assertEqual(C.load_corrections(self.path, self.version)[self.key][
            "themes_neg"], ["staff"])

    def test_change_after_page_load_inside_save_transaction_keeps_draft(self):
        app = self.app()
        real_save = C.save_correction

        def interleave(*args, **kwargs):
            real_save(self.path, self.key, [], ["cleanliness"], self.version,
                      expected_revision=None)
            return real_save(*args, **kwargs)

        self.themes(app).set_value(["staff"])
        with patch.object(C, "save_correction", side_effect=interleave):
            self.click(app, "Save manager decision")
        self.assert_conflict(app, ["staff"])
        self.assertEqual(len(C.load_correction_revisions(self.path, self.key)), 1)

    def test_conflict_stays_with_review_and_sessions_are_independent(self):
        first, second = self.app(), self.app()
        self.themes(first).set_value(["cleanliness"])
        self.click(first, "Save manager decision")
        self.themes(second).set_value(["staff"])
        self.click(second, "Save manager decision")
        self.assert_conflict(second, ["staff"])
        next(s for s in second.selectbox if s.label == "Synthetic review").set_value(
            "other-review").run()
        self.assertEqual(self.themes(second).value, ["service_speed"])
        next(s for s in second.selectbox if s.label == "Synthetic review").set_value(
            self.key).run()
        self.assert_conflict(second, ["staff"])
        fresh = self.app()
        self.assertEqual(self.themes(fresh).value, ["cleanliness"])
        self.assertFalse(fresh.warning)


if __name__ == "__main__":
    unittest.main()
