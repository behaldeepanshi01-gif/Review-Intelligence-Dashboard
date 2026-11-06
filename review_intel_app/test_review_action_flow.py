"""Verify the real CSV loader and action lifecycle using only synthetic data."""

import csv
from datetime import date, timedelta
import io
from pathlib import Path
import tempfile
import unittest
import copy
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

import action_tracker as A
import dataset_store as D
import engine as E
import manager_corrections as C
from dataset_store import DatasetStore, SAMPLE_ID
from calendar_test_support import manager_session, sample_app


SAMPLE = Path(__file__).parent / "data" / "sample_reviews.csv"


class ActionProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "synthetic.csv"
        self.db = self.root / "decisions.sqlite"
        self.raw = pd.DataFrame([
            {"review_id": str(i), "location": "Demo Cafe",
             "date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=i),
             "rating": 1, "text": "Service was slow."}
            for i in range(8)
        ])
        self.version = E.LOCAL_ANALYZER_VERSION

    def provenance(self, raw=None, version=None):
        version = version or self.version
        return C.tagging_provenance(
            self.raw if raw is None else raw, self.path,
            C.load_corrections(self.db, version), version)

    def action(self, provenance):
        action = A.create_action(
            "synthetic", {"location": "Demo Cafe", "theme": "Service speed",
                          "recent_share": 60, "recent_mentions": 3},
            "service_speed", "Check handoffs.", "Manager",
            date(2026, 1, 2), date(2026, 1, 20), date(2026, 1, 2),
            tagging_provenance=provenance,
        )
        action["status"] = "In progress"
        return action

    def compare(self, action, provenance):
        tagged = C.apply_corrections(
            self.raw, E.analyze_offline(self.raw), self.path,
            C.load_corrections(self.db, self.version))
        return A.follow_up(
            action, tagged.to_dict("records"), current_provenance=provenance)

    def test_correction_changes_undo_and_rules_upgrade_preserve_saved_baseline(self):
        action = self.action(self.provenance())
        log = str(self.root / "actions.json")
        A.save_actions(log, [action])
        original = Path(log).read_bytes()
        action = A.load_actions(log)[0]
        self.assertEqual(self.compare(action, self.provenance())["provenance_status"],
                         "unchanged")
        key = C.review_key(self.path, self.raw.iloc[3])
        C.save_correction(self.db, key, [], [], self.version)
        corrected = self.compare(action, self.provenance())
        self.assertTrue(corrected["ready"])
        self.assertEqual(corrected["mentions"], 5)
        self.assertEqual(corrected["provenance_status"], "changed")
        self.assertIn("manager decisions changed", corrected["provenance_message"])
        C.undo_correction(self.db, key, self.version)
        self.assertEqual(self.compare(action, self.provenance())["provenance_status"],
                         "unchanged")

        C.save_correction(self.db, key, [], [], self.version)
        corrected_action = self.action(self.provenance())
        C.save_correction(self.db, key, [], ["service_speed"], self.version)
        self.assertEqual(self.compare(corrected_action, self.provenance())[
            "provenance_status"], "changed")
        C.save_correction(self.db, key, [], [], self.version)
        self.assertEqual(self.compare(corrected_action, self.provenance())[
            "provenance_status"], "unchanged")
        C.undo_correction(self.db, key, self.version)
        self.assertEqual(self.compare(corrected_action, self.provenance())[
            "provenance_status"], "changed")
        with patch.object(E, "LOCAL_ANALYZER_VERSION", "synthetic-upgrade"):
            upgraded = self.compare(action, self.provenance(version="synthetic-upgrade"))
        self.assertEqual(upgraded["provenance_status"], "changed")
        self.assertIn("local rules changed", upgraded["provenance_message"])
        self.assertEqual(action["baseline_share"], 60)
        self.assertEqual(Path(log).read_bytes(), original)

    def test_fingerprint_ignores_timestamps_order_and_unrelated_decisions(self):
        key = C.review_key(self.path, self.raw.iloc[0])
        C.save_correction(self.db, key, ["service_speed", "price"], [], self.version)
        first = self.provenance()
        C.save_correction(self.db, key, ["price", "service_speed", "price"], [], self.version)
        self.assertEqual(self.provenance(), first)
        self.assertEqual(self.provenance(raw=self.raw.iloc[::-1]), first)
        unrelated = self.raw.iloc[0].copy()
        unrelated["location"] = "Other Cafe"
        C.save_correction(self.db, C.review_key(self.path, unrelated), [], [], self.version)
        C.save_correction(self.db, C.review_key(self.root / "other.csv", self.raw.iloc[0]),
                          [], [], self.version)
        C.save_correction(self.db, key, [], [], "older-version")
        self.assertEqual(self.provenance(), first)
        appended = pd.concat([self.raw, self.raw.iloc[[0]].assign(review_id="new")])
        self.assertEqual(self.provenance(raw=appended), first)

    def test_unknown_provenance_and_editing_do_not_backfill_history(self):
        action = self.action(self.provenance())
        del action["baseline_provenance"]
        original = copy.deepcopy(action)
        for current in (self.provenance(), None):
            result = self.compare(action, current)
            self.assertEqual(result["provenance_status"], "unknown")
            self.assertIn("Baseline tagging provenance unknown", result["provenance_message"])
        updated = A.update_action(
            action, "Check preparation.", "Manager", "Done",
            date(2026, 1, 2), date(2026, 1, 20))
        self.assertNotIn("baseline_provenance", updated)
        self.assertEqual(action, original)
        known = self.action(self.provenance())
        self.assertEqual(self.compare(known, None)["provenance_status"], "unknown")
        waiting = A.follow_up(known, [], current_provenance=self.provenance(
            version="synthetic-upgrade"))
        self.assertFalse(waiting["ready"])
        self.assertEqual(waiting["provenance_status"], "changed")

    def test_decision_breakdown_added_changed_removed_and_restored(self):
        keys = [C.review_key(self.path, self.raw.iloc[i]) for i in range(3)]
        C.save_correction(self.db, keys[0], [], ["service_speed"], self.version)
        C.save_correction(self.db, keys[1], [], ["price"], self.version)
        action = self.action(self.provenance())
        original = copy.deepcopy(action)
        C.save_correction(self.db, keys[0], ["service_speed"], [], self.version)
        C.undo_correction(self.db, keys[1], self.version)
        C.save_correction(self.db, keys[2], [], [], self.version)
        result = self.compare(action, self.provenance())
        self.assertEqual(result["decisions_status"], "changed")
        self.assertIn("1 added, 1 changed, 1 removed", result["decisions_message"])
        rows = {row["decision_ref"]: row for row in result["decision_changes"]}
        self.assertEqual(rows[keys[0]]["change"], "changed")
        self.assertEqual(rows[keys[0]]["before"]["negative"], ["service_speed"])
        self.assertEqual(rows[keys[0]]["after"]["positive"], ["service_speed"])
        self.assertIn("Recorded action-theme tags changed", rows[keys[0]]["theme_evidence"])
        self.assertIn("unproven", rows[keys[0]]["theme_evidence"])
        self.assertEqual(rows[keys[1]]["change"], "removed")
        self.assertIsNone(rows[keys[1]]["after"])
        self.assertEqual(rows[keys[2]]["change"], "added")
        self.assertIsNone(rows[keys[2]]["before"])
        self.assertIn("not established", rows[keys[2]]["theme_evidence"])
        self.assertIn("Location-wide", result["decisions_scope"])
        self.assertEqual(action, original)
        # The returned detail cannot mutate either historical or current records.
        rows[keys[0]]["before"]["negative"].clear()
        self.assertEqual(action, original)
        C.save_correction(self.db, keys[0], [], ["service_speed"], self.version)
        C.save_correction(self.db, keys[1], [], ["price"], self.version)
        C.undo_correction(self.db, keys[2], self.version)
        restored = self.compare(action, self.provenance())
        self.assertEqual(restored["decisions_status"], "unchanged")
        self.assertEqual(restored["decision_changes"], [])

    def test_unrelated_theme_and_rules_changes_are_not_proven_action_effects(self):
        key = C.review_key(self.path, self.raw.iloc[0])
        C.save_correction(self.db, key, [], ["price"], self.version)
        action = self.action(self.provenance())
        C.save_correction(self.db, key, ["price"], [], self.version)
        result = self.compare(action, self.provenance())
        self.assertIn("Location-wide change only",
                      result["decision_changes"][0]["theme_evidence"])
        upgraded = self.compare(action, self.provenance(version="synthetic-upgrade"))
        self.assertEqual(upgraded["decision_changes"][0]["change"], "removed")
        self.assertIn("not an undo", upgraded["decisions_message"])
        empty = self.action(self.provenance(version="synthetic-upgrade"))
        same_tags_new_rules = self.compare(empty, self.provenance(version="later-upgrade"))
        self.assertEqual(same_tags_new_rules["decisions_status"], "unchanged")
        self.assertEqual(same_tags_new_rules["provenance_status"], "changed")

    def test_missing_legacy_or_partial_detail_stays_unknown_without_backfill(self):
        current = self.provenance()
        action = self.action(current)
        legacy = copy.deepcopy(action)
        legacy["baseline_provenance"].pop("decisions")
        legacy["baseline_provenance"].pop("decisions_version")
        original = copy.deepcopy(legacy)
        result = self.compare(legacy, current)
        self.assertEqual(result["provenance_status"], "unchanged")
        self.assertEqual(result["decisions_status"], "unknown")
        self.assertEqual(result["decision_changes"], [])
        self.assertIn("Baseline decision detail unknown", result["decisions_message"])
        for bad in (None, {}, dict(current, decisions_version=999),
                    dict(current, decisions={"incomplete": {}}),
                    dict(current, decisions_fingerprint="wrong")):
            with self.subTest(bad=bad):
                result = self.compare(action, bad)
                self.assertEqual(result["decisions_status"], "unknown")
                self.assertEqual(result["decision_changes"], [])
        log = str(self.root / "legacy.json")
        A.save_actions(log, [legacy])
        updated = A.edit_saved_action(log, legacy, "Check handoffs.", "Manager", "Done",
                                      date(2026, 1, 2), date(2026, 1, 20))
        self.assertEqual(updated["baseline_provenance"], original["baseline_provenance"])
        self.assertEqual(legacy, original)

    def test_capture_is_detached_minimal_private_and_persists_exactly(self):
        raw = self.raw.copy()
        raw["reviewer"] = "SYNTHETIC PRIVATE GUEST"
        key = C.review_key(self.path, raw.iloc[0])
        C.save_correction(self.db, key, ["price"], ["service_speed"], self.version)
        provenance = self.provenance(raw=raw)
        provenance["raw_text"] = "SYNTHETIC PRIVATE GUEST Service was slow."
        action = self.action(provenance)
        baseline = copy.deepcopy(action["baseline_provenance"])
        provenance["decisions"][key]["positive"].clear()
        self.assertEqual(action["baseline_provenance"], baseline)
        log = self.root / "minimal.json"
        A.save_actions(str(log), [action])
        saved = log.read_text()
        for private in ("SYNTHETIC PRIVATE GUEST", "Service was slow.", str(self.path),
                        "saved_at", "raw_text"):
            self.assertNotIn(private, saved)
        self.assertEqual(set(baseline),
                         {"rules_version", "decisions_fingerprint",
                          "decisions_version", "decisions"})
        self.assertEqual(A.load_actions(str(log))[0], action)
        summary = "\n".join(A.weekly_action_summary(
            [action], "synthetic", ["Demo Cafe"], [],
            provenance_by_location={"Demo Cafe": self.provenance(raw=raw)}))
        self.assertNotIn(key, summary)

    def test_private_decision_ui_rechecks_exact_scope_and_revoked_account(self):
        import manager_identity as identity
        import action_decisions_ui as UI
        key = C.review_key(self.path, self.raw.iloc[0])
        action = self.action(self.provenance())
        C.save_correction(self.db, key, [], ["price"], self.version)
        result = self.compare(action, self.provenance())
        script = f'''
import streamlit as st
from action_decisions_ui import show_decision_changes
show_decision_changes({action!r}, "synthetic", {result!r})
'''
        with patch.object(identity, "DB_PATH", self.root / "accounts.sqlite"):
            identity.set_account("demo-manager", "synthetic-long-password",
                                 {"synthetic": ["Demo Cafe"]})
            grant = identity.authenticate("demo-manager", "synthetic-long-password")
            app = AppTest.from_string(script).run()
            self.assertFalse(app.exception)
            self.assertFalse(app.dataframe)
            self.assertTrue(any("locked" in item.value for item in app.info))
            app.session_state["_manager_report_grant"] = grant
            app.run()
            self.assertFalse(app.exception)
            self.assertEqual(app.dataframe[0].value.iloc[0]["Change"], "Added")
            self.assertEqual(app.dataframe[0].value.iloc[0]["Decision reference"], key)
            # Same identity, wrong dataset or restaurant: no detail reaches the UI.
            for dataset, location in (("other-dataset", "Demo Cafe"),
                                      ("synthetic", "Other Cafe")):
                denied_script = (
                    "from action_decisions_ui import show_decision_changes\n"
                    f"show_decision_changes({dict(action, location=location)!r}, "
                    f"{dataset!r}, {result!r})")
                denied = AppTest.from_string(denied_script)
                denied.session_state["_manager_report_grant"] = grant
                denied.run()
                self.assertFalse(denied.exception)
                self.assertFalse(denied.dataframe)
            with patch.object(identity.time, "time", return_value=grant["expires"]):
                app.run()
                self.assertFalse(app.dataframe)
            identity.remove_account("demo-manager")
            app.run()
            self.assertFalse(app.dataframe)
            self.assertFalse(app.exception)
        # Authorized older histories remain visibly unknown, not a zero-change claim.
        legacy = copy.deepcopy(action)
        legacy["baseline_provenance"].pop("decisions")
        with patch.object(UI, "authorized", return_value=True):
            unknown_result = self.compare(legacy, self.provenance())
            unknown = AppTest.from_string(
                "from action_decisions_ui import show_decision_changes\n"
                f"show_decision_changes({legacy!r}, 'synthetic', {unknown_result!r})").run()
        self.assertTrue(any("Baseline decision detail unknown" in w.value
                            for w in unknown.warning))
        self.assertFalse(unknown.dataframe)

    def test_weekly_summary_labels_each_comparison(self):
        known = self.action(self.provenance())
        changed = copy.deepcopy(known)
        changed["baseline_provenance"]["rules_version"] = "earlier-rules"
        older = copy.deepcopy(known)
        del older["baseline_provenance"]
        reviews = E.analyze_offline(self.raw).to_dict("records")
        text = "\n".join(A.weekly_action_summary(
            [known, changed, older], "synthetic", ["Demo Cafe"], reviews,
            provenance_by_location={"Demo Cafe": self.provenance()}))
        self.assertIn("Tagging provenance unchanged", text)
        self.assertIn("Tagging changed", text)
        self.assertIn("Baseline tagging provenance unknown", text)
        self.assertEqual(text.count("Follow-up:"), 3)

    def test_action_tracker_renders_known_changed_and_legacy_provenance(self):
        raw = E.load_reviews(SAMPLE)
        session = manager_session(self, self.root, {
            SAMPLE_ID: list(raw["location"].unique()) + ["Removed Cafe"]})
        location = raw.iloc[0]["location"]
        provenance = C.tagging_provenance(
            raw[raw["location"] == location], SAMPLE, {}, self.version)
        base = self.action(provenance)
        base.update(dataset_tag=SAMPLE_ID, location=location)
        base["baseline_source"] = D.source_cohort(
            raw.to_dict("records"), SAMPLE_ID, location, base["alert_end_date"])
        changed = copy.deepcopy(base)
        changed["action_id"] = "changed"
        changed["baseline_provenance"]["rules_version"] = "earlier-rules"
        changed["baseline_source"]["counts"]["synthetic-removed-review"] = 1
        legacy = dict(base, action_id="legacy")
        del legacy["baseline_provenance"]
        del legacy["baseline_source"]
        removed_location = copy.deepcopy(base)
        removed_location.update(action_id="missing-location", location="Removed Cafe")
        removed_location["baseline_source"].update(
            location="Removed Cafe", counts={"synthetic-removed-review": 1})
        with patch.object(A, "load_actions",
                          return_value=[base, changed, legacy, removed_location]), \
                patch.object(C, "load_corrections", return_value={}), \
                patch.object(C, "load_prior_corrections", return_value={}):
            app = AppTest.from_file(str(SAMPLE.parent.parent / "app.py"),
                                   default_timeout=30)
            sample_app(app, session)
        self.assertEqual(list(app.exception), [])
        self.assertTrue(any("Tagging provenance unchanged" in item.value
                            for item in app.caption))
        self.assertTrue(any("Tagging changed" in item.value for item in app.warning))
        self.assertTrue(any("Baseline tagging provenance unknown" in item.value
                            for item in app.warning))
        self.assertTrue(any("Source cohort unchanged" in item.value for item in app.caption))
        self.assertTrue(any("Source data changed" in item.value for item in app.warning))
        self.assertTrue(any("Source-data comparability unknown" in item.value
                            for item in app.warning))
        self.assertTrue(any("Removed Cafe is absent" in item.value
                            and "Source data changed" in item.value for item in app.warning))

    def test_saving_action_from_warning_captures_location_provenance(self):
        actions = []
        session = manager_session(self, self.root,
                                  {SAMPLE_ID: list(E.load_reviews(SAMPLE)["location"].unique())})

        def save(_path, action, **_kwargs):
            actions.append(action)

        with patch.object(A, "load_actions", side_effect=lambda *_: list(actions)), \
                patch.object(A, "append_action", side_effect=save), \
                patch.object(C, "load_corrections", return_value={}), \
                patch.object(C, "load_prior_corrections", return_value={}):
            app = AppTest.from_file(str(SAMPLE.parent.parent / "app.py"),
                                   default_timeout=30)
            sample_app(app, session)
            self.assertEqual(list(app.exception), [])
            next(button for button in app.button
                 if button.label == "Save action plan").click().run()
            self.assertEqual(list(app.exception), [])
        self.assertEqual(len(actions), 1)
        action = actions[0]
        raw = E.load_reviews(SAMPLE)
        expected = C.tagging_provenance(
            raw[raw["location"] == action["location"]], SAMPLE, {}, self.version)
        self.assertEqual(action["baseline_provenance"], expected)
        self.assertEqual(action["baseline_source"], D.source_cohort(
            raw.to_dict("records"), SAMPLE_ID, action["location"], action["alert_end_date"]))
        self.assertTrue(any("Tagging provenance unchanged" in item.value
                            for item in app.caption))
        self.assertTrue(any("Source cohort unchanged" in item.value for item in app.caption))

    def test_action_tracker_wires_private_location_decision_breakdown(self):
        import action_decisions_ui as UI
        raw = E.load_reviews(SAMPLE)
        session = manager_session(self, self.root, {SAMPLE_ID: list(raw["location"].unique())})
        location = raw.iloc[0]["location"]
        scoped = raw[raw["location"] == location]
        baseline = C.tagging_provenance(scoped, SAMPLE, {}, self.version)
        action = self.action(baseline)
        action.update(dataset_tag=SAMPLE_ID, location=location)
        key = C.review_key(SAMPLE, scoped.iloc[0])
        corrections = {key: {"rules_version": self.version, "themes_pos": [],
                             "themes_neg": ["price"], "saved_at": "synthetic"}}
        with patch.object(A, "load_actions", return_value=[action]), \
                patch.object(C, "load_corrections", return_value=corrections), \
                patch.object(C, "load_prior_corrections", return_value={}), \
                patch.object(UI, "authorized", return_value=True):
            app = AppTest.from_file(str(SAMPLE.parent.parent / "app.py"),
                                   default_timeout=30)
            sample_app(app, session)
        self.assertFalse(app.exception)
        details = [frame.value for frame in app.dataframe
                   if "Decision reference" in frame.value.columns]
        self.assertEqual(len(details), 1)
        self.assertEqual(details[0].iloc[0]["Decision reference"], key)
        self.assertEqual(details[0].iloc[0]["Change"], "Added")
        self.assertTrue(any("1 added, 0 changed, 0 removed" in text.value
                            for text in app.markdown))


class SourceComparabilityTests(unittest.TestCase):
    """Exercise replacement CSVs, including generated IDs, through the real loader."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.content = (
            b"location,date,rating,text\n"
            b"Demo Cafe,2026-01-01,1,Service was slow.\n"
            b"Demo Cafe,2026-01-02,2,Long wait.\n"
            b"Other Cafe,2026-01-02,5,Quick service.\n"
        )
        sample = self.root / "sample.csv"
        sample.write_bytes(self.content)
        self.store = DatasetStore(self.root / "uploads", sample)
        self.dataset = self.store.save_snapshot("synthetic.csv", self.content)
        self.raw = E.load_reviews(self.dataset["path"])
        self.provenance = C.tagging_provenance(
            self.raw[self.raw.location == "Demo Cafe"],
            self.dataset["correction_path"], {}, E.LOCAL_ANALYZER_VERSION)
        self.action = A.create_action(
            self.dataset["dataset_id"],
            {"location": "Demo Cafe", "theme": "Service speed",
             "recent_share": 100, "recent_mentions": 2},
            "service_speed", "Check handoffs.", "Manager",
            date(2026, 1, 2), date(2026, 1, 20), date(2026, 1, 2),
            tagging_provenance=self.provenance, source_reviews=self.raw.to_dict("records"))
        self.action["status"] = "In progress"
        self.log = str(self.root / "actions.json")
        A.save_actions(self.log, [self.action])
        self.saved_bytes = Path(self.log).read_bytes()

    def compare_csv(self, content):
        updated = self.store.save_snapshot("renamed.csv", content, self.dataset["dataset_id"])
        restarted = DatasetStore(self.root / "uploads", self.root / "sample.csv")
        raw = E.load_reviews(restarted.get(updated["dataset_id"])["path"])
        tagged = E.analyze_offline(raw).to_dict("records")
        provenance = C.tagging_provenance(
            raw[raw.location == "Demo Cafe"], updated["correction_path"], {},
            E.LOCAL_ANALYZER_VERSION)
        result = A.follow_up(
            A.load_actions(self.log)[0], tagged, current_provenance=provenance,
            current_source_reviews=raw.to_dict("records"),
            current_dataset_tag=updated["dataset_id"])
        self.assertEqual(Path(self.log).read_bytes(), self.saved_bytes)
        self.assertEqual(Path(self.dataset["path"]).read_bytes(), self.content)
        return result, raw

    def test_append_only_and_reordered_csv_remain_comparable(self):
        appended = self.content + b"".join(
            f"Demo Cafe,2026-01-{day:02},5,Quick service.\n".encode()
            for day in range(3, 8))
        for content in (self.content, appended,
                        b"\n".join([appended.splitlines()[0]]
                                   + list(reversed(appended.splitlines()[1:]))) + b"\n"):
            with self.subTest(content=content):
                result, _ = self.compare_csv(content)
                self.assertEqual(result["source_status"], "unchanged")
                self.assertEqual(result["comparability_status"], "unchanged")
        self.assertTrue(result["ready"])
        self.assertEqual(result["review_count"], 5)

    def test_edits_removals_and_backfills_warn_without_decisions(self):
        variants = [
            self.content.replace(b"Service was slow.", b"Quick service."),
            self.content.replace(b"2026-01-01,1", b"2026-01-01,5"),
            self.content.replace(b"2026-01-01", b"2026-01-03"),
            self.content.replace(b"Demo Cafe,2026-01-01", b"Other Cafe,2026-01-01"),
            self.content.replace(b"Demo Cafe,2026-01-01,1,Service was slow.\n", b""),
            self.content + b"Demo Cafe,2026-01-01,5,Friendly staff.\n",
            self.content + b"Demo Cafe,2026-01-01,1,Service was slow.\n",
        ]
        for content in variants:
            with self.subTest(content=content):
                result, _ = self.compare_csv(content)
                self.assertEqual(result["provenance_status"], "unchanged")
                self.assertEqual(result["source_status"], "changed")
                self.assertEqual(result["comparability_status"], "changed")
                self.assertIn("saved baseline is unchanged", result["source_message"])
                self.assertFalse(result["ready"])
        # Restoring identical analysis inputs restores comparability.
        self.assertEqual(self.compare_csv(self.content)[0]["source_status"], "unchanged")

    def test_other_locations_and_later_review_edits_are_outside_cohort(self):
        content = self.content.replace(b"Other Cafe,2026-01-02,5,Quick service.",
                                       b"Other Cafe,2026-01-02,1,Long wait.")
        content += b"Demo Cafe,2026-01-10,1,Long wait.\n"
        self.assertEqual(self.compare_csv(content)[0]["source_status"], "unchanged")

    def test_source_warning_is_present_for_ready_and_planned_actions(self):
        content = self.content.replace(b"Long wait.", b"Quick service.")
        content += b"".join(f"Demo Cafe,2026-01-{day:02},5,Quick service.\n".encode()
                            for day in range(3, 8))
        result, raw = self.compare_csv(content)
        self.assertTrue(result["ready"])
        self.assertEqual(result["source_status"], "changed")
        planned = dict(self.action, status="Planned")
        result = A.follow_up(planned, [], current_source_reviews=raw.to_dict("records"))
        self.assertEqual(result["reason"], "not_started")
        self.assertEqual(result["source_status"], "changed")

    def test_duplicate_counts_and_unknown_history_are_conservative(self):
        rows = self.raw.to_dict("records")
        duplicate = rows + [rows[0]]
        action = copy.deepcopy(self.action)
        action["baseline_source"] = D.source_cohort(
            duplicate, action["dataset_tag"], "Demo Cafe", action["alert_end_date"])
        self.assertEqual(A.comparison_source(action, rows)["source_status"], "changed")
        for baseline in (None, {}, {"version": 999}):
            older = copy.deepcopy(self.action)
            older["baseline_source"] = baseline
            original = copy.deepcopy(older)
            self.assertEqual(A.comparison_source(older, rows)["source_status"], "unknown")
            edited = A.update_action(older, "New step", "Manager", "Done",
                                    date(2026, 1, 2), date(2026, 1, 20))
            self.assertEqual(edited["baseline_source"], baseline)
            self.assertEqual(older, original)
        self.assertEqual(A.comparison_source(self.action, None)["source_status"], "unknown")
        self.assertEqual(A.comparison_source(
            self.action, rows, "another-dataset")["source_status"], "unknown")

    def test_weekly_summary_reports_source_changes(self):
        _, changed = self.compare_csv(self.content.replace(b"Long wait.", b"Quick service."))
        text = "\n".join(A.weekly_action_summary(
            [self.action], self.action["dataset_tag"], ["Demo Cafe"],
            E.analyze_offline(changed).to_dict("records"),
            provenance_by_location={"Demo Cafe": self.provenance},
            source_reviews=changed.to_dict("records")))
        self.assertIn("Tagging provenance unchanged", text)
        self.assertIn("Source data changed", text)


class ReviewActionFlowTests(unittest.TestCase):
    def test_upload_controls_keep_new_uploads_and_explicit_updates_separate(self):
        content = (
            b"location,date,rating,text\n"
            b"Demo Cafe,2026-01-01,1,Service was slow.\n"
            b"Demo Cafe,2026-01-02,5,Quick service.\n"
        )
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sample = root / "sample.csv"
            sample.write_bytes(content)
            store = DatasetStore(root / "uploads", sample)
            first = store.save_snapshot("sample.csv", content)
            session = manager_session(self, folder, {first["dataset_id"]: ["Demo Cafe"]})
            upload = SimpleNamespace(name="sample.csv", file_id="first",
                                     getvalue=lambda: content)
            analyze = E.analyze_offline
            # Keep this UI check focused on upload controls, not the unrelated
            # manager-correction selectbox's AppTest formatter state.
            with patch.object(D, "DatasetStore", return_value=store), patch(
                "streamlit.delta_generator.DeltaGenerator.file_uploader",
                return_value=upload,
            ) as uploader, patch.object(A, "load_actions", return_value=[]), patch.object(
                E, "analyze_offline",
                side_effect=lambda raw: analyze(raw).assign(engine="upload_ui_fixture"),
            ):
                app = AppTest.from_file(str(SAMPLE.parent.parent / "app.py"),
                                       default_timeout=30)
                app.session_state["_manager_report_grant"] = session
                app.run()

                def radio(label):
                    return next(item for item in app.sidebar.radio if item.label == label)

                def save():
                    next(item for item in app.sidebar.button
                         if item.label == "Save CSV").click().run()
                    self.assertEqual(list(app.exception), [])

                radio("Data").set_value("Upload my reviews (CSV)").run()
                self.assertEqual(radio("Upload purpose").options, ["Update an existing dataset"])
                save()
                app.run()
                self.assertEqual(len(store.list_datasets()), 1)

                newer = content + b"Demo Cafe,2026-01-03,5,Quick service.\n"
                uploader.return_value = SimpleNamespace(
                    name="newer.csv", file_id="update", getvalue=lambda: newer
                )
                radio("Upload purpose").set_value("Update an existing dataset").run()
                next(item for item in app.sidebar.selectbox
                     if item.label == "Dataset to update").set_value(first["dataset_id"]).run()
                save()
                updated = store.get(first["dataset_id"])
                self.assertEqual(len(store.list_datasets()), 1)
                self.assertEqual(Path(updated["path"]).read_bytes(), newer)
                self.assertEqual(Path(first["path"]).read_bytes(), content)

                uploader.return_value = SimpleNamespace(
                    name="newer.csv", file_id="bad", getvalue=lambda: b"wrong,columns\n1,2\n"
                )
                app.run()
                self.assertEqual(list(app.exception), [])
                self.assertTrue(any("Couldn't validate that CSV" in item.value
                                    for item in app.error))
                self.assertFalse(any(item.label == "Save CSV" for item in app.sidebar.button))
                self.assertEqual(store.get(first["dataset_id"]), updated)
                self.assertEqual(Path(updated["path"]).read_bytes(), newer)

                radio("Data").set_value("Saved file").run()
                next(item for item in app.sidebar.selectbox
                     if item.label == "Dataset").set_value(first["dataset_id"]).run()
                self.assertEqual(list(app.exception), [])
                self.assertTrue(any(first["dataset_id"] in item.value
                                    for item in app.sidebar.caption))
                self.assertEqual(sample.read_bytes(), content)

    def test_colliding_uploads_and_explicit_updates_use_real_csv_follow_up(self):
        original = (
            "review_id,location,date,rating,text\n"
            "r1,Demo Cafe,2026-01-01,1,Service was slow.\n"
        ).encode()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sample = root / "sample.csv"
            sample.write_bytes(original)
            store = DatasetStore(root / "uploads", sample)
            first = store.save_snapshot("sample.csv", original)
            unrelated = store.save_snapshot("sample.csv", original)
            action = A.create_action(
                first["dataset_id"],
                {"location": "Demo Cafe", "theme": "Service speed",
                 "recent_share": 100, "recent_mentions": 1},
                "service_speed", "Check handoffs.", "Manager",
                date(2026, 1, 1), date(2026, 1, 10), date(2026, 1, 1),
            )
            action["status"] = "In progress"
            log = str(root / "actions.json")
            A.save_actions(log, [action])
            original_log = Path(log).read_bytes()
            appended = original + "".join(
                f"new{i},Demo Cafe,2026-01-0{i + 2},5,Quick service.\n"
                for i in range(5)
            ).encode()
            updated = store.save_snapshot("snapshot.csv", appended, first["dataset_id"])
            # A corrected existing review is also a legitimate replacement.
            corrected = appended.replace(b"Service was slow.", b"Quick service.")
            updated = store.save_snapshot("corrected.csv", corrected, updated["dataset_id"])
            restarted = DatasetStore(root / "uploads", sample)
            saved = A.load_actions(log, restarted.get(first["dataset_id"])["dataset_id"])[0]
            tagged = E.analyze_offline(E.load_reviews(updated["path"]))
            result = A.follow_up(saved, tagged.to_dict("records"))
            self.assertTrue(result["ready"])
            self.assertEqual(result["review_count"], 5)
            self.assertEqual(result["mentions"], 0)
            self.assertEqual(result["baseline_share"], 100)
            self.assertEqual(A.load_actions(log, unrelated["dataset_id"]), [])
            self.assertEqual(A.load_actions(log, SAMPLE_ID), [])
            self.assertEqual(Path(log).read_bytes(), original_log)
            self.assertEqual(Path(first["path"]).read_bytes(), original)

    def test_sample_loads_without_changing_its_columns_or_source_file(self):
        original = SAMPLE.read_bytes()
        columns = next(csv.reader(io.StringIO(original.decode("utf-8"))))
        loaded = E.load_reviews(SAMPLE)

        self.assertEqual(list(loaded.columns), columns)
        self.assertEqual(len(loaded), 930)
        self.assertEqual(set(loaded["source"]), {"synthetic"})
        self.assertEqual(SAMPLE.read_bytes(), original)

    def test_alert_action_update_and_follow_up_stay_with_the_dataset(self):
        reviews = E.load_reviews(SAMPLE)
        tagged = E.analyze_offline(reviews)
        alerts = E.early_warnings(tagged)
        alert = alerts[alerts["theme"] == "Service speed"].iloc[0].to_dict()
        start = reviews["date"].max().date()
        action = A.create_action(
            "sample", alert, "service_speed", "Check service handoffs.",
            "", start, start + timedelta(days=7), start,
        )
        self.assertEqual(A.follow_up(action, [])["reason"], "not_started")
        updated = A.update_action(
            action, "Review the handoff checklist.", "Manager", "In progress",
            start, start + timedelta(days=10),
        )
        other_action = A.create_action(
            "another-file", alert, "service_speed", "Check service handoffs.",
            "", start, start + timedelta(days=7), start,
        )

        with tempfile.TemporaryDirectory() as folder:
            log = str(Path(folder) / "actions.json")
            A.save_actions(log, [action, other_action])
            all_actions = A.load_actions(log)
            A.save_actions(log, [
                updated if row["action_id"] == action["action_id"] else row
                for row in all_actions
            ], expected_actions=all_actions)
            saved = A.load_actions(log, "sample")[0]
            self.assertEqual(saved, updated)
            self.assertEqual(A.load_actions(log, "another-file"), [other_action])
            self.assertEqual(saved["baseline_share"], action["baseline_share"])
            self.assertEqual(saved["alert_end_date"], action["alert_end_date"])
            self.assertEqual(saved["status"], "In progress")
            self.assertEqual(action["status"], "Planned")

        with SAMPLE.open(newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            columns = reader.fieldnames
            rows = list(reader)
        for i in range(5):
            rows.append({
                "review_id": f"synthetic-follow-up-{i}",
                "location": saved["location"],
                "date": (start + timedelta(days=i + 1)).isoformat(),
                "rating": 1 if i == 0 else 5,
                "reviewer": "Guest",
                "text": "Service was slow." if i == 0 else "Quick service.",
                "source": "synthetic",
            })

        def check(rows_to_load):
            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows_to_load)
            buffer.seek(0)
            newer = E.analyze_offline(E.load_reviews(buffer))
            return A.follow_up(saved, newer.to_dict("records"))

        waiting = check(rows[:-1])
        self.assertFalse(waiting["ready"])
        self.assertEqual(waiting["review_count"], 4)
        ready = check(rows)
        self.assertTrue(ready["ready"])
        self.assertEqual(ready["review_count"], 5)
        self.assertEqual(ready["mentions"], 1)
        self.assertEqual(ready["share"], 20.0)
        self.assertEqual(ready["direction"], "lower")
        self.assertEqual(ready["baseline_share"], saved["baseline_share"])


if __name__ == "__main__":
    unittest.main()
