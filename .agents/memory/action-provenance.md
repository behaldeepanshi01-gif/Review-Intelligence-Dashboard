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
