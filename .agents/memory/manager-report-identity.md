---
name: Manager report identity boundary
description: Approved local identity scope and reuse boundary for calendar authorization.
---
The user extended the original report-only account scope to the whole restaurant
dashboard. Keep one local identity system for dashboards, reports, and calendars.

**Why:** The app must remain free and local without new packages. The original
report-only boundary was deliberately expanded; do not restore an unsigned
dashboard for compatibility with older tests. Already downloaded files cannot
be recalled.

**How to apply:** Reuse the local identity service for future protected features. Explicitly scope grants to stable dataset IDs and exact locations, never filenames. Do not silently retain shared-password access as a fallback or create a second identity store for timezone permissions.

Report-file retrieval requires fresh credential confirmation by the issuing
manager, in addition to the original dashboard login still being valid.

**Why:** The local dashboard identity lives in Streamlit session state, not an
authenticated HTTP browser cookie. A random download URL alone must not become
authority to read a report. Reauthentication avoids adding a second cookie-based
login system. Reports are temporary, single-process deliveries, not durable assets.

**How to apply:** Preserve the privacy acknowledgment and filtered report builder
when adding formats. Never switch reports back to public Streamlit media links.
Keep explicit logout invalidation and retrieval-time permission checks; do not
promise recall of bytes already delivered.

Dataset creation and unassigned legacy-history recovery are trusted local-owner
operations, not implied by a location grant. Snapshot replacement needs grants
for all old and new locations, including rejected CSV rows.

**Why:** Partial-location managers must not delete another restaurant's reviews,
and filename-based orphan history has no trustworthy authorization scope.

**How to apply:** Do not reintroduce dashboard create/claim/transfer controls
without an explicit owner permission model. Preserve stored histories and
previous snapshots.

Authorization based on a snapshot must remain bound to that snapshot at publication.

**Why:** A manager with access to one location could otherwise validate an old
single-location snapshot and overwrite a newer multi-location snapshot they
were never authorized to replace.

**How to apply:** Use a conditional write against the checked immutable snapshot
identity, or hold a transaction across the authorization check and publication.
Test with interleaved saves by differently scoped managers, not just sequential denials.
