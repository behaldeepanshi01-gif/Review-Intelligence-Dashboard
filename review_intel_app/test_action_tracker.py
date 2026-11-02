"""Quick standard-library tests for the action tracker."""

from datetime import date
import tempfile
import unittest

from action_tracker import (
    create_action,
    find_active_action,
    follow_up,
    load_actions,
    save_actions,
    suggested_step,
    update_action,
    weekly_action_summary,
)


class ActionTrackerTests(unittest.TestCase):
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

        summary = weekly_action_summary(actions, "sample", ["A"], reviews)
        text = "\n".join(summary)

        self.assertIn("Review busy-period handoffs.", text)
        self.assertIn("Status: In progress", text)
        self.assertIn("Owner: Manager", text)
        self.assertIn("Due: 2026-01-17", text)
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
