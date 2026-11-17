"""
Generate a SYNTHETIC review dataset for a 4-location Indian restaurant group.

Every review here is fake. Names, staff and text are invented. Use it to build,
test and demo the tool. Swap in real reviews later (same CSV columns).

Built-in patterns, so the dashboard has real signals to find:
  - Upscale Dining Room: loved for ambiance and staff, but slow service rises
    in the last ~2 months.
  - Neighborhood Bistro A: strong catering praise, recurring "too mild /
    under-seasoned" complaints.
  - Neighborhood Bistro B: loyal regulars, but "not the same anymore"
    consistency complaints rise in the last ~3 months.
  - Food Hall Express: friendly staff, frequent small-portion / value complaints.

Run:  python generate_data.py
Out:  data/sample_reviews.csv
"""

import csv
import os
import random
from datetime import date, timedelta

random.seed(42)

TODAY = date(2026, 10, 31)
START = TODAY - timedelta(days=365)

LOCATIONS = {
    "Upscale Dining Room": {"n": 260, "base_rating": 4.5},
    "Neighborhood Bistro A": {"n": 300, "base_rating": 4.3},
    "Neighborhood Bistro B": {"n": 220, "base_rating": 4.4},
    "Food Hall Express": {"n": 150, "base_rating": 4.2},
}

STAFF = ["Asha", "Rohan", "Meera", "Kabir", "Nisha", "Arjun", "Tara", "Dev"]
STAFF_BY_LOC = {
    "Upscale Dining Room": ["Asha", "Rohan", "Meera"],
    "Neighborhood Bistro A": ["Kabir", "Nisha"],
    "Neighborhood Bistro B": ["Arjun", "Tara"],
    "Food Hall Express": ["Dev"],
}

DISHES = ["butter chicken", "chicken tikka masala", "lamb rogan josh", "dal makhani",
          "palak paneer", "baingan bharta", "chicken biryani", "goat curry",
          "malai kofta", "tandoori chicken", "garlic naan", "momos", "pani puri",
          "fish curry", "chana masala", "mango lassi"]

FIRST = ["Sam", "Priya", "Jordan", "Alex", "Neha", "Chris", "Maria", "Raj", "Emily",
         "Omar", "Kate", "Vikas", "Lena", "Mike", "Sana", "Tom", "Ana", "Ben", "Isha", "Leo"]

# Sentence banks per theme: (positive, negative)
BANK = {
    "food_flavor": (
        ["The {dish} was rich and full of flavor.",
         "Loved the {dish}, easily one of the best I have had.",
         "The {dish} was perfectly cooked and tasted fresh."],
        ["The {dish} was just okay, nothing special.",
         "The {dish} was dry and a bit disappointing."],
    ),
    "seasoning": (
        ["Spice level was spot on, they asked how hot we wanted it.",
         "Great balance of spices in every dish."],
        ["Food was too mild, it needed more spice and seasoning.",
         "Flavors felt diluted and bland for Indian food.",
         "Even when we asked for spicy, the {dish} had barely any heat."],
    ),
    "consistency": (
        ["Every visit the food is just as good as the last.",
         "Consistently great, we come back every month."],
        ["We have been coming for years but the food is not the same anymore.",
         "The {dish} used to be amazing, this time it tasted different.",
         "Quality has gone down compared to our last few visits."],
    ),
    "service_speed": (
        ["Food came out quickly even on a busy night.",
         "Service was fast and smooth."],
        ["Service was really slow, we waited almost an hour for our mains.",
         "It took forever to get our order and the check.",
         "Long wait between courses, the kitchen seemed overwhelmed."],
    ),
    "staff": (
        ["{staff} was so warm and attentive, made our night.",
         "Our server {staff} gave great recommendations.",
         "Shout out to {staff}, amazing hospitality."],
        ["Our server seemed distracted and hard to flag down.",
         "Staff felt rushed and not very friendly."],
    ),
    "portion_value": (
        ["Generous portions, we took leftovers home.",
         "Great value for the price."],
        ["Portions were small for the price, barely any chicken in the bowl.",
         "Paid over $20 for a bowl and a drink, not worth it.",
         "Very stingy with the meat, mostly rice."],
    ),
    "price": (
        ["A bit pricey but worth it for the experience."],
        ["Prices are on the high side for what you get."],
    ),
    "ambiance": (
        ["The decor is beautiful, it feels like a special night out.",
         "Loved the train station theme, so unique.",
         "Cozy and calm atmosphere, great for a date."],
        ["It was very loud, hard to have a conversation."],
    ),
    "cleanliness": (
        ["Very clean restaurant and restrooms."],
        ["Tables were sticky and the restroom needed attention."],
    ),
    "catering": (
        ["They catered our wedding for 250 guests and everyone loved it.",
         "Used them for an office event, food and setup were excellent.",
         "Catering for our family party was perfect and on time."],
        ["Catering order arrived late for our event."],
    ),
    "wait_reservation": (
        ["Got a table quickly even without a reservation."],
        ["Even with a reservation we waited 30 minutes to be seated."],
    ),
    "takeout": (
        ["Takeout was packed well and still hot at home."],
        ["Takeout order was missing an item."],
    ),
}

# Per-location theme weights: theme -> (probability mentioned, prob positive)
PROFILE = {
    "Upscale Dining Room": {
        "ambiance": (0.55, 0.95), "staff": (0.55, 0.92), "food_flavor": (0.6, 0.85),
        "service_speed": (0.25, 0.6), "price": (0.2, 0.5), "seasoning": (0.1, 0.8),
        "wait_reservation": (0.12, 0.5), "cleanliness": (0.08, 0.9),
    },
    "Neighborhood Bistro A": {
        "food_flavor": (0.5, 0.65), "seasoning": (0.35, 0.2), "catering": (0.25, 0.92),
        "staff": (0.4, 0.88), "ambiance": (0.25, 0.85), "cleanliness": (0.12, 0.85),
        "takeout": (0.12, 0.7), "consistency": (0.08, 0.6),
    },
    "Neighborhood Bistro B": {
        "food_flavor": (0.55, 0.8), "consistency": (0.2, 0.75), "staff": (0.45, 0.9),
        "portion_value": (0.25, 0.85), "cleanliness": (0.2, 0.9), "ambiance": (0.2, 0.85),
        "takeout": (0.12, 0.8),
    },
    "Food Hall Express": {
        "portion_value": (0.5, 0.35), "food_flavor": (0.5, 0.7), "staff": (0.35, 0.9),
        "price": (0.2, 0.3), "service_speed": (0.2, 0.8), "seasoning": (0.1, 0.6),
    },
}


def random_date():
    return START + timedelta(days=random.randint(0, 365))


def adjust_for_trends(loc, d, profile):
    """Inject time-based patterns so early-warning alerts have something to catch."""
    p = {k: list(v) for k, v in profile.items()}
    days_ago = (TODAY - d).days
    if loc == "Upscale Dining Room" and days_ago <= 60:
        p["service_speed"] = [0.55, 0.15]  # slow service spike
    if loc == "Neighborhood Bistro B" and days_ago <= 90:
        p["consistency"] = [0.45, 0.1]     # quality drift
    return p


def make_review(loc, idx):
    d = random_date()
    profile = adjust_for_trends(loc, d, PROFILE[loc])
    sentences, pos, neg = [], 0, 0
    for theme, (p_mention, p_pos) in profile.items():
        if random.random() < p_mention:
            positive = random.random() < p_pos
            options = BANK[theme][0] if positive else BANK[theme][1]
            s = random.choice(options).format(
                dish=random.choice(DISHES),
                staff=random.choice(STAFF_BY_LOC[loc]))
            sentences.append(s)
            pos += positive
            neg += not positive
    if not sentences:
        sentences.append(random.choice(BANK["food_flavor"][0]).format(dish=random.choice(DISHES)))
        pos += 1
    random.shuffle(sentences)

    # Rating driven by the balance of positive vs negative points
    base = LOCATIONS[loc]["base_rating"]
    score = base + 0.45 * pos - 1.1 * neg + random.gauss(0, 0.4)
    rating = int(max(1, min(5, round(score))))

    return {
        "review_id": f"{''.join(w[0] for w in loc.split()).upper()}-{idx:04d}",
        "location": loc,
        "date": d.isoformat(),
        "rating": rating,
        "reviewer": f"{random.choice(FIRST)} {random.choice('ABCDEFGHJKLMNPRSTW')}.",
        "text": " ".join(sentences),
        "source": "synthetic",
    }


def main():
    os.makedirs("data", exist_ok=True)
    rows = []
    for loc, cfg in LOCATIONS.items():
        rows += [make_review(loc, i) for i in range(cfg["n"])]
    rows.sort(key=lambda r: r["date"])
    path = os.path.join("data", "sample_reviews.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} synthetic reviews to {path}")


if __name__ == "__main__":
    main()
