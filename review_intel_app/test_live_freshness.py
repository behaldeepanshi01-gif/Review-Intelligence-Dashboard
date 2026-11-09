"""Fast checks for the browser watchdog, including a suspended browser clock."""
from datetime import datetime, timezone
import re
import subprocess
import unittest

from live_freshness import freshness_html


class LiveFreshnessTests(unittest.TestCase):
    def test_timestamp_and_safe_label(self):
        html = freshness_html("<Action>", datetime(2026, 1, 2, tzinfo=timezone.utc))
        self.assertIn("&lt;Action&gt; last updated: 2026-01-02 00:00:00 UTC", html)
        self.assertNotIn("<Action>", html)

    def test_watchdog_requires_new_render_to_recover(self):
        html = freshness_html("Action status", datetime.now(timezone.utc))
        script = re.search(r"<script>(.*?)</script>", html, re.S).group(1)
        harness = """
const assert = require('node:assert/strict');
let wall = 100000, monotonic = 0;
const status = {};
const listeners = {};
global.Date = {now: () => wall};
global.performance = {now: () => monotonic};
Object.defineProperty(global, 'navigator', {value: {onLine: true}});
global.document = {
  getElementById: () => status,
  addEventListener: (name, fn) => listeners[name] = fn
};
global.window = {addEventListener: (name, fn) => listeners[name] = fn};
global.setInterval = fn => listeners.tick = fn;
""" + script + """
assert.match(status.textContent, /Updated recently/);
wall += 75000; // device slept: performance clock did not advance
listeners.visibilitychange();
assert.match(status.textContent, /Updates may be stale/);
assert.match(status.textContent, /Copy unsaved text/);
wall = 100000;
monotonic = 75000; // wall-clock rollback cannot hide staleness
listeners.tick();
assert.match(status.textContent, /Updates may be stale/);
monotonic = 0;
navigator.onLine = false;
listeners.offline();
assert.match(status.textContent, /Updates may be stale/);
navigator.onLine = true;
listeners.online();
assert.match(status.textContent, /Updates may be stale/);
"""
        result = subprocess.run(["node", "-e", harness], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
