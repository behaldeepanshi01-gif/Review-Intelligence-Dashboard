"""Synthetic identities and grants only. Never touches the real account store."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import manager_identity as M


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.patch = patch.object(M, "DB_PATH", Path(self.temp.name) / "accounts.sqlite")
        self.patch.start()
        self.addCleanup(self.patch.stop)
        M.set_account("alice", "synthetic-password-for-alice", {"dataset-a": ["Cafe"]})
        M.set_account("bob", "synthetic-password-for-bob", {"dataset-b": ["Cafe", "Other"]})

    def test_login_and_scopes(self):
        self.assertIsNone(M.authenticate("alice", "incorrect"))
        self.assertIsNone(M.authenticate("missing", "synthetic-password-for-alice"))
        session = M.authenticate("alice", "synthetic-password-for-alice")
        self.assertTrue(M.permits(session, "dataset-a", ["Cafe"]))
        for dataset, locations in [("dataset-b", ["Cafe"]), ("dataset-a", ["Other"]),
                                   ("dataset-a", ["Cafe", "Other"]), ("dataset-a", []),
                                   ("legacy-name", ["Cafe"])]:
            self.assertFalse(M.permits(session, dataset, locations))
        bob = M.authenticate("bob", "synthetic-password-for-bob")
        self.assertTrue(M.permits(bob, "dataset-b", ["Other"]))
        self.assertFalse(M.permits(bob, "dataset-a", ["Cafe"]))

    def test_expiry_rotation_revocation_and_corruption(self):
        session = M.authenticate("alice", "synthetic-password-for-alice")
        with patch.object(M.time, "time", return_value=session["expires"]):
            self.assertFalse(M.permits(session, "dataset-a", ["Cafe"]))
        M.set_account("alice", "replacement-synthetic-password", {"dataset-a": ["Other"]})
        self.assertFalse(M.permits(session, "dataset-a", ["Cafe"]))
        session = M.authenticate("alice", "replacement-synthetic-password")
        self.assertFalse(M.permits(session, "dataset-a", ["Cafe"]))
        self.assertTrue(M.permits(session, "dataset-a", ["Other"]))
        M.remove_account("alice")
        self.assertFalse(M.permits(session, "dataset-a", ["Other"]))
        M.DB_PATH.write_bytes(b"not sqlite")
        self.assertFalse(M.permits(session, "dataset-a", ["Other"]))

    def test_missing_store_and_legacy_grant_fail_closed(self):
        self.assertFalse(M.permits({"fingerprint": "old-shared-secret"}, "dataset-a", ["Cafe"]))
        with patch.object(M, "DB_PATH", Path(self.temp.name) / "missing"):
            self.assertFalse(M.configured())
            self.assertIsNone(M.authenticate("alice", "synthetic-password-for-alice"))
            self.assertFalse(M.DB_PATH.exists())

    def test_ui_denial_and_live_revocation(self):
        from streamlit.testing.v1 import AppTest
        # Exercise the real report UI with no app filesystem or action history.
        script = '''
import streamlit as st
import pandas as pd
import manager_report_ui as UI
dataset = st.selectbox("Test dataset", ["dataset-a", "dataset-b"])
locations = st.multiselect("Test locations", ["Cafe", "Other"], default=["Cafe"])
UI.show_manager_report([], dataset, locations, pd.DataFrame([]), None, {}, {})
'''
        app = AppTest.from_string(script, default_timeout=30).run()
        app.text_input(key="_manager_username").set_value("alice")
        app.text_input(key="_manager_report_password").set_value("synthetic-password-for-alice")
        next(b for b in app.button if b.label == "Unlock manager report").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.text_area)
        app.selectbox[0].select("dataset-b").run()
        self.assertFalse(app.text_area)
        self.assertFalse(app.get("download_button"))
        app.selectbox[0].select("dataset-a").run()
        app.multiselect[0].set_value(["Cafe", "Other"]).run()
        self.assertFalse(app.text_area)
        app.multiselect[0].set_value(["Cafe"]).run()
        self.assertTrue(app.text_area)
        M.remove_account("alice")
        app.run()
        self.assertFalse(app.exception)
        self.assertFalse(app.text_area)
        self.assertFalse(app.get("download_button"))


if __name__ == "__main__":
    unittest.main()
