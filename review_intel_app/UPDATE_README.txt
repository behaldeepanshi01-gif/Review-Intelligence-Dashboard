Review Intelligence action tracker update

This update is based on the source ZIP uploaded to Replit.

Files in the update bundle:
- app.py: updated dashboard, including action planning and the Action tracker tab.
- action_tracker.py: local action-log and follow-up helpers.
- test_action_tracker.py: quick standard-library tests.
- app.py.bak: original app.py from the uploaded ZIP for reference.
- gitignore_additions.txt: one optional privacy rule to append to your existing .gitignore.

Before copying to your Windows project:
1. Check whether Downloads contains a newer app.py, such as "app (2).py".
2. Back up the app.py currently in your project folder.
3. Copy the updated app.py and new action_tracker.py into the project folder.
4. Keep data/uploads and all Ollama cache files unchanged.

The bundle does not include data/uploads, Ollama caches, or yelp_demo_reviews.csv.
The feature needs no new packages and does not scrape Google reviews.

On the first saved action, the app creates data/action_log.json. It stores the
manager's action, owner, status, dates, and the alert baseline. Keep that file
private. Add the line in gitignore_additions.txt to your existing .gitignore if
you use GitHub. To undo the feature, restore your own app.py backup. The extra
helper and action log can remain unused.
