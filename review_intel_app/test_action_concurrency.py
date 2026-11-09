"""Synthetic, temporary logs only: exercise real overlapping manager saves."""

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from copy import deepcopy
from datetime import date
import json
import multiprocessing
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import streamlit as st
from streamlit.testing.v1 import AppTest

import action_tracker as A
import engine as E
import manager_identity as identity
from dataset_store import SAMPLE_ID
from calendar_test_support import manager_session, sample_app


DAY = date(2026, 1, 1)


def plan(theme="Service speed", dataset=SAMPLE_ID):
    return A.create_action(
        dataset, {"location": "Demo Cafe", "theme": theme,
                  "recent_share": 60, "recent_mentions": 6},
        "service_speed", "Check handoffs.", "Manager", DAY, DAY, DAY,
        today=DAY, tagging_provenance={
            "rules_version": "synthetic", "decisions_fingerprint": "synthetic"},
    )


def worker(path, barrier, session, account_path, operation, action, text):
    # Spawned processes share the parent's temporary identity store.
    identity.DB_PATH = Path(account_path)
    barrier.wait(timeout=10)
    try:
        if operation == "create":
            A.append_action(path, action)
        else:
            A.edit_saved_action(
                path, action, text, text, "In progress", DAY, DAY, session=session)
        return "saved"
    except A.ActionConflictError:
        return "conflict"


class ConcurrentActionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / "actions.json")
        self.session = manager_session(self, self.temp.name, {SAMPLE_ID: ["Demo Cafe"]})

    def overlap(self, jobs, processes=False):
        if processes:
            context = multiprocessing.get_context("spawn")
            with context.Manager() as manager:
                barrier = manager.Barrier(len(jobs))
                with ProcessPoolExecutor(
                    len(jobs), mp_context=context
                ) as executor:
                    futures = [executor.submit(worker, self.path, barrier,
                                               self.session, str(identity.DB_PATH), *job)
                               for job in jobs]
                    return [future.result(timeout=20) for future in futures]
        barrier = threading.Barrier(len(jobs))
        with ThreadPoolExecutor(len(jobs)) as executor:
            futures = [executor.submit(worker, self.path, barrier,
                                       self.session, str(identity.DB_PATH), *job) for job in jobs]
            return [future.result(timeout=20) for future in futures]

    def test_overlapping_creates_preserve_all_datasets_threads_and_processes(self):
        for processes in (False, True):
            with self.subTest(processes=processes):
                actions = [plan(dataset=f"synthetic-{processes}-{i}") for i in range(8)]
                self.assertEqual(
                    self.overlap([("create", a, "") for a in actions], processes),
                    ["saved"] * 8)
                saved = A.load_actions(self.path)
                for action in actions:
                    self.assertIn(action, saved)
        self.assertEqual(len(A.load_actions(self.path)), 16)

    def test_same_warning_has_only_one_active_plan(self):
        self.assertCountEqual(
            self.overlap([("create", plan(), ""), ("create", plan(), "")], True),
            ["saved", "conflict"])
        self.assertEqual(len(A.load_actions(self.path)), 1)

    def test_overlapping_create_and_edit_preserve_legacy_and_baselines(self):
        original = plan()
        legacy = {"action_id": "legacy", "dataset_tag": "old.csv",
                  "baseline_share": 12, "unknown_historical_field": {"kept": True}}
        A.save_actions(self.path, [original, legacy])
        new = plan("Cleanliness")
        self.assertEqual(self.overlap([
            ("edit", original, "Updated handoff."),
            ("create", new, ""),
        ], True), ["saved", "saved"])
        saved = A.load_actions(self.path)
        self.assertIn(new, saved)
        self.assertIn(legacy, saved)
        expected = A.update_action(
            original, "Updated handoff.", "Updated handoff.", "In progress", DAY, DAY)
        edited = next(a for a in saved if a["action_id"] == original["action_id"])
        self.assertEqual({k: v for k, v in edited.items() if k != "edit_history"}, expected)
        self.assertEqual(len(edited["edit_history"]), 1)

    def test_overlapping_edits_to_distinct_actions_both_survive(self):
        first, second = plan(), plan("Cleanliness")
        A.save_actions(self.path, [first, second])
        self.assertEqual(self.overlap([
            ("edit", first, "First edit"), ("edit", second, "Second edit"),
        ], True), ["saved", "saved"])
        self.assertEqual([a["action_text"] for a in A.load_actions(self.path)],
                         ["First edit", "Second edit"])

    def test_overlapping_same_action_edits_reject_stale_snapshot(self):
        original = plan()
        A.save_actions(self.path, [original])
        self.assertCountEqual(self.overlap([
            ("edit", deepcopy(original), "First edit"),
            ("edit", deepcopy(original), "Second edit"),
        ], True), ["saved", "conflict"])
        saved = A.load_actions(self.path)[0]
        self.assertIn(saved["action_text"], ["First edit", "Second edit"])
        self.assertEqual(len(saved["edit_history"]), 1)
        self.assertEqual(saved["baseline_provenance"], original["baseline_provenance"])

    def test_bulk_save_cannot_replace_a_stale_log(self):
        first, second = plan(), plan("Cleanliness")
        A.save_actions(self.path, [first])
        snapshot = A.load_actions(self.path)
        A.append_action(self.path, second)
        for expected in (None, snapshot):
            with self.assertRaises(A.ActionConflictError):
                A.save_actions(self.path, [], expected_actions=expected)
        self.assertEqual(A.load_actions(self.path), [first, second])

    def test_checked_bulk_save_preserves_compatibility(self):
        original = plan()
        A.save_actions(self.path, [original])
        changed = dict(original, owner="New owner")
        A.save_actions(self.path, [changed], expected_actions=[original])
        self.assertEqual(A.load_actions(self.path), [changed])

    def test_legacy_active_plan_blocks_duplicate_after_explicit_link(self):
        original = plan(dataset="old.csv")
        A.save_actions(self.path, [original])
        with self.assertRaises(A.ActionConflictError):
            A.append_action(self.path, plan(), legacy_tag="old.csv")
        self.assertEqual(A.load_actions(self.path), [original])

    def test_failed_write_and_corrupt_log_are_not_overwritten(self):
        original = plan()
        A.save_actions(self.path, [original])
        before = Path(self.path).read_bytes()
        with patch.object(A.os, "replace", side_effect=OSError("Synthetic failure")):
            with self.assertRaises(OSError):
                A.append_action(self.path, plan("Cleanliness"))
        self.assertEqual(Path(self.path).read_bytes(), before)
        self.assertEqual(list(Path(self.temp.name).glob(".actions-*.tmp")), [])
        Path(self.path).write_text("{broken", encoding="utf-8")
        with self.assertRaises(ValueError):
            A.append_action(self.path, plan("Cleanliness"))
        self.assertEqual(Path(self.path).read_text(), "{broken")

    def test_missing_and_ambiguous_actions_cannot_be_edited(self):
        original = plan()
        for actions in ([], [original, original]):
            Path(self.path).write_text(json.dumps(actions), encoding="utf-8")
            with self.assertRaises(A.ActionConflictError):
                A.edit_saved_action(self.path, original, "Edit", "", "Done", DAY, DAY,
                                    session=self.session)
            self.assertEqual(A.load_actions(self.path), actions)

    def open_app(self, history=None):
        sample = E.load_reviews(Path(__file__).parent / "data" / "sample_reviews.csv")
        original = plan()
        original["location"] = sample.iloc[0]["location"]
        if history is not None:
            original["edit_history"] = history
        A.save_actions(self.path, [original])
        source = (Path(__file__).parent / "app.py").read_text()
        source = source.replace(
            'ACTION_LOG = os.path.join(BASE_DIR, "data", "action_log.json")',
            f"ACTION_LOG = {self.path!r}")
        # from_string has no app.py __file__ in the original directory.
        source = source.replace(
            "BASE_DIR = os.path.dirname(os.path.abspath(__file__))",
            f"BASE_DIR = {str(Path(__file__).parent.resolve())!r}")
        session = manager_session(self, self.temp.name,
                                  {SAMPLE_ID: list(sample["location"].unique())})
        self.session = session
        self.app_source = source
        app = sample_app(AppTest.from_string(source, default_timeout=30), session)
        self.assertEqual(list(app.exception), [])
        return original, app

    def comparison(self, app):
        return next(table.value for table in app.dataframe
                    if "Your unsaved draft" in table.value.columns)

    def action_widget(self, app, action, prefix):
        widgets = (list(app.text_area) + list(app.text_input)
                   + list(app.selectbox) + list(app.date_input))
        return next(w for w in widgets
                    if w.key and w.key.startswith(f"{prefix}{action['action_id']}_"))

    def action_button(self, app, action, label):
        return next(b for b in app.button
                    if b.label == label and b.key
                    and b.key.startswith(f"update_action_{action['action_id']}_"))

    def action_table(self, app, action, column):
        editor = next(e for e in app.expander
                      if e.label.startswith(
                          f"Edit {action['location']}: {action['theme']} ·"))
        return next(t.value for t in editor.dataframe if column in t.value.columns)

    def set_action_fields(self, app, action, values):
        for field, prefix in [
            ("action_text", "update_text_"), ("owner", "update_owner_"),
            ("status", "update_status_"), ("start_date", "update_start_"),
            ("due_date", "update_due_"),
        ]:
            value = values[field]
            if field in ("start_date", "due_date"):
                value = date.fromisoformat(value)
            self.action_widget(app, action, prefix).set_value(value)

    def test_two_conflicts_keep_reload_and_save_are_action_and_manager_isolated(self):
        # Resolve in both orders: a rerun must not reset an earlier or later
        # editor, nor borrow the other action's snapshot/reference.
        for resolved_index in (0, 1):
            with self.subTest(resolved_first=resolved_index):
                self.check_two_conflicts_isolated(resolved_index)

    def check_two_conflicts_isolated(self, resolved_index):
        # Each subcase gets a new log; no workspace action history is touched.
        self.path = str(Path(self.temp.name) / f"multi-{resolved_index}.json")
        first, app = self.open_app()
        second = plan("Cleanliness")
        second["location"] = first["location"]
        untouched = {
            "action_id": "untouched-legacy", "dataset_tag": "synthetic-old.csv",
            "location": "Synthetic archived cafe", "theme": "Historical theme",
            "baseline_share": 12, "baseline_mentions": 3,
            "unknown_historical_field": {"keep": ["exactly", 42]},
        }
        A.append_action(self.path, second)
        A.append_action(self.path, untouched)
        app.run()
        self.assertFalse(app.exception)
        originals = [deepcopy(first), deepcopy(second)]

        other_id = f"other-manager-{resolved_index}"
        password = "synthetic-other-manager-password"
        identity.set_account(other_id, password, identity.current_account(
            self.session)["grants"])
        other_session = identity.authenticate(other_id, password)
        self.assertIsNotNone(other_session)
        other_app = sample_app(
            AppTest.from_string(self.app_source, default_timeout=30), other_session)
        self.assertFalse(other_app.exception)
        drafts = [
            {"action_text": "Private handoff draft\nDo not share",
             "owner": "", "status": "Done",
             "start_date": "2026-02-02", "due_date": "2026-02-04"},
            {"action_text": "Private cleaning draft\nKeep separate",
             "owner": "Draft cleaning owner", "status": "In progress",
             "start_date": "2026-03-03", "due_date": "2026-03-06"},
        ]
        winners = [
            {"action_text": "Other manager handoff", "owner": "Handoff lead",
             "status": "In progress",
             "start_date": "2026-01-05", "due_date": "2026-01-07"},
            {"action_text": "Other manager cleaning", "owner": "Cleaning lead",
             "status": "Done",
             "start_date": "2026-01-08", "due_date": "2026-01-09"},
        ]
        for action, draft in zip(originals, drafts):
            self.set_action_fields(app, action, draft)

        # Both sessions opened the same versions. The second manager saves via
        # separate AppTest editors while the first has two unsaved drafts.
        expected = [deepcopy(first), deepcopy(second), deepcopy(untouched)]
        for index, action in enumerate(originals):
            self.set_action_fields(other_app, action, winners[index])
            self.action_button(other_app, action, "Save updates").click().run()
            self.assertFalse(other_app.exception)
            saved = A.load_actions(self.path)
            self.assertEqual(saved[index]["edit_history"][-1]["saved_by"], other_id)
            self.assertEqual(
                {field: saved[index][field] for field in A.EDITABLE_FIELDS},
                winners[index])
            for field in action.keys() - set(A.EDITABLE_FIELDS):
                self.assertEqual(saved[index][field], action[field])
            expected[index] = deepcopy(saved[index])
            self.assertEqual(saved, expected)

        before = Path(self.path).read_bytes()
        app.run()
        self.assertFalse(app.exception)

        def assert_conflict(index):
            action = originals[index]
            table = self.action_table(app, action, "Your unsaved draft")
            self.assertEqual(list(table["Your unsaved draft"]),
                             [drafts[index][f] for f in A.EDITABLE_FIELDS])
            self.assertEqual(list(table["Latest saved"]),
                             [winners[index][f] for f in A.EDITABLE_FIELDS])
            self.assertTrue(table["Different"].all())
            self.assertTrue(self.action_button(app, action, "Save updates").disabled)

        assert_conflict(0)
        assert_conflict(1)
        resolved = originals[resolved_index]
        pending_index = 1 - resolved_index
        pending = originals[pending_index]
        self.action_button(app, resolved, "Keep draft for reference").click().run()
        self.assertFalse(app.exception)
        assert_conflict(pending_index)
        kept = self.action_table(app, resolved, "Kept draft").copy(deep=True)
        self.assertEqual(list(kept["Kept draft"]),
                         [drafts[resolved_index][f] for f in A.EDITABLE_FIELDS])
        reference = self.draft_download(app)
        self.assertEqual(reference["context"]["action_id"], resolved["action_id"])
        self.assertEqual(reference["editable_fields"], drafts[resolved_index])
        self.assertEqual(sum("Kept draft" in t.value.columns for t in app.dataframe), 1)
        self.action_button(app, resolved, "Reload latest action").click().run()
        self.assertFalse(app.exception)
        assert_conflict(pending_index)
        self.assertFalse(self.action_button(app, resolved, "Save updates").disabled)
        self.assertEqual(self.action_widget(app, resolved, "update_text_").value,
                         winners[resolved_index]["action_text"])
        self.assertTrue(kept.equals(self.action_table(app, resolved, "Kept draft")))
        self.assertEqual(self.draft_download(app), reference)
        self.assertEqual(Path(self.path).read_bytes(), before)

        # The other signed-in manager, and even a fresh session for the first
        # account, must see neither private reference tables nor download bytes.
        fresh = sample_app(
            AppTest.from_string(self.app_source, default_timeout=30), self.session)
        for isolated_app in (other_app, fresh):
            isolated_app.run()
            self.assert_no_draft_download(isolated_app)
            self.assertFalse(any("Kept draft" in t.value.columns
                                 for t in isolated_app.dataframe))
            self.assertFalse(any(key.startswith("action_draft_reference_")
                                 for key in isolated_app.session_state))
        self.assertEqual(Path(self.path).read_bytes(), before)

        # Reconcile only the reloaded editor. A successful save must leave the
        # second conflict, its full draft, and every other log record unchanged.
        reconciled = dict(winners[resolved_index],
                          action_text="Manually reconciled intended action")
        self.set_action_fields(app, resolved, reconciled)
        self.action_button(app, resolved, "Save updates").click().run()
        self.assertFalse(app.exception)
        assert_conflict(pending_index)
        saved = A.load_actions(self.path)
        edited = saved[resolved_index]
        self.assertEqual({field: edited[field] for field in A.EDITABLE_FIELDS}, reconciled)
        self.assertEqual(edited["edit_history"][:-1],
                         expected[resolved_index]["edit_history"])
        self.assertEqual(edited["edit_history"][-1]["saved_by"], "test-manager")
        self.assertEqual(edited["edit_history"][-1]["changes"], {
            "action_text": {"before": winners[resolved_index]["action_text"],
                            "after": reconciled["action_text"]}})
        for field in resolved.keys() - set(A.EDITABLE_FIELDS):
            self.assertEqual(edited[field], resolved[field])
        expected[resolved_index] = deepcopy(edited)
        self.assertEqual(saved, expected)
        self.assertEqual(self.draft_download(app), reference)

        # Keeping the remaining conflict must create a second, distinct
        # reference, not replace the one already retained.
        before = Path(self.path).read_bytes()
        self.action_button(app, pending, "Keep draft for reference").click().run()
        self.action_button(app, pending, "Reload latest action").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(Path(self.path).read_bytes(), before)
        self.assertEqual(sum("Kept draft" in t.value.columns for t in app.dataframe), 2)
        for index, action in enumerate(originals):
            self.assertEqual(list(self.action_table(app, action, "Kept draft")["Kept draft"]),
                             [drafts[index][f] for f in A.EDITABLE_FIELDS])
            self.assertFalse(self.action_button(app, action, "Save updates").disabled)
        self.assertFalse(any("Your unsaved draft" in t.value.columns for t in app.dataframe))
        for isolated_app in (other_app, fresh):
            isolated_app.run()
            self.assert_no_draft_download(isolated_app)
            self.assertFalse(any("Kept draft" in t.value.columns
                                 for t in isolated_app.dataframe))
            self.assertFalse(any(key.startswith("action_draft_reference_")
                                 for key in isolated_app.session_state))
        self.assertEqual(A.load_actions(self.path), expected)

    def test_history_shows_unknown_legacy_actor_and_verified_unchanged_save(self):
        legacy_entry = {
            "saved_at": "2025-12-01T00:00:00+00:00",
            "changes": {"owner": {"before": "", "after": "Manager"}},
        }
        original, app = self.open_app(history=[legacy_entry])
        history = next(t.value for t in app.dataframe
                       if "Saved at (UTC)" in t.value.columns)
        self.assertEqual(list(history["Saved by"]), ["Unknown"])
        next(b for b in app.button if b.label == "Save updates").click().run()
        self.assertFalse(app.exception)
        history = next(t.value for t in app.dataframe
                       if "Saved at (UTC)" in t.value.columns)
        self.assertEqual(list(history["Saved by"]), ["test-manager", "Unknown"])
        self.assertEqual(history.iloc[0]["Field"], "Saved without field changes")
        saved = A.load_actions(self.path)[0]
        self.assertEqual(saved["edit_history"][0], original["edit_history"][0])
        self.assertEqual(saved["owner"], "Manager")

    def test_open_form_rejects_other_manager_edit_and_can_reload(self):
        # A real Streamlit form reruns the script before handling its submit.
        # It must compare against the open-time snapshot, not that fresh load.
        original, app = self.open_app()
        text = next(item for item in app.text_area
                    if item.key and item.key.startswith("update_text_"))
        text.set_value("Stale manager draft")
        next(item for item in app.text_input
             if item.key and item.key.startswith("update_owner_")).set_value("")
        next(item for item in app.selectbox
             if item.key and item.key.startswith("update_status_")).set_value("Done")
        next(item for item in app.date_input
             if item.key and item.key.startswith("update_start_")).set_value(date(2026, 1, 2))
        next(item for item in app.date_input
             if item.key and item.key.startswith("update_due_")).set_value(date(2026, 1, 3))
        other = A.edit_saved_action(
            self.path, original, "Other manager saved", "Other", "In progress", DAY, DAY,
            session=self.session)
        next(b for b in app.button if b.label == "Save updates").click().run()
        self.assertEqual(list(app.exception), [])
        self.assertTrue(any("Your changes were not saved" in e.value for e in app.error))
        self.assertEqual(A.load_actions(self.path), [other])
        comparison = self.comparison(app)
        self.assertEqual(list(comparison["Field"]), [
            "Manager action", "Owner", "Status", "Action start date", "Due date"])
        self.assertEqual(list(comparison["Your unsaved draft"]), [
            "Stale manager draft", "", "Done", "2026-01-02", "2026-01-03"])
        self.assertEqual(list(comparison["Latest saved"]), [
            "Other manager saved", "Other", "In progress", "2026-01-01", "2026-01-01"])
        self.assertTrue(comparison["Different"].all())
        self.assertTrue(next(b for b in app.button if b.label == "Save updates").disabled)
        self.assertTrue(text.key in [t.key for t in app.text_area])
        next(b for b in app.button if b.label == "Reload latest action").click().run()
        text = next(item for item in app.text_area
                    if item.key and item.key.startswith("update_text_"))
        self.assertEqual(text.value, "Other manager saved")
        text.set_value("Reviewed latest and saved")
        next(b for b in app.button if b.label == "Save updates").click().run()
        self.assertEqual(list(app.exception), [])
        saved = A.load_actions(self.path)[0]
        self.assertEqual(saved["action_text"], "Reviewed latest and saved")
        self.assertEqual(saved["baseline_provenance"], original["baseline_provenance"])
        for field in original.keys() - set(A.EDITABLE_FIELDS):
            self.assertEqual(saved[field], original[field])
        self.assertFalse(any("Kept draft" in table.value.columns for table in app.dataframe))
        self.assertEqual(len(saved["edit_history"]), 2)
        history = next(table for table in app.dataframe
                       if "Saved at (UTC)" in table.value.columns).value
        text_changes = history[history["Field"] == "Manager action"]
        self.assertEqual(list(text_changes["Before"]),
                         ["Other manager saved", "Check handoffs."])
        self.assertEqual(list(text_changes["After"]),
                         ["Reviewed latest and saved", "Other manager saved"])
        self.assertEqual(set(history["Saved by"]), {"test-manager"})

    def test_kept_reference_survives_reload_and_never_overwrites_newer_saves(self):
        original, app = self.open_app()
        next(t for t in app.text_area if t.key and t.key.startswith("update_text_")).set_value(
            "Keep this draft\nFor manual comparison")
        other = A.edit_saved_action(
            self.path, original, "Other saved", "Other", "In progress", DAY, DAY,
            session=self.session)
        next(b for b in app.button if b.label == "Save updates").click().run()
        before = Path(self.path).read_bytes()
        # Keep must submit the form too, including changes made after the
        # initial conflict, not just the draft from the rejected save.
        next(t for t in app.text_area if t.key and t.key.startswith("update_text_")).set_value(
            "Keep this revised draft\nFor manual comparison")
        next(b for b in app.button if b.label == "Keep draft for reference").click().run()
        self.assertFalse(app.exception)
        kept = next(t.value for t in app.dataframe if "Kept draft" in t.value.columns)
        self.assertEqual(kept.iloc[0]["Kept draft"],
                         "Keep this revised draft\nFor manual comparison")
        self.assertEqual(Path(self.path).read_bytes(), before)
        self.assertEqual(self.comparison(app).iloc[0]["Your unsaved draft"],
                         "Keep this revised draft\nFor manual comparison")
        self.assertFalse(self.comparison(app).iloc[-1]["Different"])
        # A further intervening edit must be shown, never overwritten by Keep.
        latest = A.edit_saved_action(
            self.path, other, "Third saved", "", "Done", DAY, DAY,
            session=self.session)
        app.run()
        self.assertEqual(self.comparison(app).iloc[0]["Latest saved"], "Third saved")
        self.assertEqual(A.load_actions(self.path), [latest])
        next(b for b in app.button if b.label == "Reload latest action").click().run()
        self.assertFalse(app.exception)
        text = next(t for t in app.text_area if t.key and t.key.startswith("update_text_"))
        self.assertEqual(text.value, "Third saved")
        self.assertFalse(text.disabled)
        self.assertFalse(any("Your unsaved draft" in t.value.columns for t in app.dataframe))
        self.assertTrue(kept.equals(
            next(t.value for t in app.dataframe if "Kept draft" in t.value.columns)))
        text.set_value("Manually reconciled")
        next(b for b in app.button if b.label == "Save updates").click().run()
        self.assertFalse(app.exception)
        saved = A.load_actions(self.path)[0]
        self.assertEqual(saved["action_text"], "Manually reconciled")
        self.assertEqual(saved["status"], "Done")
        self.assertEqual(saved["owner"], "")
        self.assertEqual(len(saved["edit_history"]), 3)
        self.assertEqual(saved["edit_history"][-1]["changes"], {
            "action_text": {"before": "Third saved", "after": "Manually reconciled"}})
        for field in original.keys() - set(A.EDITABLE_FIELDS):
            self.assertEqual(saved[field], original[field])

    def test_save_time_race_shows_comparison_without_losing_draft(self):
        original, app = self.open_app()
        next(t for t in app.text_area if t.key and t.key.startswith("update_text_")).set_value(
            "Race draft")
        real_edit = A.edit_saved_action

        def concurrent_edit(*args, **kwargs):
            real_edit(self.path, original, "Race winner", "", "Planned", DAY, DAY,
                      session=self.session)
            return real_edit(*args, **kwargs)

        with patch.object(A, "edit_saved_action", side_effect=concurrent_edit):
            next(b for b in app.button if b.label == "Save updates").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(self.comparison(app).iloc[0]["Your unsaved draft"], "Race draft")
        self.assertEqual(self.comparison(app).iloc[0]["Latest saved"], "Race winner")
        saved = A.load_actions(self.path)[0]
        self.assertEqual(saved["action_text"], "Race winner")
        self.assertEqual(len(saved["edit_history"]), 1)

    def draft_download(self, app):
        """Capture the bytes passed to the real Streamlit download widget."""
        with patch("streamlit.download_button", wraps=st.download_button) as downloads:
            app.run()
        self.assertFalse(app.exception)
        calls = [call for call in downloads.call_args_list
                 if call.args[0] == "Download kept draft (unsaved reference)"]
        self.assertEqual(len(calls), 1)
        call = calls[0]
        self.assertEqual(call.kwargs["mime"], "application/json")
        self.assertTrue(call.kwargs["file_name"].startswith("unsaved-action-draft-"))
        self.assertTrue(call.kwargs["file_name"].endswith(".json"))
        self.assertEqual(call.kwargs["on_click"], "ignore")
        self.assertEqual(sum(w.label == call.args[0]
                             for w in app.get("download_button")), 1)
        return json.loads(call.args[1].decode("utf-8"))

    def assert_no_draft_download(self, app):
        self.assertFalse(app.exception)
        self.assertFalse(any(w.label == "Download kept draft (unsaved reference)"
                             for w in app.get("download_button")))

    def test_download_contains_only_kept_unsaved_fields_and_action_context(self):
        original, app = self.open_app()
        self.assert_no_draft_download(app)
        draft = {
            "action_text": "Réviser café handoffs.\nKeep exact punctuation: \"yes\", please!",
            "owner": "", "status": "Done",
            "start_date": "2026-01-02", "due_date": "2026-01-03",
        }
        for prefix, value in [
            ("update_text_", draft["action_text"]), ("update_owner_", ""),
            ("update_status_", "Done"), ("update_start_", date(2026, 1, 2)),
            ("update_due_", date(2026, 1, 3)),
        ]:
            widgets = list(app.text_area) + list(app.text_input) + list(
                app.selectbox) + list(app.date_input)
            next(w for w in widgets if w.key and w.key.startswith(prefix)).set_value(value)
        A.edit_saved_action(
            self.path, original, "Newer saved action", "Other", "In progress", DAY, DAY,
            session=self.session)
        next(b for b in app.button if b.label == "Save updates").click().run()
        self.assert_no_draft_download(app)
        before = Path(self.path).read_bytes()
        next(b for b in app.button if b.label == "Keep draft for reference").click().run()
        payload = self.draft_download(app)
        self.assertEqual(set(payload), {
            "reference_status", "notice", "context", "editable_fields"})
        self.assertIn("UNSAVED", payload["reference_status"])
        self.assertIn("not saved", payload["notice"])
        self.assertIn("not an approved action or an import file", payload["notice"])
        self.assertEqual(payload["context"], {
            "dataset_id": SAMPLE_ID, "action_id": original["action_id"],
            "location": original["location"], "theme": original["theme"],
        })
        self.assertEqual(payload["editable_fields"], draft)
        self.assertEqual(set(payload["editable_fields"]), set(A.EDITABLE_FIELDS))
        self.assertNotIn("baseline_share", json.dumps(payload))
        self.assertNotIn("baseline_provenance", json.dumps(payload))
        self.assertEqual(Path(self.path).read_bytes(), before)
        # Later edits and reloading the latest action must not change the kept file.
        next(t for t in app.text_area
             if t.key and t.key.startswith("update_text_")).set_value("Not kept").run()
        self.assertEqual(self.draft_download(app), payload)
        next(b for b in app.button if b.label == "Reload latest action").click().run()
        self.assertEqual(self.draft_download(app), payload)
        self.assertEqual(next(t.value for t in app.text_area
                              if t.key and t.key.startswith("update_text_")),
                         "Newer saved action")
        self.assertEqual(Path(self.path).read_bytes(), before)

    def test_kept_download_is_scoped_to_visible_action_and_current_session(self):
        original, app = self.open_app()
        next(t for t in app.text_area if t.key and t.key.startswith("update_text_")).set_value(
            "Private kept reference for the first action")
        A.edit_saved_action(
            self.path, original, "Other saved", "", "Planned", DAY, DAY,
            session=self.session)
        next(b for b in app.button if b.label == "Save updates").click().run()
        next(b for b in app.button if b.label == "Keep draft for reference").click().run()
        payload = self.draft_download(app)
        locations = next(w for w in app.multiselect if w.label == "Locations")
        second = plan("Cleanliness")
        second["location"] = next(loc for loc in locations.options
                                  if loc != original["location"])
        A.append_action(self.path, second)
        before = Path(self.path).read_bytes()
        locations.set_value([second["location"]]).run()
        self.assert_no_draft_download(app)
        next(w for w in app.multiselect if w.label == "Locations").set_value(
            [original["location"]]).run()
        self.assertEqual(self.draft_download(app), payload)
        # Even a fresh session for the same signed-in account has no kept reference.
        fresh = sample_app(
            AppTest.from_string(self.app_source, default_timeout=30), self.session)
        self.assert_no_draft_download(fresh)
        self.assertFalse(any("Kept draft" in t.value.columns for t in fresh.dataframe))
        self.assertEqual(Path(self.path).read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
