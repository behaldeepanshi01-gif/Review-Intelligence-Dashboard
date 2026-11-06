"""Prepare a blind human-only batch; never score or invent reference labels."""
import csv
import html
import json
import random
import unicodedata
from pathlib import Path

import engine as E
from labeling_sheet import (
    APP_DIR, PRIVATE_ROOT, HEADERS, file_hash, private_file,
    remove_reviewer_identity, spreadsheet_text, text_hash,
)

EXPECTED = {
    "engine.py": "c239d262fd38050781b293e9294f4a7873f0c6ae6d396f28eeba44a12f6920ff",
    "local_analyzer.py": "d6396a7253644cf6322d64f7da38e6f48ab0439e4982e9b18ed009f292fdbfbd",
    "price_rules.py": "633d70e5d29d0c10b7eb3aa7f903de64a2353ee5a3424cb763ce040ba0d5bc22",
}


def normalize(text):
    return "".join(c for c in unicodedata.normalize("NFKC", text).casefold()
                   if c.isalnum())


def read_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def eligible_rows(source, tuning, previous_hashes=()):
    ids = {r["review_id"] for r in tuning}
    texts = {normalize(r["review_text"]) for r in tuning}
    seen = set()
    result = []
    for row in source:
        key = normalize(row["text"])
        if (not key or row["review_id"] in ids or key in texts or key in seen
                or text_hash(row["text"]) in previous_hashes):
            continue
        seen.add(key)
        result.append(row)
    return result


def prepare(source, tuning, destination):
    inputs = {"source": source, "tuning": tuning,
              **{name: APP_DIR / name for name in
                 (*EXPECTED, "app.py", "labeling_sheet.py", "prepare_heldout.py")}}
    hashes = {key: file_hash(path) for key, path in inputs.items()}
    if any(hashes[key] != value for key, value in EXPECTED.items()):
        raise ValueError("Actual analyzer differs from verified handoff; stop.")
    tuning_rows = read_rows(tuning)
    if len(tuning_rows) != 61 or len({r["review_id"] for r in tuning_rows}) != 61:
        raise ValueError("Expected all 61 unique tuning reviews.")
    if destination.exists():
        raise ValueError("Batch already exists; inspect and reuse, never overwrite.")
    previous = set()
    for path in PRIVATE_ROOT.rglob("frozen_predictions.json"):
        data = json.loads(path.read_text())
        if (data.get("batch_kind") == "unused_manager_heldout"
                and data.get("inputs_sha256") == hashes):
            raise ValueError(f"Matching batch already exists: {path.parent.name}")
        previous.update(r["original_text_sha256"] for r in data.get("reviews", []))
    source_rows = read_rows(source)
    # Exclude normalized variants of previously sampled source passages too.
    previously_used = {normalize(r["text"]) for r in source_rows
                       if text_hash(r["text"]) in previous}
    candidates = [r for r in eligible_rows(source_rows, tuning_rows, previous)
                  if normalize(r["text"]) not in previously_used]
    rng = random.Random(20261106)
    rng.shuffle(candidates)  # No analyzer or rating information used for selection.
    selected = candidates[:30]
    if not selected:
        raise ValueError("No unused passages remain.")
    sheet, frozen = [], []
    for number, row in enumerate(selected, 1):
        sid = f"H{number:03d}"
        text = remove_reviewer_identity(row["text"], row["reviewer"])
        displayed = spreadsheet_text(text)
        prediction = E.tag_offline(text, int(float(row["rating"])))
        sheet.append(dict(sample_id=sid, review_text=displayed,
                          **{label: "" for label in E.THEME_LABELS.values()},
                          human_checked="", notes=""))
        frozen.append(dict(
            sample_id=sid, review_id=row["review_id"],
            original_text_sha256=text_hash(row["text"]),
            normalized_text_sha256=text_hash(normalize(row["text"])),
            display_text_sha256=text_hash(text), csv_text_sha256=text_hash(displayed),
            source_rating=int(float(row["rating"])),
            prediction={key: prediction[key] for key in
                        ("themes_pos", "themes_neg", "needs_review")},
        ))
    guide = (APP_DIR / "LABELING_GUIDE.md").read_text()
    guide = guide.replace("small, balanced diagnostic sample", "small diagnostic sample")
    guide = guide.replace(
        "The sample covers location and rating groups, not every theme.",
        "The sample is drawn from unused passages, not chosen to cover every theme.")
    guide = guide.replace("deliberately balanced, small sample", "small selected sample")
    guide += """

## This unused held-out batch

Selection is a seeded shuffle of unused, distinct passages, not theme or rating
balancing. The 61 tuning IDs and normalized duplicate texts are excluded, as are
passages sampled in earlier blind batches. No analyzer output selected the rows.

Apply these approved definitions:
- Consistency requires an explicit comparison across visits or orders.
- Catering requires catering or an organized event with event-specific service,
  not simply dinner with friends.
- Takeout includes explicitly evaluated pickup, delivery, packaging, accuracy,
  or off-premise food condition. Food and Takeout may both apply without guessing
  the cause.
- Both means praise and criticism of the SAME theme. Neutral or ambiguous wording
  is Unclear; Absent means the theme is not discussed.

Only you or a restaurant manager may label this sheet. Do not use AI to fill it.
Return the completed CSV and explicitly state that you personally reviewed and
approve this batch for scoring. Earlier tuning-set approvals do not apply.
No scoring occurs until that approval arrives. The frozen rule implementation,
source files, and each sheet text must still match before a single scoring run.
Changed rules invalidate the batch for those rules; never silently refresh its
predictions. No accuracy claim is available now.
"""
    if any(file_hash(path) != hashes[key] for key, path in inputs.items()):
        raise ValueError("Inputs changed during freeze.")
    destination.mkdir(mode=0o700)
    with private_file(destination / "labeling_sheet.csv", "utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(sheet)
    with private_file(destination / "labeling_guide.html") as handle:
        handle.write('<!doctype html><meta charset="utf-8"><title>Private labeling guide</title>'
                     '<style>body{max-width:850px;margin:40px auto;padding:24px;'
                     'font:16px system-ui}pre{white-space:pre-wrap}</style><pre>'
                     + html.escape(guide) + '</pre>')
    manifest = dict(
        schema_version=1, batch_kind="unused_manager_heldout",
        status="awaiting_human_labels_and_explicit_approval",
        rules_version=E.LOCAL_ANALYZER_VERSION, inputs_sha256=hashes,
        selection=dict(method="seeded_shuffle_unused_distinct_passages",
                       seed=20261106, eligible_count=len(candidates), selected_count=len(selected)),
        theme_labels=E.THEME_LABELS, reviews=frozen,
        deliverable_sha256={name: file_hash(destination / name) for name in
                            ("labeling_sheet.csv", "labeling_guide.html")},
    )
    with private_file(destination / "frozen_predictions.json") as handle:
        json.dump(manifest, handle, indent=2)
    print(f"Eligible unused passages: {len(candidates)}; frozen blank rows: {len(selected)}.")


if __name__ == "__main__":
    root = APP_DIR.parent
    prepare(
        root / "attached_assets/mumbai_central_reviews_1793677255749.csv",
        root / "attached_assets/mumbai_central_labeling_sheet_(15)_1793731218764.csv",
        PRIVATE_ROOT / "heldout_money_waste_20261106",
    )
