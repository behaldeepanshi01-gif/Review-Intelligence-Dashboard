"""Deliberate owner-only recovery and correction of legacy associations."""

import sqlite3

import streamlit as st
import manager_identity as identity


def history_changed(store, association):
    current = store.get(association["dataset_id"])
    return (current["legacy_tag"], current["history_revision"]) != (
        association["legacy_tag"], association["history_revision"])


@st.fragment(run_every="30s")
def show_live_history_notice(store, association):
    """Only this notice rerenders; browser-buffered action forms stay intact."""
    try:
        changed = history_changed(store, association)
    except (ValueError, sqlite3.Error) as ex:
        st.error(f"Couldn't check the history link: {ex}. Ownership is checked again on save.")
        return
    if changed:
        st.warning(
            "The dataset history link changed in another session. Action views refresh "
            "every 30 seconds. Older-history editors are retained to protect your draft; "
            "their saves must pass a fresh ownership check. Use Keep draft and refresh "
            "editor in an affected form before continuing. Dataset-ID actions are unaffected."
        )


def action_editors(state, dataset, actions):
    """Retain old legacy editors, not their ownership permission, across reruns."""
    key = f"history_editors_{dataset['dataset_id']}"
    editors = state.setdefault(key, {})
    current = []
    for action in actions:
        if action.get("dataset_tag") == dataset["dataset_id"]:
            current.append((action, None))
        elif dataset["legacy_tag"] is not None and action.get("dataset_tag") == dataset["legacy_tag"]:
            action_id = action.get("action_id", "")
            if action_id not in editors:
                editors[action_id] = (dict(action), dict(dataset))
    # Prefer the latest action for concurrency comparison, but preserve the
    # association the editor was opened against even if the link comes back.
    latest = {action.get("action_id"): action for action in actions}
    return current + [
        (latest.get(action_id, action), association)
        for action_id, (action, association) in editors.items()
    ]


def show_history_link_log(store, dataset_id):
    """Read-only association audit, independent of recovery controls/actions."""
    with st.sidebar.expander("History-link corrections"):
        st.caption(
            "Read-only record of older-history claims, unlinks, and transfers "
            "involving this dataset, newest first. This is not action-edit history. "
            "Original actions and baselines are unchanged. Changes made before "
            "recording began are not available. Changed by is the authenticated "
            "manager ID, not an action's assigned owner. Unknown means no manager "
            "identity was recorded, including trusted local-owner maintenance."
        )
        try:
            events = store.history_link_events(dataset_id)
        except sqlite3.Error as ex:
            st.error(f"Couldn't load history-link corrections: {ex}")
            return
        if not events:
            st.info("No recorded history-link changes for this dataset.")
            return
        st.dataframe([
            {
                "Time (UTC)": event["occurred_at"],
                "Operation": event["operation"].capitalize(),
                "Changed by": event.get("changed_by") or "Unknown",
                "Legacy tag": event["legacy_tag"],
                "Source dataset ID": event["source_dataset_id"] or "Unlinked",
                "Destination dataset ID": event["destination_dataset_id"] or "Unlinked",
            }
            for event in events
        ], hide_index=True)


def show_history_controls(store, dataset, actions):
    try:
        identity.require_owner(st.session_state.get("_manager_report_grant"))
    except PermissionError:
        st.error("Owner access is required. Sign in again with an authorized owner account.")
        return
    dataset_id = dataset["dataset_id"]
    legacy_tag = dataset["legacy_tag"]
    revision = dataset["history_revision"]
    notice = st.session_state.pop("history_link_notice", None)
    if notice:
        st.sidebar.success(notice)
    show_history_link_log(store, dataset_id)

    if legacy_tag is None:
        unclaimed = store.unclaimed_legacy_tags(actions)
        if not unclaimed:
            return
        with st.sidebar.expander("Recover older action history"):
            st.caption("Older actions were saved by filename and may belong to another "
                       "dataset. Nothing has been deleted. Each history can belong "
                       "to just one dataset.")
            old_tag = st.selectbox("Older history", unclaimed)
            st.write(f"Link to: {dataset['label']} · {dataset_id}")
            st.json([row for row in actions if row.get("dataset_tag") == old_tag])
            key = f"confirm_history_{dataset_id}_{revision}_{old_tag}"
            confirmed = st.checkbox(
                "I confirm this older history belongs to the current dataset", key=key,
            )
            if st.button("Link older history", disabled=not confirmed):
                try:
                    store.claim_legacy_history(
                        dataset_id, old_tag, actions, expected_revision=revision,
                        session=st.session_state.get("_manager_report_grant"),
                    )
                    st.session_state.pop(key, None)
                    st.session_state["history_link_notice"] = "Older history linked."
                    st.rerun()
                except (ValueError, PermissionError, sqlite3.Error) as ex:
                    st.error(f"Couldn't link that history: {ex}")
        return

    with st.sidebar.expander("Correct linked action history"):
        older_actions = [row for row in actions if row.get("dataset_tag") == legacy_tag]
        native_count = sum(row.get("dataset_tag") == dataset_id for row in actions)
        st.write(f"Current dataset: {dataset['label']} · {dataset_id}")
        st.write(f"Linked older history: {legacy_tag}")
        st.caption(f"{len(older_actions)} legacy actions affected (all locations and dates). "
                   f"{native_count} actions created with this dataset's ID will stay here.")
        st.json(older_actions)
        mode = st.radio("History correction", ["Unlink only", "Reassign to another dataset"])
        target = None
        if mode == "Reassign to another dataset":
            eligible = {
                item["dataset_id"]: item
                for item in store.list_datasets(include_sample=True)
                if item["dataset_id"] != dataset_id and item["legacy_tag"] is None
            }
            if not eligible:
                st.info("No other dataset has an empty history link. Unlink only, "
                        "or first correct the destination's existing link.")
                return
            target_id = st.selectbox(
                "Destination dataset", list(eligible),
                format_func=lambda value: f"{eligible[value]['label']} · {value}",
            )
            target = eligible[target_id]
            target_count = sum(row.get("dataset_tag") == target_id for row in actions)
            st.write(f"Destination: {target['label']} · {target_id}")
            st.caption(f"{target_count} destination dataset-ID actions will stay there. "
                       "Only the legacy-history association will move.")
        else:
            st.warning("The older history will no longer appear under this dataset. "
                       "It will remain saved and available under Recover older action history.")
        st.caption("No actions are deleted or rewritten. Original baselines, evidence, "
                   "owners, statuses, and dates remain unchanged.")
        key = (
            f"correct_history_{dataset_id}_{revision}_{legacy_tag}_{mode}_"
            f"{target['dataset_id'] if target else ''}_"
            f"{target['history_revision'] if target else ''}"
        )
        confirmed = st.checkbox(
            "I checked the affected actions and confirm this history correction", key=key,
        )
        if st.button("Confirm history correction", disabled=not confirmed):
            try:
                store.correct_legacy_history(
                    dataset_id, legacy_tag, expected_source_revision=revision,
                    target_id=target["dataset_id"] if target else None,
                    expected_target_revision=target["history_revision"] if target else None,
                    session=st.session_state.get("_manager_report_grant"),
                )
                st.session_state.pop(key, None)
                st.session_state["history_link_notice"] = (
                    "Older history reassigned. Dataset-ID actions stayed with their datasets."
                    if target else "Older history unlinked. All saved actions are preserved."
                )
                st.rerun()
            except (ValueError, PermissionError, sqlite3.Error) as ex:
                st.error(f"Couldn't correct that history: {ex}")
        if st.button("Cancel history correction"):
            st.session_state.pop(key, None)
            st.rerun()
