---
name: Restaurant action calendar
description: Scope of the restaurant timezone and why it defaults to Eastern time.
---

Use America/New_York as the initial restaurant timezone because the demo targets
Falls Church, Virginia. Calendar ownership is the stable dataset identity plus
exact location name; unrelated datasets must not share settings merely because
restaurant names match. Calendar access uses the individual local manager accounts
and exact dataset/location assignments, including both names for rename operations.

**Why:** There is no global restaurant identity. Dataset-scoped ownership avoids silently connecting unrelated uploads,
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

A confirmed reversal may restore this calendar's own previous name even when
that name is absent from the current review upload. Moving to an unrelated new
name still requires it to appear in the selected dataset.

**Why:** Undoing a mistaken calendar link must not require replacing review
evidence first. This is calendar ownership recovery, not proof that two review
histories belong together.

**How to apply:** Keep the restored name's calendar generation newer than all
earlier editors, reserve the name it moved from, and do not move action history.
