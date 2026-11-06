"""Synthetic-only checks of persistence, isolation, reports and the manager UI."""

import copy
from contextlib import closing
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

    def test_renewal_history_is_exact_scoped_and_never_applied_automatically(self):
        self.assertEqual(C.load_prior_corrections(self.db, "current"), {})
        C.save_correction(self.db, self.key, ["staff"], ["cleanliness"], "old-a")
        C.save_correction(self.db, self.key, [], [], "old-b")
        history = C.load_prior_corrections(self.db, E.LOCAL_ANALYZER_VERSION)
        self.assertEqual([d["rules_version"] for d in history[self.key]],
                         ["old-b", "old-a"])
        self.assertEqual(self.effective().iloc[0]["tag_source"], "local_rules")
        queue = C.renewal_queue(self.raw, self.file, {}, history)
        self.assertEqual(set(queue), {self.key})
        self.assertEqual(C.renewal_queue(self.raw, self.file.with_name("other.csv"),
                                        {}, history), {})
        for field, value in dict(review_id="changed", text="Changed text", rating=1,
                                 reviewer="Other", location="Other",
                                 date=pd.Timestamp("2026-11-01")).items():
            with self.subTest(field=field):
                changed = self.raw.copy()
                changed.at[0, field] = value
                self.assertEqual(C.renewal_queue(changed, self.file, {}, history), {})
                with self.assertRaises(ValueError):
                    C.approve_prior_correction(
                        self.db, self.file, changed.iloc[0], history[self.key][0],
                        E.LOCAL_ANALYZER_VERSION)
        # A manager may select an older historical decision rather than the latest.
        C.approve_prior_correction(self.db, self.file, self.raw.iloc[0],
                                   history[self.key][1], E.LOCAL_ANALYZER_VERSION)
        current = C.load_corrections(self.db, E.LOCAL_ANALYZER_VERSION)
        self.assertEqual(current[self.key]["source_rules_version"], "old-a")
        self.assertEqual(current[self.key]["source_decision_revision"],
                         history[self.key][1]["saved_at"])
        self.assertEqual(C.renewal_queue(self.raw, self.file, current, history), {})
        self.assertEqual(self.effective().iloc[0]["themes_neg"], ["cleanliness"])
        self.assertEqual(C.load_prior_corrections(self.db, E.LOCAL_ANALYZER_VERSION),
                         history)
        with self.assertRaises(ValueError):
            C.approve_prior_correction(self.db, self.file, self.raw.iloc[0],
                                       history[self.key][0], E.LOCAL_ANALYZER_VERSION)
        C.undo_correction(self.db, self.key, E.LOCAL_ANALYZER_VERSION)
        self.assertEqual(set(C.renewal_queue(self.raw, self.file, {}, history)), {self.key})
        # Empty historical tags are still an explicit, valid approval.
        C.approve_prior_correction(self.db, self.file, self.raw.iloc[0],
                                   history[self.key][0], E.LOCAL_ANALYZER_VERSION)
        self.assertFalse(self.effective().iloc[0]["needs_review"])
        self.assertEqual(self.effective().iloc[0]["themes_neg"], [])

    def test_stale_history_cannot_be_approved(self):
        C.save_correction(self.db, self.key, [], ["staff"], "old")
        earlier = C.load_prior_corrections(self.db, E.LOCAL_ANALYZER_VERSION)[self.key][0]
        C.save_correction(self.db, self.key, [], ["cleanliness"], "old")
        with self.assertRaisesRegex(ValueError, "changed"):
            C.approve_prior_correction(self.db, self.file, self.raw.iloc[0], earlier,
                                       E.LOCAL_ANALYZER_VERSION)
        C.undo_correction(self.db, self.key, "old")
        with self.assertRaisesRegex(ValueError, "changed"):
            C.approve_prior_correction(self.db, self.file, self.raw.iloc[0], earlier,
                                       E.LOCAL_ANALYZER_VERSION)
        self.assertEqual(C.load_corrections(self.db, E.LOCAL_ANALYZER_VERSION), {})

    def test_legacy_migration_preserves_records_without_guessing_origin(self):
        with closing(C.sqlite3.connect(self.db)) as db, db:
            db.execute(
                "CREATE TABLE corrections (review_key TEXT, rules_version TEXT, "
                "positive TEXT, negative TEXT, saved_at TEXT, "
                "PRIMARY KEY (review_key, rules_version))")
            original = (self.key, "old", '["staff"]', '["cleanliness"]', "legacy-revision")
            db.execute("INSERT INTO corrections VALUES (?, ?, ?, ?, ?)", original)
        earlier = C.load_prior_corrections(self.db, "current")[self.key][0]
        self.assertEqual(earlier["decision_origin"], "legacy")
        self.assertIsNone(earlier["source_rules_version"])
        self.assertIsNone(earlier["source_decision_revision"])
        self.assertIn("origin not recorded", C.decision_origin_label(earlier))
        C.approve_prior_correction(self.db, self.file, self.raw.iloc[0], earlier, "current")
        renewed = C.load_corrections(self.db, "current")[self.key]
        self.assertEqual(renewed["source_rules_version"], "old")
        self.assertEqual(renewed["source_decision_revision"], "legacy-revision")
        # Repeated opens are safe, and the original row's bytes remain unchanged.
        self.assertEqual(C.load_prior_corrections(self.db, "current")[self.key][0], earlier)
        with closing(C.sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute(
                "SELECT review_key, rules_version, positive, negative, saved_at "
                "FROM corrections WHERE rules_version='old'").fetchone(), original)

    def test_renewal_links_selected_revision_across_reload_chain_edit_and_undo(self):
        C.save_correction(self.db, self.key, ["staff"], [], "first")
        first = C.load_corrections(self.db, "first")[self.key]
        C.approve_prior_correction(self.db, self.file, self.raw.iloc[0], first, "second")
        second = C.load_corrections(self.db, "second")[self.key]
        self.assertEqual(second["decision_origin"], "renewal")
        self.assertEqual(second["source_rules_version"], "first")
        self.assertEqual(second["source_decision_revision"], first["saved_at"])
        C.approve_prior_correction(self.db, self.file, self.raw.iloc[0], second, "third")
        third = C.load_corrections(self.db, "third")[self.key]
        self.assertEqual(third["source_rules_version"], "second")
        self.assertEqual(third["source_decision_revision"], second["saved_at"])
        history = C.load_prior_corrections(self.db, "third")[self.key]
        self.assertIn(second, history)
        self.assertIn(first, history)
        # A separate manual save is not attributed to a renewal, even with identical tags.
        C.save_correction(self.db, self.key, ["staff"], [], "third")
        edited = C.load_corrections(self.db, "third")[self.key]
        self.assertEqual(edited["decision_origin"], "correction")
        self.assertIsNone(edited["source_rules_version"])
        self.assertIsNone(edited["source_decision_revision"])
        C.undo_correction(self.db, self.key, "third")
        self.assertEqual(C.load_prior_corrections(self.db, "third")[self.key], history)
        # Removing the source cannot erase an already-recorded renewal origin.
        C.undo_correction(self.db, self.key, "first")
        self.assertEqual(C.load_corrections(self.db, "second")[self.key], second)

    def test_same_tags_but_changed_source_revision_cannot_be_renewed(self):
        C.save_correction(self.db, self.key, [], [], "old")
        earlier = C.load_corrections(self.db, "old")[self.key]
        with closing(C.sqlite3.connect(self.db)) as db, db:
            db.execute("UPDATE corrections SET saved_at=?", ("different-revision",))
        with self.assertRaisesRegex(ValueError, "changed"):
            C.approve_prior_correction(self.db, self.file, self.raw.iloc[0],
                                      earlier, "current")
        self.assertEqual(C.load_corrections(self.db, "current"), {})

    def test_obsolete_history_is_visible_but_cannot_be_reapproved(self):
        C.save_correction(self.db, self.key, [], ["staff"], "old")
        # Simulate a theme that was valid when the old rules were active.
        with closing(C.sqlite3.connect(self.db)) as db, db:
            db.execute("UPDATE corrections SET negative=?", ('["retired_theme"]',))
        prior = C.load_prior_corrections(self.db, E.LOCAL_ANALYZER_VERSION)
        self.assertEqual(prior[self.key][0]["themes_neg"], ["retired_theme"])
        self.assertEqual(self.effective().iloc[0]["tag_source"], "local_rules")
        with self.assertRaisesRegex(ValueError, "unsupported"):
            C.approve_prior_correction(self.db, self.file, self.raw.iloc[0],
                                       prior[self.key][0], E.LOCAL_ANALYZER_VERSION)
        self.assertEqual(C.load_corrections(self.db, E.LOCAL_ANALYZER_VERSION), {})

    def test_streamlit_obsolete_history_never_blocks_reports_or_valid_corrections(self):
        source = APP.read_text().replace(
            'BASE_DIR = os.path.dirname(os.path.abspath(__file__))',
            f"BASE_DIR = {str(APP.parent)!r}").replace(
            'CORRECTIONS_LOG = os.path.join(BASE_DIR, "data", "manager_corrections.sqlite")',
            f"CORRECTIONS_LOG = {self.db!r}").replace(
            'UPLOAD_DIR = os.path.join(BASE_DIR, "data", "uploads")',
            f"UPLOAD_DIR = {str(Path(self.temp.name) / 'uploads')!r}")
        sample = APP.parent / "data" / "sample_reviews.csv"
        key = C.review_key(sample, self.raw.iloc[1])
        other_key = C.review_key(self.file.with_name("unrelated.csv"), self.raw.iloc[0])
        for stored_key in (key, other_key):
            C.save_correction(self.db, stored_key, [], ["staff"], "old")
        with closing(C.sqlite3.connect(self.db)) as db, db:
            db.execute("UPDATE corrections SET negative=?", ('["retired_theme"]',))
        with patch.object(E, "load_reviews", return_value=self.raw):
            app = AppTest.from_string(source, default_timeout=30).run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.error), 0)
            self.assertTrue(app.tabs)
            self.assertTrue(any("Decisions needing renewed approval (1)" == h.value
                                for h in app.subheader))
            self.assertTrue(any("retired_theme" in w.value for w in app.warning))
            self.assertTrue(next(b for b in app.button
                                 if b.label == "Approve earlier tags for current rules").disabled)
            next(w for w in app.multiselect
                 if w.label == "Confirmed complaint themes").set_value(["cleanliness"])
            next(b for b in app.button if b.label == "Save manager decision").click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.error), 0)
            self.assertEqual(C.load_corrections(self.db, E.LOCAL_ANALYZER_VERSION)[key][
                "themes_neg"], ["cleanliness"])
            # Only unrelated obsolete history remains; reports still load.
            app = AppTest.from_string(source, default_timeout=30).run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(len(app.error), 0)
            self.assertTrue(any("Decisions needing renewed approval (0)" == h.value
                                for h in app.subheader))

    def test_streamlit_renewal_compare_approve_reload_and_filter(self):
        source = APP.read_text().replace(
            'BASE_DIR = os.path.dirname(os.path.abspath(__file__))',
            f"BASE_DIR = {str(APP.parent)!r}").replace(
            'CORRECTIONS_LOG = os.path.join(BASE_DIR, "data", "manager_corrections.sqlite")',
            f"CORRECTIONS_LOG = {self.db!r}").replace(
            'UPLOAD_DIR = os.path.join(BASE_DIR, "data", "uploads")',
            f"UPLOAD_DIR = {str(Path(self.temp.name) / 'uploads')!r}")
        # Built-in sample identity, but only synthetic in-memory reviews are loaded.
        sample = APP.parent / "data" / "sample_reviews.csv"
        key = C.review_key(sample, self.raw.iloc[1])
        C.save_correction(self.db, key, ["staff"], ["cleanliness"], "old-rules")
        earlier = C.load_corrections(self.db, "old-rules")[key]
        changed = self.raw.iloc[0].copy()
        changed["text"] = "No longer the same review."
        C.save_correction(self.db, C.review_key(sample, changed), [], ["staff"], "old-rules")
        with patch.object(E, "load_reviews", return_value=self.raw):
            app = AppTest.from_string(source, default_timeout=30).run()
            self.assertEqual(len(app.exception), 0)
            self.assertTrue(any("1 unchanged reviews need renewed" in w.value
                                for w in app.warning))
            self.assertTrue(any("Decisions needing renewed approval (1)" == h.value
                                for h in app.subheader))
            # Read-only reruns never create a current-version decision.
            app.run()
            self.assertEqual(C.load_corrections(self.db, E.LOCAL_ANALYZER_VERSION), {})
            displayed = [j.value for j in app.json]
            self.assertTrue(any('"cleanliness"' in j and '"staff"' in j for j in displayed))
            self.assertTrue(any('"service_speed"' in j for j in displayed))
            # Narrow the date range to exclude the pending review.
            next(w for w in app.slider if w.label == "Date range").set_range(
                self.raw.iloc[0]["date"].date(), self.raw.iloc[0]["date"].date()).run()
            self.assertTrue(any("Decisions needing renewed approval (0)" == h.value
                                for h in app.subheader))
            self.assertFalse(any(b.label == "Approve earlier tags for current rules"
                                 for b in app.button))
            # A new session recovers the queue from disk and can explicitly approve.
            app = AppTest.from_string(source, default_timeout=30).run()
            next(b for b in app.button
                 if b.label == "Approve earlier tags for current rules").click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertTrue(any("Decisions needing renewed approval (0)" == h.value
                                for h in app.subheader))
            self.assertEqual(C.load_corrections(self.db, E.LOCAL_ANALYZER_VERSION)[
                key]["themes_neg"], ["cleanliness"])
            renewed = C.load_corrections(self.db, E.LOCAL_ANALYZER_VERSION)[key]
            self.assertEqual(renewed["source_rules_version"], "old-rules")
            self.assertEqual(renewed["source_decision_revision"], earlier["saved_at"])
            origin = C.decision_origin_label(renewed)
            self.assertTrue(any(c.value == origin for c in app.caption))
            self.assertTrue(any("Current source: manager" in c.value for c in app.caption))
            app = AppTest.from_string(source, default_timeout=30).run()
            self.assertTrue(any(c.value == origin for c in app.caption))
            self.assertFalse(any(b.label == "Approve earlier tags for current rules"
                                 for b in app.button))
            self.assertEqual(len(C.load_prior_corrections(
                self.db, E.LOCAL_ANALYZER_VERSION)[key]), 1)

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
            self.assertTrue(any("Newly entered manager correction" in c.value
                                for c in app.caption))
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
