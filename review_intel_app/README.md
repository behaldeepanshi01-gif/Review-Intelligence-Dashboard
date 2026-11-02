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
| Reply inbox | AI-drafted replies sorted by urgency. Edit, approve, copy. Nothing posts automatically |
| Export | Analyzed reviews CSV, alerts CSV, and a weekly owner summary ready to paste into email or WhatsApp |

## Quick start

```bash
pip install -r requirements.txt
streamlit run app.py
```

It opens in your browser with 930 synthetic reviews across four sample locations.

To regenerate the sample data:

```bash
python generate_data.py
```

## Three AI engines

- **Offline (default):** keyword and rule based tagging. Free, instant, no account needed.
- **Ollama (free, local):** runs an open-source AI model on your own computer. Install Ollama
  from ollama.com, run `ollama pull llama3.2:3b` once, then pick "Ollama" in the sidebar and
  analyze reviews in rounds (50 at a time by default). Progress is saved after every few reviews,
  so you can stop and continue later. Reviews not yet analyzed fall back to offline results.
  On a laptop with less than 8 GB of RAM, use `llama3.2:1b` instead.
- **Claude API:** pick "Claude API" in the sidebar, paste an Anthropic API key, click
  "Run Claude analysis." Claude reads each review like a person would, which matters for
  real, messy reviews (sarcasm, mixed feelings, typos). Results are cached in `data/`, so
  each review is only sent once. You can also set the key as an environment variable:
  `export ANTHROPIC_API_KEY=...`

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
engine.py          Tagging (offline + Claude), alerts, staff leaderboard, reply drafts
generate_data.py   Builds the synthetic dataset
data/              Sample data and Claude cache
```

## Roadmap

1. Connect directly to Google Business Profile so new reviews flow in automatically
2. Weekly summary sent to owners by email or WhatsApp
3. Link review themes to POS data (for example, do "small portion" complaints line up with a
   recipe or supplier change?)
