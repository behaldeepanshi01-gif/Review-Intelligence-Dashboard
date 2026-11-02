"""Legacy correction uses exclusive associations, never moves action records."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import date
from pathlib import Path
import sqlite3
import tempfile
from threading import Barrier
import unittest

from streamlit.testing.v1 import AppTest

import action_tracker as A
from dataset_store import DatasetStore


class HistoryCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sample = self.root / "sample.csv"
        self.sample.write_text("synthetic")
        self.store = DatasetStore(self.root / "uploads", self.sample)
        self.source = self.store.save_snapshot("same.csv", b"source")
        self.target = self.store.save_snapshot("same.csv", b"target")
        self.third = self.store.save_snapshot("third.csv", b"third")
        self.actions = [
            {"action_id": "old", "dataset_tag": "old.csv", "location": "Demo",
             "theme": "Service", "status": "Done", "baseline_share": 27.5,
             "baseline_provenance": {"rules_version": "historical"},
             "owner": "Manager", "start_date": "2026-01-01",
             "due_date": "2026-01-08", "unknown_legacy_field": ["preserve"]},
            {"action_id": "source-native", "dataset_tag": self.source["dataset_id"]},
            {"action_id": "target-native", "dataset_tag": self.target["dataset_id"]},
            {"action_id": "other-old", "dataset_tag": "other.csv"},
        ]
        self.log = str(self.root / "actions.json")
        A.save_actions(self.log, self.actions)
        self.original_bytes = Path(self.log).read_bytes()
        self.source = self.store.claim_legacy_history(
            self.source["dataset_id"], "old.csv", self.actions,
        )

    def correct(self, target=None, source=None):
        source = source or self.source
        self.store.correct_legacy_history(
            source["dataset_id"], "old.csv",
            expected_source_revision=source["history_revision"],
            target_id=target["dataset_id"] if target else None,
            expected_target_revision=target["history_revision"] if target else None,
        )

    def visible(self, dataset):
        current = self.store.get(dataset["dataset_id"])
        return {row["action_id"] for row in A.load_actions(
            self.log, current["dataset_id"], legacy_tag=current["legacy_tag"],
        )}

    def test_transfer_preserves_native_actions_baselines_and_log_bytes_on_restart(self):
        self.correct(self.target)
        self.assertEqual(self.visible(self.source), {"source-native"})
        self.assertEqual(self.visible(self.target), {"old", "target-native"})
        self.assertEqual(Path(self.log).read_bytes(), self.original_bytes)
        self.store = DatasetStore(self.root / "uploads", self.sample)
        self.assertEqual(self.visible(self.target), {"old", "target-native"})
        self.assertNotIn("old.csv", self.store.unclaimed_legacy_tags(self.actions))

    def test_unlink_and_recover_preserves_every_record(self):
        self.correct()
        self.assertEqual(self.visible(self.source), {"source-native"})
        self.assertIn("old.csv", self.store.unclaimed_legacy_tags(self.actions))
        self.store.claim_legacy_history(self.target["dataset_id"], "old.csv", self.actions)
        self.assertEqual(self.visible(self.target), {"old", "target-native"})
        self.assertEqual(Path(self.log).read_bytes(), self.original_bytes)
        with self.assertRaises(ValueError):
            self.store.claim_legacy_history(self.third["dataset_id"], "old.csv", self.actions)

    def test_action_created_after_link_stays_with_original_dataset(self):
        action = A.create_action(
            self.source["dataset_id"],
            {"location": "Demo", "theme": "Price", "recent_share": 40, "recent_mentions": 8},
            "price", "Check menu value", "Manager", date(2026, 1, 2),
            date(2026, 1, 9), date(2026, 1, 1), today=date(2026, 1, 2),
            tagging_provenance={"rules_version": "current"},
        )
        A.append_action(self.log, action, legacy_tag="old.csv")
        before_transfer = Path(self.log).read_bytes()
        self.correct(self.target)
        self.assertIn(action["action_id"], self.visible(self.source))
        self.assertNotIn(action["action_id"], self.visible(self.target))
        self.assertEqual(Path(self.log).read_bytes(), before_transfer)
        self.assertIn(action, A.load_actions(self.log, self.source["dataset_id"]))

    def test_invalid_destination_does_not_detach_source(self):
        occupied = self.store.claim_legacy_history(
            self.target["dataset_id"], "other.csv", self.actions,
        )
        for target in (occupied, self.source, dict(self.third, dataset_id="missing"),
                       dict(self.third, history_revision=99)):
            with self.subTest(target=target), self.assertRaises(ValueError):
                self.correct(target)
            self.assertEqual(self.store.get(self.source["dataset_id"]), self.source)
        self.assertEqual(Path(self.log).read_bytes(), self.original_bytes)

    def test_stale_source_rejected_even_after_link_returns_to_original_owner(self):
        self.correct()
        current = self.store.claim_legacy_history(
            self.source["dataset_id"], "old.csv", self.actions,
        )
        with self.assertRaises(ValueError):
            self.correct(self.target)
        self.assertEqual(self.store.get(self.source["dataset_id"]), current)
        with self.assertRaises(ValueError):
            self.store.claim_legacy_history(
                self.target["dataset_id"], self.source["dataset_id"], self.actions,
            )

    def test_stale_target_rejected_even_when_its_link_is_empty_again(self):
        claimed = self.store.claim_legacy_history(
            self.target["dataset_id"], "other.csv", self.actions,
        )
        self.store.correct_legacy_history(
            claimed["dataset_id"], "other.csv",
            expected_source_revision=claimed["history_revision"],
        )
        with self.assertRaises(ValueError):
            self.correct(self.target)
        with self.assertRaises(ValueError):
            self.store.claim_legacy_history(
                self.target["dataset_id"], "other.csv", self.actions,
                expected_revision=self.target["history_revision"],
            )
        self.assertEqual(self.visible(self.source), {"old", "source-native"})

    def run_race(self, operations):
        barrier = Barrier(len(operations))

        def run(operation):
            barrier.wait(timeout=10)
            try:
                operation()
                return "saved"
            except ValueError:
                return "conflict"

        with ThreadPoolExecutor(max_workers=len(operations)) as pool:
            results = list(pool.map(run, operations))
        self.assertCountEqual(results, ["saved", "conflict"])

    def test_competing_transfers_have_only_one_winner(self):
        self.run_race([lambda: self.correct(self.target), lambda: self.correct(self.third)])
        owners = [
            row for row in self.store.list_datasets(include_sample=True)
            if row["legacy_tag"] == "old.csv"
        ]
        self.assertEqual(len(owners), 1)
        self.assertNotEqual(owners[0]["dataset_id"], self.source["dataset_id"])
        self.assertEqual(Path(self.log).read_bytes(), self.original_bytes)

    def test_transfer_and_concurrent_destination_claim_cannot_overwrite_each_other(self):
        self.run_race([
            lambda: self.correct(self.target),
            lambda: self.store.claim_legacy_history(
                self.target["dataset_id"], "other.csv", self.actions),
        ])
        destination = self.store.get(self.target["dataset_id"])
        source = self.store.get(self.source["dataset_id"])
        self.assertIn(destination["legacy_tag"], ("old.csv", "other.csv"))
        self.assertEqual(
            source["legacy_tag"], None if destination["legacy_tag"] == "old.csv" else "old.csv",
        )

    def test_pre_revision_registry_migrates_without_changing_existing_link(self):
        uploads = self.root / "old-uploads"
        uploads.mkdir()
        with closing(sqlite3.connect(uploads / "datasets.sqlite")) as db, db:
            db.execute(
                "CREATE TABLE datasets (dataset_id TEXT PRIMARY KEY, label TEXT NOT NULL, "
                "path TEXT NOT NULL UNIQUE, legacy_tag TEXT UNIQUE, correction_path TEXT)"
            )
            db.execute(
                "INSERT INTO datasets VALUES ('upload:old', 'Old', ?, 'old.csv', ?)",
                (str(self.root / "old.csv"), str(self.root / "original.csv")),
            )
        migrated = DatasetStore(uploads, self.sample)
        old = migrated.get("upload:old")
        self.assertEqual(old["legacy_tag"], "old.csv")
        self.assertEqual(old["history_revision"], 0)
        self.assertEqual(old["correction_path"], str(self.root / "original.csv"))
        migrated.correct_legacy_history(
            "upload:old", "old.csv", expected_source_revision=0,
        )
        self.assertIsNone(migrated.get("upload:old")["legacy_tag"])

    def ui(self):
        app = AppTest.from_string("""
import streamlit as st
import action_tracker as A
from legacy_history_ui import show_history_controls
store = st.session_state["store"]
show_history_controls(store, store.get(st.session_state["dataset_id"]),
                      A.load_actions(st.session_state["log"]))
""")
        app.session_state["store"] = self.store
        app.session_state["dataset_id"] = self.source["dataset_id"]
        app.session_state["log"] = self.log
        return app.run()

    @staticmethod
    def button(app, label):
        return next(item for item in app.button if item.label == label)

    def test_ui_confirmation_cancel_and_reassign(self):
        app = self.ui()
        self.assertFalse(app.exception)
        self.assertTrue(self.button(app, "Confirm history correction").disabled)
        self.assertTrue(any(self.source["dataset_id"] in item.value for item in app.markdown))
        self.assertEqual(len(app.json), 1)
        app.checkbox[0].check().run()
        self.button(app, "Cancel history correction").click().run()
        self.assertFalse(app.checkbox[0].value)
        self.assertEqual(self.store.get(self.source["dataset_id"]), self.source)
        app.radio[0].set_value("Reassign to another dataset").run()
        app.selectbox[0].set_value(self.target["dataset_id"]).run()
        app.checkbox[0].check().run()
        self.button(app, "Confirm history correction").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any("reassigned" in item.value for item in app.success))
        self.assertEqual(self.visible(self.source), {"source-native"})
        self.assertEqual(self.visible(self.target), {"old", "target-native"})
        self.assertEqual(Path(self.log).read_bytes(), self.original_bytes)

    def test_ui_unlink_and_explicit_recovery(self):
        app = self.ui()
        app.checkbox[0].check().run()
        self.button(app, "Confirm history correction").click().run()
        self.assertFalse(app.exception)
        app.selectbox[0].set_value("old.csv").run()
        self.assertTrue(self.button(app, "Link older history").disabled)
        app.checkbox[0].check().run()
        self.button(app, "Link older history").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(self.visible(self.source), {"old", "source-native"})
        self.assertEqual(Path(self.log).read_bytes(), self.original_bytes)

    def test_ui_target_change_clears_confirmation(self):
        app = self.ui()
        app.radio[0].set_value("Reassign to another dataset").run()
        app.selectbox[0].set_value(self.target["dataset_id"]).run()
        app.checkbox[0].check().run()
        app.selectbox[0].set_value(self.third["dataset_id"]).run()
        self.assertFalse(app.checkbox[0].value)
        self.assertTrue(self.button(app, "Confirm history correction").disabled)


if __name__ == "__main__":
    unittest.main()
