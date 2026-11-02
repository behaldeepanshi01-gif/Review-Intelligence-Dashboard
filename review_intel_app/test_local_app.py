"""Browser-free Streamlit script checks using synthetic data only."""

from pathlib import Path
from datetime import date, timedelta
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest
import engine as E
import action_tracker as A


APP = Path(__file__).with_name("app.py")


class LocalAppTests(unittest.TestCase):
    def test_overdue_warning_and_summary_exclude_completed_actions(self):
        sample = E.load_reviews(APP.parent / "data" / "sample_reviews.csv")
        base = {
            "dataset_tag": "sample", "location": sample.iloc[0]["location"],
            "theme": "Service speed", "status": "Planned",
            "start_date": (date.today() - timedelta(days=10)).isoformat(),
            "due_date": (date.today() - timedelta(days=1)).isoformat(),
            "action_text": "Check handoffs.",
        }
        actions = [
            dict(base, action_id="late"),
            dict(base, action_id="done", status="Done", action_text="Finished plan"),
            dict(base, action_id="today", due_date=date.today().isoformat()),
        ]
        with patch.object(E, "load_reviews", return_value=sample), patch.object(
            A, "load_actions", return_value=actions
        ), patch("os.listdir", return_value=[]):
            app = AppTest.from_file(str(APP), default_timeout=30).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(sum("Overdue" in item.value for item in app.warning), 1)
        summary = next(item.value for item in app.code if "Manager actions:" in item.value)
        self.assertEqual(summary.count("OVERDUE"), 1)
        self.assertNotIn("Finished plan", summary)

    def test_default_engine_has_evidence_and_no_ollama_controls(self):
        sample = E.load_reviews(APP.parent / "data" / "sample_reviews.csv")
        with patch.object(E, "load_reviews", return_value=sample), patch(
            "urllib.request.urlopen", side_effect=AssertionError("Network forbidden")
        ):
            app = AppTest.from_file(str(APP), default_timeout=30).run()
        self.assertEqual(len(app.exception), 0)
        engine = next(radio for radio in app.sidebar.radio if radio.label == "Analysis engine")
        self.assertTrue(engine.value.startswith("Local Review Analyzer"))
        self.assertFalse(any("Ollama" in option for option in engine.options))
        self.assertTrue(any(item.label == "Why these tags?" for item in app.expander))
        self.assertTrue(any("Reviews needing manager review" in item.label
                            for item in app.expander))

    def test_no_theme_dataset_renders_without_chart_failure(self):
        df = pd.DataFrame([
            {"location": "Demo Cafe", "review_id": str(index), "reviewer": "Guest",
             "date": pd.Timestamp(f"2026-10-0{index + 1}"), "rating": 3,
             "text": "Visited yesterday."}
            for index in range(2)
        ])
        with patch.object(E, "load_reviews", return_value=df):
            app = AppTest.from_file(str(APP), default_timeout=30).run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any("No clear praise" in info.value for info in app.info))


if __name__ == "__main__":
    unittest.main()
