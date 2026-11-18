"""Tests for inline supporting review evidence on Early warning cards and walkthrough cues."""
from pathlib import Path
import unittest

import pandas as pd

import alert_evidence_ui as AE
import demo_data_boundary as B
import engine as E


APP_DIR = Path(__file__).resolve().parent
DEMO_DIR = APP_DIR.parent / "artifacts" / "review-intelligence-demo"


class AlertEvidenceTests(unittest.TestCase):
    def test_matches_early_warnings_counts_on_synthetic_sample(self):
        df = E.load_reviews(APP_DIR / "data" / "sample_reviews.csv")
        tagged = E.analyze_offline(df)
        alerts = E.early_warnings(tagged, recent_days=30)
        self.assertFalse(alerts.empty)

        original_columns = list(tagged.columns)
        original_len = len(tagged)
        for alert in alerts.to_dict("records"):
            rows = AE.supporting_alert_reviews(
                tagged, alert["location"], alert["theme"], recent_days=30
            )
            self.assertEqual(len(rows), int(alert["recent_mentions"]))
            self.assertTrue(all(r["location"] == alert["location"] for r in rows))
            # Sorted newest first
            dates = [r["date"] for r in rows]
            self.assertEqual(dates, sorted(dates, reverse=True))
        # Input DataFrame untouched
        self.assertEqual(list(tagged.columns), original_columns)
        self.assertEqual(len(tagged), original_len)

    def test_window_location_theme_and_manager_tag_scoping(self):
        df = pd.DataFrame([
            {
                "review_id": "r-recent-1", "location": "Cafe",
                "date": pd.Timestamp("2026-10-30"), "rating": 2,
                "reviewer": "Private Guest One",
                "text": "Service was slow and took forever for entrees.",
                "themes_neg": ["service_speed"], "themes_pos": [],
                "tag_evidence": [{
                    "theme": "service_speed", "polarity": "Complaint",
                    "matched_terms": ["slow", "forever"],
                    "excerpt": "Service was slow and took forever for entrees",
                }],
                "tag_source": "local",
            },
            {
                "review_id": "r-recent-mgr", "location": "Cafe",
                "date": pd.Timestamp("2026-10-28"), "rating": 3,
                "reviewer": "Private Guest Two",
                "text": "Waited quite a stretch before courses arrived.",
                "themes_neg": ["service_speed"], "themes_pos": [],
                "tag_evidence": [],
                "tag_source": "manager",
            },
            {
                "review_id": "r-praise-only", "location": "Cafe",
                "date": pd.Timestamp("2026-10-29"), "rating": 5,
                "reviewer": "Happy Guest",
                "text": "Service was fast and smooth.",
                "themes_neg": [], "themes_pos": ["service_speed"],
                "tag_evidence": [{
                    "theme": "service_speed", "polarity": "Praise",
                    "matched_terms": ["fast"], "excerpt": "Service was fast",
                }],
                "tag_source": "local",
            },
            {
                "review_id": "r-old-boundary", "location": "Cafe",
                "date": pd.Timestamp("2026-09-30"), "rating": 1,
                "reviewer": "Old Guest",
                "text": "Old slow service outside the 30-day window.",
                "themes_neg": ["service_speed"], "themes_pos": [],
                "tag_evidence": [],
                "tag_source": "local",
            },
            {
                "review_id": "r-other-loc", "location": "Bistro",
                "date": pd.Timestamp("2026-10-30"), "rating": 1,
                "reviewer": "Other Guest",
                "text": "Slow service at another restaurant.",
                "themes_neg": ["service_speed"], "themes_pos": [],
                "tag_evidence": [],
                "tag_source": "local",
            },
        ])

        rows = AE.supporting_alert_reviews(df, "Cafe", "Service speed", recent_days=30)
        self.assertEqual([r["review_id"] for r in rows], ["r-recent-1", "r-recent-mgr"])
        self.assertEqual(rows[0]["matched_terms"], ["forever", "slow"])
        self.assertEqual(rows[0]["excerpts"], ["Service was slow and took forever for entrees"])
        self.assertEqual(rows[1]["tag_source"], "manager")
        # Reviewer names are never copied into alert evidence dicts
        for row in rows:
            self.assertNotIn("reviewer", row)

    def test_alert_evidence_ui_renders_matched_terms_and_excludes_reviewer_names(self):
        from streamlit.testing.v1 import AppTest

        script = '''
import pandas as pd
import alert_evidence_ui as AE

df = pd.DataFrame([
    {
        "review_id": "r1", "location": "Cafe",
        "date": pd.Timestamp("2026-10-30"), "rating": 2,
        "reviewer": "Secret Reviewer Name",
        "text": "Service was really slow between courses.",
        "themes_neg": ["service_speed"], "themes_pos": [],
        "tag_evidence": [{
            "theme": "service_speed", "polarity": "Complaint",
            "matched_terms": ["slow"],
            "excerpt": "Service was really slow between courses",
        }],
        "tag_source": "local",
    },
])
AE.show_alert_evidence(df, {"location": "Cafe", "theme": "Service speed"}, recent_days=30)
'''
        app = AppTest.from_string(script, default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertTrue(any(e.label == "Recent reviews behind this alert (1)" for e in app.expander))
        captions = "\n".join(c.value for c in app.caption)
        texts = "\n".join(t.value for t in app.text)
        self.assertIn("Matched terms: slow", captions)
        self.assertIn("Triggering excerpt: Service was really slow between courses", captions)
        self.assertIn("Service was really slow between courses.", texts)
        self.assertNotIn("Secret Reviewer Name", captions + texts)

    def test_walkthrough_shows_evidence_cues_and_manager_followup_without_breaking_boundary(self):
        scene3 = (DEMO_DIR / "src/components/video/video_scenes/Scene3.tsx").read_text(encoding="utf-8")
        scene4 = (DEMO_DIR / "src/components/video/video_scenes/Scene4.tsx").read_text(encoding="utf-8")
        self.assertIn("Evidence cues:", scene3)
        self.assertIn("Why manager review:", scene3)
        self.assertIn("EXAMPLE MANAGER FOLLOW-UP", scene4)
        self.assertIn("Wait for 5 newer reviews", scene4)
        self.assertIn("not proof of cause", scene4)
        self.assertEqual(B.audit_demo_boundary(DEMO_DIR), [])


if __name__ == "__main__":
    unittest.main()
