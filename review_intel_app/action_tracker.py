"""Small, local helpers for saving and checking manager action plans."""

from __future__ import annotations

from datetime import date, datetime, timezone
from contextlib import contextmanager, nullcontext
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import copy
import fcntl
import hashlib
import json
import os
import tempfile
import uuid
from dataset_store import source_cohort


MIN_FOLLOWUP_REVIEWS = 5
STATUS_OPTIONS = ("Planned", "In progress", "Done")
EDITABLE_FIELDS = ("action_text", "owner", "status", "start_date", "due_date")
DEFAULT_RESTAURANT_TIMEZONE = "America/New_York"


def restaurant_today(
    timezone_name: str = DEFAULT_RESTAURANT_TIMEZONE,
    *, now: datetime | None = None,
) -> date:
    """Return the restaurant's calendar day; injected instants must be aware."""
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise ValueError("Enter a valid IANA timezone, such as America/New_York.") from exc
    if now is None:
        return datetime.now(zone).date()
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("The current instant must include a timezone.")
    return now.astimezone(zone).date()

# These are practical checks for a manager to consider, not claims about causes.
ACTION_IDEAS = {
    "Food & flavor": "Review recent comments and check preparation for the dishes mentioned.",
    "Seasoning & spice": "Check spice-level descriptions and kitchen seasoning steps.",
    "Consistency": "Compare recent recipes and prep steps for the dishes mentioned.",
    "Service speed": "Review staffing and handoffs during the busiest service periods.",
    "Staff & hospitality": "Discuss the feedback with the team and agree on one service step.",
    "Portions & value": "Check portion standards and how value is explained on the menu.",
    "Price": "Review recent price changes and menu details for the items mentioned.",
    "Ambiance & decor": "Walk the dining room during service and check the reported conditions.",
    "Cleanliness": "Recheck table, restroom, and opening-cleaning routines.",
    "Catering & events": "Review the event handoff and catering checklist with the team.",
    "Seating & reservations": "Review the reservation and table handoff during busy periods.",
    "Takeout & delivery": "Check order packing and pickup handoff for completeness.",
}


def suggested_step(theme: str) -> str:
    """Return a free, theme-based check for a manager to review."""
    return ACTION_IDEAS.get(
        theme,
        "Read the recent reviews for this theme and choose one process to check.",
    )


def parse_date(value, fallback: date | None = None) -> date | None:
    """Read a date saved by Streamlit or in the JSON action log."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return fallback
    return fallback


def is_overdue(
    action: dict, today: date | None = None,
    *, timezone_name: str = DEFAULT_RESTAURANT_TIMEZONE,
    timezones_by_location: dict | None = None,
    now: datetime | None = None,
) -> bool:
    """An unfinished plan is overdue only after its valid due date has passed."""
    due_date = parse_date(action.get("due_date"))
    return (
        action.get("status") != "Done"
        and due_date is not None
        and due_date < (today if today is not None else location_today(
            action.get("location"), timezones_by_location, timezone_name=timezone_name, now=now))
    )


def location_today(location, timezones_by_location=None, *,
                   timezone_name=DEFAULT_RESTAURANT_TIMEZONE, now=None):
    zone = (timezones_by_location or {}).get(location, timezone_name)
    return restaurant_today(zone) if now is None else restaurant_today(zone, now=now)


def matches_dataset(action: dict, dataset_tag: str, legacy_tag: str | None = None) -> bool:
    """Include an old history only when it was explicitly linked to this dataset."""
    return action.get("dataset_tag") == dataset_tag or (
        legacy_tag is not None and action.get("dataset_tag") == legacy_tag
    )


def load_actions(
    path: str, data_tag: str | None = None, *, legacy_tag: str | None = None
) -> list[dict]:
    """Load saved actions. A broken action log is reported instead of hidden."""
    if not os.path.exists(path):
        return []

    try:
        with open(path, encoding="utf-8") as file:
            actions = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError("The action log contains invalid JSON.") from exc

    if not isinstance(actions, list) or not all(isinstance(row, dict) for row in actions):
        raise ValueError("The action log must contain a list of action records.")

    if data_tag is None:
        return actions
    return [row for row in actions if matches_dataset(row, data_tag, legacy_tag)]


class ActionConflictError(ValueError):
    """Another manager changed the action after this form was opened."""


@contextmanager
def _action_lock(path: str):
    # Lock a stable sidecar inode, not the JSON inode replaced by atomic saves.
    path = os.path.realpath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".lock", "a", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield path
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _write_actions(path: str, actions: list[dict]) -> None:
    """Caller holds the lock. Leave the old log intact on any write failure."""
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=os.path.dirname(path),
            prefix=".actions-", suffix=".tmp", delete=False,
        ) as file:
            temp_path = file.name
            json.dump(actions, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and os.path.exists(temp_path):
            os.unlink(temp_path)


def save_actions(
    path: str, actions: list[dict], *, expected_actions: list[dict] | None = None,
) -> None:
    """Initialize a log or replace an explicitly checked snapshot, never blindly."""
    with _action_lock(path) as path:
        current = load_actions(path)
        expected = [] if expected_actions is None else expected_actions
        if current != expected:
            raise ActionConflictError(
                "The action log changed. Reload it before saving; nothing was overwritten.")
        _write_actions(path, actions)


def append_action(path: str, action: dict, *, legacy_tag: str | None = None) -> None:
    """Append against the latest log and check for an active plan under the lock."""
    with _action_lock(path) as path:
        actions = load_actions(path)
        if not action.get("action_id"):
            raise ValueError("An action ID is required.")
        if any(row.get("action_id") == action["action_id"] for row in actions):
            raise ActionConflictError("This action was already saved. Reload the action tracker.")
        if find_active_action(
            actions, action["dataset_tag"], action["location"], action["theme"],
            legacy_tag=legacy_tag,
        ):
            raise ActionConflictError(
                "Another manager already saved an active plan for this warning. "
                "Reload and open the Action tracker to review it.")
        _write_actions(path, actions + [action])


def edit_saved_action(
    path: str, expected: dict, action_text: str, owner: str, status: str,
    start_date: date, due_date: date,
    *, history_store=None, dataset_id=None, expected_history_revision=None,
) -> dict:
    """Compare the displayed snapshot, then update only manager-editable fields."""
    if history_store is not None and not dataset_id:
        raise ValueError("A dataset identity is required to validate action ownership.")
    guard = (
        history_store.action_history_guard(
            dataset_id, expected.get("dataset_tag"), expected_history_revision)
        if history_store is not None else nullcontext()
    )
    # Always acquire the registry transaction before the JSON lock. Transfers
    # cannot slip between ownership validation and the atomic action write.
    with guard, _action_lock(path) as path:
        actions = load_actions(path)
        matches = [i for i, row in enumerate(actions)
                   if row.get("action_id") == expected.get("action_id")]
        if not expected.get("action_id") or len(matches) != 1:
            raise ActionConflictError(
                "This action is missing or its ID is ambiguous. Reload the action tracker.")
        index = matches[0]
        if actions[index] != expected:
            raise ActionConflictError(
                "Another manager changed this action. Your changes were not saved. "
                "Reload the latest action before editing again.")
        updated = update_action(
            actions[index], action_text, owner, status, start_date, due_date)
        history = actions[index].get("edit_history", [])
        if not isinstance(history, list):
            raise ValueError("The action edit history is invalid; nothing was saved.")
        # Keep the audit entry in the same atomic write as the edited action.
        # Never infer earlier edits for legacy actions or include alert baselines.
        updated["edit_history"] = history + [{
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "changes": {
                field: {"before": actions[index].get(field), "after": updated[field]}
                for field in EDITABLE_FIELDS
                if actions[index].get(field) != updated[field]
            },
        }]
        actions[index] = updated
        _write_actions(path, actions)
        return updated


def create_action(
    dataset_tag: str,
    alert: dict,
    theme_key: str,
    action_text: str,
    owner: str,
    start_date: date,
    due_date: date,
    alert_end_date: date,
    *, today: date | None = None,
    timezone_name: str = DEFAULT_RESTAURANT_TIMEZONE,
    tagging_provenance: dict | None = None,
    source_reviews: list[dict] | None = None,
    timezones_by_location: dict | None = None,
    now: datetime | None = None,
) -> dict:
    """Create one manager-owned action using the warning as its baseline."""
    return {
        "action_id": uuid.uuid4().hex,
        "dataset_tag": dataset_tag,
        "location": alert["location"],
        "theme": alert["theme"],
        "theme_key": theme_key,
        "action_text": action_text.strip(),
        "owner": owner.strip(),
        "status": "Planned",
        "start_date": start_date.isoformat(),
        "due_date": due_date.isoformat(),
        "created_on": (today if today is not None else location_today(
            alert["location"], timezones_by_location,
            timezone_name=timezone_name, now=now)).isoformat(),
        "alert_end_date": alert_end_date.isoformat(),
        "baseline_share": float(alert["recent_share"]),
        "baseline_mentions": int(alert["recent_mentions"]),
        "baseline_provenance": capture_tagging_provenance(tagging_provenance),
        "baseline_source": source_cohort(
            source_reviews, dataset_tag, alert["location"], alert_end_date
        ) if source_reviews is not None else None,
    }


def update_action(
    action: dict,
    action_text: str,
    owner: str,
    status: str,
    start_date: date,
    due_date: date,
) -> dict:
    """Update editable manager fields without changing the action's alert scope."""
    if not action_text.strip():
        raise ValueError("Enter an action before saving.")
    if status not in STATUS_OPTIONS:
        raise ValueError(f"Status must be one of: {', '.join(STATUS_OPTIONS)}.")
    if due_date < start_date:
        raise ValueError("The due date must be on or after the start date.")

    updated = dict(action)
    updated.update({
        "action_text": action_text.strip(),
        "owner": owner.strip(),
        "status": status,
        "start_date": start_date.isoformat(),
        "due_date": due_date.isoformat(),
    })
    return updated


def find_active_action(
    actions: list[dict], dataset_tag: str, location: str, theme: str,
    *, legacy_tag: str | None = None,
) -> dict | None:
    """Return the newest plan that is not marked done."""
    matching = [
        row for row in actions
        if matches_dataset(row, dataset_tag, legacy_tag)
        and row.get("location") == location
        and row.get("theme") == theme
        and row.get("status") != "Done"
    ]
    if not matching:
        return None
    return max(matching, key=lambda row: row.get("created_on", ""))


def _decision_snapshot(provenance: dict | None) -> dict | None:
    """Validate complete, versioned history without requiring today's vocabulary."""
    if (not isinstance(provenance, dict) or provenance.get("decisions_version") != 1
            or not isinstance(provenance.get("rules_version"), str)
            or not provenance["rules_version"]):
        return None
    decisions = provenance.get("decisions")
    if not isinstance(decisions, dict):
        return None
    for key, tags in decisions.items():
        if (not isinstance(key, str) or len(key) != 64
                or any(c not in "0123456789abcdef" for c in key)
                or not isinstance(tags, dict) or set(tags) != {"positive", "negative"}):
            return None
        for values in tags.values():
            if (not isinstance(values, list) or any(not isinstance(t, str) for t in values)
                    or values != sorted(set(values))):
                return None
    fingerprint = hashlib.sha256(
        json.dumps(decisions, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return decisions if fingerprint == provenance.get("decisions_fingerprint") else None


def capture_tagging_provenance(provenance: dict | None) -> dict | None:
    """Capture only the minimal supported fields and detach caller-owned objects."""
    if not isinstance(provenance, dict):
        return None
    captured = {key: provenance[key] for key in ("rules_version", "decisions_fingerprint")
                if key in provenance}
    decisions = _decision_snapshot(provenance)
    if decisions is not None:
        captured.update(decisions_version=1, decisions=copy.deepcopy(decisions))
    return captured


def comparison_decisions(action: dict, current: dict | None) -> dict:
    """Explain net location-wide decision changes, never infer missing history."""
    baseline = action.get("baseline_provenance")
    before = _decision_snapshot(baseline)
    after = _decision_snapshot(current)
    scope = (
        "Location-wide decisions, independent of dashboard date filters. These changes "
        "are potentially relevant, not proof that this action theme's counts changed "
        "or that the action caused an operational result. Added or removed decisions "
        "do not record the local-rule fallback tags; their effective theme impact is unknown."
    )
    if before is None or after is None:
        missing = "Baseline" if before is None else "Current"
        return {
            "decisions_status": "unknown",
            "decisions_message": f"{missing} decision detail unknown — a complete supported "
            "decision snapshot was not captured or is unavailable. Added, changed and "
            "removed decisions cannot be reconstructed. The saved baseline is unchanged.",
            "decisions_scope": scope,
            "decision_changes": [],
        }
    rows = []
    for key in sorted(before.keys() | after.keys()):
        old, new = before.get(key), after.get(key)
        if old == new:
            continue
        kind = "added" if old is None else "removed" if new is None else "changed"
        theme = action.get("theme_key")
        theme_changed = (
            old is not None and new is not None and bool(theme)
            and any((theme in old[polarity]) != (theme in new[polarity])
                    for polarity in ("positive", "negative"))
        )
        rows.append({
            "decision_ref": key, "change": kind,
            "before": copy.deepcopy(old), "after": copy.deepcopy(new),
            "theme_evidence": (
                "Recorded action-theme tags changed; effect on comparison counts unproven."
                if theme_changed else
                "Location-wide change only; action-theme impact not established."
            ),
        })
    counts = {kind: sum(row["change"] == kind for row in rows)
              for kind in ("added", "changed", "removed")}
    rules_changed = baseline.get("rules_version") != current.get("rules_version")
    message = (
        f"Since capture: {counts['added']} added, {counts['changed']} changed, "
        f"{counts['removed']} removed applicable decisions."
        if rows else "No net manager-decision changes since capture."
    )
    if rules_changed:
        message += (
            " Rules versions differ: this compares approved tag records only. Removed "
            "decisions may reflect approvals no longer applicable under the current rules, "
            "not an undo. Matching records do not establish rules comparability."
        )
    return {"decisions_status": "changed" if rows else "unchanged",
            "decisions_message": message, "decisions_scope": scope,
            "decision_changes": rows}


def comparison_provenance(action: dict, current: dict | None) -> dict:
    """Describe comparability without ever changing a saved historical baseline."""
    baseline = action.get("baseline_provenance")
    fields = ("rules_version", "decisions_fingerprint")
    if not isinstance(baseline, dict) or not all(baseline.get(k) for k in fields):
        return {
            "provenance_status": "unknown",
            "provenance_message": "Baseline tagging provenance unknown — this older action "
            "has no recorded rules version and manager-decision fingerprint. "
            "Comparability cannot be confirmed; the saved baseline is unchanged.",
        }
    if not isinstance(current, dict) or not all(current.get(k) for k in fields):
        return {
            "provenance_status": "unknown",
            "provenance_message": "Current tagging provenance unknown — comparability "
            "cannot be confirmed for this analysis. The saved baseline is unchanged.",
        }
    changes = []
    if baseline["rules_version"] != current["rules_version"]:
        changes.append(
            f"local rules changed ({baseline['rules_version']} → {current['rules_version']})")
    if baseline["decisions_fingerprint"] != current["decisions_fingerprint"]:
        changes.append("applicable manager decisions changed")
    if changes:
        return {
            "provenance_status": "changed",
            "provenance_message": "Tagging changed — " + "; ".join(changes) + ". "
            "This follow-up may not be comparable with its saved baseline. "
            "The saved baseline is unchanged; do not interpret this as an operational result.",
        }
    return {
        "provenance_status": "unchanged",
        "provenance_message": "Tagging provenance unchanged — local rules and applicable "
        "manager decisions match the saved baseline.",
    }


def comparison_source(action: dict, reviews: list[dict] | None,
                      dataset_tag: str | None = None) -> dict:
    """Check the saved source cohort independently of tagging provenance."""
    baseline = action.get("baseline_source")
    unknown = {
        "source_status": "unknown",
        "source_message": "Source-data comparability unknown — the saved source cohort "
        "or complete current source data is unavailable. The saved baseline is unchanged.",
    }
    if not isinstance(baseline, dict) or baseline.get("version") != 1 or reviews is None:
        return unknown
    if (baseline.get("dataset_id") != action.get("dataset_tag")
            or baseline.get("location") != action.get("location")
            or baseline.get("through_date") != action.get("alert_end_date")
            or not isinstance(baseline.get("counts"), dict)
            or any(not isinstance(n, int) or n < 1 for n in baseline["counts"].values())):
        return unknown
    if dataset_tag is not None and dataset_tag != baseline["dataset_id"]:
        return unknown
    try:
        current = source_cohort(
            reviews, baseline["dataset_id"], baseline["location"], baseline["through_date"])
    except (KeyError, TypeError, ValueError):
        return unknown
    if baseline["counts"] != current["counts"]:
        return {
            "source_status": "changed",
            "source_message": "Source data changed — reviews through the saved alert date "
            "were edited, removed, or added. This follow-up may not be comparable with "
            "its saved baseline, even if tagging rules and manager decisions match. "
            "The saved baseline is unchanged; do not interpret this as an operational result.",
        }
    return {
        "source_status": "unchanged",
        "source_message": "Source cohort unchanged — reviews through the saved alert date "
        "match. Newer follow-up reviews do not invalidate this source-data check.",
    }


def follow_up(
    action: dict, reviews: list[dict], *, current_provenance: dict | None = None,
    current_source_reviews: list[dict] | None = None,
    current_dataset_tag: str | None = None,
) -> dict:
    """Compare newer mentions, carrying a comparability label even while waiting."""
    provenance = comparison_provenance(action, current_provenance)
    source = comparison_source(action, current_source_reviews, current_dataset_tag)
    statuses = (provenance["provenance_status"], source["source_status"])
    comparable = "changed" if "changed" in statuses else (
        "unknown" if "unknown" in statuses else "unchanged")
    return {**_follow_up_counts(action, reviews), **provenance, **source,
            **comparison_decisions(action, current_provenance),
            "comparability_status": comparable}


def _follow_up_counts(action: dict, reviews: list[dict]) -> dict:
    """Compare newer negative mentions with the warning's original share."""
    start_date = parse_date(action.get("start_date"))
    if action.get("status") == "Planned" or start_date is None:
        return {"ready": False, "reason": "not_started", "review_count": 0, "mentions": 0}

    newer_reviews = []
    for review in reviews:
        if review.get("location") != action.get("location"):
            continue
        review_date = parse_date(review.get("date"))
        if review_date is not None and review_date > start_date:
            newer_reviews.append(review)

    theme_key = action.get("theme_key")
    mentions = sum(theme_key in (row.get("themes_neg") or []) for row in newer_reviews)
    review_count = len(newer_reviews)

    if review_count < MIN_FOLLOWUP_REVIEWS:
        return {
            "ready": False,
            "reason": "not_enough_reviews",
            "review_count": review_count,
            "mentions": mentions,
        }

    share = round(100 * mentions / review_count, 1)
    baseline = float(action.get("baseline_share", 0))
    change = round(share - baseline, 1)
    direction = "lower" if change < 0 else "higher" if change > 0 else "unchanged"
    return {
        "ready": True,
        "review_count": review_count,
        "mentions": mentions,
        "share": share,
        "baseline_share": round(baseline, 1),
        "change_points": change,
        "direction": direction,
    }


def weekly_action_summary(
    actions: list[dict],
    dataset_tag: str,
    locations: list[str],
    reviews: list[dict],
    today: date | None = None,
    *, legacy_tag: str | None = None,
    timezone_name: str = DEFAULT_RESTAURANT_TIMEZONE,
    provenance_by_location: dict | None = None,
    source_reviews: list[dict] | None = None,
    timezones_by_location: dict | None = None,
    now: datetime | None = None,
) -> list[str]:
    """Summarize active plans without including guest names or review text."""
    selected_locations = set(locations)
    active_actions = [
        row for row in actions
        if matches_dataset(row, dataset_tag, legacy_tag)
        and row.get("location") in selected_locations
        and row.get("status") != "Done"
    ]
    active_actions.sort(key=lambda row: row.get("created_on", ""), reverse=True)

    if not active_actions:
        return ["Manager actions: no active actions for the selected file and locations."]

    lines = ["Manager actions:"]
    for action in active_actions:
        location = action.get("location", "Location")
        theme = action.get("theme", "Theme")
        action_text = action.get("action_text", "Action not described")
        owner = action.get("owner") or "Not assigned"
        status = action.get("status", "Planned")
        due_date = action.get("due_date") or "Not set"
        overdue_label = "OVERDUE — " if is_overdue(
            action, today, timezone_name=timezone_name,
            timezones_by_location=timezones_by_location, now=now) else ""
        lines.append(
            f"- {overdue_label}{location}, {theme}: {action_text} "
            f"(Status: {status}; Owner: {owner}; Due: {due_date})"
        )

        result = follow_up(
            action, reviews,
            current_provenance=(provenance_by_location or {}).get(location),
            current_source_reviews=source_reviews,
            current_dataset_tag=dataset_tag,
        )
        lines.append("  " + result["provenance_message"])
        lines.append("  " + result["source_message"])
        if result["ready"]:
            lines.append(
                f"  Follow-up: {result['mentions']} of {result['review_count']} "
                f"newer reviews mention this theme ({result['share']}%), compared "
                f"with {result['baseline_share']}% in the alert period. "
                f"{abs(result['change_points']):.1f} percentage points "
                f"{result['direction']}."
            )

    lines.append("Review trends do not prove an action caused a change.")
    return lines
