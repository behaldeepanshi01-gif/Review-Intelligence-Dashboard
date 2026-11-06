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
