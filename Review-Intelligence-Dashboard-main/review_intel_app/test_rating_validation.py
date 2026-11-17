"""Rating policy and pre-confirmation warnings using synthetic uploads only."""
import io
from pathlib import Path
import tempfile
import unittest

import engine as E
from test_upload_validation import UploadUITests, VALID


CONTENT = (
    b"location,date,rating,text\n"
    b"Demo,2026-02-01,,Missing\n"
    b"Demo,2026-01-01,garbage,Bad\n"
    b"Demo,2026-01-02,4.9,Fraction\n"
    b"Demo,2026-01-03,0.5,Low\n"
    b"Demo,2026-01-04,7.8,High\n"
    b"Demo,,bad,Rejected\n"
    b"Demo,2026-01-05,5,Unchanged\n"
)


class RatingTests(unittest.TestCase):
    def test_policy_and_source_order(self):
        frame, preview = E.preview_reviews(io.BytesIO(CONTENT))
        self.assertEqual(frame.rating.tolist(), [3, 4, 1, 5, 5, 3])
        changes = preview["ratings"]
        self.assertEqual(changes["changed"], 5)
        self.assertEqual(list(changes["reasons"].values()), [1, 1, 1, 1, 1])
        self.assertEqual([r["source_row"] for r in changes["rows"]], [2, 3, 4, 5, 6])
        self.assertEqual([r["original_rating"] for r in changes["rows"]],
                         ["", "garbage", "4.9", "0.5", "7.8"])
        self.assertEqual([r["analysis_rating"] for r in changes["rows"]], [3, 3, 4, 1, 5])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "original.csv"
            path.write_bytes(CONTENT)
            self.assertEqual(E.preview_reviews(path)[1], preview)
            self.assertEqual(path.read_bytes(), CONTENT)

    def test_edge_cases_and_alias(self):
        cases = [(" ", 3), ("NA", 3), ("NaN", 3), ("inf", 5), ("-inf", 1),
                 ("-2.7", 1), ("1.9", 1), ("5.0", 5), ("3", 3)]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                content = f"location,date,stars,text\nDemo,2026-01-01,{raw},Review\n".encode()
                frame, preview = E.preview_reviews(io.BytesIO(content))
                self.assertEqual(frame.rating.tolist(), [expected])
                rows = preview["ratings"]["rows"]
                self.assertEqual(bool(rows), raw not in ("5.0", "3"))
                if rows:
                    self.assertEqual(rows[0]["original_rating"], raw)

    def test_empty_and_rejected_ratings_are_not_adjusted(self):
        for content in [VALID.splitlines()[0] + b"\n",
                        b"location,date,rating,text\nDemo,,bad,Rejected\n"]:
            _, preview = E.preview_reviews(io.BytesIO(content))
            self.assertEqual(preview["ratings"]["changed"], 0)
            self.assertEqual(preview["ratings"]["rows"], [])


class RatingUITests(UploadUITests):
    def test_rating_warning_before_confirmation_and_original_preserved(self):
        self.upload = io.BytesIO(CONTENT)
        self.upload.name, self.upload.file_id = "ratings.csv", "ratings"
        app = self.open_app()
        self.assertTrue(any("5 of 6 accepted reviews" in w.value for w in app.warning))
        self.assertTrue(any("truncated, not rounded" in c.value for c in app.caption))
        self.assertEqual(app.dataframe[0].value["original_rating"].tolist(),
                         ["", "garbage", "4.9", "0.5", "7.8"])
        self.assert_unchanged()
        next(b for b in app.button if b.label == "Save CSV").click().run()
        self.assertFalse(app.exception)
        current = self.store.get(self.existing["dataset_id"])
        self.assertEqual(Path(current["path"]).read_bytes(), CONTENT)
        self.assertEqual(Path(self.existing["path"]).read_bytes(), VALID)
        self.assertEqual(E.load_reviews(current["path"]).rating.tolist(), [3, 4, 1, 5, 5, 3])


if __name__ == "__main__":
    unittest.main()
