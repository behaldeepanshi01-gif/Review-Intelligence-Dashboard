---
name: Restaurant action calendar
description: Scope of the restaurant timezone and why it defaults to Eastern time.
---

Use America/New_York as the initial restaurant timezone because the demo targets
Falls Church, Virginia. The current setting is session-wide, not a per-location
or persisted business setting.

**Why:** Deadline evaluation needed a restaurant-local day without introducing
a new settings store or changing existing action records. Multi-location
timezone ownership was not specified.

**How to apply:** Keep existing due dates as calendar dates. If adding persistent
settings or cross-timezone locations, define the owning restaurant explicitly
rather than inferring it from the server or a manager's browser timezone.
