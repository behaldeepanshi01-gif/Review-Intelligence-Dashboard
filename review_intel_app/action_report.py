"""Internal action-only export. Never exports review records or reply drafts."""
import re

import action_tracker as A


def _privacy_filter(reviews):
    # Known identities and copied passages can also occur in manager-entered notes.
    terms = set()
    for row in reviews:
        name = str(row.get("reviewer") or "").strip()
        text = str(row.get("text") or "").strip()
        if name and name.lower() not in {"nan", "anonymous", "guest"}:
            terms.add(name)
            if len(name.split()[0]) >= 3:
                terms.add(name.split()[0])
        if text:
            terms.add(text)
            # Also remove complete quoted sentences copied into an action.
            terms.update(s.strip() for s in re.split(r"(?<=[.!?])\s+", text)
                         if len(s.split()) >= 4)
    patterns = [re.compile(r"(?<!\w)" + r"\s+".join(re.escape(w) for w in term.split())
                           + r"(?!\w)", re.I)
                for term in sorted(terms, key=len, reverse=True)]

    def clean(value):
        result = str(value or "")
        for pattern in patterns:
            result = pattern.sub("[private content removed]", result)
        # Keep manager input from introducing report headings or control characters.
        return " ".join(result.replace("—", "-").split())
    return clean


def build_report(actions, dataset_tag, locations, reviews, *, legacy_tag=None,
                 provenance_by_location=None, timezones_by_location=None, today=None):
    """Use full selected-dataset reviews, not the dashboard's date-filtered view."""
    selected = [a for a in actions if A.matches_dataset(a, dataset_tag, legacy_tag)
                and a.get("location") in set(locations)]
    selected.sort(key=lambda a: (a.get("location", ""), a.get("created_on", ""),
                                 a.get("action_id", "")))
    clean = _privacy_filter(reviews)
    lines = [
        "MANAGER ACTION REPORT",
        "Internal manager use only. Keep downloaded copies private.",
        "Scope: selected dataset and selected locations; all action statuses.",
        "Locations: " + ", ".join(clean(loc) for loc in sorted(locations)),
        "Dashboard date and action-status filters do not limit this report.",
        "Review text, guest identity fields, and reply drafts are excluded.",
        "Known guest names and copied passages in action fields are redacted. "
        "Check for other private details before sharing.",
        "",
    ]
    for heading, completed in [("ACTIVE ACTIONS", False), ("COMPLETED ACTIONS", True)]:
        group = [a for a in selected if (a.get("status") == "Done") == completed]
        lines += [f"{heading} ({len(group)})"]
        if not group:
            lines += ["None.", ""]
        for action in group:
            location = action.get("location", "")
            overdue = A.is_overdue(action, today,
                                   timezones_by_location=timezones_by_location)
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
            result = A.follow_up(
                action, reviews,
                current_provenance=(provenance_by_location or {}).get(location),
                current_source_reviews=reviews, current_dataset_tag=dataset_tag)
            lines.append("Comparability: " + clean(result["provenance_message"]))
            lines.append("Source data: " + clean(result["source_message"]))
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
