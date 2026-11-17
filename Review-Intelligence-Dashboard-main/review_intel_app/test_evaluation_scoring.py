"""Synthetic scoring tests; no real review content."""
import unittest
from evaluate_approved_sheet import score


class ScoringTests(unittest.TestCase):
    def test_mixed_counts_both(self):
        self.assertEqual(score("mixed", True, True), [(1, 0, 0), (1, 0, 0)])
        self.assertEqual(score("mixed", True, False), [(1, 0, 0), (0, 1, 0)])

    def test_none_counts_neither(self):
        self.assertEqual(score("none", False, False), [(0, 0, 0), (0, 0, 0)])
        self.assertEqual(score("none", True, True), [(0, 0, 1), (0, 0, 1)])

    def test_unclear_is_unscored(self):
        for p in (True, False):
            for n in (True, False):
                self.assertIsNone(score(" Unclear ", p, n))

    def test_wrong_polarity_counts_two_errors(self):
        self.assertEqual(score("pos", False, True), [(0, 1, 0), (0, 0, 1)])
        self.assertEqual(score("neg", True, False), [(0, 0, 1), (0, 1, 0)])

    def test_missing_or_invalid_labels_are_not_negatives(self):
        for label in ("", " ", "invalid"):
            with self.assertRaises(KeyError):
                score(label, False, False)


if __name__ == "__main__":
    unittest.main()
