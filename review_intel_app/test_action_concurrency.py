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

from streamlit.testing.v1 import AppTest

import action_tracker as A
import engine as E
from dataset_store import SAMPLE_ID


DAY = date(2026, 1, 1)


def plan(theme="Service speed", dataset=SAMPLE_ID):
    return A.create_action(
        dataset, {"location": "Demo Cafe", "theme": theme,
                  "recent_share": 60, "recent_mentions": 6},
        "service_speed", "Check handoffs.", "Manager", DAY, DAY, DAY,
        today=DAY, tagging_provenance={
            "rules_version": "synthetic", "decisions_fingerprint": "synthetic"},
    )


def worker(path, barrier, operation, action, text):
    barrier.wait(timeout=10)
    try:
        if operation == "create":
            A.append_action(path, action)
        else:
            A.edit_saved_action(
                path, action, text, text, "In progress", DAY, DAY)
        return "saved"
    except A.ActionConflictError:
        return "conflict"


class ConcurrentActionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / "actions.json")

    def overlap(self, jobs, processes=False):
        if processes:
            context = multiprocessing.get_context("spawn")
            with context.Manager() as manager:
                barrier = manager.Barrier(len(jobs))
                with ProcessPoolExecutor(
                    len(jobs), mp_context=context
                ) as executor:
                    futures = [executor.submit(worker, self.path, barrier, *job)
                               for job in jobs]
                    return [future.result(timeout=20) for future in futures]
        barrier = threading.Barrier(len(jobs))
        with ThreadPoolExecutor(len(jobs)) as executor:
            futures = [executor.submit(worker, self.path, barrier, *job) for job in jobs]
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
        self.assertIn(expected, saved)

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
                A.edit_saved_action(self.path, original, "Edit", "", "Done", DAY, DAY)
            self.assertEqual(A.load_actions(self.path), actions)

    def test_open_form_rejects_other_manager_edit_and_can_reload(self):
        # A real Streamlit form reruns the script before handling its submit.
        # It must compare against the open-time snapshot, not that fresh load.
        sample = E.load_reviews(Path(__file__).parent / "data" / "sample_reviews.csv")
        original = plan()
        original["location"] = sample.iloc[0]["location"]
        A.save_actions(self.path, [original])
        source = (Path(__file__).parent / "app.py").read_text()
        source = source.replace(
            'ACTION_LOG = os.path.join(BASE_DIR, "data", "action_log.json")',
            f"ACTION_LOG = {self.path!r}")
        # from_string has no app.py __file__ in the original directory.
        source = source.replace(
            "BASE_DIR = os.path.dirname(os.path.abspath(__file__))",
            f"BASE_DIR = {str(Path(__file__).parent.resolve())!r}")
        app = AppTest.from_string(source, default_timeout=30).run()
        self.assertEqual(list(app.exception), [])
        text = next(item for item in app.text_area
                    if item.key.startswith("update_text_"))
        text.set_value("Stale manager draft")
        other = A.edit_saved_action(
            self.path, original, "Other manager saved", "Other", "In progress", DAY, DAY)
        next(b for b in app.button if b.label == "Save updates").click().run()
        self.assertEqual(list(app.exception), [])
        self.assertTrue(any("Your changes were not saved" in e.value for e in app.error))
        self.assertEqual(A.load_actions(self.path), [other])
        next(b for b in app.button if b.label == "Reload latest action").click().run()
        text = next(item for item in app.text_area
                    if item.key.startswith("update_text_"))
        self.assertEqual(text.value, "Other manager saved")
        text.set_value("Reviewed latest and saved")
        next(b for b in app.button if b.label == "Save updates").click().run()
        self.assertEqual(list(app.exception), [])
        saved = A.load_actions(self.path)[0]
        self.assertEqual(saved["action_text"], "Reviewed latest and saved")
        self.assertEqual(saved["baseline_provenance"], original["baseline_provenance"])


if __name__ == "__main__":
    unittest.main()
