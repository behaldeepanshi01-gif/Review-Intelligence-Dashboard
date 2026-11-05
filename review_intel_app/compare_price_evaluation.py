"""Compare two frozen private runs. Never includes review text or names."""
import argparse
import csv
import hashlib
import html
import json
from pathlib import Path


def load_rows(path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare(before, after):
    b = json.loads((before / "scores.json").read_text())
    a = json.loads((after / "scores.json").read_text())
    bm = json.loads((before / "manifest.json").read_text())
    am = json.loads((after / "manifest.json").read_text())
    # No comparison across different batches, source snapshots or evaluated text.
    for name in ("mumbai_central_labeling_sheet_(15)_1793731218764.csv",
                 "mumbai_central_reviews_1793677255749.csv"):
        old = next(v for k, v in bm["input_sha256"].items() if Path(k).name == name)
        new = next(v for k, v in am["input_sha256"].items() if Path(k).name == name)
        assert old == new, "Source/batch fingerprint mismatch"
    bf = json.loads((before / "text_fingerprints.json").read_text())
    af = json.loads((after / "text_fingerprints.json").read_text())
    assert [(r["sample_id"], r["text_sha256"]) for r in bf] == [
        (r["sample_id"], r["text_sha256"]) for r in af]
    bp = {r["sample_id"]: r for r in load_rows(before / "predictions.csv")}
    ap = {r["sample_id"]: r for r in load_rows(after / "predictions.csv")}
    assert bp.keys() == ap.keys()
    non_price_changes = []
    for sample, old in bp.items():
        assert old["review_id"] == ap[sample]["review_id"]
        for side in ("praise_tags", "complaint_tags"):
            old_set = set(filter(None, old[side].split(";"))) - {"price"}
            new_set = set(filter(None, ap[sample][side].split(";"))) - {"price"}
            if old_set != new_set:
                non_price_changes.append([sample, side, sorted(old_set), sorted(new_set)])
    assert not non_price_changes, "Unexpected non-price prediction changes"
    old_errors = {tuple(r[k] for k in ("sample_id", "theme", "side", "error"))
                  for r in load_rows(before / "errors.csv")}
    new_errors = {tuple(r[k] for k in ("sample_id", "theme", "side", "error"))
                  for r in load_rows(after / "errors.csv")}
    improved = sorted(old_errors - new_errors)
    regressed = sorted(new_errors - old_errors)
    unchanged = sorted(new_errors & old_errors)
    # Validate the frozen artifacts, not just totals.
    for directory, manifest in ((before, bm), (after, am)):
        for name, digest in manifest["output_sha256"].items():
            assert fingerprint(directory / name) == digest
    result = {
        "before": str(before), "after": str(after),
        "rules_before": b["rules_version"], "rules_after": a["rules_version"],
        "count_order": ["correct", "missed", "unsupported"],
        "improvements": improved, "regressions": regressed,
        "unchanged_residual_errors": unchanged,
        "non_price_prediction_changes": non_price_changes,
        "warning_changes": [
            [old["sample_id"], old["needs_review"], new["needs_review"]]
            for old, new in zip(bf, af) if old["needs_review"] != new["needs_review"]],
        "before_summary": b, "after_summary": a,
    }
    for filename, data, headings in (
        ("improvements.csv", improved, ["sample_id", "theme", "side", "resolved_error"]),
        ("regressions.csv", regressed, ["sample_id", "theme", "side", "new_error"]),
        ("unchanged_errors.csv", unchanged, ["sample_id", "theme", "side", "error"]),
    ):
        with (after / filename).open("x", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headings)
            writer.writerows(data)
    (after / "price_comparison.json").write_text(json.dumps(result, indent=2))
    lines = [
        "# Private price-tagging before-and-after report",
        "Tuning-set evidence only, not held-out accuracy or restaurant-performance evidence.",
        "All 61 labels began as Claude AI drafts and were user-approved. 56 rows say Yes "
        "in the CSV. MC001 to MC005 say no but were separately approved in chat. Labels "
        "were not changed. No restaurant-manager adjudication is claimed.",
        "Both snapshots were saved after labeling. The baseline was frozen before this "
        "price update, not before labeling. The supplied export's origin is user-reported.",
        f"Rules: {b['rules_version']} -> {a['rules_version']}.",
        "## Results (correct / missed / unsupported)",
        "| Theme | Praise before | Praise after | Complaint before | Complaint after |",
        "|---|---|---|---|---|",
    ]
    fmt = lambda counts: " / ".join(map(str, counts))
    for theme in b["per_theme"]:
        lines.append(f"| {theme} | {fmt(b['per_theme'][theme][0])} | "
                     f"{fmt(a['per_theme'][theme][0])} | {fmt(b['per_theme'][theme][1])} | "
                     f"{fmt(a['per_theme'][theme][1])} |")
    lines.extend([
        f"Overall praise: {fmt(b['praise'])} -> {fmt(a['praise'])}.",
        f"Overall complaint: {fmt(b['complaint'])} -> {fmt(a['complaint'])}.",
        f"Combined: {fmt(b['combined'])} -> {fmt(a['combined'])}.",
        f"Mixed both sides: {b['mixed_both']}/{b['mixed']} -> {a['mixed_both']}/{a['mixed']}.",
        f"Unclear cells excluded: {b['unclear']} -> {a['unclear']}.",
        f"Needs manager review: {b['needs_review']}/61 -> {a['needs_review']}/61.",
        f"Improvements: {len(improved)}. Regressions: {len(regressed)}. "
        f"Unchanged residual errors: {len(unchanged)}. Non-price prediction changes: 0.",
        "All 12 themes were scored; no non-price changes were hidden.",
        "The single price mixed cell remains incompletely tagged. Rare themes have too "
        "few examples for general claims. Fee/tip/money mentions are not automatically complaints.",
        "An intermediate candidate made an unsupported price-praise prediction at MC050. "
        "The unqualified worth cue was removed; it is not present in the final results.",
    ])
    for title, rows in (("Every improvement", improved), ("Every regression", regressed),
                        ("Every unchanged residual error", unchanged)):
        lines.extend(["## " + title, "| Sample | Theme | Side | Error |",
                      "|---|---|---|---|"])
        lines.extend("| " + " | ".join(row) + " |" for row in rows)
        if not rows:
            lines.append("None.")
    lines.extend([
        "## Scope, verification and undo",
        "Changed implementation: local_analyzer.py calls the isolated price_rules.py; "
        "the original non-price matching pass remains intact. No uploaded proposal was executed "
        "or substituted. No Ollama, paid API or model calls. engine.py and app.py unchanged.",
        "The rules-version bump invalidates cached local analysis and requires renewed manager "
        "approval. Old decisions and historical action baselines are not rewritten. Existing "
        "provenance warnings remain active.",
        "Changed evaluation helper: evaluate_approved_sheet.py now fingerprints price_rules.py. "
        "Added synthetic tests and compare_price_evaluation.py.",
        "Backup and SHA-256 manifest: review_intel_app/backups/"
        "price_tagging_20261105T223902898070Z/.",
        "Where to inspect: Local Review Analyzer, What guests say, Read the reviews behind a "
        "theme, Theme = Price, select Praise or Complaints, then Why these tags?. "
        "Neutral/ambiguous price evidence is under Reviews needing manager review, then "
        "Review needing a check; its warning and evidence appear inline. This is the "
        "Replit workspace, not a separate laptop or deployment.",
        "Safe undo: only if there are no later edits, restore local_analyzer.py and "
        "evaluate_approved_sheet.py from that backup. Otherwise reverse only this task's "
        "changes. New helpers may remain unused. Do not restore labels, uploads, corrections "
        "or action histories. Restart Streamlit and use Clear cache in its menu before rerunning "
        "local analysis. Restoring local-rules-1 makes prior local-rules-1 approvals eligible "
        "only under their original exact-source checks; local-rules-2-price approvals must not "
        "carry backward. If reapproval of all decisions is wanted, use a fresh rollback rules "
        "version instead of reusing either version. Never delete decision history.",
        "No production deployment performed. Task status is separate from local code verification.",
        "Next: manager-labeled unused reviews with rules frozen (existing follow-up task).",
    ])
    text = "\n\n".join(lines)
    (after / "price_report.md").write_text(text)
    (after / "price_report.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Private price evaluation</title>'
        '<style>body{max-width:1100px;margin:40px auto;padding:20px;font:15px system-ui}'
        'pre{white-space:pre-wrap;line-height:1.6}</style><pre>' + html.escape(text) + '</pre>')
    manifest = {"before_manifest_sha256": fingerprint(before / "manifest.json"),
                "after_manifest_sha256": fingerprint(after / "manifest.json"),
                "comparison_helper_sha256": fingerprint(Path(__file__).resolve()),
                "output_sha256": {p.name: fingerprint(p) for p in after.iterdir()
                                  if p.is_file()}}
    (after / "comparison_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps({"improvements": len(improved), "regressions": len(regressed),
                      "residual_errors": len(unchanged), "non_price_changes": 0}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    args = parser.parse_args()
    compare(args.before.resolve(), args.after.resolve())
