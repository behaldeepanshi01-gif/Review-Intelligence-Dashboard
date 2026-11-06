# Manager action report

## Where to find it

1. Select the saved dataset and locations in the sidebar.
2. Open **Export**, then **Manager action report**.
3. Sign in using your individual manager ID and password, then check the preview for private guest details.
4. Tick the privacy-check box and choose **Download manager action report (TXT)**.

The download is disabled when there are no matching actions. Save an action in
Early warnings first, or select a file/location with saved actions.

## Contents and limits

- Only actions belonging to the selected dataset, or its explicitly linked legacy
  history, and selected locations are included.
- Active and completed actions are in separate sections. The report includes
  action, owner, status, start date, due date and overdue status.
- Dashboard date and Action tracker status filters do not limit the export.
- Follow-up uses the full current dataset, counts reviews strictly after the
  action start date, and requires at least five newer reviews.
- Comparisons are withheld if rules/manager-decision provenance changed or is
  unknown. Historical baselines are not rewritten.
- Review identity fields, raw review records and replies are not exported.
  Known reviewer names and copied passages in manager fields are redacted.
  Redaction cannot recognize every partial quotation or unknown person's name.
  Managers must inspect the preview before downloading or sharing it.
- Report preview and download require an individual manager account with explicit
  grants for the current dataset ID and EVERY selected location. Mixed allowed and
  denied selections are refused entirely. Filenames and legacy IDs do not grant access.
  The old shared password is no longer accepted. There are no default accounts.
  Access expires after 30 minutes. Password/grant replacement and account removal
  revoke sessions on the next check. Use **Lock manager report** to log out.
  The same account assignments now protect calendar reads, timezone edits, and
  calendar renames. Calendar-dependent views require sign-in first. This is not
  complete access control for dataset management, ordinary exports, or all Action
  tracker operations. Do not share the full app with untrusted users.
  Downloaded files cannot be revoked; previously rendered content cannot be recalled.
  Streamlit download links already issued are not a separately authenticated API.
  Downloaded copies must stay private.
- When the date range has no reviews, the report panel remains below the warning.
- Trends are not proof that an action caused a change.

## Verification

Run from the workspace:

```sh
cd review_intel_app
python -B -m unittest test_manager_identity test_action_report test_action_tracker test_action_timezone -v
```

The UI test uses Streamlit AppTest in a temporary copy with synthetic reviews
and mocked actions; it does not drive a browser or change real action logs.

## Undo this update

The pre-update entry point and its SHA-256 manifest are in
`backups/manager_report_20261105T215814174424Z/`.
If no later changes have been made to `app.py`, restore that backed-up `app.py`
and restart Streamlit. Otherwise reverse only the `manager_report_ui` import,
the manager report block at the beginning of the Export tab, and the manager
report call and action-loading block in the empty-date-filter branch.
The added report helper and tests may remain unused.
Do not restore or delete datasets, corrections, action logs, or history registries.
This workspace change does not update a separate laptop copy or published app.

## Individual account setup (app owner only)

This is local, single-instance access control, not a hosted identity service.
No package installation or paid API is needed. Shell/project editors are trusted
administrators and can change all grants. Do not give managers project edit access.

1. Read **Dataset identity** in the sidebar and the exact restaurant names.
2. Create `data/manager_permissions_alice.json` privately, for example:
   `{"EXACT-DATASET-ID": ["EXACT RESTAURANT NAME"]}`. No wildcard permissions.
3. In a terminal in `review_intel_app`, run:
   `python manage_managers.py set alice --permissions data/manager_permissions_alice.json`
4. Enter and confirm a unique password (16 or more characters) at the hidden prompts.
   Never put passwords in chat, a command argument, or the permissions file.
5. Give that manager their ID/password privately. Open Export to sign in.

Repeat with a different ID for each manager. Running `set` again replaces ALL
grants and the password for that ID and invalidates its sessions. For immediate
removal run `python manage_managers.py remove alice`. To temporarily revoke all
permissions, set the account with an empty permissions object `{}`.

Account hashes and exact grants are stored in `data/manager_accounts.sqlite`,
excluded from Git and deployment along with `data/manager_permissions*.json`.
Protect backups of this database as credentials. Do not copy development accounts
into public demo assets. No real manager accounts were created by this update.
Login throttling is process-local (10 attempts/minute across users), not distributed
protection against a public attacker.

`manager_identity.current_account(session)` and `permits(session, dataset_id, locations)`
are the shared identity/authorization interface for the timezone-authorization work.
Do not create a second identity store. This change does not grant timezone editing.

### Undo individual accounts safely

Backups: `backups/manager_identity_20261106T171241Z/` with SHA-256 manifest.
Restoring `manager_report_access.py`, `manager_report_ui.py`, `test_action_report.py`
and this document reverts this change; reconcile later edits before restoring.
Restart Streamlit to discard sessions. This restores the weaker shared-password
policy, so do not undo in a shared environment without reviewing that consequence.
Leave uploads, corrections, histories and the private account database untouched.
