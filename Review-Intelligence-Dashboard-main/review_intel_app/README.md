# Review Intelligence

An AI review assistant for multi-location restaurant groups. It reads every guest review,
finds what guests praise and complain about at each location, warns owners when a problem
starts rising, tracks which staff guests praise by name, and drafts a reply for every review
that a manager approves before posting.

Built by Deepanshi Behal.

## What it does

| Tab | What owners get |
|---|---|
| Overview | Rating by location, monthly trend, complaint rate |
| What guests say | Heatmap of 12 themes (food, spice, consistency, service speed, portions, staff, ambiance, catering and more), top complaints, and the actual reviews behind each theme |
| Early warnings | Themes whose complaints jumped in the last 30 days vs the 90 days before |
| Staff shout-outs | Staff praised by name, per location |
| Reply inbox | Editable local reply templates, or optional API drafts. Edit, approve, copy. Nothing posts automatically |
| Export | Analyzed reviews CSV, alerts CSV, and a weekly owner summary ready to paste into email or WhatsApp |

## Quick start

```bash
python -m pip install -r requirements.txt
python serve_dashboard.py
```

It opens in your browser with 930 synthetic reviews across four sample locations.

### Restaurant action calendar

The sidebar's **Location calendars** lets managers select a location and explicitly
save an IANA **Restaurant timezone** (for example, `America/New_York` or
`Asia/Kolkata`). Unconfigured locations default to `America/New_York` for the
Falls Church demo. Settings belong to the stable dataset identity and exact
location name, not to a browser session or filename. Updating the same dataset
retains them; separate datasets and renamed locations have independent settings.
Calendar reads and edits require an individual local manager account, using the
same accounts as manager reports (see `MANAGER_ACTION_REPORT.md` and
`manage_managers.py`). The app owner grants access to stable dataset IDs and exact
location names; no filename matching, wildcard, or automatic ownership is used.
For dataset registration and legacy-history recovery, explicitly provision an
owner using `python manage_managers.py set OWNER_ID --permissions permissions.json --owner`.
The permissions file can be `{}` for an owner without restaurant dashboard access.
Enter the password privately at the prompts and type `OWNER` to confirm the
global maintenance capability. Existing accounts remain ordinary managers.
Running `set` without `--owner` removes owner capability and revokes previous
sessions, as does removing the account.

After signing in, owners can choose **Workspace → Owner dataset maintenance**.
Preview a CSV and confirm registration of a separate dataset; no existing
snapshot is replaced and no filename history is attached automatically.
Copy the new stable dataset ID into exact-location permissions when granting
restaurant dashboard access. Owner capability alone does not grant those views.
In maintenance, select a dataset and inspect the sidebar's older-history
controls. Claims, unlinks, and transfers require deliberate confirmation and
reject stale source/destination revisions. They move only the association:
original snapshots, action records, and saved baselines remain unchanged.
Ordinary manager sessions cannot use these maintenance operations even when
they have every location grant. Trusted offline Python maintenance remains a
local-operator interface; never expose its session-omitting calls to web users.

Only assigned locations appear in calendar-dependent dashboard views. Sessions
expire after 30 minutes; account removal or permission/password replacement
revokes access. Storage methods recheck permission on every read and write,
including rename operations, which require grants for both old and new names.
Unsigned access is denied even when no accounts have been configured.
This is not a complete dashboard privacy boundary: upload, dataset management,
and other data paths still need their separate access-control work before shared
external use.
Settings persist in `data/location_settings.sqlite` on the shared local filesystem;
independent deployment hosts do not share this file. Back it up with the action log.
Stale manager edits are rejected; use **Reload saved timezone** before retrying.
Invalid names are rejected without changing the saved calendar.
Action defaults, creation dates, overdue filters, warnings, and weekly summaries
use each action's location calendar, including mixed-location summaries, independently
of the hosting server's timezone. Each interaction or refresh reloads saved settings.
An unfinished action becomes overdue only on the day after its due date.
Daylight-saving changes are handled by timezone rules, not fixed UTC offsets.
Refresh or interact with the app after midnight to update the displayed day.
Existing saved dates and baselines are not converted or rewritten.

To regenerate the sample data:

```bash
python generate_data.py
```

## Local Review Analyzer

The default analyzer uses restaurant phrases, bounded word matching, and nearby
sentiment cues. It is a rule-based tool, not a newly trained language model.
It uses no API, network requests, model downloads, or additional packages.
The Ollama controls have been removed. Existing Ollama cache files are not changed.

- Explicit praise and complaints can both be retained, including for the same theme.
  Star ratings do not erase clear criticism.
- Open **What guests say**, then **Why these tags?**, to see matched terms and the
  original passage that supports a tag.
- The **Reviews needing manager review** section lets you select unclear results.
  Neutral mentions and tentative statements are not forced into praise or complaints.
- Local reply drafts are templates. Check them before approval. Nothing posts automatically.
- The analyzer can miss sarcasm, unusual phrasing, implicit complaints, and context.
  A large review-needed count means manual checking is needed, not that accuracy is high.
- No confidence percentages or accuracy claims are shown without a labeled evaluation.

**Claude API** remains an optional paid mode and runs only when requested. Local
analysis never calls it. Local rule explanations are not presented as evidence for
Claude-produced tags.

### Manager decisions

In **What guests say → Approve or correct review tags**, select any review and
save its complete praise and complaint theme sets. Both can contain the same
theme for mixed feedback; both can be empty to approve no supported theme.
Saving unchanged tags approves the rule result. The original rule tags, review
reasons and evidence remain visible separately from the effective manager tags.

Decisions are saved locally in `data/manager_corrections.sqlite`, not in uploads,
rule caches or action records. The store contains hashed file/review identities,
theme keys, the rule version and save time, not review text or guest names.
Keep this file private; it is excluded from Git. Reopening the same saved file
restores decisions only for reviews with the same ID and all loaded source
fields unchanged. A different file path or changed review will not inherit them.
Reviews without explicit IDs use generated IDs; reordering such a CSV can require
manager review again. A rules-version change requires renewed manager approval.

Saving or undoing a decision recalculates current theme counts, warnings, staff
lists, reply templates and exports. It does not rewrite saved action baselines or
previously approved reply text. Check those manually before using them again.

Reply approvals are saved separately in
`data/manager_corrections_reply_approvals.sqlite`. Approved wording is preserved
verbatim with the exact source review, dataset identity, positive/negative tag
snapshot, analysis context, approving manager, and approval time. Reopening the
dashboard restores it; changing effective tags brings the unchanged wording back
into the queue until a manager explicitly chooses **Recheck and approve reply**.
Saving or undoing a tag decision never approves wording. If the original tags are
restored, the original reply approval matches again.

Approvals are shared restaurant work: managers with current access to the same
dataset and restaurant can see them. They use the existing local manager accounts,
not another login. Unsaved wording edits remain session-only. A changed source
review or another dataset cannot inherit an approval, even with the same review
ID and tags; restoring the exact original source can restore its own approval.
Keep this private SQLite file with the other local history when backing up or
moving the dashboard. It is not included in Git or public deployment assets.
Storage errors are shown explicitly rather than reporting an unsaved approval as
successful.
**Undo manager decision** restores that review's current rule result without
deleting any reviews, caches, or actions. Corrections apply only to the local
analyzer, never to optional Claude results.

An open tag form is tied to the saved revision it displayed. If another session
saves, renews, or removes that decision, stale saves and undo attempts are blocked.
The conflict view shows the latest saved tags and keeps your unsaved selections.
Choose **Review latest and keep my draft** to acknowledge the displayed revision
without saving, or **Discard my draft and load latest tags** to replace your
selections. You must then save explicitly; another intervening edit will conflict
again. Drafts are private to the signed-in session, not durable recovery copies.

Programmatic callers of `save_correction` and `undo_correction` must pass the
displayed `expected_revision` (`saved_at`, or `None` for no decision). The check
and write share one SQLite transaction; do not reload the revision immediately
before saving an already-open draft, which would bypass stale-edit protection.

```bash
python -m unittest -v test_correction_concurrency test_manager_corrections
```

### Rule cache and saved baselines

The local rules version is part of the Streamlit cache key. When editing the rules,
bump `RULES_VERSION` in `local_analyzer.py`. Existing action records are preserved.
Old saved baselines may use earlier rules: do not interpret changes in tagging as
proof of restaurant improvements.

### Checks and undo

```bash
python -m unittest -v test_local_analyzer test_action_tracker test_local_app
python benchmark_local.py data/sample_reviews.csv
```

The app checks use Streamlit's in-process test utility, not a browser. Benchmark
output contains only counts and timing, never guest text or names. Timing on a
Replit machine does not guarantee the same speed on a Windows laptop.

Backups made before the local-analyzer update are in `backups/before_local_analyzer/`.
Restore that folder's `app.py`, `engine.py`, and `README.md` to undo this change.
The new helper can remain unused. The backup app exposes the old Ollama option, so
leave it on Offline if you restore. Do not delete your uploads, caches, or action log.

## Using real reviews

Upload a CSV from the sidebar with these columns:

| Column | Required | Example |
|---|---|---|
| location | yes | Upscale Dining Room |
| date | yes | 2026-10-12 |
| rating | yes | 4 |
| text | yes | The butter chicken was great but service was slow. |
| reviewer | no | Sam K. |
| review_id | no | G-0001 |

Uploaded files are saved in `data/uploads/`, so after a refresh or restart you can pick them
under "Saved file" instead of uploading again.

### Dataset identity and action history

Every saved dataset has a persistent identity, shown in the sidebar. Filenames
are labels, not identities. After choosing a CSV, choose **Create a separate
dataset** (the default) or **Update an existing dataset**, select its target, and
press **Save CSV**. A newer snapshot can have a different filename and still keep
the selected dataset's actions and original alert baselines. Updates replace the
current review view; include all reviews needed for follow-up in the snapshot.
Earlier CSV snapshots remain on disk, and an unreadable CSV is not saved.

Two separate uploads named `reviews.csv` have separate identities, even if their
contents match. An uploaded `sample.csv` is also separate from the built-in sample,
which cannot be replaced by an upload.

Existing filename-based action records are not deleted, rewritten, or
automatically assigned. Open **Recover older action history**, inspect the saved
actions, and explicitly confirm they belong to the currently selected dataset
before linking them. A legacy history can be linked to only one dataset, including
the built-in sample. Old basename collisions cannot be disambiguated from the
old log alone; do not link a mixed history without checking it.

To fix a mistaken link, select its current dataset and open **Correct linked
action history** in the sidebar. Inspect the full legacy actions and dataset
identities, choose **Unlink only** or **Reassign to another dataset**, and check
the confirmation before saving. Cancel makes no changes. Reassignment requires
a destination without an existing history link; it never replaces another
history. Unlinked histories remain available under **Recover older action
history**. Original action records, baselines, evidence, dates, and statuses are
not rewritten, and actions created with a dataset ID stay with that dataset.
Concurrent link changes reject stale confirmations instead of overwriting
another manager's choice. These guarantees require a shared local registry.

Keep `data/uploads/datasets.sqlite`, the upload files and snapshots, and
`data/action_log.json` together when backing up or moving local state. The registry
stores the stable identities and explicit legacy-history links.

**History-link corrections** is a read-only sidebar log, separate from action-edit
history. New claims, unlinks, and transfers made with a valid local manager session
record that manager ID in **Changed by**, alongside the operation, UTC time, and
source/destination dataset IDs. Earlier events remain **Unknown**; authors are
never inferred from action owners or dataset grants. Trusted local-owner
maintenance without a manager session is also **Unknown**. Supplying an expired
or revoked session rejects the change without adding an event. Recovery controls
remain owner-only; this log does not grant recovery or reassignment permission.

Synthetic correction checks (including manager controls, cancellation, recovery,
restart, and concurrent claims) run from the project root with:
`python -m unittest discover -s review_intel_app -p 'test_dataset_history.py' -v`.

### Concurrent manager action saves

Action saves lock `data/action_log.json.lock`, read the latest log, and atomically
replace the JSON only after applying the requested create or edit. Different
actions and datasets are preserved, including legacy fields and saved baselines.
Two managers cannot create active plans for the same dataset, location and theme.
If another manager edits the same action while your form is open, your stale save
is rejected. **Reload latest action** discards the draft and opens the saved
version; review it before editing again.

The JSON format is unchanged; no migration is needed. Keep the stable lock file
in place while the app is running. This protects processes sharing the same local
filesystem, not separate machines or independent deployment filesystems.
Bulk replacement through `save_actions` requires an explicit `expected_actions`
snapshot for an existing log; normal app saves use per-action operations.

Synthetic concurrency checks use temporary logs and separate threads/processes:
`python -m unittest discover -s review_intel_app -p 'test_action_concurrency.py' -v`
from the project root.

Common alternatives are renamed automatically (`stars` to rating, `review` to text,
`name` to reviewer). The Yelp filter script output works too after adding a `location` column.

**Where to get real reviews, legitimately:**
- With the owner's permission, their Google Business Profile shows every review and lets them reply.
- Without access, copy recent public reviews by hand into a spreadsheet. Don't use scraping tools,
  which break Google's and Yelp's terms.

## Privacy and honesty rules

- The sample data is fully synthetic. Names, staff and text are invented.
- Keep real guest names and private sales data out of anything public, including GitHub.
- Replies are drafts. A person approves every reply before it is posted.

## Action-tracking verification

From this directory, after installing the requirements, run:

```bash
python -m unittest discover -p 'test_*.py' -v
```

No special test ordering is required. Spawn-based action-save and history-transfer
checks use `process_test_support.isolated_process_test` to run the selected test
in a fresh interpreter before launching real concurrent workers. This prevents
Streamlit AppTest's temporary main module from becoming a worker entry point.
Child failures and timeouts fail the parent test with captured output. Use the
same decorator for new tests that launch spawned workers alongside AppTest.

The checks load the included synthetic CSV through the existing review loader and
confirm its columns and source file remain unchanged. They create an action from a
generated alert, update and reload it in an isolated temporary log, and confirm that
another dataset's action is unchanged. Follow-up waits at four newer reviews and
becomes available at five, using additional synthetic rows loaded through the same
CSV loader. No test writes to the application's real upload folder or action log.

### Supplied Yelp CSV verification

The source ZIP contained only synthetic data. A subsequently supplied local Yelp
CSV was verified separately without checking its contents into Git or changing it:

- All 385 rows loaded through `engine.load_reviews`, with the original six columns
  unchanged: `location`, `date`, `rating`, `text`, `reviewer`, `review_id`.
- The normal 30- and 60-day windows produced no alerts. The supported 90-day window
  produced one Food & flavor alert, which was used for the action lifecycle check.
- An action was created, saved, updated to In progress, reloaded, and marked Done
  in a temporary log. Its original dataset tag and alert baseline remained intact.
  Another dataset's action was unchanged throughout.
- The original file had no reviews newer than the action's start date. Five
  explicitly synthetic rows were added only in memory and loaded through the same
  CSV loader. Four newer rows kept follow-up waiting; five enabled it, with one
  negative theme mention out of five reviews (20%).
- The original upload remained byte-for-byte unchanged. No real app action log or
  upload folder was modified, and only aggregate results were printed.

The automated checks above continue using synthetic fixtures so the private Yelp
CSV need not be distributed with the code. No Google or Yelp scraping is needed.
Do not include guest names or real review text in public results or demo materials.

## Files

```
app.py             Streamlit dashboard
engine.py          Local/API analysis, alerts, staff leaderboard, reply templates
local_analyzer.py  Explainable local phrase rules and evidence
benchmark_local.py Counts and timing only, no private review output
generate_data.py   Builds the synthetic dataset
data/              Sample data and Claude cache
```

## Keeping a calendar after a restaurant rename

Upload the new reviews using **Update an existing dataset**, selecting the same
dataset identity. In **Location calendars → Restaurant renamed?**, select the
previous saved calendar and its new name, review the timezone, confirm that both
names refer to the same restaurant, and click **Link renamed restaurant calendar**.
The previous name must be absent from the current reviews and the new name present.
Separate datasets are never linked, even if their filenames or restaurant names match.

The move preserves the saved timezone across refreshes and restarts. It does not
rename reviews, action plans, baselines, or due dates. An existing destination
calendar cannot be overwritten, and a previously renamed name remains reserved
to prevent stale editors from recreating its calendar. If another manager changes
the source calendar or replaces the dataset snapshot, reload and confirm again.
Calendar editing uses the dashboard's existing local-manager access model.

## Roadmap

1. Connect directly to Google Business Profile so new reviews flow in automatically
2. Weekly summary sent to owners by email or WhatsApp
3. Link review themes to POS data (for example, do "small portion" complaints line up with a
   recipe or supplier change?)
