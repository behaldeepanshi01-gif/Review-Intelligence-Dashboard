"""Real startup/HTTP/WebSocket regression, with no workspace accounts or data.

Run: uv run python -m unittest discover -s review_intel_app -p test_dashboard_server.py -v
The launcher and report UI are production code; only the dashboard's input script
is replaced with a tiny synthetic report fixture. No test endpoint is installed.
"""
import asyncio
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from unittest.mock import patch

import manager_identity as identity
from streamlit.proto.BackMsg_pb2 import BackMsg
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
from websockets.asyncio.client import connect


PASSWORD = "synthetic-server-test-password"
FIXTURE = '''
import streamlit as st
import pandas as pd
import manager_identity as identity
from manager_report_ui import show_manager_report

if "_manager_report_grant" not in st.session_state:
    st.session_state["_manager_report_grant"] = identity.authenticate(
        "synthetic-manager", "synthetic-server-test-password")
actions = [dict(dataset_tag="synthetic-dataset", location="Synthetic Cafe",
    theme="Speed", theme_key="service_speed", action_text="SYNTHETIC PRIVATE ACTION",
    owner="Shift lead", status="Planned", start_date="2026-01-01",
    due_date="2026-01-03")]
reviews = pd.DataFrame([dict(location="Synthetic Cafe", date="2026-01-02",
    rating=4, text="Synthetic review only", reviewer="FixtureGuestperson",
    themes_neg=[])])
show_manager_report(actions, "synthetic-dataset", ["Synthetic Cafe"], reviews,
    None, {}, {})
'''


class DashboardServerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="dashboard-server-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        # Copy code only. In particular, never copy data/, accounts, or histories.
        source = Path(__file__).resolve().parent
        for path in source.glob("*.py"):
            if not path.name.startswith("test_"):
                shutil.copy2(path, self.root / path.name)
        (self.root / "app.py").write_text(FIXTURE)
        with patch.object(identity, "DB_PATH", self.root / "data/manager_accounts.sqlite"):
            for user in ("synthetic-manager", "synthetic-other"):
                identity.set_account(user, PASSWORD, {"synthetic-dataset": ["Synthetic Cafe"]})
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            self.port = listener.getsockname()[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self.process = None
        self.log = (self.root / "server.log").open("w+")
        self.addCleanup(self.log.close)
        self.addCleanup(self.stop_server)
        self.start_server()

    def diagnostics(self):
        self.log.flush()
        return (self.root / "server.log").read_text()

    def start_server(self):
        # Do not pass inherited secrets, Streamlit settings, or workspace paths.
        env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT") if key in os.environ}
        env.update(PORT=str(self.port), HOME=str(self.root), PYTHONUNBUFFERED="1",
                   PYTHONDONTWRITEBYTECODE="1")
        self.process = subprocess.Popen(
            [sys.executable, str(self.root / "serve_dashboard.py")],
            cwd=self.root, env=env, stdout=self.log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                self.fail("Dashboard exited during startup:\n" + self.diagnostics())
            try:
                status, _, body = self.http("/dashboard/_stcore/health")
                if status == 200 and body == b"ok":
                    return
            except (URLError, TimeoutError, ConnectionError):
                pass
            time.sleep(0.1)
        self.fail("Dashboard did not become healthy:\n" + self.diagnostics())

    def stop_server(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
            self.process = None

    def http(self, path, fields=None):
        request = Request(self.base + path,
                          data=None if fields is None else urlencode(fields).encode())
        try:
            response = urlopen(request, timeout=3)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, response.read()

    async def render(self, ws, widgets=()):
        message = BackMsg()
        message.rerun_script.SetInParent()
        for widget_id, value in widgets:
            widget = message.rerun_script.widget_states.widgets.add()
            widget.id = widget_id
            field = "trigger_value" if widget_id.startswith("button:") else "bool_value"
            # The prefix is test metadata, not part of the Streamlit widget ID.
            if field == "trigger_value":
                widget.id = widget_id.removeprefix("button:")
            setattr(widget, field, value)
        await ws.send(message.SerializeToString())
        elements = []
        async with asyncio.timeout(30):
            while True:
                raw = await ws.recv()
                self.assertIsInstance(raw, bytes)
                message = ForwardMsg.FromString(raw)
                if message.HasField("delta") and message.delta.HasField("new_element"):
                    element = message.delta.new_element
                    self.assertFalse(element.HasField("exception"), str(element))
                    self.assertFalse(element.HasField("download_button"), str(element))
                    elements.append(element)
                if message.HasField("script_finished"):
                    return elements

    async def prepare(self, ws):
        elements = await self.render(ws)
        checkbox = next(e.checkbox for e in elements if e.HasField("checkbox"))
        elements = await self.render(ws, [(checkbox.id, True)])
        button = next(e.button for e in elements if e.HasField("button")
                      and e.button.label == "Prepare secure report download")
        self.assertFalse(button.disabled)
        elements = await self.render(ws, [(checkbox.id, True), ("button:" + button.id, True)])
        # A public st.download_button must never replace protected report delivery.
        self.assertFalse(any(e.HasField("download_button") for e in elements))
        link = next(e.link_button for e in elements if e.HasField("link_button")
                    and e.link_button.label == "Download manager action report (TXT)")
        self.assertTrue(link.url.startswith("/dashboard/report-download/"), link.url)
        self.assertFalse(urlsplit(link.url).netloc)
        return link.url

    def assert_private(self, response, status):
        code, headers, body = response
        self.assertEqual(code, status, body)
        self.assertIn("no-store", headers["Cache-Control"])
        self.assertNotIn(b"SYNTHETIC PRIVATE ACTION", body)

    def test_real_launcher_mounts_routes_and_restart_discards_links(self):
        credentials = {"username": "synthetic-manager", "password": PASSWORD}

        async def before_restart():
            async with connect(
                f"ws://127.0.0.1:{self.port}/dashboard/_stcore/stream",
                origin=self.base, subprotocols=["streamlit"], open_timeout=5,
            ) as ws:
                self.assertEqual(ws.subprotocol, "streamlit")
                link = await self.prepare(ws)
                self.assert_private(self.http(link), 200)
                self.assert_private(self.http(link, {}), 403)
                self.assert_private(self.http(link, dict(credentials, password="wrong")), 403)
                self.assert_private(self.http(link, dict(
                    credentials, username="synthetic-other")), 403)
                # Public media cannot fetch the pending protected report.
                token = link.rsplit("/", 1)[1]
                media = self.http(f"/dashboard/media/{token}.txt")
                self.assertEqual(media[0], 404)
                self.assertNotIn(b"SYNTHETIC PRIVATE ACTION", media[2])
                status, headers, body = self.http(link, credentials)
                self.assertEqual(status, 200, body)
                self.assertIn(b"SYNTHETIC PRIVATE ACTION", body)
                self.assertIn("attachment", headers["Content-Disposition"])
                self.assertIn("no-store", headers["Cache-Control"])
                self.assert_private(self.http(link, credentials), 403)
                pending = await self.prepare(ws)
                self.assertNotEqual(link, pending)
                self.assert_private(self.http(pending), 200)
                return pending

        pending = asyncio.run(before_restart())
        self.stop_server()
        self.start_server()
        # Same port, account database and correct credentials; only process memory
        # changed. The old link must not survive or accidentally return app HTML.
        self.assert_private(self.http(pending), 403)
        self.assert_private(self.http(pending, credentials), 403)

        async def after_restart():
            async with connect(
                f"ws://127.0.0.1:{self.port}/dashboard/_stcore/stream",
                origin=self.base, subprotocols=["streamlit"], open_timeout=5,
            ) as ws:
                link = await self.prepare(ws)
                self.assertNotEqual(link, pending)
                status, _, body = self.http(link, credentials)
                self.assertEqual(status, 200, body)
                self.assertIn(b"SYNTHETIC PRIVATE ACTION", body)

        asyncio.run(after_restart())


if __name__ == "__main__":
    unittest.main()
