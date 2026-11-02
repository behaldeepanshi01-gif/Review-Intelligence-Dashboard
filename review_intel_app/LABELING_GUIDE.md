# Private review labeling

## What this is

This sheet is for a person to check theme tagging, not to generate more AI labels.
It is a small, balanced diagnostic sample, not proof of accuracy for all reviews
or evidence about Mumbai Central. No accuracy result exists until human labels
have been returned and checked.

## Keep it private

- The CSV contains real review text. Do not post it on GitHub, LinkedIn, or in a demo.
- Reviewer identity columns are omitted. Exact known reviewer display names are
  removed from the text where matched, but other personal details can remain.
  This is not anonymized data suitable for publication.
- Use Excel or a local spreadsheet editor. There is no need to upload it to an AI
  service or a shared online document.
- Generated sheets, human answers, and frozen predictions belong only under
  `data/private_evaluation/`, which is ignored by Git. Do not add them to source ZIPs.

## How to fill in the sheet

1. Open `labeling_sheet.csv`. Keep the column headings and sample IDs unchanged.
2. Read one review. Do not try to predict what the analyzer would say.
3. Fill in every one of its 12 theme cells using exactly one choice below.
4. If helpful, explain a hard decision in `notes`. Do not add personal details.
5. Set `human_checked` to **Yes** only after you personally check all 12 theme cells.
6. Save as **CSV UTF-8**, then return the completed file. Do not change `review_text`.

You can work in several sittings. Save after each sitting and keep a backup of
your filled-in copy. Blank cells mean unfinished, not "Absent". Never fill all
blank cells automatically with "Absent".

## The five choices

| Choice | Meaning |
|---|---|
| Praise | The reviewer clearly says something positive about this theme. |
| Complaint | The reviewer clearly criticizes this theme. |
| Both | There is explicit praise and criticism of this same theme. |
| Absent | This theme is not discussed in the review. |
| Unclear | The theme is mentioned neutrally, tentatively, or ambiguously. You cannot confidently assign praise or complaint. |

Use the wording, not the overall star rating. Multiple themes may apply to the
same passage. Do not guess the cause of a complaint. If genuinely unsure, choose
Unclear and add a short note.

Synthetic example only: "Delicious food, but the order took forever" praises Food
& flavor and complains about Service speed. It does not automatically criticize
the staff's attitude.

## Theme guide

| Column | What to look for |
|---|---|
| Food & flavor | Taste, freshness, cooking quality, or the dishes themselves. |
| Seasoning & spice | Spice level, salt, blandness, and seasoning. |
| Consistency | Whether quality stays the same or changes across visits. |
| Service speed | How long ordering, food, or service takes. |
| Staff & hospitality | Courtesy, helpfulness, attentiveness, and staff behavior. |
| Portions & value | Amount of food and whether the meal feels worth its cost. |
| Price | Prices being affordable, expensive, or otherwise evaluated. |
| Ambiance & decor | Atmosphere, decor, comfort, and noise. |
| Cleanliness | Hygiene or the condition of tables, floors, or restrooms. |
| Catering & events | Catering orders, group events, and event service. |
| Seating & reservations | Reservations, getting seated, and table availability. |
| Takeout & delivery | Pickup, delivery, packaging, or missing off-premise items. |

## Why some information is hidden

Ratings, location names, and analyzer predictions are not on the labeling sheet.
Predictions and rule fingerprints were frozen separately before labeling. Do not
open `frozen_predictions.json` before finishing; that could influence your answers.
The analyzer is evaluated on the reviewer-name-redacted text shown in your sheet.
Its normal use of source star ratings for review-needed flags is preserved.

The sample covers location and rating groups, not every theme. Rare themes may
still have too few examples to evaluate. If rules are changed after seeing these
answers, the same sample is no longer an untouched test for those new rules.

## What happens after you return it

- Check IDs, completed cells, valid choices, and human approval before scoring.
- Report correct and incorrect praise and complaint tags separately for each theme.
- Report mixed cases, human-unclear counts, and the analyzer's review-needed rate.
- Do not treat missing labels as negatives or unclear labels as certain answers.
- Mark themes with too few examples as insufficient evidence. Do not claim an
  overall accuracy percentage from this deliberately balanced, small sample.

The app, saved actions, original reviews, and caches are not changed by this sheet.
