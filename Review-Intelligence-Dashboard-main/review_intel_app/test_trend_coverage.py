"""Synthetic-only checks for descriptive dashboard coverage."""
import unittest

import pandas as pd
from pandas.testing import assert_frame_equal
from streamlit.testing.v1 import AppTest

import engine as E
from trend_coverage import coverage_tables, warning_windows


def sample(dates, location="Sample"):
    return pd.DataFrame({"location": location, "date": pd.to_datetime(dates),
                         "rating": 4, "themes_neg": [[] for _ in dates]})


class TrendCoverageTests(unittest.TestCase):
    def test_partial_months_empty_month_and_monday_week(self):
        data = sample(["2026-01-31", "2026-03-02"])
        before = data.copy(deep=True)
        obs, months, weeks, gaps = coverage_tables(
            data, data, ["Sample"], ("2026-01-31", "2026-03-02"))
        self.assertEqual(months.reviews.tolist(), [1, 0, 1])
        self.assertTrue(pd.isna(months.iloc[1].avg_rating))
        self.assertIn("Outside observed boundaries", months.iloc[0].context)
        self.assertIn("Date filter cuts month", months.iloc[2].context)
        self.assertIn("2026-02-02", weeks["Week starting Monday"].astype(str).tolist())
        self.assertEqual(gaps.iloc[0]["Days without rows"], 29)
        self.assertEqual(str(obs.iloc[0]["First available date"]), "2026-01-31")
        assert_frame_equal(data, before)
        expected = E.monthly_trend(data)
        actual = months[months.reviews > 0][expected.columns].reset_index(drop=True)
        assert_frame_equal(actual, expected)

    def test_filter_truncation_and_location_without_selected_rows(self):
        data = pd.concat([sample(["2026-01-01", "2026-01-15", "2026-01-31"]),
                          sample(["2026-01-01"], "Other")], ignore_index=True)
        view = data[data.date == pd.Timestamp("2026-01-15")]
        obs, months, _, _ = coverage_tables(
            data, view, ["Sample", "Other"], ("2026-01-10", "2026-01-20"))
        self.assertEqual(obs["Selected rows"].tolist(), [1, 0])
        self.assertIn("Date filter cuts month", months.iloc[0].context)
        self.assertNotIn("Outside observed boundaries", months.iloc[0].context)
        self.assertIn("No records", months.iloc[1].context)

    def test_windows_match_strict_engine_boundaries_all_options(self):
        end = pd.Timestamp("2026-11-03")
        for days in (30, 60, 90):
            with self.subTest(days=days):
                data = sample([end, end - pd.Timedelta(days=days - 1),
                               end - pd.Timedelta(days=days),
                               end - pd.Timedelta(days=4 * days - 1),
                               end - pd.Timedelta(days=4 * days)])
                windows = warning_windows(data, ["Sample", "Empty"], days)
                self.assertEqual(windows["CSV rows (denominator)"].tolist(), [2, 2, 0, 0])
                self.assertEqual(windows.iloc[0]["After (exclusive)"],
                                 end - pd.Timedelta(days=days))
                self.assertIn("comparison unavailable", windows.iloc[2]["Context"])

    def test_shared_anchor_and_three_row_november(self):
        data = pd.concat([sample(["2026-11-01", "2026-11-02", "2026-11-03"]),
                          sample(["2026-08-01"], "Other")], ignore_index=True)
        windows = warning_windows(data, ["Sample", "Other"], 30)
        self.assertEqual(windows["CSV rows (denominator)"].tolist(), [3, 0, 0, 1])
        months = coverage_tables(data, data, ["Sample"], ("2026-11-01", "2026-11-03"))[1]
        self.assertEqual(months.iloc[0].reviews, 3)
        self.assertIn("Few rows", months.iloc[0].context)

    def test_empty_input_windows_and_single_day(self):
        data = sample(["2026-11-03"])
        self.assertTrue(warning_windows(data.iloc[:0], ["Sample"], 30).empty)
        tables = coverage_tables(data, data, ["Sample"], ("2026-11-03", "2026-11-03"))
        self.assertEqual(len(tables[1]), 1)
        self.assertTrue(tables[2].empty)
        self.assertTrue(tables[3].empty)

    def test_read_only_panels_render_with_synthetic_records(self):
        def render():
            import pandas as pd
            from trend_coverage import coverage_tables
            from trend_coverage_ui import show_monthly_coverage, show_warning_coverage
            data = pd.DataFrame({"location": ["Sample", "Sample"],
                                 "date": pd.to_datetime(["2026-01-31", "2026-03-02"]),
                                 "rating": [4, 5]})
            selected = ("2026-01-31", "2026-03-02")
            show_monthly_coverage(coverage_tables(data, data, ["Sample"], selected), selected)
            show_warning_coverage(data, ["Sample"], 30)
        app = AppTest.from_function(render).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe), 5)
        self.assertIn("not complete Google review history", app.warning[0].value)
        self.assertIn("No alert does not prove", app.warning[1].value)


if __name__ == "__main__":
    unittest.main()
