"""Process and manager-session races using isolated synthetic registries and logs."""

from datetime import date
import multiprocessing
from pathlib import Path
import shutil
import sqlite3
import tempfile
import traceback
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import action_tracker as A
import dataset_store as D
import engine as E
import manager_identity as identity
from legacy_history_ui import history_changed
from calendar_test_support import manager_session
from process_test_support import isolated_process_test


DAY = date(2026, 1, 1)
PROCESS_TIMEOUT = 20


def _history_race_worker(config, operation, pause, start, release, channel):
    """Spawn-safe worker: exercise real locks, patching only the pause boundary."""
    try:
        identity.DB_PATH = Path(config["accounts"])
        # Initialize both stores before either operation takes its transaction.
        # Otherwise constructor writes could be mistaken for operation contention.
        store = D.DatasetStore(config["uploads"], config["sample"])
        channel.send(("ready", None))
        if not start.wait(PROCESS_TIMEOUT):
            raise TimeoutError("History operation was not started")

        def wait_for_release():
            channel.send(("paused", None))
            if not release.wait(PROCESS_TIMEOUT):
                raise TimeoutError("Paused history operation was not released")

        def save():
            return A.edit_saved_action(
                config["log"], config["legacy"],
                "" if operation == "invalid_save" else "Saved before transfer",
                "Synthetic manager", "In progress", DAY, DAY,
                history_store=store, dataset_id=D.SAMPLE_ID,
                expected_history_revision=config["source"]["history_revision"],
                session=config["session"])

        def transfer():
            store.correct_legacy_history(
                D.SAMPLE_ID, "old.csv",
                expected_source_revision=config["source"]["history_revision"],
                target_id=config["target"]["dataset_id"],
                expected_target_revision=config["target"]["history_revision"])

        invoke = transfer if operation == "transfer" else save
        if not pause:
            real_connect = store.connect

            def short_connect():
                db = real_connect()
                db.execute("PRAGMA busy_timeout = 200")
                return db

            # A real SQLITE_BUSY proves this process reached the locked database;
            # merely sleeping and checking an unset event could pass by accident.
            with patch.object(store, "connect", side_effect=short_connect):
                try:
                    invoke()
                except sqlite3.OperationalError as exc:
                    if exc.sqlite_errorcode != sqlite3.SQLITE_BUSY:
                        raise
                else:
                    raise AssertionError("Contending operation was not blocked")
            channel.send(("blocked", None))
            # Retry the real operation, with its normal bounded SQLite timeout.
            try:
                result = invoke()
            except D.HistoryAssociationError as exc:
                channel.send(("rejected", str(exc)))
            else:
                channel.send(("completed", result))
        elif operation == "transfer":
            record = store._record_history_link

            def paused_record(*args, **kwargs):
                record(*args, **kwargs)
                # Association and audit writes are made, but not yet committed.
                wait_for_release()

            with patch.object(store, "_record_history_link", side_effect=paused_record):
                invoke()
            channel.send(("completed", None))
        elif operation == "invalid_save":
            update = A.update_action

            def paused_update(*args, **kwargs):
                wait_for_release()
                return update(*args, **kwargs)

            with patch.object(A, "update_action", side_effect=paused_update):
                try:
                    invoke()
                except ValueError as exc:
                    channel.send(("rejected", str(exc)))
                else:
                    raise AssertionError("Invalid action was accepted")
        else:
            replace = A.os.replace

            def paused_replace(*args, **kwargs):
                # Validation passed; JSON is written and fsynced to a temp file.
                # Both the registry transaction and action lock must still hold.
                wait_for_release()
                if operation == "failed_save":
                    raise OSError("Synthetic action publication failure")
                return replace(*args, **kwargs)

            with patch.object(A.os, "replace", side_effect=paused_replace):
                try:
                    result = invoke()
                except OSError as exc:
                    if operation != "failed_save":
                        raise
                    channel.send(("rejected", str(exc)))
                else:
                    channel.send(("completed", result))
    except BaseException:
        channel.send(("error", traceback.format_exc()))
        raise
    finally:
        channel.close()


class GuardedHistoryProcessTests(unittest.TestCase):
    """Exercise real spawned workers independently of earlier AppTest runs."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sample = self.root / "sample.csv"
        self.sample.write_text(
            "date,rating,text,location\n2026-01-01,2,Slow service,Demo Cafe\n",
            encoding="utf-8")
        self.store = D.DatasetStore(self.root / "uploads", self.sample)
        self.target = self.store.save_snapshot("destination.csv", self.sample.read_bytes())
        self.legacy = A.create_action(
            "old.csv", dict(location="Demo Cafe", theme="Service speed",
                            recent_share=40, recent_mentions=4),
            "service_speed", "Original legacy plan", "", DAY, DAY, DAY, today=DAY,
            tagging_provenance={"rules_version": "synthetic"},
            source_reviews=[dict(location="Demo Cafe", date=DAY.isoformat(),
                                 rating=2, text="Slow service")])
        self.legacy["unknown_historical_field"] = {"preserve": ["synthetic evidence"]}
        native = dict(self.legacy, action_id="native", dataset_tag=D.SAMPLE_ID)
        target_native = dict(self.legacy, action_id="target-native",
                             dataset_tag=self.target["dataset_id"])
        self.actions = [self.legacy, native, target_native]
        self.log = self.root / "actions.json"
        A.save_actions(str(self.log), self.actions)
        self.before = self.log.read_bytes()
        self.source = self.store.claim_legacy_history(D.SAMPLE_ID, "old.csv", self.actions)
        session = manager_session(self, self.root, {D.SAMPLE_ID: ["Demo Cafe"]})
        self.config = dict(
            uploads=str(self.root / "uploads"), sample=str(self.sample),
            accounts=str(identity.DB_PATH), log=str(self.log), legacy=self.legacy,
            source=self.source, target=self.target, session=session)

    def receive(self, channel, expected):
        self.assertTrue(channel.poll(PROCESS_TIMEOUT), f"Timed out waiting for {expected}")
        message, result = channel.recv()
        self.assertEqual(message, expected, result)
        return result

    def run_race(self, holder_operation, contender_operation):
        context = multiprocessing.get_context("spawn")
        release = context.Event()
        workers = []

        def cleanup():
            release.set()
            for process, channel, _ in workers:
                if process.is_alive():
                    process.terminate()
                process.join(timeout=5)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=5)
                channel.close()
                process.close()

        self.addCleanup(cleanup)
        for operation, pause in ((holder_operation, True), (contender_operation, False)):
            parent, child = context.Pipe()
            start = context.Event()
            process = context.Process(
                target=_history_race_worker,
                args=(self.config, operation, pause, start, release, child))
            process.start()
            child.close()
            workers.append((process, parent, start))
        holder, contender = workers
        for _, channel, _ in workers:
            self.receive(channel, "ready")
        holder[2].set()
        self.receive(holder[1], "paused")
        contender[2].set()
        self.receive(contender[1], "blocked")
        self.assertFalse(contender[1].poll(0.2), "Contender finished before release")
        self.assertEqual(self.log.read_bytes(), self.before)
        self.assertEqual(self.store.get(D.SAMPLE_ID), self.source)
        self.assertEqual(self.store.get(self.target["dataset_id"]), self.target)
        if holder_operation in ("save", "failed_save"):
            self.assertEqual(len(list(self.root.glob(".actions-*.tmp"))), 1)
        release.set()
        return workers

    def finish(self, workers, expected_holder, expected_contender):
        results = [self.receive(worker[1], expected)
                   for worker, expected in zip(workers, (expected_holder, expected_contender))]
        for process, _, _ in workers:
            process.join(timeout=PROCESS_TIMEOUT)
            self.assertFalse(process.is_alive(), "History worker did not exit")
            self.assertEqual(process.exitcode, 0)
        self.assertEqual(list(self.root.glob(".actions-*.tmp")), [])
        source = self.store.get(D.SAMPLE_ID)
        target = self.store.get(self.target["dataset_id"])
        self.assertIsNone(source["legacy_tag"])
        self.assertEqual(target["legacy_tag"], "old.csv")
        self.assertEqual(source["history_revision"], self.source["history_revision"] + 1)
        self.assertEqual(target["history_revision"], self.target["history_revision"] + 1)
        owners = [row["dataset_id"] for row in self.store.list_datasets(include_sample=True)
                  if row["legacy_tag"] == "old.csv"]
        self.assertEqual(owners, [self.target["dataset_id"]])
        return results

    @isolated_process_test
    def test_transfer_waits_for_validated_action_json_write(self):
        workers = self.run_race("save", "transfer")
        saved, _ = self.finish(workers, "completed", "completed")
        expected = A.update_action(
            self.legacy, "Saved before transfer", "Synthetic manager", "In progress", DAY, DAY)
        self.assertEqual({k: v for k, v in saved.items() if k != "edit_history"}, expected)
        self.assertEqual(len(saved["edit_history"]), 1)
        self.assertEqual(saved["edit_history"][0]["saved_by"], "test-manager")
        # Compare every field, not just selected baseline counters, and both native records.
        self.assertEqual(A.load_actions(str(self.log)), [saved, *self.actions[1:]])
        target = self.store.get(self.target["dataset_id"])
        self.assertIn(saved, A.load_actions(
            str(self.log), target["dataset_id"], legacy_tag=target["legacy_tag"]))

    @isolated_process_test
    def test_transfer_first_blocks_then_rejects_former_owner_save(self):
        workers = self.run_race("transfer", "save")
        _, error = self.finish(workers, "completed", "rejected")
        self.assertIn("history link changed", error)
        self.assertEqual(self.log.read_bytes(), self.before)

    @isolated_process_test
    def test_rejected_action_validation_releases_transaction_for_transfer(self):
        workers = self.run_race("invalid_save", "transfer")
        error, _ = self.finish(workers, "rejected", "completed")
        self.assertEqual(error, "Enter an action before saving.")
        self.assertEqual(self.log.read_bytes(), self.before)

    @isolated_process_test
    def test_failed_json_write_releases_transaction_without_changing_baselines(self):
        workers = self.run_race("failed_save", "transfer")
        error, _ = self.finish(workers, "rejected", "completed")
        self.assertEqual(error, "Synthetic action publication failure")
        self.assertEqual(self.log.read_bytes(), self.before)


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
