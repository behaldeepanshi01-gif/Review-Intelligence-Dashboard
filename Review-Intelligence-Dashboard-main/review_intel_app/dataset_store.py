"""Explicit local dataset identities; filenames never decide action ownership."""

from contextlib import closing, contextmanager
from collections import Counter
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

import manager_identity as identity


SAMPLE_ID = "builtin:synthetic-sample"
_LOCAL_OWNER = object()


class HistoryAssociationError(ValueError):
    """An open legacy editor no longer has its approved history association."""


def source_cohort(reviews, dataset_id, location, through_date):
    """Hash analysis inputs through the alert date, not CSV paths or row IDs.

    Generated/duplicate review IDs depend on CSV order. Count identical content
    instead, so reordering is harmless but removing a duplicate is detectable.
    Guest names and raw review text are never persisted in the action log.
    """
    cutoff = date.fromisoformat(str(through_date)[:10])
    counts = Counter()
    for row in reviews:
        if row.get("location") != location:
            continue
        day = date.fromisoformat(str(row["date"])[:10])
        if day > cutoff:
            continue
        payload = [str(row["location"]), str(row["date"]), int(row["rating"]),
                   str(row["text"])]
        digest = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()
        counts[digest] += 1
    return {"version": 1, "dataset_id": dataset_id, "location": location,
            "through_date": cutoff.isoformat(), "counts": dict(sorted(counts.items()))}


def source_cohort_difference(baseline, current):
    """Return aggregate multiset differences, never review identities or hashes.

    One edited review can contribute to both counts. These are unmatched content
    occurrences, not evidence of particular edits, deletions, or backfills.
    """
    before = Counter(baseline["counts"])
    after = Counter(current["counts"])
    return {
        "source_missing_count": sum((before - after).values()),
        "source_added_older_count": sum((after - before).values()),
    }


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
            db.execute("""
                CREATE TABLE IF NOT EXISTS history_link_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_dataset_id TEXT,
                    destination_dataset_id TEXT,
                    legacy_tag TEXT NOT NULL,
                    operation TEXT NOT NULL CHECK (operation IN ('claim', 'unlink', 'transfer')),
                    occurred_at TEXT NOT NULL
                )
            """)
            if "changed_by" not in {
                row["name"] for row in db.execute("PRAGMA table_info(history_link_events)")
            }:
                # Earlier events have no known actor; never infer one from ownership.
                db.execute("ALTER TABLE history_link_events ADD COLUMN changed_by TEXT")
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

    @contextmanager
    def action_history_guard(self, dataset_id, action_tag, expected_revision):
        """Hold ownership stable through the JSON write, including unlink/relink."""
        if action_tag == dataset_id:
            yield
            return
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute(
                "SELECT legacy_tag, history_revision FROM datasets WHERE dataset_id = ?",
                (dataset_id,),
            ).fetchone()
            if (current is None or action_tag is None
                    or current["legacy_tag"] != action_tag
                    or expected_revision is None
                    or current["history_revision"] != expected_revision):
                raise HistoryAssociationError(
                    "The dataset history link changed. Your draft was not saved. "
                    "Refresh the history and review its current ownership before editing.")
            yield

    def save_snapshot(self, name, content, dataset_id=None, *, expected_path=None,
                      session=_LOCAL_OWNER):
        """Create a new dataset unless a specific existing ID was selected.

        Keep previous CSV snapshots untouched. Publish the new path only once
        its complete bytes have been written; failed writes keep the old path.
        Callers must validate CSV content before saving.
        Protected callers pass the exact path whose locations were authorized.
        A conditional update atomically rejects a replacement of a newer snapshot.
        """
        if dataset_id is None and session is not _LOCAL_OWNER:
            identity.require_owner(session)
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
                if session is not _LOCAL_OWNER and expected_path is None:
                    identity.require_owner(session)
                if expected_path is not None:
                    result = db.execute(
                        "UPDATE datasets SET path = ? WHERE dataset_id = ? AND path = ?",
                        (str(path), dataset_id, expected_path),
                    )
                    if result.rowcount != 1:
                        raise ValueError(
                            "The dataset snapshot changed. Reload and validate the upload "
                            "again before saving. Nothing was replaced.")
                elif db.execute(
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

    def rename_location_calendar(self, calendars, dataset_id, old_location, new_location,
                                 *, expected_path, expected_revision, confirmed=False):
        """Keep a confirmed calendar move within an unchanged dataset snapshot."""
        import engine

        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT path FROM datasets WHERE dataset_id=?",
                                 (dataset_id,)).fetchone()
            if current is None or current["path"] != expected_path:
                raise ValueError("The dataset snapshot changed. Reload and review the rename again.")
            locations = set(engine.load_reviews(current["path"])["location"])
            if old_location in locations or new_location not in locations:
                raise ValueError(
                    "The old name must be absent and the new name present in the current reviews.")
            calendars.rename(dataset_id, old_location, new_location,
                             expected_revision=expected_revision, confirmed=confirmed)

    def correct_calendar_link(self, calendars, dataset_id, current_location, new_location,
                              *, expected_path, expected_revision, confirmed=False):
        """Serialize corrections with dataset replacement; never touch actions."""
        import engine
        from location_settings import SettingsConflictError

        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT path FROM datasets WHERE dataset_id=?",
                                 (dataset_id,)).fetchone()
            if current is None or current["path"] != expected_path:
                raise ValueError("The dataset snapshot changed. Reload and review the correction again.")
            locations = set(engine.load_reviews(current["path"])["location"])
            calendars.require_access(dataset_id, [current_location, new_location])
            snapshot = calendars.load(dataset_id).get(current_location)
            if snapshot is None or snapshot["revision"] != expected_revision:
                raise SettingsConflictError("Calendar ownership or timezone changed. Reload and review again.")
            owners = calendars.ownership(dataset_id)
            if new_location not in locations and owners.get(new_location) != current_location:
                raise ValueError("Choose a current review location or a previous name of this calendar.")
            calendars.correct_link(
                dataset_id, current_location, new_location,
                expected_revision=expected_revision, confirmed=confirmed)

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

    def history_link_events(self, dataset_id):
        """Read association changes involving this dataset, newest first.

        Existing associations are not backfilled: their original operation and
        time are unknown. This log is separate from action-field edit history.
        """
        with closing(self.connect()) as db:
            return [
                dict(row) for row in db.execute(
                    "SELECT * FROM history_link_events "
                    "WHERE source_dataset_id = ? OR destination_dataset_id = ? "
                    "ORDER BY event_id DESC",
                    (dataset_id, dataset_id),
                )
            ]

    @staticmethod
    def _record_history_link(db, operation, legacy_tag, source_id, destination_id,
                             *, session=_LOCAL_OWNER):
        """Commit attribution and ownership together, without storing credentials.

        Omitting session is reserved for trusted local-owner maintenance, which
        has no authenticated manager to attribute. An explicitly supplied session
        (including None) must still be valid when the event is written.
        """
        changed_by = None
        if session is not _LOCAL_OWNER:
            account = identity.require_owner(session)
            changed_by = account["username"]
        db.execute(
            "INSERT INTO history_link_events "
            "(source_dataset_id, destination_dataset_id, legacy_tag, operation, occurred_at, "
            "changed_by) VALUES (?, ?, ?, ?, ?, ?)",
            (source_id, destination_id, legacy_tag, operation,
             datetime.now(timezone.utc).isoformat(), changed_by),
        )

    def claim_legacy_history(self, dataset_id, legacy_tag, actions, *, expected_revision=None,
                             session=_LOCAL_OWNER):
        """Link an old filename-scoped history once, without rewriting its log."""
        if session is not _LOCAL_OWNER:
            identity.require_owner(session)
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
            self._record_history_link(
                db, "claim", legacy_tag, None, dataset_id, session=session)
        return self.get(dataset_id)

    def correct_legacy_history(
        self, source_id, legacy_tag, *, expected_source_revision,
        target_id=None, expected_target_revision=None, session=_LOCAL_OWNER,
    ):
        """Atomically detach or transfer only the association, never action records.

        Revisions reject stale confirmations even if a link was removed and then
        restored to the same dataset while the manager's screen was open.
        """
        if session is not _LOCAL_OWNER:
            identity.require_owner(session)
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
            self._record_history_link(
                db, "transfer" if target_id is not None else "unlink",
                legacy_tag, source_id, target_id, session=session,
            )
