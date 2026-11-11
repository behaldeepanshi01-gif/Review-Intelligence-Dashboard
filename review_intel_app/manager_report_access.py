"""Individual local manager sign-in. Shared passwords no longer grant access."""
import threading
import time
import math
import streamlit as st
import manager_identity as identity
import report_downloads

_lock = threading.Lock()
_attempts = []
EXPIRY_WARNING_SECONDS = 300


@st.fragment(run_every="10s")
def show_session_expiry():
    """Refresh only the notice, never the editors holding unsubmitted input."""
    grant = st.session_state.get("_manager_report_grant")
    if not authorized():
        report_downloads.revoke(st.session_state.pop("_manager_report_grant", None))
        clear_private_state()
        st.rerun(scope="app")
    remaining = grant["expires"] - time.time()
    if remaining <= EXPIRY_WARNING_SECONDS:
        minutes = max(1, math.ceil(remaining / 60))
        st.warning(
            f"Sign-in expires in {minutes} minute{'s' if minutes != 1 else ''} or less. "
            "Save any unsaved action edits now using each action's Save button, "
            "including drafts retained under other filters or datasets. "
            "Only edits you are still authorized to save can be saved. "
            "Unsaved drafts are cleared when sign-in expires; they are not saved "
            "automatically. Editing or saving does not extend your sign-in."
        )


def clear_private_state():
    """An identity change must not retain another manager's widgets or drafts."""
    for key in list(st.session_state):
        if key not in {"_manager_username", "_manager_report_password",
                       "_manager_report_error", "_manager_report_grant"}:
            del st.session_state[key]


def authorized(dataset_id=None, locations=None):
    grant = st.session_state.get("_manager_report_grant")
    if dataset_id is None:
        return identity.current_account(grant) is not None
    return identity.permits(grant, dataset_id, locations)


def _try_login():
    password = st.session_state.pop("_manager_report_password", "")
    username = st.session_state.get("_manager_username", "").strip()
    report_downloads.revoke(st.session_state.pop("_manager_report_grant", None))
    clear_private_state()
    # Clear privacy acknowledgments on every identity change.
    for key in list(st.session_state):
        if key.startswith("manager_report_checked_"):
            del st.session_state[key]
    now = time.time()
    with _lock:
        _attempts[:] = [t for t in _attempts if t > now - 60]
        if len(_attempts) >= 10:
            st.session_state["_manager_report_error"] = "Too many attempts. Try again in a minute."
            return
        _attempts.append(now)
    grant = identity.authenticate(username, password)
    if grant:
        st.session_state["_manager_report_grant"] = grant
        st.session_state.pop("_manager_report_error", None)
    else:
        st.session_state["_manager_report_error"] = "Manager ID or password not accepted."


def require_manager(*, purpose="manager report"):
    if authorized():
        st.caption("Signed in as " + st.session_state["_manager_report_grant"]["username"])
        if st.button("Lock " + purpose, key=f"lock_{purpose}"):
            report_downloads.revoke(st.session_state.pop("_manager_report_grant", None))
            clear_private_state()
            for key in list(st.session_state):
                if key.startswith("manager_report_checked_"):
                    del st.session_state[key]
            st.rerun()
        show_session_expiry()
        return True
    report_downloads.revoke(st.session_state.pop("_manager_report_grant", None))
    clear_private_state()
    if not identity.configured():
        st.warning(f"{purpose.capitalize()} locked. The app owner must set up individual accounts "
                   "using manage_managers.py. The shared report password is no longer accepted.")
        return False
    st.info(f"Sign in with your individual manager account to access {purpose}.")
    with st.form(f"{purpose}_login", clear_on_submit=True):
        st.text_input("Manager ID", key="_manager_username")
        st.text_input("Manager report password", type="password", key="_manager_report_password")
        st.form_submit_button("Unlock " + purpose, on_click=_try_login)
    if st.session_state.get("_manager_report_error"):
        st.error(st.session_state["_manager_report_error"])
    return False
