---
name: Upload publication dates
description: Calendar-date semantics for review timestamps with timezone offsets.
---
Keep a review's publication calendar date as stated by its source when normalizing uploaded timestamps; do not shift it to a UTC calendar day.

**Why:** Review trends and action comparisons are grouped by publication day. UTC conversion near midnight can silently move an accepted review into another month or year.

**How to apply:** When changing date parsing, test mixed naive and offset timestamps on month/year boundaries, and continue rejecting absent dates instead of substituting retrieval time.

Upload correction reports use logical CSV row numbers (header = 1), not physical
text-editor line numbers; blank lines are skipped.

**Why:** A quoted review can span multiple physical lines but remains one CSV
record. Corrections must refer to source order before date sorting or rejection
filtering, without copying private review text into the report.

**How to apply:** Keep the numbering explanation visible beside the download and
preserve multiline-record tests when changing the CSV reader.
