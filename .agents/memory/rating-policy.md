---
name: Rating normalization compatibility
description: Why upload warnings retain the existing rating conversion policy.
---
Preserve existing rating normalization semantics when adding upload warnings.

**Why:** Changing rounding or rejecting malformed ratings would also change
existing datasets' averages and automatic analysis when reloaded. The requested
change was transparency before confirmation, not a new scoring scheme.

**How to apply:** Treat future changes to rating defaults, clipping, or decimal
handling as explicit policy changes with historical-comparison implications.
