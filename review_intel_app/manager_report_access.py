"""Shared manager passphrase gate for the local report; no account service needed."""
import hashlib
import hmac
import os
import threading
import time

import streamlit as st

_lock = threading.Lock()
_attempts = []
SESSION_SECONDS = 1800


def authorized():
    secret = os.environ.get("MANAGER_REPORT_PASSWORD", "")
    if len(secret) < 16:
        return False
    grant = st.session_state.get("_manager_report_grant", {})
    return (time.time() < grant.get("expires", 0) and hmac.compare_digest(
        grant.get("fingerprint", ""), hashlib.sha256(secret.encode()).hexdigest()))


def _try_login():
    supplied = st.session_state.pop("_manager_report_password", "")
    secret = os.environ.get("MANAGER_REPORT_PASSWORD", "")
    st.session_state.pop("_manager_report_grant", None)
    now = time.time()
    with _lock:
        _attempts[:] = [t for t in _attempts if t > now - 60]
        if len(_attempts) >= 10:
            st.session_state["_manager_report_error"] = "Too many attempts. Try again in a minute."
            return
        _attempts.append(now)
    if len(secret) >= 16 and hmac.compare_digest(supplied.encode(), secret.encode()):
        st.session_state["_manager_report_grant"] = {
            "fingerprint": hashlib.sha256(secret.encode()).hexdigest(),
            "expires": now + SESSION_SECONDS}
        st.session_state.pop("_manager_report_error", None)
    else:
        st.session_state["_manager_report_error"] = "Manager password not accepted."


def require_manager():
    if authorized():
        if st.button("Lock manager report"):
            st.session_state.pop("_manager_report_grant", None)
            st.rerun()
        return True
    if len(os.environ.get("MANAGER_REPORT_PASSWORD", "")) < 16:
        st.warning("Manager report locked. Configure MANAGER_REPORT_PASSWORD in Secrets "
                   "with a passphrase of at least 16 characters.")
        return False
    st.info("Enter the manager passphrase to view or download this report.")
    with st.form("manager_report_login", clear_on_submit=True):
        st.text_input("Manager report password", type="password", key="_manager_report_password")
        st.form_submit_button("Unlock manager report", on_click=_try_login)
    if st.session_state.get("_manager_report_error"):
        st.error(st.session_state["_manager_report_error"])
    return False
