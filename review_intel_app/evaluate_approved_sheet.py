"""Read-only analyzer evaluation; writes only a new, private result directory."""
import argparse
import csv
import hashlib
import html
import json
from datetime import datetime, timezone
from pathlib import Path
import unicodedata

import engine as E


def score(label, praise, complaint):
    """Return praise/complaint (correct, missed, unsupported); exclude unclear."""
    label = label.strip().lower()
    if label == "unclear":
        return None
    gold = {"pos": (True, False), "neg": (False, True),
            "mixed": (True, True), "none": (False, False)}[label]
    return [(int(g and p), int(g and not p), int(p and not g))
            for g, p in zip(gold, (praise, complaint))]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("Duplicate columns")
        return list(reader)


def evaluate(sheet, source):
    app = Path(__file__).resolve().parent
    inputs = [sheet, source, app / "engine.py", app / "app.py",
              app / "local_analyzer.py", Path(__file__).resolve()]
    hashes = {str(p): digest(p) for p in inputs}
    rows = read_csv(sheet)
    original_rows = read_csv(source)
    original = {r["review_id"]: r for r in original_rows}
    assert len(original) == len(original_rows)
    assert len(rows) == 61
    assert {r["sample_id"] for r in rows} == {f"MC{i:03}" for i in range(1, 62)}
    assert len({r["review_id"] for r in rows}) == 61
    chat_approved = {"MC001", "MC002", "MC003", "MC004", "MC005"}
    assert sum(r["human_checked"].strip().lower() == "yes" for r in rows) == 56
    assert all(r["sample_id"] in chat_approved or
               r["human_checked"].strip().lower() == "yes" for r in rows)
    normalize = lambda s: "".join(
        c for c in unicodedata.normalize("NFKC", s).casefold() if c.isalnum())
    formatting, fingerprints = [], []
    stats = {k: [[0, 0, 0], [0, 0, 0]] for k in E.THEMES}
    support = {k: dict(pos=0, neg=0, mixed=0, none=0, unclear=0) for k in E.THEMES}
    totals = [[0, 0, 0], [0, 0, 0]]
    errors, predictions = [], []
    unclear = mixed = both = warnings = 0
    for r in rows:
        old = original[r["review_id"]]
        assert float(old["rating"]) == float(r["rating"])
        assert old["date"] == r["date"]
        assert normalize(old["text"]) == normalize(r["review_text"])
        if " ".join(old["text"].split()) != " ".join(r["review_text"].split()):
            formatting.append(r["sample_id"])
        p = E.tag_offline(r["review_text"], int(r["rating"]))
        warnings += bool(p["needs_review"])
        predictions.append([r["sample_id"], r["review_id"],
                            ";".join(p["themes_pos"]), ";".join(p["themes_neg"])])
        fingerprints.append(dict(sample_id=r["sample_id"],
                                 text_sha256=hashlib.sha256(r["review_text"].encode()).hexdigest(),
                                 needs_review=p["needs_review"]))
        for key, label in E.THEME_LABELS.items():
            value = r[label].strip().lower()
            positive, negative = key in p["themes_pos"], key in p["themes_neg"]
            result = score(value, positive, negative)  # Reject blanks/invalid labels.
            support[key][value] += 1
            if result is None:
                unclear += 1
                continue
            if value == "mixed":
                mixed += 1
                both += positive and negative
            for side, counts in enumerate(result):
                for metric, n in enumerate(counts):
                    stats[key][side][metric] += n
                    totals[side][metric] += n
                for metric, name in [(1, "missed"), (2, "unsupported")]:
                    if counts[metric]:
                        errors.append([r["sample_id"], key,
                                       ["praise", "complaint"][side], name])
    combined = [sum(pair) for pair in zip(*totals)]
    summary = dict(rules_version=E.LOCAL_ANALYZER_VERSION, praise=totals[0],
                   complaint=totals[1], combined=combined, per_theme=stats,
                   support=support, unclear=unclear, mixed=mixed, mixed_both=both,
                   needs_review=warnings, count_order=["correct", "missed", "unsupported"])
    lines = [
        "# Current Replit app evaluation",
        "Tuning-set evidence only. Labels began as Claude AI drafts and were user-approved.",
        "56 rows have CSV approval; MC001–MC005 were approved separately in chat.",
        "Snapshot saved after labeling; not frozen before labeling and not a held-out test.",
        "The user-reported official source export has not been independently authenticated.",
        "No claims are made about a separate laptop installation or restaurant performance.",
        f"Rules: {E.LOCAL_ANALYZER_VERSION}. Reviews: 61.",
        f"Mixed both sides: {both}/{mixed}. Unclear excluded: {unclear}. Needs review: {warnings}/61.",
        "Evaluated sheet text. Formatting-only source differences: " + ", ".join(formatting),
        "Counts below: correct / missed / unsupported.",
        "| Theme | Praise | Complaint |", "|---|---|---|"]
    for key, label in E.THEME_LABELS.items():
        lines.append(f"| {label} | {' / '.join(map(str, stats[key][0]))} | "
                     f"{' / '.join(map(str, stats[key][1]))} |")
    lines += [
        f"Overall praise: {totals[0]}; complaint: {totals[1]}; combined: {combined}.",
        "## Comparison with the earlier retyped analyzer",
        "Earlier retyped engine (3).py: praise 80/42/14, complaint 42/47/13, combined 122/89/27.",
        "Current minus earlier praise: " + str([a-b for a,b in zip(totals[0], [80,42,14])]),
        "Current minus earlier complaint: " + str([a-b for a,b in zip(totals[1], [42,47,13])]),
        "Current minus earlier combined: " + str([a-b for a,b in zip(combined, [122,89,27])]),
        "Mixed both sides: earlier 0/29. These are different analyzers, not changes made here.",
        "## Limits and coverage",
        "Sparse themes, particularly catering, takeout, cleanliness and consistency, have few "
        "examples. This selected sample is not a random population estimate. User approval "
        "does not establish independently adjudicated ground truth.",
        "Theme support (mixed contributes to both praise and complaint):",
        "| Theme | Praise only | Complaint only | Mixed | Absent | Unclear |",
        "|---|---|---|---|---|---|"]
    for key, label in E.THEME_LABELS.items():
        lines.append("| " + label + " | " + " | ".join(
            str(support[key][s]) for s in ["pos", "neg", "mixed", "none", "unclear"]) + " |")
    lines += [
        "## Reproduction",
        "Run from the workspace, quoting input paths: python -B "
        "review_intel_app/evaluate_approved_sheet.py --sheet <sheet.csv> --source <source.csv>.",
        "Scoring tests: cd review_intel_app && python -B -m unittest test_evaluation_scoring -v",
        "The manifest records exact source, code, test and output fingerprints. Existing "
        "uploads, prior evaluations, manager overrides and action history are not modified.",
        "Next: preserve this baseline for focused price improvements. Use newly manager-labeled "
        "unused reviews for an independent test with rules frozen.",
        "## Every error", "| Sample | Theme | Side | Error |", "|---|---|---|---|"]
    lines += ["| " + " | ".join(e) + " |" for e in errors]
    assert all(digest(p) == hashes[str(p)] for p in inputs)
    out = app / "data/private_evaluation" / (
        "current_app_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    out.mkdir(parents=True, exist_ok=False)
    for name, header, data in [
        ("predictions.csv", ["sample_id", "review_id", "praise_tags", "complaint_tags"], predictions),
        ("errors.csv", ["sample_id", "theme", "side", "error"], errors)]:
        with (out / name).open("x", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(data)
    (out / "report.md").write_text("\n\n".join(lines), encoding="utf-8")
    # Self-contained, readable HTML document with real tables and no external assets.
    fragments, in_table = [], False
    for line in lines:
        if line.startswith("|"):
            if line.startswith("|---"):
                continue
            if not in_table:
                fragments.append("<table>")
                in_table = True
            fragments.append("<tr>" + "".join("<td>" + html.escape(c.strip()) + "</td>"
                                             for c in line.strip("|").split("|")) + "</tr>")
        else:
            if in_table:
                fragments.append("</table>")
                in_table = False
            tag = "h1" if line.startswith("# ") else "h2" if line.startswith("## ") else "p"
            fragments.append(f"<{tag}>" + html.escape(line.lstrip("# ")) + f"</{tag}>")
    if in_table:
        fragments.append("</table>")
    (out / "report.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Private current-app evaluation</title>'
        '<style>body{max-width:1100px;margin:40px auto;padding:20px;font:16px system-ui}'
        'table{border-collapse:collapse;width:100%;margin:20px 0}'
        'td{border:1px solid #ccc;padding:8px}tr:first-child{font-weight:bold}'
        'p{line-height:1.6}</style>' + "".join(fragments), encoding="utf-8")
    (out / "scores.json").write_text(json.dumps(summary, indent=2))
    (out / "text_fingerprints.json").write_text(json.dumps(fingerprints, indent=2))
    hashes[str(app / "test_evaluation_scoring.py")] = digest(app / "test_evaluation_scoring.py")
    manifest = dict(input_sha256=hashes, rules_version=E.LOCAL_ANALYZER_VERSION,
                    created_utc=datetime.now(timezone.utc).isoformat(),
                    timing="After labeling; not held-out", output_sha256={
                        p.name: digest(p) for p in out.iterdir()})
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    for name, fingerprint in manifest["output_sha256"].items():
        assert digest(out / name) == fingerprint
    print(json.dumps({"output": str(out), "combined": combined, "error_rows": len(errors)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sheet", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    evaluate(args.sheet.resolve(), args.source.resolve())
