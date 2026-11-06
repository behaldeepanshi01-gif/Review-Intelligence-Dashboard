"""Server permission checks use real isolated identities, not UI hiding."""
from pathlib import Path
import tempfile
import unittest

from calendar_test_support import manager_session, sample_app
from location_settings import LocationSettings
import manager_identity as identity


class CalendarPermissionsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.session = manager_session(self, temp.name, {"dataset": ["Cafe", "New"]})
        self.path = Path(temp.name) / "calendars.sqlite"
        self.store = LocationSettings(self.path, session=self.session)
        self.store.save("dataset", "Cafe", "Asia/Kolkata", expected_revision=0)

    def test_unsigned_and_wrong_scopes_cannot_read_or_write(self):
        unsigned = LocationSettings(self.path)
        with self.assertRaises(PermissionError):
            unsigned.load("dataset")
        for store, dataset, location in [
            (unsigned, "dataset", "Cafe"), (self.store, "other", "Cafe"),
            (self.store, "dataset", "Other"),
        ]:
            with self.assertRaises(PermissionError):
                store.save(dataset, location, "UTC", expected_revision=1)
        self.assertEqual(self.store.load("other"), {})
        identity.set_account("other", "another-synthetic-password", {"dataset": ["Other"]})
        other = LocationSettings(self.path, session=identity.authenticate(
            "other", "another-synthetic-password"))
        self.assertEqual(other.load("dataset"), {})
        self.assertEqual(self.store.load("dataset")["Cafe"]["timezone"], "Asia/Kolkata")

    def test_rename_requires_both_assignments(self):
        with self.assertRaises(PermissionError):
            self.store.rename("dataset", "Cafe", "Forbidden",
                              expected_revision=1, confirmed=True)
        self.store.rename("dataset", "Cafe", "New", expected_revision=1, confirmed=True)
        self.assertEqual(self.store.load("dataset")["New"]["timezone"], "Asia/Kolkata")

    def test_expired_and_revoked_sessions_fail_at_storage_boundary(self):
        for invalidate in [
            lambda: self.session.update(expires=0),
            lambda: identity.remove_account("test-manager"),
        ]:
            self.session["expires"] = identity.time.time() + 1800
            invalidate()
            with self.assertRaises(PermissionError):
                self.store.load("dataset")
            with self.assertRaises(PermissionError):
                self.store.save("dataset", "Cafe", "UTC", expected_revision=1)
            with self.assertRaises(PermissionError):
                self.store.rename("dataset", "Cafe", "New",
                                  expected_revision=1, confirmed=True)

    def test_dashboard_login_scope_save_and_revocation(self):
        from unittest.mock import patch
        from streamlit.testing.v1 import AppTest
        import pandas as pd
        import engine
        from dataset_store import SAMPLE_ID
        identity.set_account("test-manager", "synthetic-calendar-password",
                             {SAMPLE_ID: ["Cafe"]})
        data = pd.DataFrame([
            {"location": loc, "review_id": f"{loc}-{i}", "reviewer": "Guest",
             "date": pd.Timestamp(f"2026-10-0{i+1}"), "rating": 3, "text": "Good food"}
            for loc in ["Cafe", "Other"] for i in range(2)
        ])
        # Only the calendar path and input data are replaced; authentication,
        # widgets and storage permission checks run as in the application.
        original = LocationSettings
        with patch.object(engine, "load_reviews", return_value=data), patch(
            "location_settings.LocationSettings",
            side_effect=lambda path, **kw: original(self.path, **kw),
        ) as constructor:
            constructor.default.side_effect = original.default
            app = sample_app(AppTest.from_file(str(Path(__file__).with_name("app.py")),
                                               default_timeout=30))
            self.assertFalse(app.exception)
            self.assertFalse(any(t.label == "Restaurant timezone" for t in app.text_input))
            app.text_input(key="_manager_username").set_value("test-manager")
            app.text_input(key="_manager_report_password").set_value("synthetic-calendar-password")
            next(b for b in app.button if b.label == "Unlock restaurant calendars").click().run()
            self.assertFalse(app.exception)
            picker = next(s for s in app.selectbox if s.label == "Calendar location")
            self.assertEqual(picker.options, ["Cafe"])
            next(t for t in app.text_input if t.label == "Restaurant timezone").set_value("UTC")
            next(b for b in app.button if b.label == "Save location timezone").click().run()
            self.assertFalse(app.exception)
            session = identity.authenticate("test-manager", "synthetic-calendar-password")
            self.assertEqual(original(self.path, session=session).load(SAMPLE_ID)["Cafe"]["timezone"],
                             "UTC")
            identity.remove_account("test-manager")
            app.run()
            self.assertFalse(app.exception)
            self.assertFalse(any(t.label == "Restaurant timezone" for t in app.text_input))


if __name__ == "__main__":
    unittest.main()
