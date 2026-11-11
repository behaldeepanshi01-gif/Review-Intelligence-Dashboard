"""Owner maintenance is separate from exact-location manager views."""
import hashlib
import io
import sqlite3

import streamlit as st

import engine
from legacy_history_ui import show_history_controls


def show_owner_datasets(access, store, action_path):
    access.require_owner()
    st.header("Owner dataset maintenance")
    st.info("Owner capability allows registering datasets and inspecting all older histories. "
            "It does not grant restaurant dashboard access. Assign exact dataset IDs and "
            "locations using the local account tool after registration.")
    upload = st.file_uploader("Register a separate review CSV", type="csv", key="owner_csv")
    if upload is not None:
        content = upload.getvalue()
        try:
            _, validation = engine.preview_reviews(io.BytesIO(content))
            st.write(f"Total: {validation['total']} · Accepted: {validation['accepted']} · "
                     f"Rejected: {validation['rejected']}")
            st.json(validation["reasons"])
            st.caption(engine.RATING_POLICY)
            if validation["ratings"]["changed"]:
                st.dataframe(validation["ratings"]["rows"], hide_index=True)
            token = hashlib.sha256(content + upload.name.encode()).hexdigest()
            confirmed = st.checkbox(
                "Create a separate dataset; do not replace reviews or attach older history",
                key=f"owner_confirm_{token}")
            saved_key = f"owner_saved_{token}"
            if st.button("Register dataset", disabled=(
                    not confirmed or not validation["accepted"] or saved_key in st.session_state)):
                result = access.register_dataset(store, upload.name, content, confirmed=confirmed)
                st.session_state[saved_key] = result["dataset_id"]
            if saved_key in st.session_state:
                st.success(f"Registered dataset: {st.session_state[saved_key]}")
        except (ValueError, UnicodeError, OSError, sqlite3.Error) as ex:
            st.error(f"Couldn't register this CSV: {ex}")
    entries = {row["dataset_id"]: row for row in access.owner_datasets(store)}
    if entries:
        selected = st.selectbox("Dataset for history recovery", list(entries),
                                format_func=lambda key: f"{entries[key]['label']} · {key}")
        st.caption("Use the sidebar to inspect, confirm, and recover or correct older history. "
                   "Snapshots, action records, and saved baselines are preserved.")
        show_history_controls(store, entries[selected], access.owner_actions(action_path))
