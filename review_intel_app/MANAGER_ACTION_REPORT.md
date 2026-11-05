# Manager action report

## Where to find it

1. Select the saved dataset and locations in the sidebar.
2. Open **Export**, then **Manager action report**.
3. Unlock using the manager passphrase, then check the preview for private guest details.
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
- Report preview and download require the shared `MANAGER_REPORT_PASSWORD`
  passphrase configured in Secrets (at least 16 characters). There is no default.
  Only share it with authorized managers. Access expires after 30 minutes and
  password rotation invalidates prior grants. Use **Lock manager report** to log out.
  This protects this report only, not the existing dashboard or Action tracker.
  It is not per-user or per-location authorization. Downloaded copies must stay private.
- When the date range has no reviews, the report panel remains below the warning.
- Trends are not proof that an action caused a change.

## Verification

Run from the workspace:

```sh
cd review_intel_app
python -B -m unittest test_action_report test_action_tracker test_action_timezone -v
```

The UI test uses Streamlit AppTest in a temporary copy with synthetic reviews
and mocked actions; it does not drive a browser or change real action logs.

## Undo this update

The pre-update entry point and its SHA-256 manifest are in
`backups/manager_report_20261105T215814174424Z/`.
If no later changes have been made to `app.py`, restore that backed-up `app.py`
and restart Streamlit. Otherwise reverse only the `action_report` import and the
manager report block at the beginning of the Export tab.
The added report helper and tests may remain unused.
Do not restore or delete datasets, corrections, action logs, or history registries.
This workspace change does not update a separate laptop copy or published app.
