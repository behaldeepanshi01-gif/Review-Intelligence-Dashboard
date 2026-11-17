# Local analyzer checks

## Scope

This is a deterministic, rule-based analyzer, not a trained language model.
All regression test passages are synthetic. Private review text and guest names
are not stored in these checks or included in the source update bundle.

## Timing run

Measured on Replit on 2026-11-02, with no API or model calls:

| Dataset | Reviews | Locations | Analysis seconds | Flagged for manager review |
|---|---:|---:|---:|---:|
| Synthetic sample | 930 | 4 | 0.670 | 531 |
| Private review upload | 385 | 4 | 0.874 | 317 |

The measurements exclude imports, CSV loading, and UI rendering. The sample ran
first and the private upload ran second in the same process. Both measurements
include theme rules, evidence, and reply templates. Windows laptop timings may
differ. There is no accuracy claim: the private dataset has no verified theme
labels, and flagging 317 of 385 reviews means substantial manual checking may
be needed. This does not mean that all other tags on flagged reviews are wrong.

## Verification

The final check run passed 23 tests, plus Python compilation and whitespace checks.

- Synthetic tests cover all 12 theme keys, mixed praise and criticism, negation,
  word boundaries, neutral and hedged statements, rating conflicts, staff praise,
  and no-theme reviews.
- Existing action tracker and weekly summary tests are retained.
- Streamlit's in-process checks exercise default local analysis, visible rule
  explanations, review-needed navigation, and no-theme empty states without a browser.
- Cached external results are not shown with explanations from local rules.
- Local analysis and the default app check forbid urllib network calls.

Run the checks with:

```powershell
python -m unittest -v test_local_analyzer test_action_tracker test_local_app
python benchmark_local.py data/sample_reviews.csv
```

This is not the separate end-to-end Yelp action-tracking verification. It is a
regression and speed check of the local analyzer only.
