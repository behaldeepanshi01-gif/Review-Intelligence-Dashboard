"""Inline supporting review evidence for Early warning cards (dashboard UI only)."""
from datetime import timedelta

import pandas as pd
import streamlit as st

import engine as E


def _theme_key_for_label(theme_label: str) -> str:
    for key, label in E.THEME_LABELS.items():
        if label == theme_label:
            return key
    return theme_label if theme_label in E.THEME_LABELS else ""


def supporting_alert_reviews(
    view: pd.DataFrame,
    location: str,
    theme_label: str,
    recent_days: int,
) -> list[dict]:
    """Return recent-window complaint reviews behind an alert, newest first.

    Uses the exact recent-window boundary as engine.early_warnings without mutating view.
    """
    if view is None or view.empty:
        return []
    theme_key = _theme_key_for_label(theme_label)
    if not theme_key:
        return []

    dates = pd.to_datetime(view["date"])
    end = dates.max()
    if pd.isna(end):
        return []
    recent_start = end - timedelta(days=int(recent_days))

    mask = (view["location"] == location) & (dates > recent_start)
    subset = view.loc[mask].copy()
    if subset.empty:
        return []
    subset["sort_date"] = dates.loc[mask]
    matches = []
    for row in subset.sort_values(["sort_date"], ascending=False).to_dict("records"):
        neg = row.get("themes_neg") or []
        if theme_key not in neg:
            continue
        evidence_items = row.get("tag_evidence") or []
        theme_evidence = [
            item for item in evidence_items
            if isinstance(item, dict)
            and item.get("theme") == theme_key
            and item.get("polarity") == "Complaint"
        ]
        matched_terms = sorted({
            term
            for item in theme_evidence
            for term in (item.get("matched_terms") or [])
        })
        excerpts = [
            str(item.get("excerpt", "")).strip()
            for item in theme_evidence
            if str(item.get("excerpt", "")).strip()
        ]
        row_date = row.get("sort_date")
        date_str = row_date.date().isoformat() if hasattr(row_date, "date") else str(row_date)[:10]
        matches.append({
            "review_id": str(row.get("review_id", "")),
            "location": str(row.get("location", "")),
            "date": date_str,
            "rating": int(row.get("rating", 0)),
            "text": str(row.get("text", "")),
            "matched_terms": matched_terms,
            "excerpts": excerpts,
            "tag_source": str(row.get("tag_source", "local")),
        })
    return matches


def show_alert_evidence(
    view: pd.DataFrame,
    alert: dict,
    recent_days: int,
    *,
    max_items: int = 8,
) -> list[dict]:
    """Render collapsed inline evidence inside an Early warning card."""
    rows = supporting_alert_reviews(
        view, alert["location"], alert["theme"], recent_days
    )
    with st.expander(f"Recent reviews behind this alert ({len(rows)})"):
        st.caption(
            f"Recent complaints in the last {int(recent_days)} days for "
            f"{alert['location']} tagged with {alert['theme']}. "
            "Review text stays in the dashboard and is excluded from action reports and owner summaries."
        )
        if not rows:
            st.caption("No matching recent reviews in the current view.")
            return rows
        for item in rows[:max_items]:
            stars = "★" * max(0, min(5, item["rating"])) + "☆" * max(0, 5 - max(0, min(5, item["rating"])))
            st.markdown(f"**{item['date']}** · {stars}")
            if item["matched_terms"]:
                st.caption("Matched terms: " + ", ".join(item["matched_terms"]))
            elif item["tag_source"] == "manager":
                st.caption("Tagged via manager decision.")
            if item["excerpts"]:
                st.caption("Triggering excerpt: " + " | ".join(item["excerpts"][:2]))
            st.text(item["text"])
        if len(rows) > max_items:
            st.caption(
                f"Showing the {max_items} most recent of {len(rows)} matching reviews. "
                "Open What guests say to inspect the full list."
            )
    return rows
