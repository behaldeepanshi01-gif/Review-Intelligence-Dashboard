"""Browser-side age warnings: a stopped server cannot render a stale warning."""
from datetime import datetime, timezone
from html import escape

import streamlit as st


def freshness_html(label: str, updated_at: datetime) -> str:
    stamp = updated_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"""<!doctype html>
<html><body>
<p><strong>{escape(label)} last updated: {stamp}</strong></p>
<p id="freshness" role="status" aria-live="polite">
Updates expected every 30 seconds. Checking freshness…</p>
<script>
const receivedAt = Date.now();
const started = performance.now();
let awaitingUpdate = false;
function render() {{
  // Wall time includes device sleep; monotonic time also tolerates clock rollback.
  const age = Math.max(Date.now() - receivedAt, performance.now() - started);
  const stale = age >= 75000 || awaitingUpdate || !navigator.onLine;
  const status = document.getElementById("freshness");
  status.textContent = stale
    ? "Updates may be stale — do not rely on these overdue counts yet. "
      + "Check your connection and keep this tab open while it reconnects. "
      + "Wait for a new last-updated time (normally within 30 seconds). "
      + "Copy unsaved text before reloading or signing in again."
    : "Updated recently · checks every 30 seconds while connected. "
      + "If updates stop for 75 seconds, this view is marked stale.";
}}
window.addEventListener("offline", () => {{ awaitingUpdate = true; render(); }});
window.addEventListener("online", render);
document.addEventListener("visibilitychange", render);
window.addEventListener("pageshow", render);
setInterval(render, 1000);
render();
</script>
</body></html>"""


def show_live_freshness(label: str) -> None:
    """Call only after the associated view has successfully rendered."""
    st.iframe(freshness_html(label, datetime.now(timezone.utc)),
              height="content", alt=f"{label} refresh status")
