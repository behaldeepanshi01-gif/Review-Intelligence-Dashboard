"""Two independent managers share calendars without overwriting stale settings."""
from datetime import date, datetime
from pathlib import Path
import tempfile
import unittest

import action_tracker as A
from location_settings import LocationSettings, SettingsConflictError
from calendar_test_support import manager_session


class LocationSettingsTests(unittest.TestCase):
    def test_two_managers_locations_and_dataset_ownership(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calendars.sqlite"
            session = manager_session(self, directory, {"dataset": ["East", "India"]})
            manager_one = LocationSettings(path, session=session)
            manager_two = LocationSettings(path, session=session)
            manager_one.save("dataset", "East", "America/New_York", expected_revision=0)
            manager_two.save("dataset", "India", "Asia/Kolkata", expected_revision=0)
            self.assertEqual(manager_one.load("dataset"), manager_two.load("dataset"))
            self.assertEqual(LocationSettings(path, session=session).load("dataset"), manager_one.load("dataset"))
            self.assertEqual(manager_two.load("unrelated"), {})
            with self.assertRaises(SettingsConflictError):
                manager_two.save("dataset", "East", "UTC", expected_revision=0)
            with self.assertRaises(ValueError):
                manager_two.save("dataset", "East", "Invalid/Zone", expected_revision=1)
            zones = {loc: row["timezone"] for loc, row in manager_two.load("dataset").items()}
            now = datetime.fromisoformat("2026-01-02T00:00:00+00:00")
            actions = [{"dataset_tag": "dataset", "location": loc, "status": "Planned",
                        "due_date": "2026-01-01", "start_date": "2026-01-01"}
                       for loc in ["East", "India"]]
            originals = [dict(action) for action in actions]
            self.assertEqual([A.is_overdue(a, timezones_by_location=zones, now=now)
                              for a in actions], [False, True])
            summary = A.weekly_action_summary(actions, "dataset", ["East", "India"], [],
                                              timezones_by_location=zones, now=now)
            self.assertTrue(any("- OVERDUE — India" in line for line in summary))
            self.assertFalse(any("- OVERDUE — East" in line for line in summary))
            for loc, expected in [("East", "2026-01-01"), ("India", "2026-01-02")]:
                action = A.create_action(
                    "dataset", {"location": loc, "theme": "Speed", "recent_share": 10,
                                "recent_mentions": 2}, "speed", "Check", "",
                    date(2026, 1, 1), date(2026, 1, 7), date(2026, 1, 1),
                    timezones_by_location=zones, now=now)
                self.assertEqual(action["created_on"], expected)
            manager_one.save("dataset", "East", "Asia/Kolkata", expected_revision=1)
            zones["East"] = manager_two.load("dataset")["East"]["timezone"]
            self.assertTrue(A.is_overdue(actions[0], timezones_by_location=zones, now=now))
            self.assertEqual(actions, originals)


if __name__ == "__main__":
    unittest.main()
