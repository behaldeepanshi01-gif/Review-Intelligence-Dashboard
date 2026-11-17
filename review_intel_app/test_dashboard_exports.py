"""Synthetic export checks through the real protected HTTP handler and UI."""
import io
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import manager_identity as M
import report_downloads as D
import test_report_downloads


class CsvExportTests(test_report_downloads.DownloadTests):
    # Exercise copied links, logout, edits/removal, both expiries, racing logout,
    # and exact scope against CSV payloads as well as the existing TXT report.
    def issue(self):
        return D.issue(self.grant, "dataset-a", ["Cafe"], b"SYNTHETIC PRIVATE REPORT",
                       acknowledged=True, filename="analyzed_reviews.csv", media_type="text/csv")

    def test_csv_headers_and_exact_bytes(self):
        payload = 'location,text\nCafe,"café, one\nsecond line"\n'.encode()
        token = D.issue(self.grant, "dataset-a", ["Cafe"], payload, acknowledged=True,
                        filename="original.csv", media_type="text/csv")
        response = self.request(token, "POST")
        self.assertEqual(response.body, payload)
        self.assertEqual(response.headers["content-disposition"],
                         'attachment; filename="original.csv"')
        self.assertIn("text/csv", response.headers["content-type"])

    def test_password_edit_with_same_permissions_revokes_link(self):
        token = self.issue()
        new_password = "new-synthetic-password"
        M.set_account("alice", new_password, {"dataset-a": ["Cafe"]})
        self.assertEqual(self.request(token, "POST", password=new_password).status_code, 403)

    def test_scope_is_exact_and_rechecked_during_authentication(self):
        for dataset, locations in [
            ("dataset-b", ["Cafe"]), ("dataset-a", ["cafe"]),
            ("dataset-a", ["Cafe", "Other"]), ("dataset-a", []),
        ]:
            with self.assertRaises(PermissionError):
                D.issue(self.grant, dataset, locations, "private", acknowledged=True)
        token = self.issue()
        authenticate = M.authenticate
        def interleave(username, password):
            fresh = authenticate(username, password)
            M.set_account("alice", password, {"dataset-a": ["Other"]})
            return fresh
        with patch.object(M, "authenticate", side_effect=interleave):
            self.assertEqual(self.request(token, "POST").status_code, 403)

    def test_other_formats_and_preparing_replaces_previous_link(self):
        for filename, mime in [("weekly_owner_summary.txt", "text/plain"),
                               ("weekly_owner_summary.html", "text/html"),
                               ("unsaved-action-draft.json", "application/json"),
                               ("upload_validation_report.csv", "text/csv"),
                               ("early_warnings.csv", "text/csv")]:
            with self.subTest(filename=filename):
                previous = self.issue()
                token = D.issue(self.grant, "dataset-a", ["Cafe"], "synthetic",
                                acknowledged=True, filename=filename, media_type=mime)
                self.assertEqual(self.request(previous, "POST").status_code, 403)
                response = self.request(token, "POST")
                self.assertEqual(response.body, b"synthetic")
                self.assertIn(filename, response.headers["content-disposition"])
                self.assertIn(mime, response.headers["content-type"])

    def test_public_downloads_are_not_used_in_dashboard(self):
        self.assertNotIn("st.download_button", Path(__file__).with_name("app.py").read_text())


import unittest
import test_local_app


class ExportUiTests(unittest.TestCase):
    setUp = test_local_app.LocalAppTests.setUp
    open_app = test_local_app.LocalAppTests.open_app

    def test_filtered_reviews_are_delivered_only_after_acknowledgment(self):
        app = self.open_app()
        locations = next(w for w in app.multiselect if w.label == "Locations")
        chosen = locations.value[0]
        locations.set_value([chosen]).run()
        date_range = next(w for w in app.slider if w.label == "Date range")
        low, high = date_range.value
        from datetime import timedelta
        low = high - timedelta(days=30)
        date_range.set_value((low, high)).run()
        label = "Prepare secure export: Download analyzed reviews (CSV)"
        self.assertTrue(next(b for b in app.button if b.label == label).disabled)
        next(c for c in app.checkbox if c.label.startswith("I checked analyzed_reviews.csv")).check().run()
        with patch.object(D, "issue", wraps=D.issue) as issued:
            next(b for b in app.button if b.label == label).click().run()
        self.assertFalse(app.exception)
        args = issued.call_args
        self.assertEqual(args.args[2], [chosen])
        frame = pd.read_csv(io.BytesIO(args.args[3]))
        self.assertEqual(set(frame.location), {chosen})
        dates = pd.to_datetime(frame.date).dt.date
        self.assertTrue(((dates >= low) & (dates <= high)).all())
        self.assertFalse(app.get("download_button"))
        self.assertTrue(any("/dashboard/report-download/" in b.url
                            for b in app.get("link_button")))
        self.assertTrue(any("cannot be recalled" in c.value for c in app.caption))

        # Printable Weekly Owner Summary (HTML) sits alongside weekly_owner_summary.txt
        # and reuses the same acknowledgment gate and /dashboard/report-download/ flow.
        txt_label = "Prepare secure export: Download weekly owner summary (TXT)"
        html_label = "Prepare secure export: Download printable weekly owner summary (HTML)"
        self.assertTrue(any(b.label == txt_label for b in app.button))
        self.assertTrue(next(b for b in app.button if b.label == html_label).disabled)
        next(c for c in app.checkbox if c.label.startswith("I checked weekly_owner_summary.html")).check().run()
        with patch.object(D, "issue", wraps=D.issue) as issued_html:
            next(b for b in app.button if b.label == html_label).click().run()
        self.assertFalse(app.exception)
        html_args = issued_html.call_args
        self.assertEqual(html_args.args[2], [chosen])
        self.assertEqual(html_args.kwargs["filename"], "weekly_owner_summary.html")
        self.assertEqual(html_args.kwargs["media_type"], "text/html")
        html_text = html_args.args[3].decode("utf-8")
        self.assertIn("WEEKLY OWNER SUMMARY", html_text)
        self.assertIn("@media print", html_text)
        self.assertIn("@page", html_text)
        self.assertIn(chosen, html_text)
        self.assertIn("Review trends do not prove an action caused a change.", html_text)
        self.assertTrue(any(
            b.label == "Download printable weekly owner summary (HTML)"
            and "/dashboard/report-download/" in b.url
            for b in app.get("link_button")
        ))
        self.assertFalse(app.get("download_button"))


if __name__ == "__main__":
    unittest.main()
