"""Read-only coverage context. No analyzer or source changes."""
import streamlit as st

from trend_coverage import DISCLAIMER, warning_windows


def show_monthly_coverage(tables, selected):
    observations, months, weeks, gaps = tables
    st.warning(DISCLAIMER)
    st.caption(
        f"Selected dates: {selected[0]} through {selected[1]}, inclusive. "
        "Boundary-limited months and months with fewer than 5 rows should not be "
        "read as comparable full-month samples. The <5 notice is a descriptive "
        "caution, not a statistical reliability threshold. Empty ratings remain undefined."
    )
    st.dataframe(observations, hide_index=True, width="stretch")
    with st.expander("Monthly denominators and absent-record intervals"):
        st.dataframe(months.rename(columns={
            "location": "Location", "month": "Month", "reviews": "CSV rows",
            "avg_rating": "Average rating", "context": "Context",
        }), hide_index=True, width="stretch")
        st.caption("Monday-start weeks with no rows in the selected interval")
        if weeks.empty:
            st.write("No empty weekly bins in this selection; completeness is still unknown.")
        else:
            st.dataframe(weeks, hide_index=True, width="stretch")
        st.caption("Internal gaps between observed dates in this selection")
        if gaps.empty:
            st.write("No internal date gaps in this selection; completeness is still unknown.")
        else:
            st.dataframe(gaps, hide_index=True, width="stretch")


def show_warning_coverage(view, locations, window):
    st.warning(
        "Compare available records cautiously. Empty or small denominators can make "
        "shares misleading. A 'new issue' label can reflect an empty baseline, not "
        "a newly emerging complaint. No alert does not prove no complaints."
    )
    st.caption(
        "Windows end at the latest filtered review date across selected locations, "
        "not today or each location's latest date. Baseline length is 3× the recent "
        "window. All denominators use filtered records; date filters may truncate them. "
        "Recent periods with fewer than 5 rows do not generate alerts. "
        "The <5 baseline notice is descriptive only; thresholds are unchanged."
    )
    st.dataframe(warning_windows(view, locations, window),
                 hide_index=True, width="stretch")
    st.caption(DISCLAIMER)
