---
name: Agent Plan toggle versus workspace Build tab
description: Distinguish the two mode controls when writes are unexpectedly blocked.
---

The workspace's top Build tab does not mean the Agent composer has Plan disabled. Check the separate Plan toggle beside the model selector in the message composer.

**Why:** Repeated workspace writes were blocked while the top Build tab was selected; the user's screenshot showed the composer Plan toggle still enabled. Disabling that toggle produced the explicit Build-mode update and restored writes.

**How to apply:** When tools report Plan-mode write restrictions, inspect the composer toggle before suggesting restarts, new chats, task-routing changes, or support. Do not treat a queued task as assigned merely because Build is selected.
