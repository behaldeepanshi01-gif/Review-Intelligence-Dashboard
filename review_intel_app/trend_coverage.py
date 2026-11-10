"""Descriptive coverage of accepted rows; never a source-completeness estimate."""
from datetime import timedelta

import pandas as pd


DISCLAIMER = (
    "Coverage describes accepted CSV records only, not complete Google review history. "
    "No records in this file—not evidence of zero Google reviews or a collection outage. "
    "Even interior periods with records are not proof of complete capture."
)
SMALL_N = 5


def coverage_tables(tagged, view, locations, selected):
    """Use authorized rows only. Keep unfiltered observations separate from filters."""
    start, end = map(pd.Timestamp, selected)
    observations, months, weeks, gaps = [], [], [], []
    for loc in locations:
        source = tagged.loc[tagged["location"] == loc, "date"]
        rows = view[view["location"] == loc]
        dates = rows["date"]
        observed_start = source.min() if len(source) else pd.NaT
        observed_end = source.max() if len(source) else pd.NaT
        observations.append({
            "Location": loc,
            "First available date": None if pd.isna(observed_start) else observed_start.date(),
            "Last available date": None if pd.isna(observed_end) else observed_end.date(),
            "Selected rows": len(rows),
        })
        for month in pd.period_range(start, end, freq="M"):
            left, right = month.start_time, month.end_time.normalize()
            group = rows[dates.dt.to_period("M") == month]
            reasons = []
            if start > left or end < right:
                reasons.append("Date filter cuts month")
            if pd.notna(observed_start) and (observed_start > left or observed_end < right):
                reasons.append("Outside observed boundaries")
            n = len(group)
            if not n:
                reasons.append("No records in this file")
            elif n < SMALL_N:
                reasons.append("Few rows (<5); compare cautiously")
            months.append({
                "location": loc, "month": left, "reviews": n,
                "avg_rating": round(group["rating"].mean(), 2) if n else float("nan"),
                "context": "; ".join(reasons) or "Coverage completeness unknown",
            })
        # Monday-start bins include zero-row weeks within the selected range.
        monday = start - pd.Timedelta(days=start.weekday())
        for left in pd.date_range(monday, end, freq="7D"):
            right = left + pd.Timedelta(days=6)
            n = int(((dates.dt.normalize() >= left) & (dates.dt.normalize() <= right)).sum())
            if not n:
                weeks.append({"Location": loc, "Week starting Monday": left.date(),
                              "Selected interval start": max(left, start).date(),
                              "Selected interval end": min(right, end).date(),
                              "CSV rows": 0})
        unique = sorted(set(dates.dt.date))
        for a, b in zip(unique, unique[1:]):
            if (b - a).days > 1:
                gaps.append({"Location": loc, "Start": a + timedelta(days=1),
                             "End": b - timedelta(days=1), "Days without rows": (b - a).days - 1})
    return (pd.DataFrame(observations), pd.DataFrame(months),
            pd.DataFrame(weeks), pd.DataFrame(gaps))


def warning_windows(view, locations, recent_days):
    """Mirror engine.early_warnings' shared anchor and strict lower boundaries."""
    end = view["date"].max()
    if pd.isna(end):
        return pd.DataFrame()
    recent_start = end - timedelta(days=recent_days)
    base_start = recent_start - timedelta(days=3 * recent_days)
    result = []
    for loc in locations:
        dates = view.loc[view["location"] == loc, "date"]
        for label, lower, upper in (
            ("Recent", recent_start, end), ("Baseline", base_start, recent_start)
        ):
            n = int(((dates > lower) & (dates <= upper)).sum())
            result.append({
                "Location": loc, "Period": label,
                "After (exclusive)": lower, "Through (inclusive)": upper,
                "CSV rows (denominator)": n,
                "Context": ("No records; comparison unavailable" if not n else
                            "Few rows (<5); compare cautiously" if n < SMALL_N else
                            "Coverage completeness unknown"),
            })
    return pd.DataFrame(result)
