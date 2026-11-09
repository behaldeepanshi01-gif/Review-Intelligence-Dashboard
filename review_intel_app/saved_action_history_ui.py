"""Authorized action history, deliberately independent of current-review filters."""
import hashlib
import json

import streamlit as st

import action_tracker as A
import dataset_store as D
from location_settings import LocationSettings


def show_saved_action_history(access, datasets, dataset, raw, action_log,
                              settings_path, require_access):
    tag = dataset["dataset_id"]
    require_access(tag)
    # Always reread both the association and actions; widget state is not authority.
    dataset = datasets.get(tag)
    try:
        actions = access.actions(action_log, dataset)
        settings = LocationSettings(settings_path, session=access.session).load(tag)
    except (OSError, ValueError, D.sqlite3.Error) as ex:
        st.error(f"Couldn't read saved action history: {ex}")
        return
    absent = sorted({a["location"] for a in actions
                     if a.get("location") not in set(raw["location"])})
    st.title("Saved actions for absent locations")
    st.caption(f"Selected dataset: {dataset['label']} · {tag}")
    st.info("These locations have saved plans but no current reviews in this dataset "
            "snapshot. This history is separate from review filters and charts. "
            "No reviews are invented and saved evidence and baselines stay unchanged. "
            "Follow-up trends are unavailable until reviews for the location return.")
    if not absent:
        st.info("No saved plans for absent locations in your assigned restaurants.")
        return
    location = st.selectbox("Saved-action location", absent,
                            key=f"action_history_location_{tag}")
    require_access(tag, [location])
    timezone = settings.get(location, LocationSettings.default())["timezone"]
    today = A.location_today(location, {location: timezone})
    st.caption(f"Action calendar: {today.isoformat()} · {timezone}")
    status = st.radio("Saved-history status", ["All plans", "Active plans",
                                             "Overdue only", "Completed plans"],
                      horizontal=True, key=f"action_history_status_{tag}")
    visible = sorted((a for a in actions if a.get("location") == location),
                     key=lambda a: a.get("created_on", ""), reverse=True)
    if status == "Active plans":
        visible = [a for a in visible if a.get("status") != "Done"]
    elif status == "Completed plans":
        visible = [a for a in visible if a.get("status") == "Done"]
    elif status == "Overdue only":
        visible = [a for a in visible if A.is_overdue(a, today)]
    if not visible:
        st.info("No plans match this status. Choose All plans to see saved history.")
    for action in visible:
        require_access(tag, [location])
        with st.container(border=True):
            st.subheader(f"{location}: {action.get('theme', 'Theme')}")
            st.write(action.get("action_text", ""))
            st.caption(f"Status: {action.get('status', 'Planned')} | "
                       f"Owner: {action.get('owner') or 'Not assigned'} | "
                       f"Due: {action.get('due_date', 'Not set')}")
            if A.is_overdue(action, today):
                st.warning("Overdue — this active action is past its due date.")
            source = A.comparison_source(action, raw.to_dict("records"), tag)
            st.warning(source["source_message"])
            st.caption(source["source_details"])
            with st.expander("Saved evidence, baseline and edit history"):
                st.caption("Read-only original record. Missing historical evidence "
                           "is not reconstructed from the current snapshot.")
                st.json(action)
            _edit_action(action, dataset, datasets, action_log, require_access)


def _edit_action(action, dataset, datasets, action_log, require_access):
    tag, action_id = dataset["dataset_id"], action["action_id"]
    snapshot_key = f"action_snapshot_history_{tag}_{action_id}"
    association_key = f"{snapshot_key}_association"
    if snapshot_key not in st.session_state:
        st.session_state[snapshot_key] = dict(action)
        st.session_state[association_key] = dict(dataset)
    snapshot = st.session_state[snapshot_key]
    association = st.session_state[association_key]
    stale_link = snapshot.get("dataset_tag") != tag and (
        association["legacy_tag"], association["history_revision"]) != (
            dataset["legacy_tag"], dataset["history_revision"])
    conflicted = snapshot != action
    version = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
    prefix = f"update_history_{tag}_{action_id}_{version}"

    def initial(key, value):
        return None if key in st.session_state else value

    with st.expander("Edit saved plan"):
        st.caption("Only Save updates saves changes. Drafts stay in this signed-in "
                   "session when navigating away; locking or closing clears them.")
        if conflicted:
            st.warning("Another manager changed this action. Your draft was not saved. "
                       "Copy it before reloading the latest saved plan.")
        if stale_link:
            st.warning("This older-history link changed. Copy your draft before "
                       "reloading the editor. Nothing has been saved.")
        text = st.text_area("Manager action", key=f"update_text_{prefix}",
                           value=initial(f"update_text_{prefix}", snapshot["action_text"]))
        owner = st.text_input("Owner (optional)", key=f"update_owner_{prefix}",
                              value=initial(f"update_owner_{prefix}", snapshot.get("owner", "")))
        status = st.selectbox(
            "Status", A.STATUS_OPTIONS, key=f"update_status_{prefix}",
            index=initial(f"update_status_{prefix}",
                          A.STATUS_OPTIONS.index(snapshot.get("status", "Planned"))))
        start = st.date_input(
            "Action start date", key=f"update_start_{prefix}",
            value=initial(f"update_start_{prefix}", A.parse_date(snapshot["start_date"])))
        due = st.date_input(
            "Due date", key=f"update_due_{prefix}",
            value=initial(f"update_due_{prefix}", A.parse_date(snapshot["due_date"])))
        if st.button("Reload latest saved plan", key=f"{prefix}_reload"):
            require_access(tag, [snapshot["location"]])
            st.session_state[snapshot_key] = dict(action)
            st.session_state[association_key] = dict(dataset)
            # Reload must discard fields even when the saved version is unchanged.
            for field in ("text", "owner", "status", "start", "due"):
                st.session_state.pop(f"update_{field}_{prefix}", None)
            st.rerun()
        if st.button("Save updates", key=f"{prefix}_save",
                     disabled=conflicted or stale_link):
            require_access(tag, [snapshot["location"]])
            try:
                updated = A.edit_saved_action(
                    action_log, snapshot, text, owner, status, start, due,
                    history_store=datasets, dataset_id=tag,
                    expected_history_revision=association["history_revision"])
            except (OSError, ValueError, D.sqlite3.Error) as ex:
                st.error(f"Couldn't update the action: {ex}. Your draft is still here.")
            else:
                st.session_state[snapshot_key] = updated
                st.toast("Action updated.")
                st.rerun()
