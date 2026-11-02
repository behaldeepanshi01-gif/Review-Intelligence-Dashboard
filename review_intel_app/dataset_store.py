"""Explicit local dataset identities; filenames never decide action ownership."""

from contextlib import closing
from pathlib import Path
import sqlite3
import uuid


SAMPLE_ID = "builtin:synthetic-sample"


class DatasetStore:
    def __init__(self, uploads, sample):
        self.uploads = Path(uploads)
        self.uploads.mkdir(parents=True, exist_ok=True)
        self.database = self.uploads / "datasets.sqlite"
        with closing(self.connect()) as db, db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS datasets (
                    dataset_id TEXT PRIMARY KEY, label TEXT NOT NULL,
                    path TEXT NOT NULL UNIQUE, legacy_tag TEXT UNIQUE,
                    correction_path TEXT
                )
            """)
            if "correction_path" not in {
                row["name"] for row in db.execute("PRAGMA table_info(datasets)")
            }:
                db.execute("ALTER TABLE datasets ADD COLUMN correction_path TEXT")
            if "history_revision" not in {
                row["name"] for row in db.execute("PRAGMA table_info(datasets)")
            }:
                db.execute(
                    "ALTER TABLE datasets ADD COLUMN history_revision INTEGER NOT NULL DEFAULT 0"
                )
            db.execute("UPDATE datasets SET correction_path = path WHERE correction_path IS NULL")
            db.execute("""
                CREATE TABLE IF NOT EXISTS imported_files (
                    path TEXT PRIMARY KEY
                )
            """)
            db.execute(
                "INSERT OR IGNORE INTO datasets "
                "(dataset_id, label, path, legacy_tag, correction_path) VALUES (?, ?, ?, NULL, ?)",
                (SAMPLE_ID, "Sample data (synthetic)",
                 str(Path(sample).resolve()), str(Path(sample).resolve())),
            )
            # Retain old files, but do not guess which history belongs to them.
            for path in sorted(self.uploads.iterdir()):
                if not path.is_file() or path.suffix.lower() != ".csv":
                    continue
                if db.execute(
                    "SELECT 1 FROM imported_files WHERE path = ?", (str(path.resolve()),)
                ).fetchone():
                    continue
                db.execute(
                    "INSERT OR IGNORE INTO datasets "
                    "(dataset_id, label, path, legacy_tag, correction_path) VALUES (?, ?, ?, NULL, ?)",
                    ("upload:" + uuid.uuid4().hex, path.name,
                     str(path.resolve()), str(path.resolve())),
                )
                db.execute("INSERT INTO imported_files VALUES (?)", (str(path.resolve()),))

    def connect(self):
        db = sqlite3.connect(self.database)
        db.row_factory = sqlite3.Row
        return db

    def list_datasets(self, include_sample=False):
        with closing(self.connect()) as db:
            rows = db.execute("SELECT * FROM datasets ORDER BY label, dataset_id")
            return [
                dict(row) for row in rows
                if include_sample or row["dataset_id"] != SAMPLE_ID
            ]

    def get(self, dataset_id):
        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT * FROM datasets WHERE dataset_id = ?", (dataset_id,)
            ).fetchone()
        if row is None:
            raise ValueError("That saved dataset no longer exists.")
        return dict(row)

    def save_snapshot(self, name, content, dataset_id=None):
        """Create a new dataset unless a specific existing ID was selected.

        Keep previous CSV snapshots untouched. Publish the new path only once
        its complete bytes have been written; failed writes keep the old path.
        Callers must validate CSV content before saving.
        """
        if dataset_id == SAMPLE_ID:
            raise ValueError("The built-in sample cannot be replaced by an upload.")
        if dataset_id is not None:
            self.get(dataset_id)
        else:
            dataset_id = "upload:" + uuid.uuid4().hex
        folder = self.uploads / "snapshots"
        folder.mkdir(exist_ok=True)
        path = (folder / f"{uuid.uuid4().hex}.csv").resolve()
        with path.open("xb") as file:
            file.write(content)
        try:
            with closing(self.connect()) as db, db:
                if db.execute(
                    "SELECT 1 FROM datasets WHERE dataset_id = ?", (dataset_id,)
                ).fetchone():
                    db.execute(
                        "UPDATE datasets SET path = ? WHERE dataset_id = ?",
                        (str(path), dataset_id),
                    )
                else:
                    db.execute(
                        "INSERT INTO datasets "
                        "(dataset_id, label, path, legacy_tag, correction_path) VALUES (?, ?, ?, NULL, ?)",
                        (dataset_id, Path(name).name, str(path), str(path)),
                    )
        except Exception:
            path.unlink()
            raise
        return self.get(dataset_id)

    def unclaimed_legacy_tags(self, actions):
        claimed = {
            row["legacy_tag"] for row in self.list_datasets(include_sample=True)
            if row["legacy_tag"]
        }
        return sorted({
            row["dataset_tag"] for row in actions
            if isinstance(row.get("dataset_tag"), str)
            and not row["dataset_tag"].startswith(("upload:", "builtin:"))
            and row["dataset_tag"] not in claimed
        })

    def claim_legacy_history(self, dataset_id, legacy_tag, actions, *, expected_revision=None):
        """Link an old filename-scoped history once, without rewriting its log."""
        if (not isinstance(legacy_tag, str)
                or legacy_tag.startswith(("upload:", "builtin:"))
                or not any(row.get("dataset_tag") == legacy_tag for row in actions)):
            raise ValueError("That legacy history is unavailable or already linked.")
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute(
                "SELECT 1 FROM datasets WHERE legacy_tag = ?", (legacy_tag,)
            ).fetchone():
                raise ValueError("That legacy history is unavailable or already linked.")
            current = db.execute(
                "SELECT * FROM datasets WHERE dataset_id = ?", (dataset_id,)
            ).fetchone()
            if current is None or (
                expected_revision is not None
                and current["history_revision"] != expected_revision
            ):
                raise ValueError("The dataset history link changed. Refresh and review it again.")
            result = db.execute(
                "UPDATE datasets SET legacy_tag = ?, history_revision = history_revision + 1 "
                "WHERE dataset_id = ? AND legacy_tag IS NULL",
                (legacy_tag, dataset_id),
            )
            if result.rowcount != 1:
                raise ValueError("This dataset already has a linked history.")
        return self.get(dataset_id)

    def correct_legacy_history(
        self, source_id, legacy_tag, *, expected_source_revision,
        target_id=None, expected_target_revision=None,
    ):
        """Atomically detach or transfer only the association, never action records.

        Revisions reject stale confirmations even if a link was removed and then
        restored to the same dataset while the manager's screen was open.
        """
        if target_id == source_id:
            raise ValueError("Choose a different destination dataset.")
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            source = db.execute(
                "SELECT * FROM datasets WHERE dataset_id = ?", (source_id,)
            ).fetchone()
            if (source is None or legacy_tag is None
                    or source["legacy_tag"] != legacy_tag
                    or source["history_revision"] != expected_source_revision):
                raise ValueError("The source history link changed. Refresh and review it again.")
            if target_id is not None:
                target = db.execute(
                    "SELECT * FROM datasets WHERE dataset_id = ?", (target_id,)
                ).fetchone()
                if (target is None or target["legacy_tag"] is not None
                        or expected_target_revision is None
                        or target["history_revision"] != expected_target_revision):
                    raise ValueError(
                        "The destination history link changed or is already occupied. "
                        "Refresh and review it again."
                    )
            db.execute(
                "UPDATE datasets SET legacy_tag = NULL, history_revision = history_revision + 1 "
                "WHERE dataset_id = ?", (source_id,),
            )
            if target_id is not None:
                db.execute(
                    "UPDATE datasets SET legacy_tag = ?, history_revision = history_revision + 1 "
                    "WHERE dataset_id = ?", (legacy_tag, target_id),
                )
