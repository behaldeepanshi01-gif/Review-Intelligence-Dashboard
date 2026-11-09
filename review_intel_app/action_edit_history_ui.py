"""Read-only action audit display shared by current and absent locations."""

import streamlit as st


def show_action_edit_history(action):
    st.markdown("**Action edit history**")
    st.caption("Successful saves only, newest first. Times are UTC. "
               "Earlier edits made before history was available are not recorded. "
               "Unknown means the saving manager was not recorded. "
               "Owner is the plan's assigned owner, not the person who saved it.")
    history = action.get("edit_history", [])
    if not history:
        st.info("No recorded action edits yet.")
        return
    if not isinstance(history, list):
        st.error("The saved action edit history is invalid.")
        return
    labels = {
        "action_text": "Manager action", "owner": "Owner", "status": "Status",
        "start_date": "Action start date", "due_date": "Due date",
    }
    rows = []
    for entry in reversed(history):
        saved = {
            "Saved at (UTC)": entry["saved_at"],
            "Saved by": entry.get("saved_by") or "Unknown",
        }
        for field, values in entry["changes"].items():
            rows.append(dict(saved, Field=labels.get(field, field),
                             Before=values["before"], After=values["after"]))
        if not entry["changes"]:
            rows.append(dict(saved, Field="Saved without field changes", Before="", After=""))
    st.dataframe(rows, hide_index=True, use_container_width=True)
