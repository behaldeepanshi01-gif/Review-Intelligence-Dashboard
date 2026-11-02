Review Intelligence action tracker update

This update is based on the source ZIP uploaded to Replit.

Files in the update bundle:
- app.py: updated dashboard, including action planning, the Action tracker tab,
  manager actions in the weekly owner summary, and local rule explanations.
- engine.py and local_analyzer.py: the fast rule-based analyzer replacing Ollama
  in the dashboard. Copy both along with app.py.
- action_tracker.py: local action-log, follow-up, and summary helpers.
- test_action_tracker.py, test_local_analyzer.py, and test_local_app.py: local checks.
- benchmark_local.py: optional timings without printing review text or guest names.
- app.py.bak: original app.py from the uploaded ZIP for reference.
- gitignore_additions.txt: one optional privacy rule to append to your existing .gitignore.

Before copying to your Windows project:
1. Check whether Downloads contains a newer app.py, such as "app (2).py".
2. Back up the app.py currently in your project folder.
3. Copy app.py, engine.py, local_analyzer.py, and action_tracker.py into the project
   folder. Back up your own engine.py first as well as app.py.
4. Keep data/uploads and all Ollama cache files unchanged.

The bundle does not include data/uploads, Ollama caches, or yelp_demo_reviews.csv.
The feature needs no new packages and does not scrape Google reviews.
This local analyzer is a rule-based tool, not a trained language model. No Ollama
execution is offered. Existing Ollama cache files are left in place.

On the first saved action, the app creates data/action_log.json. It stores the
manager's action, owner, status, dates, and the alert baseline. Keep that file
private. Add the line in gitignore_additions.txt to your existing .gitignore if
you use GitHub. To undo the local analyzer, restore your own app.py and engine.py
backups. The Replit source backups are included under backups/before_local_analyzer/
for reference, but your laptop may have newer files. Extra helpers and the action
log can remain unused. If restoring the older app, leave its engine on Offline.
