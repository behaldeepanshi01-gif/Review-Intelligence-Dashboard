---
name: Live calendar refresh safety
description: Why timed status views must not rerender action editors, and how to verify browser-only drafts.
---

Keep action editors outside timed rendering, even when a live filter changes which
saved actions qualify for display.

**Why:** Streamlit forms buffer unsubmitted input in the browser. A full app rerun
is not equivalent to a fragment timer event; AppTest's full rerun cannot establish
that browser-only drafts survive. The midnight requirement was verified using an
isolated clock-controlled app and a browser in the same environment.

**How to apply:** Test automatic rollover without interacting with the page after
advancing the clock. Check both the overdue views and unsent inputs. If a remote
test browser cannot reach a local harness, run browser automation beside the
harness rather than treating connection refusal as an application error.

Freshness warnings must run in the browser and measure each view's successful
render, not an independent server heartbeat.

**Why:** A disconnected server cannot send its own stale warning, and a healthy
heartbeat does not establish that a particular overdue view finished updating.
Browser wall time must supplement monotonic elapsed time to account for sleep.

**How to apply:** Keep the watchdog independent of draft widgets; only a newly
rendered view should clear its warning. Describe missed updates as potentially
stale rather than claiming to know the Streamlit socket's connection state.
