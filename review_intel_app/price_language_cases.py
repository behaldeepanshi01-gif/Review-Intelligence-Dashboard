"""Invented safety specifications, never manager labels or held-out examples.

The final field names a known gap in the frozen rules, NOT a desired outcome.
Remove it only in an explicitly approved new rule/evaluation cycle.
"""

# id, text, desired praise, desired complaint, known frozen-rule gap
CASES = (
    ("question_fair", "Are the prices fair?", False, False, "question"),
    ("question_expensive", "Is it expensive?", False, False, "question"),
    ("question_negative", "Isn't it affordable?", False, False, "question"),
    ("question_fragment", "Reasonable prices?", False, False, "question"),
    ("question_worth", "Was it worth the money?", False, False, "question"),
    ("rhetorical_fair", "Who would call these prices fair?", False, False, "rhetoric"),
    ("rhetorical_cheap", "Cheap prices, really?", False, False, "rhetoric"),
    ("rhetorical_as_if", "As if these prices were fair!", False, False, ""),
    ("rhetorical_right", "Yeah right, affordable prices!", False, False, "scope"),
    ("reported_fair", "They said the prices were fair.", False, False, "reported"),
    ("reported_expensive", "I heard it was expensive.", False, False, "reported"),
    ("quoted_positive", 'The sign says "affordable prices".', False, False, "quoted"),
    ("quoted_negative", 'The word “overpriced” appeared in the flyer.', False, False, "quoted"),
    ("quoted_single", "The brochure calls the prices 'reasonable'.", False, False, "quoted"),
    ("quoted_fragment", '"Fair prices."', False, False, "quoted"),
    ("negation_comma", "The prices are not, in my view, reasonable.", False, True, "scope"),
    ("negation_semicolon", "Affordable prices; not.", False, False, "scope"),
    ("negation_dash", "Prices are not — reasonable.", False, True, ""),
    ("negation_parentheses", "Prices are not (at all) reasonable.", False, True, ""),
    ("negation_smart", "Prices aren’t reasonable.", False, True, ""),
    ("negation_period", "Prices are reasonable. Not expensive.", True, False, ""),
    ("negation_question", "Not expensive?", False, False, "question"),
    ("hedge_comma", "Maybe, the prices are fair.", False, False, "scope"),
    ("hedge_colon", "Maybe: the prices are fair.", False, False, ""),
    ("explicit_praise", "Prices are fair!", True, False, ""),
    ("explicit_complaint", "Prices are unreasonable!", False, True, ""),
    ("explicit_mixed", "Fair lunch prices; overpriced dinner.", True, True, ""),
    ("reported_then_praise", 'They said "expensive". My prices were fair.', True, False, "reported"),
    ("reported_then_complaint", 'The sign says "cheap". My meal was overpriced.', False, True, "quoted"),
    ("question_then_praise", "Expensive? My prices were fair.", True, False, "question"),
    ("question_then_complaint", "Affordable? My meal was overpriced.", False, True, "question"),
    ("nonprice_staff", "Friendly staff. Are the prices fair?", False, False, "question"),
    ("nonprice_portions", "Generous portions. Is it expensive?", False, False, "question"),
    ("nonprice_food", 'Delicious food. They said "fair prices".', False, False, "quoted"),
    ("nonprice_mixed", "Friendly staff. Small portions. Fair prices but overpriced drinks.", True, True, ""),
    ("neutral_fee", "Is a service charge included?", False, False, ""),
    ("money_warning", "Please don't waste your money.", False, True, ""),
    ("money_quoted", 'They said "waste of money".', False, False, ""),
)
