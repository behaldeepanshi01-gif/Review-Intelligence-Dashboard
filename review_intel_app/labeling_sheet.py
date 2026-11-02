"""Prepare a private, blind human-labeling sample. Never invent human labels."""

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import random
import re

import engine as E


APP_DIR = Path(__file__).resolve().parent
PRIVATE_ROOT = APP_DIR / "data" / "private_evaluation"
LABEL_CHOICES = ("Praise", "Complaint", "Both", "Absent", "Unclear")
HEADERS = ["sample_id", "review_text", *E.THEME_LABELS.values(), "human_checked", "notes"]


def text_hash(text):
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rating_bucket(rating):
    return "low" if rating <= 2 else "middle" if rating == 3 else "high"


def choose_sample(data, count=48, seed=42):
    """Round-robin across location/rating groups, excluding duplicate passages.

    This is a balanced diagnostic sample, not a representative prevalence sample.
    No analyzer outputs influence the selection.
    """
    if not isinstance(count, int) or count < 1:
        raise ValueError("The sample size must be a positive whole number.")
    candidates = data.copy()
    candidates["_text_key"] = candidates["text"].astype(str).apply(
        lambda text: text_hash(" ".join(text.split()).casefold())
    )
    candidates = candidates.drop_duplicates("_text_key")
    if len(candidates) < count:
        raise ValueError("There are fewer distinct review passages than requested.")
    groups = {}
    for index, row in candidates.iterrows():
        key = (str(row["location"]), rating_bucket(row["rating"]))
        groups.setdefault(key, []).append(index)
    rng = random.Random(seed)
    for indices in groups.values():
        rng.shuffle(indices)
    selected = []
    while len(selected) < count:
        keys = sorted(key for key, indices in groups.items() if indices)
        rng.shuffle(keys)
        for key in keys:
            selected.append(groups[key].pop())
            if len(selected) == count:
                break
    rng.shuffle(selected)
    return candidates.loc[selected].drop(columns="_text_key").copy()


def remove_reviewer_identity(text, reviewer):
    """Remove an exact known display name; this is not full anonymization."""
    text, reviewer = str(text), str(reviewer).strip()
    if len(reviewer) > 1 and reviewer.casefold() not in {"guest", "anonymous", "nan"}:
        text = re.sub(r"(?<!\w)" + re.escape(reviewer) + r"(?!\w)",
                      "[reviewer removed]", text, flags=re.IGNORECASE)
    return text


def spreadsheet_text(text):
    """Keep review content from being interpreted as a spreadsheet formula."""
    text = str(text)
    if text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def private_file(path, encoding="utf-8"):
    """Create a new file without overwriting any earlier labeling work."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    return os.fdopen(descriptor, "w", encoding=encoding, newline="")


def prepare_sheet(source, batch, count=48, seed=42, private_root=PRIVATE_ROOT):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,60}", batch):
        raise ValueError("Use only lowercase letters, numbers, hyphens, and underscores for a batch.")
    destination = Path(private_root) / batch
    if destination.exists():
        raise ValueError("That batch already exists. Use a new batch name; nothing was overwritten.")
    source_fingerprint = file_hash(source)
    data = E.load_reviews(source)
    sample = choose_sample(data, count, seed)
    sheet_rows, snapshots = [], []
    for number, (_, row) in enumerate(sample.iterrows(), 1):
        sample_id = f"L{number:03d}"
        display_text = remove_reviewer_identity(row["text"], row["reviewer"])
        csv_text = spreadsheet_text(display_text)
        # Freeze predictions before a human sees the sheet. No reply text or names.
        prediction = E.tag_offline(display_text, int(row["rating"]))
        sheet_rows.append({
            "sample_id": sample_id, "review_text": csv_text,
            **{label: "" for label in E.THEME_LABELS.values()},
            "human_checked": "", "notes": "",
        })
        snapshots.append({
            "sample_id": sample_id,
            "original_text_sha256": text_hash(row["text"]),
            "display_text_sha256": text_hash(display_text),
            "csv_text_sha256": text_hash(csv_text),
            "source_rating": int(row["rating"]),
            "prediction": {
                "themes_pos": prediction["themes_pos"],
                "themes_neg": prediction["themes_neg"],
                "needs_review": prediction["needs_review"],
                "unclear_themes": sorted({
                    item["theme"] for item in prediction["tag_evidence"]
                    if item["polarity"] == "Needs review"
                }),
            },
        })
    # Detect source changes during preparation instead of silently mixing versions.
    if file_hash(source) != source_fingerprint:
        raise ValueError("The source file changed during preparation. Try again.")
    manifest = {
        "schema_version": 1, "status": "awaiting_human_labels",
        "rules_version": E.LOCAL_ANALYZER_VERSION,
        "source_sha256": source_fingerprint,
        "code_sha256": {
            name: file_hash(APP_DIR / name) for name in ("engine.py", "local_analyzer.py")
        },
        "selection": {
            "method": "round_robin_location_rating_without_duplicate_text",
            "seed": seed, "source_reviews": len(data), "sample_reviews": len(sample),
            "locations_represented": int(sample["location"].nunique()),
            "rating_buckets": {
                bucket: int(sample["rating"].apply(rating_bucket).eq(bucket).sum())
                for bucket in ("low", "middle", "high")
            },
            "not_representative_of_all_reviews": True,
        },
        "theme_keys": list(E.THEME_LABELS),
        "label_choices": list(LABEL_CHOICES),
        "reviews": snapshots,
    }
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination.mkdir(mode=0o700)
    with private_file(destination / "labeling_sheet.csv", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(sheet_rows)
    with private_file(destination / "frozen_predictions.json") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
    with private_file(destination / "START_HERE.txt") as handle:
        handle.write((APP_DIR / "LABELING_GUIDE.md").read_text(encoding="utf-8"))
    return destination, manifest["selection"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--batch", required=True, help="New private batch name. Never overwrites.")
    parser.add_argument("--count", type=int, default=48)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    _, summary = prepare_sheet(args.csv, args.batch, args.count, args.seed)
    # Only non-identifying aggregates may reach logs.
    print(f"Prepared {summary['sample_reviews']} blank-label reviews across "
          f"{summary['locations_represented']} locations. Human labels are still required.")
