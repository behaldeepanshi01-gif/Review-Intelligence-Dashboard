# Private action-cohort tagging effects

Open **Action tracker → Manager decisions since this action was captured** while
signed in with access to the exact dataset and restaurant.

New locally analyzed actions capture enough private evidence to compare negative
mentions under approvals at capture and approvals now, on two fixed cohorts:

- **Saved alert cohort:** the exact reviews used by the alert's recent window,
  including the dashboard's date selection when the action was created.
- **Current follow-up cohort:** current restaurant reviews strictly after the
  action's current start date, independently of dashboard date filters.

The table shows reviews, negative mentions before/now, added mentions, removed
mentions, and net change. Equal totals can hide offsetting changes, so added and
removed mentions are shown separately. A review may belong to both cohorts.
The follow-up cohort table is a tagging diagnostic even before five newer reviews
exist or an action is marked in progress; it does not replace the normal
follow-up eligibility check.

## Capture contract

`baseline_action_tags` version 1 is an allowlisted, detached JSON capture:

- Exact dataset, location, action theme, alert cutoff, and local rules version.
- For every source review at that location: an opaque correction-key hash,
  calendar date, duplicate multiplicity, saved-alert membership, and four boolean
  action-theme flags (rule positive/negative, effective positive/negative).
- No text, guest names, source paths, review IDs, or full analyzer output.

The capture uses the same source identity as manager decisions. It records all
location reviews, not just negative mentions: a previously untagged review can
gain a complaint tag later. The capture is refused unless alert membership
reproduces the saved negative mention count. It never repairs the saved baseline.
The existing complete, versioned location-wide approval snapshot establishes
which applicable decisions existed at capture.

## Interpretation and unknown cases

The calculation is supported only under the same local rules version, with
complete decision snapshots and consistent rule/effective evidence. Adding an
approval compares against rule fallback; removing one restores rule fallback.
For a genuinely new follow-up source identity absent from the complete saved
approval snapshot, “before” means local-rule tags without a manager approval.
This is a counterfactual under the two approval states, not a claim that this
new review existed or was counted when the action was created.

Missing/malformed capture, changed rules, mismatching dataset, changed rule
outputs, inconsistent decision evidence, or missing/changed-multiplicity saved
alert members yield **unknown**, not zero effects. Exact source identity changes
can make the comparison unavailable; reviews are not paired by similarity or
external IDs. Legacy actions are never backfilled, even if decision fingerprints
match. Editing start dates changes the current follow-up cohort, never the saved
alert cohort or numeric baseline.

These counts isolate tagging effects; they do **not** prove operational outcomes,
that the action worked, or why source data changed. Existing provenance and
source-comparability warnings remain conservative and separate. The location-wide
approval breakdown still describes approval records, not cohort effects by
itself. Private captures and their references are not added to ordinary exports
or manager action reports.
