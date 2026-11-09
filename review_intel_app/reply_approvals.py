"""Local reply approvals, separate from manager tag decisions.

Approved text is stored verbatim. Only an explicit wording approval replaces
its tag snapshot; loading or changing a tag decision never writes here.
"""
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from dashboard_access import DashboardAccess


def _connect(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    try:
        with db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS reply_approvals (
                    dataset_id TEXT NOT NULL,
                    review_key TEXT NOT NULL,
                    location TEXT NOT NULL,
                    source TEXT NOT NULL,
                    wording TEXT NOT NULL,
                    tag_snapshot TEXT,
                    analysis_context TEXT NOT NULL,
                    approved_by TEXT NOT NULL,
                    approved_at TEXT NOT NULL,
                    PRIMARY KEY (dataset_id, review_key)
                )
            """)
        path.chmod(0o600)
    except Exception:
        db.close()
        raise
    return db


def load(path, session, dataset_id):
    """Read only restaurants currently assigned to the existing manager account."""
    access = DashboardAccess(session)
    allowed = access.require(dataset_id)
    with closing(_connect(path)) as db:
        rows = db.execute(
            "SELECT review_key, location, wording, tag_snapshot "
            "FROM reply_approvals WHERE dataset_id=?", (dataset_id,)).fetchall()
    access.require(dataset_id, allowed)
    return {
        key: {"wording": wording,
              "tags": json.loads(snapshot) if snapshot is not None else None}
        for key, location, wording, snapshot in rows if location in allowed
    }


def save(path, session, dataset_id, review_key, source, wording, tags, analysis_context):
    """Publish wording and its exact context atomically after checking access."""
    location = str(source["location"])
    access = DashboardAccess(session)
    access.require(dataset_id, [location])
    if not isinstance(wording, str) or tags.get("review_key") != review_key:
        raise ValueError("Reply approval must include wording and its exact tag context.")
    source_json = json.dumps(
        {str(k): str(v) for k, v in sorted(dict(source).items())}, ensure_ascii=False)
    with closing(_connect(path)) as db, db:
        access.require(dataset_id, [location])
        db.execute("""
            INSERT OR REPLACE INTO reply_approvals
            (dataset_id, review_key, location, source, wording, tag_snapshot,
             analysis_context, approved_by, approved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (dataset_id, review_key, location, source_json, wording,
              json.dumps(tags, ensure_ascii=False),
              json.dumps(analysis_context, ensure_ascii=False),
              session["username"], datetime.now(timezone.utc).isoformat()))
