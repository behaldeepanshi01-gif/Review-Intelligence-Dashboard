---
name: Action comparison provenance
description: Scope and interpretation of manager-decision fingerprints for action baselines.
---

Treat provenance as a conservative, location-wide comparability check, not proof
that the specific action theme's counts changed. Use all applicable decisions in
the dataset's location, independent of dashboard date filters.

**Why:** Rule and correction changes can make historical comparisons misleading.
New uncorrected follow-up reviews and filter changes should not create warnings,
while adding, changing, or undoing a decision should. Save timestamps do not
change the interpretation; restoring identical decisions restores the match.

**How to apply:** Keep the saved baseline immutable. Describe mismatches as
potential non-comparability, and describe missing/non-local provenance as unknown,
never as unchanged. Exclude other datasets and locations from the fingerprint.

Check source data separately from tagging, using the location's analysis inputs
through the saved alert date. Allow newer follow-up reviews, but warn on edits,
removals, duplicate-count changes, or backfilled reviews in that earlier cohort.
Ignore CSV row ordering, generated review IDs, guest names, and snapshot paths.

**Why:** A tagging match does not prove that the underlying baseline reviews still
match. CSV-generated IDs change with row order, and explicit dataset updates use
new paths even when the earlier reviews remain identical.

**How to apply:** Preserve historical baselines without backfilling old source
snapshots. Treat missing source history as unknown. Compare normalized analysis
content with duplicate multiplicity, not a whole-file checksum or generated IDs.
