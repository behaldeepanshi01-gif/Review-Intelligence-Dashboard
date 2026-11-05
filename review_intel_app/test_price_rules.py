"""Synthetic price cases, not held-out accuracy evidence."""
import unittest
import engine as E


class PriceRulesTests(unittest.TestCase):
    def assert_sides(self, text, praise, complaint):
        for rating in (1, 5):
            with self.subTest(text=text, rating=rating):
                result = E.tag_offline(text, rating)
                self.assertEqual("price" in result["themes_pos"], praise)
                self.assertEqual("price" in result["themes_neg"], complaint)
        return result

    def test_price_praise_and_synonyms(self):
        for text in ("Reasonable prices.", "Fair pricing.", "Affordable prices.",
                     "Reasonably priced.", "Well priced.", "Inexpensive meal.",
                     "Worth the money."):
            self.assert_sides(text, True, False)

    def test_price_complaints_and_synonyms(self):
        for text in ("Overpriced.", "Pricier than expected.", "Expensive prices.",
                     "Pricing is excessive.", "High prices.", "Waste of money.",
                     "Not worth the price.", "A hidden service charge.",
                     "They demanded a tip."):
            self.assert_sides(text, False, True)

    def test_neutral_money_and_fees_need_review(self):
        for text in ("A service charge is included.", "Gratuity is 20%.",
                     "I left a tip.", "Money was on the table.", "Pricing is listed.",
                     "The meal costs $20.", "Good food and a tip."):
            result = self.assert_sides(text, False, False)
            self.assertTrue(result["needs_review"])
            self.assertTrue(any(i["theme"] == "price" and i["polarity"] == "Needs review"
                                for i in result["tag_evidence"]))
        self.assert_sides("We discussed whether dinner was worth the price.", False, False)

    def test_mixed_price_preserves_both_sides(self):
        self.assert_sides("Lunch prices are fair but dinner is overpriced.", True, True)
        self.assert_sides("Cheap prices and expensive drinks.", True, True)

    def test_negation(self):
        for text in ("Not expensive.", "Not too pricey.", "Not overpriced.",
                     "Prices are not unreasonable.", "Not only fair prices."):
            self.assert_sides(text, True, False)
        for text in ("Not affordable.", "Prices are not reasonable.", "Not cheap."):
            self.assert_sides(text, False, True)

    def test_portion_value_coexists(self):
        result = self.assert_sides("Generous portions and fair prices.", True, False)
        self.assertIn("portion_value", result["themes_pos"])
        result = self.assert_sides("Small portions and overpriced.", False, True)
        self.assertIn("portion_value", result["themes_neg"])

    def test_ambiguity_is_not_forced(self):
        for text in ("Maybe the prices are fair.", "Perhaps overpriced.",
                     "I don't think the prices are fair."):
            result = self.assert_sides(text, False, False)
            self.assertTrue(result["needs_review"])

    def test_no_sentiment_leakage(self):
        self.assert_sides("Prices listed with good food.", False, False)
        self.assert_sides("The service charge covered excellent staff.", False, False)
        result = self.assert_sides("Overpriced meal.", False, True)
        self.assertNotIn("food_flavor", result["themes_neg"])
        self.assert_sides("Good tip for the server.", False, False)

    def test_boundaries_and_evidence(self):
        self.assert_sides("The priceless keepsake tipped over.", False, False)
        result = self.assert_sides("Fair pricing.", True, False)
        item = next(i for i in result["tag_evidence"] if i["theme"] == "price")
        self.assertIn("pricing", item["matched_terms"])
        self.assertEqual(item["excerpt"], "Fair pricing")
        self.assertTrue(item["reason"])


if __name__ == "__main__":
    unittest.main()
