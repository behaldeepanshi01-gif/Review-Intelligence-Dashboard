"""Read-only, standard-library coverage audit. Never imports the analyzer.

Writes aggregate evidence only to a private, deployment-excluded directory.
Dates must be explicit ISO calendar dates; ambiguous dates are not guessed.
"""
import argparse
from collections import Counter
import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "review_intel_app/data/private_source_readiness"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_csv(path):
    raw = path.read_bytes()
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    rows = list(reader)
    if not reader.fieldnames or any(None in row or None in row.values() for row in rows):
        raise ValueError("Malformed CSV; audit stopped without repairing records.")
    return raw, reader.fieldnames, rows


def duplicate_counts(values):
    counts = Counter(values)
    groups = [n for n in counts.values() if n > 1]
    return {"groups": len(groups), "rows_in_groups": sum(groups),
            "excess_rows": sum(n - 1 for n in groups)}


def audit(path, as_of):
    raw, fields, rows = read_csv(path)
    required = {"location", "date", "rating", "text"}
    if not required.issubset(fields):
        raise ValueError("Missing required source columns.")
    missing = {k: sum(not r[k].strip() for r in rows) for k in fields}
    dates, invalid_dates, invalid_ratings = [], 0, 0
    for row in rows:
        value = row["date"].strip()
        if value:
            try:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                    raise ValueError("Not an explicit ISO day")
                dates.append(date.fromisoformat(value))
            except ValueError:
                invalid_dates += 1
        if row["rating"].strip():
            try:
                rating = Decimal(row["rating"].strip())
                if not rating.is_finite() or not 1 <= rating <= 5 or rating != rating.to_integral_value():
                    invalid_ratings += 1
            except InvalidOperation:
                invalid_ratings += 1
    dates.sort()
    result = {
        "file": path.relative_to(ROOT).as_posix(), "bytes": len(raw),
        "sha256": digest(raw), "rows": len(rows), "columns": fields,
        "missing_by_column": missing, "invalid_nonblank_dates": invalid_dates,
        "invalid_nonblank_ratings": invalid_ratings,
        "future_dates_relative_to_as_of": sum(d > as_of for d in dates),
        "locations": dict(Counter(r["location"].strip() for r in rows)),
        "source_claims": dict(Counter(r.get("source", "").strip() for r in rows)),
        "ratings": dict(sorted(Counter(r["rating"].strip() for r in rows).items())),
        "duplicates": {
            "exact_rows": duplicate_counts(tuple(r[k] for k in fields) for r in rows),
            "normalized_text": duplicate_counts(
                " ".join(r["text"].split()).casefold() for r in rows if r["text"].strip()),
            "location_date_rating_text": duplicate_counts(
                tuple(" ".join(r[k].split()).casefold() for k in ("location", "date", "rating", "text"))
                for r in rows),
        },
    }
    if "review_id" in fields:
        result["duplicates"]["nonblank_review_ids"] = duplicate_counts(
            r["review_id"].strip() for r in rows if r["review_id"].strip())
    if not dates:
        result["coverage"] = None
        return result
    unique = sorted(set(dates))
    gaps = [
        {"start": (a + timedelta(days=1)).isoformat(),
         "end": (b - timedelta(days=1)).isoformat(), "days": (b - a).days - 1}
        for a, b in zip(unique, unique[1:]) if (b - a).days > 1
    ]
    monthly = Counter(d.strftime("%Y-%m") for d in dates)
    weekly = Counter((d - timedelta(days=d.weekday())).isoformat() for d in dates)
    day = dates[0].replace(day=1)
    while day <= dates[-1]:
        monthly.setdefault(day.strftime("%Y-%m"), 0)
        day = (day.replace(day=28) + timedelta(days=4)).replace(day=1)
    day = dates[0] - timedelta(days=dates[0].weekday())
    while day <= dates[-1]:
        weekly.setdefault(day.isoformat(), 0)
        day += timedelta(days=7)
    end = dates[-1]
    result["coverage"] = {
        "valid_dates": len(dates), "start": dates[0].isoformat(), "end": end.isoformat(),
        "inclusive_span_days": (end - dates[0]).days + 1, "distinct_days": len(unique),
        "days_without_records_inside_span": (end - dates[0]).days + 1 - len(unique),
        "days_since_latest_at_as_of": (as_of - end).days,
        "monthly_rows": dict(sorted(monthly.items())),
        "weekly_rows_monday_start": dict(sorted(weekly.items())),
        "internal_empty_day_runs": gaps,
        "largest_internal_empty_run_days": max((g["days"] for g in gaps), default=0),
        "latest_date_anchored_windows": {
            "recent_30_start_inclusive": (end - timedelta(days=29)).isoformat(),
            "recent_30_end_inclusive": end.isoformat(),
            "recent_30_rows": sum(end - timedelta(days=30) < d <= end for d in dates),
            "prior_90_start_inclusive": (end - timedelta(days=119)).isoformat(),
            "prior_90_end_inclusive": (end - timedelta(days=30)).isoformat(),
            "prior_90_rows": sum(end - timedelta(days=120) < d <= end - timedelta(days=30) for d in dates),
        },
    }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--website", type=Path, required=True)
    parser.add_argument("--yelp", type=Path, required=True)
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    sources = {name: audit(path.resolve(), args.as_of) for name, path in
               (("export", args.export), ("website_testimonials", args.website),
                ("philadelphia_yelp", args.yelp))}
    evidence = {"as_of": args.as_of.isoformat(), "sources": sources,
                "method": "Raw UTF-8 CSV; strict ISO days; no analyzer, source merging, deduplication or imputation."}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    folder = PRIVATE / stamp
    folder.mkdir(parents=True, mode=0o700)
    data = json.dumps(evidence, indent=2, sort_keys=True).encode() + b"\n"
    (folder / "aggregate_evidence_PRIVATE.json").write_bytes(data)
    export = sources["export"]
    c = export["coverage"]
    if c is None:
        raise ValueError("Export has no usable ISO dates; inspect private aggregate evidence.")
    windows = c["latest_date_anchored_windows"]
    monthly = "\n".join(f"| {m} | {n} |" for m, n in c["monthly_rows"].items())
    hashes = "\n".join(f"- {name}: `{s['file']}` — SHA-256 `{s['sha256']}` ({s['bytes']} bytes, {s['rows']} rows)"
                       for name, s in sources.items())
    report = f"""# PRIVATE — Mumbai Central source readiness

Audit as of {args.as_of}. Aggregate-only; no reviewer identities, review wording,
individual review IDs, theme tags or accuracy scores. Keep this directory out of
public assets, demos, source ZIPs and deployment bundles.

## Decision
The CSV supports descriptive, within-file date grouping, not verified Google
coverage or a representative trend claim. The user described it as an “Official
review export”; that is user-reported provenance, not independent authentication.
Explicit source dates are present, but their historical truth cannot be established
from CSV contents. No collection time, filename timestamp or website retrieval
date has been substituted for publication dates.

## Export quality and identity
- Rows: {export['rows']}; valid explicit ISO dates: {c['valid_dates']}.
- Missing values by column: {json.dumps(export['missing_by_column'], sort_keys=True)}.
- Invalid nonblank dates: {export['invalid_nonblank_dates']}; invalid nonblank ratings:
  {export['invalid_nonblank_ratings']}; future dates at audit date:
  {export['future_dates_relative_to_as_of']}.
- Location labels: {json.dumps(export['locations'])}; source labels: {json.dumps(export['source_claims'])}.
- Rating counts: {json.dumps(export['ratings'], sort_keys=True)}.
- Duplicate checks (groups / participating rows / excess rows):
  {json.dumps(export['duplicates'], sort_keys=True)}.
  Exact rows use raw parsed cells; text/content checks fold case and whitespace.
  Duplicate IDs omit blank IDs. These checks do not detect paraphrases or prove
  unique people, unique Google records, or review authenticity. Nothing was removed.
- Intended target: Mumbai Central, 7505 VA-7, Falls Church, VA 22043, from project
  context. The CSV has a matching business name but no address, Google place ID,
  source review URL or independently verifiable location identifier. Its `google`
  field and review IDs are claims, not authentication. Falls Church identity is
  context-supported, not independently established by this file.

## Date coverage
- Observed interval: {c['start']} through {c['end']} inclusive
  ({c['inclusive_span_days']} calendar days); {c['distinct_days']} distinct publication days.
- {c['days_without_records_inside_span']} days inside that interval have no rows;
  largest internal empty run: {c['largest_internal_empty_run_days']} days.
- Latest row is {c['days_since_latest_at_as_of']} days before the audit date.
  No rows before/after the interval does not establish no reviews existed then.
- All monthly and Monday-start weekly counts and every internal empty-day run
  are in aggregate_evidence_PRIVATE.json. Zero-row intervals mean absent records
  in this file, not proven collection outages or zero reviews on Google.

| Observed month | Rows |
| --- | ---: |
{monthly}

First and last months are boundary-truncated observations, not complete-month
samples. An interior month having rows is also not proof of complete capture.
Do not compare November's partial month against full calendar months as a decline.

### Existing early-warning window denominators (no theme analysis)
The engine uses the latest dataset date, not today's date, and a strict lower
boundary. For this file the recent 30-day interval is
{windows['recent_30_start_inclusive']}–{windows['recent_30_end_inclusive']}:
{windows['recent_30_rows']} rows. The preceding 90-day interval is
{windows['prior_90_start_inclusive']}–{windows['prior_90_end_inclusive']}:
{windows['prior_90_rows']} rows. Counts describe available denominators only;
they do not establish adequate theme-level sample sizes, statistical significance,
or action impact. No labels were scored or analyzer functions executed.

## Separate sources — never merged
- Export: the privately supplied CSV audited here, not the website collection.
- Website: existing saved collection of three selected five-star testimonials,
  all undated, attributed to Google by the site. Selection bias and absent dates
  make them unsuitable for weekly/monthly trends or representative complaint rates.
  The saved collection is evidence of that crawl, not a fresh website check.
- Philadelphia Yelp: the earlier, separate 385-row, four-business test input.
  Different businesses and city; not Mumbai Central evidence. Its provenance here
  is project context, not independently authenticated Yelp access. Its aggregate
  audit and hash are retained solely to distinguish the inputs.
- Saved upload registry was inspected read-only during discovery and contained
  only the sample dataset; the original attachment is the located export.
  No upload, registry, sample, website collection or source CSV was changed.

## Readiness and next decision
Ready for explicitly qualified exploration of this file's dated records.
Not ready to claim a complete Google history, population complaint rates,
absence of complaints during gaps, or causal improvement after an action.
Before relying on representative trends, reconcile the source with an authorized
export's place identity, date semantics, extraction time, selection filters,
pagination and expected record counts. Do not request another copy just to repeat
this audit. Any trend UI change needs separate approval.

## Evidence and reproducibility
{hashes}
- Aggregate evidence SHA-256: `{digest(data)}`.
- Source bytes hashed before parsing; UTF-8 BOM accepted; dates require YYYY-MM-DD
  and a valid calendar day. Ratings must be finite integer values 1–5;
  missing, fractional, out-of-range and nonnumeric values are not repaired.
- Review engine inspected only for import and window semantics. Its rating coercion
  and ID rewriting were deliberately bypassed. No analyzer or dashboard edits.
- SHA256SUMS.json hashes the report and evidence; hashes identify bytes, not truth,
  source ownership or completeness. Re-run with audit_source_coverage.py using
  the three paths above and --as-of {args.as_of}.
"""
    (folder / "source_readiness_PRIVATE.md").write_text(report)
    manifest = {p.name: digest(p.read_bytes()) for p in sorted(folder.iterdir()) if p.is_file()}
    (folder / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2) + "\n")
    for p in folder.iterdir():
        p.chmod(0o600)
    print(f"Private aggregate report saved: {folder.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
