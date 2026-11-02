"""Deliberate manager-only recovery and correction of legacy associations."""

import sqlite3

import streamlit as st


def show_history_controls(store, dataset, actions):
    dataset_id = dataset["dataset_id"]
    legacy_tag = dataset["legacy_tag"]
    revision = dataset["history_revision"]
    notice = st.session_state.pop("history_link_notice", None)
    if notice:
        st.sidebar.success(notice)

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
                    )
                    st.session_state.pop(key, None)
                    st.session_state["history_link_notice"] = "Older history linked."
                    st.rerun()
                except (ValueError, sqlite3.Error) as ex:
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
                )
                st.session_state.pop(key, None)
                st.session_state["history_link_notice"] = (
                    "Older history reassigned. Dataset-ID actions stayed with their datasets."
                    if target else "Older history unlinked. All saved actions are preserved."
                )
                st.rerun()
            except (ValueError, sqlite3.Error) as ex:
                st.error(f"Couldn't correct that history: {ex}")
        if st.button("Cancel history correction"):
            st.session_state.pop(key, None)
            st.rerun()
