"""Regression checks for the isolation boundary, not substitutes for races."""

import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from process_test_support import isolated_process_test


class ProcessTestSupportTests(unittest.TestCase):
    @isolated_process_test
    def isolated_probe(self):
        # This is also selectable by its explicit unittest name in the child.
        import multiprocessing
        context = multiprocessing.get_context("spawn")
        with context.Manager() as manager:
            self.assertEqual(list(manager.list(["spawned"])), ["spawned"])

    def test_spawn_after_apptest_and_another_rerun(self):
        original_main = sys.modules["__main__"]
        self.addCleanup(sys.modules.__setitem__, "__main__", original_main)
        app = AppTest.from_string("import streamlit as st\nst.write('Synthetic')")
        for _ in range(2):
            app.run()
            self.assertFalse(app.exception)
            app_main = sys.modules["__main__"]
            self.isolated_probe()
            self.assertIs(sys.modules["__main__"], app_main)

    def test_child_failures_are_not_hidden(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "process_test_support.subprocess.run",
            return_value=subprocess.CompletedProcess([], 1, "", "AssertionError: sentinel"),
        ):
            with self.assertRaisesRegex(AssertionError, "AssertionError: sentinel"):
                self.isolated_probe()

    def test_child_timeout_is_a_test_failure(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "process_test_support.subprocess.run",
            side_effect=subprocess.TimeoutExpired("unittest", 180),
        ):
            with self.assertRaisesRegex(AssertionError, "Isolated test timed out"):
                self.isolated_probe()


if __name__ == "__main__":
    unittest.main()
