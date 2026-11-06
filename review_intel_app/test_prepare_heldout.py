import unittest
from prepare_heldout import eligible_rows, normalize, text_hash


class ExclusionTests(unittest.TestCase):
    def test_ids_normalized_duplicates_and_previous_batches(self):
        tuning = [{"review_id": "used", "review_text": "Great FOOD!"}]
        source = [
            {"review_id": "used", "text": "Edited wording"},
            {"review_id": "duplicate", "text": "Ｇｒｅａｔ food"},
            {"review_id": "old", "text": "Earlier sample"},
            {"review_id": "new", "text": "New passage."},
            {"review_id": "new2", "text": "NEW PASSAGE"},
            {"review_id": "empty", "text": "  "},
        ]
        result = eligible_rows(source, tuning, {text_hash("Earlier sample")})
        self.assertEqual([row["review_id"] for row in result], ["new"])

    def test_normalization_handles_punctuation_unicode_and_spacing(self):
        self.assertEqual(normalize("ＦＯＯＤ & flavor!"), normalize("food flavor"))


if __name__ == "__main__":
    unittest.main()
