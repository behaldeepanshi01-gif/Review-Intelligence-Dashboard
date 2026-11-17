"""Timezone audit entries share the successful settings transaction."""
from datetime import datetime
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from calendar_test_support import manager_session
from location_settings import LocationSettings, SettingsConflictError
import manager_identity as identity


class TimezoneHistoryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.session = manager_session(self, temp.name, {"dataset": ["Cafe", "New", "Other"]})
        self.path = Path(temp.name) / "calendars.sqlite"
        self.store = LocationSettings(self.path, session=self.session)

    def test_successful_saves_persist_attribution_and_revisions(self):
        self.assertEqual(self.store.timezone_history("dataset", "Cafe"), [])
        self.store.save("dataset", "Cafe", "UTC", expected_revision=0)
        identity.set_account("second", "another-synthetic-password", {"dataset": ["Cafe"]})
        second = LocationSettings(self.path, session=identity.authenticate(
            "second", "another-synthetic-password"))
        second.save("dataset", "Cafe", "Asia/Kolkata", expected_revision=1)
        rows = LocationSettings(self.path, session=self.session).timezone_history("dataset", "Cafe")
        self.assertEqual([r["manager"] for r in rows], ["second", "test-manager"])
        self.assertEqual([r["revision"] for r in rows], [2, 1])
        self.assertEqual(rows[0]["previous_timezone"], "UTC")
        self.assertEqual(rows[0]["new_timezone"], "Asia/Kolkata")
        self.assertEqual(rows[1]["previous_timezone"], "America/New_York")
        self.assertIsNotNone(datetime.fromisoformat(rows[0]["changed_at"]).tzinfo)
        self.assertEqual(self.store.timezone_history("dataset", "Other"), [])

    def test_failed_saves_never_append_and_failed_audit_rolls_back_settings(self):
        self.store.save("dataset", "Cafe", "UTC", expected_revision=0)
        before = self.store.timezone_history("dataset", "Cafe")
        for zone, revision in [("Asia/Kolkata", 0), ("Invalid/Zone", 1)]:
            with self.assertRaises(ValueError):
                self.store.save("dataset", "Cafe", zone, expected_revision=revision)
        with patch.object(self.store, "_record_timezone", side_effect=sqlite3.OperationalError("disk")):
            with self.assertRaises(sqlite3.Error):
                self.store.save("dataset", "Cafe", "Asia/Kolkata", expected_revision=1)
        self.assertEqual(self.store.load("dataset")["Cafe"], {"timezone": "UTC", "revision": 1})
        self.assertEqual(self.store.timezone_history("dataset", "Cafe"), before)
        for store, dataset, location in [
            (LocationSettings(self.path), "dataset", "Cafe"),
            (self.store, "unrelated", "Cafe"), (self.store, "dataset", "Forbidden"),
            (LocationSettings(self.path, session={**self.session, "expires": 0}), "dataset", "Cafe"),
        ]:
            with self.assertRaises(PermissionError):
                store.save(dataset, location, "UTC", expected_revision=1)
            with self.assertRaises(PermissionError):
                store.timezone_history(dataset, location)
        identity.remove_account("test-manager")
        with self.assertRaises(PermissionError):
            self.store.save("dataset", "Cafe", "UTC", expected_revision=1)
        with self.assertRaises(PermissionError):
            self.store.timezone_history("dataset", "Cafe")
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM calendar_timezone_history").fetchone()[0], 1)

    def test_history_is_append_only_and_legacy_rows_are_not_fabricated(self):
        with self.store.connect() as db:
            db.execute("INSERT INTO location_calendars VALUES ('dataset', 'Cafe', 'UTC', 5)")
        self.assertEqual(self.store.timezone_history("dataset", "Cafe"), [])
        self.store.save("dataset", "Cafe", "Asia/Kolkata", expected_revision=5)
        for statement in ["DELETE FROM calendar_timezone_history",
                          "UPDATE calendar_timezone_history SET manager='fake'"]:
            with self.assertRaises(sqlite3.IntegrityError), self.store.connect() as db:
                db.execute(statement)
        row = self.store.timezone_history("dataset", "Cafe")[0]
        self.assertEqual((row["previous_timezone"], row["revision"]), ("UTC", 6))

    def test_rename_preserves_original_events_without_leaking_old_names(self):
        self.store.save("dataset", "Cafe", "UTC", expected_revision=0)
        original = self.store.timezone_history("dataset", "Cafe")
        self.store.rename("dataset", "Cafe", "New", expected_revision=1, confirmed=True)
        self.assertEqual(self.store.timezone_history("dataset", "New"), original)
        with self.assertRaises(SettingsConflictError):
            self.store.save("dataset", "Cafe", "Asia/Kolkata", expected_revision=1)
        self.store.save("dataset", "New", "Asia/Kolkata", expected_revision=2)
        identity.set_account("limited", "another-synthetic-password", {"dataset": ["New"]})
        limited = LocationSettings(self.path, session=identity.authenticate(
            "limited", "another-synthetic-password"))
        rows = limited.timezone_history("dataset", "New")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["location"], "New")
        self.assertEqual(rows[0]["revision"], 3)


if __name__ == "__main__":
    unittest.main()
