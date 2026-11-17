---
name: Streamlit dashboard routing
description: Avoid sending users to the animated demo or an unforwarded port.
---
The user repeatedly reached the animated demo when trying to open Export. Do not
give a development-host link with `:8000` merely because localhost health works.
Verify the public path serves Streamlit and that its WebSocket connects.

**Why:** This workspace uses path routing; root belongs to the separate video.
A locally healthy Streamlit process was not registered with the application router.

**How to apply:** Inspect current service routes and use the dashboard's registered
prefix, including its base URL setting. After workflow removal, verify the old
listener exited before starting a replacement; the old process survived removal
in this environment. Do not terminate unrelated apps.

Run Streamlit in explicit headless mode in unattended workspace workflows.

**Why:** A desktop display can make Streamlit default to interactive startup.
On a fresh workspace it then waits for an email address instead of opening its
port, even when usage-stat collection is disabled.

**How to apply:** If a restart stalls at the first-run email prompt, enable
`STREAMLIT_SERVER_HEADLESS=true` for development or use the equivalent startup
flag. Do not diagnose that prompt as an application crash or a routing failure.
