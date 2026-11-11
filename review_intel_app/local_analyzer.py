"""Explainable restaurant rules. No models, network requests, or training."""

from functools import lru_cache
import re
from price_rules import analyze_price

# Bump this whenever rules change so Streamlit does not reuse old analysis.
RULES_VERSION = "local-rules-4-price-context"

EXTRA_TERMS = {
    "food_flavor": ["food", "meal", "chicken", "dishes", "tasty", "undercooked", "overcooked"],
    "seasoning": ["salty", "saltiness", "spices"],
    "consistency": ["consistent", "inconsistent", "inconsistency"],
    "service_speed": ["quick", "speed", "long wait", "waiting"],
    "staff": ["service", "waiter", "waitress", "bartender", "host", "helpful", "polite"],
    "portion_value": ["generous", "tiny portion"],
    "ambiance": ["noisy", "noise"],
    "cleanliness": ["unclean", "filthy", "hygiene"],
    "catering": ["events"],
    "wait_reservation": ["reservations", "tables"],
    "takeout": ["pickup", "pick-up", "packaging", "delivered"],
}
AMBIGUOUS_TERMS = {"warm", "special", "theme", "the meat"}

POSITIVE = [
    "great", "good", "amazing", "excellent", "delicious", "friendly", "attentive",
    "wonderful", "love", "loved", "best", "fantastic", "perfect", "awesome",
    "helpful", "welcoming", "tasty", "fresh", "outstanding", "incredible",
    "kind", "polite", "fast", "quick", "quickly", "generous", "beautiful",
    "cozy", "flavorful", "impressed", "favorite", "clean", "consistent",
    "affordable", "worth it",
]
NEGATIVE = [
    "slow", "bland", "diluted", "small", "stingy", "barely", "disappointing",
    "disappointed", "disappoints", "dry", "late", "missing", "sticky", "loud",
    "noisy", "high side", "forever", "rushed", "distracted", "gone down",
    "overwhelmed", "rude", "cold", "worst", "bad", "poor", "dirty", "unclean",
    "filthy", "expensive", "pricey", "inconsistent", "undercooked", "overcooked",
    "mostly rice", "needed attention", "long wait", "took long",
]
# Explicit phrases take priority over their individual words.
PHRASES = {
    "not bad": "pos", "no wait": "pos", "no waiting": "pos",
    "never disappoints": "pos", "never disappointed": "pos",
    "not disappointed": "pos", "no complaints": "pos", "not too spicy": "pos",
    "not too salty": "pos", "not worth": "neg", "too spicy": "neg",
    "too salty": "neg", "too mild": "neg", "not the same": "neg",
    "could be better": "neg", "not enough": "neg",
}
NEGATORS = {
    "not", "no", "never", "isn't", "wasn't", "weren't", "aren't", "didn't",
    "doesn't", "don't", "isnt", "wasnt", "cannot", "can't",
}
HEDGING = re.compile(
    r"\b(?:maybe|perhaps|possibly|might|unsure|unclear|not sure|"
    r"could(?!\s+(?:not|be better))|yeah right|as if)\b", re.I
)
WORDS = re.compile(r"[a-z]+(?:'[a-z]+)?")


@lru_cache(maxsize=512)
def _pattern(term):
    """Boundaries prevent matches such as 'heat' inside 'theater'."""
    return re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", re.I)


def _gap(a, b):
    return max(0, a[0] - b[1], b[0] - a[1])


def _cues(text):
    low = text.lower().replace("’", "'")
    cues, occupied = [], []
    for phrase, polarity in sorted(PHRASES.items(), key=lambda item: -len(item[0])):
        for match in _pattern(phrase).finditer(low):
            span = match.span()
            if any(_gap(span, used) == 0 and span[0] < used[1] and used[0] < span[1]
                   for used in occupied):
                continue
            cues.append((span, polarity, phrase))
            occupied.append(span)
    for terms, polarity in [(POSITIVE, "pos"), (NEGATIVE, "neg")]:
        for term in terms:
            for match in _pattern(term).finditer(low):
                span = match.span()
                if any(span[0] < used[1] and used[0] < span[1] for used in occupied):
                    continue
                before = WORDS.findall(low[:span[0]])[-3:]
                # A conjunction ends the scope of a preceding negation.
                for boundary in ("and", "or", "while"):
                    if boundary in before:
                        before = before[len(before) - before[::-1].index(boundary):]
                negations = sum(word in NEGATORS for word in before)
                if low[:span[0]].rstrip().endswith("not only"):
                    negations = 0
                result = polarity
                if negations % 2:
                    result = "neg" if polarity == "pos" else "pos"
                cues.append((span, result, term))
    return cues


def analyze_text(text, themes):
    """Return theme sets and evidence; unknown wording stays unclassified."""
    positive, negative, evidence, reasons = set(), set(), [], set()
    clauses = re.split(
        r"[.!?;\n]+|,\s*|\b(?:but|however|although|though|yet)\b", str(text),
        flags=re.I,
    )
    for clause in clauses:
        clause = clause.strip()
        if not clause:
            continue
        low = clause.lower().replace("’", "'")
        # Anticipation is not a service-speed complaint.
        searchable = re.sub(
            r"\b(?:can't|cannot) wait to (?:return|come back|visit|try)\b",
            lambda match: " " * len(match.group()), low,
        )
        hits = []
        for theme, config in themes.items():
            terms = (set(config["kw"]) | set(EXTRA_TERMS.get(theme, []))) - AMBIGUOUS_TERMS
            for term in sorted(terms):
                for match in _pattern(term).finditer(searchable):
                    hits.append((theme, match.span(), term))
        if not hits:
            continue
        # Generic "service" does not turn a speed complaint into a staff complaint.
        if any(theme == "service_speed" for theme, _, _ in hits):
            hits = [hit for hit in hits if not (hit[0] == "staff" and hit[2] == "service")]
        cues = _cues(searchable)
        assignments = {theme: set() for theme, _, _ in hits}
        uncertain = bool(HEDGING.search(low))
        if not uncertain:
            for span, polarity, _ in cues:
                intrinsic = [hit for hit in hits if hit[1] == span]
                if intrinsic:
                    targets = intrinsic
                elif len(cues) == 1 and not any(
                    span[0] < hit[1][1] and hit[1][0] < span[1] for hit in hits
                ):
                    targets = hits  # A shared adjective: "great food and service".
                else:
                    distance = min(_gap(span, hit[1]) for hit in hits)
                    targets = [hit for hit in hits if _gap(span, hit[1]) == distance
                               and distance <= 60]
                for theme, _, _ in targets:
                    assignments[theme].add(polarity)
        for theme, polarities in assignments.items():
            terms = sorted({term for key, _, term in hits if key == theme})
            if uncertain or not polarities:
                reason = ("Tentative wording needs a person to check it." if uncertain else
                          "A theme is mentioned without clear praise or criticism.")
                reasons.add(reason)
                evidence.append({
                    "theme": theme, "polarity": "Needs review", "matched_terms": terms,
                    "excerpt": clause[:600], "reason": reason,
                })
            for polarity in sorted(polarities):
                (positive if polarity == "pos" else negative).add(theme)
                evidence.append({
                    "theme": theme,
                    "polarity": "Praise" if polarity == "pos" else "Complaint",
                    "matched_terms": terms, "excerpt": clause[:600],
                    "reason": "Matched theme terms and a nearby sentiment phrase.",
                })
    # Keep the old matching pass intact for every non-price theme. New price
    # vocabulary and cues must not steal sentiment from food, staff or portions.
    positive.discard("price")
    negative.discard("price")
    evidence = [item for item in evidence if item["theme"] != "price"]
    price_pos, price_neg, price_evidence, price_reasons = analyze_price(text, themes, HEDGING)
    if price_pos:
        positive.add("price")
    if price_neg:
        negative.add("price")
    evidence.extend(price_evidence)
    reasons.update(price_reasons)
    if not evidence:
        reasons.add("No supported restaurant theme was found. Check this review manually.")
    return positive, negative, evidence, sorted(reasons)
