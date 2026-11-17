"""Internal action-only and executive summary exports. Never exports review records or reply drafts."""
import html

import action_tracker as A


_privacy_filter = A.privacy_filter


def _to_records(obj):
    """Convert a DataFrame or iterable of dicts to a new list of dicts without mutating input."""
    if obj is None:
        return []
    if hasattr(obj, "to_dict") and hasattr(obj, "empty"):
        return [] if obj.empty else obj.to_dict("records")
    return [dict(item) for item in obj]


def _format_follow_up_text(result):
    if not result["ready"]:
        if result["reason"] == "not_started":
            return "Follow-up pending: action has not started or has no start date."
        return (
            f"Follow-up pending: {result['review_count']} newer reviews; "
            f"at least {A.MIN_FOLLOWUP_REVIEWS} are required."
        )
    if result["comparability_status"] != "unchanged":
        return "Comparison withheld until baseline comparability is confirmed."
    return (
        f"Follow-up: {result['mentions']} of {result['review_count']} newer reviews "
        f"mention this complaint ({result['share']}%). "
        f"Saved baseline: {result['baseline_share']}%. "
        f"Change: {result['change_points']:+.1f} percentage points."
    )


def _shared_print_css():
    return """    @page {
      margin: 1.5cm;
    }
    * {
      box-sizing: border-box;
    }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
      line-height: 1.5;
      color: #222;
      margin: 2rem;
      background-color: #fff;
      orphans: 3;
      widows: 3;
    }
    p, li, td, div {
      orphans: 3;
      widows: 3;
    }
    h1, h2, h3, .section-title {
      break-after: avoid;
      page-break-after: avoid;
      break-inside: avoid;
      page-break-inside: avoid;
    }
    .section-lead {
      break-inside: avoid;
      page-break-inside: avoid;
    }
    .section-title + .action-card,
    .section-title + .data-table,
    .section-title + .empty-section,
    .section-title + .summary-callout {
      break-before: avoid;
      page-break-before: avoid;
    }
    .report-header {
      border-bottom: 2px solid #2c3e50;
      padding-bottom: 1rem;
      margin-bottom: 1.5rem;
      break-inside: avoid;
      page-break-inside: avoid;
    }
    .report-title {
      margin: 0 0 0.45rem 0;
      font-size: 1.6rem;
      font-weight: 700;
      color: #1a252f;
      letter-spacing: 0.02em;
    }
    .report-meta {
      color: #555;
      font-size: 0.88rem;
      margin: 0.2rem 0;
    }
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 0.75rem;
      margin-bottom: 1.5rem;
      break-inside: avoid;
      page-break-inside: avoid;
    }
    .kpi-card {
      border: 1px solid #d5dbe1;
      border-top: 3px solid #2c3e50;
      border-radius: 4px;
      padding: 0.75rem 0.9rem;
      background-color: #f8fafc;
      break-inside: avoid;
      page-break-inside: avoid;
    }
    .kpi-label {
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: #55606e;
      margin-bottom: 0.25rem;
      font-weight: 600;
    }
    .kpi-value {
      font-size: 1.3rem;
      font-weight: 700;
      color: #111;
    }
    .kpi-sub {
      font-size: 0.8rem;
      color: #555;
      margin-top: 0.15rem;
    }
    .report-section {
      margin-bottom: 1.75rem;
    }
    .report-section.completed,
    .report-section.actions-section {
      break-before: page;
      page-break-before: always;
    }
    .section-title {
      font-size: 1.2rem;
      font-weight: 700;
      color: #1a252f;
      border-bottom: 1px solid #cfd6de;
      padding-bottom: 0.35rem;
      margin: 0 0 0.9rem 0;
    }
    .summary-callout {
      border-left: 4px solid #2c3e50;
      background-color: #f4f6f8;
      padding: 0.7rem 1rem;
      margin-bottom: 0.9rem;
      font-size: 0.94rem;
      break-inside: avoid;
      page-break-inside: avoid;
    }
    .data-table {
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 1rem;
      font-size: 0.9rem;
    }
    .data-table thead {
      display: table-header-group;
    }
    .data-table tfoot {
      display: table-footer-group;
    }
    .data-table tr {
      break-inside: avoid;
      page-break-inside: avoid;
    }
    .data-table th,
    .data-table td {
      border: 1px solid #d5dbe1;
      padding: 0.48rem 0.65rem;
      text-align: left;
      vertical-align: top;
      break-inside: avoid;
    }
    .data-table th {
      background-color: #f0f3f6;
      font-weight: 600;
      color: #222;
    }
    .data-table td.num,
    .data-table th.num {
      text-align: right;
      white-space: nowrap;
    }
    .severity-high {
      color: #b00020;
      font-weight: 700;
    }
    .severity-medium {
      color: #8a5300;
      font-weight: 600;
    }
    .action-card {
      border: 1px solid #d5dbe1;
      border-radius: 4px;
      padding: 0.85rem 1rem;
      margin-bottom: 0.85rem;
      background-color: #fafafa;
      break-inside: avoid;
      page-break-inside: avoid;
    }
    .action-row {
      margin: 0.28rem 0;
      font-size: 0.92rem;
    }
    .action-label {
      font-weight: 600;
      color: #333;
    }
    .action-value {
      color: #111;
    }
    .action-value.overdue {
      color: #c00;
      font-weight: 700;
    }
    .follow-up {
      margin-top: 0.45rem;
      padding-top: 0.45rem;
      border-top: 1px dashed #c8cdd3;
      font-size: 0.88rem;
      color: #333;
    }
    .meta-note {
      margin-top: 0.25rem;
      font-size: 0.82rem;
      color: #555;
    }
    .empty-section {
      font-style: italic;
      color: #666;
      margin: 0.4rem 0;
    }
    .disclaimer {
      margin-top: 1.75rem;
      padding-top: 0.9rem;
      border-top: 1px solid #ccc;
      font-size: 0.84rem;
      color: #555;
      font-style: italic;
      break-inside: avoid;
      page-break-inside: avoid;
    }
    @media print {
      body {
        margin: 0;
        padding: 0;
        background: #fff;
        color: #000;
        orphans: 3;
        widows: 3;
      }
      p, li, td, div {
        orphans: 3;
        widows: 3;
      }
      h1, h2, h3, .section-title {
        break-after: avoid;
        page-break-after: avoid;
        break-inside: avoid;
        page-break-inside: avoid;
      }
      .section-lead {
        break-inside: avoid;
        page-break-inside: avoid;
      }
      .report-header,
      .kpi-grid,
      .kpi-card,
      .summary-callout,
      .disclaimer {
        break-inside: avoid;
        page-break-inside: avoid;
        box-shadow: none;
      }
      .report-section.completed,
      .report-section.actions-section {
        break-before: page;
        page-break-before: always;
      }
      .data-table thead {
        display: table-header-group;
      }
      .data-table tr {
        break-inside: avoid;
        page-break-inside: avoid;
      }
      .action-card {
        break-inside: avoid;
        page-break-inside: avoid;
        box-shadow: none;
        border: 1px solid #999;
        background-color: #fff;
      }
      .kpi-card {
        border: 1px solid #999;
        border-top: 3px solid #000;
        background-color: #fff;
      }
      .summary-callout {
        background-color: #fff;
        border: 1px solid #bbb;
        border-left: 4px solid #000;
      }
    }"""


def _render_action_card(entry, clean):
    action = entry["action"]
    overdue = entry["overdue"]
    result = entry["result"]
    location_text = html.escape(clean(entry["location"]) or "Unknown location")
    theme_text = html.escape(clean(action.get("theme")) or "General")
    action_text = html.escape(clean(action.get("action_text")) or "Not described")
    owner_text = html.escape(clean(action.get("owner")) or "Not assigned")
    status_text = html.escape(clean(action.get("status")) or "Planned")
    start_date_text = html.escape(clean(action.get("start_date")) or "Not set")
    due_date_raw = clean(action.get("due_date")) or "Not set"
    overdue_suffix = ' <span class="action-value overdue">(OVERDUE)</span>' if overdue else ""
    due_date_html = html.escape(due_date_raw) + overdue_suffix
    follow_up_html = html.escape(_format_follow_up_text(result))
    prov_html = html.escape(clean(result["provenance_message"]))
    src_html = html.escape(clean(result["source_message"]))

    return (
        '      <div class="action-card">\n'
        f'        <div class="action-row"><span class="action-label">Location &amp; Theme:</span> '
        f'<span class="action-value">{location_text} &middot; {theme_text}</span></div>\n'
        f'        <div class="action-row"><span class="action-label">Action:</span> '
        f'<span class="action-value">{action_text}</span></div>\n'
        f'        <div class="action-row"><span class="action-label">Owner:</span> '
        f'<span class="action-value">{owner_text}</span></div>\n'
        f'        <div class="action-row"><span class="action-label">Status:</span> '
        f'<span class="action-value">{status_text}</span></div>\n'
        f'        <div class="action-row"><span class="action-label">Start date:</span> '
        f'<span class="action-value">{start_date_text}</span> &nbsp;|&nbsp; '
        f'<span class="action-label">Due date:</span> '
        f'<span class="action-value">{due_date_html}</span></div>\n'
        f'        <div class="follow-up"><span class="action-label">Follow-up comparison:</span> '
        f'<span class="action-value">{follow_up_html}</span>'
        f'<div class="meta-note">{prov_html} &middot; {src_html}</div></div>\n'
        '      </div>'
    )


def _render_card_section(section_class, title, cards, empty_text="None."):
    """Keep section heading tethered to its first card (or empty notice) via .section-lead."""
    parts = [f'    <section class="report-section {section_class}">']
    if not cards:
        parts.append(
            '      <div class="section-lead">\n'
            f'        <h2 class="section-title">{html.escape(title)}</h2>\n'
            f'        <p class="empty-section">{html.escape(empty_text)}</p>\n'
            '      </div>'
        )
    else:
        parts.append(
            '      <div class="section-lead">\n'
            f'        <h2 class="section-title">{html.escape(title)}</h2>\n'
            f'{cards[0]}\n'
            '      </div>'
        )
        parts.extend(cards[1:])
    parts.append('    </section>')
    return "\n".join(parts)


def _collect_report_data(actions, dataset_tag, locations, reviews, *, legacy_tag=None,
                         provenance_by_location=None, timezones_by_location=None, today=None,
                         source_reviews=None, now=None):
    selected = [a for a in actions if A.matches_dataset(a, dataset_tag, legacy_tag)
                and a.get("location") in set(locations)]
    selected.sort(key=lambda a: (a.get("location", ""), a.get("created_on", ""),
                                 a.get("action_id", "")))
    corpus = list(reviews or [])
    if source_reviews:
        corpus.extend(source_reviews)
    clean = _privacy_filter(corpus)
    effective_source = source_reviews if source_reviews is not None else reviews
    groups = []
    for heading, completed in [("ACTIVE ACTIONS", False), ("COMPLETED ACTIONS", True)]:
        group_actions = [a for a in selected if (a.get("status") == "Done") == completed]
        action_entries = []
        for action in group_actions:
            location = action.get("location", "")
            overdue = A.is_overdue(action, today,
                                   timezones_by_location=timezones_by_location, now=now)
            result = A.follow_up(
                action, reviews,
                current_provenance=(provenance_by_location or {}).get(location),
                current_source_reviews=effective_source, current_dataset_tag=dataset_tag)
            action_entries.append({
                "action": action,
                "location": location,
                "overdue": overdue,
                "result": result,
            })
        groups.append((heading, completed, action_entries))
    return clean, sorted(set(locations)), groups


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
            lines.append(_format_follow_up_text(result))
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
        sec_title = f"{heading} ({len(entries)})"
        cards = [_render_action_card(entry, clean) for entry in entries]
        sections_html.append(_render_card_section(section_class, sec_title, cards, empty_text="None."))

    sections_joined = "\n".join(sections_html)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Manager Action Report</title>
  <style>
{_shared_print_css()}
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


def build_printable_weekly_summary(
    *,
    period_reviews=None,
    alerts=None,
    staff_leaderboard=None,
    urgent_reply_count=0,
    actions=None,
    dataset_tag="",
    locations=(),
    reviews=(),
    date_range=None,
    legacy_tag=None,
    provenance_by_location=None,
    source_reviews=None,
    timezones_by_location=None,
    today=None,
    now=None,
):
    """Self-contained printable executive HTML for the Weekly Owner Summary.

    Excludes guest names, raw review passages, and reply drafts. Reuses dataset/location
    scoping, 5-newer-review threshold gating, and comparability checks.
    """
    selected_locations = set(locations)
    sorted_locs = sorted(selected_locations)

    period_rows_all = _to_records(period_reviews)
    review_rows_all = _to_records(reviews)
    source_rows_all = _to_records(source_reviews) if source_reviews is not None else None

    # Build privacy filter across every review set so no guest names or passages can leak.
    privacy_corpus = list(review_rows_all) + list(period_rows_all)
    if source_rows_all:
        privacy_corpus.extend(source_rows_all)
    clean = _privacy_filter(privacy_corpus)

    # Filter weekly metrics to selected locations (fail closed if locations is empty).
    period_rows = [
        r for r in period_rows_all
        if r.get("location") in selected_locations
    ]
    ratings = [float(r["rating"]) for r in period_rows if r.get("rating") is not None]
    total_period_reviews = len(period_rows)
    avg_rating_str = f"{(sum(ratings) / len(ratings)):.2f}" if ratings else "N/A"

    # Location breakdown
    loc_buckets = {}
    for row in period_rows:
        loc = row.get("location", "")
        bucket = loc_buckets.setdefault(loc, [])
        if row.get("rating") is not None:
            bucket.append(float(row["rating"]))
    location_breakdown = []
    for loc in sorted(loc_buckets):
        vals = loc_buckets[loc]
        location_breakdown.append({
            "location": loc,
            "count": len(vals),
            "avg_rating": f"{(sum(vals) / len(vals)):.2f}" if vals else "N/A",
        })

    # Rising complaint watch list (scoped to selected_locations)
    alert_rows = [
        row for row in _to_records(alerts)
        if row.get("location") in selected_locations
    ]

    # Most praised staff (scoped to selected_locations)
    staff_rows = [
        row for row in _to_records(staff_leaderboard)
        if row.get("location") in selected_locations
    ]

    # Active manager actions (same dataset/location/status filtering as weekly_action_summary)
    active_actions = [
        row for row in (actions or [])
        if A.matches_dataset(row, dataset_tag, legacy_tag)
        and row.get("location") in selected_locations
        and row.get("status") != "Done"
    ]
    active_actions.sort(
        key=lambda row: (row.get("created_on", ""), row.get("location", ""), row.get("action_id", "")),
        reverse=True,
    )

    effective_source = source_rows_all if source_rows_all is not None else review_rows_all
    action_entries = []
    overdue_count = 0
    for action in active_actions:
        raw_location = action.get("location", "")
        overdue = A.is_overdue(
            action, today,
            timezones_by_location=timezones_by_location, now=now,
        )
        if overdue:
            overdue_count += 1
        result = A.follow_up(
            action, review_rows_all,
            current_provenance=(provenance_by_location or {}).get(raw_location),
            current_source_reviews=effective_source,
            current_dataset_tag=dataset_tag,
        )
        action_entries.append({
            "action": action,
            "location": raw_location,
            "overdue": overdue,
            "result": result,
        })

    # Format period header
    period_meta_html = ""
    if date_range and len(date_range) == 2:
        start_s = html.escape(str(date_range[0]))
        end_s = html.escape(str(date_range[1]))
        period_meta_html = f'\n    <div class="report-meta">Period: {start_s} to {end_s}</div>'
    elif isinstance(date_range, str) and date_range.strip():
        period_meta_html = f'\n    <div class="report-meta">Period: {html.escape(clean(date_range))}</div>'

    locs_html = html.escape(", ".join(clean(loc) for loc in sorted_locs)) if sorted_locs else "None selected"

    # KPI summary strip
    urgent_count = max(0, int(urgent_reply_count or 0))
    overdue_sub = f"{overdue_count} overdue" if overdue_count else "None overdue"
    if staff_rows:
        top = staff_rows[0]
        top_staff_name = html.escape(clean(top.get("staff")) or "Staff")
        top_staff_loc = html.escape(clean(top.get("location")) or "")
        top_staff_mentions = int(top.get("mentions", 0))
        top_staff_kpi = f"{top_staff_name}"
        top_staff_sub = f"{top_staff_loc} ({top_staff_mentions} mentions)"
    else:
        top_staff_kpi = "None noted"
        top_staff_sub = "No staff mentions in period"

    kpi_html = f"""  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-label">Reviews This Period</div>
      <div class="kpi-value">{total_period_reviews}</div>
      <div class="kpi-sub">Across {len(location_breakdown)} active location(s)</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Average Rating</div>
      <div class="kpi-value">{html.escape(avg_rating_str)} &#9733;</div>
      <div class="kpi-sub">Selected period average</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Urgent Reply Backlog</div>
      <div class="kpi-value">{urgent_count}</div>
      <div class="kpi-sub">High-urgency reviews needing reply</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Active Manager Actions</div>
      <div class="kpi-value">{len(action_entries)}</div>
      <div class="kpi-sub">{html.escape(overdue_sub)}</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Most Praised Staff</div>
      <div class="kpi-value">{top_staff_kpi}</div>
      <div class="kpi-sub">{top_staff_sub}</div>
    </div>
  </div>"""

    # Section 1: Location Breakdown
    if location_breakdown:
        loc_tr = "\n".join(
            "          <tr>"
            f"<td>{html.escape(clean(row['location']))}</td>"
            f"<td class=\"num\">{row['count']}</td>"
            f"<td class=\"num\">{html.escape(row['avg_rating'])} stars</td>"
            "</tr>"
            for row in location_breakdown
        )
        loc_section_html = (
            '    <section class="report-section summary-section">\n'
            '      <h2 class="section-title">LOCATION BREAKDOWN</h2>\n'
            '      <table class="data-table">\n'
            '        <thead><tr><th>Location</th><th class="num">Reviews</th><th class="num">Average Rating</th></tr></thead>\n'
            '        <tbody>\n'
            f'{loc_tr}\n'
            '        </tbody>\n'
            '      </table>\n'
            '    </section>'
        )
    else:
        loc_section_html = _render_card_section(
            "summary-section",
            "LOCATION BREAKDOWN",
            [],
            empty_text="No reviews for the selected period and locations.",
        )

    # Section 2: Rising Complaint Watch List
    if alert_rows:
        alert_tr_list = []
        for row in alert_rows:
            loc_s = html.escape(clean(row.get("location")) or "Location")
            theme_s = html.escape(clean(row.get("theme")) or "Theme")
            change_s = html.escape(clean(row.get("change")) or "rising")
            sev_raw = clean(row.get("severity")) or ""
            sev_cls = "severity-high" if sev_raw.lower() == "high" else (
                "severity-medium" if sev_raw.lower() == "medium" else ""
            )
            sev_html = f'<span class="{sev_cls}">{html.escape(sev_raw or "Watch")}</span>'
            recent_share = row.get("recent_share")
            recent_mentions = row.get("recent_mentions")
            if recent_share is not None and recent_mentions is not None:
                detail_s = html.escape(f"{recent_mentions} mentions ({recent_share}%)")
            elif recent_share is not None:
                detail_s = html.escape(f"{recent_share}% share")
            else:
                detail_s = "-"
            alert_tr_list.append(
                "          <tr>"
                f"<td>{loc_s}</td>"
                f"<td>{theme_s}</td>"
                f"<td class=\"num\">{change_s}</td>"
                f"<td class=\"num\">{detail_s}</td>"
                f"<td>{sev_html}</td>"
                "</tr>"
            )
        alert_tr = "\n".join(alert_tr_list)
        watch_section_html = (
            '    <section class="report-section summary-section">\n'
            f'      <h2 class="section-title">RISING COMPLAINT WATCH LIST ({len(alert_rows)})</h2>\n'
            '      <table class="data-table">\n'
            '        <thead><tr><th>Location</th><th>Complaint Theme</th><th class="num">Change</th><th class="num">Recent Volume</th><th>Severity</th></tr></thead>\n'
            '        <tbody>\n'
            f'{alert_tr}\n'
            '        </tbody>\n'
            '      </table>\n'
            '    </section>'
        )
    else:
        watch_section_html = _render_card_section(
            "summary-section",
            "RISING COMPLAINT WATCH LIST (0)",
            [],
            empty_text="No rising complaint alerts for the selected period and locations.",
        )

    # Section 3: Most Praised Staff
    if staff_rows:
        top = staff_rows[0]
        callout_html = (
            '      <div class="summary-callout">'
            f'<strong>Top praised team member:</strong> '
            f'{html.escape(clean(top.get("staff")) or "Staff")} at '
            f'{html.escape(clean(top.get("location")) or "Location")} '
            f'({int(top.get("mentions", 0))} mentions).'
            '</div>\n'
        )
        staff_tr_list = []
        for row in staff_rows[:10]:
            staff_s = html.escape(clean(row.get("staff")) or "Staff")
            loc_s = html.escape(clean(row.get("location")) or "Location")
            mentions_s = int(row.get("mentions", 0))
            avg_s = (
                f"{float(row['avg_rating']):.2f} stars"
                if row.get("avg_rating") is not None else "-"
            )
            staff_tr_list.append(
                "          <tr>"
                f"<td>{staff_s}</td>"
                f"<td>{loc_s}</td>"
                f"<td class=\"num\">{mentions_s}</td>"
                f"<td class=\"num\">{html.escape(avg_s)}</td>"
                "</tr>"
            )
        staff_tr = "\n".join(staff_tr_list)
        staff_section_html = (
            '    <section class="report-section summary-section">\n'
            f'      <h2 class="section-title">MOST PRAISED STAFF ({len(staff_rows)})</h2>\n'
            f'{callout_html}'
            '      <table class="data-table">\n'
            '        <thead><tr><th>Staff Member</th><th>Location</th><th class="num">Mentions</th><th class="num">Avg Rating</th></tr></thead>\n'
            '        <tbody>\n'
            f'{staff_tr}\n'
            '        </tbody>\n'
            '      </table>\n'
            '    </section>'
        )
    else:
        staff_section_html = _render_card_section(
            "summary-section",
            "MOST PRAISED STAFF (0)",
            [],
            empty_text="No staff praise mentions recorded for this period.",
        )

    # Section 4: Active Manager Actions (clean page break via .actions-section)
    action_cards = [_render_action_card(entry, clean) for entry in action_entries]
    actions_section_html = _render_card_section(
        "actions-section",
        f"ACTIVE MANAGER ACTIONS ({len(action_entries)})",
        action_cards,
        empty_text="No active actions for the selected file and locations.",
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Weekly Owner Summary</title>
  <style>
{_shared_print_css()}
  </style>
</head>
<body>
  <div class="report-header">
    <h1 class="report-title">WEEKLY OWNER SUMMARY</h1>{period_meta_html}
    <div class="report-meta">Locations: {locs_html}</div>
    <div class="report-meta">Internal owner and manager use only. Keep downloaded copies private.</div>
    <div class="report-meta">Review text, guest identity fields, and reply drafts are excluded. Known guest names and copied passages in action fields are redacted.</div>
  </div>
{kpi_html}
{loc_section_html}
{watch_section_html}
{staff_section_html}
{actions_section_html}
  <p class="disclaimer">Rule changes can change theme counts. Earlier saved action baselines may use different rules or manager decisions, so check them before comparing. Corrections recalculate current reports, not saved action baselines. Review trends do not prove an action caused a change.</p>
</body>
</html>"""


build_html_report = build_printable_report
build_weekly_summary_html = build_printable_weekly_summary
