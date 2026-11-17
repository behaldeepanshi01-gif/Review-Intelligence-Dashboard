"""Read-only inspection of saved review-tag revisions and their renewal sources."""

import streamlit as st

import manager_corrections as C


def render(path, key, *, context):
    with st.expander("Saved tag revisions (read-only)"):
        st.caption(
            "Includes active, replaced and undone tag decisions for this exact review. "
            "Viewing history does not apply tags or make archived decisions eligible "
            "for approval. Decisions lost before archiving began cannot be recovered."
        )
        try:
            revisions = C.load_correction_revisions(path, key)
        except (OSError, ValueError, C.sqlite3.Error) as ex:
            st.error(f"Couldn't load saved tag revisions: {ex}")
            return
        if not revisions:
            st.info("No saved tag revisions for this review.")
            return
        identities = [(r["rules_version"], r["saved_at"]) for r in revisions]
        version, saved_at = st.selectbox(
            "Tag revision to inspect", identities,
            format_func=lambda ref: f"{ref[0]} | saved {ref[1]}",
            key=f"tag-revision-{context}-{key}",
        )
        decision = C.find_correction_revision(revisions, version, saved_at)
        visited = set()
        while decision is not None:
            reference = (decision["rules_version"], decision["saved_at"])
            if reference in visited:
                st.warning("This renewal chain repeats a revision. Inspection stopped.")
                break
            visited.add(reference)
            st.caption(
                f"Tag revision — rules: {reference[0]} | saved: {reference[1]}"
            )
            st.caption(C.decision_origin_label(decision))
            st.json(decision)
            if decision["decision_origin"] != "renewal":
                break
            source_version = decision["source_rules_version"]
            source_revision = decision["source_decision_revision"]
            decision = C.find_correction_revision(revisions, source_version, source_revision)
            if decision is None:
                st.warning(
                    "Referenced tag revision unavailable — rules: "
                    f"{source_version} | saved: {source_revision}. "
                    "It may have been replaced or undone before archiving began."
                )
            else:
                st.write("Referenced source tag revision")
