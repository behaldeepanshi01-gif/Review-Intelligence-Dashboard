"""Small, local helpers for saving and checking manager action plans."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import json
import os
import uuid


MIN_FOLLOWUP_REVIEWS = 5
STATUS_OPTIONS = ("Planned", "In progress", "Done")
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
) -> bool:
    """An unfinished plan is overdue only after its valid due date has passed."""
    due_date = parse_date(action.get("due_date"))
    return (
        action.get("status") != "Done"
        and due_date is not None
        and due_date < (today if today is not None else restaurant_today(timezone_name))
    )


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


def save_actions(path: str, actions: list[dict]) -> None:
    """Write actions atomically so an interrupted save does not replace the log."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)

    temp_path = path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(actions, file, ensure_ascii=False, indent=2)
    os.replace(temp_path, path)


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
        "created_on": (today if today is not None else restaurant_today(timezone_name)).isoformat(),
        "alert_end_date": alert_end_date.isoformat(),
        "baseline_share": float(alert["recent_share"]),
        "baseline_mentions": int(alert["recent_mentions"]),
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


def follow_up(action: dict, reviews: list[dict]) -> dict:
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

    today = today if today is not None else restaurant_today(timezone_name)
    lines = ["Manager actions:"]
    for action in active_actions:
        location = action.get("location", "Location")
        theme = action.get("theme", "Theme")
        action_text = action.get("action_text", "Action not described")
        owner = action.get("owner") or "Not assigned"
        status = action.get("status", "Planned")
        due_date = action.get("due_date") or "Not set"
        overdue_label = "OVERDUE — " if is_overdue(action, today) else ""
        lines.append(
            f"- {overdue_label}{location}, {theme}: {action_text} "
            f"(Status: {status}; Owner: {owner}; Due: {due_date})"
        )

        result = follow_up(action, reviews)
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
