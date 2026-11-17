"""Synthetic report fixtures only; no saved action histories are modified."""
import copy
from datetime import date
import unittest
import csv
from pathlib import Path
import tempfile
import os
from unittest.mock import patch

import action_report as R
from dataset_store import source_cohort
import manager_identity as MI


PROVENANCE = {"rules_version": "rules", "decisions_fingerprint": "decisions"}


def action(**updates):
    row = dict(dataset_tag="dataset-a", location="Cafe", theme="Speed",
               theme_key="service_speed", action_text="Check kitchen handoffs",
               owner="Shift lead", status="In progress", start_date="2026-01-01",
               due_date="2026-01-03", baseline_share=40, baseline_provenance=PROVENANCE,
               alert_end_date="2026-01-01",
               baseline_source=source_cohort([], "dataset-a", "Cafe", "2026-01-01"))
    return dict(row, **updates)


def reviews(count):
    return [dict(location="Cafe", date="2026-01-02", reviewer="Guestperson Private",
                 text="This confidential guest passage should not appear.",
                 themes_neg=["service_speed"] if i == 0 else []) for i in range(count)]


class ActionReportTests(unittest.TestCase):
    def render(self, actions, rows, **kw):
        return R.build_report(actions, "dataset-a", ["Cafe"], rows,
                              today=date(2026, 1, 4),
                              provenance_by_location={"Cafe": PROVENANCE}, **kw)

    def render_html(self, actions, rows, **kw):
        return R.build_printable_report(actions, "dataset-a", ["Cafe"], rows,
                                        today=date(2026, 1, 4),
                                        provenance_by_location={"Cafe": PROVENANCE}, **kw)

    def test_scope_groups_and_nonmutation(self):
        actions = [action(), action(status="Done"), action(dataset_tag="dataset-b",
                   action_text="Other dataset"), action(location="Elsewhere",
                   action_text="Other location")]
        original = copy.deepcopy(actions)
        result = self.render(actions, reviews(5))
        self.assertIn("ACTIVE ACTIONS (1)", result)
        self.assertIn("COMPLETED ACTIONS (1)", result)
        self.assertNotIn("Other dataset", result)
        self.assertNotIn("Other location", result)
        self.assertEqual(result.count("(OVERDUE)"), 1)
        self.assertEqual(actions, original)

    def test_five_review_boundary_and_start_date(self):
        rows = reviews(4) + [dict(reviews(1)[0], date="2026-01-01")]
        result = self.render([action()], rows)
        self.assertIn("4 newer reviews", result)
        self.assertNotIn("Saved baseline:", result)
        result = self.render([action()], reviews(5))
        self.assertIn("1 of 5 newer reviews", result)
        self.assertIn("Change: -20.0 percentage points", result)
        self.assertNotIn("Saved baseline:", self.render([action(status="Planned")], reviews(8)))

    def test_changed_and_missing_provenance_suppress_comparison(self):
        for baseline in [None, dict(PROVENANCE, rules_version="older")]:
            result = self.render([action(baseline_provenance=baseline)], reviews(5))
            self.assertIn("Comparison withheld", result)
            self.assertNotIn("Saved baseline:", result)
            self.assertIn("saved baseline is unchanged", result)

    def test_source_changes_and_unknown_source_suppress_comparison(self):
        for source in (None, source_cohort(
                [dict(location="Cafe", date="2026-01-01", rating=1, text="Long wait.")],
                "dataset-a", "Cafe", "2026-01-01")):
            result = self.render([action(baseline_source=source)], reviews(5))
            self.assertIn("Comparison withheld", result)
            self.assertNotIn("Saved baseline:", result)
            self.assertIn("Tagging provenance unchanged", result)
            self.assertIn("Source data:", result)

    def test_known_private_content_is_removed_from_manager_fields(self):
        row = action(action_text="Ask Guestperson Private: This confidential guest "
                     "passage should not appear.", owner="Guestperson")
        result = self.render([row], reviews(5))
        self.assertNotIn("Guestperson", result)
        self.assertNotIn("confidential guest passage", result)
        self.assertIn("[private content removed]", result)

    def test_explicit_legacy_link_and_empty_selection(self):
        legacy = action(dataset_tag="old-file")
        self.assertIn("ACTIVE ACTIONS (0)", self.render([legacy], []))
        self.assertIn("ACTIVE ACTIONS (1)", self.render([legacy], [], legacy_tag="old-file"))
        self.assertIn("ACTIVE ACTIONS (0)",
                      R.build_report([action()], "dataset-a", [], reviews(5)))

    def test_printable_sections_and_page_break_styling(self):
        actions = [
            action(action_text="Active kitchen task"),
            action(status="Done", action_text="Done cleaning task"),
            action(dataset_tag="dataset-b", action_text="Other dataset"),
            action(location="Elsewhere", action_text="Other location"),
        ]
        html_out = self.render_html(actions, reviews(5))
        # Sections are clearly separated
        self.assertIn("ACTIVE ACTIONS (1)", html_out)
        self.assertIn("COMPLETED ACTIONS (1)", html_out)
        self.assertNotIn("Other dataset", html_out)
        self.assertNotIn("Other location", html_out)
        # Check print styling requirements: @media print, @page, clean page breaks, break-inside avoid
        self.assertIn("@media print", html_out)
        self.assertIn("@page", html_out)
        self.assertIn("margin:", html_out)
        self.assertIn("break-before: page", html_out)
        self.assertIn("break-inside: avoid", html_out)
        # Shows action text, owner, status, due date
        self.assertIn("Active kitchen task", html_out)
        self.assertIn("Done cleaning task", html_out)
        self.assertIn("Shift lead", html_out)
        self.assertIn("2026-01-03", html_out)
        self.assertIn("(OVERDUE)", html_out)
        self.assertIn("Review trends do not prove that an action caused a change.", html_out)

    def test_printable_follow_up_comparisons_require_five_reviews(self):
        # Fewer than 5 reviews (4 reviews)
        rows_4 = reviews(4) + [dict(reviews(1)[0], date="2026-01-01")]
        html_4 = self.render_html([action()], rows_4)
        self.assertIn("4 newer reviews", html_4)
        self.assertIn("at least 5 are required", html_4)
        self.assertNotIn("Saved baseline:", html_4)
        self.assertNotIn("Change: -20.0", html_4)

        # Exactly 5 reviews: comparison appears
        html_5 = self.render_html([action()], reviews(5))
        self.assertIn("1 of 5 newer reviews", html_5)
        self.assertIn("Saved baseline: 40.0%", html_5)
        self.assertIn("Change: -20.0 percentage points", html_5)

        # Status Planned: comparison withheld
        planned_html = self.render_html([action(status="Planned")], reviews(8))
        self.assertNotIn("Saved baseline:", planned_html)
        self.assertIn("not started or has no start date", planned_html)

    def test_printable_filtering_and_provenance_withholding_match_txt(self):
        actions = [action(action_text="Scoped action"), action(dataset_tag="dataset-b", action_text="Unscoped action")]
        txt_out = self.render(actions, reviews(5))
        html_out = self.render_html(actions, reviews(5))
        self.assertIn("Scoped action", txt_out)
        self.assertIn("Scoped action", html_out)
        self.assertNotIn("Unscoped action", txt_out)
        self.assertNotIn("Unscoped action", html_out)

        # Provenance changed
        for baseline in [None, dict(PROVENANCE, rules_version="older")]:
            txt_prov = self.render([action(baseline_provenance=baseline)], reviews(5))
            html_prov = self.render_html([action(baseline_provenance=baseline)], reviews(5))
            self.assertIn("Comparison withheld", txt_prov)
            self.assertIn("Comparison withheld", html_prov)
            self.assertNotIn("Saved baseline:", txt_prov)
            self.assertNotIn("Saved baseline:", html_prov)

        # Source changed
        source_diff = source_cohort(
            [dict(location="Cafe", date="2026-01-01", rating=1, text="Long wait.")],
            "dataset-a", "Cafe", "2026-01-01")
        txt_src = self.render([action(baseline_source=source_diff)], reviews(5))
        html_src = self.render_html([action(baseline_source=source_diff)], reviews(5))
        self.assertIn("Comparison withheld", txt_src)
        self.assertIn("Comparison withheld", html_src)
        self.assertNotIn("Saved baseline:", txt_src)
        self.assertNotIn("Saved baseline:", html_src)

    def test_guest_names_raw_reviews_and_reply_drafts_completely_excluded(self):
        guest_name = "Guestperson Private"
        raw_passage = "This confidential guest passage should not appear."
        reply_draft = "Dear Guestperson, thank you for visiting us."
        row = action(action_text=f"Ask {guest_name}: {raw_passage} Reply: {reply_draft}",
                     owner="Guestperson")

        # In printable HTML report
        html_out = self.render_html([row], reviews(5))
        self.assertNotIn(guest_name, html_out)
        self.assertNotIn(raw_passage, html_out)
        self.assertIn("[private content removed]", html_out)

        # In weekly owner summary
        summary = R.A.weekly_action_summary([row], "dataset-a", ["Cafe"], reviews(5), today=date(2026, 1, 4))
        summary_text = "\n".join(summary)
        self.assertNotIn(guest_name, summary_text)
        self.assertNotIn(raw_passage, summary_text)
        self.assertIn("[private content removed]", summary_text)
        self.assertIn("Review trends do not prove an action caused a change.", summary_text)


class ActionReportAppTests(unittest.TestCase):
    def test_private_preview_download_and_empty_state(self):
        from streamlit.testing.v1 import AppTest
        from dataset_store import SAMPLE_ID
        # A copied entry point gives all mutable app storage a temporary base path.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = Path(__file__).with_name("app.py")
            (root / "app.py").write_text(app.read_text(encoding="utf-8"), encoding="utf-8")
            (root / "data").mkdir()
            with (root / "data/sample_reviews.csv").open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["review_id", "location", "date", "rating", "text", "reviewer"])
                for i in range(12):
                    writer.writerow([f"synthetic-{i}", "Cafe", f"2026-01-{i*2+2:02}",
                                     4, "Great food and slow service.", "Guestperson Private"])
            plan = action(dataset_tag=SAMPLE_ID)
            with patch.object(MI, "DB_PATH", root / "accounts.sqlite"):
                MI.set_account("test-manager", "synthetic-test-passphrase-only", {SAMPLE_ID: ["Cafe"]})
            with patch.object(R.A, "load_actions", return_value=[plan]), patch.object(
                    MI, "DB_PATH", root / "accounts.sqlite"):
                app_test = AppTest.from_file(str(root / "app.py"), default_timeout=30).run()
                self.assertFalse(app_test.exception)
                self.assertFalse(any(x.label == "Manager report preview" for x in app_test.text_area))
                self.assertFalse(any(x.proto.label == "Download manager action report (TXT)"
                                     for x in app_test.get("download_button")))
                password = next(x for x in app_test.text_input if x.label == "Manager report password")
                next(x for x in app_test.text_input if x.label == "Manager ID").set_value("test-manager")
                password.set_value("wrong")
                next(x for x in app_test.button if x.label == "Unlock restaurant dashboard").click().run()
                self.assertFalse(any(x.label == "Manager report preview" for x in app_test.text_area))
                next(x for x in app_test.text_input if x.label == "Manager report password").set_value(
                    "synthetic-test-passphrase-only")
                next(x for x in app_test.text_input if x.label == "Manager ID").set_value("test-manager")
                next(x for x in app_test.button if x.label == "Unlock restaurant dashboard").click().run()
                self.assertFalse(app_test.exception)
                preview = next(x for x in app_test.text_area if x.label == "Manager report preview")
                self.assertIn("Check kitchen handoffs", preview.value)
                self.assertNotIn("Guestperson", preview.value)
                button = next(x for x in app_test.button
                              if x.label == "Prepare secure report download")
                self.assertTrue(button.proto.disabled)
                check = next(x for x in app_test.checkbox
                             if x.label.startswith("I checked the report"))
                check.check().run()
                self.assertFalse(app_test.exception)
                button = next(x for x in app_test.button
                              if x.label == "Prepare secure report download")
                self.assertFalse(button.proto.disabled)
                button.click().run()
                links = app_test.get("link_button")
                self.assertTrue(links)
                link_labels = [x.label for x in links]
                self.assertIn("Download manager action report (TXT)", link_labels)
                self.assertIn("Download printable manager action report (HTML)", link_labels)
                self.assertFalse(any(x.proto.label == "Download manager action report (TXT)"
                                     for x in app_test.get("download_button")))
                # No review on Jan 3, but the report and its full-dataset counts remain available.
                next(x for x in app_test.slider if x.label == "Date range").set_value(
                    (date(2026, 1, 3), date(2026, 1, 3))).run()
                self.assertFalse(app_test.exception)
                self.assertTrue(any("No reviews match" in x.value for x in app_test.warning))
                self.assertTrue(any(x.label == "Manager report preview" for x in app_test.text_area))
            with patch.object(R.A, "load_actions", return_value=[]), patch.object(
                    MI, "DB_PATH", root / "accounts.sqlite"):
                app_test.run()
                self.assertFalse(app_test.exception)
                button = next(x for x in app_test.button
                              if x.label == "Prepare secure report download")
                self.assertTrue(button.proto.disabled)
                self.assertTrue(any("No action plans for this file" in i.value for i in app_test.info))
                next(x for x in app_test.button if x.label == "Lock manager report").click().run()
                self.assertFalse(any(x.label == "Manager report preview" for x in app_test.text_area))
            with patch.object(MI, "DB_PATH", root / "missing.sqlite"):
                app_test.run()
                self.assertFalse(app_test.exception)
                self.assertFalse(any(x.label == "Manager report preview" for x in app_test.text_area))
                self.assertTrue(any("Restaurant dashboard locked" in x.value for x in app_test.warning))


if __name__ == "__main__":
    unittest.main()
