"""Real HTTP handler checks with synthetic reports and isolated account storage."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlencode
from unittest.mock import patch

from starlette.requests import Request
import manager_identity as M
import report_downloads as D


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patcher = patch.object(M, "DB_PATH", Path(self.temp.name) / "accounts.sqlite")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.password = "synthetic-password-only"
        for username in ("alice", "bob"):
            M.set_account(username, self.password, {"dataset-a": ["Cafe"]})
        self.grant = M.authenticate("alice", self.password)
        D._reports.clear()
        D._attempts.clear()
        self.addCleanup(D._reports.clear)

    def issue(self):
        return D.issue(self.grant, "dataset-a", ["Cafe"], "SYNTHETIC PRIVATE REPORT",
                       acknowledged=True)

    def request(self, token, method="GET", username="alice", password=None):
        body = urlencode({"username": username, "password": password or self.password}).encode()
        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}
        request = Request({
            "type": "http", "method": method, "path": "/dashboard/report-download/" + token,
            "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
            "path_params": {"token": token},
        }, receive)
        return asyncio.run(D.download(request))

    def test_copied_link_requires_credentials_and_same_manager(self):
        token = self.issue()
        response = self.request(token)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"SYNTHETIC PRIVATE REPORT", response.body)
        self.assertIn("no-store", response.headers["cache-control"])
        self.assertEqual(self.request(token, "POST", password="wrong").status_code, 403)
        # Bob deliberately has the SAME grants; identity binding still denies him.
        self.assertEqual(self.request(token, "POST", username="bob").status_code, 403)
        result = self.request(token, "POST")
        self.assertEqual(result.body, b"SYNTHETIC PRIVATE REPORT")
        self.assertIn("attachment", result.headers["content-disposition"])
        self.assertIn("no-store", result.headers["cache-control"])
        self.assertEqual(self.request(token, "POST").status_code, 403)

    def test_logout_revokes_but_does_not_recall_delivered_bytes(self):
        delivered = self.request(self.issue(), "POST").body
        token = self.issue()
        D.revoke(self.grant)
        self.assertEqual(self.request(token, "POST").status_code, 403)
        self.assertEqual(delivered, b"SYNTHETIC PRIVATE REPORT")

    def test_grant_replacement_and_account_removal(self):
        token = self.issue()
        M.set_account("alice", self.password, {"dataset-a": ["Other"]})
        self.assertEqual(self.request(token, "POST").status_code, 403)
        M.set_account("alice", self.password, {"dataset-a": ["Cafe"]})
        self.grant = M.authenticate("alice", self.password)
        token = self.issue()
        M.remove_account("alice")
        self.assertEqual(self.request(token, "POST").status_code, 403)

    def test_link_and_original_login_expire(self):
        token = self.issue()
        with patch.object(D.time, "time", return_value=D._reports[token]["expires"]):
            self.assertEqual(self.request(token, "POST").status_code, 403)
        self.grant["expires"] = D.time.time() + 1
        token = self.issue()
        with patch.object(D.time, "time", return_value=self.grant["expires"]):
            self.assertEqual(self.request(token, "POST").status_code, 403)

    def test_logout_during_reauthentication(self):
        token = self.issue()
        authenticate = M.authenticate
        def interleave(username, password):
            result = authenticate(username, password)
            D.revoke(self.grant)
            return result
        with patch.object(M, "authenticate", side_effect=interleave):
            self.assertEqual(self.request(token, "POST").status_code, 403)

    def test_privacy_scope_size_and_rate_limits(self):
        for dataset, locations, ack in [
                ("dataset-a", ["Cafe"], False), ("dataset-b", ["Cafe"], True),
                ("dataset-a", ["Cafe", "Other"], True)]:
            with self.assertRaises(PermissionError):
                D.issue(self.grant, dataset, locations, "private", acknowledged=ack)
        with self.assertRaises(ValueError):
            D.issue(self.grant, "dataset-a", ["Cafe"], "x" * (D.MAX_REPORT_BYTES + 1),
                    acknowledged=True)
        token = self.issue()
        for _ in range(10):
            self.assertEqual(self.request(token, "POST", password="bad").status_code, 403)
        self.assertEqual(self.request(token, "POST").status_code, 403)


if __name__ == "__main__":
    unittest.main()
