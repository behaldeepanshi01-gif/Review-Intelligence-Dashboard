"""Legacy correction uses exclusive associations, never moves action records."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path
import sqlite3
import tempfile
from threading import Barrier
import unittest

from streamlit.testing.v1 import AppTest

import action_tracker as A
import manager_identity as identity
from calendar_test_support import manager_session
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
        self.assertEqual(migrated.history_link_events("upload:old"), [])
        migrated.correct_legacy_history(
            "upload:old", "old.csv", expected_source_revision=0,
        )
        self.assertIsNone(migrated.get("upload:old")["legacy_tag"])

    def test_audit_records_claim_transfer_unlink_and_recovery_after_restart(self):
        self.correct(self.target)
        target = self.store.get(self.target["dataset_id"])
        self.correct(source=target)
        self.store.claim_legacy_history(self.source["dataset_id"], "old.csv", self.actions)
        self.store = DatasetStore(self.root / "uploads", self.sample)
        source_events = self.store.history_link_events(self.source["dataset_id"])
        target_events = self.store.history_link_events(self.target["dataset_id"])
        self.assertEqual([e["operation"] for e in source_events], ["claim", "transfer", "claim"])
        self.assertEqual([e["operation"] for e in target_events], ["unlink", "transfer"])
        claim = source_events[-1]
        transfer = target_events[-1]
        unlink = target_events[0]
        self.assertIsNone(claim["source_dataset_id"])
        self.assertEqual(claim["destination_dataset_id"], self.source["dataset_id"])
        self.assertEqual(transfer["source_dataset_id"], self.source["dataset_id"])
        self.assertEqual(transfer["destination_dataset_id"], self.target["dataset_id"])
        self.assertEqual(unlink["source_dataset_id"], self.target["dataset_id"])
        self.assertIsNone(unlink["destination_dataset_id"])
        self.assertEqual(self.store.history_link_events(self.third["dataset_id"]), [])
        for event in source_events + target_events:
            self.assertEqual(event["legacy_tag"], "old.csv")
            self.assertEqual(datetime.fromisoformat(event["occurred_at"]).utcoffset(),
                             timedelta(0))
        self.assertEqual(Path(self.log).read_bytes(), self.original_bytes)

    def test_rejected_and_competing_changes_do_not_add_spurious_events(self):
        before = self.store.history_link_events(self.source["dataset_id"])
        for operation in (
            lambda: self.correct(dict(self.target, history_revision=99)),
            lambda: self.correct(source=dict(self.source, history_revision=99)),
            lambda: self.store.claim_legacy_history(
                self.target["dataset_id"], "old.csv", self.actions),
            lambda: self.store.claim_legacy_history(
                self.source["dataset_id"], "other.csv", self.actions),
        ):
            with self.assertRaises(ValueError):
                operation()
            self.assertEqual(self.store.history_link_events(self.source["dataset_id"]), before)
        self.run_race([lambda: self.correct(self.target), lambda: self.correct(self.third)])
        self.assertEqual(len(self.store.history_link_events(self.source["dataset_id"])), 2)
        with closing(self.store.connect()) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM history_link_events").fetchone()[0], 2)

    def test_audit_insert_failure_rolls_back_association_and_revision(self):
        with closing(self.store.connect()) as db, db:
            db.execute("""
                CREATE TRIGGER fail_audit BEFORE INSERT ON history_link_events
                BEGIN SELECT RAISE(ABORT, 'audit unavailable'); END
            """)
        before = self.store.list_datasets(include_sample=True)
        for operation in (
            lambda: self.correct(),
            lambda: self.correct(self.target),
            lambda: self.store.claim_legacy_history(
                self.target["dataset_id"], "other.csv", self.actions),
        ):
            with self.assertRaisesRegex(sqlite3.IntegrityError, "audit unavailable"):
                operation()
            self.assertEqual(self.store.list_datasets(include_sample=True), before)
            self.assertEqual(len(self.store.history_link_events(self.source["dataset_id"])), 1)
            self.assertEqual(self.store.history_link_events(self.target["dataset_id"]), [])
        self.assertEqual(Path(self.log).read_bytes(), self.original_bytes)

    def test_authenticated_actors_persist_for_all_operations_without_editing_actions(self):
        first = manager_session(self, self.root, {})
        identity.set_account("second-manager", "synthetic-second-password", {})
        second = identity.authenticate("second-manager", "synthetic-second-password")
        self.store.claim_legacy_history(
            self.third["dataset_id"], "other.csv", self.actions, session=first)
        third = self.store.get(self.third["dataset_id"])
        self.store.correct_legacy_history(
            third["dataset_id"], "other.csv",
            expected_source_revision=third["history_revision"],
            target_id=self.target["dataset_id"],
            expected_target_revision=self.target["history_revision"], session=second)
        target = self.store.get(self.target["dataset_id"])
        self.store.correct_legacy_history(
            target["dataset_id"], "other.csv",
            expected_source_revision=target["history_revision"], session=first)
        self.store.claim_legacy_history(
            self.third["dataset_id"], "other.csv", self.actions, session=second)
        restarted = DatasetStore(self.root / "uploads", self.sample)
        events = restarted.history_link_events(third["dataset_id"])
        self.assertEqual(
            [(e["operation"], e["changed_by"]) for e in events],
            [("claim", "second-manager"), ("transfer", "second-manager"),
             ("claim", "test-manager")])
        self.assertEqual(
            [(e["operation"], e["changed_by"])
             for e in restarted.history_link_events(target["dataset_id"])],
            [("unlink", "test-manager"), ("transfer", "second-manager")])
        self.assertIsNone(
            restarted.history_link_events(self.source["dataset_id"])[0]["changed_by"])
        for event in events:
            self.assertEqual(set(event), {
                "event_id", "source_dataset_id", "destination_dataset_id",
                "legacy_tag", "operation", "occurred_at", "changed_by"})
        self.assertEqual(Path(self.log).read_bytes(), self.original_bytes)

    def test_old_event_schema_migrates_without_inventing_authors(self):
        before = self.store.history_link_events(self.source["dataset_id"])[0]
        with closing(self.store.connect()) as db, db:
            db.execute("ALTER TABLE history_link_events DROP COLUMN changed_by")
        migrated = DatasetStore(self.root / "uploads", self.sample)
        self.assertEqual(
            migrated.history_link_events(self.source["dataset_id"]), [before])
        self.assertIsNone(before["changed_by"])
        session = manager_session(self, self.root, {})
        migrated.correct_legacy_history(
            self.source["dataset_id"], "old.csv",
            expected_source_revision=self.source["history_revision"], session=session)
        events = DatasetStore(self.root / "uploads", self.sample).history_link_events(
            self.source["dataset_id"])
        self.assertEqual([e["changed_by"] for e in events], ["test-manager", None])
        self.assertEqual(events[-1], before)

    def test_invalid_expired_and_revoked_sessions_cannot_change_links_or_audit(self):
        session = manager_session(self, self.root, {})
        invalid_sessions = [None, {}, dict(session, expires=0),
                            dict(session, username="not-a-manager"),
                            dict(session, revision="forged")]
        identity.remove_account("test-manager")
        invalid_sessions.append(session)
        for invalid in invalid_sessions:
            for operation in (
                lambda: self.store.claim_legacy_history(
                    self.target["dataset_id"], "other.csv", self.actions, session=invalid),
                lambda: self.store.correct_legacy_history(
                    self.source["dataset_id"], "old.csv",
                    expected_source_revision=self.source["history_revision"],
                    session=invalid),
                lambda: self.store.correct_legacy_history(
                    self.source["dataset_id"], "old.csv",
                    expected_source_revision=self.source["history_revision"],
                    target_id=self.target["dataset_id"],
                    expected_target_revision=self.target["history_revision"],
                    session=invalid),
            ):
                with self.subTest(session=invalid), self.assertRaises(PermissionError):
                    operation()
                self.assertEqual(self.store.get(self.source["dataset_id"]), self.source)
                self.assertEqual(self.store.get(self.target["dataset_id"]), self.target)
                self.assertEqual(
                    len(self.store.history_link_events(self.source["dataset_id"])), 1)
                self.assertEqual(self.store.history_link_events(self.target["dataset_id"]), [])
        self.assertEqual(Path(self.log).read_bytes(), self.original_bytes)

    def ui(self):
        app = AppTest.from_string("""
import streamlit as st
import action_tracker as A
from legacy_history_ui import show_history_controls
store = st.session_state["store"]
show_history_controls(store, store.get(st.session_state["dataset_id"]),
                      A.load_actions(st.session_state["log"]))
""", default_timeout=10)
        app.session_state["store"] = self.store
        app.session_state["dataset_id"] = self.source["dataset_id"]
        app.session_state["log"] = self.log
        app.session_state["_manager_report_grant"] = manager_session(self, self.root, {})
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

    def test_ui_log_is_separate_read_only_and_visible_after_unlink(self):
        app = self.ui()
        self.assertFalse(app.exception)
        self.assertIn("History-link corrections", [item.label for item in app.expander])
        self.assertEqual(app.dataframe[0].value["Operation"].tolist(), ["Claim"])
        self.assertEqual(app.dataframe[0].value["Changed by"].tolist(), ["Unknown"])
        self.assertTrue(any("not action-edit history" in item.value for item in app.caption))
        app.checkbox[0].check().run()
        self.button(app, "Confirm history correction").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.dataframe[0].value["Operation"].tolist(), ["Unlink", "Claim"])
        self.assertEqual(
            app.dataframe[0].value["Changed by"].tolist(), ["test-manager", "Unknown"])
        app.session_state["dataset_id"] = self.third["dataset_id"]
        app.run()
        self.assertFalse(app.exception)
        self.assertFalse(app.dataframe)
        self.assertTrue(any("No recorded history-link changes" in item.value for item in app.info))

    def test_ui_recovery_and_transfer_forward_the_authenticated_identity(self):
        app = self.ui()
        app.checkbox[0].check().run()
        self.button(app, "Confirm history correction").click().run()
        app.selectbox[0].set_value("old.csv").run()
        app.checkbox[0].check().run()
        self.button(app, "Link older history").click().run()
        app.radio[0].set_value("Reassign to another dataset").run()
        app.selectbox[0].set_value(self.target["dataset_id"]).run()
        app.checkbox[0].check().run()
        self.button(app, "Confirm history correction").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(
            app.dataframe[0].value["Changed by"].tolist(),
            ["test-manager", "test-manager", "test-manager", "Unknown"])
        app.session_state["dataset_id"] = self.target["dataset_id"]
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.dataframe[0].value["Changed by"].tolist(), ["test-manager"])

    def test_ui_expired_login_does_not_publish_a_correction(self):
        app = self.ui()
        app.checkbox[0].check().run()
        session = app.session_state["_manager_report_grant"]
        app.session_state["_manager_report_grant"] = dict(session, expires=0)
        self.button(app, "Confirm history correction").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any("Sign in again" in item.value for item in app.error))
        self.assertEqual(self.store.get(self.source["dataset_id"]), self.source)
        self.assertEqual(len(self.store.history_link_events(self.source["dataset_id"])), 1)


if __name__ == "__main__":
    unittest.main()
