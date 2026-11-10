import contextlib
import csv
import hashlib
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

import evaluate_heldout as heldout
from evaluate_heldout import validate_rows
from labeling_sheet import HEADERS, text_hash
import engine as E


class HeldoutValidationTests(unittest.TestCase):
    def setUp(self):
        self.row = dict(sample_id="H001", review_text="Synthetic food comment.",
                        **{name: "Absent" for name in E.THEME_LABELS.values()})
        self.frozen = [dict(sample_id="H001",
                            csv_text_sha256=text_hash(self.row["review_text"]))]

    def test_exact_batch_approval_allows_chat_approval(self):
        validate_rows([self.row], self.frozen, ["H001"])

    def test_missing_approval_rejected(self):
        with self.assertRaises(ValueError):
            validate_rows([self.row], self.frozen, [])

    def test_duplicate_id_rejected(self):
        with self.assertRaises(ValueError):
            validate_rows([self.row, self.row], self.frozen, ["H001"])

    def test_modified_text_rejected(self):
        self.row["review_text"] += " edited"
        with self.assertRaises(ValueError):
            validate_rows([self.row], self.frozen, ["H001"])

    def test_blank_or_invalid_label_rejected(self):
        for value in ("", "neutral", "made-up"):
            self.row[next(iter(E.THEME_LABELS.values()))] = value
            with self.assertRaises(ValueError):
                validate_rows([self.row], self.frozen, ["H001"])


class HeldoutIntegrationTests(unittest.TestCase):
    """Exercise the real scorer using only disposable, synthetic batch files."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.app = self.root / "app"
        self.app.mkdir()
        self.batch = self.root / "batch"
        self.batch.mkdir(mode=0o700)
        self.inputs = {}
        for name in ("source", "tuning", "engine.py", "local_analyzer.py",
                     "price_rules.py", "app.py", "labeling_sheet.py",
                     "prepare_heldout.py"):
            path = (self.root if name in ("source", "tuning") else self.app) / name
            path.write_bytes(f"Synthetic frozen input: {name}\n".encode())
            self.inputs[name] = path
        (self.app / "evaluate_approved_sheet.py").write_bytes(b"# Synthetic primitive\n")
        self.enterContext(patch.object(heldout, "APP_DIR", self.app))
        self.analyzer = self.enterContext(patch.object(
            E, "tag_offline", side_effect=AssertionError("Do not regenerate predictions")))
        self.scorer = self.enterContext(patch.object(heldout, "score", wraps=heldout.score))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))

        first_theme, first_label = next(iter(E.THEME_LABELS.items()))
        self.row = dict(
            sample_id="H001", review_text='Synthetic café, "good"\r\nbut uneven.',
            **{name: "Absent" for name in E.THEME_LABELS.values()},
            human_checked="", notes='Synthetic AI draft; not human-only.\r\nKeep "quotes".',
        )
        self.row[first_label] = "Both"
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=HEADERS, lineterminator="\r\n")
        writer.writeheader()
        writer.writerow(self.row)
        self.sheet = self.root / "submitted.csv"
        self.sheet.write_bytes(buffer.getvalue().encode("utf-8-sig"))
        blank = dict(self.row, **{name: "" for name in E.THEME_LABELS.values()})
        with (self.batch / "labeling_sheet.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=HEADERS)
            writer.writeheader()
            writer.writerow(blank)
        (self.batch / "labeling_guide.html").write_text("<p>Synthetic blind guide</p>")
        self.manifest = dict(
            rules_version=E.LOCAL_ANALYZER_VERSION,
            inputs_sha256={name: self.digest(path) for name, path in self.inputs.items()},
            deliverable_sha256={
                name: self.digest(self.batch / name)
                for name in ("labeling_sheet.csv", "labeling_guide.html")
            },
            reviews=[dict(
                sample_id="H001", csv_text_sha256=text_hash(self.row["review_text"]),
                prediction=dict(themes_pos=[first_theme], themes_neg=[first_theme],
                                needs_review=False),
            )],
        )
        self.manifest_path = self.batch / "frozen_predictions.json"
        self.manifest_path.write_text(json.dumps(self.manifest))
        self.approval = self.root / "approval.json"
        self.approve_sheet()
        self.result = self.batch / "scored_once"

    @staticmethod
    def digest(path):
        # Independent of the production hashing helper.
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def approve_sheet(self):
        self.approval.write_text(json.dumps(dict(
            explicitly_approved=True, sheet_sha256=self.digest(self.sheet),
            approval_statement="Synthetic test approval for this exact batch.",
            labeling_statement="Synthetic fixture, not real human ground truth.",
            sample_ids=["H001"],
        )))

    def evaluate(self):
        heldout.evaluate(self.batch, self.sheet, self.inputs["source"],
                         self.inputs["tuning"], self.approval)

    def assert_rejected_before_scoring(self, message):
        self.scorer.reset_mock()
        with self.assertRaisesRegex(ValueError, message):
            self.evaluate()
        self.scorer.assert_not_called()
        self.analyzer.assert_not_called()
        self.assertFalse(self.result.exists())

    def test_changed_rules_version_rejects_before_scoring(self):
        with patch.object(E, "LOCAL_ANALYZER_VERSION", "synthetic-changed-version"):
            self.assert_rejected_before_scoring("Rules changed")

    def test_changed_input_fingerprints_reject_before_scoring(self):
        for name, path in self.inputs.items():
            with self.subTest(input=name):
                original = path.read_bytes()
                try:
                    path.write_bytes(original + b"changed\n")
                    self.assert_rejected_before_scoring(
                        rf"Frozen input changed \({name.replace('.', '[.]')}\)")
                finally:
                    path.write_bytes(original)

    def test_changed_deliverable_fingerprints_reject_before_scoring(self):
        for name in self.manifest["deliverable_sha256"]:
            with self.subTest(deliverable=name):
                path = self.batch / name
                original = path.read_bytes()
                try:
                    path.write_bytes(original + b"changed\n")
                    self.assert_rejected_before_scoring("Frozen deliverable changed")
                finally:
                    path.write_bytes(original)

    def test_approval_hash_binds_bytes_even_when_parsed_rows_match(self):
        original = self.sheet.read_bytes()
        # Removing a BOM or changing record quoting does not change parsed values.
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=HEADERS, quoting=csv.QUOTE_ALL,
                                lineterminator="\n")
        writer.writeheader()
        writer.writerow(self.row)
        variants = (original.removeprefix(b"\xef\xbb\xbf"),
                    buffer.getvalue().encode("utf-8-sig"))
        for changed in variants:
            with self.subTest(digest=hashlib.sha256(changed).hexdigest()):
                self.sheet.write_bytes(changed)
                self.assertNotEqual(changed, original)
                self.assertEqual(heldout.read_sheet(self.sheet), [self.row])
                self.assert_rejected_before_scoring("exact sheet")
        # An explicit approval for the new bytes permits that same valid sheet.
        self.approve_sheet()
        self.evaluate()
        self.assertEqual((self.result / "submitted_labels.csv").read_bytes(), variants[-1])
        self.assertTrue(self.scorer.called)
        self.analyzer.assert_not_called()

    def snapshot_result(self):
        return {path.name: (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
                for path in self.result.iterdir()}

    def test_success_preserves_bytes_permissions_and_verifiable_hashes(self):
        original = self.sheet.read_bytes()
        self.evaluate()
        self.assertEqual((self.result / "submitted_labels.csv").read_bytes(), original)
        self.assertEqual(self.sheet.read_bytes(), original)
        self.assertEqual(heldout.read_sheet(self.result / "submitted_labels.csv"), [self.row])
        self.assertEqual(stat.S_IMODE(self.result.stat().st_mode), 0o700)
        expected_outputs = {"scores.json", "errors.json", "approval.json", "report.md",
                            "report.html", "submitted_labels.csv"}
        self.assertEqual({p.name for p in self.result.iterdir()},
                         expected_outputs | {"verification.json"})
        for path in self.result.iterdir():
            with self.subTest(output=path.name):
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        verification = json.loads((self.result / "verification.json").read_text())
        self.assertNotIn("verification.json", verification["outputs_sha256"])
        self.assertEqual(verification["outputs_sha256"], {
            name: self.digest(self.result / name) for name in expected_outputs})
        self.assertEqual(verification["inputs_sha256"], self.manifest["inputs_sha256"])
        for key, path in (
            ("frozen_manifest_sha256", self.manifest_path),
            ("submitted_sheet_sha256", self.sheet),
            ("scorer_sha256", Path(heldout.__file__)),
            ("scoring_primitive_sha256", self.app / "evaluate_approved_sheet.py"),
        ):
            self.assertEqual(verification[key], self.digest(path))
        summary = json.loads((self.result / "scores.json").read_text())
        self.assertEqual(summary["reviews"], 1)
        self.assertEqual(summary["praise"], [1, 0, 0])
        self.assertEqual(summary["complaint"], [1, 0, 0])
        self.assertEqual(summary["mixed_both"], 1)
        self.assertEqual(json.loads((self.result / "errors.json").read_text()), [])
        self.assertEqual(json.loads((self.result / "approval.json").read_text()),
                         json.loads(self.approval.read_text()))
        self.assertEqual(self.scorer.call_count, len(E.THEME_LABELS))
        self.analyzer.assert_not_called()

    def test_repeat_scoring_cannot_overwrite_completed_result(self):
        self.evaluate()
        before = self.snapshot_result()
        self.scorer.reset_mock()
        with self.assertRaises(FileExistsError):
            self.evaluate()
        self.scorer.assert_not_called()
        self.analyzer.assert_not_called()
        self.assertEqual(self.snapshot_result(), before)

    def test_existing_incomplete_result_is_not_overwritten(self):
        self.result.mkdir(mode=0o700)
        (self.result / "partial.txt").write_bytes(b"Synthetic failed-attempt evidence")
        before = self.snapshot_result()
        with self.assertRaises(FileExistsError):
            self.evaluate()
        self.scorer.assert_not_called()
        self.assertEqual(self.snapshot_result(), before)


if __name__ == "__main__":
    unittest.main()
