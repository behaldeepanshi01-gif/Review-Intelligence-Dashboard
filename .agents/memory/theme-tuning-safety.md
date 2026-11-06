---
name: Theme tuning safeguards
description: Why narrowly scoped theme updates require exact per-review comparisons.
---

For a price-only update, preserve the interpretation of all other themes and
compare their praise/complaint sets for every review, not only aggregate scores.
Do not expand the shared vocabulary as a shortcut without checking cross-theme
effects.

**Why:** Nearby sentiment assignment means adding a theme hit can take a cue
away from an existing theme. Aggregate totals can stay identical while different
reviews change. The user explicitly authorized price-only tuning and asked
that improvements and regressions not be hidden.

**How to apply:** Freeze the actual app predictions before tuning, compare exact
non-target sets afterward, and disclose any differences. Isolating the price
interpretation while preserving the existing non-price matching pass is an
intentional conservative tradeoff, not a reason to silently retune other themes.

Only the narrow monetary-waste wording gap was authorized before the blind
evaluation freeze; broader indirect-price expansion remains deferred.

**Why:** The user wants a stable actual-app analyzer before independent human
labeling, not continued tuning on the evaluation batch.

**How to apply:** Freeze implementation hashes and hidden predictions without
showing unused-review predictions to the labeler. Only the user or restaurant
manager supplies and approves blind labels; never substitute AI ground truth.
