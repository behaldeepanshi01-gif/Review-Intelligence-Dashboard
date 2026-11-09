"""Report generation and download are behind the manager gate."""
import hashlib
import streamlit as st
import action_report as AR
import action_tracker as A
import report_downloads
from manager_report_access import require_manager, authorized


def show_manager_report(actions, tag, pick, tagged, legacy_tag, provenance, timezones):
    st.subheader("Manager action report")
    if not require_manager():
        return
    if not authorized(tag, pick):
        st.warning("You do not have report access to every selected restaurant in this file. "
                   "Select only your assigned restaurants or ask the app owner for access.")
        return
    st.caption("Manager access expires after 30 minutes. Includes active and completed actions "
               "for the selected file and locations. Follow-up ignores dashboard date filters.")
    report_text = AR.build_report(
        actions, tag, pick, tagged.to_dict("records"), legacy_tag=legacy_tag,
        provenance_by_location=provenance, timezones_by_location=timezones)
    st.text_area("Manager report preview", value=report_text, height=240, disabled=True)
    identity_key = st.session_state["_manager_report_grant"]["revision"]
    fingerprint = hashlib.sha256((identity_key + tag + report_text).encode()).hexdigest()
    checked = st.checkbox("I checked the report for private guest details before downloading",
                          key=f"manager_report_checked_{fingerprint}")
    has_actions = any(A.matches_dataset(a, tag, legacy_tag) and a.get("location") in pick
                      for a in actions)
    if not has_actions:
        st.info("No action plans for this file and selected locations. Save a plan in Early warnings.")
    if authorized(tag, pick):
        if st.button(
            "Prepare secure report download",
            disabled=not (checked and has_actions),
            key=f"manager_report_download_{fingerprint}"):
            try:
                token = report_downloads.issue(
                    st.session_state["_manager_report_grant"], tag, pick, report_text,
                    acknowledged=checked)
                st.link_button("Download manager action report (TXT)",
                               f"/dashboard/report-download/{token}")
                st.caption("Single-use link expires in two minutes. Confirm your manager ID "
                           "and password to download. Locking the dashboard invalidates the link. "
                           "Files already downloaded cannot be recalled.")
            except (PermissionError, ValueError) as ex:
                st.warning(str(ex))
