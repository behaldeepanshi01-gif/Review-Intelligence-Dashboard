"""Browser-free UI verification, isolated from all real app state."""
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest
import engine as E


class PriceAppTests(unittest.TestCase):
    def test_price_evidence_and_neutral_review_warning(self):
        with tempfile.TemporaryDirectory() as directory:
            app_file = Path(directory) / "app.py"
            shutil.copy2(Path(__file__).with_name("app.py"), app_file)
            rows = pd.DataFrame([
                {"review_id": "synthetic-price", "location": "Demo Cafe",
                 "date": pd.Timestamp("2026-10-01"), "rating": 5, "reviewer": "Guest",
                 "text": "Fair pricing."},
                {"review_id": "synthetic-fee", "location": "Demo Cafe",
                 "date": pd.Timestamp("2026-10-02"), "rating": 3, "reviewer": "Guest",
                 "text": "A service charge is included."},
            ])
            with patch.object(E, "load_reviews", return_value=rows):
                app = AppTest.from_file(str(app_file), default_timeout=30).run()
                self.assertFalse(app.exception)
                next(s for s in app.selectbox if s.label == "Theme").select("Price")
                next(r for r in app.radio if r.label == "Showing").set_value("Praise")
                app.run()
                self.assertFalse(app.exception)
                self.assertTrue(any("Price: Praise" in m.value for m in app.markdown))
                self.assertTrue(any(e.label == "Why these tags?" for e in app.expander))
                self.assertTrue(any("pricing" in c.value for c in app.caption))
                self.assertTrue(any("no clear cost opinion" in w.value for w in app.warning))
                self.assertTrue(any(s.label == "Review needing a check" for s in app.selectbox))
                self.assertTrue(any(e.label.startswith("Reviews needing manager review")
                                    for e in app.expander))


if __name__ == "__main__":
    unittest.main()
