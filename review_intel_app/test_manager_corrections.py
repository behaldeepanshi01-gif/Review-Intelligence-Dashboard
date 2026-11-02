"""Synthetic-only checks of persistence, isolation, reports and the manager UI."""

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

import engine as E
import manager_corrections as C


APP = Path(__file__).with_name("app.py")


def reviews():
    return pd.DataFrame([
        dict(review_id="demo-1", location="Demo Cafe", date=pd.Timestamp("2026-10-01"),
             rating=3, reviewer="Guest", text="Visited yesterday."),
        dict(review_id="demo-2", location="Demo Cafe", date=pd.Timestamp("2026-10-02"),
             rating=3, reviewer="Guest", text="The service was slow."),
    ])


class ManagerCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = str(Path(self.temp.name) / "corrections.sqlite")
        self.raw = reviews()
        self.tagged = E.analyze_offline(self.raw)
        self.file = Path(self.temp.name) / "demo.csv"
        self.key = C.review_key(self.file, self.raw.iloc[0])

    def save(self, positive=None, negative=None):
        C.save_correction(self.db, self.key, positive or [], negative or [],
                          E.LOCAL_ANALYZER_VERSION)

    def effective(self, raw=None, file=None, version=None):
        raw = self.raw if raw is None else raw
        return C.apply_corrections(
            raw, E.analyze_offline(raw), file or self.file,
            C.load_corrections(self.db, version or E.LOCAL_ANALYZER_VERSION))

    def test_persist_apply_and_undo_without_mutating_rules_or_other_records(self):
        before = copy.deepcopy(self.tagged.to_dict("records"))
        self.save(["staff"], ["cleanliness"])
        self.assertTrue(Path(self.db).exists())
        saved = C.load_corrections(self.db, E.LOCAL_ANALYZER_VERSION)[self.key]
        self.assertEqual(saved["rules_version"], E.LOCAL_ANALYZER_VERSION)
        out = C.apply_corrections(self.raw, self.tagged, self.file, {self.key: saved})
        first = out.iloc[0]
        self.assertEqual(first["themes_neg"], ["cleanliness"])
        self.assertEqual(first["themes_pos"], ["staff"])
        self.assertEqual(first["sentiment"], "Mixed")
        self.assertEqual(first["urgency"], "High")
        self.assertFalse(first["needs_review"])
        self.assertEqual(first["tag_source"], "manager")
        self.assertEqual(first["tag_evidence"], before[0]["tag_evidence"])
        self.assertEqual(first["rule_output"]["review_reasons"], before[0]["review_reasons"])
        self.assertEqual(self.tagged.to_dict("records"), before)
        self.assertEqual(out.iloc[1]["themes_neg"], before[1]["themes_neg"])
        table = E.theme_table(out)
        self.assertEqual(table.loc[table["theme"] == "Cleanliness", "negative"].iloc[0], 1)
        # Undo only the selected decision. All other decisions remain.
        second_key = C.review_key(self.file, self.raw.iloc[1])
        C.save_correction(self.db, second_key, ["staff"], [], E.LOCAL_ANALYZER_VERSION)
        C.undo_correction(self.db, self.key, E.LOCAL_ANALYZER_VERSION)
        C.undo_correction(self.db, self.key, E.LOCAL_ANALYZER_VERSION)
        self.assertEqual(set(C.load_corrections(self.db, E.LOCAL_ANALYZER_VERSION)),
                         {second_key})
        restored = self.effective().iloc[0]
        self.assertEqual(restored["themes_neg"], before[0]["themes_neg"])
        self.assertEqual(restored["needs_review"], before[0]["needs_review"])
        self.assertEqual(restored["reply_draft"], before[0]["reply_draft"])

    def test_scope_covers_file_identity_all_content_and_rule_version(self):
        self.save(negative=["service_speed"])
        self.assertEqual(self.effective(file=self.file.with_name("other.csv")).iloc[0][
            "tag_source"], "local_rules")
        for field, value in dict(review_id="different", text="Changed review.",
                                 rating=1, location="Other Cafe", reviewer="New Guest",
                                 date=pd.Timestamp("2026-10-03")).items():
            with self.subTest(field=field):
                changed = self.raw.copy()
                changed.at[0, field] = value
                self.assertEqual(self.effective(raw=changed).iloc[0]["tag_source"],
                                 "local_rules")
        self.assertEqual(self.effective(version="future-rules").iloc[0]["tag_source"],
                         "local_rules")
        # Reordering an unchanged review with an explicit ID is safe.
        shuffled = self.raw.iloc[::-1].reset_index(drop=True)
        self.assertEqual(self.effective(raw=shuffled).iloc[1]["tag_source"], "manager")

    def test_empty_approval_mixed_polarity_and_invalid_decisions(self):
        self.save()
        first = self.effective().iloc[0]
        self.assertFalse(first["needs_review"])
        self.assertEqual(first["themes_neg"], [])
        self.assertEqual(first["themes_pos"], [])
        self.save(["service_speed"], ["service_speed"])
        first = self.effective().iloc[0]
        self.assertEqual(first["themes_pos"], first["themes_neg"])
        with self.assertRaises(ValueError):
            self.save(negative=["not-a-theme"])
        Path(self.db).write_text("broken database")
        with self.assertRaises(C.sqlite3.DatabaseError):
            C.load_corrections(self.db, E.LOCAL_ANALYZER_VERSION)

    def test_reports_and_drafts_use_effective_tags(self):
        self.save(negative=["service_speed"])
        effective = self.effective()
        expected = self.tagged.copy()
        row = self.raw.iloc[0]
        fields = E.effective_tag_fields(row["text"], row["rating"], [], ["service_speed"])
        for name, value in fields.items():
            expected.at[0, name] = value
        for calculate in (E.theme_table, E.early_warnings, E.monthly_trend,
                          E.staff_leaderboard):
            pd.testing.assert_frame_equal(calculate(effective), calculate(expected))
        self.assertEqual(effective.iloc[0]["reply_draft"],
                         E.draft_reply_offline(effective.iloc[0].to_dict()))

    def test_streamlit_save_reload_edit_and_undo(self):
        source = APP.read_text().replace(
            'CORRECTIONS_LOG = os.path.join(BASE_DIR, "data", "manager_corrections.sqlite")',
            f"CORRECTIONS_LOG = {self.db!r}")
        with patch.object(E, "load_reviews", return_value=self.raw), patch(
                "os.listdir", return_value=[]):
            app = AppTest.from_string(source, default_timeout=30).run()
            self.assertEqual(len(app.exception), 0)
            def button(label):
                return next(b for b in app.button if b.label == label)
            def themes(label):
                return next(w for w in app.multiselect if w.label == label)
            themes("Confirmed complaint themes").set_value(["cleanliness"])
            button("Save manager decision").click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertTrue(any("Current source: manager" in c.value for c in app.caption))
            # A fresh session must recover the same decision from disk.
            app = AppTest.from_string(source, default_timeout=30).run()
            self.assertEqual(themes("Confirmed complaint themes").value, ["cleanliness"])
            themes("Confirmed complaint themes").set_value([])
            themes("Confirmed praise themes").set_value(["service_speed"])
            button("Save manager decision").click().run()
            self.assertEqual(themes("Confirmed praise themes").value, ["service_speed"])
            self.assertEqual(themes("Confirmed complaint themes").value, [])
            button("Undo manager decision").click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(themes("Confirmed complaint themes").value, ["service_speed"])
            self.assertEqual(themes("Confirmed praise themes").value, [])
            self.assertEqual(C.load_corrections(self.db, E.LOCAL_ANALYZER_VERSION), {})

    def test_same_session_reply_refreshes_on_save_and_undo_but_keeps_approval(self):
        source = APP.read_text().replace(
            'CORRECTIONS_LOG = os.path.join(BASE_DIR, "data", "manager_corrections.sqlite")',
            f"CORRECTIONS_LOG = {self.db!r}")
        with patch.object(E, "load_reviews", return_value=self.raw), patch(
                "os.listdir", return_value=[]):
            app = AppTest.from_string(source, default_timeout=30).run()
            def button(label):
                return next(b for b in app.button if b.label == label)
            def complaints():
                return next(w for w in app.multiselect
                            if w.label == "Confirmed complaint themes")
            def reply():
                return app.text_area(key="d_demo-2")
            self.assertIn("the wait you had", reply().value)
            reply().input("Unapproved manual edit").run()
            # Ordinary reruns must preserve unsaved edits under unchanged tags.
            app.run()
            self.assertEqual(reply().value, "Unapproved manual edit")
            complaints().set_value(["cleanliness"])
            button("Save manager decision").click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertIn("the cleanliness issue", reply().value)
            self.assertNotIn("the wait you had", reply().value)
            button("Undo manager decision").click().run()
            self.assertIn("the wait you had", reply().value)
            self.assertNotIn("the cleanliness issue", reply().value)
            reply().input("Previously approved manager wording").run()
            button("Approve reply").click().run()
            next(t for t in app.toggle if t.label == "Show approved").set_value(True).run()
            complaints().set_value(["cleanliness"])
            button("Save manager decision").click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(reply().value, "Previously approved manager wording")
            button("Undo manager decision").click().run()
            self.assertEqual(reply().value, "Previously approved manager wording")


if __name__ == "__main__":
    unittest.main()
