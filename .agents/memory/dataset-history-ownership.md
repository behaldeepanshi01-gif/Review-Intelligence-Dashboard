---
name: Dataset history ownership
description: Conservative recovery of ambiguous filename-based action histories.
---

Treat matching CSV names, and even matching CSV bytes, as insufficient evidence
that two uploads represent the same dataset. Updates require an explicitly selected
stable dataset identity. Never automatically attach old filename-scoped actions,
including old `sample` actions, to either an upload or the built-in sample.

**Why:** Old filename scopes cannot distinguish unrelated restaurants or uploaded
samples from the built-in demo; guessing would attribute another dataset's actions
and saved baselines to the current reviews.

**How to apply:** Preserve old action records and baselines unchanged. Require a
manager to inspect and explicitly link a legacy history, exclusively to one
dataset. Keep the identity registry with the local review files and action log.

History-link corrections move the entire legacy association, not selected
records or actions subsequently created with a stable dataset identity.

**Why:** The user requires mistaken links to be correctable without moving newer
dataset-owned actions or rewriting historical baselines.

**How to apply:** Keep unlinking reversible through explicit recovery, require
confirmation for transfers, and reject stale ownership decisions rather than
overwriting another manager's link.
