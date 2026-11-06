"""Explicit same-dataset recovery of a renamed restaurant's calendar."""
import sqlite3

import streamlit as st


def show_calendar_rename(datasets, dataset, calendars, settings, locations):
    sources = sorted(set(settings) - set(locations))
    if not sources:
        return
    st.markdown("**Restaurant renamed?**")
    st.caption(
        "After updating this same dataset, link an old calendar to its new restaurant name. "
        "Nothing is matched automatically. This moves only the timezone; action histories, "
        "baselines and due dates are not renamed or changed."
    )
    dataset_id = dataset["dataset_id"]
    old = st.selectbox("Previous calendar location", sources,
                       key=f"rename_source_{dataset_id}")
    new = st.selectbox("Renamed restaurant location", locations,
                       key=f"rename_target_{dataset_id}")
    snapshot = settings[old]
    st.caption(f"Move {old} → {new}: {snapshot['timezone']}")
    occupied = new in settings
    if occupied:
        st.warning("This destination already has a saved calendar. It cannot be overwritten.")
    with st.form(f"rename_calendar_{dataset_id}_{dataset['path']}_{old}_{new}_{snapshot['revision']}"):
        confirmed = st.checkbox("I confirm these names refer to the same restaurant in this dataset.")
        submitted = st.form_submit_button("Link renamed restaurant calendar", disabled=occupied)
    if submitted:
        try:
            datasets.rename_location_calendar(
                calendars, dataset_id, old, new, expected_path=dataset["path"],
                expected_revision=snapshot["revision"], confirmed=confirmed,
            )
        except (ValueError, OSError, sqlite3.Error) as ex:
            st.error(f"Couldn't link calendar: {ex}")
        else:
            st.session_state.pop(f"calendar_{dataset_id}_{new}", None)
            st.session_state["calendar_rename_notice"] = (
                f"Calendar linked: {old} → {new}. Timezone kept: {snapshot['timezone']}."
            )
            st.rerun()
