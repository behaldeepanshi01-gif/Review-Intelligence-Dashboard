"""Score an explicitly approved blind batch once, using frozen predictions only."""
import argparse
import csv
import html
import json
from pathlib import Path

import engine as E
from evaluate_approved_sheet import score
from labeling_sheet import APP_DIR, HEADERS, file_hash, private_file, text_hash

CHOICES = {"praise": "pos", "complaint": "neg", "both": "mixed",
           "absent": "none", "unclear": "unclear"}


def read_sheet(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != HEADERS:
            raise ValueError("Sheet headings differ from the blind sheet.")
        return list(reader)


def validate_rows(rows, frozen, approved_ids):
    ids = [r["sample_id"] for r in rows]
    expected = {r["sample_id"]: r for r in frozen}
    if len(ids) != len(set(ids)) or set(ids) != set(expected):
        raise ValueError("Sample IDs missing, added, or duplicated.")
    if set(approved_ids) != set(expected):
        raise ValueError("Explicit approval must cover every sample.")
    for row in rows:
        if text_hash(row["review_text"]) != expected[row["sample_id"]]["csv_text_sha256"]:
            raise ValueError("Passage text changed.")
        for theme in E.THEME_LABELS.values():
            if row[theme].strip().lower() not in CHOICES:
                raise ValueError("Blank or invalid theme label.")


def evaluate(batch, sheet, source, tuning, approval):
    manifest_path = batch / "frozen_predictions.json"
    manifest = json.loads(manifest_path.read_text())
    approval_record = json.loads(approval.read_text())
    if (approval_record.get("explicitly_approved") is not True
            or approval_record.get("sheet_sha256") != file_hash(sheet)
            or not approval_record.get("approval_statement")
            or not approval_record.get("labeling_statement")):
        raise ValueError("Missing explicit approval tied to this exact sheet.")
    inputs = {"source": source, "tuning": tuning,
              **{k: APP_DIR / k for k in manifest["inputs_sha256"]
                 if k not in ("source", "tuning")}}
    def verify():
        if E.LOCAL_ANALYZER_VERSION != manifest["rules_version"]:
            raise ValueError("Rules changed: evaluation invalid.")
        for key, path in inputs.items():
            if file_hash(path) != manifest["inputs_sha256"][key]:
                raise ValueError(f"Frozen input changed ({key}): evaluation invalid.")
        for name, digest in manifest["deliverable_sha256"].items():
            if file_hash(batch / name) != digest:
                raise ValueError("Frozen deliverable changed.")
    verify()
    rows = read_sheet(sheet)
    validate_rows(rows, manifest["reviews"], approval_record.get("sample_ids", []))
    fixed = {r["sample_id"]: r["prediction"] for r in manifest["reviews"]}
    result = batch / "scored_once"
    # Atomic no-overwrite gate. Failed attempts are retained for explicit inspection.
    result.mkdir(mode=0o700)
    stats = {}
    errors = []
    for key, name in E.THEME_LABELS.items():
        support = dict.fromkeys(("pos", "neg", "mixed", "none", "unclear"), 0)
        sides = [[0, 0, 0], [0, 0, 0]]
        both = unclear_flagged = 0
        for row in rows:
            label = CHOICES[row[name].strip().lower()]
            support[label] += 1
            p = fixed[row["sample_id"]]
            positive, negative = key in p["themes_pos"], key in p["themes_neg"]
            both += int(label == "mixed" and positive and negative)
            unclear_flagged += int(label == "unclear" and bool(p["needs_review"]))
            counts = score(label, positive, negative)
            if counts is None:
                continue
            for side, values in enumerate(counts):
                sides[side] = [a + b for a, b in zip(sides[side], values)]
                for i, kind in ((1, "missed"), (2, "unsupported")):
                    if values[i]:
                        errors.append(dict(sample_id=row["sample_id"], theme=name,
                                           side=("praise", "complaint")[side], error=kind))
        stats[key] = dict(label=name, praise=sides[0], complaint=sides[1],
                          support=support, mixed_both=both,
                          unclear_with_review_warning=unclear_flagged)
    summary = dict(
        rules_version=manifest["rules_version"], reviews=len(rows),
        count_order=["correct", "missed", "unsupported"], per_theme=stats,
        needs_review=sum(bool(p["needs_review"]) for p in fixed.values()),
        mixed=sum(v["support"]["mixed"] for v in stats.values()),
        mixed_both=sum(v["mixed_both"] for v in stats.values()),
        unclear_excluded=sum(v["support"]["unclear"] for v in stats.values()),
        errors=len(errors),
    )
    for side in ("praise", "complaint"):
        summary[side] = [sum(v[side][i] for v in stats.values()) for i in range(3)]
    lines = [
        "# Private frozen-batch evaluation",
        f"Rules: {summary['rules_version']}. Passages: {len(rows)}.",
        "Predictions frozen before labeling; no predictions regenerated and no rules tuned.",
        "Provenance: the uploaded file is named Claude draft and its notes identify AI "
        "involvement. All CSV human_checked fields are blank. The user explicitly stated "
        "manager approval and personally labeling H001–H030 blind to analyzer predictions. "
        "Those chat statements are retained as batch-specific approval, not inferred CSV "
        "checks. AI-draft provenance is unresolved; this is NOT certified independent "
        "human-only ground truth. No population accuracy claim is justified.",
        "Counts below are correct / missed / unsupported; Unclear cells are excluded.",
        "| Theme | Praise | Complaint | Both captured / labeled | Unclear excluded |",
        "|---|---|---|---|---|",
    ]
    for v in stats.values():
        lines.append(f"| {v['label']} | {' / '.join(map(str,v['praise']))} | "
                     f"{' / '.join(map(str,v['complaint']))} | "
                     f"{v['mixed_both']} / {v['support']['mixed']} | {v['support']['unclear']} |")
    lines += [
        f"Overall praise: {summary['praise']}; complaint: {summary['complaint']}.",
        f"Mixed both sides captured: {summary['mixed_both']}/{summary['mixed']}. "
        f"Unclear cells excluded: {summary['unclear_excluded']}. "
        f"Review-needed passages: {summary['needs_review']}/{len(rows)}.",
        "Review-needed is an analyzer warning count, not measured warning accuracy. "
        "Unclear-with-warning counts in scores.json refer to a review-wide flag, not "
        "a theme-specific flag.",
        "Small seeded sample of 30 from 141 eligible passages; rare themes may have "
        "insufficient evidence. Both contributes to praise and complaint support. "
        "Support counts are in scores.json. Earlier tuning-set approvals were not reused.",
        "Next: resolve reference-label provenance before making independent-validation "
        "claims. This batch is now evaluated; do not reuse it as an untouched test after tuning.",
    ]
    verify()
    artifacts = {"scores.json": summary, "errors.json": errors,
                 "approval.json": approval_record}
    for name, value in artifacts.items():
        with private_file(result / name) as handle:
            json.dump(value, handle, indent=2)
    with private_file(result / "report.md") as handle:
        handle.write("\n\n".join(lines))
    with private_file(result / "report.html") as handle:
        handle.write('<!doctype html><meta charset="utf-8"><title>Private evaluation</title>'
                     '<style>body{font:16px system-ui;max-width:1100px;margin:30px auto;'
                     'padding:20px}pre{white-space:pre-wrap}</style><pre>'
                     + html.escape("\n\n".join(lines)) + "</pre>")
    # Preserve submitted bytes, including blank checkboxes and AI provenance notes.
    with private_file(result / "submitted_labels.csv") as handle:
        handle.buffer.write(sheet.read_bytes())
    with private_file(result / "verification.json") as handle:
        json.dump(dict(
            frozen_manifest_sha256=file_hash(manifest_path),
            submitted_sheet_sha256=file_hash(sheet),
            scorer_sha256=file_hash(Path(__file__)),
            scoring_primitive_sha256=file_hash(APP_DIR / "evaluate_approved_sheet.py"),
            inputs_sha256=manifest["inputs_sha256"],
            outputs_sha256={p.name: file_hash(p) for p in result.iterdir()
                            if p.name != "verification.json"},
        ), handle, indent=2)
    print(json.dumps({k: v for k, v in summary.items() if k != "per_theme"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("batch", "sheet", "source", "tuning", "approval"):
        parser.add_argument("--" + name, type=Path, required=True)
    evaluate(**vars(parser.parse_args()))
