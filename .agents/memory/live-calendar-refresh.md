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

Permission loss during a timed fragment must invalidate the whole private page,
not merely stop rendering that fragment.

**Why:** Streamlit preserves content outside the refreshing fragment. A denial
message inside it can coexist with old reviews, download controls, and retained
action editors even after server-side draft state has been cleared.

**How to apply:** Route invalidated sessions back through the full-page sign-in
gate. Verify revocation without browser clicks or reloads, including private
widgets outside the timed section; a full-rerun AppTest denial cannot prove this.

Clearing server-side widget state alone does not guarantee a visible draft reset.

**Why:** A real Streamlit browser can restore the old input when the widget
identity stays unchanged, even though AppTest shows the expected default.

**How to apply:** Reset unchanged widget identities explicitly to their defaults
in a callback, or change their identity. Verify destructive draft resets in a
real browser; server-state assertions alone cannot prove the displayed reset.

Warn near sign-in expiry even when server state does not prove a draft is dirty.

**Why:** Unsaved action text may still be focused in the browser, and retained
widget values can be defaults rather than edits. Conditioning the warning on
server-side dirty detection can miss the draft most at risk.

**How to apply:** Keep expiry notices independent of editor rendering and remind
managers to save explicitly; notices and saves must never renew authentication.
