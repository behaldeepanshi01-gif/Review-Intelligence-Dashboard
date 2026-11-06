"""
Review Intelligence: an AI review assistant for multi-location restaurant groups.

Run:  streamlit run app.py
"""

import io
import hashlib
import json
import os
from datetime import timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

import action_tracker as A
from action_decisions_ui import show_decision_changes
from manager_report_ui import show_manager_report
from manager_report_access import require_manager, authorized
import manager_identity as identity
import engine as E
import manager_corrections as C
import dataset_store as D
from location_settings import LocationSettings
from calendar_rename_ui import show_calendar_rename
from legacy_history_ui import (
    show_history_controls, show_live_history_notice, history_changed, action_editors,
)

st.set_page_config(page_title="Review Intelligence", page_icon="🍛", layout="wide")

ACCENT = "#B5482A"
st.markdown(f"""
<style>
  .block-container {{padding-top: 1.6rem; max-width: 1300px;}}
  h1, h2, h3 {{letter-spacing: -0.01em;}}
  .kpi {{border: 1px solid rgba(128,128,128,.25); border-radius: 12px; padding: 14px 16px;}}
  .kpi .v {{font-size: 1.9rem; font-weight: 700; line-height: 1.1;}}
  .kpi .l {{font-size: .85rem; opacity: .7;}}
  .alert {{border-left: 5px solid {ACCENT}; padding: 10px 14px; border-radius: 8px;
           background: rgba(181,72,42,.07); margin-bottom: 10px;}}
  .alert.med {{border-left-color: #D49A2A; background: rgba(212,154,42,.08);}}
  .tag {{display:inline-block; padding:1px 8px; margin:2px 4px 2px 0; border-radius:10px;
         font-size:.78rem; border:1px solid rgba(128,128,128,.35);}}
  .tag.neg {{border-color:{ACCENT}; color:{ACCENT};}}
  .tag.pos {{border-color:#2E7D5B; color:#2E7D5B;}}
</style>
""", unsafe_allow_html=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(BASE_DIR, "data", "sample_reviews.csv")
ACTION_LOG = os.path.join(BASE_DIR, "data", "action_log.json")
CORRECTIONS_LOG = os.path.join(BASE_DIR, "data", "manager_corrections.sqlite")
LOCATION_SETTINGS = os.path.join(BASE_DIR, "data", "location_settings.sqlite")


# ----------------------------------------------------------------------------
# Sidebar: data, engine, filters
# ----------------------------------------------------------------------------
st.sidebar.title("🍛 Review Intelligence")
st.sidebar.caption("AI review assistant for multi-location restaurants")

UPLOAD_DIR = os.path.join(BASE_DIR, "data", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
try:
    datasets = D.DatasetStore(UPLOAD_DIR, SAMPLE)
    saved_datasets = datasets.list_datasets()
except (OSError, D.sqlite3.Error) as ex:
    st.error(f"Couldn't open saved dataset identities: {ex}")
    st.stop()


def dataset_label(dataset_id):
    item = datasets.get(dataset_id)
    return f"{item['label']} · {dataset_id[-8:]}"


if "data_source" not in st.session_state:
    st.session_state["data_source"] = (
        "Saved file" if saved_datasets else "Sample data (synthetic)"
    )
source = st.sidebar.radio(
    "Data", ["Sample data (synthetic)", "Saved file", "Upload my reviews (CSV)"],
    key="data_source",
    help="Uploaded files are saved, so they're still here after a refresh or restart.")
dataset = datasets.get(D.SAMPLE_ID)
if source == "Saved file":
    if not saved_datasets:
        st.info("No saved files yet. Upload a CSV once and it will appear here.")
        st.stop()
    selected_id = st.sidebar.selectbox(
        "Dataset", [item["dataset_id"] for item in saved_datasets],
        format_func=dataset_label,
    )
    dataset = datasets.get(selected_id)
elif source.startswith("Upload"):
    upload = st.sidebar.file_uploader(
        "CSV with columns: location, date, rating, text (reviewer, review_id optional)",
        type="csv")
    if upload is None:
        st.info("Upload a CSV to begin, or switch back to the sample data.")
        st.stop()
    mode = st.sidebar.radio(
        "Upload purpose", ["Create a separate dataset", "Update an existing dataset"],
        help="Matching filenames never share actions automatically. Update only "
             "when this CSV is a newer snapshot of the same restaurant dataset.",
    )
    target_id = None
    if mode == "Update an existing dataset":
        if not saved_datasets:
            st.info("Save a separate dataset first before updating it.")
            st.stop()
        target_id = st.sidebar.selectbox(
            "Dataset to update", [item["dataset_id"] for item in saved_datasets],
            format_func=dataset_label,
        )
        st.sidebar.warning("This replaces the selected dataset's current reviews. "
                           "Its actions and original baselines will be kept.")
    if st.sidebar.button("Save CSV", type="primary"):
        try:
            E.load_reviews(io.BytesIO(upload.getvalue()))
            dataset = datasets.save_snapshot(upload.name, upload.getvalue(), target_id)
            st.session_state["saved_upload"] = {
                "file_id": upload.file_id, "target_id": target_id,
                "dataset_id": dataset["dataset_id"],
            }
        except (OSError, ValueError, D.sqlite3.Error) as ex:
            st.error(f"Couldn't save that CSV: {ex}")
            st.stop()
    saved_upload = st.session_state.get("saved_upload", {})
    if (saved_upload.get("file_id") != upload.file_id
            or saved_upload.get("target_id") != target_id):
        st.info("Choose whether this is a separate dataset or an update, then save the CSV.")
        st.stop()
    dataset = datasets.get(saved_upload["dataset_id"])
    st.sidebar.success("Saved. Next time pick it under 'Saved file'.")

data_path, tag = dataset["path"], dataset["dataset_id"]
legacy_tag = dataset["legacy_tag"]
st.sidebar.caption(f"Dataset identity: {tag}")
show_live_history_notice(datasets, dataset)

try:
    raw = E.load_reviews(data_path)
except Exception as ex:  # show a friendly error instead of a stack trace
    st.error(f"Couldn't read that file: {ex}")
    st.stop()

engine_choice = st.sidebar.radio(
    "Analysis engine", ["Local Review Analyzer (free, offline)",
                        "Claude API (optional, paid)"],
    help="The local analyzer uses explainable rules, not a trained language model. "
         "It needs no model download or API. Claude is optional and only runs on request.")
st.sidebar.caption(
    "Local analysis stays on this computer. Rules can miss context, sarcasm, "
    "and unfamiliar wording. A manager should check the results."
)


@st.cache_data(show_spinner=False)
def run_offline(df: pd.DataFrame, rules_version: str) -> pd.DataFrame:
    # The version is part of the cache key; bump it when imported rules change.
    return E.analyze_offline(df)


tagged = run_offline(raw, E.LOCAL_ANALYZER_VERSION)

if engine_choice.startswith("Claude"):
    snapshot_tag = f"{tag}-{os.path.basename(data_path)}"
    key = st.sidebar.text_input("Anthropic API key", type="password",
                                value=os.environ.get("ANTHROPIC_API_KEY", ""))
    if st.sidebar.button("Run Claude analysis", type="primary", disabled=not key):
        bar = st.sidebar.progress(0.0, text="Reading reviews...")
        try:
            st.session_state["claude_result"] = E.analyze_with_claude(
                raw, key, data_tag=snapshot_tag,
                progress=lambda p: bar.progress(p, text="Reading reviews..."))
            st.session_state["claude_tag"] = snapshot_tag
        except Exception as ex:
            st.sidebar.error(f"Claude call failed: {ex}")
    if (st.session_state.get("claude_tag") == snapshot_tag
            and "claude_result" in st.session_state):
        tagged = st.session_state["claude_result"]
        st.sidebar.success("Showing Claude analysis")
    else:
        st.sidebar.caption("Showing local rule results until you run Claude.")


is_local = tagged["engine"].eq("local_rules").all()
provenance_by_location = {}
if is_local:
    try:
        corrections = C.load_corrections(CORRECTIONS_LOG, E.LOCAL_ANALYZER_VERSION)
        tagged = C.apply_corrections(raw, tagged, dataset["correction_path"], corrections)
        prior_decisions = C.load_prior_corrections(
            CORRECTIONS_LOG, E.LOCAL_ANALYZER_VERSION)
        renewals = C.renewal_queue(raw, dataset["correction_path"],
                                  corrections, prior_decisions)
        provenance_by_location = {
            location: C.tagging_provenance(
                rows, dataset["correction_path"], corrections, E.LOCAL_ANALYZER_VERSION)
            for location, rows in raw.groupby("location")
        }
    except (OSError, ValueError, C.sqlite3.Error) as ex:
        st.error(f"Couldn't load manager corrections. Reports were stopped: {ex}")
        st.stop()

    if renewals:
        st.warning(
            f"{len(renewals)} unchanged reviews need renewed manager approval after "
            "a rules change. Earlier decisions are not applied to reports. "
            "Review them in What guests say → Decisions needing renewed approval."
        )


def show_rule_evidence(row):
    """Show local explanations only in the private review-inspection UI."""
    if row.needs_review:
        st.warning("Needs manager review: " + " ".join(row.review_reasons))
    with st.expander("Why these tags?"):
        if getattr(row, "tag_source", "") == "manager":
            st.info("Manager-confirmed tags are used in reports. Evidence below is "
                    "the original rule output, not the manager's reasoning.")
            st.json(row.rule_output)
        if not row.tag_evidence:
            st.caption("No local rule evidence is available for this result.")
        for item in row.tag_evidence:
            st.write(f"{E.THEME_LABELS[item['theme']]}: {item['polarity']}")
            st.caption("Matched terms: " + ", ".join(item["matched_terms"]))
            st.text(item["excerpt"])
            st.caption(item["reason"])

locations = sorted(tagged["location"].unique())
with st.sidebar.expander("Manager calendar access", expanded=True):
    if not require_manager(purpose="restaurant calendars"):
        st.stop()
session = st.session_state.get("_manager_report_grant")
account = identity.current_account(session)
allowed_locations = account["grants"].get(tag, []) if account else []
locations = [loc for loc in locations if loc in allowed_locations]
if not locations:
    st.warning("You do not have calendar access to any current restaurant in this dataset. "
               "Choose an assigned dataset or ask the app owner for access.")
    st.stop()
try:
    all_actions = A.load_actions(ACTION_LOG)
except (OSError, ValueError) as ex:
    st.error(f"Couldn't read the action log: {ex}")
    st.stop()
# A removed/renamed location cannot be selected in the current-review filters.
# Still surface its source warning rather than silently hiding every old plan.
for missing_action in all_actions:
    if (A.matches_dataset(missing_action, tag, legacy_tag)
            and missing_action.get("location") not in locations):
        source_check = A.comparison_source(missing_action, raw.to_dict("records"), tag)
        st.warning(f"Saved action location {missing_action.get('location', 'Location')} "
                   f"is absent from this dataset snapshot. {source_check['source_message']}")
try:
    calendars = LocationSettings(LOCATION_SETTINGS, session=session)
    calendar_settings = calendars.load(tag)
except (OSError, D.sqlite3.Error) as ex:
    st.error(f"Couldn't read location calendars: {ex}")
    st.stop()
timezones_by_location = {
    loc: calendar_settings.get(loc, LocationSettings.default())["timezone"]
    for loc in locations
}
with st.sidebar.expander("Location calendars"):
    if notice := st.session_state.pop("calendar_rename_notice", None):
        st.success(notice)
    show_calendar_rename(datasets, dataset, calendars, calendar_settings, locations)
    st.caption(
        "Only signed-in managers assigned to this dataset and exact restaurant "
        "can read or edit its calendar. Separate datasets own separate settings. "
        "Existing due dates never change.")
    calendar_location = st.selectbox("Calendar location", locations)
    current_calendar = calendar_settings.get(calendar_location, LocationSettings.default())
    calendar_key = f"calendar_{tag}_{calendar_location}"
    if calendar_key not in st.session_state:
        st.session_state[calendar_key] = current_calendar
    calendar_snapshot = st.session_state[calendar_key]
    if calendar_snapshot != current_calendar:
        st.warning("Another manager changed this calendar. Reload before saving.")
    if st.button("Reload saved timezone"):
        st.session_state[calendar_key] = current_calendar
        st.rerun()
    with st.form(f"{calendar_key}_{calendar_snapshot['revision']}"):
        zone = st.text_input("Restaurant timezone", value=calendar_snapshot["timezone"],
                             key=f"{calendar_key}_{calendar_snapshot['revision']}_zone",
                             help="IANA name, for example America/New_York or Asia/Kolkata.")
        save_calendar = st.form_submit_button("Save location timezone")
    if save_calendar:
        try:
            calendars.save(tag, calendar_location, zone,
                           expected_revision=calendar_snapshot["revision"])
        except (ValueError, OSError, D.sqlite3.Error) as ex:
            st.error(f"Couldn't save timezone: {ex}")
        else:
            del st.session_state[calendar_key]
            st.rerun()
    st.caption("Saved calendars reload on each interaction or page refresh. "
               "Plans become overdue the day after their local due date.")
    @st.fragment(run_every="30s")
    def show_calendar_days():
        for loc in locations:
            if not authorized(tag, [loc]):
                st.warning("Calendar access expired or was removed. Sign in again.")
                return
            st.caption(f"{loc} — Action calendar: "
                       f"{A.location_today(loc, timezones_by_location).isoformat()} · "
                       f"{timezones_by_location[loc]}")

    show_calendar_days()

pick = st.sidebar.multiselect("Locations", locations, default=locations)
dmin, dmax = tagged["date"].min().date(), tagged["date"].max().date()
dr = st.sidebar.slider("Date range", min_value=dmin, max_value=dmax, value=(dmin, dmax))
window = st.sidebar.selectbox(
    "Early-warning window", [30, 60, 90], index=0, format_func=lambda d: f"Last {d} days",
    help="Compares recent complaints with the 3x longer period before it. "
         "Use 60 or 90 days for lower-volume locations.")

view = tagged[tagged["location"].isin(pick)
              & (tagged["date"].dt.date >= dr[0]) & (tagged["date"].dt.date <= dr[1])]
if view.empty:
    st.warning("No reviews match these filters.")
    try:
        report_actions = A.load_actions(ACTION_LOG)
    except (OSError, ValueError) as ex:
        st.error(f"Couldn't read the action log: {ex}")
        st.stop()
    show_manager_report(report_actions, tag, pick, tagged, legacy_tag,
                        provenance_by_location, timezones_by_location)
    st.stop()

# ----------------------------------------------------------------------------
# Header + KPIs
# ----------------------------------------------------------------------------
st.title("Review Intelligence")
if source.startswith("Sample"):
    st.caption("Demo mode: every review here is synthetic. Upload real reviews from the sidebar.")

if "approved" not in st.session_state:
    st.session_state["approved"] = {}
if "approved_reply_tags" not in st.session_state:
    st.session_state["approved_reply_tags"] = {}


def reply_tag_state(row):
    """Compare effective tags, not decision timestamps or generated wording."""
    return {
        "review_key": getattr(row, "correction_key", None),
        "positive": sorted(set(row.themes_pos)),
        "negative": sorted(set(row.themes_neg)),
    }


reply_tags = {r.review_id: reply_tag_state(r) for r in tagged.itertuples()}
reply_rechecks = {
    review_id for review_id, state in reply_tags.items()
    if review_id in st.session_state["approved"]
    and st.session_state["approved_reply_tags"].get(review_id) != state
}

high_open = view[(view["urgency"] == "High")
                 & (~view["review_id"].isin(st.session_state["approved"].keys()))]
neg_share = 100 * (view["themes_neg"].str.len() > 0).mean()
alerts = E.early_warnings(view, recent_days=window, baseline_days=window * 3)
show_history_controls(datasets, dataset, all_actions)

k1, k2, k3, k4 = st.columns(4)
for col, val, label in [
    (k1, f"{len(view):,}", "Reviews analyzed"),
    (k2, f"{view['rating'].mean():.2f} ★", "Average rating"),
    (k3, f"{neg_share:.0f}%", "Reviews with a complaint"),
    (k4, f"{len(high_open)}", "High-urgency, no reply yet"),
]:
    col.markdown(f'<div class="kpi"><div class="v">{val}</div><div class="l">{label}</div></div>',
                 unsafe_allow_html=True)

st.write("")
tabs = st.tabs(["📊 Overview", "🧭 What guests say", "🚨 Early warnings",
                "🙌 Staff shout-outs", "✉️ Reply inbox", "⬇️ Export",
                "🧭 Action tracker"])

# ----------------------------------------------------------------------------
# Overview
# ----------------------------------------------------------------------------
with tabs[0]:
    c1, c2 = st.columns([1, 1.4])
    by_loc = (view.groupby("location")
                  .agg(avg_rating=("rating", "mean"), reviews=("rating", "size"),
                       complaint_pct=("themes_neg", lambda s: 100 * (s.str.len() > 0).mean()))
                  .round(2).reset_index().sort_values("avg_rating"))
    fig = px.bar(by_loc, x="avg_rating", y="location", orientation="h", text="avg_rating",
                 range_x=[1, 5], color_discrete_sequence=[ACCENT],
                 labels={"avg_rating": "Average rating", "location": ""})
    fig.update_layout(height=320, margin=dict(l=0, r=10, t=30, b=0), title="Rating by location")
    c1.plotly_chart(fig, width="stretch")

    trend = E.monthly_trend(view)
    fig2 = px.line(trend, x="month", y="avg_rating", color="location", markers=True,
                   labels={"avg_rating": "Average rating", "month": ""})
    fig2.update_layout(height=320, margin=dict(l=0, r=10, t=30, b=0),
                       title="Monthly rating trend", legend_title_text="")
    c2.plotly_chart(fig2, width="stretch")

    st.subheader("Location snapshot")
    snap = by_loc.sort_values("avg_rating", ascending=False).rename(columns={
        "location": "Location", "avg_rating": "Avg rating", "reviews": "Reviews",
        "complaint_pct": "% with complaint"})
    st.dataframe(snap, hide_index=True, width="stretch")

# ----------------------------------------------------------------------------
# Themes
# ----------------------------------------------------------------------------
with tabs[1]:
    tt = E.theme_table(view)
    st.markdown("**Net sentiment by theme** (green = guests praise it, red = guests complain). "
                "Number = % of that location's reviews, praise minus complaints.")
    if tt.empty:
        st.info("No clear praise or complaints matched the supported themes. "
                "Check the reviews needing manager review below.")
    else:
        heat = tt.pivot(index="theme", columns="location", values="net").fillna(0)
        fig3 = px.imshow(heat, text_auto=True, aspect="auto", color_continuous_scale="RdYlGn",
                         color_continuous_midpoint=0, labels=dict(color="Net %"))
        fig3.update_layout(height=480, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig3, width="stretch")

    st.subheader("Top complaints")
    top_c = (tt[tt["negative"] > 0].sort_values("pct_negative", ascending=False)
             .head(10)[["location", "theme", "negative", "pct_negative"]]
             .rename(columns={"location": "Location", "theme": "Theme",
                              "negative": "Reviews", "pct_negative": "% of reviews"}))
    st.dataframe(top_c, hide_index=True, width="stretch")

    st.subheader("Read the reviews behind a theme")
    cc1, cc2 = st.columns(2)
    th = cc1.selectbox("Theme", list(E.THEME_LABELS.values()))
    pol = cc2.radio("Showing", ["Complaints", "Praise"], horizontal=True)
    key_t = {v: k for k, v in E.THEME_LABELS.items()}[th]
    col_t = "themes_neg" if pol == "Complaints" else "themes_pos"
    sub = view[view[col_t].apply(lambda x: key_t in x)].sort_values("date", ascending=False)
    st.caption(f"{len(sub)} reviews")
    for r in sub.head(8).itertuples():
        st.markdown(f"**{r.location}** · {'★' * r.rating} · {r.date.date()}  \n{r.text}")
        show_rule_evidence(r)

    # Unknown themes must be reachable even when no theme filter matches them.
    needs_review = view[view["needs_review"]].sort_values("date", ascending=False)
    with st.expander(f"Reviews needing manager review ({len(needs_review)})"):
        st.caption("Unclear wording is not automatically counted as praise or a complaint.")
        if not needs_review.empty:
            position = st.selectbox(
                "Review needing a check", list(range(len(needs_review))),
                format_func=lambda index: (
                    f"{needs_review.iloc[index]['review_id']} | "
                    f"{needs_review.iloc[index]['location']} | "
                    f"{needs_review.iloc[index]['date'].date()}"
                ),
            )
            r = next(needs_review.iloc[[position]].itertuples())
            st.write(f"{r.location} | {r.date.date()} | {r.rating} stars")
            st.text(r.text)
            # Avoid nesting expanders on older Streamlit versions.
            st.warning(" ".join(r.review_reasons))
            for item in r.tag_evidence:
                st.write(f"{E.THEME_LABELS[item['theme']]}: {item['polarity']}")
                st.caption("Matched terms: " + ", ".join(item["matched_terms"]))
                st.text(item["excerpt"])

    if is_local:
        pending = view[view["correction_key"].isin(renewals)].drop_duplicates(
            "correction_key").sort_values("date", ascending=False)
        st.subheader(f"Decisions needing renewed approval ({len(pending)})")
        st.caption(
            f"{len(renewals)} unchanged reviews in this dataset; "
            f"{len(pending)} match the location and date filters. "
            "Changed reviews are excluded. Earlier tags remain history only until "
            "you explicitly approve them for the current rules version."
        )
        if not pending.empty:
            renewal_key = st.selectbox(
                "Review needing renewed approval", pending["correction_key"].tolist(),
                format_func=lambda key: (
                    f"{pending.loc[pending['correction_key'] == key, 'review_id'].iloc[0]} | "
                    f"{pending.loc[pending['correction_key'] == key, 'location'].iloc[0]}"),
            )
            renewal = pending.loc[pending["correction_key"] == renewal_key].iloc[0]
            st.text(renewal["text"])
            st.caption(f"{renewal['location']} | {renewal['date'].date()} | "
                       f"{renewal['rating']} stars")
            history = renewals[renewal_key]
            history_index = st.selectbox(
                "Earlier manager decision", list(range(len(history))),
                key=f"renewal-history-{renewal_key}",
                format_func=lambda i: (
                    f"{history[i]['rules_version']} | saved {history[i]['saved_at']}"),
            )
            earlier = history[history_index]
            obsolete = sorted(
                (set(earlier["themes_pos"]) | set(earlier["themes_neg"])) - set(E.THEMES))
            old_column, rule_column = st.columns(2)
            with old_column:
                st.write("Earlier manager tags — not currently applied")
                st.caption(f"Rules: {earlier['rules_version']} | "
                           f"Saved: {earlier['saved_at']}")
                st.caption(C.decision_origin_label(earlier))
                st.json({k: earlier[k] for k in ("themes_pos", "themes_neg")})
            with rule_column:
                st.write("Current rule output")
                st.caption(f"Rules: {E.LOCAL_ANALYZER_VERSION}")
                st.json(renewal["rule_output"])
                st.write("Current rule evidence")
                st.json(renewal["tag_evidence"])
            if obsolete:
                st.warning(
                    "These earlier tags are no longer supported by the current rules: "
                    + ", ".join(obsolete)
                    + ". Direct reapproval is disabled. Select this review under "
                    "'Approve or correct review tags' below and save supported current "
                    "tags (or confirm no supported theme)."
                )
            st.caption(
                "Approval applies these earlier tags to current reports and unapproved "
                "reply drafts. Saved action baselines and approved replies are not "
                "rewritten; check them separately. To use different tags, use "
                "'Approve or correct review tags' below."
            )
            if st.button("Approve earlier tags for current rules",
                         key=f"renew-{renewal_key}-{earlier['saved_at']}",
                         disabled=bool(obsolete)):
                # Use the source row, not the derived rule/effective fields.
                source_row = next(
                    row for row in raw.to_dict("records")
                    if C.review_key(dataset["correction_path"], row) == renewal_key)
                try:
                    C.approve_prior_correction(
                        CORRECTIONS_LOG, dataset["correction_path"], source_row,
                        earlier, E.LOCAL_ANALYZER_VERSION)
                except (OSError, ValueError, C.sqlite3.Error) as ex:
                    st.error(f"Couldn't renew the manager decision: {ex}")
                else:
                    st.rerun()
        else:
            st.info("No decisions need renewed approval in the current filters.")

        st.subheader("Approve or correct review tags")
        st.caption(
            "Select any review, including an unclear or previously corrected result. "
            "Save the complete set of praise and complaint tags; a theme can appear in "
            "both for mixed feedback. Leave both empty to confirm no supported theme. "
            "Nothing changes in reports until you save. Undo restores the local rules."
        )
        inspection = view.sort_values("date", ascending=False)
        selected = st.selectbox(
            "Review to approve or correct", inspection["correction_key"].tolist(),
            format_func=lambda key: (
                f"{inspection.loc[inspection['correction_key'] == key, 'review_id'].iloc[0]} | "
                f"{inspection.loc[inspection['correction_key'] == key, 'location'].iloc[0]}"),
        )
        r = inspection.loc[inspection["correction_key"] == selected].iloc[0]
        st.text(r["text"])
        st.caption(f"{r['date'].date()} | {r['rating']} stars | "
                   f"Current source: {r['tag_source']} | Rules: {r['rules_version']}")
        if r["manager_correction"]:
            st.info("Manager decision saved " + r["manager_correction"]["saved_at"])
            st.caption(C.decision_origin_label(r["manager_correction"]))
        st.write("Original rule result")
        st.json(r["rule_output"])
        st.write("Original rule evidence")
        st.json(r["tag_evidence"])
        # A decision revision resets defaults after save/undo, not just review changes.
        revision = (r["manager_correction"] or {}).get("saved_at", "rules")
        with st.form(f"correction-{selected}-{revision}"):
            positive = st.multiselect(
                "Confirmed praise themes", list(E.THEMES),
                default=r["themes_pos"], format_func=E.THEME_LABELS.get)
            negative = st.multiselect(
                "Confirmed complaint themes", list(E.THEMES),
                default=r["themes_neg"], format_func=E.THEME_LABELS.get)
            save = st.form_submit_button("Save manager decision")
        if save:
            try:
                C.save_correction(CORRECTIONS_LOG, selected, positive, negative,
                                  E.LOCAL_ANALYZER_VERSION)
            except (OSError, ValueError, C.sqlite3.Error) as ex:
                st.error(f"Couldn't save the manager decision: {ex}")
            else:
                st.rerun()
        if r["manager_correction"] and st.button(
                "Undo manager decision", key=f"undo-{selected}"):
            try:
                C.undo_correction(CORRECTIONS_LOG, selected, E.LOCAL_ANALYZER_VERSION)
            except (OSError, ValueError, C.sqlite3.Error) as ex:
                st.error(f"Couldn't undo the manager decision: {ex}")
            else:
                st.rerun()

# ----------------------------------------------------------------------------
# Early warnings
# ----------------------------------------------------------------------------
with tabs[2]:
    st.markdown(f"Themes where complaints **jumped in the last {window} days** compared with the "
                f"{window * 3} days before. These are the problems to fix before they cost regulars.")
    if alerts.empty:
        st.success("No rising issues right now.")
    for index, alert in enumerate(alerts.to_dict("records")):
        action_today = A.location_today(alert["location"], timezones_by_location)
        key = f"{tag}_{index}"
        with st.container(border=True):
            st.markdown(f"**{alert['location']}: {alert['theme']}**")
            st.write(
                f"{alert['severity']} warning. {alert['recent_share']}% of recent reviews "
                f"mention this theme, compared with {alert['baseline_share']}% before. "
                f"{alert['recent_mentions']} recent reviews."
            )
            suggestion = A.suggested_step(alert["theme"])
            st.markdown(f"**Possible next check:** {suggestion}")
            st.caption("This is a general prompt, not a confirmed cause.")

            active = A.find_active_action(
                all_actions, tag, alert["location"], alert["theme"],
                legacy_tag=legacy_tag)
            if active:
                st.info(
                    f"Action already tracked as {active['status']}. "
                    "Open the Action tracker tab to update it."
                )
            else:
                with st.form(f"new_action_{key}"):
                    action_text = st.text_area(
                        "Action to try", value=suggestion, key=f"action_text_{key}")
                    owner = st.text_input(
                        "Owner (optional)", key=f"action_owner_{key}")
                    start_date = st.date_input(
                        "Action start date", value=action_today, key=f"start_date_{key}")
                    due_date = st.date_input(
                        "Due date", value=action_today + timedelta(days=7),
                        key=f"due_date_{key}")
                    submitted = st.form_submit_button("Save action plan")

                if submitted:
                    if not action_text.strip():
                        st.error("Enter an action before saving.")
                    elif due_date < start_date:
                        st.error("The due date must be on or after the start date.")
                    else:
                        theme_key = next(
                            (key for key, label in E.THEME_LABELS.items()
                             if label == alert["theme"]),
                            "",
                        )
                        if not theme_key:
                            st.error("Couldn't match this alert to a theme.")
                        else:
                            action = A.create_action(
                                dataset_tag=tag,
                                alert=alert,
                                theme_key=theme_key,
                                action_text=action_text,
                                owner=owner,
                                start_date=start_date,
                                due_date=due_date,
                                alert_end_date=view["date"].max().date(),
                                today=action_today,
                                tagging_provenance=provenance_by_location.get(
                                    alert["location"]),
                                source_reviews=raw.to_dict("records"),
                            )
                            try:
                                A.append_action(ACTION_LOG, action, legacy_tag=legacy_tag)
                            except (OSError, ValueError) as ex:
                                st.error(f"Couldn't save the action plan: {ex}")
                            else:
                                st.toast("Action plan saved.")
                                st.rerun()

# ----------------------------------------------------------------------------
# Staff
# ----------------------------------------------------------------------------
with tabs[3]:
    lb = E.staff_leaderboard(view)
    if lb.empty:
        st.info("No staff names found in these reviews.")
    else:
        st.markdown("Staff guests praise by name. A simple way to recognize your best people.")
        fig4 = px.bar(lb.head(15).sort_values("mentions"), x="mentions", y="staff",
                      color="location", orientation="h", text="mentions",
                      labels={"mentions": "Mentions", "staff": ""})
        fig4.update_layout(height=420, margin=dict(l=0, r=0, t=10, b=0), legend_title_text="")
        st.plotly_chart(fig4, width="stretch")
        st.dataframe(lb.rename(columns={"location": "Location", "staff": "Staff",
                                        "mentions": "Mentions", "positive": "Positive",
                                        "avg_rating": "Avg rating"}),
                     hide_index=True, width="stretch")

# ----------------------------------------------------------------------------
# Reply inbox
# ----------------------------------------------------------------------------
with tabs[4]:
    st.markdown("Local replies use editable templates; optional Claude replies use that API. "
                "**Nothing is posted automatically.** Check the wording before approving "
                "and copying into Google or Yelp.")
    f1, f2, f3 = st.columns(3)
    urg = f1.multiselect("Urgency", ["High", "Medium", "Low"], default=["High", "Medium"])
    show_done = f2.toggle("Show approved", value=False)
    n_show = f3.number_input("Show", min_value=5, max_value=100, value=10, step=5)

    recheck_count = int(view["review_id"].isin(reply_rechecks).sum())
    if recheck_count:
        st.warning(
            f"{recheck_count} approved replies need a wording recheck. Their effective "
            "tags differ from the tags at reply approval (or no approval snapshot exists). "
            "Approved text has not been changed. These replies stay in the queue "
            "regardless of urgency and Show approved filters."
        )
    inbox = view[view["urgency"].isin(urg)
                 | view["review_id"].isin(reply_rechecks)].sort_values(
        ["urgency", "date"], key=lambda c: c.map({"High": 0, "Medium": 1, "Low": 2})
        if c.name == "urgency" else c, ascending=[True, False])
    if not show_done:
        inbox = inbox[~inbox["review_id"].isin(st.session_state["approved"].keys())
                      | inbox["review_id"].isin(reply_rechecks)]
    st.caption(f"{len(inbox)} reviews in queue · {len(st.session_state['approved'])} approved")

    for r in inbox.head(int(n_show)).itertuples():
        with st.container(border=True):
            top = st.columns([3, 1])
            top[0].markdown(f"**{r.location}** · {'★' * r.rating}{'☆' * (5 - r.rating)} · "
                            f"{r.reviewer} · {r.date.date()}")
            top[1].markdown(f"Urgency: **{r.urgency}**")
            st.write(r.text)
            show_rule_evidence(r)
            tags = "".join(f'<span class="tag neg">{E.THEME_LABELS[t]}</span>' for t in r.themes_neg)
            tags += "".join(f'<span class="tag pos">{E.THEME_LABELS[t]}</span>' for t in r.themes_pos)
            st.markdown(tags, unsafe_allow_html=True)
            needs_recheck = r.review_id in reply_rechecks
            if needs_recheck:
                st.warning(
                    "Approved reply needs recheck: tags changed since approval, or "
                    "the approval's tag snapshot is unavailable. Read the current tags "
                    "and wording, edit if needed, then click Recheck and approve reply. "
                    "The previously approved wording is preserved until you approve again."
                )
            draft = st.session_state["approved"].get(r.review_id, r.reply_draft)
            draft_key = f"d_{r.review_id}"
            revision_key = f"draft_revision_{r.review_id}"
            revision = json.dumps([
                getattr(r, "correction_key", None), r.engine, r.themes_pos,
                r.themes_neg, r.reply_draft,
                getattr(r, "manager_correction", None),
            ], sort_keys=True)
            # A text-area's existing state wins over its default on rerun. Refresh
            # unapproved wording when tags change, including an undo, but leave
            # manager-approved replies and edits under unchanged tags alone.
            if (draft_key not in st.session_state
                    or (r.review_id not in st.session_state["approved"]
                        and st.session_state.get(revision_key) != revision)):
                st.session_state[draft_key] = draft
            st.session_state[revision_key] = revision
            text = st.text_area("Reply draft", key=draft_key, height=150)
            if st.button("Recheck and approve reply" if needs_recheck else "Approve reply",
                         key=f"a_{r.review_id}"):
                st.session_state["approved"][r.review_id] = text
                st.session_state["approved_reply_tags"][r.review_id] = reply_tags[r.review_id]
                st.toast("Approved")
                st.rerun()

# ----------------------------------------------------------------------------
# Export
# ----------------------------------------------------------------------------
with tabs[5]:
    show_manager_report(all_actions, tag, pick, tagged, legacy_tag,
                        provenance_by_location, timezones_by_location)
    st.divider()
    st.caption("The review export includes guest text and reviewer names. Keep it private. "
               "Use synthetic sample data for public demos.")
    out = view.copy()
    for c in ["themes_pos", "themes_neg", "staff"]:
        out[c] = out[c].apply(lambda xs: "; ".join(E.THEME_LABELS.get(x, x) for x in xs))
    for c in ["tag_evidence", "review_reasons", "rule_output", "manager_correction"]:
        if c in out:
            out[c] = out[c].apply(lambda value: json.dumps(value, ensure_ascii=False))
    out["approved_reply"] = (
        out["review_id"].map(st.session_state["approved"]).astype("object").fillna("")
    )
    out["approved_reply_needs_recheck"] = out["review_id"].isin(reply_rechecks)
    buf = io.StringIO()
    out.to_csv(buf, index=False)
    st.download_button("Download analyzed reviews (CSV)", buf.getvalue(),
                       file_name="analyzed_reviews.csv", mime="text/csv", type="primary")
    if not alerts.empty:
        st.download_button("Download early warnings (CSV)", alerts.to_csv(index=False),
                           file_name="early_warnings.csv", mime="text/csv")
    st.markdown("**Weekly owner summary** (copy into an email or WhatsApp)")
    st.caption("Rule changes can change theme counts. Earlier saved action baselines "
               "may use different rules or manager decisions, so check them before comparing. "
               "Corrections recalculate current reports, not saved action baselines.")
    lines = [f"Reviews this period: {len(view)}, average {view['rating'].mean():.2f} stars."]
    for loc, g in view.groupby("location"):
        lines.append(f"- {loc}: {g['rating'].mean():.2f} stars from {len(g)} reviews")
    if not alerts.empty:
        lines.append("Watch list:")
        lines += [f"- {a.location}: {a.theme} complaints rising ({a.change})"
                  for a in alerts.itertuples()]
    lb2 = E.staff_leaderboard(view)
    if not lb2.empty:
        top = lb2.iloc[0]
        lines.append(f"Most praised staff: {top['staff']} at {top['location']} "
                     f"({int(top['mentions'])} mentions).")
    lines.append(f"High-urgency reviews still needing a reply: {len(high_open)}.")
    @st.fragment(run_every="30s")
    def show_live_owner_summary():
        # Never mutate the captured review summary on a timer tick.
        current_history = datasets.get(tag)["legacy_tag"]
        action_lines = A.weekly_action_summary(
            A.load_actions(ACTION_LOG),
            dataset_tag=tag,
            locations=pick,
            reviews=tagged.to_dict("records"),
            timezones_by_location=timezones_by_location,
            legacy_tag=current_history,
            provenance_by_location=provenance_by_location,
            source_reviews=raw.to_dict("records"),
        )
        st.code("\n".join(lines + action_lines), language=None)

    show_live_owner_summary()

# ----------------------------------------------------------------------------
# Action tracker
# ----------------------------------------------------------------------------
@st.fragment(run_every="30s")
def show_live_action_tracker():
    st.markdown(
        "Keep a manager's action with the alert, then check later reviews for the same theme. "
        "A change in review mentions is a signal, not proof that an action caused it."
    )
    st.caption("An older saved baseline may use earlier tagging rules. A change in the "
               "analyzer is not evidence of an operational improvement.")
    st.caption("Source data is checked separately through each action's saved alert date. "
               "Edits, removals and backfilled reviews can affect comparability; "
               "newer follow-up reviews are allowed. Older actions without a saved "
               "source cohort have unknown source-data comparability.")
    st.caption("Overdue warnings, filters and the owner summary update every 30 seconds "
               "while connected. Action editors below are not refreshed by this timer.")
    current_history = datasets.get(tag)["legacy_tag"]
    saved_actions = [
        action for action in A.load_actions(ACTION_LOG)
        if A.matches_dataset(action, tag, current_history) and action.get("location") in pick
    ]
    saved_actions.sort(key=lambda action: action.get("created_on", ""), reverse=True)

    status_filter = st.radio(
        "Show action plans",
        ("All active actions", "Overdue only", "Completed plans"),
        horizontal=True,
        key="action_status_filter",
    )
    if status_filter == "Overdue only":
        visible_actions = [action for action in saved_actions if A.is_overdue(
            action, timezones_by_location=timezones_by_location)]
    elif status_filter == "Completed plans":
        visible_actions = [action for action in saved_actions if action.get("status") == "Done"]
    else:
        visible_actions = [action for action in saved_actions if action.get("status") != "Done"]

    st.caption(f"Showing {len(visible_actions)} of {len(saved_actions)} action plans "
               "for the current dataset and selected locations.")
    if not saved_actions:
        st.info("No action plans saved for this file and location yet.")
    elif not visible_actions:
        empty_messages = {
            "All active actions": "No active action plans for this dataset and selected locations.",
            "Overdue only": "No overdue action plans for this dataset and selected locations.",
            "Completed plans": "No completed action plans for this dataset and selected locations.",
        }
        st.info(empty_messages[status_filter] + " Choose another status filter to see other plans.")

    for action in visible_actions:
        action_today = A.location_today(action.get("location"), timezones_by_location)
        action_id = action.get("action_id", "")
        with st.container(border=True):
            st.markdown(f"**{action.get('location', 'Location')}: {action.get('theme', 'Theme')}**")
            st.caption(
                f"Status: {action.get('status', 'Planned')} | "
                f"Owner: {action.get('owner') or 'Not assigned'} | "
                f"Due: {action.get('due_date', 'Not set')}"
            )
            if A.is_overdue(action, action_today):
                st.warning("Overdue — this active action is past its due date.")

            location_reviews = tagged[tagged["location"] == action.get("location")]
            result = A.follow_up(
                action, location_reviews.to_dict("records"),
                current_provenance=provenance_by_location.get(action.get("location")),
                current_source_reviews=raw.to_dict("records"),
                current_dataset_tag=tag,
            )
            if result["provenance_status"] == "unchanged":
                st.caption(result["provenance_message"])
            else:
                st.warning(result["provenance_message"])
            show_decision_changes(action, tag, result)
            if result["source_status"] == "unchanged":
                st.caption(result["source_message"])
            else:
                st.warning(result["source_message"])
            if result.get("reason") == "not_started":
                st.info("Mark the action In progress when it starts to begin follow-up.")
            elif not result["ready"]:
                st.info(
                    f"Waiting for at least {A.MIN_FOLLOWUP_REVIEWS} newer reviews. "
                    f"{result['review_count']} found so far."
                )
            else:
                change_label = (
                    f"{abs(result['change_points']):.1f} percentage points "
                    f"{result['direction']} than the alert period"
                )
                st.write(
                    f"Since the action start date, {result['mentions']} of "
                    f"{result['review_count']} newer reviews mention this theme "
                    f"({result['share']}%). The alert period was "
                    f"{result['baseline_share']}%. That is {change_label}."
                )
                st.caption(
                    "This is a review trend only. It does not prove the action caused the change."
                )

with tabs[6]:
    show_live_action_tracker()
    st.subheader("Edit action plans")
    st.caption("Editors stay available regardless of the status filter above, so "
               "a calendar update cannot remove an unsaved draft.")
    for reference in st.session_state.get(f"history_drafts_{tag}", {}).values():
        st.markdown("**Kept history-link draft for reference — not saved**")
        st.caption(f"Action: {reference['action_id']} · Older history: "
                   f"{reference['dataset_tag']}. Session-only reference; not reapplied.")
        st.json(reference["draft"])
    editable_actions = sorted(
        ((action, association) for action, association in
         action_editors(st.session_state, dataset, all_actions)
         if action.get("location") in pick),
        key=lambda item: item[0].get("created_on", ""), reverse=True,
    )
    for action, editor_association in editable_actions:
        action_id = action.get("action_id", "")
        action_today = A.location_today(action.get("location"), timezones_by_location)
        with st.expander(
            f"Edit {action.get('location', 'Location')}: {action.get('theme', 'Theme')} "
            f"· {action.get('owner') or 'Not assigned'}"
        ):
            st.markdown("**Action edit history**")
            st.caption("Successful saves only, newest first. Times are UTC. "
                       "Earlier edits made before history was available are not recorded. "
                       "Owner is the plan's assigned owner, not the person who saved it.")
            history = action.get("edit_history", [])
            if not history:
                st.info("No recorded action edits yet.")
            elif not isinstance(history, list):
                st.error("The saved action edit history is invalid.")
            else:
                field_labels = {
                    "action_text": "Manager action", "owner": "Owner",
                    "status": "Status", "start_date": "Action start date",
                    "due_date": "Due date",
                }
                history_rows = []
                for entry in reversed(history):
                    for field, values in entry["changes"].items():
                        history_rows.append({
                            "Saved at (UTC)": entry["saved_at"],
                            "Field": field_labels.get(field, field),
                            "Before": values["before"],
                            "After": values["after"],
                        })
                    if not entry["changes"]:
                        history_rows.append({
                            "Saved at (UTC)": entry["saved_at"],
                            "Field": "Saved without field changes",
                            "Before": "", "After": "",
                        })
                st.dataframe(history_rows, hide_index=True, use_container_width=True)
            # Streamlit reloads the log on submit. Keep the snapshot the manager
            # actually saw, rather than treating that fresh load as their version.
            snapshot_key = f"action_snapshot_{tag}_{action_id}"
            if snapshot_key not in st.session_state:
                st.session_state[snapshot_key] = dict(action)
            snapshot = st.session_state[snapshot_key]
            conflicted = snapshot != action
            association_stale = (
                editor_association is not None
                and history_changed(datasets, editor_association)
            )
            if association_stale:
                st.warning("This older-history link changed. Your draft has not been "
                           "saved. Keep the draft and refresh this editor to review "
                           "the current history. Dataset-ID actions are unaffected.")
            reference_key = f"action_draft_reference_{tag}_{action_id}"
            field_labels = {
                "action_text": "Manager action", "owner": "Owner",
                "status": "Status", "start_date": "Action start date",
                "due_date": "Due date",
            }
            if conflicted:
                st.warning("Another manager changed this action. Your draft has not "
                           "been saved. Compare the versions below before reloading.")
                st.error("Your changes were not saved. Reload the latest action "
                         "before editing again; there is no force-overwrite option.")
            form_version = hashlib.sha256(
                json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
            form_key = f"{action_id}_{form_version}"
            with st.form(f"update_action_{form_key}"):
                action_text = st.text_area(
                    "Manager action", value=snapshot.get("action_text", ""),
                    key=f"update_text_{form_key}")
                cols = st.columns(2)
                owner = cols[0].text_input(
                    "Owner (optional)", value=snapshot.get("owner", ""),
                    key=f"update_owner_{form_key}")
                status = cols[1].selectbox(
                    "Status", A.STATUS_OPTIONS,
                    index=A.STATUS_OPTIONS.index(snapshot.get("status", "Planned"))
                    if snapshot.get("status", "Planned") in A.STATUS_OPTIONS else 0,
                    key=f"update_status_{form_key}")
                start_date = st.date_input(
                    "Action start date",
                    value=A.parse_date(snapshot.get("start_date"), action_today),
                    key=f"update_start_{form_key}")
                due_date = st.date_input(
                    "Due date",
                    value=A.parse_date(snapshot.get("due_date"), action_today),
                    key=f"update_due_{form_key}")
                submitted = st.form_submit_button(
                    "Save updates", disabled=conflicted or association_stale)
                refresh_editor = False
                if association_stale:
                    refresh_editor = st.form_submit_button("Keep draft and refresh editor")
                keep_draft = reload_latest = False
                if conflicted:
                    # Submit these choices with the form so even newer,
                    # browser-buffered draft changes are available to Keep.
                    keep_draft = st.form_submit_button("Keep draft for reference")
                    reload_latest = st.form_submit_button("Reload latest action")

            if refresh_editor or (submitted and association_stale):
                references = st.session_state.setdefault(f"history_drafts_{tag}", {})
                references[action_id] = {
                    "action_id": action_id, "dataset_tag": snapshot.get("dataset_tag"),
                    "draft": {
                        "action_text": action_text, "owner": owner, "status": status,
                        "start_date": start_date.isoformat(), "due_date": due_date.isoformat(),
                    },
                }
                if refresh_editor:
                    st.session_state[f"history_editors_{tag}"].pop(action_id, None)
                    st.session_state.pop(snapshot_key, None)
                    st.rerun()
                st.error("History ownership changed. Nothing was saved. Your submitted "
                         "draft is kept for reference; use Keep draft and refresh editor.")

            if conflicted:
                draft = {
                    "action_text": action_text, "owner": owner, "status": status,
                    "start_date": start_date.isoformat(), "due_date": due_date.isoformat(),
                }
                st.markdown("**Compare your unsaved draft with the latest saved action**")
                st.dataframe([
                    {"Field": field_labels[field], "Your unsaved draft": draft[field],
                     "Latest saved": action.get(field, ""),
                     "Different": draft[field] != action.get(field, "")}
                    for field in A.EDITABLE_FIELDS
                ], hide_index=True, use_container_width=True)
                st.caption("Only editable fields are compared. Saved alert evidence and "
                           "baseline fields remain read-only. Reload discards the draft "
                           "in the editor. Keep it for reference first if you need it; "
                           "the reference stays only in this dashboard session.")
                if keep_draft:
                    st.session_state[reference_key] = dict(draft)
                    st.success("Draft kept for reference in this session. It has not "
                               "been saved to the action log.")
                if reload_latest:
                    st.session_state[snapshot_key] = dict(action)
                    st.rerun()

            if reference_key in st.session_state:
                st.markdown("**Kept draft for reference — not saved**")
                st.caption("Use this reference to manually revise the latest action. "
                           "It is not automatically applied or saved.")
                st.dataframe([
                    {"Field": field_labels[field],
                     "Kept draft": st.session_state[reference_key][field]}
                    for field in A.EDITABLE_FIELDS
                ], hide_index=True, use_container_width=True)

            if submitted and not conflicted and not association_stale:
                if not action_text.strip():
                    st.error("Enter an action before saving.")
                elif due_date < start_date:
                    st.error("The due date must be on or after the start date.")
                else:
                    try:
                        updated = A.edit_saved_action(
                            ACTION_LOG, snapshot, action_text, owner, status,
                            start_date, due_date, history_store=datasets, dataset_id=tag,
                            expected_history_revision=(
                                editor_association["history_revision"]
                                if editor_association else None),
                        )
                    except D.HistoryAssociationError as ex:
                        st.session_state.setdefault(f"history_drafts_{tag}", {})[action_id] = {
                            "action_id": action_id, "dataset_tag": snapshot.get("dataset_tag"),
                            "draft": {
                                "action_text": action_text, "owner": owner, "status": status,
                                "start_date": start_date.isoformat(),
                                "due_date": due_date.isoformat(),
                            },
                        }
                        st.error(str(ex) + " Your draft is kept for reference.")
                    except A.ActionConflictError:
                        # A manager may save after this run loaded the log.
                        # Reread it without changing the draft's widget keys.
                        st.rerun()
                    except (OSError, ValueError, D.sqlite3.Error) as ex:
                        st.error(f"Couldn't update the action: {ex}")
                    else:
                        st.session_state[snapshot_key] = updated
                        st.toast("Action updated.")
                        st.rerun()
