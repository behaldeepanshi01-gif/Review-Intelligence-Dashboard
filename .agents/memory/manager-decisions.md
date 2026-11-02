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
