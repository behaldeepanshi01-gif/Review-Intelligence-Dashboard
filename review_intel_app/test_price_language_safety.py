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
            "local_analyzer.py": "c73717a8e97ebaf056815a98ccae17b317fe26f6fd58343643b8e01f2e197d5c",
            "price_rules.py": "b3bc68e69468132b8e891799de370b46a91ac89fccfdefbdd370a6d0f56105eb",
        }
        for filename, digest in expected.items():
            with self.subTest(file=filename):
                self.assertEqual(hashlib.sha256(
                    Path(__file__).with_name(filename).read_bytes()).hexdigest(), digest)
        self.assertEqual(E.LOCAL_ANALYZER_VERSION, "local-rules-5-price-punctuation")


class PriceContextBoundaryTests(unittest.TestCase):
    def test_punctuation_scope_controls(self):
        cases = [
            ("Prices are not, in my opinion, fair.", False, True, False),
            ("Prices aren’t, in my view, reasonable.", False, True, False),
            ("Prices are not, by any means, reasonable.", False, True, False),
            ("Prices are not, to me, expensive.", True, False, False),
            ("Perhaps, the prices are fair.", False, False, True),
            ("Maybe, the prices are fair. My meal was overpriced.", False, True, True),
            ("Affordable prices; not. My meal was overpriced.", False, True, True),
            ("Overpriced meal; not! My prices were fair.", True, False, True),
            ("Affordable prices; not expensive.", True, False, False),
            ("Maybe. The prices are fair.", True, False, False),
            ("Prices are not — reasonable.", False, True, False),
            ("Prices are not (at all) reasonable.", False, True, False),
            ("Prices aren’t reasonable.", False, True, False),
            ("Prices are reasonable. Not expensive.", True, False, False),
            ("Yeah right, affordable prices!", False, False, True),
        ]
        for text, praise, complaint, unclear in cases:
            baseline = None
            for rating in (1, 3, 5):
                with self.subTest(text=text, rating=rating):
                    result = E.tag_offline(text, rating)
                    self.assertEqual(
                        ("price" in result["themes_pos"], "price" in result["themes_neg"]),
                        (praise, complaint))
                    evidence = [e for e in result["tag_evidence"] if e["theme"] == "price"]
                    self.assertTrue(evidence)
                    self.assertEqual(any(e["polarity"] == "Needs review" for e in evidence), unclear)
                    self.assertTrue(all(e["excerpt"] in text and e["matched_terms"]
                                        and e["reason"] for e in evidence))
                    if unclear:
                        self.assertTrue(result["needs_review"])
                        self.assertTrue(result["review_reasons"])
                    if "; not." in text or "; not!" in text:
                        self.assertTrue(any("; not" in e["excerpt"] for e in evidence))
                    if baseline is not None:
                        self.assertEqual(evidence, baseline)
                    baseline = evidence

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
