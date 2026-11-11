"""Clock-controlled expiry checks with synthetic accounts and no real data."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
import manager_identity as identity
import manager_report_access as access


SCRIPT = """
import streamlit as st
from manager_report_access import require_manager, authorized
if not require_manager(purpose="restaurant dashboard"):
    st.stop()
st.text_area("Action draft", key="action_text_fixture")
if st.button("Save action"):
    if authorized("fixture", ["Cafe"]):
        st.session_state["saved_action"] = st.session_state["action_text_fixture"]
        st.success("Saved action")
"""


class SessionExpiryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        db = patch.object(identity, "DB_PATH", Path(directory.name) / "accounts.sqlite")
        db.start()
        self.addCleanup(db.stop)
        self.clock = patch.object(identity.time, "time", return_value=10000).start()
        self.addCleanup(patch.stopall)
        identity.set_account("fixture", "synthetic-fixture-password", {"fixture": ["Cafe"]})
        self.grant = identity.authenticate("fixture", "synthetic-fixture-password")
        self.app = AppTest.from_string(SCRIPT)
        self.app.session_state["_manager_report_grant"] = self.grant.copy()

    def run_at(self, remaining):
        self.clock.return_value = self.grant["expires"] - remaining
        self.app.run()
        self.assertFalse(self.app.exception)

    def test_warning_boundary_preserves_drafts_and_never_renews_session(self):
        self.run_at(301)
        self.assertFalse(self.app.warning)
        self.app.text_area[0].set_value("Unsaved private wording").run()
        self.app.session_state["update_text_hidden_dataset"] = "Hidden retained draft"
        self.run_at(300)
        self.assertIn("Sign-in expires in 5 minutes or less", self.app.warning[0].value)
        self.assertIn("not saved automatically", self.app.warning[0].value)
        self.assertEqual(self.app.text_area[0].value, "Unsaved private wording")
        self.assertEqual(self.app.session_state["update_text_hidden_dataset"], "Hidden retained draft")
        self.run_at(1)
        next(b for b in self.app.button if b.label == "Save action").click().run()
        self.assertEqual(self.app.session_state["saved_action"], "Unsaved private wording")
        self.assertEqual(self.app.session_state["_manager_report_grant"], self.grant)
        self.run_at(0)
        self.assertFalse(self.app.text_area)
        self.assertFalse(self.app.warning)
        self.assertFalse(identity.permits(self.grant, "fixture", ["Cafe"]))
        for key in ["action_text_fixture", "update_text_hidden_dataset", "saved_action",
                    "_manager_report_grant"]:
            self.assertNotIn(key, self.app.session_state)
        self.assertTrue(any("Sign in" in i.value for i in self.app.info))

    def test_revocation_during_warning_clears_private_state(self):
        self.run_at(200)
        self.app.text_area[0].set_value("Private draft").run()
        identity.remove_account("fixture")
        self.run_at(199)
        self.assertFalse(self.app.text_area)
        self.assertNotIn("action_text_fixture", self.app.session_state)

    def test_timer_denial_clears_state_and_requests_full_page_rerun(self):
        # A fragment-only stop would leave the surrounding private UI visible.
        state = {"_manager_report_grant": self.grant, "action_text_fixture": "Private"}
        self.clock.return_value = self.grant["expires"]
        with patch.object(access.st, "session_state", state), \
                patch.object(access.st, "rerun", side_effect=RuntimeError("rerun")) as rerun:
            with self.assertRaisesRegex(RuntimeError, "rerun"):
                access.show_session_expiry.__wrapped__()
            rerun.assert_called_once_with(scope="app")
        self.assertNotIn("action_text_fixture", state)
        self.assertNotIn("_manager_report_grant", state)


if __name__ == "__main__":
    unittest.main()
