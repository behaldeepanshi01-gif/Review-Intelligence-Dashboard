# Focused price-tagging update

## What changed

The existing Local Review Analyzer now has isolated price rules for reasonable
or fair pricing, affordability, pricier/overpriced wording and explicit cost
opinions about fees, tips or money. A fee, tip or money mention alone is not
praise or a complaint. Tentative wording stays flagged for manager review.
Mixed price statements can retain both sides. Star ratings never supply the
price sentiment.

The existing matching pass still determines all non-price outputs. New price
terms and opinions cannot take cues away from other themes. Existing warnings
are retained conservatively, so a newly supported price tag does not necessarily
clear a review's earlier warning.

Implementation:

- `local_analyzer.py`: version `local-rules-2-price`, price-only integration.
- `price_rules.py`: local vocabulary, negation, evidence and ambiguous cases.
- `evaluate_approved_sheet.py`: fingerprints the new price helper.
- `compare_price_evaluation.py`: exact per-review before/after comparison.
- `test_price_rules.py`, `test_price_app.py`: synthetic, browser-free checks.

No uploaded proposal was executed or substituted. `engine.py` and `app.py`
are unchanged. No Ollama, model download, paid API or deployment was used.

## Results on the approved 61-review tuning set

Counts below are **correct / missed / unsupported**, not an overall accuracy
percentage or restaurant-performance measure.

| Price side | Before | After |
|---|---|---|
| Praise | 0 / 4 / 0 | 3 / 1 / 0 |
| Complaint | 0 / 10 / 0 | 3 / 7 / 0 |

Six missed price tags were resolved. No final regressions or non-price prediction
changes were found. Eight price-side misses remain, including both sides of the
one mixed price cell. Across all themes, 120 errors remain. Mixed both-side
coverage stays 4/29. Thirteen Unclear cells remain unscored, and 53/61 reviews
still need manager review.

An intermediate candidate introduced an unsupported price-praise tag. Its
unqualified worth cue was removed before the final comparison.

All labels began as Claude AI drafts, subsequently approved by the user.
Fifty-six rows say Yes in the CSV; the first five retain no in the CSV and have
separate chat approval. No labels were changed and no manager adjudication is
claimed. These snapshots were saved after labeling. The baseline predates this
update, not the labels. This is **tuning-set evidence only, not a held-out test**.

Private outputs, including every improvement, regression and residual error:

- Before: `data/private_evaluation/current_app_20261105T223828256705Z/`
- After: `data/private_evaluation/current_app_20261105T224443846493Z/`
- Open `price_report.html` or `price_report.md` in the after directory.
- `price_comparison.json` has both summaries; `predictions.csv`, `errors.csv`,
  `improvements.csv`, `regressions.csv` and `unchanged_errors.csv` contain IDs
  and tags only, never guest names or raw review text.
- The original Task #6 evaluation is preserved separately.

## Verification

Run from `review_intel_app`:

```sh
python -B -m unittest test_price_rules test_price_app test_local_analyzer test_evaluation_scoring test_manager_corrections test_review_action_flow test_action_tracker test_local_app -v
```

The regression pass ran 72 tests. Seventy-one passed; the new UI test initially
expected an incorrect warning prefix. Only that assertion was corrected, and
`python -B -m unittest test_price_app -v` then passed. All 72 final test cases
have passing results. No analyzer code changed after that regression pass.
The UI tests are Streamlit AppTest, not browser automation.

Reproduce the evaluation in a new private directory:

```sh
python -B evaluate_approved_sheet.py --sheet '../attached_assets/mumbai_central_labeling_sheet_(15)_1793731218764.csv' --source ../attached_assets/mumbai_central_reviews_1793677255749.csv
```

To reproduce the comparison, pass the newly created after directory and frozen
before directory to `compare_price_evaluation.py --before <before> --after <after>`.
Do not overwrite earlier snapshots.

## Where to see it

In this Replit workspace, choose **Local Review Analyzer**, then:

1. **What guests say → Read the reviews behind a theme**.
2. Set **Theme** to **Price**, then choose **Praise** or **Complaints**.
3. Open **Why these tags?** beneath a review to see price terms and evidence.
4. For neutral or unclear mentions, open **Reviews needing manager review** and
   use **Review needing a check**. Its warning and evidence appear inline.

Existing manager decisions from older rules require renewed approval under
**What guests say → Decisions needing renewed approval**. They are not silently
reapplied. Historical action baselines remain unchanged; their provenance warning
can make follow-up comparisons unsuitable.

These are workspace changes. A separate Windows copy or published application
does not update automatically. Task merge status is separate from deployment.

## Safe undo

Backups and original SHA-256 hashes are in
`backups/price_tagging_20261105T223902898070Z/manifest.json`.

If neither file has later changes, restore these exact originals:

- `local_analyzer.py`
- `evaluate_approved_sheet.py`

If either has later edits, reverse only this update rather than overwriting
unrelated work. The added helpers and tests may remain unused. Do not restore
or delete source uploads, labels, caches, manager decisions, actions or baselines.

Restart Streamlit and use its **Clear cache** menu option, then rerun local
analysis. The restored version also changes the local cache key. Prior
`local-rules-1` approvals become eligible only under their original exact-source
checks; `local-rules-2-price` approvals must not apply backward. To require all
approvals afresh after rollback, use a new rollback rules version instead of
reusing either old version. Never erase decision history to force this.

Next recommended task: evaluate frozen rules on unused reviews independently
labeled by a restaurant manager, as already proposed.
