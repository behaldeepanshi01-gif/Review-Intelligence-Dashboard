"""Synthetic examples only. These tests are not an accuracy score on real data."""

import unittest
from unittest.mock import patch

import pandas as pd
import engine as E


class LocalAnalyzerTests(unittest.TestCase):
    def test_all_twelve_themes_have_supported_examples(self):
        examples = {
            "food_flavor": ("Delicious food.", "themes_pos"),
            "seasoning": ("The curry was too salty.", "themes_neg"),
            "consistency": ("Inconsistent recipes.", "themes_neg"),
            "service_speed": ("Slow service.", "themes_neg"),
            "staff": ("Friendly staff.", "themes_pos"),
            "portion_value": ("Generous portions.", "themes_pos"),
            "price": ("Expensive prices.", "themes_neg"),
            "ambiance": ("Cozy atmosphere.", "themes_pos"),
            "cleanliness": ("Dirty restroom.", "themes_neg"),
            "catering": ("Excellent catering.", "themes_pos"),
            "wait_reservation": ("Great reservations.", "themes_pos"),
            "takeout": ("Late delivery.", "themes_neg"),
        }
        self.assertEqual(set(examples), set(E.THEMES))
        for theme, (text, field) in examples.items():
            with self.subTest(theme=theme):
                self.assertIn(theme, E.tag_offline(text, 3)[field])

    def test_mixed_feedback_without_a_contrast_word(self):
        result = E.tag_offline("Great food and slow service.", 5)
        self.assertIn("food_flavor", result["themes_pos"])
        self.assertIn("service_speed", result["themes_neg"])
        self.assertNotIn("service_speed", result["themes_pos"])
        self.assertEqual(result["sentiment"], "Mixed")

    def test_rating_does_not_erase_same_theme_criticism(self):
        for rating in (1, 5):
            result = E.tag_offline("The curry was great but the curry was cold.", rating)
            self.assertIn("food_flavor", result["themes_pos"])
            self.assertIn("food_flavor", result["themes_neg"])

    def test_local_negation_and_boundaries(self):
        examples = [
            ("The food was not good.", "food_flavor", "themes_neg"),
            ("The staff were not rude.", "staff", "themes_pos"),
            ("The tables were not clean.", "cleanliness", "themes_neg"),
            ("The curry was not bad.", "food_flavor", "themes_pos"),
            ("No wait and friendly staff.", "service_speed", "themes_pos"),
            ("Not only good food but also friendly staff.", "food_flavor", "themes_pos"),
        ]
        for text, theme, field in examples:
            with self.subTest(text=text):
                self.assertIn(theme, E.tag_offline(text, 3)[field])
        result = E.tag_offline("Not good food and friendly staff.", 3)
        self.assertIn("food_flavor", result["themes_neg"])
        self.assertIn("staff", result["themes_pos"])

    def test_word_fragments_and_anticipation_do_not_create_themes(self):
        for text in ("The theater overlooks saltwater.", "I can't wait to return."):
            with self.subTest(text=text):
                result = E.tag_offline(text, 3)
                self.assertEqual(result["themes_pos"], [])
                self.assertEqual(result["themes_neg"], [])
                self.assertTrue(result["needs_review"])

    def test_hedged_and_neutral_statements_need_review(self):
        for text in ("Maybe the service was slow.", "We ordered catering."):
            result = E.tag_offline(text, 3)
            self.assertTrue(result["needs_review"])
            self.assertEqual(result["themes_pos"], [])
            self.assertEqual(result["themes_neg"], [])
            self.assertTrue(result["review_reasons"])
            self.assertEqual(result["tag_evidence"][0]["polarity"], "Needs review")

    def test_rating_conflict_is_flagged_not_used_as_polarity(self):
        result = E.tag_offline("The food was bad.", 5)
        self.assertIn("food_flavor", result["themes_neg"])
        self.assertTrue(result["needs_review"])

    def test_evidence_explains_the_matching_theme(self):
        result = E.tag_offline("The staff were friendly.", 5)
        item = next(item for item in result["tag_evidence"] if item["theme"] == "staff")
        self.assertEqual(item["polarity"], "Praise")
        self.assertIn("staff", item["matched_terms"])
        self.assertEqual(item["excerpt"], "The staff were friendly")
        self.assertTrue(item["reason"])

    def test_only_explicitly_praised_staff_enter_shoutouts(self):
        self.assertEqual(E.tag_offline("Our server Alex was rude.", 1)["staff"], [])
        self.assertEqual(E.tag_offline("Our server Alex was friendly.", 5)["staff"], ["Alex"])
        self.assertEqual(E.tag_offline("Alex was amazing.", 5)["staff"], [])

    def test_analysis_keeps_contract_and_makes_no_network_calls(self):
        df = pd.DataFrame([{
            "location": "Demo Cafe", "review_id": "synthetic-1", "reviewer": "Guest",
            "date": pd.Timestamp("2026-10-01"), "rating": 5,
            "text": "Great food and slow service.",
        }])
        with patch("urllib.request.urlopen", side_effect=AssertionError("Network forbidden")):
            result = E.analyze_offline(df)
        expected = {
            "themes_pos", "themes_neg", "staff", "urgency", "sentiment",
            "reply_draft", "engine", "tag_evidence", "needs_review", "review_reasons",
        }
        self.assertTrue(expected.issubset(result.columns))
        self.assertEqual(result.iloc[0]["engine"], "local_rules")
        self.assertIn("sorry", result.iloc[0]["reply_draft"])
        self.assertNotIn("I've shared", result.iloc[0]["reply_draft"])
        self.assertFalse(E.theme_table(result).empty)
        self.assertIn("location", E.staff_leaderboard(result).columns)
        E.early_warnings(result)

    def test_unknown_review_gets_neutral_reply_and_empty_theme_table(self):
        df = pd.DataFrame([{
            "location": "Demo Cafe", "review_id": "synthetic-2", "reviewer": "Guest",
            "date": pd.Timestamp("2026-10-01"), "rating": 3, "text": "Visited yesterday.",
        }])
        result = E.analyze_offline(df)
        self.assertNotIn("kind words", result.iloc[0]["reply_draft"])
        self.assertTrue(E.theme_table(result).empty)
        self.assertIn("theme", E.theme_table(result).columns)

    def test_external_cache_does_not_borrow_local_evidence(self):
        df = pd.DataFrame([
            {"location": "Demo Cafe", "review_id": identifier, "reviewer": "Guest",
             "date": pd.Timestamp("2026-10-01"), "rating": 4, "text": "Great food."}
            for identifier in ("external", "local-fallback")
        ])
        result = E._merge_results(df, {
            "external": {
                "themes_pos": ["staff"], "themes_neg": [], "staff": [],
                "sentiment": "Positive", "urgency": "Low", "reply_draft": "Draft",
            },
        }, "claude").set_index("review_id")
        self.assertEqual(result.loc["external", "tag_evidence"], [])
        self.assertEqual(result.loc["external", "themes_pos"], ["staff"])
        self.assertTrue(result.loc["local-fallback", "tag_evidence"])


if __name__ == "__main__":
    unittest.main()
