"""Private per-action provenance detail; never part of ordinary exports."""

import streamlit as st
from manager_corrections import review_key
from manager_report_access import authorized


def _tags(tags):
    if tags is None:
        return "No applicable manager decision (rule fallback unknown)"
    return ("Positive: " + (", ".join(tags["positive"]) or "none")
            + " | Negative: " + (", ".join(tags["negative"]) or "none"))


def show_decision_changes(action, dataset_id, result, *, current_reviews=None,
                          correction_path=None):
    with st.expander("Manager decisions since this action was captured"):
        # Recheck the live account and exact dataset/location on every render,
        # including timer refreshes. Reuse report identity, not another login.
        if not authorized(dataset_id, [action.get("location")]):
            st.info("Private decision detail is locked. Sign in under Weekly summary → "
                    "Manager action report with an account assigned to this restaurant "
                    "and dataset.")
            return
        st.caption("Private action history contains no guest names or review text. "
                   "Decision references are opaque hashes, not guest identifiers. "
                   "Open a reference below to inspect its current source review.")
        if result["decisions_status"] == "unknown":
            st.warning(result["decisions_message"])
        else:
            st.write(result["decisions_message"])
        st.caption(result["decisions_scope"])
        if result.get("tag_effect_status", "unknown") == "unknown":
            st.warning(result.get("tag_effect_message",
                                 "Action-cohort tagging-count effects unknown."))
        else:
            st.write(result["tag_effect_message"])
            st.dataframe([
                {"Cohort": row["cohort"], "Reviews": row["review_count"],
                 "Negative mentions before": row["before_mentions"],
                 "Negative mentions now": row["after_mentions"],
                 "Added mentions": row["added_mentions"],
                 "Removed mentions": row["removed_mentions"],
                 "Net mention change": row["net_mentions"]}
                for row in result["tag_effect_cohorts"]
            ], hide_index=True, width="stretch")
        if result["decision_changes"]:
            st.dataframe([
                {"Decision reference": row["decision_ref"],
                 "Change": row["change"].capitalize(),
                 "At capture": _tags(row["before"]),
                 "Now": _tags(row["after"]),
                 "Action-theme evidence": row["theme_evidence"]}
                for row in result["decision_changes"]
            ], hide_index=True, width="stretch")
            reference = st.selectbox(
                "Open current review for decision reference",
                [row["decision_ref"] for row in result["decision_changes"]],
                index=None, placeholder="Choose a decision reference",
                key=f"action_decision_source_{dataset_id}_{action.get('action_id', '')}",
            )
            if reference is None:
                return
            # Resolve only exact source identities, in memory, after the live
            # dataset/location gate above. Never persist these rows in action logs.
            source = None
            if current_reviews is not None and correction_path is not None:
                for row in current_reviews.to_dict("records"):
                    if (row.get("location") == action.get("location")
                            and review_key(correction_path, row) == reference):
                        source = row
                        break
            if source is None:
                st.info("Source cannot be opened: this exact review is not available "
                        "in the current dataset for this restaurant. It may have been "
                        "removed or changed. No substitute review has been selected.")
                return
            st.caption("Current source review — not a saved historical snapshot. "
                       "This review is shown independently of dashboard date filters.")
            st.write(f"{source['location']} | {source['date']} | "
                     f"{source['rating']} stars")
            st.text(source["text"])
