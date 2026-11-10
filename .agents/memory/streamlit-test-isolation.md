---
name: Streamlit test isolation
description: AppTest process state and workspace uploads can affect otherwise isolated tests.
---
Run multiprocessing-based tests in a separate Python process rather than relying
on discovery order. Explicitly select sample data in fixtures that expect it.

**Why:** AppTest can leave the process main-module path pointing at its temporary
dashboard script. Spawned multiprocessing workers then execute that script
instead of the test entry point, producing misleading app errors and EOF failures.
Separately, a new workspace upload changes the dashboard's default data source,
including during simultaneous browser testing.

**How to apply:** Isolate spawn-based checks at the test boundary so standard
discovery and selective runs remain safe after any AppTest rerun. Do not replace
spawn with fork or threads to hide the failure: those exercise different locking
behavior. Give each protected UI fixture a temporary account
and explicit dataset selection rather than relying on the current workspace.
Use a file-backed, import-safe entry point for spawned-process checks, not a
stdin runner: spawned workers must be able to import the parent's main module.

AppTest can retain a stale formatted-selectbox mapping when switching between
datasets with identical review display labels but different internal review keys.

**Why:** Navigation checks encountered a test-driver serialization error before
the app reran: the new raw review key was not in the previous display options.
This is distinct from action draft loss.

**How to apply:** In action-focused AppTest fixtures, use raw IDs for unrelated
review selectors if this occurs; retain production formatting in the real-browser
navigation check rather than treating the fixture workaround as browser proof.
