"""Tests for Task #147: catch demo connections to real restaurant data."""
import csv
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import demo_data_boundary as B


class DemoDataBoundaryTests(unittest.TestCase):
    def _copy_demo(self) -> Path:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        dest = Path(temp.name) / "review-intelligence-demo"
        shutil.copytree(
            B.DEFAULT_DEMO_DIR,
            dest,
            ignore=shutil.ignore_patterns("node_modules", "dist", ".git"),
        )
        return dest

    def test_real_public_walkthrough_passes_audit(self):
        violations = B.audit_demo_boundary(B.DEFAULT_DEMO_DIR)
        self.assertEqual(violations, [])

    def test_catches_live_network_and_backend_connections(self):
        snippets = [
            "fetch('/api/reviews')",
            "import axios from 'axios'; axios.get('/reviews')",
            "new WebSocket('ws://localhost:8501/stream')",
            "new EventSource('/api/events')",
            "const url = '/dashboard/report-download/abc';",
            "const endpoint = 'https://reviews.example.org/mumbai-central';",
            "const key = import.meta.env.VITE_API_URL;",
        ]
        for snippet in snippets:
            with self.subTest(snippet=snippet):
                demo = self._copy_demo()
                scene = demo / "src/components/video/video_scenes/Scene2.tsx"
                scene.write_text(
                    scene.read_text(encoding="utf-8") + f"\n// {snippet}\n",
                    encoding="utf-8",
                )
                violations = B.audit_demo_boundary(demo, upload_dirs=[])
                self.assertTrue(violations, f"Expected violation for: {snippet}")

    def test_catches_private_app_and_asset_imports(self):
        imports = [
            "import data from '../../../review_intel_app/data/sample_reviews.csv';",
            "import secret from '@assets/private_reviews.json';",
            "import api from '../../api-server/src/app';",
            "const db = 'data/uploads/datasets.sqlite';",
            "const store = 'manager_accounts.sqlite';",
        ]
        for line in imports:
            with self.subTest(line=line):
                demo = self._copy_demo()
                scene = demo / "src/components/video/video_scenes/Scene1.tsx"
                scene.write_text(
                    line + "\n" + scene.read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
                violations = B.audit_demo_boundary(demo, upload_dirs=[])
                self.assertTrue(violations, f"Expected violation for: {line}")

    def test_catches_bundled_data_files_and_review_json(self):
        for rel_path, content in [
            ("public/real_reviews.csv", "location,date,rating,text\nCafe,2026-01-01,5,Great\n"),
            ("src/export.xlsx", "binary-placeholder"),
            ("src/datasets.sqlite", "sqlite-placeholder"),
        ]:
            with self.subTest(rel_path=rel_path):
                demo = self._copy_demo()
                target = demo / rel_path
                target.write_text(content, encoding="utf-8")
                violations = B.audit_demo_boundary(demo, upload_dirs=[])
                self.assertTrue(any("Bundled data file" in v for v in violations))

        demo = self._copy_demo()
        (demo / "src/leaked_reviews.json").write_text(
            json.dumps([{"review_id": "r1", "reviewer": "Guest", "themes_neg": ["price"]}]),
            encoding="utf-8",
        )
        violations = B.audit_demo_boundary(demo, upload_dirs=[])
        self.assertTrue(any("Review-like JSON dataset" in v for v in violations))

    def test_catches_vite_proxy_and_private_app_aliases(self):
        for addition in [
            "server: { proxy: { '/api': 'http://localhost:5000' } }",
            "'@private': path.resolve(import.meta.dirname, '../../review_intel_app')",
        ]:
            with self.subTest(addition=addition):
                demo = self._copy_demo()
                cfg = demo / "vite.config.ts"
                cfg.write_text(
                    cfg.read_text(encoding="utf-8") + f"\n// {addition}\n",
                    encoding="utf-8",
                )
                violations = B.audit_demo_boundary(demo, upload_dirs=[])
                self.assertTrue(any("vite.config.ts" in v for v in violations))

    def test_catches_yelp_and_misleading_live_data_claims(self):
        for phrase in [
            "Imported from Yelp reviews",
            "Connected to live restaurant feed",
            "Actual Mumbai Central reviews shown below",
        ]:
            with self.subTest(phrase=phrase):
                demo = self._copy_demo()
                scene = demo / "src/components/video/video_scenes/Scene4.tsx"
                scene.write_text(
                    scene.read_text(encoding="utf-8") + f"\n// {phrase}\n",
                    encoding="utf-8",
                )
                violations = B.audit_demo_boundary(demo, upload_dirs=[])
                self.assertTrue(violations, f"Expected violation for: {phrase}")

    def test_catches_removed_fictional_boundary_disclosures(self):
        demo = self._copy_demo()
        scene1 = demo / "src/components/video/video_scenes/Scene1.tsx"
        scene1.write_text(
            scene1.read_text(encoding="utf-8").replace("FICTIONAL SAMPLE REVIEW", "CUSTOMER REVIEW"),
            encoding="utf-8",
        )
        violations = B.audit_demo_boundary(demo, upload_dirs=[])
        self.assertTrue(any("Missing required fictional-boundary disclosure" in v for v in violations))

    def test_catches_private_review_and_guest_name_leakage_without_echoing_secrets(self):
        secret_guest = "Privateperson Redacted"
        secret_passage = "This synthetic private dining review sentence must never enter the walkthrough."
        with tempfile.TemporaryDirectory() as upload_tmp:
            upload_dir = Path(upload_tmp)
            csv_path = upload_dir / "private_upload.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["review_id", "location", "date", "rating", "text", "reviewer"])
                writer.writerow(["p1", "Mumbai Central", "2026-01-05", 2, secret_passage, secret_guest])

            # Clean copy passes against the private upload
            clean_demo = self._copy_demo()
            self.assertEqual(B.audit_demo_boundary(clean_demo, upload_dirs=[upload_dir]), [])

            # Leaked guest name is caught and never echoed in the violation message
            guest_demo = self._copy_demo()
            scene5 = guest_demo / "src/components/video/video_scenes/Scene5.tsx"
            scene5.write_text(
                scene5.read_text(encoding="utf-8").replace("Maya Chen", secret_guest),
                encoding="utf-8",
            )
            guest_violations = B.audit_demo_boundary(guest_demo, upload_dirs=[upload_dir])
            self.assertTrue(any("Private reviewer name matched" in v for v in guest_violations))
            for v in guest_violations:
                self.assertNotIn(secret_guest, v)

            # Leaked review passage is caught and never echoed in the violation message
            passage_demo = self._copy_demo()
            scene1 = passage_demo / "src/components/video/video_scenes/Scene1.tsx"
            scene1.write_text(
                scene1.read_text(encoding="utf-8") + f"\n{{/* {secret_passage} */}}\n",
                encoding="utf-8",
            )
            passage_violations = B.audit_demo_boundary(passage_demo, upload_dirs=[upload_dir])
            self.assertTrue(any("Private review passage matched" in v for v in passage_violations))
            for v in passage_violations:
                self.assertNotIn(secret_passage, v)


if __name__ == "__main__":
    unittest.main()
