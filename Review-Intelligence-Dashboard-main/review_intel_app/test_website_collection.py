"""Synthetic extraction checks. No real reviews or network requests."""
import unittest
from collect_website_reviews import extract, official_url


class WebsiteCollectionTests(unittest.TestCase):
    def test_identity_dates_and_duplicates(self):
        item = ('<section><div class="item"><h3 class="review-by">Review by - Google</h3>'
                '<h4 class="reviewer">Synthetic Person</h4>'
                '<i class="fa fa-star"></i><blockquote><p>Invented food feedback.</p>'
                '</blockquote></div></section>')
        rows, _ = extract('<div id="reviews_v2">' + item * 2 +
                          item.replace("food", "service") +
                          item.replace("Synthetic Person", "Another Person") +
                          '</div>', "https://mumbaicentralva.com/", "now")
        self.assertEqual(len(rows), 4)
        self.assertEqual(len({r["review_id"] for r in rows}), 3)
        self.assertTrue(all(r["date"] == "" for r in rows))
        self.assertTrue(all(r["rating"] == "1" for r in rows))
        self.assertNotIn("Synthetic Person", str(rows))
        self.assertEqual(rows[0]["source_attribution"], "Review by - Google")
        self.assertEqual(rows[0]["text"], "Invented food feedback.")

    def test_external_urls_are_not_crawled(self):
        self.assertIsNone(official_url("https://google.com/reviews"))
        self.assertIsNone(official_url("https://mumbaicentralva.com.evil.test/"))
        self.assertEqual(official_url("https://mumbaicentralva.com/party?source=popup#x"),
                         "https://mumbaicentralva.com/party")


if __name__ == "__main__":
    unittest.main()
