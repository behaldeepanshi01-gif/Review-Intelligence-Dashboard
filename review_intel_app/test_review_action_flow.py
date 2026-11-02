"""Verify the real CSV loader and action lifecycle using only synthetic data."""

import csv
from datetime import timedelta
import io
from pathlib import Path
import tempfile
import unittest

import action_tracker as A
import engine as E


SAMPLE = Path(__file__).parent / "data" / "sample_reviews.csv"


class ReviewActionFlowTests(unittest.TestCase):
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
            ])
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
