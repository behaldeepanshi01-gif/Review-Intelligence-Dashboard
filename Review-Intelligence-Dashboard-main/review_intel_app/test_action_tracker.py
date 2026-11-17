"""Quick standard-library tests for the action tracker."""

from datetime import date
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dataset_store import DatasetStore, SAMPLE_ID

from action_tracker import (
    create_action,
    find_active_action,
    follow_up,
    is_overdue,
    load_actions,
    save_actions,
    suggested_step,
    update_action,
    weekly_action_summary,
)


class DatasetIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sample = self.root / "sample.csv"
        self.sample.write_bytes(b"built-in synthetic sample")
        self.store = DatasetStore(self.root / "uploads", self.sample)

    def test_same_name_and_same_bytes_do_not_imply_same_identity(self):
        first = self.store.save_snapshot("reviews.csv", b"snapshot")
        other = self.store.save_snapshot("reviews.csv", b"snapshot")
        self.assertNotEqual(first["dataset_id"], other["dataset_id"])
        self.assertNotEqual(first["path"], other["path"])
        self.assertEqual(Path(first["path"]).read_bytes(), b"snapshot")
        log = str(self.root / "actions.json")
        actions = [{"action_id": "first", "dataset_tag": first["dataset_id"]}]
        save_actions(log, actions)
        self.assertEqual(load_actions(log, other["dataset_id"]), [])
        restarted = DatasetStore(self.root / "uploads", self.sample)
        self.assertEqual(restarted.get(first["dataset_id"]), first)
        self.assertEqual(len(restarted.list_datasets()), 2)

    def test_update_renamed_snapshot_keeps_identity_and_old_bytes(self):
        first = self.store.save_snapshot("reviews.csv", b"original")
        updated = self.store.save_snapshot(
            "newer-name.csv", b"updated and appended", first["dataset_id"]
        )
        self.assertEqual(updated["dataset_id"], first["dataset_id"])
        self.assertEqual(updated["correction_path"], first["correction_path"])
        self.assertEqual(Path(first["path"]).read_bytes(), b"original")
        self.assertEqual(Path(updated["path"]).read_bytes(), b"updated and appended")
        self.assertEqual(len(self.store.list_datasets()), 1)

    def test_failed_snapshot_write_keeps_previous_snapshot(self):
        first = self.store.save_snapshot("reviews.csv", b"original")
        with patch.object(Path, "open", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                self.store.save_snapshot("reviews.csv", b"new", first["dataset_id"])
        self.assertEqual(self.store.get(first["dataset_id"]), first)

    def test_uploaded_sample_cannot_inherit_or_replace_builtin(self):
        uploaded = self.store.save_snapshot("sample.csv", self.sample.read_bytes())
        self.assertNotEqual(uploaded["dataset_id"], SAMPLE_ID)
        self.assertNotEqual(uploaded["path"], str(self.sample))
        with self.assertRaises(ValueError):
            self.store.save_snapshot("sample.csv", b"replacement", SAMPLE_ID)
        self.assertEqual(self.sample.read_bytes(), b"built-in synthetic sample")
        self.assertEqual(load_actions(str(self.root / "absent"), SAMPLE_ID), [])

    def test_legacy_file_imported_only_once_even_after_update(self):
        old = self.root / "uploads" / "reviews.CSV"
        old.write_bytes(b"original legacy file")
        restarted = DatasetStore(self.root / "uploads", self.sample)
        first = restarted.list_datasets()[0]
        restarted.save_snapshot("reviews.CSV", b"new", first["dataset_id"])
        again = DatasetStore(self.root / "uploads", self.sample)
        self.assertEqual(len(again.list_datasets()), 1)
        self.assertEqual(old.read_bytes(), b"original legacy file")
        self.assertIsNone(again.get(first["dataset_id"])["legacy_tag"])
        self.assertEqual(again.get(first["dataset_id"])["correction_path"], str(old.resolve()))

    def test_legacy_history_requires_explicit_exclusive_link_and_stays_unchanged(self):
        first = self.store.save_snapshot("sample.csv", b"uploaded")
        other = self.store.save_snapshot("sample.csv", b"unrelated")
        log = str(self.root / "actions.json")
        actions = [{
            "dataset_tag": "sample", "location": "Demo", "theme": "Price",
            "action_id": "old", "status": "Planned", "baseline_share": 25,
            "alert_end_date": "2026-01-01",
        }]
        save_actions(log, actions)
        original = Path(log).read_bytes()
        for dataset_id in (SAMPLE_ID, first["dataset_id"], other["dataset_id"]):
            self.assertEqual(load_actions(log, dataset_id), [])
        claimed = self.store.claim_legacy_history(first["dataset_id"], "sample", actions)
        self.assertEqual(
            load_actions(log, first["dataset_id"], legacy_tag=claimed["legacy_tag"]),
            actions,
        )
        self.assertEqual(
            find_active_action(actions, first["dataset_id"], "Demo", "Price",
                               legacy_tag=claimed["legacy_tag"]), actions[0],
        )
        self.assertIn("Demo", "\n".join(weekly_action_summary(
            actions, first["dataset_id"], ["Demo"], [], legacy_tag="sample"
        )))
        self.assertEqual(Path(log).read_bytes(), original)
        for dataset_id in (SAMPLE_ID, other["dataset_id"]):
            with self.assertRaises(ValueError):
                self.store.claim_legacy_history(dataset_id, "sample", actions)
            self.assertEqual(load_actions(log, dataset_id), [])
        restarted = DatasetStore(self.root / "uploads", self.sample)
        self.assertEqual(restarted.get(first["dataset_id"])["legacy_tag"], "sample")


class ActionTrackerTests(unittest.TestCase):
    def test_overdue_status_and_date_boundaries(self):
        today = date(2026, 1, 17)
        for status in ("Planned", "In progress", "Done"):
            for due, past in [
                ("2026-01-16", True), (date(2026, 1, 16), True),
                ("2026-01-17", False), ("2026-01-18", False),
                (None, False), ("", False), ("invalid", False),
            ]:
                with self.subTest(status=status, due=due):
                    self.assertEqual(
                        is_overdue({"status": status, "due_date": due}, today),
                        past and status != "Done",
                    )

    def test_summary_marks_only_scoped_overdue_active_actions(self):
        base = {
            "dataset_tag": "sample", "location": "A", "status": "Planned",
            "due_date": "2026-01-16",
        }
        actions = [
            dict(base, action_text="Past planned"),
            dict(base, action_text="Past started", status="In progress"),
            dict(base, action_text="Due today", due_date="2026-01-17"),
            dict(base, action_text="Due later", due_date="2026-01-18"),
            dict(base, action_text="No due date", due_date=None),
            dict(base, action_text="Invalid due date", due_date="invalid"),
            dict(base, action_text="Completed", status="Done"),
            dict(base, action_text="Other file", dataset_tag="other"),
            dict(base, action_text="Other location", location="B"),
        ]
        lines = weekly_action_summary(actions, "sample", ["A"], [], date(2026, 1, 17))
        overdue = [line for line in lines if "OVERDUE" in line]
        self.assertEqual(len(overdue), 2)
        self.assertIn("Past planned", overdue[0])
        self.assertIn("Past started", overdue[1])
        text = "\n".join(lines)
        for excluded in ("Completed", "Other file", "Other location"):
            self.assertNotIn(excluded, text)

    def test_create_action_keeps_alert_baseline_and_scope(self):
        action = create_action(
            dataset_tag="sample",
            alert={
                "location": "Demo Cafe",
                "theme": "Service speed",
                "recent_share": 25.0,
                "recent_mentions": 5,
            },
            theme_key="service_speed",
            action_text="Check the handoff during busy periods.",
            owner="Manager",
            start_date=date(2026, 1, 10),
            due_date=date(2026, 1, 17),
            alert_end_date=date(2026, 1, 9),
        )

        self.assertEqual(action["dataset_tag"], "sample")
        self.assertEqual(action["theme_key"], "service_speed")
        self.assertEqual(action["baseline_share"], 25.0)
        self.assertEqual(action["baseline_mentions"], 5)
        self.assertEqual(action["status"], "Planned")
        self.assertEqual(action["start_date"], "2026-01-10")

    def test_action_log_round_trip_and_dataset_filter(self):
        with tempfile.TemporaryDirectory() as folder:
            path = f"{folder}/action_log.json"
            actions = [
                {"action_id": "one", "dataset_tag": "sample"},
                {"action_id": "two", "dataset_tag": "other"},
            ]
            save_actions(path, actions)

            self.assertEqual(load_actions(path), actions)
            self.assertEqual(load_actions(path, "sample"), actions[:1])
            self.assertEqual(load_actions(path, "other"), actions[1:])

    def test_update_action_preserves_dataset_scope_and_persists(self):
        action = create_action(
            dataset_tag="sample",
            alert={
                "location": "Demo Cafe",
                "theme": "Service speed",
                "recent_share": 25.0,
                "recent_mentions": 5,
            },
            theme_key="service_speed",
            action_text="Review handoffs.",
            owner="Manager",
            start_date=date(2026, 1, 10),
            due_date=date(2026, 1, 17),
            alert_end_date=date(2026, 1, 9),
        )
        updated = update_action(
            action,
            "Check the busy-period handoff.",
            "Shift lead",
            "In progress",
            date(2026, 1, 11),
            date(2026, 1, 20),
        )

        with tempfile.TemporaryDirectory() as folder:
            path = f"{folder}/action_log.json"
            other_dataset_action = {
                "action_id": "other",
                "dataset_tag": "another-file",
            }
            save_actions(path, [updated, other_dataset_action])

            loaded = load_actions(path, "sample")
            self.assertEqual(loaded, [updated])
            self.assertEqual(loaded[0]["dataset_tag"], "sample")
            self.assertEqual(loaded[0]["status"], "In progress")
            self.assertEqual(loaded[0]["owner"], "Shift lead")
            self.assertEqual(
                find_active_action(loaded, "sample", "Demo Cafe", "Service speed"),
                updated,
            )
            self.assertIsNone(
                find_active_action(loaded, "another-file", "Demo Cafe", "Service speed")
            )

    def test_update_action_rejects_invalid_status(self):
        with self.assertRaises(ValueError):
            update_action(
                {"dataset_tag": "sample"},
                "Check service.",
                "",
                "Started",
                date(2026, 1, 10),
                date(2026, 1, 11),
            )

    def test_suggestion_is_available_for_alert_theme(self):
        self.assertIn("handoffs", suggested_step("Service speed"))
        self.assertTrue(suggested_step("Unknown theme"))

    def test_active_action_excludes_done_records(self):
        actions = [
            {"dataset_tag": "sample", "location": "A", "theme": "Price",
             "status": "Done", "created_on": "2026-01-01"},
            {"dataset_tag": "sample", "location": "A", "theme": "Price",
             "status": "In progress", "created_on": "2026-01-02"},
        ]
        self.assertEqual(
            find_active_action(actions, "sample", "A", "Price"),
            actions[1],
        )

    def test_follow_up_waits_for_five_new_reviews(self):
        action = {
            "location": "A",
            "theme_key": "service_speed",
            "status": "In progress",
            "start_date": "2026-01-10",
            "baseline_share": 40,
        }
        reviews = [
            {"location": "A", "date": date(2026, 1, 11), "themes_neg": []}
            for _ in range(4)
        ]
        result = follow_up(action, reviews)
        self.assertFalse(result["ready"])
        self.assertEqual(result["review_count"], 4)

    def test_follow_up_compares_rates_without_claiming_cause(self):
        action = {
            "location": "A",
            "theme_key": "service_speed",
            "status": "In progress",
            "start_date": "2026-01-10",
            "baseline_share": 40,
        }
        reviews = [
            {"location": "A", "date": date(2026, 1, 9), "themes_neg": ["service_speed"]},
            {"location": "A", "date": date(2026, 1, 11), "themes_neg": ["service_speed"]},
            {"location": "A", "date": date(2026, 1, 12), "themes_neg": []},
            {"location": "A", "date": date(2026, 1, 13), "themes_neg": []},
            {"location": "A", "date": date(2026, 1, 14), "themes_neg": []},
            {"location": "A", "date": date(2026, 1, 15), "themes_neg": []},
            {"location": "B", "date": date(2026, 1, 16), "themes_neg": []},
        ]

        result = follow_up(action, reviews)

        self.assertTrue(result["ready"])
        self.assertEqual(result["review_count"], 5)
        self.assertEqual(result["mentions"], 1)
        self.assertEqual(result["share"], 20.0)
        self.assertEqual(result["change_points"], -20.0)
        self.assertEqual(result["direction"], "lower")

    def test_corrupt_action_log_fails_clearly(self):
        with tempfile.TemporaryDirectory() as folder:
            path = f"{folder}/action_log.json"
            with open(path, "w", encoding="utf-8") as file:
                file.write("{broken")

            with self.assertRaises(ValueError):
                load_actions(path)

    def test_weekly_summary_filters_scope_and_hides_review_content(self):
        actions = [
            {
                "dataset_tag": "sample",
                "location": "A",
                "theme": "Service speed",
                "theme_key": "service_speed",
                "action_text": "Review busy-period handoffs.",
                "owner": "Manager",
                "status": "In progress",
                "start_date": "2026-01-10",
                "due_date": "2026-01-17",
                "created_on": "2026-01-10",
                "baseline_share": 40,
            },
            {
                "dataset_tag": "other",
                "location": "A",
                "theme": "Price",
                "status": "Planned",
            },
            {
                "dataset_tag": "sample",
                "location": "B",
                "theme": "Cleanliness",
                "status": "Planned",
            },
            {
                "dataset_tag": "sample",
                "location": "A",
                "theme": "Food",
                "status": "Done",
            },
        ]
        reviews = [
            {
                "location": "A",
                "date": date(2026, 1, 11),
                "themes_neg": ["service_speed"],
                "reviewer": "Guest Name",
                "text": "Raw guest review that must not appear.",
            }
            for _ in range(5)
        ]

        summary = weekly_action_summary(actions, "sample", ["A"], reviews, date(2026, 1, 18))
        text = "\n".join(summary)

        self.assertIn("Review busy-period handoffs.", text)
        self.assertIn("Status: In progress", text)
        self.assertIn("Owner: Manager", text)
        self.assertIn("Due: 2026-01-17", text)
        self.assertIn("OVERDUE", text)
        self.assertIn("5 newer reviews", text)
        self.assertIn("do not prove", text)
        self.assertNotIn("Guest Name", text)
        self.assertNotIn("Raw guest review", text)
        self.assertNotIn("Cleanliness", text)
        self.assertNotIn("Price", text)
        self.assertNotIn("Done", text)

    def test_weekly_summary_omits_follow_up_until_five_reviews(self):
        action = {
            "dataset_tag": "sample",
            "location": "A",
            "theme": "Service speed",
            "theme_key": "service_speed",
            "action_text": "Check handoffs.",
            "status": "In progress",
            "start_date": "2026-01-10",
            "baseline_share": 40,
        }
        reviews = [
            {"location": "A", "date": date(2026, 1, 11), "themes_neg": []}
            for _ in range(4)
        ]

        summary = weekly_action_summary([action], "sample", ["A"], reviews)

        self.assertTrue(any("Check handoffs." in line for line in summary))
        self.assertFalse(any("Follow-up:" in line for line in summary))


if __name__ == "__main__":
    unittest.main()
