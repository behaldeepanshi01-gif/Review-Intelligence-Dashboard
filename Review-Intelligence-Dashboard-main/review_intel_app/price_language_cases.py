"""Invented specifications, never manager labels or held-out examples.

The final field names a remaining gap, NOT a desired outcome. Question,
rhetorical and reported/quoted cases were resolved in the approved separate
price-context cycle. The separate punctuation cycle resolved the remaining
negation/hedge cases without changing their desired assertions.
"""

# id, text, desired praise, desired complaint, known frozen-rule gap
CASES = (
    ("question_fair", "Are the prices fair?", False, False, ""),
    ("question_expensive", "Is it expensive?", False, False, ""),
    ("question_negative", "Isn't it affordable?", False, False, ""),
    ("question_fragment", "Reasonable prices?", False, False, ""),
    ("question_worth", "Was it worth the money?", False, False, ""),
    ("rhetorical_fair", "Who would call these prices fair?", False, False, ""),
    ("rhetorical_cheap", "Cheap prices, really?", False, False, ""),
    ("rhetorical_as_if", "As if these prices were fair!", False, False, ""),
    ("rhetorical_right", "Yeah right, affordable prices!", False, False, ""),
    ("reported_fair", "They said the prices were fair.", False, False, ""),
    ("reported_expensive", "I heard it was expensive.", False, False, ""),
    ("quoted_positive", 'The sign says "affordable prices".', False, False, ""),
    ("quoted_negative", 'The word “overpriced” appeared in the flyer.', False, False, ""),
    ("quoted_single", "The brochure calls the prices 'reasonable'.", False, False, ""),
    ("quoted_fragment", '"Fair prices."', False, False, ""),
    ("negation_comma", "The prices are not, in my view, reasonable.", False, True, ""),
    ("negation_semicolon", "Affordable prices; not.", False, False, ""),
    ("negation_dash", "Prices are not — reasonable.", False, True, ""),
    ("negation_parentheses", "Prices are not (at all) reasonable.", False, True, ""),
    ("negation_smart", "Prices aren’t reasonable.", False, True, ""),
    ("negation_period", "Prices are reasonable. Not expensive.", True, False, ""),
    ("negation_question", "Not expensive?", False, False, ""),
    ("hedge_comma", "Maybe, the prices are fair.", False, False, ""),
    ("hedge_colon", "Maybe: the prices are fair.", False, False, ""),
    ("explicit_praise", "Prices are fair!", True, False, ""),
    ("explicit_complaint", "Prices are unreasonable!", False, True, ""),
    ("explicit_mixed", "Fair lunch prices; overpriced dinner.", True, True, ""),
    ("reported_then_praise", 'They said "expensive". My prices were fair.', True, False, ""),
    ("reported_then_complaint", 'The sign says "cheap". My meal was overpriced.', False, True, ""),
    ("question_then_praise", "Expensive? My prices were fair.", True, False, ""),
    ("question_then_complaint", "Affordable? My meal was overpriced.", False, True, ""),
    ("nonprice_staff", "Friendly staff. Are the prices fair?", False, False, ""),
    ("nonprice_portions", "Generous portions. Is it expensive?", False, False, ""),
    ("nonprice_food", 'Delicious food. They said "fair prices".', False, False, ""),
    ("nonprice_mixed", "Friendly staff. Small portions. Fair prices but overpriced drinks.", True, True, ""),
    ("neutral_fee", "Is a service charge included?", False, False, ""),
    ("money_warning", "Please don't waste your money.", False, True, ""),
    ("money_quoted", 'They said "waste of money".', False, False, ""),
)
