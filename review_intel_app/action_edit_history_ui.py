"""Read-only action audit display shared by current and absent locations."""

import streamlit as st


SAVES_PER_PAGE = 20


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
    total = len(history)
    pages = (total + SAVES_PER_PAGE - 1) // SAVES_PER_PAGE
    page = 1
    if pages > 1:
        page_key = (f"action_edit_history_page_{action.get('dataset_tag', '')}_"
                    f"{action['action_id']}")
        # A refreshed history can be shorter; never leave an inaccessible page.
        if page_key in st.session_state:
            bounded_page = max(
                1, min(int(st.session_state[page_key]), pages))
            if bounded_page != st.session_state[page_key]:
                st.session_state[page_key] = bounded_page
        page = int(st.number_input(
            "History page", min_value=1, max_value=pages,
            value=None if page_key in st.session_state else 1, step=1,
            key=page_key,
            help="Page 1 has the newest saves. Higher pages show older saves. "
                 "All field changes from a save stay together."))
    offset = (page - 1) * SAVES_PER_PAGE
    end = min(offset + SAVES_PER_PAGE, total)
    st.caption(f"Page {page} of {pages} · Showing saves {offset + 1}–{end} "
               f"of {total}, newest first · Up to {SAVES_PER_PAGE} saves per page.")
    rows = []
    # Slice before expanding field changes: do not build rows for older pages.
    for entry in reversed(history[total - end:total - offset]):
        saved = {
            "Saved at (UTC)": entry["saved_at"],
            "Saved by": entry.get("saved_by") or "Unknown",
        }
        for field, values in entry["changes"].items():
            rows.append(dict(saved, Field=labels.get(field, field),
                             Before=values["before"], After=values["after"]))
        if not entry["changes"]:
            rows.append(dict(saved, Field="Saved without field changes", Before="", After=""))
    st.dataframe(rows, hide_index=True, width="stretch")
