"""Deterministic local-calendar tests; no dependency on the server clock."""

from datetime import date, datetime
import unittest
from unittest.mock import patch

import action_tracker as A


class RestaurantCalendarTests(unittest.TestCase):
    def test_midnight_and_dst_boundaries(self):
        # Spring day lasts 23 hours; autumn day lasts 25 hours in New York.
        cases = [
            ("2026-01-02T04:59:59+00:00", "2026-01-01"),
            ("2026-01-02T05:00:00+00:00", "2026-01-02"),
            ("2026-03-08T04:59:59+00:00", "2026-03-07"),
            ("2026-03-08T05:00:00+00:00", "2026-03-08"),
            ("2026-03-08T06:59:59+00:00", "2026-03-08"),
            ("2026-03-08T07:00:00+00:00", "2026-03-08"),
            ("2026-03-09T03:59:59+00:00", "2026-03-08"),
            ("2026-03-09T04:00:00+00:00", "2026-03-09"),
            ("2026-11-01T03:59:59+00:00", "2026-10-31"),
            ("2026-11-01T04:00:00+00:00", "2026-11-01"),
            ("2026-11-01T05:30:00+00:00", "2026-11-01"),
            ("2026-11-01T06:30:00+00:00", "2026-11-01"),
            ("2026-11-02T04:59:59+00:00", "2026-11-01"),
            ("2026-11-02T05:00:00+00:00", "2026-11-02"),
        ]
        for instant, expected in cases:
            with self.subTest(instant=instant):
                local_day = A.restaurant_today(now=datetime.fromisoformat(instant))
                self.assertEqual(local_day, date.fromisoformat(expected))
                for status in A.STATUS_OPTIONS:
                    action = {"status": status, "due_date": expected}
                    self.assertFalse(A.is_overdue(action, local_day))
                    action["due_date"] = date.fromordinal(local_day.toordinal() - 1)
                    self.assertEqual(A.is_overdue(action, local_day), status != "Done")

    def test_configurable_zone_and_default_clock_paths(self):
        instant = datetime.fromisoformat("2026-01-02T00:00:00+00:00")
        with patch.object(A, "datetime") as clock:
            clock.now.side_effect = lambda zone: instant.astimezone(zone)
            self.assertEqual(A.restaurant_today(), date(2026, 1, 1))
            self.assertEqual(A.restaurant_today("Asia/Kolkata"), date(2026, 1, 2))
        action = {"dataset_tag": "sample", "location": "A",
                  "status": "Planned", "due_date": "2026-01-01"}
        for zone, overdue in [("America/New_York", False), ("Asia/Kolkata", True)]:
            with patch.object(A, "restaurant_today",
                              return_value=A.restaurant_today(zone, now=instant)) as today:
                self.assertEqual(A.is_overdue(action, timezone_name=zone), overdue)
                summary = A.weekly_action_summary(
                    [action], "sample", ["A"], [], timezone_name=zone)
                self.assertEqual("OVERDUE" in "\n".join(summary), overdue)
                today.assert_called_with(zone)

    def test_invalid_timezone_and_naive_instant_rejected(self):
        for zone in ["", "Invalid/Zone", "../UTC"]:
            with self.subTest(zone=zone), self.assertRaisesRegex(ValueError, "IANA"):
                A.restaurant_today(zone)
        with self.assertRaisesRegex(ValueError, "include a timezone"):
            A.restaurant_today(now=datetime(2026, 1, 1))


if __name__ == "__main__":
    unittest.main()
