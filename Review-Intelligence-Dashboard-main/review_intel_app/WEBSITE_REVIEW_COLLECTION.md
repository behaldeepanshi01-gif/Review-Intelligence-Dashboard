# Official website testimonial collection

Run the free, standard-library collector from this directory:

```sh
python collect_website_reviews.py
python -B -m unittest test_website_collection -v
```

The collector checks robots.txt, the sitemap and same-domain page links, with
at least one second between requests. It never follows third-party review links
or requests private endpoints. Review text and reviewer identity headings never
appear in console output. Identity headings are used only inside a one-way
record fingerprint, not exported as columns.

Each run creates a separate timestamped directory in
`data/private_website_reviews/`. Existing runs and all app datasets are untouched.
The CSV preserves the published testimonial wording, normalizing HTML whitespace.
It includes the displayed rating, source attribution and URL, stable fingerprint,
and retrieval time. Missing publication dates remain blank.

The summary lists every page checked, status, content hash, extraction counts,
any potential pagination links, CSV hash and completeness limitations. Site
markup changes can require updating the parser; do not equate a successful HTTP
response with complete access to Google review history.

## Privacy and source bundles

This directory is ignored by Git and excluded from deployment by `.replitignore`.
Do not manually add it to source ZIPs, demos, screenshots, public repositories or
videos. A ZIP tool does not automatically honor Git's exclusions: bundle only
tracked source files, for example with `git archive`, rather than zipping the
whole application directory. Downloads contain real review wording and remain
private, even though reviewer columns are omitted.

## Important data limits

Website-selected testimonials attributed to Google are not reviews independently
retrieved from Google. They do not establish the complete review history.
Positive selection bias makes them unsuitable for representative complaint rates.
Without real dates, they cannot support early warnings or weekly trends.
The upload preview reports missing and invalid dates before saving. Files with
no eligible reviews cannot replace an existing dataset. Saved CSVs retain all
original bytes, but undated records are excluded from analysis and trends.
Cancel upload leaves saved datasets unchanged; Download original CSV retains
even an all-undated file without importing it. Do not substitute retrieval time for
publication date or import this collection as a date-complete dashboard dataset.
Use the owner's authorized, dated export for a separate verified analysis.

## Checks and undo

The synthetic tests cover repeated carousel items, distinct wording, identical
wording from different reviewers, blank dates, attribution, identity exclusion
and external-domain rejection. They make no network requests.

No app code, labels, caches or action histories are changed by collection, so
there is no dashboard change to undo. Simply keep using the existing saved file.
To undo exclusion-file edits only, the originals and their SHA-256 manifest are
in `backups/website_collection_20261105T223458Z/`. Prefer removing just this
collection's exclusion entries if those files have later changes. Keep private
data excluded while retaining it; restoring exclusions must not publish it.
