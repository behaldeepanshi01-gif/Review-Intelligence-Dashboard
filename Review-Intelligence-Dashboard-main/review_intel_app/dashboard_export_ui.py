"""Private exports share the report service and the dashboard's local identity."""
import hashlib
import json

import streamlit as st
import report_downloads


def secure_export(label, content, *, dataset, locations, file_name, mime, key=None):
    grant = st.session_state.get("_manager_report_grant")
    payload = content.encode("utf-8") if isinstance(content, str) else bytes(content)
    locations = sorted(set(locations))
    fingerprint = hashlib.sha256(
        json.dumps([grant, dataset, locations, file_name, mime, key],
                   sort_keys=True).encode() + payload
    ).hexdigest()
    checked = st.checkbox(
        f"I checked {file_name} for private details before downloading",
        key=f"export_checked_{fingerprint}",
    )
    st.caption("Secure downloads require your manager ID and password again. Links are "
               "single-use and expire in two minutes. Preparing another export replaces "
               "your previous link. Locking the dashboard invalidates outstanding links. "
               "Files already downloaded cannot be recalled.")
    if st.button(f"Prepare secure export: {label}", disabled=not checked,
                 key=f"export_prepare_{fingerprint}"):
        try:
            token = report_downloads.issue(
                grant, dataset, locations, payload, acknowledged=checked,
                filename=file_name, media_type=mime)
        except (PermissionError, ValueError) as ex:
            st.warning(str(ex))
        else:
            st.link_button(label, f"/dashboard/report-download/{token}")
