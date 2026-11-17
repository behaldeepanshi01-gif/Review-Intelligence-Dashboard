"""Private, read-only tuning comparison. Never reads unused labeling batches."""
import argparse
import ast
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import engine as E


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_rows(path):
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def verify(backup, before, after, sheet, diagnostic, output):
    output.mkdir(parents=True, exist_ok=False)
    saved = json.loads((backup / "manifest.json").read_text())
    for source, digest in saved.items():
        assert hashlib.sha256((backup / Path(source).name).read_bytes()).hexdigest() == digest
    old_price = load_module("old_price", backup / "price_rules.py")
    old_local = load_module("old_local", backup / "local_analyzer.py")
    old_local.analyze_price = old_price.analyze_price

    def old_prediction(text, rating):
        with patch.object(E, "analyze_text", old_local.analyze_text):
            return E.tag_offline(text, rating)

    def non_price(prediction):
        return {
            "praise": sorted(set(prediction["themes_pos"]) - {"price"}),
            "complaint": sorted(set(prediction["themes_neg"]) - {"price"}),
            "evidence": [e for e in prediction["tag_evidence"] if e["theme"] != "price"],
        }

    # Parse only literal cases from the inspected evidence file; never execute it.
    tree = ast.parse(diagnostic.read_text())
    cases = next(ast.literal_eval(node.value) for node in tree.body
                 if isinstance(node, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == "cases" for t in node.targets))
    assert len(cases) == 12
    checks = []
    for case_id, text, praise, complaint, evidence in cases:
        for rating in (1, 3, 5):
            old, new = old_prediction(text, rating), E.tag_offline(text, rating)
            def passes(p):
                return ((praise is None or ("price" in p["themes_pos"]) == praise)
                        and ("price" in p["themes_neg"]) == complaint
                        and (evidence is None or any(
                            e["theme"] == "price" and e["polarity"] == evidence
                            and e["excerpt"] and e["reason"] and e["matched_terms"]
                            for e in p["tag_evidence"]))
                        and (evidence != "Needs review" or p["needs_review"]))
            unchanged = non_price(old) == non_price(new)
            checks.append(dict(case_id=case_id, rating=rating, before=passes(old),
                               after=passes(new), non_price_unchanged=unchanged))
            assert passes(new) and unchanged, (case_id, rating)
    rows = read_rows(sheet)
    assert len(rows) == 61
    frozen = {r["sample_id"]: r for r in read_rows(before / "predictions.csv")}
    changes, non_price_changes = [], []
    for row in rows:
        old = old_prediction(row["review_text"], int(row["rating"]))
        new = E.tag_offline(row["review_text"], int(row["rating"]))
        for side, key in (("praise", "themes_pos"), ("complaint", "themes_neg")):
            assert set(old[key]) == set(filter(None, frozen[row["sample_id"]][side + "_tags"].split(";")))
            for theme in sorted(set(old[key]) ^ set(new[key])):
                changes.append(dict(sample_id=row["sample_id"], theme=theme, polarity=side,
                                    before=theme in old[key], after=theme in new[key]))
        if non_price(old) != non_price(new):
            non_price_changes.append(row["sample_id"])
    assert not non_price_changes
    errors = lambda folder: {tuple(r.values()) for r in read_rows(folder / "errors.csv")}
    old_errors, new_errors = errors(before), errors(after)
    result = dict(
        rules_version=E.LOCAL_ANALYZER_VERSION,
        provenance="AI-draft labels; 56 CSV approvals; MC001–MC005 chat approvals. Tuning only.",
        before_scores=json.loads((before / "scores.json").read_text()),
        after_scores=json.loads((after / "scores.json").read_text()),
        synthetic_checks=checks, changes=changes, non_price_changes=non_price_changes,
        improvements=sorted(old_errors - new_errors), regressions=sorted(new_errors - old_errors),
        remaining_errors=sorted(new_errors),
        implementation_sha256={name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                               for name in ("engine.py", "local_analyzer.py", "price_rules.py")},
    )
    (output / "comparison.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({k: result[k] for k in ("rules_version", "changes", "non_price_changes",
                                            "improvements", "regressions", "implementation_sha256")}))
    print("Synthetic before/after:", sum(c["before"] for c in checks),
          sum(c["after"] for c in checks), "/36; remaining errors:", len(new_errors))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for name in ("backup", "before", "after", "sheet", "diagnostic", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    verify(**vars(parser.parse_args()))
