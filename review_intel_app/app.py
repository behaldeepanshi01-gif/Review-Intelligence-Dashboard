"""
Review Intelligence: an AI review assistant for multi-location restaurant groups.

Run:  streamlit run app.py
"""

import io
import json
import os
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

import action_tracker as A
import engine as E
import manager_corrections as C
import dataset_store as D

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
if is_local:
    try:
        corrections = C.load_corrections(CORRECTIONS_LOG, E.LOCAL_ANALYZER_VERSION)
        tagged = C.apply_corrections(raw, tagged, dataset["correction_path"], corrections)
    except (OSError, ValueError, C.sqlite3.Error) as ex:
        st.error(f"Couldn't load manager corrections. Reports were stopped: {ex}")
        st.stop()


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
    st.stop()

# ----------------------------------------------------------------------------
# Header + KPIs
# ----------------------------------------------------------------------------
st.title("Review Intelligence")
if source.startswith("Sample"):
    st.caption("Demo mode: every review here is synthetic. Upload real reviews from the sidebar.")

if "approved" not in st.session_state:
    st.session_state["approved"] = {}

high_open = view[(view["urgency"] == "High")
                 & (~view["review_id"].isin(st.session_state["approved"].keys()))]
neg_share = 100 * (view["themes_neg"].str.len() > 0).mean()
alerts = E.early_warnings(view, recent_days=window, baseline_days=window * 3)
try:
    all_actions = A.load_actions(ACTION_LOG)
except ValueError as ex:
    st.error(f"Couldn't read the action log: {ex}")
    st.stop()

unclaimed = datasets.unclaimed_legacy_tags(all_actions)
if unclaimed and legacy_tag is None:
    with st.sidebar.expander("Recover older action history"):
        st.caption("Older actions were saved by filename and may belong to another "
                   "dataset. Nothing has been deleted. Link only after checking "
                   "the history; each history can belong to just one dataset.")
        old_tag = st.selectbox("Older history", unclaimed)
        older_actions = [
            row for row in all_actions if row.get("dataset_tag") == old_tag
        ]
        st.json(older_actions)
        confirmed = st.checkbox(
            "I confirm this older history belongs to the current dataset",
            key=f"confirm_history_{tag}_{old_tag}",
        )
        if st.button("Link older history", disabled=not confirmed):
            try:
                datasets.claim_legacy_history(tag, old_tag, all_actions)
                st.rerun()
            except (ValueError, D.sqlite3.Error) as ex:
                st.error(f"Couldn't link that history: {ex}")

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
                        "Action start date", value=date.today(), key=f"start_date_{key}")
                    due_date = st.date_input(
                        "Due date", value=date.today() + timedelta(days=7),
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
                            )
                            A.save_actions(ACTION_LOG, all_actions + [action])
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

    inbox = view[view["urgency"].isin(urg)].sort_values(
        ["urgency", "date"], key=lambda c: c.map({"High": 0, "Medium": 1, "Low": 2})
        if c.name == "urgency" else c, ascending=[True, False])
    if not show_done:
        inbox = inbox[~inbox["review_id"].isin(st.session_state["approved"].keys())]
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
            if st.button("Approve reply", key=f"a_{r.review_id}"):
                st.session_state["approved"][r.review_id] = text
                st.toast("Approved")
                st.rerun()

# ----------------------------------------------------------------------------
# Export
# ----------------------------------------------------------------------------
with tabs[5]:
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
    lines.extend(A.weekly_action_summary(
        all_actions,
        dataset_tag=tag,
        locations=pick,
        reviews=tagged.to_dict("records"),
        legacy_tag=legacy_tag,
    ))
    st.code("\n".join(lines), language=None)

# ----------------------------------------------------------------------------
# Action tracker
# ----------------------------------------------------------------------------
with tabs[6]:
    st.markdown(
        "Keep a manager's action with the alert, then check later reviews for the same theme. "
        "A change in review mentions is a signal, not proof that an action caused it."
    )
    st.caption("An older saved baseline may use earlier tagging rules. A change in the "
               "analyzer is not evidence of an operational improvement.")
    saved_actions = [
        action for action in all_actions
        if A.matches_dataset(action, tag, legacy_tag) and action.get("location") in pick
    ]
    saved_actions.sort(key=lambda action: action.get("created_on", ""), reverse=True)

    status_filter = st.radio(
        "Show action plans",
        ("All active actions", "Overdue only", "Completed plans"),
        horizontal=True,
        key="action_status_filter",
    )
    if status_filter == "Overdue only":
        visible_actions = [action for action in saved_actions if A.is_overdue(action)]
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
        action_id = action.get("action_id", "")
        with st.container(border=True):
            st.markdown(f"**{action.get('location', 'Location')}: {action.get('theme', 'Theme')}**")
            st.caption(
                f"Status: {action.get('status', 'Planned')} | "
                f"Owner: {action.get('owner') or 'Not assigned'} | "
                f"Due: {action.get('due_date', 'Not set')}"
            )
            if A.is_overdue(action):
                st.warning("Overdue — this active action is past its due date.")

            location_reviews = tagged[tagged["location"] == action.get("location")]
            result = A.follow_up(action, location_reviews.to_dict("records"))
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

            with st.form(f"update_action_{action_id}"):
                action_text = st.text_area(
                    "Manager action", value=action.get("action_text", ""),
                    key=f"update_text_{action_id}")
                cols = st.columns(2)
                owner = cols[0].text_input(
                    "Owner (optional)", value=action.get("owner", ""),
                    key=f"update_owner_{action_id}")
                status = cols[1].selectbox(
                    "Status", A.STATUS_OPTIONS,
                    index=A.STATUS_OPTIONS.index(action.get("status", "Planned"))
                    if action.get("status", "Planned") in A.STATUS_OPTIONS else 0,
                    key=f"update_status_{action_id}")
                start_date = st.date_input(
                    "Action start date",
                    value=A.parse_date(action.get("start_date"), date.today()),
                    key=f"update_start_{action_id}")
                due_date = st.date_input(
                    "Due date",
                    value=A.parse_date(action.get("due_date"), date.today()),
                    key=f"update_due_{action_id}")
                submitted = st.form_submit_button("Save updates")

            if submitted:
                if not action_text.strip():
                    st.error("Enter an action before saving.")
                elif due_date < start_date:
                    st.error("The due date must be on or after the start date.")
                else:
                    updated = A.update_action(
                        action, action_text, owner, status, start_date, due_date)
                    updated_actions = [
                        updated if row.get("action_id") == action_id else row
                        for row in all_actions
                    ]
                    A.save_actions(ACTION_LOG, updated_actions)
                    st.toast("Action updated.")
                    st.rerun()
