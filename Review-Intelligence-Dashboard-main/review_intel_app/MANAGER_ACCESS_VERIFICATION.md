# Individual manager report access verification

## Scope

Individual local accounts protect manager report preview and download creation.
The owner approved report-only access control, not full dashboard authentication.
No real accounts were seeded. The shared password no longer unlocks reports.
No analyzer, labels, uploads, decisions, action histories or calendar settings changed.

## Checks

From `review_intel_app`:

1. `python -B -m unittest test_manager_identity test_action_report test_action_tracker test_action_timezone -v`
   ran 32 tests: 31 passed, 1 error. The new AppTest timed out at its default
   3-second startup limit; no authorization assertion failed.
2. Increased that synthetic AppTest timeout to 30 seconds and ran
   `python -B -m unittest test_manager_identity.IdentityTests.test_ui_denial_and_live_revocation -v`:
   1 passed.
3. Closed SQLite connections explicitly, then ran
   `python -B -m unittest test_manager_identity test_action_report -v`:
   10 passed, 0 failures/errors.

All 32 distinct selected cases have passing results; this is not a claim that
the entire repository suite was run. Tests use temporary databases and synthetic
reviews/actions. Streamlit AppTest exercises widgets without browser automation.

Covered: wrong/unknown login, exact dataset and location matching, two separate
manager identities, mixed-selection denial, no legacy-filename authorization,
session expiry, password/grant replacement, account deletion, missing/corrupt
storage, denial before preview/download rendering, live revocation on rerun,
privacy acknowledgment, empty actions, empty date range, logout, report redaction,
unchanged report comparisons and action/calendar regression checks.

The Review Intelligence App workflow restarted successfully on port 8000.
No packages, paid APIs, Ollama, deployment or browser automation were used.

## Setup and remaining limitations

See `MANAGER_ACTION_REPORT.md` for owner-only account setup with hidden password
prompts. Reports intentionally remain locked until accounts are configured.
The existing dashboard and other exports are not protected by this gate.
Already downloaded content cannot be recalled. Issued Streamlit media links
are not individually authenticated download endpoints. Local rate limits and
SQLite account storage assume one trusted app host, not distributed deployment.

## Backups and undo

`backups/manager_identity_20261106T171241Z/manifest.json` records SHA-256 hashes
of the original report helpers, report test, documentation and deployment-ignore
file. All backup hashes verified. Follow the document's narrow restore steps,
preserving later work and all private data. Restoring the previous gate restores
weaker shared-password authorization.
