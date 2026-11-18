"""Tests for Reviews needing manager review and Reply inbox triage filters."""
import unittest
import pandas as pd

import review_triage_ui as T


def _sample_needs_review():
    return pd.DataFrame([
        {
            "review_id": "r-price", "location": "Cafe",
            "date": pd.Timestamp("2026-10-30"), "rating": 3,
            "text": "Are the prices fair? Maybe.",
            "tag_evidence": [{
                "theme": "price", "polarity": "Needs review",
                "matched_terms": ["prices"], "excerpt": "Are the prices fair",
            }],
            "review_reasons": [
                "Question, rhetorical or reported/quoted price wording needs a person to check it."
            ],
        },
        {
            "review_id": "r-speed", "location": "Cafe",
            "date": pd.Timestamp("2026-10-29"), "rating": 4,
            "text": "Great food, mentioned waiting briefly.",
            "tag_evidence": [
                {"theme": "food_flavor", "polarity": "Praise",
                 "matched_terms": ["food"], "excerpt": "Great food"},
                {"theme": "service_speed", "polarity": "Needs review",
                 "matched_terms": ["waiting"], "excerpt": "mentioned waiting briefly"},
            ],
            "review_reasons": ["A theme is mentioned without clear praise or criticism."],
        },
        {
            "review_id": "r-none", "location": "Bistro",
            "date": pd.Timestamp("2026-10-28"), "rating": 3,
            "text": "Stopped in yesterday afternoon.",
            "tag_evidence": [],
            "review_reasons": ["No supported restaurant theme was found. Check this review manually."],
        },
    ])


class ReviewTriageTests(unittest.TestCase):
    def test_needs_review_theme_and_reason_filtering(self):
        df = _sample_needs_review()
        orig_ids = df["review_id"].tolist()

        themes = T.flagged_theme_options(df)
        self.assertEqual(themes[0], T.ALL_FLAGGED_THEMES)
        self.assertIn("Price", themes)
        self.assertIn("Service speed", themes)
        self.assertIn(T.NO_THEME_LABEL, themes)
        # Praise-only food_flavor should NOT appear as a flagged theme
        self.assertNotIn("Food & flavor", themes)

        reasons = T.flagged_reason_options(df)
        self.assertEqual(reasons[0], T.ALL_REASONS)
        self.assertEqual(len(reasons), 4)

        # Default returns all rows in exact original order
        self.assertEqual(T.filter_needs_review(df)["review_id"].tolist(), orig_ids)
        # Theme filters
        self.assertEqual(
            T.filter_needs_review(df, theme_filter="Price")["review_id"].tolist(),
            ["r-price"],
        )
        self.assertEqual(
            T.filter_needs_review(df, theme_filter=T.NO_THEME_LABEL)["review_id"].tolist(),
            ["r-none"],
        )
        # Combined theme + mismatched reason yields clean empty DataFrame
        empty = T.filter_needs_review(
            df,
            theme_filter="Price",
            reason_filter="No supported restaurant theme was found. Check this review manually.",
        )
        self.assertTrue(empty.empty)
        # Non-mutation
        self.assertEqual(df["review_id"].tolist(), orig_ids)

    def test_reply_inbox_theme_and_recheck_invariants(self):
        df = pd.DataFrame([
            {
                "reply_key": "k-high-speed", "urgency": "High",
                "date": pd.Timestamp("2026-10-30"),
                "themes_neg": ["service_speed"], "themes_pos": [],
            },
            {
                "reply_key": "k-med-price", "urgency": "Medium",
                "date": pd.Timestamp("2026-10-29"),
                "themes_neg": ["price"], "themes_pos": [],
            },
            {
                "reply_key": "k-low-stale", "urgency": "Low",
                "date": pd.Timestamp("2026-10-28"),
                "themes_neg": ["cleanliness"], "themes_pos": [],
            },
            {
                "reply_key": "k-high-approved", "urgency": "High",
                "date": pd.Timestamp("2026-10-27"),
                "themes_neg": ["service_speed"], "themes_pos": [],
            },
        ])
        approved = {"k-low-stale", "k-high-approved"}
        rechecks = {"k-low-stale"}

        opts = T.reply_theme_options(df)
        self.assertEqual(opts[0], T.ALL_REPLY_THEMES)
        self.assertIn("Service speed", opts)
        self.assertIn("Price", opts)

        # Filter to Service speed, High+Medium, hide approved -> stale approval STILL stays visible!
        by_theme = T.filter_reply_inbox(
            df,
            urgencies=["High", "Medium"],
            show_approved=False,
            approved_keys=approved,
            reply_rechecks=rechecks,
            theme_filter="Service speed",
        )
        self.assertEqual(by_theme["reply_key"].tolist(), ["k-high-speed", "k-low-stale"])

        # Empty urgency + non-matching theme still keeps stale approval visible
        stale_kept = T.filter_reply_inbox(
            df,
            urgencies=[],
            show_approved=False,
            approved_keys=approved,
            reply_rechecks=rechecks,
            theme_filter="Price",
        )
        self.assertEqual(stale_kept["reply_key"].tolist(), ["k-low-stale"])

        # Needs recheck only narrows exclusively to stale approvals
        only_recheck = T.filter_reply_inbox(
            df,
            urgencies=["High", "Medium", "Low"],
            show_approved=True,
            approved_keys=approved,
            reply_rechecks=rechecks,
            recheck_only=True,
        )
        self.assertEqual(only_recheck["reply_key"].tolist(), ["k-low-stale"])

    def test_needs_review_triage_widget_renders_and_filters(self):
        from streamlit.testing.v1 import AppTest

        script = '''
import pandas as pd
import review_triage_ui as T

df = pd.DataFrame([
    {
        "review_id": "r-price", "location": "Cafe",
        "date": pd.Timestamp("2026-10-30"), "rating": 3,
        "text": "Are the prices fair?",
        "tag_evidence": [{"theme": "price", "polarity": "Needs review",
                          "matched_terms": ["prices"], "excerpt": "Are the prices fair"}],
        "review_reasons": ["Question, rhetorical or reported/quoted price wording needs a person to check it."],
    },
    {
        "review_id": "r-none", "location": "Bistro",
        "date": pd.Timestamp("2026-10-28"), "rating": 3,
        "text": "Stopped in yesterday.",
        "tag_evidence": [],
        "review_reasons": ["No supported restaurant theme was found. Check this review manually."],
    },
])
filtered = T.show_needs_review_triage(df)
'''
        app = AppTest.from_string(script, default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertTrue(any("Showing 2 of 2" in c.value for c in app.caption))
        next(s for s in app.selectbox if s.label == "Filter by flagged theme").select("Price").run()
        self.assertFalse(app.exception)
        self.assertTrue(any("Showing 1 of 2" in c.value for c in app.caption))


    def test_no_deprecated_use_container_width_in_app_modules(self):
        from pathlib import Path
        app_dir = Path(__file__).resolve().parent
        for path in sorted(app_dir.glob("*.py")):
            if path.name.startswith("test_"):
                continue
            self.assertNotIn(
                "use_container_width",
                path.read_text(encoding="utf-8"),
                f"Deprecated use_container_width found in {path.name}",
            )


if __name__ == "__main__":
    unittest.main()
