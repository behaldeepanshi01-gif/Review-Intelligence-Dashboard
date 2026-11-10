# Private source coverage audit

This is a read-only audit utility, separate from the dashboard and analyzer.
It does not import records, score labels, infer dates or combine sources.
It writes an aggregate Markdown report, JSON evidence and SHA-256 manifest to
`data/private_source_readiness/<run>/`, excluded from Git and deployment.
Do not attach that directory to public assets, source ZIPs, videos or demos.

From the workspace root, reproduce the Mumbai Central audit:

```sh
python review_intel_app/audit_source_coverage.py \
  --export attached_assets/mumbai_central_reviews_1793677255749.csv \
  --website review_intel_app/data/private_website_reviews/20261105T223618131112Z/website_testimonials_PRIVATE.csv \
  --yelp attached_assets/0_YELP_UPLOAD_1793648198191.csv \
  --as-of 2026-11-06
```

Existing attachments are used; no replacement upload or network collection is
needed. The report is intentionally local/private rather than a Library download.
The private generated files are not included in source merges; regenerate in the
destination workspace from its existing private inputs if needed.

Verification uses synthetic records only:

```sh
cd review_intel_app
python -B -m unittest test_source_coverage -v
```

Raw CSV bytes are hashed before parsing. Duplicate checks cover exact records,
nonblank IDs, normalized text, and location/date/rating/text tuples. Date parsing
accepts only explicit ISO calendar days and does not guess ambiguous formats.
The audit measures all monthly/weekly bins and empty-day runs within the observed
interval. An empty bin is not evidence of missing collection or zero actual reviews.

The export's “official” provenance is user-reported, not authenticated. The
website's selected undated testimonials and Philadelphia Yelp test input remain
separate sources. Hashes establish byte identity, not provenance or completeness.
The utility's narrative is specific to this audit and its known source context;
it is not a generic source-authentication service.

No trend UI changes are authorized by this audit.

## Reconcile an existing source workbook

When the user supplies the original Outscraper workbook, compare it with the
existing CSV rather than requesting another CSV or collecting new reviews:

```sh
python -B review_intel_app/reconcile_source_workbook.py \
  --workbook 'attached_assets/0_Outscraper-20261103033201s3ccf_(1)_1794330514022.xlsx' \
  --export attached_assets/mumbai_central_reviews_1793677255749.csv

cd review_intel_app
python -B -m unittest test_source_workbook_reconciliation test_source_coverage -v
```

The standalone standard-library utility reads a single-sheet OOXML export,
rejects formulas and unexpected sheet layouts, and never imports the analyzer.
It compares the nonblank-text subset using date/rating/text multisets and row
order; only HTML line-break tags and whitespace are normalized for comparison.
Original records, IDs and dates remain untouched. Aggregate output and its
SHA-256 manifest go to a new private source-readiness directory. No review text,
author identity, per-review IDs or pagination markers are emitted.

A private companion `collection_scope_reconciliation_PRIVATE.md` records the
source-specific conclusion, public business-identity corroboration, provider
field documentation and the unresolved job controls. Findings belong only in
that private directory, not public demos or this guide. It supersedes the initial
blocked reconciliation, which is retained as earlier evidence. Generated evidence
is not merged; repeat the command and retain the narrative privately in the
destination workspace using the already available originals.

Interpret a successful content match narrowly: it establishes a relationship
between supplied files, not independent source authentication. Workbook creation
properties are not authenticated extraction times; per-record pagination markers
do not prove page completion; place totals are not necessarily expected job
counts. Query wording and observed ordering are not saved limit/filter settings.
Preserve UTC versus restaurant-local calendar distinctions without changing the
analyzer. Resolve missing settings only with an original, redacted provider job
receipt/settings/log linked to the workbook—not another review upload or scrape.
