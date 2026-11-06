import unittest
from evaluate_heldout import validate_rows
from labeling_sheet import text_hash
import engine as E


class HeldoutValidationTests(unittest.TestCase):
    def setUp(self):
        self.row = dict(sample_id="H001", review_text="Synthetic food comment.",
                        **{name: "Absent" for name in E.THEME_LABELS.values()})
        self.frozen = [dict(sample_id="H001",
                            csv_text_sha256=text_hash(self.row["review_text"]))]

    def test_exact_batch_approval_allows_chat_approval(self):
        validate_rows([self.row], self.frozen, ["H001"])

    def test_missing_approval_rejected(self):
        with self.assertRaises(ValueError):
            validate_rows([self.row], self.frozen, [])

    def test_duplicate_id_rejected(self):
        with self.assertRaises(ValueError):
            validate_rows([self.row, self.row], self.frozen, ["H001"])

    def test_modified_text_rejected(self):
        self.row["review_text"] += " edited"
        with self.assertRaises(ValueError):
            validate_rows([self.row], self.frozen, ["H001"])

    def test_blank_or_invalid_label_rejected(self):
        for value in ("", "neutral", "made-up"):
            self.row[next(iter(E.THEME_LABELS.values()))] = value
            with self.assertRaises(ValueError):
                validate_rows([self.row], self.frozen, ["H001"])


if __name__ == "__main__":
    unittest.main()
