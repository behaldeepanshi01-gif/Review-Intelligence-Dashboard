"""Session-only, individually scoped draft resets. Never writes action history."""

import sqlite3
import streamlit as st


def show_reset(key, fields, load_target, clear_keys, snapshot_key=None,
               label="Discard unsaved changes"):
    """Recheck authorization and saved state on every click, including confirmation.

    load_target returns (full saved snapshot, editable widget defaults). Keeping
    the full snapshot in the confirmation token also detects evidence-only edits.
    Callbacks run before widget creation so deleting widget state is safe.
    """
    pending_key = f"discard_pending_{key}"
    error_key = f"discard_error_{key}"

    def reset(confirm=False):
        try:
            target, defaults = load_target()
        except (OSError, ValueError, PermissionError, sqlite3.Error) as ex:
            st.session_state[error_key] = f"Couldn't reset this editor: {ex}"
            st.session_state.pop(pending_key, None)
            return
        draft = {name: st.session_state.get(widget, defaults[name])
                 for name, widget in fields.items()}
        token = (target, defaults, draft)
        changed = draft != defaults
        pending = st.session_state.get(pending_key)
        if (confirm and pending != token) or (not confirm and changed):
            st.session_state[pending_key] = token
            return
        # Only this editor's keys, including older snapshot versions, are removed.
        for widget in list(st.session_state):
            if clear_keys(widget):
                del st.session_state[widget]
        # Deletion alone lets an unchanged browser widget restore its old value.
        # Explicitly set defaults when its identity will stay the same. A changed
        # saved snapshot gets new widget identities, so leave old keys removed.
        if snapshot_key is None or st.session_state.get(snapshot_key) == target:
            for name, widget in fields.items():
                st.session_state[widget] = defaults[name]
        if snapshot_key:
            st.session_state[snapshot_key] = dict(target)
        st.session_state.pop(pending_key, None)
        st.session_state.pop(error_key, None)

    st.button(label, key=f"discard_{key}", on_click=reset)
    if error_key in st.session_state:
        st.error(st.session_state[error_key])
    if pending_key in st.session_state:
        target, defaults, draft = st.session_state[pending_key]
        st.warning("Discard this editor's unsaved changes? Other drafts and the "
                   "saved action log will not change. If the saved action changes "
                   "again, review the new values and confirm again.")
        st.dataframe([
            {"Field": name, "Unsaved draft": str(draft[name]),
             "Reset to": str(defaults[name])}
            for name in fields
        ], hide_index=True)
        st.button("Confirm discard", key=f"confirm_discard_{key}",
                  on_click=reset, args=(True,))
        st.button("Keep editing", key=f"cancel_discard_{key}",
                  on_click=lambda: st.session_state.pop(pending_key, None))
