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
The user initially chose “Keep the evaluation freeze.” On 2026-11-10,
the user explicitly chose “Authorize separate rule cycle” for price questions,
rhetorical wording and reported/quoted opinions, using invented cases only.
This supersedes the freeze for that separate cycle, not for held-out evaluation.
Punctuation-separated negation and hedges remain outside that authorization.

**Why:** The user wants a stable actual-app analyzer before independent human
labeling, not continued tuning on the evaluation batch.

**How to apply:** Freeze implementation hashes and hidden predictions without
showing unused-review predictions to the labeler. Only the user or restaurant
manager supplies and approves blind labels; never substitute AI ground truth.
Keep synthetic diagnostics and separately authorized fixes separate from the
old evaluation. Never reuse old frozen predictions as evidence for new rules.

Approval of a file with AI-draft provenance does not establish independent
human-only reference labels, even if the user confirms personal labeling blind
to analyzer predictions. Preserve both statements rather than removing the
draft notes or silently claiming independence.

**Why:** Blindness to the evaluated analyzer and independence from AI-assisted
labeling are different properties.

**How to apply:** Record explicit batch-specific chat approval separately from
blank CSV checkboxes; report provenance limitations and coverage gaps with any
scores. Never convert an AI-draft evaluation into an independent accuracy claim.

On 2026-11-10 the user approved conditional preparation under the human-only
protocol in `review_intel_app/INDEPENDENT_LABELING_PROTOCOL.md`, not scoring or
rule changes. Missing original private evaluation and prior-use records are a
stop condition: recover and verify them before certifying eligibility or
preparing a new batch. Do not reconstruct the completed evaluation.

**Why:** The user approved a protocol that separates source availability,
human-only independence, and scoring authorization; approval is not evidence
that any of those prerequisites have already been satisfied.

**How to apply:** Keep any candidate counts provisional until exposure history
is verified. Use blank, prediction-blind human labeling without AI screening;
request separate scoring permission only after reporting human-labeled support.
