---
name: Manager decision scope
description: Conservative reuse policy for local manager decisions and saved action baselines.
---

Require renewed manager approval after a local rules-version change, even if the
review itself is unchanged. Preserve rule evidence separately from effective
manager tags, and do not rewrite previously saved action baselines when tags change.

**Why:** A manager approves a specific interpretation of a review, not future
rule behavior. Rewriting historical baselines would make later comparisons misleading.

**How to apply:** When changing rule versions or correction behavior, preserve the
original decisions for provenance without silently applying them to a new version.
Explain that saved baselines and approved replies may need manual checking.

Historical decisions must remain readable after the supported theme vocabulary
changes. Obsolete tags are history, not valid candidates for direct reapproval.

**Why:** Rules migrations can remove themes. Validating all historical tags against
the new vocabulary can block unrelated datasets and reports even though that history
is never applied. Keep history compatibility separate from current-decision validity.

**How to apply:** Show obsolete tags for review, require supported current tags
before saving a new decision, and never silently drop or translate historical tags.

Do not infer whether a legacy decision was a renewal from matching tags. A renewal
must reference the particular source rules version and saved decision revision
selected by the manager, not merely the most recent earlier decision.

**Why:** Identical tags can result from either a new correction or a renewal;
invented provenance would misrepresent what the manager approved.

**How to apply:** Keep legacy origin explicitly unknown. Retain recorded source
references even if the earlier decision is later edited or removed. A manual
correction is a separate origin, not a continuation inferred from matching tags.
