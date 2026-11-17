"""Audit the public walkthrough to catch connections to real restaurant data.

Never prints private review text or real guest names in violation messages.
"""
import csv
import json
from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DEMO_DIR = REPO_ROOT / "artifacts" / "review-intelligence-demo"
DEFAULT_UPLOAD_DIR = Path(__file__).resolve().parent / "data" / "uploads"

SKIP_DIRS = {"node_modules", "dist", ".git", "__pycache__"}
FORBIDDEN_DATA_SUFFIXES = {
    ".csv", ".tsv", ".xlsx", ".xls", ".sqlite", ".sqlite3", ".db", ".parquet",
}
CODE_SUFFIXES = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
REVIEW_JSON_KEYS = {"review_id", "reviewer", "themes_neg", "themes_pos", "reply_draft"}

NETWORK_AND_BACKEND_PATTERNS = [
    (re.compile(r"\bfetch\s*\("), "live network call (fetch)"),
    (re.compile(r"\baxios\b"), "live network client (axios)"),
    (re.compile(r"\bXMLHttpRequest\b"), "live network client (XMLHttpRequest)"),
    (re.compile(r"\bnew\s+WebSocket\b"), "live WebSocket connection"),
    (re.compile(r"\bnew\s+EventSource\b"), "live EventSource stream"),
    (re.compile(r"\bnavigator\.sendBeacon\b"), "network beacon call"),
    (re.compile(r"""['"`][^'"`]*/api/"""), "API endpoint reference (/api/)"),
    (re.compile(r"""['"`][^'"`]*/dashboard(?:/|['"`])"""), "live dashboard route reference (/dashboard)"),
    (re.compile(r"\bVITE_API\w*"), "API environment variable reference"),
    (re.compile(r"\bDATABASE_URL\b"), "database connection string reference"),
    (re.compile(r"\bstreamlit\b", re.I), "Streamlit backend reference"),
    (re.compile(r":(?:8501|8000|5000)\b"), "local backend port reference"),
]

PRIVATE_PATH_PATTERNS = [
    (re.compile(r"review_intel_app", re.I), "private app directory reference (review_intel_app)"),
    (re.compile(r"api-server", re.I), "backend artifact reference (api-server)"),
    (re.compile(r"data[/\\]uploads", re.I), "private upload directory reference"),
    (re.compile(r"manager_accounts", re.I), "manager account store reference"),
    (re.compile(r"manager_corrections", re.I), "manager corrections store reference"),
    (re.compile(r"datasets\.sqlite", re.I), "dataset store database reference"),
    (re.compile(r"reply_approvals", re.I), "reply approvals store reference"),
    (re.compile(r"actions\.json", re.I), "action tracker log reference"),
    (re.compile(r"""(?:from\s+['"]|import\s*\(\s*['"]|require\s*\(\s*['"])(?:@assets|[^'"]*attached_assets)"""),
     "import from attached_assets"),
    (re.compile(r"""['"`][^'"`]*\.(?:csv|tsv|xlsx|xls|sqlite|sqlite3|db)\b""", re.I),
     "data file reference inside demo code"),
]

ALLOWED_CODE_URLS = {
    "http://www.w3.org/2000/svg",
    "http://www.w3.org/1999/xlink",
}
URL_PATTERN = re.compile(r"https?://[^\s'\"`<>)]+")

VITE_FORBIDDEN_PATTERNS = [
    (re.compile(r"\bproxy\s*:"), "Vite server proxy configuration"),
    (re.compile(r"review_intel_app", re.I), "Vite reference to review_intel_app"),
    (re.compile(r"api-server", re.I), "Vite reference to api-server"),
    (re.compile(r"data[/\\]uploads", re.I), "Vite reference to data/uploads"),
    (re.compile(r"\.(?:csv|sqlite|sqlite3|db)\b", re.I), "Vite reference to data file"),
]

SCENE_FORBIDDEN_PATTERNS = [
    (re.compile(r"\byelp\b", re.I), "Yelp reference in public walkthrough"),
    (re.compile(r"\bconnected to live\b", re.I), "claim of live restaurant connection"),
    (re.compile(r"\bimported from google\b", re.I), "claim of imported Google reviews"),
    (re.compile(r"\bactual mumbai central reviews\b", re.I), "claim of actual Mumbai Central reviews"),
]

REQUIRED_DISCLOSURES = {
    "src/components/video/ShowcaseUI.tsx": [
        "DEMO MODE",
        "No live data connected",
        "No CSV or POS export supplied",
    ],
    "src/components/video/video_scenes/Scene1.tsx": [
        "FICTIONAL SAMPLE REVIEW",
        "Not a real guest",
        "NO LIVE RESTAURANT DATA",
    ],
    "src/components/video/video_scenes/Scene3.tsx": [
        "SYNTHETIC EXAMPLE",
        "Needs manager review",
    ],
    "src/components/video/video_scenes/Scene4.tsx": [
        "ILLUSTRATIVE ALERT",
        "Not a finding about Mumbai Central",
    ],
    "src/components/video/video_scenes/Scene5.tsx": [
        "FICTIONAL STAFF PRAISE",
        "Invented names",
    ],
    "src/components/video/video_scenes/Scene6.tsx": [
        "FICTIONAL SAMPLE",
        "Manager reviews before sending.",
    ],
    "src/components/video/video_scenes/Scene7.tsx": [
        "Not supplied",
        "Not imported",
        "Nothing shown here is a real performance finding.",
    ],
    "src/components/video/video_scenes/Scene8.tsx": [
        "FICTIONAL INPUTS",
        "Not a finding about Mumbai Central",
    ],
    "src/components/video/video_scenes/Scene9.tsx": [
        "Demo only",
        "no live restaurant data",
    ],
}

GENERIC_REVIEWER_NAMES = {"guest", "anonymous", "nan", "none", "user", "customer", "a google user"}


def _iter_files(root: Path):
    for path in sorted(root.rglob("*")):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_file():
            yield path


def _normalize_ws(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def _extract_private_terms(csv_paths) -> tuple[set[str], set[str]]:
    """Extract normalized guest names and review passages from private CSV files."""
    reviewer_terms: set[str] = set()
    passage_terms: set[str] = set()
    for path in csv_paths:
        if not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                if not reader.fieldnames:
                    continue
                lower_map = {name.lower().strip(): name for name in reader.fieldnames if name}
                reviewer_col = lower_map.get("reviewer") or lower_map.get("author") or lower_map.get("guest")
                text_col = lower_map.get("text") or lower_map.get("review") or lower_map.get("review_text")
                for row in reader:
                    if reviewer_col:
                        raw_name = _normalize_ws(row.get(reviewer_col, ""))
                        if raw_name and raw_name not in GENERIC_REVIEWER_NAMES:
                            if len(raw_name.split()) >= 2 or len(raw_name) >= 6:
                                reviewer_terms.add(raw_name)
                    if text_col:
                        raw_text = _normalize_ws(row.get(text_col, ""))
                        if len(raw_text.split()) >= 5:
                            passage_terms.add(raw_text)
                            for sentence in re.split(r"(?<=[.!?])\s+", raw_text):
                                sent = sentence.strip()
                                if len(sent.split()) >= 5:
                                    passage_terms.add(sent)
        except (OSError, UnicodeError, csv.Error):
            continue
    return reviewer_terms, passage_terms


def _json_contains_review_records(data) -> bool:
    if isinstance(data, dict):
        if len(REVIEW_JSON_KEYS.intersection(data.keys())) >= 2:
            return True
        return any(_json_contains_review_records(v) for v in data.values())
    if isinstance(data, list):
        return any(_json_contains_review_records(item) for item in data[:50])
    return False


def audit_demo_boundary(
    demo_dir: Path = DEFAULT_DEMO_DIR,
    *,
    upload_dirs=None,
    forbidden_review_csvs=None,
    require_disclosures: bool = True,
) -> list[str]:
    """Return a list of boundary violations for the public walkthrough (empty = clean)."""
    demo_dir = Path(demo_dir)
    if not demo_dir.is_dir():
        return [f"Demo directory not found: {demo_dir}"]

    violations: list[str] = []

    # 1. Bundled data files and suspicious JSON inside src/ or public/
    for path in _iter_files(demo_dir):
        rel = path.relative_to(demo_dir).as_posix()
        suffix = path.suffix.lower()
        if suffix in FORBIDDEN_DATA_SUFFIXES:
            violations.append(f"Bundled data file not allowed in public demo: {rel}")
            continue
        if suffix == ".json" and (rel.startswith("src/") or rel.startswith("public/")):
            try:
                parsed = json.loads(path.read_text(encoding="utf-8"))
                if _json_contains_review_records(parsed):
                    violations.append(f"Review-like JSON dataset found in public demo: {rel}")
            except (OSError, UnicodeError, json.JSONDecodeError):
                pass

    # 2. Network calls, backend endpoints, external URLs, and private paths in demo code
    src_dir = demo_dir / "src"
    if src_dir.is_dir():
        for path in _iter_files(src_dir):
            if path.suffix.lower() not in CODE_SUFFIXES:
                continue
            rel = path.relative_to(demo_dir).as_posix()
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pattern, label in NETWORK_AND_BACKEND_PATTERNS:
                if pattern.search(text):
                    violations.append(f"Disallowed {label} in {rel}")
            for pattern, label in PRIVATE_PATH_PATTERNS:
                if pattern.search(text):
                    violations.append(f"Disallowed {label} in {rel}")
            for url in URL_PATTERN.findall(text):
                if url not in ALLOWED_CODE_URLS:
                    violations.append(f"Disallowed external URL in demo code ({rel})")
                    break

    # 3. Vite configuration check
    vite_cfg = demo_dir / "vite.config.ts"
    if vite_cfg.is_file():
        cfg_text = vite_cfg.read_text(encoding="utf-8", errors="ignore")
        for pattern, label in VITE_FORBIDDEN_PATTERNS:
            if pattern.search(cfg_text):
                violations.append(f"Disallowed {label} in vite.config.ts")

    # 4. Rendered walkthrough scene checks (no Yelp mentions or live-data claims)
    rendered_scene_paths = []
    video_dir = demo_dir / "src" / "components" / "video"
    if video_dir.is_dir():
        rendered_scene_paths.extend(
            p for p in _iter_files(video_dir) if p.suffix.lower() in CODE_SUFFIXES
        )

    for path in rendered_scene_paths:
        rel = path.relative_to(demo_dir).as_posix()
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern, label in SCENE_FORBIDDEN_PATTERNS:
            if pattern.search(text):
                violations.append(f"Disallowed {label} in {rel}")

    scene_paths = list(rendered_scene_paths)
    script_md = demo_dir / "SCRIPT.md"
    if script_md.is_file():
        scene_paths.append(script_md)

    # 5. Required synthetic/fictional boundary disclosures
    if require_disclosures:
        for rel, snippets in REQUIRED_DISCLOSURES.items():
            target = demo_dir / rel
            if not target.is_file():
                violations.append(f"Missing expected walkthrough file: {rel}")
                continue
            content = target.read_text(encoding="utf-8", errors="ignore")
            for snippet in snippets:
                if snippet not in content:
                    violations.append(
                        f"Missing required fictional-boundary disclosure '{snippet}' in {rel}"
                    )

    # 6. Privacy-safe cross-check against uploaded/private review CSVs
    csv_paths: list[Path] = []
    if upload_dirs is None:
        if DEFAULT_UPLOAD_DIR.is_dir():
            csv_paths.extend(sorted(DEFAULT_UPLOAD_DIR.rglob("*.csv")))
    else:
        for directory in upload_dirs:
            d = Path(directory)
            if d.is_dir():
                csv_paths.extend(sorted(d.rglob("*.csv")))
    if forbidden_review_csvs:
        csv_paths.extend(Path(p) for p in forbidden_review_csvs)

    reviewer_terms, passage_terms = _extract_private_terms(csv_paths)
    if reviewer_terms or passage_terms:
        scan_targets = list(scene_paths)
        if src_dir.is_dir():
            for path in _iter_files(src_dir):
                if path.suffix.lower() in CODE_SUFFIXES and path not in scan_targets:
                    scan_targets.append(path)
        for path in scan_targets:
            rel = path.relative_to(demo_dir).as_posix()
            norm = _normalize_ws(path.read_text(encoding="utf-8", errors="ignore"))
            if any(re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", norm)
                   for name in reviewer_terms):
                violations.append(
                    f"Private reviewer name matched in public demo file: {rel}"
                )
            if any(passage in norm for passage in passage_terms):
                violations.append(
                    f"Private review passage matched in public demo file: {rel}"
                )

    return violations


def main() -> int:
    violations = audit_demo_boundary()
    if violations:
        for item in violations:
            print(f"ERROR: {item}", file=sys.stderr)
        return 1
    print("Public demo data-boundary audit passed: walkthrough is fictional and disconnected from real restaurant data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
