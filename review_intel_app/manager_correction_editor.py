"""Revision-bound tag forms; drafts stay private to the authenticated session."""

import streamlit as st

import engine as E
import manager_corrections as C


def _revision(decision):
    return (decision or {}).get("saved_at")


def _accept_latest(state_key, prefix, latest, positive, negative, discard):
    """Callback args bind acknowledgment to the comparison actually displayed."""
    st.session_state[state_key]["expected_revision"] = _revision(latest)
    st.session_state[state_key].pop("conflict", None)
    if discard:
        st.session_state[prefix + "-positive"] = positive
        st.session_state[prefix + "-negative"] = negative


def render(path, key, row, require_access):
    version = E.LOCAL_ANALYZER_VERSION
    prefix = f"tag-editor-{key}-{version}"
    state_key = prefix + "-state"
    latest = row["manager_correction"]
    if state_key not in st.session_state:
        st.session_state[state_key] = {"expected_revision": _revision(latest)}
        st.session_state[prefix + "-positive"] = list(row["themes_pos"])
        st.session_state[prefix + "-negative"] = list(row["themes_neg"])
    state = st.session_state[state_key]
    expected = state["expected_revision"]
    conflict = state.get("conflict") or expected != _revision(latest)
    if conflict:
        st.warning(
            "Another manager changed or removed this decision. Nothing was overwritten. "
            "Your unsaved tag draft is still in the form below. Compare it with the "
            "latest saved decision before choosing what to do.")
        st.write("Latest saved decision")
        if latest:
            st.caption("Saved revision: " + latest["saved_at"])
            st.json({k: latest[k] for k in ("themes_pos", "themes_neg")})
        else:
            st.info("No manager decision is currently saved; local rules apply.")
            st.json(row["rule_output"])
        st.caption(
            "Keeping your draft does not save it. Review the latest tags above, then "
            "keep your draft to edit or save against that revision. Loading the latest "
            "tags replaces your unsaved selections.")

    # Stable widget identity is essential: a concurrent save must not reset the
    # browser's buffered form values on submission. Undo also submits the draft.
    with st.form(prefix):
        positive = st.multiselect(
            "Confirmed praise themes", list(E.THEMES),
            key=prefix + "-positive", format_func=E.THEME_LABELS.get)
        negative = st.multiselect(
            "Confirmed complaint themes", list(E.THEMES),
            key=prefix + "-negative", format_func=E.THEME_LABELS.get)
        save = st.form_submit_button("Save manager decision", disabled=bool(conflict))
        undo = st.form_submit_button(
            "Undo manager decision", disabled=bool(conflict)) if expected else False
        if conflict:
            args = (state_key, prefix, latest,
                    list(row["themes_pos"]), list(row["themes_neg"]))
            st.form_submit_button(
                "Review latest and keep my draft", on_click=_accept_latest,
                args=(*args, False))
            st.form_submit_button(
                "Discard my draft and load latest tags", on_click=_accept_latest,
                args=(*args, True))
    if not (save or undo):
        return
    require_access()
    try:
        if save:
            C.save_correction(path, key, positive, negative, version,
                              expected_revision=expected)
        else:
            C.undo_correction(path, key, version, expected_revision=expected)
    except C.CorrectionConflictError:
        state["conflict"] = True
        st.rerun()
    except (OSError, ValueError, C.sqlite3.Error) as ex:
        st.error(f"Couldn't {'save' if save else 'undo'} the manager decision: {ex}")
    else:
        for name in (state_key, prefix + "-positive", prefix + "-negative"):
            del st.session_state[name]
        st.rerun()
