"""Tests for Task #146: show when unclear wording needs a manager instead of guessing."""
from pathlib import Path
import unittest

import engine as E
import unclear_wording_ui as U


REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = REPO_ROOT / "artifacts" / "review-intelligence-demo"


class UnclearWordingExampleTests(unittest.TestCase):
    def test_example_triggers_manager_review_without_guessing(self):
        example = U.build_unclear_wording_example(E.THEMES)
        self.assertEqual(example["text"], U.UNCLEAR_WORDING_EXAMPLE)
        self.assertEqual(example["themes_pos"], [])
        self.assertEqual(example["themes_neg"], [])
        self.assertTrue(example["needs_review"])
        self.assertIn("Price", example["flagged_themes"])
        self.assertTrue(example["reasons"])
        self.assertTrue(
            any(item["theme"] == "price" and item["polarity"] == "Needs review"
                for item in example["evidence"])
        )

    def test_public_walkthrough_and_script_show_same_unclear_example(self):
        scene3 = (
            DEMO_DIR / "src" / "components" / "video" / "video_scenes" / "Scene3.tsx"
        ).read_text(encoding="utf-8")
        script_md = (DEMO_DIR / "SCRIPT.md").read_text(encoding="utf-8")

        for content in (scene3, script_md):
            self.assertIn(U.UNCLEAR_WORDING_EXAMPLE, content)
            self.assertIn("Needs manager review", content)
        self.assertIn("FICTIONAL UNCLEAR EXAMPLE", scene3)
        self.assertIn("instead of guessing", scene3)

    def test_dashboard_callout_renders_unclear_wording_example(self):
        from streamlit.testing.v1 import AppTest

        script = (
            "import unclear_wording_ui as U\n"
            "U.show_unclear_wording_example()\n"
        )
        app = AppTest.from_string(script, default_timeout=30).run()
        self.assertFalse(app.exception)
        markdown_text = "\n".join(m.value for m in app.markdown)
        caption_text = "\n".join(c.value for c in app.caption)
        self.assertIn("unclear wording asks a manager instead of guessing", markdown_text.lower())
        self.assertIn(U.UNCLEAR_WORDING_EXAMPLE, caption_text)
        self.assertIn("Fictional example", caption_text)
        self.assertIn("Auto-counted praise/complaint tags: none", caption_text)
        self.assertIn("Price", caption_text)


if __name__ == "__main__":
    unittest.main()
