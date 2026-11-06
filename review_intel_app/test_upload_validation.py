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
        })
        self.assertEqual(accepted["text"].tolist(), ["Good"])
        pd.testing.assert_frame_equal(accepted, E.load_reviews(io.BytesIO(MIXED)))

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
