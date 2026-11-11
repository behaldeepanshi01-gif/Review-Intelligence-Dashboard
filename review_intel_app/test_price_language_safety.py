"""Synthetic-only price-context checks; expected failures are open defects.

Run: python -B -m unittest test_price_language_safety -v
Do not count expected failures as successful language handling or accuracy.
Each case/rating is separate so one failure cannot mask another case.
"""
import hashlib
import json
from pathlib import Path
import unittest

import engine as E
from price_language_cases import CASES


class PriceLanguageSafetyTests(unittest.TestCase):
    pass


def safety_test(case, rating):
    case_id, text, praise, complaint, gap = case

    def check(self):
        result = E.tag_offline(text, rating)
        self.assertEqual(
            ("price" in result["themes_pos"], "price" in result["themes_neg"]),
            (praise, complaint), f"{case_id}: {text}",
        )
        evidence = [item for item in result["tag_evidence"] if item["theme"] == "price"]
        self.assertTrue(evidence)
        for item in evidence:
            self.assertTrue(item["excerpt"])
            self.assertIn(item["excerpt"], text)
            self.assertTrue(item["matched_terms"])
            self.assertTrue(item["reason"])
        if not praise and not complaint:
            self.assertTrue(result["needs_review"])
            self.assertTrue(result["review_reasons"])
            self.assertTrue(all(item["polarity"] == "Needs review" for item in evidence))
        else:
            for expected, polarity in ((praise, "Praise"), (complaint, "Complaint")):
                if expected:
                    self.assertTrue(any(item["polarity"] == polarity for item in evidence))
        if (not praise and not complaint) or case_id in {
            "reported_then_praise", "reported_then_complaint",
            "question_then_praise", "question_then_complaint",
        }:
            # A clear opinion in another sentence must survive, but must not
            # erase the warning/evidence for the ambiguous fragment.
            self.assertTrue(result["needs_review"])
            self.assertTrue(result["review_reasons"])
            self.assertTrue(any(item["polarity"] == "Needs review" for item in evidence))

    # Runtime exceptions must be errors, not silently counted as known gaps.
    # Run the analyzer separately in the always-passing invariant tests below.
    return unittest.expectedFailure(check) if gap else check


for case in CASES:
    for rating in (1, 3, 5):
        setattr(PriceLanguageSafetyTests, f"test_{case[0]}_rating_{rating}",
                safety_test(case, rating))


def nonprice_snapshot():
    """Exact per-review sides and evidence, not aggregate theme counts."""
    rows = []
    for case_id, text, *_ in CASES:
        result = E.tag_offline(text, 3)
        rows.append({
            "id": case_id,
            "positive": sorted(set(result["themes_pos"]) - {"price"}),
            "negative": sorted(set(result["themes_neg"]) - {"price"}),
            "evidence": [item for item in result["tag_evidence"] if item["theme"] != "price"],
        })
    return rows


class FrozenPriceLanguageTests(unittest.TestCase):
    def test_rating_never_changes_tags_or_evidence(self):
        # Ratings intentionally affect urgency and mismatch warnings, but
        # cannot supply theme polarity or alter textual tagging evidence.
        for case_id, text, *_ in CASES:
            with self.subTest(case=case_id):
                baseline = E.tag_offline(text, 3)
                for rating in (1, 5):
                    actual = E.tag_offline(text, rating)
                    for field in ("themes_pos", "themes_neg", "tag_evidence"):
                        self.assertEqual(actual[field], baseline[field])

    def test_exact_nonprice_baseline(self):
        path = Path(__file__).with_name("price_language_nonprice_baseline.json")
        self.assertEqual(nonprice_snapshot(), json.loads(path.read_text()))

    def test_frozen_implementation_identity(self):
        # New, separately approved cycle. The prior evaluation's source hashes
        # remain in MONEY_WASTE_HANDOFF.md and the pre-edit backup manifest.
        expected = {
            "engine.py": "b2624f72c3cc09f03e386554b53ef751372c83c6b69675a17e96a8df2be471f6",
            "local_analyzer.py": "02dbfb5fa9b8768a785ab355ae61c48d5c652c7339e6aca1bb5a5c12a0bdee39",
            "price_rules.py": "5a82af8c9c86ab1e0533f513e539e870372d8ccfdd661dc8fdfe66f5d1d321c6",
        }
        for filename, digest in expected.items():
            with self.subTest(file=filename):
                self.assertEqual(hashlib.sha256(
                    Path(__file__).with_name(filename).read_bytes()).hexdigest(), digest)
        self.assertEqual(E.LOCAL_ANALYZER_VERSION, "local-rules-4-price-context")


class PriceContextBoundaryTests(unittest.TestCase):
    def test_context_boundaries_and_explicit_mixed_feedback(self):
        cases = [
            ('"Fair prices. Cheap drinks." My meal was overpriced.', False, True),
            ('“Fair prices. Cheap drinks.” My meal was overpriced.', False, True),
            ("'Fair prices. Cheap drinks.' My meal was overpriced.", False, True),
            ('"Overpriced." My prices were fair.', True, False),
            ('"Fair prices." Do not waste your money.', False, True),
            ('"Fair prices." This was a waste of my money.', False, True),
            ('"Fair prices." This was not a waste of my money.', True, False),
            ("Are prices fair, and drinks cheap? Overpriced meal.", False, True),
            ("They said prices were fair and drinks cheap. Overpriced meal.", False, True),
            ("According to the flyer, prices are fair. My meal was overpriced.", False, True),
            ("Fair prices but overpriced drinks. Is it expensive?", True, True),
            ("Is it expensive? Fair prices but overpriced drinks.", True, True),
            ("They said prices were fair. Maybe overpriced.", False, False),
        ]
        for text, praise, complaint in cases:
            for rating in (1, 3, 5):
                with self.subTest(text=text, rating=rating):
                    result = E.tag_offline(text, rating)
                    self.assertEqual(
                        ("price" in result["themes_pos"], "price" in result["themes_neg"]),
                        (praise, complaint))
                    self.assertTrue(result["needs_review"])
                    price = [e for e in result["tag_evidence"] if e["theme"] == "price"]
                    self.assertTrue(any(e["polarity"] == "Needs review" for e in price))
                    self.assertTrue(all(e["excerpt"] in text for e in price))


if __name__ == "__main__":
    unittest.main()
