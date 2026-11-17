"""Private, versioned evidence for net decision effects on fixed review cohorts.

No source text or guest identity is retained. Counts are tagging counterfactuals,
not estimates of operational impact. Existing action baselines are never retagged.
"""

from datetime import date
import re


def _day(value):
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except (ValueError, TypeError):
        return None


def capture(action, reviews, alert_review_keys):
    """Capture only action-theme flags, exact cohort membership and multiplicity."""
    if reviews is None or alert_review_keys is None:
        return None
    version = (action.get("baseline_provenance") or {}).get("rules_version")
    if not isinstance(version, str) or not version:
        return None
    theme = action["theme_key"]
    members = set(alert_review_keys)
    rows = {}
    for row in reviews:
        if row.get("location") != action["location"]:
            continue
        key = row.get("correction_key")
        rule = row.get("rule_output")
        day = _day(row.get("date"))
        if (not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{64}", key)
                or not isinstance(rule, dict) or day is None
                or row.get("rules_version") != version):
            return None
        flags = {}
        for name, source in (("rule", rule), ("effective", row)):
            for polarity, field in (("positive", "themes_pos"), ("negative", "themes_neg")):
                if not isinstance(source.get(field), list):
                    return None
                flags[f"{name}_{polarity}"] = theme in source[field]
        record = dict(date=day, alert=key in members, count=1, **flags)
        if key in rows:
            previous = dict(rows[key], count=1)
            if record != previous:
                return None
            rows[key]["count"] += 1
        else:
            rows[key] = record
    if not members.issubset(rows):
        return None
    # Refuse a misleading capture if the supplied alert cohort cannot reproduce
    # its saved mention count. Never repair or rewrite the numeric baseline.
    if sum(r["count"] for r in rows.values()
           if r["alert"] and r["effective_negative"]) != action["baseline_mentions"]:
        return None
    return {
        "version": 1, "dataset_id": action["dataset_tag"],
        "location": action["location"], "theme": theme,
        "through_date": action["alert_end_date"],
        "rules_version": action["baseline_provenance"]["rules_version"],
        "reviews": rows,
    }


def _valid(snapshot, action):
    if not isinstance(snapshot, dict) or snapshot.get("version") != 1:
        return False
    if any(snapshot.get(k) != v for k, v in {
        "dataset_id": action.get("dataset_tag"), "location": action.get("location"),
        "theme": action.get("theme_key"), "through_date": action.get("alert_end_date"),
        "rules_version": (action.get("baseline_provenance") or {}).get("rules_version"),
    }.items()):
        return False
    rows = snapshot.get("reviews")
    if not isinstance(rows, dict):
        return False
    for key, row in rows.items():
        if (not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{64}", key)
                or not isinstance(row, dict)
                or set(row) != {"date", "alert", "count", "rule_positive",
                                "rule_negative", "effective_positive", "effective_negative"}
                or not isinstance(row["date"], str) or _day(row["date"]) != row["date"]
                or type(row["count"]) is not int or row["count"] < 1
                or any(type(row[k]) is not bool for k in
                       ("alert", "rule_positive", "rule_negative",
                        "effective_positive", "effective_negative"))):
            return False
    return sum(r["count"] for r in rows.values()
               if r["alert"] and r["effective_negative"]) == action.get("baseline_mentions")


def compare(action, reviews, current_provenance, dataset_id, decisions_valid):
    """Compare fixed cohorts under the same local rules and two decision states.

    New follow-up reviews had no applicable approval in the complete saved
    decision snapshot. Their before-state therefore uses the captured current
    local-rule fallback, only when the rules version is unchanged.
    """
    unknown = {
        "tag_effect_status": "unknown",
        "tag_effect_message": "Action-cohort tagging-count effects unknown — complete "
        "private capture and matching current review/rule evidence are required. "
        "Legacy actions are not backfilled. The saved baseline is unchanged.",
        "tag_effect_cohorts": [],
    }
    saved = action.get("baseline_action_tags")
    if (not _valid(saved, action) or not decisions_valid or dataset_id != action.get("dataset_tag")
            or not isinstance(current_provenance, dict)
            or current_provenance.get("rules_version") != saved["rules_version"]):
        return unknown
    # Reuse the allowlisted capture format to validate current rule/effective
    # evidence, but do not persist or replace any historical capture.
    current_action = dict(action, baseline_mentions=0)
    now = capture(current_action, reviews, [])
    if now is None:
        return unknown
    before, after = saved["reviews"], now["reviews"]
    old_decisions = (action.get("baseline_provenance") or {}).get("decisions", {})
    new_decisions = current_provenance.get("decisions", {})
    theme = action["theme_key"]
    for key, row in after.items():
        old = before.get(key)
        if old and any(row[f"rule_{p}"] != old[f"rule_{p}"]
                       or row["date"] != old["date"] for p in ("positive", "negative")):
            return unknown
        for polarity in ("positive", "negative"):
            current_tags = new_decisions.get(key)
            expected = (theme in current_tags[polarity] if current_tags is not None
                        else row[f"rule_{polarity}"])
            if row[f"effective_{polarity}"] != expected:
                return unknown
            if old:
                old_tags = old_decisions.get(key)
                expected_old = (theme in old_tags[polarity] if old_tags is not None
                                else old[f"rule_{polarity}"])
                if old[f"effective_{polarity}"] != expected_old:
                    return unknown
            elif key in old_decisions:
                # An approval without matching historical cohort evidence
                # cannot establish a before state.
                return unknown

    def counts(keys, baseline=False):
        totals = dict(review_count=0, before_mentions=0, after_mentions=0,
                      added_mentions=0, removed_mentions=0)
        for key, count in keys:
            old, new = before.get(key), after.get(key)
            if new is None or (baseline and new["count"] != count):
                return None
            was = old["effective_negative"] if old else new["rule_negative"]
            is_now = new["effective_negative"]
            totals["review_count"] += count
            totals["before_mentions"] += count * was
            totals["after_mentions"] += count * is_now
            totals["added_mentions"] += count * (not was and is_now)
            totals["removed_mentions"] += count * (was and not is_now)
        totals["net_mentions"] = totals["after_mentions"] - totals["before_mentions"]
        return totals

    alert = counts([(k, r["count"]) for k, r in before.items() if r["alert"]], True)
    start = _day(action.get("start_date"))
    if start is None:
        return unknown
    followup = counts([(k, r["count"]) for k, r in after.items() if r["date"] > start])
    if alert is None or followup is None:
        return unknown
    cohorts = [dict(cohort="Saved alert cohort", **alert),
               dict(cohort="Current follow-up cohort (after current start date)", **followup)]
    changed = any(r["added_mentions"] or r["removed_mentions"] for r in cohorts)
    return {
        "tag_effect_status": "changed" if changed else "unchanged",
        "tag_effect_message": (
            "Proven net manager-decision tagging effects on fixed cohorts under unchanged "
            "local rules. Before/after means approvals at capture versus approvals now; "
            "new follow-up reviews use local-rule fallback for the before state. "
            "Added and removed negative mentions may cancel in the net count. "
            "These are tagging-count effects, not operational outcomes or proof the action "
            "worked. The saved baseline is unchanged."
        ),
        "tag_effect_cohorts": cohorts,
    }
