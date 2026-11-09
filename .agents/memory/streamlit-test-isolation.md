---
name: Streamlit test isolation
description: AppTest process state and workspace uploads can affect otherwise isolated tests.
---
Run multiprocessing-based tests before Streamlit AppTest tests, or in a separate
Python process. Explicitly select sample data in fixtures that expect it.

**Why:** AppTest can leave the process main-module path pointing at its temporary
dashboard script. Spawned multiprocessing workers then execute that script
instead of the test entry point, producing misleading app errors and EOF failures.
Separately, a new workspace upload changes the dashboard's default data source,
including during simultaneous browser testing.

**How to apply:** Keep multiprocessing and browser-free Streamlit checks isolated
when running the full suite. Give each protected UI fixture a temporary account
and explicit dataset selection rather than relying on the current workspace.

AppTest can retain a stale formatted-selectbox mapping when switching between
datasets with identical review display labels but different internal review keys.

**Why:** Navigation checks encountered a test-driver serialization error before
the app reran: the new raw review key was not in the previous display options.
This is distinct from action draft loss.

**How to apply:** In action-focused AppTest fixtures, use raw IDs for unrelated
review selectors if this occurs; retain production formatting in the real-browser
navigation check rather than treating the fixture workaround as browser proof.
