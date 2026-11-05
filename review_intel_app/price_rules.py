"""Price-only evidence rules. No ratings, models, manager data or network calls."""
import re

TERMS = (
    "prices", "price", "pricing", "pricey", "pricier", "overpriced",
    "expensive", "inexpensive", "affordable", "cheap", "costly",
    "gratuity", "service charge", "service charges", "tip", "tips",
    "money", "fee", "fees", "cost", "costs",
)
POSITIVE = (
    "reasonably priced", "well priced", "affordable", "inexpensive",
    "reasonable", "fair", "cheap", "good", "great", "excellent",
    "worth the money", "value for money", "worth it",
)
NEGATIVE = (
    "waste of money", "not worth it", "not worth", "overpriced",
    "pricier", "pricey", "expensive", "costly", "unreasonable",
    "unfair", "excessive", "steep", "high side", "high", "bad", "poor",
    "hidden", "unexpected", "forced", "demanded",
)
NEGATORS = {"not", "no", "never", "isn't", "wasn't", "aren't", "weren't",
            "isnt", "wasnt", "don't", "doesn't", "didn't"}
NON_PRICE_AMBIGUOUS = {"good", "great", "excellent", "bad", "poor", "worth", "worth it"}
FEES = {"gratuity", "service charge", "service charges", "tip", "tips", "fee", "fees", "money"}
WORDS = re.compile(r"[a-z]+(?:'[a-z]+)?")


def matches(term, text):
    return re.finditer(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text, re.I)


def analyze_price(text, themes, hedging):
    """Return price sides and explanatory evidence with conservative cue scope.

    Fees/tips/money alone are neutral. Shared generic adjectives about food or
    staff are not cost opinions. Unknown, hedged or conflicting context stays
    visible for manager review instead of being inferred from star ratings.
    """
    positive = negative = False
    evidence, reasons = [], set()
    other_terms = {term for theme, config in themes.items() if theme != "price"
                   for term in config["kw"]} | {"food", "meal", "server", "service",
                                               "portion", "portions", "staff", "value"}
    clauses = re.split(
        r"[.!?;\n]+|,\s*|\b(?:but|however|although|though|yet|and|while)\b",
        str(text), flags=re.I)
    for raw in clauses:
        clause = raw.strip()
        low = clause.lower().replace("’", "'")
        hits = [(m.span(), term) for term in TERMS for m in matches(term, low)]
        # "Reasonably priced" is an explicit price opinion, not a generic adjective.
        hits.extend((m.span(), "reasonably priced")
                    for m in matches("reasonably priced", low))
        hits.extend((m.span(), "well priced") for m in matches("well priced", low))
        if not hits:
            continue
        uncertain = bool(hedging.search(low)) or bool(re.search(
            r"\b(?:don't|do not|didn't|cannot|can't)\s+(?:think|say|tell)\b", low))
        cues, occupied = [], []
        for polarity, terms in (("Praise", POSITIVE), ("Complaint", NEGATIVE)):
            for term in sorted(terms, key=len, reverse=True):
                for match in matches(term, low):
                    span = match.span()
                    cues.append((span, polarity, term))
        # Longest explicit phrase wins, including "not worth" over "worth".
        selected = []
        for span, polarity, term in sorted(cues, key=lambda c: -(c[0][1] - c[0][0])):
            if any(span[0] < end and start < span[1] for start, end in occupied):
                continue
            selected.append((span, polarity, term))
            occupied.append(span)
        assigned = set()
        if not uncertain:
            for span, polarity, term in selected:
                for anchor, anchor_term in hits:
                    start, end = min(span[1], anchor[1]), max(span[0], anchor[0])
                    between = low[start:end] if start < end else ""
                    if len(WORDS.findall(between)) > 4:
                        continue
                    # A different subject between the cost and adjective breaks scope.
                    if any(list(matches(word, between)) for word in other_terms):
                        continue
                    price_distance = max(0, span[0] - anchor[1], anchor[0] - span[1])
                    other_subjects = [
                        m.span() for word in other_terms for m in matches(word, low)
                        if not (m.start() < anchor[1] and anchor[0] < m.end())
                        and not (m.start() < span[1] and span[0] < m.end())
                    ]
                    if any(max(0, span[0] - subject[1], subject[0] - span[1])
                           < price_distance for subject in other_subjects):
                        continue
                    if anchor_term in FEES and term in NON_PRICE_AMBIGUOUS:
                        continue
                    before = WORDS.findall(low[:span[0]])[-3:]
                    negations = sum(word in NEGATORS for word in before)
                    if low[:span[0]].rstrip().endswith("not only"):
                        negations = 0
                    effective = polarity
                    if negations % 2:
                        effective = "Complaint" if polarity == "Praise" else "Praise"
                    assigned.add(effective)
        for polarity in sorted(assigned):
            positive |= polarity == "Praise"
            negative |= polarity == "Complaint"
            evidence.append({
                "theme": "price", "polarity": polarity,
                "matched_terms": sorted({term for _, term in hits}),
                "excerpt": clause[:600],
                "reason": "Matched a price term and a nearby cost opinion, with local negation.",
            })
        if uncertain or not assigned:
            reason = ("Tentative price wording needs a person to check it." if uncertain else
                      "A price, fee, tip or money mention has no clear cost opinion.")
            reasons.add(reason)
            evidence.append({
                "theme": "price", "polarity": "Needs review",
                "matched_terms": sorted({term for _, term in hits}),
                "excerpt": clause[:600], "reason": reason,
            })
    return positive, negative, evidence, reasons
