"""Explicit same-dataset recovery of a renamed restaurant's calendar."""
import sqlite3

import streamlit as st


def show_calendar_rename(datasets, dataset, calendars, settings, locations):
    show_calendar_rename_history(calendars, dataset["dataset_id"])
    show_calendar_correction(datasets, dataset, calendars, settings, locations)
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
        except (ValueError, PermissionError, OSError, sqlite3.Error) as ex:
            st.error(f"Couldn't link calendar: {ex}")
        else:
            st.session_state.pop(f"calendar_{dataset_id}_{new}", None)
            st.session_state["calendar_rename_notice"] = (
                f"Calendar linked: {old} → {new}. Timezone kept: {snapshot['timezone']}."
            )
            st.rerun()


def show_calendar_rename_history(calendars, dataset_id):
    with st.expander("Calendar rename history"):
        st.caption(
            "Successful calendar renames and ownership corrections for this dataset. "
            "Times are recorded in UTC; timezone is the calendar timezone at that change. "
            "Links created before history recording have no recorded change time. "
            "This is separate from action edits and dataset-history associations. "
            "Only records for names and current owners you can access are shown."
        )
        events = calendars.rename_history(dataset_id)
        if not events:
            st.info("No recorded calendar name changes are available for your access.")
            return
        st.table([{
            "Changed at (UTC)": event["changed_at"],
            "Change": "Ownership correction" if event["change_kind"] == "correction" else "Rename",
            "Old name": event["old_location"],
            "New name": event["new_location"],
            "Timezone": event["timezone"],
        } for event in reversed(events)])


def show_calendar_correction(datasets, dataset, calendars, settings, locations):
    dataset_id = dataset["dataset_id"]
    links = calendars.ownership(dataset_id)
    if not links:
        return
    with st.container(border=True):
        st.markdown("**Inspect or correct calendar ownership**")
        st.caption(
            "Previous names remain reserved to block stale editors. A correction moves "
            "only this calendar and keeps its timezone. Action histories, baselines and "
            "due dates stay unchanged. You may restore a previous name even if it is "
            "absent from the current reviews."
        )
        st.table([{"Previous name": old, "Current owner": owner}
                  for old, owner in sorted(links.items())])
        sources = sorted(set(links.values()) & set(settings))
        if not sources:
            return
        old = st.selectbox("Calendar to correct", sources, key=f"correct_source_{dataset_id}")
        targets = sorted((set(locations) | {alias for alias, owner in links.items()
                                           if owner == old}) - {old})
        if not targets:
            st.info("No alternative calendar name is available.")
            return
        new = st.selectbox("Correct calendar owner", targets, key=f"correct_target_{dataset_id}")
        snapshot = settings[old]
        occupied = new in settings or (new in links and links[new] != old)
        st.caption(f"Correct {old} → {new}. Keep timezone: {snapshot['timezone']}.")
        if occupied:
            st.warning("This name belongs to another calendar and cannot be overwritten.")
        with st.form(f"correct_calendar_{dataset_id}_{dataset['path']}_{old}_{new}_{snapshot['revision']}"):
            confirmed = st.checkbox("I confirm this is the correct owner of this calendar in this dataset.")
            submitted = st.form_submit_button("Correct calendar link", disabled=occupied)
        if submitted:
            try:
                datasets.correct_calendar_link(
                    calendars, dataset_id, old, new, expected_path=dataset["path"],
                    expected_revision=snapshot["revision"], confirmed=confirmed)
            except (ValueError, PermissionError, OSError, sqlite3.Error) as ex:
                st.error(f"Couldn't correct calendar: {ex}")
            else:
                for name in (old, new):
                    st.session_state.pop(f"calendar_{dataset_id}_{name}", None)
                st.session_state["calendar_rename_notice"] = (
                    f"Calendar corrected: {old} → {new}. Timezone kept: {snapshot['timezone']}."
                )
                st.rerun()
