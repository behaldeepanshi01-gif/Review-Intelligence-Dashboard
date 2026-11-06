"""Private per-action provenance detail; never part of ordinary exports."""

import streamlit as st
from manager_report_access import authorized


def _tags(tags):
    if tags is None:
        return "No applicable manager decision (rule fallback unknown)"
    return ("Positive: " + (", ".join(tags["positive"]) or "none")
            + " | Negative: " + (", ".join(tags["negative"]) or "none"))


def show_decision_changes(action, dataset_id, result):
    with st.expander("Manager decisions since this action was captured"):
        # Recheck the live account and exact dataset/location on every render,
        # including timer refreshes. Reuse report identity, not another login.
        if not authorized(dataset_id, [action.get("location")]):
            st.info("Private decision detail is locked. Sign in under Weekly summary → "
                    "Manager action report with an account assigned to this restaurant "
                    "and dataset.")
            return
        st.caption("Private action detail — no guest names or review text. "
                   "Decision references are opaque hashes, not guest identifiers.")
        if result["decisions_status"] == "unknown":
            st.warning(result["decisions_message"])
        else:
            st.write(result["decisions_message"])
        st.caption(result["decisions_scope"])
        if result["decision_changes"]:
            st.dataframe([
                {"Decision reference": row["decision_ref"],
                 "Change": row["change"].capitalize(),
                 "At capture": _tags(row["before"]),
                 "Now": _tags(row["after"]),
                 "Action-theme evidence": row["theme_evidence"]}
                for row in result["decision_changes"]
            ], hide_index=True, use_container_width=True)
