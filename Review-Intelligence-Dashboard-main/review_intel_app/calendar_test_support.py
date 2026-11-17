"""Isolated local accounts for calendar regression tests."""
from pathlib import Path
from unittest.mock import patch

import manager_identity as identity


def manager_session(test, directory, grants, *, is_owner=False):
    storage = patch.object(identity, "DB_PATH", Path(directory) / "accounts.sqlite")
    storage.start()
    test.addCleanup(storage.stop)
    identity.set_account("test-manager", "synthetic-calendar-password", grants, is_owner=is_owner)
    return identity.authenticate("test-manager", "synthetic-calendar-password")


def sample_app(app, session=None):
    """Select the sample explicitly, independent of uploads in the workspace."""
    app.session_state["data_source"] = "Sample data (synthetic)"
    if session:
        app.session_state["_manager_report_grant"] = session
    return app.run()
