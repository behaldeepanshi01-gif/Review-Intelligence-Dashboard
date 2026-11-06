---
name: Restaurant action calendar
description: Scope of the restaurant timezone and why it defaults to Eastern time.
---

Use America/New_York as the initial restaurant timezone because the demo targets
Falls Church, Virginia. Calendar ownership is the stable dataset identity plus
exact location name; unrelated datasets must not share settings merely because
restaurant names match. Managers with access to the local app share edit authority.

**Why:** There is no global restaurant identity or authenticated administrator
role. Dataset-scoped ownership avoids silently connecting unrelated uploads,
while keeping manager sessions consistent.

**How to apply:** Keep existing due dates as calendar dates when settings change.
Do not infer a restaurant timezone from a server or browser timezone. A future
cross-dataset restaurant directory needs explicit linking rather than name matching.

Calendar rename confirmations move only calendar ownership, not action histories
or review evidence. Previously renamed names remain reserved rather than being
silently reused.

**Why:** Reusing an old name can let a stale manager editor recreate a detached
calendar; moving action evidence would imply historical continuity the manager
has not separately reviewed.

**How to apply:** Keep rename recovery scoped to one explicitly selected dataset.
Treat correcting mistaken links or reusing retired names as a separate, confirmed
ownership operation rather than deleting the safeguards.
