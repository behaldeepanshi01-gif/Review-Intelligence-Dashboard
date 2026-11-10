"""
Review Intelligence engine.

Local Review Analyzer (default): explainable rules, no network or model downloads.
Optional Claude API support is retained, but is never called by local analysis.

Both return the same columns, so the dashboard works with either.
"""

from __future__ import annotations

import io
import json
import os
import re
from datetime import timedelta
from pathlib import Path

import pandas as pd
from local_analyzer import RULES_VERSION as LOCAL_ANALYZER_VERSION, analyze_text

# ----------------------------------------------------------------------------
# Theme dictionary
# ----------------------------------------------------------------------------
THEMES = {
    "food_flavor": {"label": "Food & flavor",
                    "kw": ["flavor", "flavour", "tasted", "taste", "delicious", "dish", "cooked",
                           "fresh", "curry", "naan", "biryani", "tikka", "masala", "dal", "paneer",
                           "special"]},
    "seasoning": {"label": "Seasoning & spice",
                  "kw": ["spice", "spicy", "mild", "bland", "seasoning", "seasoned", "heat",
                         "diluted", "salt"]},
    "consistency": {"label": "Consistency",
                    "kw": ["not the same", "used to", "gone down", "every visit", "consistently",
                           "tasted different", "last few visits", "anymore"]},
    "service_speed": {"label": "Service speed",
                      "kw": ["slow", "wait", "waited", "forever", "quickly", "fast", "took long",
                             "between courses", "overwhelmed"]},
    "staff": {"label": "Staff & hospitality",
              "kw": ["server", "staff", "attentive", "hospitality", "friendly", "recommendations",
                     "shout out", "warm", "rude", "distracted"]},
    "portion_value": {"label": "Portions & value",
                      "kw": ["portion", "portions", "value", "stingy", "leftovers", "not worth",
                             "barely any chicken", "barely any meat", "mostly rice", "the meat"]},
    "price": {"label": "Price",
              "kw": ["price", "prices", "pricey", "expensive", "high side", "cheap"]},
    "ambiance": {"label": "Ambiance & decor",
                 "kw": ["decor", "ambiance", "ambience", "atmosphere", "theme", "cozy", "loud",
                        "beautiful", "vibe"]},
    "cleanliness": {"label": "Cleanliness",
                    "kw": ["clean", "dirty", "sticky", "restroom", "bathroom"]},
    "catering": {"label": "Catering & events",
                 "kw": ["catered", "catering", "wedding", "event", "party"]},
    "wait_reservation": {"label": "Seating & reservations",
                         "kw": ["reservation", "seated", "table quickly", "seating"]},
    "takeout": {"label": "Takeout & delivery",
                "kw": ["takeout", "take-out", "delivery", "packed", "to go"]},
}
THEME_LABELS = {k: v["label"] for k, v in THEMES.items()}

NEG_CUES = ["not ", "no ", "never", "slow", "bland", "mild", "diluted", "small", "stingy",
            "barely", "okay", "nothing special", "disappoint", "dry", "late", "missing",
            "sticky", "loud", "high side", "forever", "rushed", "distracted", "gone down",
            "used to", "different", "waited", "overwhelmed", "rude", "cold", "worst", "mostly rice",
            "needed more", "needed attention", "hard to", "not worth", "long wait"]
POS_OVERRIDES = ["worth it", "not too", "no complaints", "never disappoints", "not disappoint",
                 "can't wait", "cannot wait", "never had a bad", "no wait", "not a single",
                 "wasn't disappoint", "won't be disappoint", "nothing but"]
POS_CUES = ["great", "amazing", "excellent", "delicious", "friendly", "attentive", "wonderful",
            "love", "loved", "best", "fantastic", "perfect", "awesome", "helpful", "welcoming",
            "warm", "tasty", "fresh", "recommend", "outstanding", "incredible", "kind", "fast",
            "quick", "generous", "beautiful", "cozy", "flavorful", "impressed", "favorite"]

STAFF_PATTERNS = [
    r"(?:server|waiter|waitress|bartender|host|manager|chef)\s+([A-Z][a-z]{2,})",
    r"[Ss]hout out to\s+([A-Z][a-z]{2,})",
    r"[Tt]hanks to\s+([A-Z][a-z]{2,})",
]
NOT_NAMES = {"The", "Our", "Food", "Service", "Everything", "This", "That", "It", "Staff",
             "Takeout", "Catering", "Every", "Even", "Very", "Great", "Loved"}

HIGH_URGENCY_THEMES = {"cleanliness", "consistency", "service_speed"}

# How a theme reads inside a reply ("We're glad you enjoyed ...")
PRAISE_PHRASE = {
    "food_flavor": "the food", "seasoning": "the spice balance",
    "consistency": "coming back to us", "service_speed": "the quick service",
    "staff": "the service from our team", "portion_value": "the portions",
    "price": "the value", "ambiance": "the atmosphere", "cleanliness": "the clean space",
    "catering": "our catering", "wait_reservation": "getting seated quickly",
    "takeout": "your takeout order",
}


# ----------------------------------------------------------------------------
# Offline tagging
# ----------------------------------------------------------------------------
def _sentences(text: str) -> list[str]:
    """Split into sentences, then split mixed clauses ("great food but slow service")."""
    parts = re.split(r"(?<=[.!?])\s+", str(text))
    clauses = []
    for p in parts:
        clauses += re.split(r"\s*(?:\bbut\b|\bhowever\b|\balthough\b|\bthough\b|;)\s*", p,
                            flags=re.I)
    return [c.strip() for c in clauses if c and c.strip()]


def _count(low: str, cues: list[str]) -> int:
    n = 0
    for c in cues:
        c2 = c.strip()
        if c.endswith(" "):          # "not ", "no " -> whole word only
            n += len(re.findall(rf"\b{re.escape(c2)}\b", low))
        else:
            n += low.count(c2)
    return n


def _clause_polarity(s: str, rating: int) -> str:
    """Return 'neg' or 'pos' for one clause, using cue balance, then rating as tie-breaker."""
    low = s.lower()
    if any(p in low for p in POS_OVERRIDES):
        return "pos"
    neg, pos = _count(low, NEG_CUES), _count(low, POS_CUES)
    if neg > pos:
        return "neg"
    if pos > neg:
        return "pos"
    if neg == pos == 0:
        return "neg" if rating <= 2 else "pos"
    return "neg" if rating <= 3 else "pos"


def find_staff(text: str) -> list[str]:
    names = set()
    for pat in STAFF_PATTERNS:
        for m in re.findall(pat, str(text)):
            if m not in NOT_NAMES:
                names.add(m)
    return sorted(names)


def tag_offline(text: str, rating: int) -> dict:
    """Keep the legacy function name while using the versioned local rules."""
    pos, neg, evidence, reasons = analyze_text(text, THEMES)
    if (rating >= 4 and neg and not pos) or (rating <= 2 and pos and not neg):
        reasons.append("The star rating and the detected wording differ. Check the result.")
    return {**effective_tag_fields(text, rating, pos, neg), "tag_evidence": evidence,
            "needs_review": bool(reasons), "review_reasons": reasons}


def effective_tag_fields(text, rating, pos, neg):
    """Derived fields shared by rule results and manager-confirmed tag sets."""
    pos, neg = set(pos), set(neg)
    # Only explicitly praised staff enter the shout-out list.
    staff = find_staff(text) if "staff" in pos and "staff" not in neg else []
    if rating <= 2 or (neg & HIGH_URGENCY_THEMES and rating <= 3):
        urgency = "High"
    elif neg:
        urgency = "Medium"
    else:
        urgency = "Low"
    sentiment = "Mixed" if (pos and neg) or not (pos or neg) else (
        "Negative" if neg else "Positive")
    return {"themes_pos": sorted(pos), "themes_neg": sorted(neg), "staff": staff,
            "urgency": urgency, "sentiment": sentiment}


def draft_reply_offline(row: dict) -> str:
    loc = row["location"]
    first = str(row.get("reviewer", "")).split(" ")[0] or "there"
    neg = row["themes_neg"]
    pos = [theme for theme in row["themes_pos"] if theme not in neg]
    staff = row["staff"]
    lines = [f"Hi {first},"]
    if not neg and not pos:
        lines.append(f"Thank you for visiting {loc} and sharing your feedback.")
        lines.append("Please contact us directly if you would like to tell us more.")
    elif not neg:
        lines.append(f"Thank you so much for the kind words about {loc}.")
        if staff:
            lines.append(f"We'll make sure {', '.join(staff)} hears this, it means a lot to the team.")
        elif pos:
            lines.append(f"We're glad {PRAISE_PHRASE[pos[0]]} stood out for you.")
        lines.append("We hope to see you again soon.")
    else:
        fix = {
            "service_speed": "the wait you had",
            "seasoning": "the spice level not meeting your expectations",
            "consistency": "the dish not tasting the way you remember",
            "portion_value": "the portion not feeling worth the price",
            "price": "the value not feeling right",
            "cleanliness": "the cleanliness issue",
            "staff": "the service you received",
            "food_flavor": "the food not meeting your expectations",
            "wait_reservation": "the delay in seating you",
            "takeout": "the problem with your order",
            "catering": "the issue with your event order",
            "ambiance": "the noise level",
        }
        order = ["cleanliness", "consistency", "service_speed", "staff", "wait_reservation",
                 "portion_value", "seasoning", "food_flavor", "takeout", "catering", "price",
                 "ambiance"]
        ranked = sorted(neg, key=lambda t: order.index(t) if t in order else 99)
        issue = " and ".join(fix.get(t, "your experience") for t in ranked[:2])
        if pos:
            lines.append(f"Thank you for visiting {loc} and for the honest feedback. "
                         f"We're glad you enjoyed {PRAISE_PHRASE[pos[0]]}.")
        else:
            lines.append(f"Thank you for visiting {loc}, and we're sorry about your experience.")
        lines.append(f"We're sorry about {issue}. We'll review this feedback with our team.")
        lines.append("If you're open to it, please reach out to us directly. We'd love the chance "
                     "to make your next visit better.")
    lines.append(f"The {loc} team")
    return "\n".join(lines)


def analyze_offline(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    tags = [tag_offline(t, r) for t, r in zip(out["text"], out["rating"])]
    for key in ["themes_pos", "themes_neg", "staff", "urgency", "sentiment",
                "tag_evidence", "needs_review", "review_reasons"]:
        out[key] = [t[key] for t in tags]
    out["reply_draft"] = [draft_reply_offline(r) for r in out.to_dict("records")]
    out["engine"] = "local_rules"
    return out


# ----------------------------------------------------------------------------
# Claude mode
# ----------------------------------------------------------------------------
CLAUDE_MODEL = os.environ.get("REVIEW_INTEL_MODEL", "claude-sonnet-5-5")

SYSTEM_PROMPT = f"""You analyze restaurant guest reviews for an owner-run Indian restaurant group.
For each review, return a JSON object with:
- "review_id": copy it exactly
- "themes_pos": list of theme keys the guest was positive about
- "themes_neg": list of theme keys the guest was negative about
- "staff": first names of staff the guest mentions (empty list if none)
- "urgency": "High" (rating 1-2, food safety, cleanliness, or a regular saying quality dropped),
  "Medium" (any other complaint), or "Low" (no complaint)
- "sentiment": "Positive", "Mixed" or "Negative"
- "reply_draft": a short, warm, specific owner reply (3-5 sentences). Thank them, name what they
  liked, own any problem without excuses, invite them back or to contact the restaurant.
  Plain language. No em dashes. Never promise refunds or discounts. Sign off "The <location> team".

Allowed theme keys: {", ".join(THEMES.keys())}.
Return ONLY a JSON array, one object per review, no other text."""


DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _cache_path(data_tag: str, engine: str = "claude") -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", data_tag)
    return os.path.join(DATA_DIR, f"{engine}_cache_{safe}.json")


def _load_cache(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_cache(path: str, cache: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f)
    os.replace(tmp, path)


def _as_list(x) -> list:
    if isinstance(x, list):
        return [str(i) for i in x if str(i).strip()]
    if isinstance(x, str) and x.strip():
        return [p.strip() for p in x.split(",") if p.strip()]
    return []


def _merge_results(df: pd.DataFrame, cache: dict, engine_name: str) -> pd.DataFrame:
    """Combine AI results with offline results for any review the AI skipped."""
    out = df.copy()
    fallback = analyze_offline(df).set_index("review_id")
    valid = set(THEMES)
    rows = []
    for r in out.itertuples():
        f = fallback.loc[r.review_id]
        c = cache.get(str(r.review_id))
        if c is None:
            rows.append({k: f[k] for k in ["themes_pos", "themes_neg", "staff", "urgency",
                                           "sentiment", "reply_draft", "tag_evidence",
                                           "needs_review", "review_reasons"]})
            continue
        urgency = c.get("urgency", "Low")
        sentiment = c.get("sentiment", "Mixed")
        rows.append({
            "themes_pos": [t for t in _as_list(c.get("themes_pos")) if t in valid],
            "themes_neg": [t for t in _as_list(c.get("themes_neg")) if t in valid],
            "staff": _as_list(c["staff"]) if "staff" in c else f["staff"],
            "urgency": urgency if urgency in {"High", "Medium", "Low"} else f["urgency"],
            "sentiment": sentiment if sentiment in {"Positive", "Mixed", "Negative"} else f["sentiment"],
            "reply_draft": c.get("reply_draft") or f["reply_draft"],
            # External results do not come with local rule evidence.
            "tag_evidence": [],
            "needs_review": False,
            "review_reasons": [],
        })
    for key in ["themes_pos", "themes_neg", "staff", "urgency", "sentiment", "reply_draft",
                "tag_evidence", "needs_review", "review_reasons"]:
        out[key] = [x[key] for x in rows]
    out["engine"] = engine_name
    return out


def analyze_with_claude(df: pd.DataFrame, api_key: str, data_tag: str = "default",
                        batch_size: int = 15, progress=None) -> pd.DataFrame:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    cache_file = _cache_path(data_tag, "claude")
    cache = _load_cache(cache_file)

    todo = df[~df["review_id"].astype(str).isin(cache.keys())]
    batches = [todo.iloc[i:i + batch_size] for i in range(0, len(todo), batch_size)]
    for n, batch in enumerate(batches, 1):
        payload = [{"review_id": str(r.review_id), "location": r.location,
                    "rating": int(r.rating), "reviewer": str(r.reviewer), "text": str(r.text)}
                   for r in batch.itertuples()]
        msg = client.messages.create(
            model=CLAUDE_MODEL, max_tokens=8000, system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}])
        raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        start, end = raw.find("["), raw.rfind("]")
        results = json.loads(raw[start:end + 1])
        for item in results:
            cache[str(item["review_id"])] = item
        _save_cache(cache_file, cache)
        if progress:
            progress(n / len(batches))

    return _merge_results(df, cache, "claude")


# ----------------------------------------------------------------------------
# Legacy Ollama helpers retained for compatibility, not exposed by the dashboard.
# Do not call these during local analysis. Existing cache files remain untouched.
# ----------------------------------------------------------------------------
OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_DEFAULT_MODEL = "llama3.2:3b"

# Short keys and a short prompt = far fewer tokens per review = much faster on a laptop.
OLLAMA_PROMPT = f"""Tag ONE restaurant review. Output JSON only:
{{"pos":[themes praised],"neg":[themes complained about],"urg":"High|Medium|Low","sent":"Positive|Mixed|Negative"{{REPLY_FIELD}}}}
Themes: {", ".join(THEMES.keys())}
Praise is not a complaint. urg High = rating 1-2, hygiene, or quality dropped. Medium = other complaint. Low = none."""

REPLY_FIELD_ON = (',"reply":"3 short owner sentences: thank, name what they liked, own any problem, '
                  'invite back. No em dashes, no refunds. End: The <location> team"')
SHORT_KEYS = {"pos": "themes_pos", "neg": "themes_neg", "urg": "urgency",
              "sent": "sentiment", "reply": "reply_draft"}


def ollama_status() -> tuple[bool, list[str]]:
    """Return (is_running, installed_model_names)."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3) as r:
            data = json.loads(r.read().decode("utf-8"))
        return True, sorted(m.get("name", "") for m in data.get("models", []))
    except Exception:
        return False, []


def _ollama_chat(model: str, system: str, user: str, num_predict: int = 120,
                 timeout: int = 300) -> str:
    import urllib.request
    body = json.dumps({
        "model": model, "stream": False, "format": "json",
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "options": {"temperature": 0, "num_ctx": 1024, "num_predict": num_predict},
        "keep_alive": "30m",  # keep the model loaded between batches
    }).encode("utf-8")
    req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))["message"]["content"]


def analyze_with_ollama(df: pd.DataFrame, model: str = OLLAMA_DEFAULT_MODEL,
                        data_tag: str = "default", write_replies: bool = False,
                        progress=None, should_stop=None) -> pd.DataFrame:
    """One review per call (small local models are more reliable that way).
    Results are cached after every review, so you can stop and resume anytime."""
    system = OLLAMA_PROMPT.replace("{REPLY_FIELD}", REPLY_FIELD_ON if write_replies else "")
    num_predict = 320 if write_replies else 120
    cache_file = _cache_path(f"{data_tag}_{model}", "ollama")
    cache = _load_cache(cache_file)

    todo = df[~df["review_id"].astype(str).isin(cache.keys())]
    total, errors = len(todo), 0
    for n, r in enumerate(todo.itertuples(), 1):
        if should_stop and should_stop():
            break
        user = f"Location: {r.location}\nRating: {int(r.rating)}\nReview: {str(r.text)[:1200]}"
        try:
            raw = _ollama_chat(model, system, user, num_predict=num_predict)
            parsed = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
            item = {SHORT_KEYS.get(k, k): v for k, v in parsed.items()}
            if not write_replies:
                item.pop("reply_draft", None)
            cache[str(r.review_id)] = item
        except Exception:
            errors += 1  # skip this one, offline result is used instead
        if n % 5 == 0 or n == total:
            _save_cache(cache_file, cache)
        if progress:
            progress(n / max(total, 1), n, total, errors)
    _save_cache(cache_file, cache)
    return _merge_results(df, cache, f"ollama:{model}")


def ollama_cached(df: pd.DataFrame, model: str, data_tag: str) -> int:
    cache = _load_cache(_cache_path(f"{data_tag}_{model}", "ollama"))
    return int(df["review_id"].astype(str).isin(cache.keys()).sum())


def load_ollama_results(df: pd.DataFrame, model: str, data_tag: str) -> pd.DataFrame:
    cache = _load_cache(_cache_path(f"{data_tag}_{model}", "ollama"))
    return _merge_results(df, cache, f"ollama:{model}")


# ----------------------------------------------------------------------------
# Loading and validating data
# ----------------------------------------------------------------------------
REQUIRED = ["location", "date", "rating", "text"]
RATING_POLICY = (
    "Analysis uses whole-number ratings from 1 to 5. Missing or nonnumeric ratings "
    "become 3; numeric values below 1 or above 5 (including infinities) are clipped "
    "to 1 or 5; remaining decimals are truncated, not rounded (4.9 becomes 4). "
    "These changes can affect averages, trends, urgency and automatic tags. "
    "Only accepted reviews are adjusted; the original CSV is never rewritten."
)


def normalize_ratings(raw: pd.Series) -> tuple[pd.Series, dict]:
    """Apply the compatibility policy and explain changes in source-record order."""
    numeric = pd.to_numeric(raw, errors="coerce")
    missing = raw.isna() | raw.astype(str).str.strip().eq("")
    clipped = numeric.fillna(3).clip(1, 5)
    normalized = clipped.astype(int)
    masks = {
        "Missing rating → 3": missing,
        "Nonnumeric rating → 3": numeric.isna() & ~missing,
        "Below 1 → 1": numeric.lt(1),
        "Above 5 → 5": numeric.gt(5),
        "Fractional rating truncated": clipped.ne(normalized),
    }
    rows = [
        {"source_row": int(index) + 2,
         "original_rating": "" if pd.isna(raw.loc[index]) else str(raw.loc[index]),
         "analysis_rating": int(normalized.loc[index]),
         "adjustments": "; ".join(reason for reason, mask in masks.items() if mask.loc[index])}
        for index in raw.index if any(mask.loc[index] for mask in masks.values())
    ]
    return normalized, {
        "changed": len(rows),
        "reasons": {reason: int(mask.sum()) for reason, mask in masks.items()},
        "rows": rows,
    }


def load_reviews(file_or_path) -> pd.DataFrame:
    """Load only analysis-eligible records; use preview_reviews before import."""
    return preview_reviews(file_or_path)[0]


def preview_reviews(file_or_path) -> tuple[pd.DataFrame, dict]:
    """Validate without writing or inventing dates; counts refer to source rows.

    Reasons may overlap (a record can lack both its date and its text).
    The caller retains the original bytes, including rejected records.
    source_row is the logical CSV row (header = 1), not a physical text line.
    Quoted multiline fields count as one record; blank lines are skipped.
    """
    # Parse a separate raw view so pandas' NA/type inference cannot erase rating
    # spelling; leave inference for all other columns unchanged.
    content = (file_or_path.read() if hasattr(file_or_path, "read")
               else Path(file_or_path).read_bytes())
    buffer = io.StringIO if isinstance(content, str) else io.BytesIO
    df = pd.read_csv(buffer(content))
    raw = pd.read_csv(buffer(content), dtype=str, keep_default_na=False)
    df.columns = [c.strip().lower() for c in df.columns]
    raw.columns = df.columns
    rename = {"stars": "rating", "review": "text", "review_text": "text",
              "restaurant": "location", "business": "location", "name": "reviewer"}
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns and v not in df.columns})
    raw = raw.rename(columns={k: v for k, v in rename.items() if k in raw.columns and v not in raw.columns})
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"CSV is missing columns: {', '.join(missing)}. "
                         f"Needed: {', '.join(REQUIRED)} (reviewer and review_id optional).")
    df["rating"] = raw["rating"]
    if "review_id" not in df.columns:
        df["review_id"] = [f"R{i:05d}" for i in range(len(df))]
    if "reviewer" not in df.columns:
        df["reviewer"] = "Guest"
    missing_date = df["date"].isna() | df["date"].astype(str).str.strip().eq("")
    # Keep each source's publication calendar date, not its UTC-converted day.
    # Parse individually because a CSV may mix naive timestamps and offsets.
    def publication_date(value):
        parsed = pd.to_datetime(value, errors="coerce", format="mixed")
        return parsed.tz_localize(None) if not pd.isna(parsed) else pd.NaT

    parsed_dates = pd.to_datetime(df["date"].map(publication_date), errors="coerce")
    missing_text = df["text"].isna() | df["text"].astype(str).str.strip().eq("")
    rejected = parsed_dates.isna() | missing_text
    reason_masks = {
        "Missing date": missing_date,
        "Invalid date": parsed_dates.isna() & ~missing_date,
        "Missing review text": missing_text,
    }
    summary = {
        "total": len(df), "accepted": int((~rejected).sum()),
        "rejected": int(rejected.sum()),
        "reasons": {reason: int(mask.sum()) for reason, mask in reason_masks.items()},
        "rejected_rows": [
            {"source_row": position + 2,
             "rejection_reasons": "; ".join(
                 reason for reason, mask in reason_masks.items() if mask.iloc[position])}
            for position in range(len(df)) if rejected.iloc[position]
        ],
    }
    df["date"] = parsed_dates
    df = df.loc[~rejected].copy()
    df["rating"], summary["ratings"] = normalize_ratings(df["rating"])
    df["review_id"] = df["review_id"].astype(str)
    dup = df["review_id"].duplicated(keep=False)
    if dup.any():  # make every ID unique so results never get mixed up
        df.loc[dup, "review_id"] = (df.loc[dup, "review_id"] + "-"
                                    + df[dup].groupby("review_id").cumcount().astype(str))
    return df.sort_values("date").reset_index(drop=True), summary


def validation_report_csv(validation: dict) -> bytes:
    """Export only row locators and fixed reasons, never source review content."""
    return pd.DataFrame(
        validation["rejected_rows"], columns=["source_row", "rejection_reasons"],
    ).to_csv(index=False).encode("utf-8")


# ----------------------------------------------------------------------------
# Insights
# ----------------------------------------------------------------------------
def theme_table(tagged: pd.DataFrame) -> pd.DataFrame:
    """Rows = location x theme, with % of reviews positive/negative on that theme."""
    records = []
    for loc, g in tagged.groupby("location"):
        n = len(g)
        for t, label in THEME_LABELS.items():
            p = sum(t in x for x in g["themes_pos"])
            q = sum(t in x for x in g["themes_neg"])
            if p + q == 0:
                continue
            records.append({"location": loc, "theme": label, "theme_key": t,
                            "positive": p, "negative": q,
                            "pct_negative": round(100 * q / n, 1),
                            "pct_positive": round(100 * p / n, 1),
                            "net": round(100 * (p - q) / n, 1)})
    return pd.DataFrame(records, columns=[
        "location", "theme", "theme_key", "positive", "negative",
        "pct_negative", "pct_positive", "net",
    ])


def early_warnings(tagged: pd.DataFrame, recent_days: int = 30, baseline_days: int = 90,
                   min_count: int = 3, min_share: float = 10.0, min_lift: float = 1.5) -> pd.DataFrame:
    """Flag themes whose negative share jumped in the last N days vs the prior baseline."""
    end = tagged["date"].max()
    recent_start = end - timedelta(days=recent_days)
    base_start = recent_start - timedelta(days=baseline_days)
    alerts = []
    for loc, g in tagged.groupby("location"):
        recent = g[g["date"] > recent_start]
        base = g[(g["date"] > base_start) & (g["date"] <= recent_start)]
        if len(recent) < 5:
            continue
        for t, label in THEME_LABELS.items():
            rc = sum(t in x for x in recent["themes_neg"])
            bc = sum(t in x for x in base["themes_neg"])
            r_share = 100 * rc / len(recent)
            b_share = 100 * bc / max(len(base), 1)
            lift = r_share / b_share if b_share > 0 else float("inf") if rc else 0
            if rc >= min_count and r_share >= min_share and lift >= min_lift:
                alerts.append({
                    "location": loc, "theme": label, "recent_mentions": rc,
                    "recent_share": round(r_share, 1), "baseline_share": round(b_share, 1),
                    "change": "new issue" if b_share == 0 else f"{lift:.1f}x",
                    "severity": "High" if r_share >= 25 else "Medium",
                })
    df = pd.DataFrame(alerts)
    if not df.empty:
        df = df.sort_values(["severity", "recent_share"], ascending=[True, False])
    return df


def staff_leaderboard(tagged: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for r in tagged.itertuples():
        for name in r.staff:
            rows.append({"location": r.location, "staff": name,
                         "positive": int(r.rating >= 4), "rating": r.rating})
    if not rows:
        return pd.DataFrame(columns=["location", "staff", "mentions", "positive", "avg_rating"])
    d = pd.DataFrame(rows)
    return (d.groupby(["location", "staff"])
             .agg(mentions=("rating", "size"), positive=("positive", "sum"),
                  avg_rating=("rating", "mean"))
             .round(2).reset_index().sort_values("mentions", ascending=False))


def monthly_trend(tagged: pd.DataFrame) -> pd.DataFrame:
    d = tagged.copy()
    d["month"] = d["date"].dt.to_period("M").dt.to_timestamp()
    return (d.groupby(["month", "location"])
             .agg(avg_rating=("rating", "mean"), reviews=("rating", "size"))
             .round(2).reset_index())
