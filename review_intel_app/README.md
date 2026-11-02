# Review Intelligence

An AI review assistant for multi-location restaurant groups. It reads every guest review,
finds what guests praise and complain about at each location, warns owners when a problem
starts rising, tracks which staff guests praise by name, and drafts a reply for every review
that a manager approves before posting.

Built by Deepanshi Behal.

## What it does

| Tab | What owners get |
|---|---|
| Overview | Rating by location, monthly trend, complaint rate |
| What guests say | Heatmap of 12 themes (food, spice, consistency, service speed, portions, staff, ambiance, catering and more), top complaints, and the actual reviews behind each theme |
| Early warnings | Themes whose complaints jumped in the last 30 days vs the 90 days before |
| Staff shout-outs | Staff praised by name, per location |
| Reply inbox | Editable local reply templates, or optional API drafts. Edit, approve, copy. Nothing posts automatically |
| Export | Analyzed reviews CSV, alerts CSV, and a weekly owner summary ready to paste into email or WhatsApp |

## Quick start

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

It opens in your browser with 930 synthetic reviews across four sample locations.

To regenerate the sample data:

```bash
python generate_data.py
```

## Local Review Analyzer

The default analyzer uses restaurant phrases, bounded word matching, and nearby
sentiment cues. It is a rule-based tool, not a newly trained language model.
It uses no API, network requests, model downloads, or additional packages.
The Ollama controls have been removed. Existing Ollama cache files are not changed.

- Explicit praise and complaints can both be retained, including for the same theme.
  Star ratings do not erase clear criticism.
- Open **What guests say**, then **Why these tags?**, to see matched terms and the
  original passage that supports a tag.
- The **Reviews needing manager review** section lets you select unclear results.
  Neutral mentions and tentative statements are not forced into praise or complaints.
- Local reply drafts are templates. Check them before approval. Nothing posts automatically.
- The analyzer can miss sarcasm, unusual phrasing, implicit complaints, and context.
  A large review-needed count means manual checking is needed, not that accuracy is high.
- No confidence percentages or accuracy claims are shown without a labeled evaluation.

**Claude API** remains an optional paid mode and runs only when requested. Local
analysis never calls it. Local rule explanations are not presented as evidence for
Claude-produced tags.

### Caching and existing actions

The local rules version is part of the Streamlit cache key. When editing the rules,
bump `RULES_VERSION` in `local_analyzer.py`. Existing action records are preserved.
Old saved baselines may use earlier rules: do not interpret changes in tagging as
proof of restaurant improvements.

### Checks and undo

```bash
python -m unittest -v test_local_analyzer test_action_tracker test_local_app
python benchmark_local.py data/sample_reviews.csv
```

The app checks use Streamlit's in-process test utility, not a browser. Benchmark
output contains only counts and timing, never guest text or names. Timing on a
Replit machine does not guarantee the same speed on a Windows laptop.

Backups made before the local-analyzer update are in `backups/before_local_analyzer/`.
Restore that folder's `app.py`, `engine.py`, and `README.md` to undo this change.
The new helper can remain unused. The backup app exposes the old Ollama option, so
leave it on Offline if you restore. Do not delete your uploads, caches, or action log.

## Using real reviews

Upload a CSV from the sidebar with these columns:

| Column | Required | Example |
|---|---|---|
| location | yes | Upscale Dining Room |
| date | yes | 2026-10-12 |
| rating | yes | 4 |
| text | yes | The butter chicken was great but service was slow. |
| reviewer | no | Sam K. |
| review_id | no | G-0001 |

Uploaded files are saved in `data/uploads/`, so after a refresh or restart you can pick them
under "Saved file" instead of uploading again.

Common alternatives are renamed automatically (`stars` to rating, `review` to text,
`name` to reviewer). The Yelp filter script output works too after adding a `location` column.

**Where to get real reviews, legitimately:**
- With the owner's permission, their Google Business Profile shows every review and lets them reply.
- Without access, copy recent public reviews by hand into a spreadsheet. Don't use scraping tools,
  which break Google's and Yelp's terms.

## Privacy and honesty rules

- The sample data is fully synthetic. Names, staff and text are invented.
- Keep real guest names and private sales data out of anything public, including GitHub.
- Replies are drafts. A person approves every reply before it is posted.

## Files

```
app.py             Streamlit dashboard
engine.py          Local/API analysis, alerts, staff leaderboard, reply templates
local_analyzer.py  Explainable local phrase rules and evidence
benchmark_local.py Counts and timing only, no private review output
generate_data.py   Builds the synthetic dataset
data/              Sample data and Claude cache
```

## Roadmap

1. Connect directly to Google Business Profile so new reviews flow in automatically
2. Weekly summary sent to owners by email or WhatsApp
3. Link review themes to POS data (for example, do "small portion" complaints line up with a
   recipe or supplier change?)
