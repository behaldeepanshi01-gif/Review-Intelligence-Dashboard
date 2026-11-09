"""Synthetic-only checks of persistence, isolation, reports and the manager UI."""

import copy
import io
from contextlib import closing
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

import engine as E
import manager_corrections as C
import dataset_store as D
from correction_test_support import save_fixture, undo_fixture


APP = Path(__file__).with_name("app.py")
from calendar_test_support import manager_session, sample_app
from dataset_store import SAMPLE_ID


def reviews():
    return pd.DataFrame([
        dict(review_id="demo-1", location="Demo Cafe", date=pd.Timestamp("2026-10-01"),
             rating=3, reviewer="Guest", text="Visited yesterday."),
        dict(review_id="demo-2", location="Demo Cafe", date=pd.Timestamp("2026-10-02"),
             rating=3, reviewer="Guest", text="The service was slow."),
    ])


class ManagerCorrectionTests(unittest.TestCase):
    @staticmethod
    def reply_widget(app):
        return next(w for w in app.text_area if w.label == "Reply draft")

    def open_app(self, source):
        session = manager_session(self, self.temp.name, {SAMPLE_ID: ["Demo Cafe"]})
        return sample_app(AppTest.from_string(source, default_timeout=30), session)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = str(Path(self.temp.name) / "corrections.sqlite")
        self.raw = reviews()
        self.tagged = E.analyze_offline(self.raw)
        self.file = Path(self.temp.name) / "demo.csv"
        self.key = C.review_key(self.file, self.raw.iloc[0])

    def save(self, positive=None, negative=None):
        save_fixture(self.db, self.key, positive or [], negative or [],
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
        save_fixture(self.db, second_key, ["staff"], [], E.LOCAL_ANALYZER_VERSION)
        undo_fixture(self.db, self.key, E.LOCAL_ANALYZER_VERSION)
        undo_fixture(self.db, self.key, E.LOCAL_ANALYZER_VERSION)
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
        save_fixture(self.db, self.key, ["staff"], ["cleanliness"], "old-a")
        save_fixture(self.db, self.key, [], [], "old-b")
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
        undo_fixture(self.db, self.key, E.LOCAL_ANALYZER_VERSION)
        self.assertEqual(set(C.renewal_queue(self.raw, self.file, {}, history)), {self.key})
        # Empty historical tags are still an explicit, valid approval.
        C.approve_prior_correction(self.db, self.file, self.raw.iloc[0],
                                   history[self.key][0], E.LOCAL_ANALYZER_VERSION)
        self.assertFalse(self.effective().iloc[0]["needs_review"])
        self.assertEqual(self.effective().iloc[0]["themes_neg"], [])

    def test_stale_history_cannot_be_approved(self):
        save_fixture(self.db, self.key, [], ["staff"], "old")
        earlier = C.load_prior_corrections(self.db, E.LOCAL_ANALYZER_VERSION)[self.key][0]
        save_fixture(self.db, self.key, [], ["cleanliness"], "old")
        with self.assertRaisesRegex(ValueError, "changed"):
            C.approve_prior_correction(self.db, self.file, self.raw.iloc[0], earlier,
                                       E.LOCAL_ANALYZER_VERSION)
        undo_fixture(self.db, self.key, "old")
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
        save_fixture(self.db, self.key, ["staff"], [], "first")
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
        save_fixture(self.db, self.key, ["staff"], [], "third")
        edited = C.load_corrections(self.db, "third")[self.key]
        self.assertEqual(edited["decision_origin"], "correction")
        self.assertIsNone(edited["source_rules_version"])
        self.assertIsNone(edited["source_decision_revision"])
        undo_fixture(self.db, self.key, "third")
        self.assertEqual(C.load_prior_corrections(self.db, "third")[self.key], history)
        # Removing the source cannot erase an already-recorded renewal origin.
        undo_fixture(self.db, self.key, "first")
        self.assertEqual(C.load_corrections(self.db, "second")[self.key], second)

    def test_same_tags_but_changed_source_revision_cannot_be_renewed(self):
        save_fixture(self.db, self.key, [], [], "old")
        earlier = C.load_corrections(self.db, "old")[self.key]
        with closing(C.sqlite3.connect(self.db)) as db, db:
            db.execute("UPDATE corrections SET saved_at=?", ("different-revision",))
        with self.assertRaisesRegex(ValueError, "changed"):
            C.approve_prior_correction(self.db, self.file, self.raw.iloc[0],
                                      earlier, "current")
        self.assertEqual(C.load_corrections(self.db, "current"), {})

    def test_revision_archive_preserves_edits_undo_and_exact_renewal_chain(self):
        save_fixture(self.db, self.key, ["staff"], [], "first")
        first = C.load_corrections(self.db, "first")[self.key]
        C.approve_prior_correction(self.db, self.file, self.raw.iloc[0], first, "second")
        second = C.load_corrections(self.db, "second")[self.key]
        C.approve_prior_correction(self.db, self.file, self.raw.iloc[0], second, "third")
        third = C.load_corrections(self.db, "third")[self.key]
        # Each referenced source can be replaced and then undone without losing it.
        for version in ("first", "second", "third"):
            save_fixture(self.db, self.key, [], ["cleanliness"], version)
            undo_fixture(self.db, self.key, version)
            undo_fixture(self.db, self.key, version)
            self.assertEqual(C.load_corrections(self.db, version), {})
        revisions = C.load_correction_revisions(self.db, self.key)
        self.assertEqual(len(revisions), 6)
        found = C.find_correction_revision(revisions, "third", third["saved_at"])
        self.assertEqual(found, third)
        for expected in (second, first):
            found = C.find_correction_revision(
                revisions, found["source_rules_version"], found["source_decision_revision"])
            self.assertEqual(found, expected)
        self.assertIsNone(C.find_correction_revision(revisions, "first", "missing"))
        self.assertEqual(C.load_correction_revisions(self.db, "other-review"), [])
        self.assertEqual(C.load_prior_corrections(self.db, "future"), {})
        # Archived or undone sources are not eligible for renewal.
        with self.assertRaisesRegex(ValueError, "changed"):
            C.approve_prior_correction(
                self.db, self.file, self.raw.iloc[0], second, "future")
        self.assertEqual(self.effective().iloc[0]["tag_source"], "local_rules")

    def test_archive_backfills_legacy_and_retired_tags_without_rewriting(self):
        with closing(C.sqlite3.connect(self.db)) as db, db:
            db.execute(
                "CREATE TABLE corrections (review_key TEXT, rules_version TEXT, "
                "positive TEXT, negative TEXT, saved_at TEXT, "
                "PRIMARY KEY (review_key, rules_version))")
            original = (self.key, "old", '["retired_theme"]', "[]", "legacy-revision")
            db.execute("INSERT INTO corrections VALUES (?, ?, ?, ?, ?)", original)
        before = C.load_correction_revisions(self.db, self.key)
        self.assertEqual(before[0]["themes_pos"], ["retired_theme"])
        self.assertEqual(before[0]["decision_origin"], "legacy")
        undo_fixture(self.db, self.key, "old")
        self.assertEqual(C.load_correction_revisions(self.db, self.key), before)
        with closing(C.sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute(
                "SELECT review_key, rules_version, positive, negative, saved_at "
                "FROM correction_revisions").fetchone(), original)
            for operation in (
                    "UPDATE correction_revisions SET positive='[]'",
                    "DELETE FROM correction_revisions"):
                with self.assertRaisesRegex(C.sqlite3.IntegrityError, "append-only"):
                    db.execute(operation)

    def test_repeated_clock_still_produces_distinct_immutable_references(self):
        instant = C.datetime(2026, 1, 1, tzinfo=C.timezone.utc)
        with patch.object(C, "datetime", wraps=C.datetime) as clock:
            clock.now.return_value = instant
            for _ in range(3):
                save_fixture(self.db, self.key, [], [], "same")
                undo_fixture(self.db, self.key, "same")
        revisions = C.load_correction_revisions(self.db, self.key)
        self.assertEqual(len(revisions), 3)
        self.assertEqual(len({r["saved_at"] for r in revisions}), 3)

    def test_archive_failure_rolls_back_manual_save_and_renewal(self):
        save_fixture(self.db, self.key, ["staff"], [], "old")
        earlier = C.load_corrections(self.db, "old")[self.key]
        with closing(C.sqlite3.connect(self.db)) as db, db:
            db.execute("""
                CREATE TRIGGER fail_new_revision BEFORE INSERT ON correction_revisions
                WHEN NOT EXISTS (
                    SELECT 1 FROM correction_revisions
                    WHERE review_key=NEW.review_key AND rules_version=NEW.rules_version
                          AND saved_at=NEW.saved_at
                )
                BEGIN SELECT RAISE(ABORT, 'synthetic archive failure'); END
            """)
        with self.assertRaisesRegex(C.sqlite3.IntegrityError, "synthetic archive"):
            save_fixture(self.db, self.key, [], ["cleanliness"], "old")
        self.assertEqual(C.load_corrections(self.db, "old")[self.key], earlier)
        with self.assertRaisesRegex(C.sqlite3.IntegrityError, "synthetic archive"):
            C.approve_prior_correction(
                self.db, self.file, self.raw.iloc[0], earlier, "current")
        self.assertEqual(C.load_corrections(self.db, "current"), {})
        self.assertEqual(C.load_correction_revisions(self.db, self.key), [earlier])

    def test_streamlit_archive_inspects_chain_after_edit_and_undo_read_only(self):
        save_fixture(self.db, self.key, ["staff"], [], "first")
        first = C.load_corrections(self.db, "first")[self.key]
        C.approve_prior_correction(self.db, self.file, self.raw.iloc[0], first, "second")
        second = C.load_corrections(self.db, "second")[self.key]
        C.approve_prior_correction(self.db, self.file, self.raw.iloc[0], second, "third")
        third = C.load_corrections(self.db, "third")[self.key]
        save_fixture(self.db, self.key, [], ["cleanliness"], "first")
        for version in ("first", "second", "third"):
            undo_fixture(self.db, self.key, version)
        source = (
            "import manager_correction_history as H\n"
            f"H.render({self.db!r}, {self.key!r}, context='test')\n")
        app = AppTest.from_string(source, default_timeout=30).run()
        self.assertFalse(app.exception)
        app.selectbox[0].set_value(("third", third["saved_at"])).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.json), 3)
        self.assertEqual(len(app.button), 0)
        self.assertFalse(app.warning)
        self.assertIn(first["saved_at"], app.json[2].value)
        self.assertIn('"staff"', app.json[2].value)
        self.assertNotIn('"cleanliness"', app.json[2].value)
        self.assertEqual(C.load_prior_corrections(self.db, "future"), {})
        self.assertEqual(len(C.load_correction_revisions(self.db, self.key)), 4)
        # A fresh view still offers undone revisions.
        fresh = AppTest.from_string(source, default_timeout=30).run()
        self.assertEqual(len(fresh.selectbox[0].options), 4)

    def test_streamlit_unrecoverable_legacy_reference_is_explicit(self):
        save_fixture(self.db, self.key, [], [], "old")
        with closing(C.sqlite3.connect(self.db)) as db, db:
            db.execute(
                "UPDATE corrections SET decision_origin='renewal', "
                "source_rules_version='lost-rules', source_decision_revision='lost-revision', "
                "saved_at='legacy-renewal'")
        app = AppTest.from_string(
            "import manager_correction_history as H\n"
            f"H.render({self.db!r}, {self.key!r}, context='missing')\n",
            default_timeout=30).run()
        self.assertFalse(app.exception)
        app.selectbox[0].set_value(("old", "legacy-renewal")).run()
        self.assertTrue(any("Referenced tag revision unavailable" in w.value
                            and "lost-revision" in w.value for w in app.warning))
        self.assertEqual(len(app.json), 1)

    def test_obsolete_history_is_visible_but_cannot_be_reapproved(self):
        save_fixture(self.db, self.key, [], ["staff"], "old")
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
            save_fixture(self.db, stored_key, [], ["staff"], "old")
        with closing(C.sqlite3.connect(self.db)) as db, db:
            db.execute("UPDATE corrections SET negative=?", ('["retired_theme"]',))
        with patch.object(E, "load_reviews", return_value=self.raw):
            app = self.open_app(source)
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
            app = self.open_app(source)
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
        save_fixture(self.db, key, ["staff"], ["cleanliness"], "old-rules")
        earlier = C.load_corrections(self.db, "old-rules")[key]
        changed = self.raw.iloc[0].copy()
        changed["text"] = "No longer the same review."
        save_fixture(self.db, C.review_key(sample, changed), [], ["staff"], "old-rules")
        with patch.object(E, "load_reviews", return_value=self.raw):
            app = self.open_app(source)
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
            app = self.open_app(source)
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
            app = self.open_app(source)
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
            app = self.open_app(source)
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
            app = self.open_app(source)
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
            app = self.open_app(source)
            def button(label):
                return next(b for b in app.button if b.label == label)
            def complaints():
                return next(w for w in app.multiselect
                            if w.label == "Confirmed complaint themes")
            def reply():
                return self.reply_widget(app)
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
            approval_key = reply().key.removeprefix("d_")
            button("Approve reply").click().run()
            approved_tags = copy.deepcopy(app.session_state["approved_reply_tags"])
            self.assertFalse(any(w.label == "Reply draft" for w in app.text_area))
            complaints().set_value(["cleanliness"])
            button("Save manager decision").click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(reply().value, "Previously approved manager wording")
            self.assertEqual(app.session_state["approved"][approval_key],
                             "Previously approved manager wording")
            self.assertEqual(app.session_state["approved_reply_tags"], approved_tags)
            self.assertTrue(any("Approved reply needs recheck" in w.value for w in app.warning))
            # Even if the manager excludes its urgency, a stale approval stays visible.
            next(w for w in app.multiselect if w.label == "Urgency").set_value([]).run()
            self.assertEqual(reply().value, "Previously approved manager wording")
            # A normal rerun cannot acknowledge the changed tags.
            app.run()
            self.assertTrue(any("Approved reply needs recheck" in w.value for w in app.warning))
            button("Undo manager decision").click().run()
            self.assertFalse(any("Approved reply needs recheck" in w.value for w in app.warning))
            self.assertEqual(app.session_state["approved_reply_tags"], approved_tags)
            # Undo restores the approval's tags. A later change requires rechecking again.
            complaints().set_value(["cleanliness"])
            button("Save manager decision").click().run()
            button("Recheck and approve reply").click().run()
            self.assertFalse(any("Approved reply needs recheck" in w.value for w in app.warning))
            self.assertNotEqual(app.session_state["approved_reply_tags"], approved_tags)
            self.assertEqual(app.session_state["approved"][approval_key],
                             "Previously approved manager wording")
            # Undo after reapproval now differs from the new snapshot.
            button("Undo manager decision").click().run()
            self.assertTrue(any("Approved reply needs recheck" in w.value for w in app.warning))
            self.assertEqual(reply().value, "Previously approved manager wording")
            reply().input("Manager checked and revised wording").run()
            button("Recheck and approve reply").click().run()
            self.assertEqual(app.session_state["approved"][approval_key],
                             "Manager checked and revised wording")
            self.assertFalse(any("Approved reply needs recheck" in w.value for w in app.warning))

    def test_approved_reply_recheck_after_renewal_and_unchanged_tags(self):
        source = APP.read_text().replace(
            'BASE_DIR = os.path.dirname(os.path.abspath(__file__))',
            f"BASE_DIR = {str(APP.parent)!r}").replace(
            'CORRECTIONS_LOG = os.path.join(BASE_DIR, "data", "manager_corrections.sqlite")',
            f"CORRECTIONS_LOG = {self.db!r}").replace(
            'UPLOAD_DIR = os.path.join(BASE_DIR, "data", "uploads")',
            f"UPLOAD_DIR = {str(Path(self.temp.name) / 'uploads')!r}")
        key = C.review_key(APP.parent / "data" / "sample_reviews.csv", self.raw.iloc[1])
        save_fixture(self.db, key, [], ["cleanliness"], "old-rules")
        with patch.object(E, "load_reviews", return_value=self.raw):
            app = self.open_app(source)

            def button(label):
                return next(b for b in app.button if b.label == label)

            self.reply_widget(app).input("Approved wait apology").run()
            approval_key = self.reply_widget(app).key.removeprefix("d_")
            button("Approve reply").click().run()
            original_tags = copy.deepcopy(app.session_state["approved_reply_tags"])
            button("Approve earlier tags for current rules").click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertTrue(any("Approved reply needs recheck" in w.value for w in app.warning))
            self.assertEqual(self.reply_widget(app).value, "Approved wait apology")
            self.assertEqual(app.session_state["approved_reply_tags"], original_tags)
            button("Recheck and approve reply").click().run()
            checked_tags = copy.deepcopy(app.session_state["approved_reply_tags"])
            # A new decision with identical effective tags must not invalidate approval.
            # Renewal changed the revision underneath the already-open manual form.
            button("Discard my draft and load latest tags").click().run()
            button("Save manager decision").click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertFalse(any("Approved reply needs recheck" in w.value for w in app.warning))
            self.assertEqual(app.session_state["approved_reply_tags"], checked_tags)
            self.assertEqual(app.session_state["approved"][approval_key], "Approved wait apology")
            # Pre-existing approvals without a snapshot must be explicitly rechecked.
            app.session_state["approved_reply_tags"] = {}
            app.run()
            self.assertTrue(any("Approved reply needs recheck" in w.value for w in app.warning))
            self.assertEqual(self.reply_widget(app).value, "Approved wait apology")

    def reply_isolation_fixture(self):
        """Real saved datasets and exports, isolated from workspace private data."""
        sample = Path(self.temp.name) / "sample.csv"
        self.raw.to_csv(sample, index=False)
        store = D.DatasetStore(Path(self.temp.name) / "uploads", sample)
        source = APP.read_text().replace(
            'CORRECTIONS_LOG = os.path.join(BASE_DIR, "data", "manager_corrections.sqlite")',
            f"CORRECTIONS_LOG = {self.db!r}").replace(
            'LOCATION_SETTINGS = os.path.join(BASE_DIR, "data", "location_settings.sqlite")',
            f"LOCATION_SETTINGS = {str(Path(self.temp.name) / 'calendars.sqlite')!r}")
        # AppTest otherwise retains an old formatted-label mapping when source
        # keys change under identical display labels. Keep this unrelated
        # tag-inspection selector raw in these reply-focused checks.
        source = source.replace(
            '''format_func=lambda key: (
                f"{inspection.loc[inspection['correction_key'] == key, 'review_id'].iloc[0]} | "
                f"{inspection.loc[inspection['correction_key'] == key, 'location'].iloc[0]}"),''',
            "format_func=str,")
        return store, source

    def assert_reply_export(self, downloads, expected):
        exports = [call.args[1] for call in downloads.call_args_list
                   if call.args[0] == "Download analyzed reviews (CSV)"]
        frame = pd.read_csv(io.StringIO(exports[-1]), keep_default_na=False)
        row = frame.set_index("review_id").loc["demo-2"]
        self.assertEqual(row["approved_reply"], expected)
        self.assertFalse(row["approved_reply_needs_recheck"])

    def test_reply_approvals_and_drafts_isolate_colliding_dataset_ids(self):
        store, source = self.reply_isolation_fixture()
        # Even byte-identical reviews must not share approval across datasets.
        other = store.save_snapshot("other.csv", self.raw.to_csv(index=False).encode())
        session = manager_session(self, self.temp.name, {
            SAMPLE_ID: ["Demo Cafe"], other["dataset_id"]: ["Demo Cafe"]})
        with patch.object(D, "DatasetStore", return_value=store), patch(
                "streamlit.download_button") as downloads:
            app = sample_app(AppTest.from_string(source, default_timeout=30), session)
            next(w for w in app.toggle if w.label == "Show approved").set_value(True).run()
            first_widget = self.reply_widget(app).key
            self.reply_widget(app).input("Original dataset approval").run()
            next(b for b in app.button if b.label == "Approve reply").click().run()
            first_approvals = copy.deepcopy(app.session_state["approved"])
            first_tags = copy.deepcopy(app.session_state["approved_reply_tags"])
            self.assert_reply_export(downloads, "Original dataset approval")
            next(w for w in app.radio if w.label == "Data").set_value("Saved file").run()
            self.assertFalse(app.exception)
            self.assertNotEqual(self.reply_widget(app).key, first_widget)
            self.assertNotEqual(self.reply_widget(app).value, "Original dataset approval")
            self.assertEqual(app.session_state["approved"], first_approvals)
            self.assertEqual(app.session_state["approved_reply_tags"], first_tags)
            self.assert_reply_export(downloads, "")
            self.assertTrue(any("1 reviews in queue · 0 approved" in w.value
                                for w in app.caption))
            self.reply_widget(app).input("Other dataset unsaved edit").run()
            next(w for w in app.radio if w.label == "Data").set_value(
                "Sample data (synthetic)").run()
            self.assertEqual(self.reply_widget(app).value, "Original dataset approval")
            self.assert_reply_export(downloads, "Original dataset approval")
            next(w for w in app.radio if w.label == "Data").set_value("Saved file").run()
            self.assertEqual(self.reply_widget(app).value, "Other dataset unsaved edit")
            next(b for b in app.button if b.label == "Approve reply").click().run()
            self.assertEqual(len(app.session_state["approved"]), 2)
            self.assert_reply_export(downloads, "Other dataset unsaved edit")
            next(w for w in app.radio if w.label == "Data").set_value(
                "Sample data (synthetic)").run()
            self.assertFalse(app.exception)
            self.assertEqual(self.reply_widget(app).key, first_widget)
            self.assertEqual(self.reply_widget(app).value, "Original dataset approval")
            for key, value in first_tags.items():
                self.assertEqual(app.session_state["approved_reply_tags"][key], value)

    def test_reply_approval_isolates_replaced_text_and_restores_original(self):
        store, source = self.reply_isolation_fixture()
        content = self.raw.to_csv(index=False).encode()
        saved = store.save_snapshot("reviews.csv", content)
        session = manager_session(self, self.temp.name, {
            SAMPLE_ID: ["Demo Cafe"], saved["dataset_id"]: ["Demo Cafe"]})
        with patch.object(D, "DatasetStore", return_value=store), patch(
                "streamlit.download_button") as downloads:
            app = sample_app(AppTest.from_string(source, default_timeout=30), session)
            next(w for w in app.radio if w.label == "Data").set_value("Saved file").run()
            next(w for w in app.toggle if w.label == "Show approved").set_value(True).run()
            original_widget = self.reply_widget(app).key
            self.reply_widget(app).input("Approval for original text").run()
            next(b for b in app.button if b.label == "Approve reply").click().run()
            original_approvals = copy.deepcopy(app.session_state["approved"])
            original_tags = copy.deepcopy(app.session_state["approved_reply_tags"])
            changed = self.raw.copy()
            # Same ID, urgency and themes: a tag-only comparison cannot detect it.
            changed.loc[1, "text"] = "The service was slow. We visited on Tuesday."
            store.save_snapshot("reviews.csv", changed.to_csv(index=False).encode(),
                                saved["dataset_id"])
            app.run()
            self.assertFalse(app.exception)
            self.assertNotEqual(self.reply_widget(app).key, original_widget)
            self.assertNotEqual(self.reply_widget(app).value, "Approval for original text")
            self.assertEqual(app.session_state["approved"], original_approvals)
            self.assertEqual(app.session_state["approved_reply_tags"], original_tags)
            self.assert_reply_export(downloads, "")
            self.reply_widget(app).input("Approval for replacement text").run()
            next(b for b in app.button if b.label == "Approve reply").click().run()
            self.assertEqual(len(app.session_state["approved"]), 2)
            self.assert_reply_export(downloads, "Approval for replacement text")
            store.save_snapshot("reviews.csv", content, saved["dataset_id"])
            app.run()
            self.assertFalse(app.exception)
            self.assertEqual(self.reply_widget(app).key, original_widget)
            self.assertEqual(self.reply_widget(app).value, "Approval for original text")
            self.assert_reply_export(downloads, "Approval for original text")
            for key, value in original_tags.items():
                self.assertEqual(app.session_state["approved_reply_tags"][key], value)

    def test_reply_approvals_isolate_generated_suffix_id_collisions(self):
        store, source = self.reply_isolation_fixture()
        collision = pd.DataFrame([
            dict(review_id=rid, location="Demo Cafe", date=f"2026-10-0{i + 1}",
                 rating=2, reviewer="Guest",
                 text=f"The service was slow. Synthetic visit {i}.")
            for i, rid in enumerate(["x", "x", "x-0"])
        ])
        dataset = store.save_snapshot(
            "collisions.csv", collision.to_csv(index=False).encode())
        # The loader currently produces x-0, x-1, x-0. Reply identity must
        # remain safe independently of that external-ID normalization.
        loaded = E.load_reviews(dataset["path"])
        self.assertEqual(loaded["review_id"].tolist(), ["x-0", "x-1", "x-0"])
        session = manager_session(self, self.temp.name, {
            dataset["dataset_id"]: ["Demo Cafe"]})
        with patch.object(D, "DatasetStore", return_value=store), patch(
                "streamlit.download_button") as downloads:
            app = AppTest.from_string(source, default_timeout=30)
            app.session_state["_manager_report_grant"] = session
            app.run()
            self.assertFalse(app.exception)
            next(w for w in app.toggle if w.label == "Show approved").set_value(True).run()
            drafts = [w for w in app.text_area if w.label == "Reply draft"]
            self.assertEqual(len(drafts), 3)
            self.assertEqual(len({w.key for w in drafts}), 3)
            # All three rows have equal urgency and appear newest first.
            newest_key, middle_key, oldest_key = [w.key for w in drafts]
            app.text_area(key=newest_key).input("Newest guest wording").run()
            app.button(key="a_" + newest_key.removeprefix("d_")).click().run()
            self.assertNotIn(oldest_key.removeprefix("d_"), app.session_state["approved"])
            app.text_area(key=oldest_key).input("Oldest guest wording").run()
            self.assertEqual(app.text_area(key=newest_key).value, "Newest guest wording")
            app.button(key="a_" + oldest_key.removeprefix("d_")).click().run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.session_state["approved"]), 2)
            snapshots = app.session_state["approved_reply_tags"]
            self.assertEqual(len(snapshots), 2)
            for draft_key in [newest_key, oldest_key]:
                key = draft_key.removeprefix("d_")
                self.assertEqual(snapshots[key]["review_key"], key)
            self.assertNotIn(middle_key.removeprefix("d_"), snapshots)
            exported = [call.args[1] for call in downloads.call_args_list
                        if call.args[0] == "Download analyzed reviews (CSV)"][-1]
            frame = pd.read_csv(io.StringIO(exported), keep_default_na=False).set_index("text")
            self.assertEqual(frame.loc[collision.iloc[0]["text"], "approved_reply"],
                             "Oldest guest wording")
            self.assertEqual(frame.loc[collision.iloc[1]["text"], "approved_reply"], "")
            self.assertEqual(frame.loc[collision.iloc[2]["text"], "approved_reply"],
                             "Newest guest wording")
            self.assertFalse(frame["approved_reply_needs_recheck"].any())


if __name__ == "__main__":
    unittest.main()
