"""Synthetic-only checks for the private coverage audit, not the analyzer."""
import csv
from datetime import date
from pathlib import Path
import tempfile
import unittest

from audit_source_coverage import ROOT, audit


class CoverageAuditTests(unittest.TestCase):
    def run_audit(self, rows):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            path = Path(folder) / "synthetic.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["location", "date", "rating", "text", "review_id"])
                writer.writerows(rows)
            before = path.read_bytes()
            result = audit(path, date(2026, 11, 6))
            self.assertEqual(path.read_bytes(), before)
            return result

    def test_missing_invalid_dates_and_ratings_are_not_repaired(self):
        result = self.run_audit([
            ["Sample", "", "", "", ""],
            ["Sample", "2026-02-30", "6", "Example", "1"],
            ["Sample", "03/04/2026", "2.5", "Other", "2"],
            ["Sample", "2026-11-07", "NaN", "Future", "3"],
        ])
        self.assertEqual(result["missing_by_column"]["date"], 1)
        self.assertEqual(result["invalid_nonblank_dates"], 2)
        self.assertEqual(result["invalid_nonblank_ratings"], 3)
        self.assertEqual(result["future_dates_relative_to_as_of"], 1)
        self.assertEqual(result["coverage"]["valid_dates"], 1)

    def test_duplicate_definitions_and_empty_months(self):
        result = self.run_audit([
            ["Sample", "2026-01-31", "5", "Good food", "1"],
            ["Sample", "2026-01-31", "5", "Good food", "1"],
            ["Sample", "2026-03-02", "5", " good   FOOD ", "2"],
        ])
        self.assertEqual(result["duplicates"]["exact_rows"]["excess_rows"], 1)
        self.assertEqual(result["duplicates"]["nonblank_review_ids"]["groups"], 1)
        self.assertEqual(result["duplicates"]["normalized_text"]["excess_rows"], 2)
        self.assertEqual(result["coverage"]["monthly_rows"]["2026-02"], 0)
        self.assertEqual(result["coverage"]["largest_internal_empty_run_days"], 29)
        self.assertEqual(result["coverage"]["days_without_records_inside_span"], 29)

    def test_window_boundaries_match_engine_strict_lower_bound(self):
        result = self.run_audit([
            ["Sample", d, "5", f"Example {i}", str(i)]
            for i, d in enumerate(["2026-11-01", "2026-10-03", "2026-10-02",
                                    "2026-07-05", "2026-07-04"])
        ])
        windows = result["coverage"]["latest_date_anchored_windows"]
        self.assertEqual(windows["recent_30_rows"], 2)
        self.assertEqual(windows["prior_90_rows"], 2)

    def test_all_undated_stays_undated(self):
        result = self.run_audit([["Sample", "", "5", "Example", "1"]])
        self.assertIsNone(result["coverage"])


if __name__ == "__main__":
    unittest.main()
