# Independent human-only labeling protocol

## Authorization and scope

On 2026-11-10, the user selected **“Approve conditional preparation”** in response
to the seven-part protocol below. This authorizes eligibility verification and
preparation of a new blank batch only after its conditions are met. It does not
authorize scoring, rule changes, relabeling, or rescoring the completed batch.

The protocol agreement and source-availability inspection are complete. New
batch preparation is blocked: the original private frozen batch and saved scores
are not available in this workspace. Do not interpret conditional authorization
as permission to bypass this stop condition.

## Agreed protocol

1. **Recover the prior evidence first.** Recover the original private batch and
   prior-use records before certifying eligibility. Preserve existing labels,
   approval statements, provenance notes, and scores unchanged. Missing records
   are a stop condition, not permission to recreate the completed evaluation.
2. **Verify eligibility and source limits.** Exclude previously labeled,
   evaluated, or tuning-exposed passages and duplicates. Record source identity
   and file hashes; hashes verify file identity, not authentic provenance or
   complete collection. Keep website testimonials, unrelated Yelp data, and
   synthetic examples outside this evaluation.
3. **Select without model influence.** After eligibility is verified, select up
   to 30 passages by a documented seeded random draw, without analyzer
   predictions, ratings, or AI sentiment screening. Freeze the current rules and
   separate hidden predictions before human labeling. Do not tune rules.
4. **Start blank and label personally.** The user or a designated manager labels
   every theme without AI suggestions, AI drafts, previous labels, or analyzer
   results. Hide ratings and remove reviewer names. Record prior exposure to
   labels or predictions and exclude affected passages from the independent set.
   Reviewer-name removal does not make the remaining review text public-safe.
5. **Keep the approved definitions.** Use Praise, Complaint, Both, Absent, and
   Unclear. Both requires praise and criticism of the same theme. Consistency
   requires an explicit comparison across visits or orders. Catering requires
   catering or an organized event with event-specific service, not simply dinner
   with friends. Takeout includes explicitly evaluated pickup, delivery,
   packaging, accuracy, or off-premise food condition; Food and Takeout may both
   apply without guessing the cause. Neutral or ambiguous wording is Unclear;
   Absent means the theme is not discussed. Do not force complaint/mixed labels
   to fill a quota. Record genuine uncertainty.
6. **Document provenance, not just approval.** Return explicit batch-specific
   statements confirming human-only labeling, lack of prediction/AI-label
   exposure, and approval of the exact completed file. Approval alone does not
   establish independence. Resolve or disclose conflicting provenance; do not
   erase it. Preserve the earlier personal blind-labeling and manager-approval
   statements alongside the earlier file's unresolved AI-draft provenance.
7. **Check coverage before requesting scoring.** Report human-labeled Complaint
   and Both support separately for each theme. Zero support means not evaluated;
   small counts mean limited evidence. No population accuracy claim is allowed.
   Request separate scoring authorization. If coverage is inadequate, seek
   authorization for a separate source or human-screened diagnostic sample,
   rather than silently changing selection.

## Recovery and handoff

Restore `data/private_evaluation/heldout_money_waste_20261106/` privately from the
workspace or backup where the original evaluation occurred, including
`frozen_predictions.json`, original deliverables, and the complete `scored_once/`
directory with its verification record. Obtain the other prior-use records
needed to establish exposure history. Validate original hashes and reconcile
source IDs, raw text fingerprints, normalized duplicates, and displayed/redacted
text matches. Do not overwrite any existing evidence or regenerate predictions
to replace missing historical records.

Local workspace and available ZIP entry searches found no copy of that batch.
The supplied draft-label sheet is still available, but it is not a replacement
for the frozen manifest, score artifacts, or complete exposure history.

Aggregate inspection evidence is in the private evaluation directory under
`independence_readiness_20261110/`. That directory is Git-ignored and excluded
from deployment, so it may not transfer on merge. Repeat the read-only inventory
against the private originals in the destination workspace. Do not publish real
review text, draft labels, reviewer identities, or private packets.

## Existing tooling limitations

Neither `prepare_heldout.py` nor `evaluate_heldout.py` was executed or changed for
this inspection. Do not run either automatically after approval of this
protocol. The former's command-line entry point targets the old batch name and
historical freeze; the latter contains report language specific to the completed
batch. They are not a ready-to-run workflow for this newly agreed protocol.
Future preparation must use a distinct batch and honor the recovery gate;
future scoring requires its own authorization and batch-appropriate reporting.
