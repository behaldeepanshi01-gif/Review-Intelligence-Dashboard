# Open the interactive dashboard

Use the workspace development host with `/dashboard/` appended, without `:8000`.
The root address `/` remains the animated demonstration, not the interactive app.

The API artifact's `Review Dashboard` service starts the existing Streamlit app.
Its managed workflow is `artifacts/api-server: Review Dashboard`.
Streamlit's base URL is `dashboard`, so static files and WebSockets share the
same routed prefix. The old standalone `Review Intelligence App` workflow was
removed to avoid duplicate listeners. No application data or analyzer code changed.

Verified through the public development host:
- `/dashboard/` returns Streamlit HTML.
- `/dashboard/_stcore/health` returns `ok`.
- `/dashboard/_stcore/stream` accepts a WebSocket connection.
- `/` still serves the separate demo.

Inside the dashboard, Export sits beside Reply inbox. Manager action reports
require individual account setup; see `MANAGER_ACTION_REPORT.md`.
The printable export is separate pending work, not added by this routing fix.

## Private dashboard access

The entire interactive dashboard now requires the same individual local manager
account as reports and restaurant calendars. Assign stable dataset IDs and exact
location names using `manage_managers.py`; the synthetic dataset also needs a
grant. Missing accounts or grants fail closed before data selectors or analysis.
Only assigned restaurants contribute to counts, date ranges, analysis, review
inspection, exports, saved actions and live summaries. Revocation or expiry
blocks the next interaction/live refresh; locking clears session drafts.
Previously viewed or downloaded information cannot be recalled.

### Synthetic account-switch browser regression

Run from the workspace root with Node, `uv`, and Playwright/Chromium available:

```sh
node review_intel_app/test_account_switch_browser.cjs
```

If Playwright or Chromium is installed outside the default search path, set
`PLAYWRIGHT_MODULE` to the Playwright module directory and `CHROMIUM_PATH` to
the browser executable. The runner fails explicitly if dependencies are missing;
it does not silently skip browser coverage.

This starts an isolated copy of the real Streamlit app on a free loopback port.
It generates two temporary accounts with disjoint dataset/location grants and
overlapping review and action IDs. In the same browser page it edits and approves
A's replies, retains an unsaved action editor, locks, and signs in as B.
Assertions cover inactive-tab text, widget values, dataset options, approval
counts, downloaded CSV rows, and B's own working action editor. It then revokes
B's grants and waits for the real 30-second fragments, with no click or reload:
the entire private page must disappear, including editors outside the fragments.
A fresh B login must show no assigned datasets.

Only Python source files are copied; all reviews, accounts, approvals, snapshots,
and action histories are generated in a temporary directory. No existing private
data is read or changed. The runner closes Chromium, terminates its Streamlit
process group, and removes the temporary directory on success, failure, SIGINT,
or SIGTERM, with a three-minute overall deadline. As with any process, SIGKILL
cannot run cleanup. Download retrieval reauthorization and conflicting action
drafts are separate tests, not part of this regression.

Managers may replace an assigned existing dataset only when they have access to
every location in both the current CSV and the replacement, including rejected
rows. This prevents a partial-location manager from deleting another location's
reviews. Previous snapshots, corrections and action histories are preserved.
Publication also checks that the authorized snapshot is still current: a
simultaneous replacement is rejected and must be reviewed again before saving.
Creating datasets and claiming/transferring unassigned filename-based history
are trusted local-owner operations, not permissions implied by a location grant.
The owner can use `dataset_store.DatasetStore` locally to register a new dataset
and inspect its stable ID before assigning it. Legacy history controls are not
exposed on the manager dashboard because those histories have no independent
authorization scope. Existing authorized linked histories remain usable.

## Plans for locations missing from a snapshot

Choose **Saved actions for absent locations** under **Dashboard view**, then a
**Saved-action location**. This separate view uses the selected stable dataset
identity and the signed-in manager's exact location grants, including authorized
linked legacy plans. It works even when none of the manager's assigned locations
has current reviews. Current-review location/date filters, charts, and exports
are not expanded with historical locations or synthetic reviews.

Saved plans, original evidence, baselines, and recorded edit history remain
available. Managers can update plan fields with the same stale-save and history
ownership checks used by the tracker. Missing-location plans show source-data
warnings, not zero-valued follow-up trends or operational improvements. Saved
calendars still determine their due-date status. Only explicit saves persist
changes; drafts remain private to the current session.

The public root animation is separate and remains synthetic. This is local
application authorization, not encryption against someone with filesystem access.

## Undo

Backups with SHA-256 hashes are under
`backups/dashboard_routing_20261106T175435Z/`.
Restore artifact routing only through the validated artifact configuration tool,
and restore the old workflow through the workflow manager. Do not run both
Streamlit services on port 8000. Undo removes the working `/dashboard/` route.
Do not restore uploads, labels, accounts or histories. Nothing was published.
