# Price-language safety suite: frozen-cycle diagnostics

## What shipped, and what did not

Added 38 **invented** language cases, each tested through the actual app's
`engine.tag_offline` at ratings 1, 3 and 5. These are specifications for
conservative behavior, not human reference labels or held-out accuracy evidence.
No real review source, labels, hidden predictions, corrections, actions or
historical baselines were read or changed by this suite.

**No analyzer fix shipped.** The current rules still incorrectly classify
several questions and reported opinions. Completing this diagnostic work must
not be described as fixing those user-visible behaviors.

After the diagnostics exposed these gaps, the user explicitly selected
**“Keep the evaluation freeze”** rather than authorizing a separate rules cycle.
The accepted scope is therefore diagnostic coverage with the actual fixes
deferred. Expected failures remain open defects, not successful safety checks.

The coordination restriction takes precedence over broader tuning: the approved
monetary-waste implementation is frozen for the separate blind-evaluation cycle.
The task records for that fix and evaluation were inspected before this work.
No rule/source/version/cache change was made; implementation hashes still match
`MONEY_WASTE_HANDOFF.md`. No existing application or test file was edited, so
no analyzer backup or new rules version was necessary. The project memory
records the user's explicit freeze decision.

## Files

- `price_language_cases.py`: invented questions, rhetoric, quotations/reported
  opinions, punctuation-sensitive negation, hedges, and preservation controls.
- `test_price_language_safety.py`: desired price polarity, textual evidence,
  manager-review warnings, rating independence of tags/evidence, frozen source
  identity, and exact per-review non-price comparison.
- `price_language_nonprice_baseline.json`: frozen non-price praise/complaint sets
  **and full evidence objects**, including neutral evidence, for every example.
  This is current behavior, not a claim that each non-price tag is ground truth.

Warnings for ambiguity must coexist with explicit opinions elsewhere in a
review. The mixed-context tests therefore require both the explicit polarity
and a `Needs review` evidence entry for the uncertain wording.
Ratings may still affect urgency and rating/text-mismatch warnings, as before;
they must not change theme sides or textual evidence.

## Results

From `review_intel_app`:

```sh
python -B -m unittest test_price_language_safety -q
```

117 tests: **42 pass and 75 expected failures**:
- 13 supported examples × 3 ratings = 39 passing language checks.
- 25 unresolved examples × 3 ratings = 75 expected failures.
- 3 additional invariants pass (ratings, exact non-price snapshot, source hashes).

Known failures by category (examples, not rating combinations):

| Category | Examples |
| --- | ---: |
| Questions | 10 |
| Quoted opinions | 6 |
| Reported opinions | 3 |
| Rhetorical wording | 2 |
| Punctuation-separated uncertainty/negation | 4 |

Examples include “Are the prices fair?”, “Isn't it affordable?”, a brochure
calling prices “reasonable”, and “The prices are not, in my view, reasonable.”
The last example is explicit criticism, not ambiguity; its future fix must
retain the negation rather than merely abstain on all punctuated text.

Expected failures assert the desired safe result, **not the current wrong result**.
Each example/rating has its own test so an early failure cannot hide another
example. Unexpected success fails the suite and signals that the recorded gap
must be examined. The separate rating checks also exercise every case without
expected-failure wrapping, so runtime errors cannot be hidden as known defects.
This is a diagnostic suite, **not a clean safety gate or an accuracy score**.

Existing regression modules also ran: `test_price_rules`, `test_local_analyzer`,
`test_evaluation_scoring`, `test_manager_corrections`, `test_review_action_flow`,
`test_action_tracker`, and `test_source_coverage`: **88 passed**.
The initial combined run found an overly broad new rating invariant (urgency
intentionally depends on stars). That test was corrected to compare theme sides
and evidence; the entire new 117-test module then passed with the 75 explicitly
expected failures above. The unchanged regression modules were not rerun.

No application code/UI changed, so no workflow restart, screenshot or browser
test was needed. Nothing was deployed.

## Separate, approved next cycle

1. Preserve the current blind batch and its provenance. Obtain explicit approval
   before changing rules; coordinate with the evaluation owner. Do not reuse
   frozen held-out predictions under a changed implementation or tune on labels
   from that batch.
2. Freeze before predictions and exact non-price outputs and make timestamped,
   non-overwriting backups/manifests of all existing files to be edited.
3. Address question/reported-opinion scope and punctuation-sensitive negation
   without broad shared sentiment cues. Keep explicit praise, complaints, mixed
   opinions and monetary-waste behavior.
4. Bump the rules version, review cache/approval/baseline provenance behavior,
   and run correction/provenance regressions. Remove known-failure annotations
   only for fixed cases; preserve their full desired assertions.
5. Update the source-identity test deliberately for the new authorized cycle.
   Keep the non-price snapshot unchanged unless a separate non-price change is
   explicitly authorized. Retain the old evaluation evidence and report all
   improvements/regressions without making held-out accuracy claims.
