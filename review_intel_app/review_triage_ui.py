"""Manager triage filters for Reviews needing manager review and Reply inbox.

Pure UI filtering helpers; never modifies analyzer rules, tags, or saved approvals.
"""
import pandas as pd
import streamlit as st

import engine as E

ALL_FLAGGED_THEMES = "All flagged themes"
NO_THEME_LABEL = "No supported theme found"
ALL_REASONS = "All reasons"
ALL_REPLY_THEMES = "All themes"


def _theme_key_for_label(label: str) -> str:
    for key, text in E.THEME_LABELS.items():
        if text == label:
            return key
    return label if label in E.THEME_LABELS else ""


def flagged_theme_options(needs_review: pd.DataFrame) -> list[str]:
    if needs_review is None or needs_review.empty:
        return [ALL_FLAGGED_THEMES]
    themes = set()
    has_no_theme = False
    for evidence in needs_review["tag_evidence"]:
        items = evidence or []
        if not items:
            has_no_theme = True
            continue
        for item in items:
            if isinstance(item, dict) and item.get("polarity") == "Needs review":
                key = item.get("theme", "")
                themes.add(E.THEME_LABELS.get(key, key))
    options = [ALL_FLAGGED_THEMES, *sorted(themes)]
    if has_no_theme:
        options.append(NO_THEME_LABEL)
    return options


def flagged_reason_options(needs_review: pd.DataFrame) -> list[str]:
    if needs_review is None or needs_review.empty:
        return [ALL_REASONS]
    reasons = sorted({
        str(reason).strip()
        for row_reasons in needs_review["review_reasons"]
        for reason in (row_reasons or [])
        if str(reason).strip()
    })
    return [ALL_REASONS, *reasons]


def filter_needs_review(
    needs_review: pd.DataFrame,
    *,
    theme_filter: str = ALL_FLAGGED_THEMES,
    reason_filter: str = ALL_REASONS,
) -> pd.DataFrame:
    """Filter flagged reviews by theme and/or reason without mutating input."""
    if needs_review is None or needs_review.empty:
        return needs_review
    mask = []
    for row in needs_review.to_dict("records"):
        evidence = row.get("tag_evidence") or []
        reasons = row.get("review_reasons") or []

        if theme_filter == ALL_FLAGGED_THEMES:
            theme_ok = True
        elif theme_filter == NO_THEME_LABEL:
            theme_ok = len(evidence) == 0
        else:
            theme_ok = any(
                isinstance(item, dict)
                and item.get("polarity") == "Needs review"
                and E.THEME_LABELS.get(item.get("theme"), item.get("theme")) == theme_filter
                for item in evidence
            )

        reason_ok = (reason_filter == ALL_REASONS) or (reason_filter in reasons)
        mask.append(theme_ok and reason_ok)

    return needs_review.loc[mask]


def show_needs_review_triage(needs_review: pd.DataFrame) -> pd.DataFrame:
    """Render theme and reason triage filters inside Reviews needing manager review."""
    t_opts = flagged_theme_options(needs_review)
    r_opts = flagged_reason_options(needs_review)
    c1, c2 = st.columns(2)
    chosen_theme = c1.selectbox(
        "Filter by flagged theme", t_opts, key="triage_needs_review_theme"
    )
    chosen_reason = c2.selectbox(
        "Filter by flag reason", r_opts, key="triage_needs_review_reason"
    )
    filtered = filter_needs_review(
        needs_review, theme_filter=chosen_theme, reason_filter=chosen_reason
    )
    st.caption(
        f"Showing {len(filtered)} of {len(needs_review)} reviews needing manager review."
    )
    return filtered


def reply_theme_options(view: pd.DataFrame) -> list[str]:
    if view is None or view.empty:
        return [ALL_REPLY_THEMES]
    keys = set()
    for col in ("themes_neg", "themes_pos"):
        if col in view.columns:
            for items in view[col]:
                for k in (items or []):
                    keys.add(k)
    labels = sorted(E.THEME_LABELS.get(k, k) for k in keys)
    return [ALL_REPLY_THEMES, *labels]


def filter_reply_inbox(
    view: pd.DataFrame,
    *,
    urgencies: list[str],
    show_approved: bool,
    approved_keys,
    reply_rechecks,
    theme_filter: str = ALL_REPLY_THEMES,
    recheck_only: bool = False,
) -> pd.DataFrame:
    """Filter Reply inbox while preserving stale-approval visibility invariants."""
    if view is None or view.empty:
        return view

    is_recheck = view["reply_key"].isin(reply_rechecks)
    if recheck_only:
        inbox = view[is_recheck]
    else:
        inbox = view[view["urgency"].isin(urgencies) | is_recheck]
        if not show_approved:
            inbox = inbox[~inbox["reply_key"].isin(approved_keys) | inbox["reply_key"].isin(reply_rechecks)]
        if theme_filter != ALL_REPLY_THEMES:
            theme_key = _theme_key_for_label(theme_filter)
            if theme_key:
                theme_mask = [
                    (theme_key in (row.get("themes_neg") or []))
                    or (theme_key in (row.get("themes_pos") or []))
                    or (row.get("reply_key") in reply_rechecks)
                    for row in inbox.to_dict("records")
                ]
                inbox = inbox.loc[theme_mask]

    return inbox.sort_values(
        ["urgency", "date"],
        key=lambda c: c.map({"High": 0, "Medium": 1, "Low": 2}) if c.name == "urgency" else c,
        ascending=[True, False],
    )
