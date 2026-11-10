"""Synthetic upload checks; never read or modify real uploaded reviews."""

import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

import dataset_store as D
import engine as E
from calendar_test_support import manager_session


VALID = b"location,date,rating,text\nDemo,2026-01-02,5,Good\n"
MIXED = (VALID + b"Demo,,4,Undated\nDemo,not-a-date,3,Invalid\n"
         b"Demo,2026-01-03,4,\nDemo, ,4, \n")
UNDATED = b"location,date,rating,text\nDemo,,5,One\nDemo,,4,Two\nDemo,,5,Three\n"
APP = Path(__file__).with_name("app.py")


class ValidationTests(unittest.TestCase):
    def test_counts_overlap_without_counting_a_row_twice(self):
        accepted, report = E.preview_reviews(io.BytesIO(MIXED))
        self.assertEqual(report, {
            "total": 5, "accepted": 1, "rejected": 4,
            "reasons": {"Missing date": 2, "Invalid date": 1, "Missing review text": 2},
            "rejected_rows": [
                {"source_row": 3, "rejection_reasons": "Missing date"},
                {"source_row": 4, "rejection_reasons": "Invalid date"},
                {"source_row": 5, "rejection_reasons": "Missing review text"},
                {"source_row": 6, "rejection_reasons": "Missing date; Missing review text"},
            ],
        })
        self.assertEqual(accepted["text"].tolist(), ["Good"])
        pd.testing.assert_frame_equal(accepted, E.load_reviews(io.BytesIO(MIXED)))

    def test_report_uses_source_record_order_with_multiline_csv(self):
        content = (
            b'location,date,rating,text\r\n'
            b'Demo,2026-02-01,5,"Private first line\r\nsecond, ""quoted"" line"\r\n'
            b'\r\n'
            b'Demo,,4,"Private undated\r\ncontinued"\r\n'
            b'Demo,invalid,3," \r\n "\r\n'
            b'Demo,2026-01-01,5,Private earlier review\r\n'
            b'Demo,,4,\r\n'
        )
        stream = io.BytesIO(content)
        accepted, validation = E.preview_reviews(stream)
        self.assertEqual(stream.getvalue(), content)
        self.assertEqual(validation["total"], 5)
        self.assertEqual(validation["rejected"], 3)
        exported = E.validation_report_csv(validation)
        report = pd.read_csv(io.BytesIO(exported))
        self.assertEqual(report.source_row.tolist(), [3, 4, 6])
        self.assertEqual(report.rejection_reasons.tolist(), [
            "Missing date", "Invalid date; Missing review text",
            "Missing date; Missing review text",
        ])
        self.assertNotIn(b"Private", exported)
        self.assertNotIn(b"Demo", exported)
        self.assertEqual(accepted.date.dt.month.tolist(), [1, 2])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.csv"
            path.write_bytes(content)
            self.assertEqual(E.preview_reviews(path)[1], validation)
            self.assertEqual(path.read_bytes(), content)

    def test_clean_and_header_only_reports_have_stable_headers(self):
        for content in (VALID, VALID.splitlines()[0] + b"\n"):
            _, validation = E.preview_reviews(io.BytesIO(content))
            self.assertEqual(E.validation_report_csv(validation),
                             b"source_row,rejection_reasons\n")

    def test_all_undated_and_empty_csv_are_empty_not_retrieval_dated(self):
        for content, total in [(UNDATED, 3), (VALID.splitlines()[0] + b"\n", 0)]:
            accepted, report = E.preview_reviews(io.BytesIO(content))
            self.assertTrue(accepted.empty)
            self.assertEqual(report["accepted"], 0)
            self.assertEqual(report["rejected"], total)

    def test_mixed_date_formats_and_bad_schema(self):
        content = VALID + b"Demo,01/03/2026,4,Also good\n"
        accepted, report = E.preview_reviews(io.BytesIO(content))
        self.assertEqual(report["accepted"], 2)
        self.assertEqual(accepted.date.dt.day.tolist(), [2, 3])
        with self.assertRaisesRegex(ValueError, "missing columns"):
            E.preview_reviews(io.BytesIO(b"text\nHello\n"))

    def test_offsets_preserve_publication_day_at_month_and_year_boundaries(self):
        content = (VALID
                   + b"Demo,2026-01-01 00:30+05:30,5,January\n"
                   + b"Demo,2026-01-31 23:30-08:00,5,Still January\n")
        accepted, report = E.preview_reviews(io.BytesIO(content))
        self.assertEqual(report["accepted"], 3)
        self.assertEqual(accepted.date.dt.strftime("%Y-%m-%d").tolist(),
                         ["2026-01-01", "2026-01-02", "2026-01-31"])
        self.assertIsNone(accepted.date.dt.tz)


class UploadUITests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = D.DatasetStore(self.directory.name, APP.parent / "data/sample_reviews.csv")
        self.existing = self.store.save_snapshot("existing.csv", VALID)
        self.session = manager_session(
            self, self.directory.name, {self.existing["dataset_id"]: ["Demo"]})
        # Run the actual upload section, stopping before unrelated dashboard analysis.
        source = APP.read_text().split('data_path, tag = dataset["path"]')[0]
        self.source = f"__file__ = {str(APP)!r}\n" + source + "\nst.stop()\n"
        self.content = MIXED
        self.upload = io.BytesIO(self.content)
        self.upload.name = "synthetic.csv"
        self.upload.file_id = "synthetic-file"
        for p in [
            patch.object(D, "DatasetStore", return_value=self.store),
            patch("streamlit.delta_generator.DeltaGenerator.file_uploader",
                  side_effect=lambda *args, **kwargs: self.upload),
            patch("legacy_history_ui.show_live_history_notice"),
        ]:
            p.start()
            self.addCleanup(p.stop)

    def open_app(self):
        app = AppTest.from_string(self.source, default_timeout=30)
        app.session_state["_manager_report_grant"] = self.session
        app.session_state["data_source"] = "Upload my reviews (CSV)"
        app.run()
        self.assertFalse(app.exception)
        next(r for r in app.radio if r.label == "Upload purpose").set_value(
            "Update an existing dataset").run()
        return app

    def assert_unchanged(self):
        self.assertEqual(self.store.get(self.existing["dataset_id"]), self.existing)
        self.assertEqual(Path(self.existing["path"]).read_bytes(), VALID)
        self.assertEqual(len(list(Path(self.directory.name).rglob("*.csv"))), 1)

    def test_preview_and_cancel_leave_existing_snapshot_unchanged(self):
        app = self.open_app()
        self.assertTrue(any("Accepted: 1 · Rejected: 4" in x.value for x in app.markdown))
        self.assertTrue(any(b.label == "Download validation report"
                            for b in app.get("download_button")))
        self.assertFalse(any("Undated" in x.value or "Good" in x.value
                             for x in app.markdown))
        self.assert_unchanged()
        next(b for b in app.button if b.label == "Cancel upload").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["data_source"], "Saved file")
        self.assertEqual(app.session_state["upload_generation"], 1)
        self.assert_unchanged()

    def test_confirm_preserves_raw_bytes_and_old_snapshot(self):
        app = self.open_app()
        next(b for b in app.button if b.label == "Save CSV").click().run()
        self.assertFalse(app.exception)
        current = self.store.get(self.existing["dataset_id"])
        self.assertNotEqual(current["path"], self.existing["path"])
        self.assertEqual(Path(current["path"]).read_bytes(), MIXED)
        self.assertEqual(Path(self.existing["path"]).read_bytes(), VALID)
        self.assertEqual(len(E.load_reviews(current["path"])), 1)

    def test_all_undated_cannot_replace_existing_dataset(self):
        self.upload = io.BytesIO(UNDATED)
        self.upload.name, self.upload.file_id = "undated.csv", "undated"
        app = self.open_app()
        self.assertTrue(next(b for b in app.button if b.label == "Save CSV").disabled)
        self.assertTrue(any("No reviews are eligible" in x.value for x in app.warning))
        self.assertTrue(any(b.label == "Download validation report"
                            for b in app.get("download_button")))
        self.assert_unchanged()

    def test_invalid_schema_cannot_save(self):
        self.upload = io.BytesIO(b"text\nHello\n")
        self.upload.name, self.upload.file_id = "invalid.csv", "invalid"
        app = self.open_app()
        self.assertTrue(any("missing columns" in x.value for x in app.error))
        self.assertFalse(any(b.label == "Save CSV" for b in app.button))
        self.assert_unchanged()


if __name__ == "__main__":
    unittest.main()
