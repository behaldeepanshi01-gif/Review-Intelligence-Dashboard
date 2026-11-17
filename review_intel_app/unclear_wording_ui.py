"""Fictional example showing when unclear wording asks a manager to review a tag."""
import streamlit as st

import engine as E
import local_analyzer as L

UNCLEAR_WORDING_EXAMPLE = "Are the prices fair? Maybe — not sure."


def build_unclear_wording_example(themes=None):
    """Run the frozen local analyzer on the fictional unclear-wording example."""
    active_themes = E.THEMES if themes is None else themes
    positive, negative, evidence, reasons = L.analyze_text(
        UNCLEAR_WORDING_EXAMPLE, active_themes
    )
    flagged_themes = sorted({
        E.THEME_LABELS.get(item["theme"], item["theme"])
        for item in evidence
        if item.get("polarity") == "Needs review"
    })
    return {
        "text": UNCLEAR_WORDING_EXAMPLE,
        "themes_pos": sorted(positive),
        "themes_neg": sorted(negative),
        "flagged_themes": flagged_themes,
        "evidence": evidence,
        "reasons": reasons,
        "needs_review": bool(reasons),
    }


def show_unclear_wording_example(themes=None):
    """Display a clear fictional example of why unclear wording asks a manager instead of guessing."""
    example = build_unclear_wording_example(themes)
    st.markdown("**Example: when unclear wording asks a manager instead of guessing**")
    st.caption(
        "Fictional example (not from any restaurant's reviews): "
        f"“{example['text']}”"
    )
    flagged = ", ".join(example["flagged_themes"]) or "Needs manager review"
    st.caption(
        f"Auto-counted praise/complaint tags: none · Flagged for manager check: {flagged}"
    )
    if example["reasons"]:
        st.caption("Why it asks a manager: " + " ".join(example["reasons"]))
