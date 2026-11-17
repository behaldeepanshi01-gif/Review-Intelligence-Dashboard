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


class WeeklyOwnerSummaryPrintableTests(unittest.TestCase):
    def _sample_period_reviews(self):
        return [
            dict(location="Cafe", date="2026-01-02", rating=4, reviewer="Guestperson Private",
                 text="This confidential guest passage should not appear.",
                 reply_draft="Private reply draft text should not leak."),
            dict(location="Cafe", date="2026-01-03", rating=5, reviewer="Another Guest",
                 text="Second private review sentence must remain excluded."),
            dict(location="Bistro", date="2026-01-03", rating=3, reviewer="Bistro Diner",
                 text="Third confidential dining comment must not appear."),
            dict(location="Elsewhere", date="2026-01-03", rating=1, reviewer="Hidden Guest",
                 text="Out of scope location review text."),
        ]

    def _sample_alerts(self):
        return [
            dict(location="Cafe", theme="Service Speed", change="2.1x",
                 recent_mentions=4, recent_share=28.5, baseline_share=13.5, severity="High"),
            dict(location="Elsewhere", theme="Hidden Theme", change="3.0x",
                 recent_mentions=5, recent_share=40.0, baseline_share=10.0, severity="High"),
        ]

    def _sample_staff(self):
        return [
            dict(location="Cafe", staff="Maya", mentions=6, positive=6, avg_rating=4.9),
            dict(location="Bistro", staff="Leo", mentions=3, positive=3, avg_rating=4.7),
            dict(location="Elsewhere", staff="HiddenStaff", mentions=9, positive=9, avg_rating=5.0),
        ]

    def test_executive_layout_metrics_scoping_and_nonmutation(self):
        period = self._sample_period_reviews()
        alerts = self._sample_alerts()
        staff = self._sample_staff()
        actions = [
            action(action_id="a1", location="Cafe", action_text="Active speed check"),
            action(action_id="a2", location="Cafe", status="Done", action_text="Completed item excluded"),
            action(action_id="a3", dataset_tag="dataset-b", action_text="Other dataset excluded"),
            action(action_id="a4", location="Elsewhere", action_text="Other location excluded"),
        ]
        orig_period = copy.deepcopy(period)
        orig_alerts = copy.deepcopy(alerts)
        orig_staff = copy.deepcopy(staff)
        orig_actions = copy.deepcopy(actions)

        html_out = R.build_printable_weekly_summary(
            period_reviews=period,
            alerts=alerts,
            staff_leaderboard=staff,
            urgent_reply_count=4,
            actions=actions,
            dataset_tag="dataset-a",
            locations=["Cafe", "Bistro"],
            reviews=reviews(5),
            date_range=("2026-01-01", "2026-01-07"),
            provenance_by_location={"Cafe": PROVENANCE, "Bistro": PROVENANCE},
            today=date(2026, 1, 4),
        )

        # Print CSS & structure
        self.assertIn("<!doctype html>", html_out)
        self.assertIn("@media print", html_out)
        self.assertIn("@page", html_out)
        self.assertIn("margin: 1.5cm;", html_out)
        self.assertIn("WEEKLY OWNER SUMMARY", html_out)
        self.assertIn("2026-01-01 to 2026-01-07", html_out)

        # Executive metrics present & scoped
        self.assertIn("4.00", html_out)  # (4+5+3)/3
        self.assertIn("4.50 stars", html_out)  # Cafe
        self.assertIn("3.00 stars", html_out)  # Bistro
        self.assertIn("LOCATION BREAKDOWN", html_out)
        self.assertIn("RISING COMPLAINT WATCH LIST (1)", html_out)
        self.assertIn("Service Speed", html_out)
        self.assertIn("2.1x", html_out)
        self.assertIn("MOST PRAISED STAFF (2)", html_out)
        self.assertIn("Maya", html_out)
        self.assertIn("6 mentions", html_out)
        self.assertIn("Urgent Reply Backlog", html_out)
        self.assertIn("ACTIVE MANAGER ACTIONS (1)", html_out)
        self.assertIn("Active speed check", html_out)
        self.assertIn("(OVERDUE)", html_out)
        self.assertIn("Review trends do not prove an action caused a change.", html_out)

        # Excluded: Done actions, out-of-scope dataset/location
        self.assertNotIn("Completed item excluded", html_out)
        self.assertNotIn("Other dataset excluded", html_out)
        self.assertNotIn("Other location excluded", html_out)
        self.assertNotIn("Elsewhere", html_out)
        self.assertNotIn("Hidden Theme", html_out)
        self.assertNotIn("HiddenStaff", html_out)

        # Inputs untouched
        self.assertEqual(period, orig_period)
        self.assertEqual(alerts, orig_alerts)
        self.assertEqual(staff, orig_staff)
        self.assertEqual(actions, orig_actions)

    def test_weekly_summary_five_review_threshold_and_comparability_gating(self):
        rows_4 = reviews(4) + [dict(reviews(1)[0], date="2026-01-01")]
        html_4 = R.build_printable_weekly_summary(
            period_reviews=self._sample_period_reviews(),
            actions=[action()],
            dataset_tag="dataset-a",
            locations=["Cafe"],
            reviews=rows_4,
            provenance_by_location={"Cafe": PROVENANCE},
            today=date(2026, 1, 4),
        )
        self.assertIn("4 newer reviews", html_4)
        self.assertIn("at least 5 are required", html_4)
        self.assertNotIn("Saved baseline:", html_4)

        html_5 = R.build_printable_weekly_summary(
            period_reviews=self._sample_period_reviews(),
            actions=[action()],
            dataset_tag="dataset-a",
            locations=["Cafe"],
            reviews=reviews(5),
            provenance_by_location={"Cafe": PROVENANCE},
            today=date(2026, 1, 4),
        )
        self.assertIn("1 of 5 newer reviews", html_5)
        self.assertIn("Saved baseline: 40.0%", html_5)
        self.assertIn("Change: -20.0 percentage points", html_5)

        html_planned = R.build_printable_weekly_summary(
            period_reviews=self._sample_period_reviews(),
            actions=[action(status="Planned")],
            dataset_tag="dataset-a",
            locations=["Cafe"],
            reviews=reviews(8),
            provenance_by_location={"Cafe": PROVENANCE},
            today=date(2026, 1, 4),
        )
        self.assertIn("not started or has no start date", html_planned)
        self.assertNotIn("Saved baseline:", html_planned)

        for bad_prov in [None, dict(PROVENANCE, rules_version="older")]:
            html_prov = R.build_printable_weekly_summary(
                period_reviews=self._sample_period_reviews(),
                actions=[action(baseline_provenance=bad_prov)],
                dataset_tag="dataset-a",
                locations=["Cafe"],
                reviews=reviews(5),
                provenance_by_location={"Cafe": PROVENANCE},
                today=date(2026, 1, 4),
            )
            self.assertIn("Comparison withheld", html_prov)
            self.assertNotIn("Saved baseline:", html_prov)

    def test_weekly_summary_privacy_and_html_escaping(self):
        guest_name = "Guestperson Private"
        raw_passage = "This confidential guest passage should not appear."
        reply_draft = "Private reply draft text should not leak."
        injected = action(
            action_text=f"Follow up with {guest_name}: {raw_passage} <script>alert(1)</script>",
            owner="Guestperson",
        )
        html_out = R.build_printable_weekly_summary(
            period_reviews=self._sample_period_reviews(),
            alerts=[dict(location="Cafe", theme="<b>Wait</b>", change="2.0x", severity="High")],
            staff_leaderboard=[dict(location="Cafe", staff="Maya <i>Lead</i>", mentions=4, avg_rating=4.8)],
            urgent_reply_count=2,
            actions=[injected],
            dataset_tag="dataset-a",
            locations=["Cafe"],
            reviews=reviews(5),
            provenance_by_location={"Cafe": PROVENANCE},
            today=date(2026, 1, 4),
        )
        self.assertNotIn(guest_name, html_out)
        self.assertNotIn("Guestperson", html_out)
        self.assertNotIn(raw_passage, html_out)
        self.assertNotIn(reply_draft, html_out)
        self.assertNotIn("Another Guest", html_out)
        self.assertNotIn("Second private review sentence", html_out)
        self.assertIn("[private content removed]", html_out)
        self.assertNotIn("<script>alert(1)</script>", html_out)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html_out)
        self.assertNotIn("<b>Wait</b>", html_out)
        self.assertIn("&lt;b&gt;Wait&lt;/b&gt;", html_out)

    def test_weekly_summary_empty_locations_fails_closed(self):
        html_out = R.build_printable_weekly_summary(
            period_reviews=self._sample_period_reviews(),
            alerts=self._sample_alerts(),
            staff_leaderboard=self._sample_staff(),
            urgent_reply_count=0,
            actions=[action()],
            dataset_tag="dataset-a",
            locations=[],
            reviews=reviews(5),
            today=date(2026, 1, 4),
        )
        self.assertIn("ACTIVE MANAGER ACTIONS (0)", html_out)
        self.assertNotIn("Check kitchen handoffs", html_out)
        self.assertNotIn("Service Speed", html_out)
        self.assertNotIn("Maya", html_out)


class HighVolumePrintPaginationStressTests(unittest.TestCase):
    """Task #141 stress tests: 20-50+ active and completed actions across multiple locations."""

    def _build_stress_fixture(self):
        locations = [
            "Bistro North",
            "Cafe Central",
            "Grill West",
            "Kitchen South",
            "Patio East",
        ]
        # Cafe Central & Grill West get >= 5 newer reviews (comparison ready);
        # Bistro North gets 3 newer reviews (< 5 threshold -> pending);
        # Kitchen South gets 6 newer reviews but changed provenance (-> withheld);
        # Patio East gets 5 newer reviews with Planned status (-> not started).
        review_counts = {
            "Bistro North": 3,
            "Cafe Central": 7,
            "Grill West": 5,
            "Kitchen South": 6,
            "Patio East": 5,
        }
        all_reviews = []
        guest_names = []
        raw_passages = []
        reply_drafts = []

        idx = 0
        for loc, count in review_counts.items():
            for i in range(count):
                guest = f"Secretguest Alpha{idx}"
                passage = f"Confidential dining passage number {idx} should never leak."
                draft = f"Unpublished reply draft number {idx} for internal review only."
                guest_names.append(guest)
                raw_passages.append(passage)
                reply_drafts.append(draft)
                all_reviews.append({
                    "location": loc,
                    "date": f"2026-01-{2 + (i % 15):02}",
                    "rating": 2 if i == 0 else 4,
                    "reviewer": guest,
                    "text": passage,
                    "reply_draft": draft,
                    "themes_neg": ["service_speed"] if i == 0 else [],
                })
                idx += 1

        # Add an out-of-scope location review as a decoy
        guest_names.append("Outsider Guestname")
        raw_passages.append("Outsider location confidential review text.")
        all_reviews.append({
            "location": "Unassigned Flagship",
            "date": "2026-01-05",
            "rating": 1,
            "reviewer": "Outsider Guestname",
            "text": "Outsider location confidential review text.",
            "themes_neg": ["service_speed"],
        })

        provenance_by_location = {loc: dict(PROVENANCE) for loc in locations}
        actions = []

        # 35 active actions (7 per location)
        for i in range(35):
            loc = locations[i % len(locations)]
            leaked_guest = guest_names[i % len(guest_names)]
            leaked_passage = raw_passages[i % len(raw_passages)]
            status = "Planned" if loc == "Patio East" else "In progress"
            prov = (
                dict(PROVENANCE, rules_version="older-rules")
                if loc == "Kitchen South" else dict(PROVENANCE)
            )
            due = "2026-01-03" if i % 2 == 0 else "2026-01-20"
            text_body = (
                f"Active task {i:02d} at {loc}: check {leaked_guest} note - {leaked_passage}"
                if i % 5 == 0 else f"Active task {i:02d} at {loc}: streamline pass handoffs"
            )
            actions.append(action(
                action_id=f"act-{i:03d}",
                created_on=f"2026-01-{(i % 20) + 1:02}",
                location=loc,
                theme="Service Speed",
                theme_key="service_speed",
                action_text=text_body,
                owner=leaked_guest if i % 7 == 0 else f"Manager {i % 5}",
                status=status,
                start_date="2026-01-01",
                due_date=due,
                baseline_share=40.0,
                baseline_provenance=prov,
                alert_end_date="2026-01-01",
                baseline_source=source_cohort([], "dataset-a", loc, "2026-01-01"),
            ))

        # 25 completed actions (5 per location) -> total 60 in-scope actions!
        for i in range(25):
            loc = locations[i % len(locations)]
            leaked_guest = guest_names[(i + 10) % len(guest_names)]
            leaked_passage = raw_passages[(i + 10) % len(raw_passages)]
            text_body = (
                f"Completed task {i:02d} at {loc}: resolved {leaked_guest} issue - {leaked_passage}"
                if i % 4 == 0 else f"Completed task {i:02d} at {loc}: retrained host stand"
            )
            actions.append(action(
                action_id=f"done-{i:03d}",
                created_on=f"2026-01-{(i % 15) + 1:02}",
                location=loc,
                theme="Service Speed",
                theme_key="service_speed",
                action_text=text_body,
                owner=f"Lead {i % 5}",
                status="Done",
                start_date="2026-01-01",
                due_date="2026-01-10",
                baseline_share=40.0,
                baseline_provenance=dict(PROVENANCE),
                alert_end_date="2026-01-01",
                baseline_source=source_cohort([], "dataset-a", loc, "2026-01-01"),
            ))

        # Out-of-scope decoys
        actions.append(action(action_id="decoy-ds", dataset_tag="dataset-z",
                              location="Cafe Central", action_text="DECOY DATASET ACTION"))
        actions.append(action(action_id="decoy-loc", dataset_tag="dataset-a",
                              location="Unassigned Flagship", action_text="DECOY LOCATION ACTION"))

        alerts = [
            dict(location=loc, theme=f"Complaint Theme {j}", change=f"{1.6 + 0.2 * j:.1f}x",
                 recent_mentions=3 + j, recent_share=15.0 + j * 3, baseline_share=8.0,
                 severity="High" if j % 2 == 0 else "Medium")
            for j, loc in enumerate(locations * 2)
        ]
        staff = [
            dict(location=loc, staff=f"TeamMember {j}", mentions=10 - j, positive=10 - j, avg_rating=4.9 - 0.05 * j)
            for j, loc in enumerate(locations * 2)
        ]
        return {
            "locations": locations,
            "reviews": all_reviews,
            "provenance": provenance_by_location,
            "actions": actions,
            "alerts": alerts,
            "staff": staff,
            "guest_names": guest_names,
            "raw_passages": raw_passages,
            "reply_drafts": reply_drafts,
        }

    def _assert_pagination_css(self, html_out):
        for rule in (
            "@page",
            "@media print",
            "break-inside: avoid",
            "page-break-inside: avoid",
            "break-before: page",
            "page-break-before: always",
            "break-after: avoid",
            "page-break-after: avoid",
            "orphans: 3",
            "widows: 3",
            ".section-lead",
            "display: table-header-group",
        ):
            self.assertIn(rule, html_out, f"Missing required pagination CSS rule: {rule}")

    def test_high_volume_manager_action_report_pagination_gating_and_privacy(self):
        import report_downloads as D
        fx = self._build_stress_fixture()
        html_out = R.build_printable_report(
            fx["actions"], "dataset-a", fx["locations"], fx["reviews"],
            provenance_by_location=fx["provenance"],
            today=date(2026, 1, 4),
        )

        # 1. Pagination CSS rules
        self._assert_pagination_css(html_out)

        # 2. Section separation & heading-to-first-card containment
        self.assertIn("ACTIVE ACTIONS (35)", html_out)
        self.assertIn("COMPLETED ACTIONS (25)", html_out)
        active_idx = html_out.index('<section class="report-section active">')
        completed_idx = html_out.index('<section class="report-section completed">')
        self.assertLess(active_idx, completed_idx)
        self.assertEqual(html_out.count('<div class="section-lead">'), 2)
        self.assertEqual(html_out.count('<div class="action-card">'), 60)

        # 3. Scope isolation
        self.assertNotIn("DECOY DATASET ACTION", html_out)
        self.assertNotIn("DECOY LOCATION ACTION", html_out)
        self.assertNotIn("Unassigned Flagship", html_out)

        # 4. Threshold & comparability gating across locations (verified per card)
        cards = html_out.split('<div class="action-card">')[1:]
        self.assertEqual(len(cards), 60)
        for card in cards:
            if "Bistro North" in card:
                self.assertIn("Follow-up pending: 3 newer reviews; at least 5 are required.", card)
                self.assertNotIn("Saved baseline:", card)
            elif "Kitchen South" in card and "Status:</span> <span class=\"action-value\">In progress" in card:
                self.assertIn("Comparison withheld until baseline comparability is confirmed.", card)
                self.assertNotIn("Saved baseline:", card)
            elif "Patio East" in card and "Status:</span> <span class=\"action-value\">Planned" in card:
                self.assertIn("Follow-up pending: action has not started or has no start date.", card)
                self.assertNotIn("Saved baseline:", card)
            elif "Cafe Central" in card:
                self.assertIn("1 of 7 newer reviews mention this complaint", card)
                self.assertIn("Saved baseline: 40.0%", card)
            elif "Grill West" in card:
                self.assertIn("1 of 5 newer reviews mention this complaint", card)
                self.assertIn("Saved baseline: 40.0%", card)

        # 5. Zero guest-name, raw-text, or reply-draft leakage
        for secret in fx["guest_names"] + fx["raw_passages"] + fx["reply_drafts"]:
            self.assertNotIn(secret, html_out)
        self.assertIn("[private content removed]", html_out)

        # 6. Fits safely within secure download byte budget
        self.assertLess(len(html_out.encode("utf-8")), D.MAX_REPORT_BYTES)

    def test_high_volume_weekly_owner_summary_pagination_gating_and_privacy(self):
        import report_downloads as D
        fx = self._build_stress_fixture()
        html_out = R.build_printable_weekly_summary(
            period_reviews=fx["reviews"],
            alerts=fx["alerts"],
            staff_leaderboard=fx["staff"],
            urgent_reply_count=14,
            actions=fx["actions"],
            dataset_tag="dataset-a",
            locations=fx["locations"],
            reviews=fx["reviews"],
            date_range=("2026-01-01", "2026-01-17"),
            provenance_by_location=fx["provenance"],
            today=date(2026, 1, 4),
        )

        # 1. Pagination CSS rules
        self._assert_pagination_css(html_out)

        # 2. Executive sections cleanly separated from Active Manager Actions
        loc_idx = html_out.index("LOCATION BREAKDOWN")
        watch_idx = html_out.index("RISING COMPLAINT WATCH LIST (10)")
        staff_idx = html_out.index("MOST PRAISED STAFF (10)")
        actions_idx = html_out.index('<section class="report-section actions-section">')
        self.assertLess(loc_idx, watch_idx)
        self.assertLess(watch_idx, staff_idx)
        self.assertLess(staff_idx, actions_idx)

        # 3. High-volume active action count (35 active; 0 completed leaked)
        self.assertIn("ACTIVE MANAGER ACTIONS (35)", html_out)
        self.assertEqual(html_out.count('<div class="action-card">'), 35)
        self.assertNotIn("Completed task 00", html_out)
        self.assertNotIn("DECOY DATASET ACTION", html_out)
        self.assertNotIn("DECOY LOCATION ACTION", html_out)
        self.assertNotIn("Unassigned Flagship", html_out)

        # 4. Threshold & comparability gating across locations (verified per card)
        cards = html_out.split('<div class="action-card">')[1:]
        self.assertEqual(len(cards), 35)
        for card in cards:
            if "Bistro North" in card:
                self.assertIn("Follow-up pending: 3 newer reviews; at least 5 are required.", card)
                self.assertNotIn("Saved baseline:", card)
            elif "Kitchen South" in card:
                self.assertIn("Comparison withheld until baseline comparability is confirmed.", card)
                self.assertNotIn("Saved baseline:", card)
            elif "Patio East" in card:
                self.assertIn("Follow-up pending: action has not started or has no start date.", card)
                self.assertNotIn("Saved baseline:", card)
            elif "Cafe Central" in card:
                self.assertIn("1 of 7 newer reviews mention this complaint", card)
                self.assertIn("Saved baseline: 40.0%", card)
            elif "Grill West" in card:
                self.assertIn("1 of 5 newer reviews mention this complaint", card)
                self.assertIn("Saved baseline: 40.0%", card)
        self.assertIn("Review trends do not prove an action caused a change.", html_out)

        # 5. Zero guest-name, raw-text, or reply-draft leakage
        for secret in fx["guest_names"] + fx["raw_passages"] + fx["reply_drafts"]:
            self.assertNotIn(secret, html_out)
        self.assertIn("[private content removed]", html_out)

        # 6. Fits safely within secure download byte budget
        self.assertLess(len(html_out.encode("utf-8")), D.MAX_REPORT_BYTES)


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
