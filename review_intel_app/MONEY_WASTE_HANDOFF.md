# Narrow monetary-waste fix and blind-evaluation handoff

## Scope and result

Rules: `local-rules-3-money-waste`. Recognizes direct “do not waste your money”,
“don't waste your money”, and “waste of my money” cost criticism. Genuine
negation, tentative/reported/quoted examples, mixed feedback, portion/value
coexistence, evidence and manager warnings are covered. No shared waste cue,
rating-based polarity, new dependency, API, model or deployment was added.
Broader indirect-price tuning is deferred.

This is synthetic and tuning-set evidence, **not held-out accuracy**.
The 61 labels began as Claude AI drafts: 56 CSV approvals and separate chat
approval for MC001–MC005. Labels and source files were not edited.

## Verification

- Existing private diagnostic was inspected, then its 12 literal invented cases
  were parsed without executing the supplied script. At ratings 1, 3 and 5:
  **24/36 before, 36/36 after**. Improvements: S01, S02, S03 and S11 at each
  rating. No synthetic regressions. Exact non-price tags and evidence preserved.
- `python -B -m unittest test_price_rules test_local_analyzer test_evaluation_scoring -v`:
  **28 passed**.
- `python -B -m unittest test_manager_corrections test_review_action_flow test_action_tracker test_source_coverage test_price_app test_local_app -v`:
  **68 passed**. Includes renewed approvals, saved-baseline provenance,
  evidence display, neutral-price warnings and isolated Streamlit UI checks.
- Both commands run from `review_intel_app`. No full-suite claim.
- All 61 unchanged tuning rows: **no changed sample/theme/polarity pairs**,
  no improvements, no regressions, no non-price changes (including evidence).
  All **120** existing errors remain: 110 missed sides and 10 unsupported sides.

Counts are correct / missed / unsupported:

| Scope | Before praise | After praise | Before complaint | After complaint |
|---|---|---|---|---|
| All themes | 71 / 51 / 7 | 71 / 51 / 7 | 30 / 59 / 3 | 30 / 59 / 3 |
| Price | 3 / 1 / 0 | 3 / 1 / 0 | 3 / 7 / 0 | 3 / 7 / 0 |

## Files and private evidence

Edited application/test files:
- `review_intel_app/price_rules.py`
- `review_intel_app/local_analyzer.py`
- `review_intel_app/test_price_rules.py`

Added `review_intel_app/verify_money_waste.py` and this handoff.
Updated `.agents/memory/theme-tuning-safety.md` with the authorized freeze boundary.

Non-overwriting backup directory:
`review_intel_app/backups/monetary_waste_20261106T213333728385Z/`.
`manifest.json` records the three original code/test SHA-256 hashes;
`memory-manifest.json` records the original memory note hash. Each original
file is copied there by basename. Existing backups were preserved.

Private frozen before snapshot:
`review_intel_app/data/private_evaluation/current_app_20261106T213338644793Z/`.
Private after snapshot:
`review_intel_app/data/private_evaluation/current_app_20261106T213419000923Z/`.
Each has `manifest.json`, `predictions.csv`, `errors.csv`, `scores.json`,
`text_fingerprints.json`, `report.md` and `report.html`.

Detailed comparison:
`review_intel_app/data/private_evaluation/money_waste_20261106T2135Z/comparison.json`.
It lists every remaining error by sample ID/theme/polarity/error, both score
tables, all 36 synthetic results, and empty change/improvement/regression lists.
`regression_tests.log` in that directory contains the 68-test run.
The 28-test output is retained in the execution transcript.
These private directories are Git-ignored: retain them in this workspace;
do not publish them or assume Git merge transfers private evidence.

## Frozen implementation for Task #30

SHA-256:

| File in review_intel_app | Hash |
|---|---|
| engine.py (unchanged) | `c239d262fd38050781b293e9294f4a7873f0c6ae6d396f28eeba44a12f6920ff` |
| local_analyzer.py | `d6396a7253644cf6322d64f7da38e6f48ab0439e4982e9b18ed009f292fdbfbd` |
| price_rules.py | `633d70e5d29d0c10b7eb3aa7f903de64a2353ee5a3424cb763ce040ba0d5bc22` |

Wait until these changes are merged and verify actual-app hashes before
freezing the blind batch. No unused-review predictions were generated or
shown in this work. Do not score held-out reviews yet. Only the user or
restaurant manager labels and approves that batch; no AI ground truth.
No new follow-up task was created: the existing downstream task covers it.

## UI inspection and undo

Interactive app path: `/dashboard/` (not the root video).
Select the authorized dataset/location, Theme → Price, Showing → Complaints,
and open “Why these tags?”; review ambiguous cases in the manager-review section.
The version remains part of the Streamlit cache key; older manager approvals
require renewed approval, and saved baselines retain provenance warnings.
Dashboard workflow restarted successfully; public health endpoint returned 200.
Authenticated evidence/manager-warning paths were checked by isolated AppTest,
not by a signed-in browser session.

To undo safely, first preserve any later edits, then restore only the three
code/test files from this backup after validating its manifest, and restart the
dashboard. Do not restore or overwrite datasets, corrections, actions, or
historical baselines. Version-specific approvals remain version-specific;
rollback can make earlier matching-version approvals eligible again, so review
their provenance. This is an undo procedure, not an undo performed here.

At handoff, changes are in the assigned task workspace, not confirmed merged
into the main app; nothing was deployed.
