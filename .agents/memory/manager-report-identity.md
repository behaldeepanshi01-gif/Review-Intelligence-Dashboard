---
name: Manager report identity boundary
description: Approved local identity scope and reuse boundary for calendar authorization.
---
The user approved individual local accounts for manager reports, not a full-dashboard login migration. Keep one identity system for report and later timezone authorization.

**Why:** The app must remain free and local without new packages. A report gate must not be described as protecting other dashboard views, ordinary exports, or already downloaded files.

**How to apply:** Reuse the local identity service for future protected features. Explicitly scope grants to stable dataset IDs and exact locations, never filenames. Do not silently retain shared-password access as a fallback or create a second identity store for timezone permissions.
