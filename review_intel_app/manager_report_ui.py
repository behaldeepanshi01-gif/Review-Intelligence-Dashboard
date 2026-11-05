"""Report generation and download are behind the manager gate."""
import hashlib
import streamlit as st
import action_report as AR
import action_tracker as A
from manager_report_access import require_manager, authorized


def show_manager_report(actions, tag, pick, tagged, legacy_tag, provenance, timezones):
    st.subheader("Manager action report")
    if not require_manager():
        return
    st.caption("Manager access expires after 30 minutes. Includes active and completed actions "
               "for the selected file and locations. Follow-up ignores dashboard date filters.")
    report_text = AR.build_report(
        actions, tag, pick, tagged.to_dict("records"), legacy_tag=legacy_tag,
        provenance_by_location=provenance, timezones_by_location=timezones)
    st.text_area("Manager report preview", value=report_text, height=240, disabled=True)
    fingerprint = hashlib.sha256((tag + report_text).encode()).hexdigest()
    checked = st.checkbox("I checked the report for private guest details before downloading",
                          key=f"manager_report_checked_{fingerprint}")
    has_actions = any(A.matches_dataset(a, tag, legacy_tag) and a.get("location") in pick
                      for a in actions)
    if not has_actions:
        st.info("No action plans for this file and selected locations. Save a plan in Early warnings.")
    if authorized():
        st.download_button(
            "Download manager action report (TXT)", report_text,
            file_name="manager_action_report.txt", mime="text/plain",
            disabled=not (checked and has_actions),
            key=f"manager_report_download_{fingerprint}")
