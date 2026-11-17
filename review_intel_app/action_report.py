"""Internal action-only export. Never exports review records or reply drafts."""
import html
import re

import action_tracker as A


_privacy_filter = A.privacy_filter


def _collect_report_data(actions, dataset_tag, locations, reviews, *, legacy_tag=None,
                         provenance_by_location=None, timezones_by_location=None, today=None):
    selected = [a for a in actions if A.matches_dataset(a, dataset_tag, legacy_tag)
                and a.get("location") in set(locations)]
    selected.sort(key=lambda a: (a.get("location", ""), a.get("created_on", ""),
                                 a.get("action_id", "")))
    clean = _privacy_filter(reviews)
    groups = []
    for heading, completed in [("ACTIVE ACTIONS", False), ("COMPLETED ACTIONS", True)]:
        group_actions = [a for a in selected if (a.get("status") == "Done") == completed]
        action_entries = []
        for action in group_actions:
            location = action.get("location", "")
            overdue = A.is_overdue(action, today,
                                   timezones_by_location=timezones_by_location)
            result = A.follow_up(
                action, reviews,
                current_provenance=(provenance_by_location or {}).get(location),
                current_source_reviews=reviews, current_dataset_tag=dataset_tag)
            action_entries.append({
                "action": action,
                "location": location,
                "overdue": overdue,
                "result": result,
            })
        groups.append((heading, completed, action_entries))
    return clean, sorted(locations), groups


def build_report(actions, dataset_tag, locations, reviews, *, legacy_tag=None,
                 provenance_by_location=None, timezones_by_location=None, today=None):
    """Use full selected-dataset reviews, not the dashboard's date-filtered view."""
    clean, sorted_locs, groups = _collect_report_data(
        actions, dataset_tag, locations, reviews, legacy_tag=legacy_tag,
        provenance_by_location=provenance_by_location,
        timezones_by_location=timezones_by_location, today=today)
    lines = [
        "MANAGER ACTION REPORT",
        "Internal manager use only. Keep downloaded copies private.",
        "Scope: selected dataset and selected locations; all action statuses.",
        "Locations: " + ", ".join(clean(loc) for loc in sorted_locs),
        "Dashboard date and action-status filters do not limit this report.",
        "Review text, guest identity fields, and reply drafts are excluded.",
        "Known guest names and copied passages in action fields are redacted. "
        "Check for other private details before sharing.",
        "",
    ]
    for heading, completed, entries in groups:
        lines += [f"{heading} ({len(entries)})"]
        if not entries:
            lines += ["None.", ""]
        for entry in entries:
            action = entry["action"]
            location = entry["location"]
            overdue = entry["overdue"]
            result = entry["result"]
            lines += [
                f"Location: {clean(location)}",
                f"Theme: {clean(action.get('theme'))}",
                f"Action: {clean(action.get('action_text')) or 'Not described'}",
                f"Owner: {clean(action.get('owner')) or 'Not assigned'}",
                f"Status: {clean(action.get('status')) or 'Planned'}",
                f"Start date: {clean(action.get('start_date')) or 'Not set'}",
                f"Due date: {clean(action.get('due_date')) or 'Not set'}"
                + (" (OVERDUE)" if overdue else ""),
            ]
            lines.append("Comparability: " + clean(result["provenance_message"]))
            lines.append("Source data: " + clean(result["source_message"]))
            lines.append("Source comparison details: " + clean(result["source_details"]))
            if not result["ready"]:
                if result["reason"] == "not_started":
                    lines.append("Follow-up pending: action has not started or has no start date.")
                else:
                    lines.append(f"Follow-up pending: {result['review_count']} newer reviews; "
                                 f"at least {A.MIN_FOLLOWUP_REVIEWS} are required.")
            elif result["comparability_status"] != "unchanged":
                lines.append("Comparison withheld until baseline comparability is confirmed.")
            else:
                lines.append(
                    f"Follow-up: {result['mentions']} of {result['review_count']} newer reviews "
                    f"mention this complaint ({result['share']}%). "
                    f"Saved baseline: {result['baseline_share']}%. "
                    f"Change: {result['change_points']:+.1f} percentage points.")
            lines.append("")
    lines.append("Review trends do not prove that an action caused a change.")
    return "\n".join(lines)


def build_printable_report(actions, dataset_tag, locations, reviews, *, legacy_tag=None,
                           provenance_by_location=None, timezones_by_location=None, today=None):
    """Self-contained printable HTML report with print page-break styling."""
    clean, sorted_locs, groups = _collect_report_data(
        actions, dataset_tag, locations, reviews, legacy_tag=legacy_tag,
        provenance_by_location=provenance_by_location,
        timezones_by_location=timezones_by_location, today=today)

    locs_html = html.escape(", ".join(clean(loc) for loc in sorted_locs))

    sections_html = []
    for heading, completed, entries in groups:
        section_class = "completed" if completed else "active"
        sec_title = "COMPLETED ACTIONS" if completed else "ACTIVE ACTIONS"
        parts = [
            f'    <section class="report-section {section_class}">',
            f'      <h2 class="section-title">{html.escape(sec_title)} ({len(entries)})</h2>',
        ]
        if not entries:
            parts.append('      <p class="empty-section">None.</p>')
        else:
            for entry in entries:
                action = entry["action"]
                overdue = entry["overdue"]
                result = entry["result"]
                action_text = html.escape(clean(action.get("action_text")) or "Not described")
                owner_text = html.escape(clean(action.get("owner")) or "Not assigned")
                status_text = html.escape(clean(action.get("status")) or "Planned")
                due_date_raw = clean(action.get("due_date")) or "Not set"
                overdue_suffix = ' <span class="action-value overdue">(OVERDUE)</span>' if overdue else ""
                due_date_html = html.escape(due_date_raw) + overdue_suffix

                if not result["ready"]:
                    if result["reason"] == "not_started":
                        follow_up_text = "Follow-up pending: action has not started or has no start date."
                    else:
                        follow_up_text = (
                            f"Follow-up pending: {result['review_count']} newer reviews; "
                            f"at least {A.MIN_FOLLOWUP_REVIEWS} are required."
                        )
                elif result["comparability_status"] != "unchanged":
                    follow_up_text = "Comparison withheld until baseline comparability is confirmed."
                else:
                    follow_up_text = (
                        f"Follow-up: {result['mentions']} of {result['review_count']} newer reviews "
                        f"mention this complaint ({result['share']}%). "
                        f"Saved baseline: {result['baseline_share']}%. "
                        f"Change: {result['change_points']:+.1f} percentage points."
                    )
                follow_up_html = html.escape(follow_up_text)

                parts.append(
                    '      <div class="action-card">\n'
                    f'        <div class="action-row"><span class="action-label">Action:</span> <span class="action-value">{action_text}</span></div>\n'
                    f'        <div class="action-row"><span class="action-label">Owner:</span> <span class="action-value">{owner_text}</span></div>\n'
                    f'        <div class="action-row"><span class="action-label">Status:</span> <span class="action-value">{status_text}</span></div>\n'
                    f'        <div class="action-row"><span class="action-label">Due date:</span> <span class="action-value">{due_date_html}</span></div>\n'
                    f'        <div class="follow-up"><span class="action-label">Follow-up comparison:</span> <span class="action-value">{follow_up_html}</span></div>\n'
                    '      </div>'
                )
        parts.append('    </section>')
        sections_html.append("\n".join(parts))

    sections_joined = "\n".join(sections_html)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Manager Action Report</title>
  <style>
    @page {{
      margin: 1.5cm;
    }}
    @media print {{
      body {{
        margin: 0;
        padding: 0;
        background: #fff;
        color: #000;
      }}
      .report-section.completed {{
        break-before: page;
        page-break-before: always;
      }}
      .action-card {{
        break-inside: avoid;
        page-break-inside: avoid;
        box-shadow: none;
        border: 1px solid #999;
      }}
    }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
      line-height: 1.5;
      color: #222;
      margin: 2rem;
      background-color: #fff;
    }}
    .report-header {{
      border-bottom: 2px solid #ccc;
      padding-bottom: 1rem;
      margin-bottom: 1.5rem;
    }}
    .report-title {{
      margin: 0 0 0.5rem 0;
      font-size: 1.6rem;
      font-weight: 700;
    }}
    .report-meta {{
      color: #555;
      font-size: 0.9rem;
      margin: 0.2rem 0;
    }}
    .report-section {{
      margin-bottom: 2rem;
    }}
    .report-section.completed {{
      break-before: page;
      page-break-before: always;
    }}
    .section-title {{
      font-size: 1.25rem;
      font-weight: 600;
      border-bottom: 1px solid #ddd;
      padding-bottom: 0.4rem;
      margin-bottom: 1rem;
    }}
    .action-card {{
      border: 1px solid #ddd;
      border-radius: 4px;
      padding: 1rem;
      margin-bottom: 1rem;
      background-color: #fafafa;
      break-inside: avoid;
      page-break-inside: avoid;
    }}
    .action-row {{
      margin: 0.35rem 0;
      font-size: 0.95rem;
    }}
    .action-label {{
      font-weight: 600;
      color: #333;
    }}
    .action-value {{
      color: #111;
    }}
    .action-value.overdue {{
      color: #c00;
      font-weight: 600;
    }}
    .follow-up {{
      margin-top: 0.5rem;
      padding-top: 0.5rem;
      border-top: 1px dashed #ccc;
      font-size: 0.9rem;
      color: #333;
    }}
    .empty-section {{
      font-style: italic;
      color: #666;
      margin: 0.5rem 0;
    }}
    .disclaimer {{
      margin-top: 2rem;
      padding-top: 1rem;
      border-top: 1px solid #ccc;
      font-size: 0.85rem;
      color: #555;
      font-style: italic;
      break-inside: avoid;
    }}
  </style>
</head>
<body>
  <div class="report-header">
    <h1 class="report-title">MANAGER ACTION REPORT</h1>
    <div class="report-meta">Internal manager use only. Keep downloaded copies private.</div>
    <div class="report-meta">Scope: selected dataset and selected locations; all action statuses.</div>
    <div class="report-meta">Locations: {locs_html}</div>
    <div class="report-meta">Dashboard date and action-status filters do not limit this report.</div>
    <div class="report-meta">Review text, guest identity fields, and reply drafts are excluded.</div>
    <div class="report-meta">Known guest names and copied passages in action fields are redacted. Check for other private details before sharing.</div>
  </div>
{sections_joined}
  <p class="disclaimer">Review trends do not prove that an action caused a change.</p>
</body>
</html>"""


build_html_report = build_printable_report
