# Price-language safety suite

## Authorized post-freeze punctuation cycle — 2026-11-11

The separately assigned punctuation cycle builds on the completed question/
quoted-opinion cycle below; it does not replace that work or tune on held-out
labels. The working tree was clean before edits and the source hashes matched
that cycle. `rhetorical_right` was already fixed and remains an ordinary passing
assertion. Only the three remaining `scope` failure annotations were retired;
their desired polarity, evidence and warning assertions were not weakened.

Rules are now **`local-rules-5-price-punctuation`**:
- Explicit negation retains scope through recognized comma-delimited speaker
  asides: “in my view/opinion”, “to me”, “at all”, and “by any means”.
  “The prices are not, in my view, reasonable” remains criticism.
- Leading comma-separated hedges abstain. A bare “; not.” afterthought
  abstains rather than confidently praising or inverting the opinion.
- Uncertain price evidence remains visible with a manager warning; the bare
  afterthought is included verbatim in its evidence excerpt.
- Existing question, quotation, rhetoric, dash, parentheses, smart-apostrophe,
  sentence-boundary and mixed-opinion controls remain passing.

This is bounded pattern matching, not a general parenthetical parser.
Unlisted speaker asides are not claimed as supported. A leading hedge can
conservatively suppress other price opinions in the same semicolon-delimited
sentence segment; explicit opinions in separate sentences remain independent.
No non-price vocabulary or UI behavior was changed.

### Frozen baseline and backups

Before edits, eight app/test/document files and the relevant memory note were
copied to `backups/price_punctuation_20261111T020401498419Z/`, with SHA-256
identities in `manifest.json`. Original backup hashes were verified afterward.
`before.json` contains all 38 invented cases at ratings 1, 3 and 5 through
`engine.tag_offline` (114 actual predictions). Its SHA-256 is
`45404bb51942509d8e6938a388f7fc448dddfbc100b20cf51656293acdab0ca3`.
`after.json` and `comparison.json` record **9 improved combinations, zero
regressions, and zero exact non-price side/evidence differences**. Only
`negation_comma`, `negation_semicolon`, and `hedge_comma` changed.
The committed non-price snapshot remains byte-for-byte unchanged.

These Git-ignored backups are local rollback evidence and do not transfer
through merge. No private evaluation, source review, human-label, manager
correction or saved-action record was opened or edited. No held-out scoring
or labeling was performed. Synthetic regression scores are not accuracy claims.
The prior evaluation identities and records remain unchanged.

Current implementation identities (superseding the earlier cycle below):

| File | SHA-256 |
| --- | --- |
| engine.py (unchanged) | `b2624f72c3cc09f03e386554b53ef751372c83c6b69675a17e96a8df2be471f6` |
| local_analyzer.py | `c73717a8e97ebaf056815a98ccae17b317fe26f6fd58343643b8e01f2e197d5c` |
| price_rules.py | `b3bc68e69468132b8e891799de370b46a91ac89fccfdefbdd370a6d0f56105eb` |

### Verification

`uv run python -B -m unittest test_price_language_safety test_price_rules
test_local_analyzer test_evaluation_scoring test_manager_corrections
test_review_action_flow test_action_tracker test_source_coverage test_price_app
test_local_app -q` passed **235 tests with zero expected failures**.
The log is `regression_tests.log` in the backup directory.

The added controls exercise 15 punctuation/boundary variants at all three
ratings. Existing correction renewal, approval and saved-baseline provenance
regressions passed. The rules-version change invalidates the existing
version-keyed analysis cache and requires renewed matching manager approval;
it does not rewrite old decisions or historical action baselines.

Isolated Streamlit AppTest fixtures confirmed that both ambiguous punctuation
examples appear in the manager queue with the new warning. The dashboard
workflow restarted cleanly and public `/dashboard/_stcore/health` returned `ok`.
The screenshot showed the existing locked-dashboard/account-setup page, not
authenticated review content; authenticated UI evidence is the isolated test,
not that screenshot. No deployment or real-browser flow test was performed.

For rollback, verify the backup manifest, preserve subsequent changes, and
restore only this cycle's rules/version/tests/docs. Never restore private data
as part of a rule rollback. An old rules version can re-enable matching old
approvals; inspect provenance before using them.

## Approved separate price-context cycle — 2026-11-10

The user explicitly selected **“Authorize separate rule cycle”** after being
informed that the prior evaluation remains frozen, held-out data must not be
used for tuning, and earlier manager tag approvals require renewed approval.
This supersedes the diagnostic-only restriction for questions, rhetoric and
reported/quoted opinions only. Punctuation-separated negation and hedges remain
deferred. The historical account below is retained, not rewritten as new
evaluation evidence.

Rules are now `local-rules-4-price-context`. Price parsing retains question and
reporting context before splitting local clauses, tracks quotation spans across
sentence punctuation, and recognizes “yeah right”/“as if” rhetoric. Ambiguous
price evidence stays visible as **Needs review** instead of being counted as
praise or criticism. Explicit opinions in other sentences, explicit mixed
feedback, monetary-waste complaints, and rating-independent tags are preserved.
No shared non-price vocabulary, application UI, source reviews, human labels,
manager decisions or historical action baselines were changed.

This remains conservative pattern matching, not general language understanding.
Reporting context can suppress a direct author opinion in the **same sentence**
as a reported claim; attribution boundaries within such sentences need a
separate change. No real-world accuracy claim is made.

### Backup and baseline provenance

Before any edits, nine existing files were copied without overwriting earlier
backups to `backups/price_context_20261110T214725957979Z/`. Its `manifest.json`
contains each original file's SHA-256. It includes the analyzer, engine, case
specification, safety/UI tests, this document, non-price snapshot, and memory
note. `before.json` freezes all 38 invented cases at ratings 1, 3 and 5 through
the actual `engine.tag_offline` entry point: **114 predictions**, not mock output.
Its SHA-256 is
`f471cdf1bd1b8d043c2b6d429f1519b8001dd50bd1532825ea5d9f6e85018ce0`.

Backup hashes were verified after implementation. `after.json` and
`comparison.json` in the same directory preserve the results:
**66 improved case/rating combinations, zero regressions, and zero non-price
side or evidence differences**. The existing non-price snapshot is byte-for-byte
unchanged. No private evaluation directory was opened, scored, or modified.
These backups are Git-ignored workspace evidence; they do not transfer through
merge. Keep them available for rollback. The historical evaluation and its old
implementation identities in `MONEY_WASTE_HANDOFF.md` remain untouched.

Current implementation hashes:

| File | SHA-256 |
| --- | --- |
| engine.py | `b2624f72c3cc09f03e386554b53ef751372c83c6b69675a17e96a8df2be471f6` |
| local_analyzer.py | `02dbfb5fa9b8768a785ab355ae61c48d5c652c7339e6aca1bb5a5c12a0bdee39` |
| price_rules.py | `5a82af8c9c86ab1e0533f513e539e870372d8ccfdd661dc8fdfe66f5d1d321c6` |

The engine already differed from the historical identity before this task;
its actual pre-edit hash above was frozen and it remains unchanged. The new
identity test deliberately identifies this new cycle, not the old evaluation.
The pre-edit price-rules and local-analyzer hashes still matched the monetary-
waste handoff.

### Verification

From `review_intel_app`, using `uv run python -B -m unittest`:

- `test_price_language_safety test_price_rules test_local_analyzer
  test_evaluation_scoring test_manager_corrections test_review_action_flow
  test_action_tracker test_source_coverage test_price_app test_local_app -q`:
  234 tests, 224 passed, 9 expected failures, and one UI fixture assertion
  failed because its newly expanded queue initially selected the quoted review
  rather than the neutral fee review.
- The fixture was corrected to explicitly select the question and fee entries.
  `test_price_app -q` then passed. No application fix was needed and the other
  passing checks were not rerun. Logs are `regression_tests.log` and `ui_tests.log`
  in the backup directory. Final combined coverage: **225 passing checks and
  9 explicitly expected failures**, not a full-suite claim.
- 22 formerly failing examples × 3 ratings now use ordinary assertions. Only
  `negation_comma`, `negation_semicolon`, and `hedge_comma` remain expected
  failures (3 × 3 = 9); their desired assertions were not weakened.
- Added multi-sentence straight/curly/single quotation controls, explicit
  monetary-waste opinions after closing quotes, question/reporting scope across
  conjunctions, and mixed-opinion preservation at all three ratings.
- Existing correction/renewal/reply-approval and action-baseline provenance
  checks passed. The rules version is already part of the app cache key and
  correction scope. No old approval or saved baseline was rewritten.
- Isolated Streamlit AppTest confirmed price evidence and question/quotation/
  neutral-fee warnings. The dashboard workflow restarted cleanly and the public
  `/dashboard/_stcore/health` returned `ok`. The screenshot captured only the
  initial Streamlit shell, so it is not claimed as signed-in UI verification.
  No real-browser test or deployment was performed.

For rollback, verify the backup manifest and preserve later edits first.
Restore only the changed rules/tests/docs appropriate to that cycle, never
datasets, corrections, or saved actions. Restoring an old rules version can
make its matching approvals eligible again; inspect their provenance.

## Historical diagnostic-only cycle

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
