---
name: Local action concurrency
description: Why action history remains local JSON and the boundary of its concurrency guarantees.
---

Keep existing local JSON action histories readable without a database migration.
Use conflict detection for open manager forms rather than silently accepting
last-writer-wins updates.

**Why:** Historical baselines and legacy fields must survive concurrency fixes
without changing ownership or rewriting past evidence. A manager submitting a
form has approved the version they saw, not another manager's intervening edit.

**How to apply:** Any future action writer must participate in the same locking
and snapshot checks. This design assumes processes share the same local
filesystem; scaling to independent hosts requires shared transactional storage,
not an assumption that local file locks coordinate those hosts.

Keep conflict-time form widget identity stable, and submit any draft-preservation
choice through the form rather than an outside button.

**Why:** Changing an input's disabled state reset submitted draft values in
Streamlit AppTest. Outside buttons also cannot collect edits still buffered by
the browser inside a form. A conflict comparison must show the manager's draft,
not silently substitute the old saved values.

**How to apply:** Disable saving rather than the editable inputs during a
conflict. Use form submit controls to capture reference drafts; a retained draft
is session-only reference material, never implicit permission to overwrite a
newer saved action.
