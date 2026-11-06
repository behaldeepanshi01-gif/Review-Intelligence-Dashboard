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

## Undo

Backups with SHA-256 hashes are under
`backups/dashboard_routing_20261106T175435Z/`.
Restore artifact routing only through the validated artifact configuration tool,
and restore the old workflow through the workflow manager. Do not run both
Streamlit services on port 8000. Undo removes the working `/dashboard/` route.
Do not restore uploads, labels, accounts or histories. Nothing was published.
