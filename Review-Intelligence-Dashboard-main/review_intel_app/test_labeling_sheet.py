"""Synthetic-only checks of blind selection and safe private sheet generation."""

import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

import labeling_sheet as L


def synthetic_reviews():
    rows = []
    for location in ("Demo North", "Demo South"):
        for rating in (1, 3, 5):
            for number in range(5):
                rows.append({
                    "location": location, "rating": rating, "reviewer": "Fictional Guest",
                    "review_id": f"{location}-{rating}-{number}", "date": "2026-10-01",
                    "text": f"Fictional Guest: nice food. Sample {location} {rating} {number}.",
                })
    return pd.DataFrame(rows)


class LabelingSheetTests(unittest.TestCase):
    def test_selection_is_balanced_reproducible_and_does_not_mutate_input(self):
        data = synthetic_reviews()
        selected = L.choose_sample(data, count=12)
        self.assertEqual(selected.review_id.tolist(), L.choose_sample(data, 12).review_id.tolist())
        self.assertEqual(selected.groupby(["location", "rating"]).size().tolist(), [2] * 6)
        self.assertNotIn("_text_key", data.columns)
        self.assertEqual(len(data), 30)

    def test_duplicate_text_does_not_enter_twice(self):
        data = synthetic_reviews()
        data.loc[1, "text"] = data.loc[0, "text"].upper()
        selected = L.choose_sample(data, count=29)
        self.assertEqual(selected.text.str.casefold().nunique(), 29)
        with self.assertRaises(ValueError):
            L.choose_sample(data, count=30)

    def test_spreadsheet_formulas_are_escaped_and_reviewer_removed(self):
        for text in ("=1+1", "+2", "-2", "@SUM(A1)", "  =3"):
            self.assertTrue(L.spreadsheet_text(text).startswith("'"))
        self.assertEqual(L.spreadsheet_text("Great food"), "Great food")
        text = L.remove_reviewer_identity("Fictional Guest: nice food.", "Fictional Guest")
        self.assertNotIn("Fictional Guest", text)
        self.assertIn("nice food", text)

    def test_sample_size_and_batch_are_checked(self):
        for count in (0, -1, 100):
            with self.assertRaises(ValueError):
                L.choose_sample(synthetic_reviews(), count=count)
        with self.assertRaises(ValueError):
            L.prepare_sheet("unused.csv", "../escape")

    def test_private_outputs_have_blank_labels_and_frozen_predictions_without_text(self):
        L.PRIVATE_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=L.PRIVATE_ROOT) as folder:
            root = Path(folder)
            source = root / "synthetic.csv"
            synthetic_reviews().to_csv(source, index=False)
            source_before = source.read_bytes()
            with patch("urllib.request.urlopen", side_effect=AssertionError("No network")):
                destination, counts = L.prepare_sheet(
                    source, "test_batch", count=12, private_root=root
                )
            self.assertEqual(counts["sample_reviews"], 12)
            self.assertEqual(source.read_bytes(), source_before)
            with (destination / "labeling_sheet.csv").open(encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 12)
            self.assertEqual(set(rows[0]), set(L.HEADERS))
            for row in rows:
                self.assertNotIn("Fictional Guest", row["review_text"])
                self.assertTrue(all(row[label] == "" for label in L.E.THEME_LABELS.values()))
                self.assertEqual(row["human_checked"], "")
            for hidden in ("rating", "location", "reviewer", "prediction", "needs_review"):
                self.assertNotIn(hidden, rows[0])
            snapshot_text = (destination / "frozen_predictions.json").read_text()
            snapshot = json.loads(snapshot_text)
            self.assertEqual(snapshot["status"], "awaiting_human_labels")
            self.assertEqual(len(snapshot["reviews"]), 12)
            self.assertNotIn("nice food", snapshot_text)
            self.assertNotIn("Fictional Guest", snapshot_text)
            self.assertTrue(snapshot["code_sha256"]["local_analyzer.py"])
            before = (destination / "labeling_sheet.csv").read_bytes()
            with self.assertRaises(ValueError):
                L.prepare_sheet(source, "test_batch", count=12, private_root=root)
            self.assertEqual((destination / "labeling_sheet.csv").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
