"""Private, local manager decisions layered over (never written into) rule results."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

import engine as E


def review_key(file_path, row):
    """Hash all loaded source fields, not tags, so edits invalidate a decision."""
    identity = {
        "file": str(Path(file_path).resolve()),
        "review": {str(k): str(v) for k, v in sorted(dict(row).items())},
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def _connect(path):
    db = sqlite3.connect(path, timeout=10)
    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS corrections (
                review_key TEXT NOT NULL,
                rules_version TEXT NOT NULL,
                positive TEXT NOT NULL,
                negative TEXT NOT NULL,
                saved_at TEXT NOT NULL,
                PRIMARY KEY (review_key, rules_version)
            )
        """)
    except Exception:
        db.close()
        raise
    return db


def _validate(positive, negative):
    if (not isinstance(positive, list) or not isinstance(negative, list)
            or any(not isinstance(t, str) or t not in E.THEMES
                   for t in positive + negative)):
        raise ValueError("Correction contains unsupported theme tags.")
    return sorted(set(positive)), sorted(set(negative))


def save_correction(path, key, positive, negative, version):
    positive, negative = _validate(positive, negative)
    db = _connect(path)
    try:
        with db:
            db.execute("INSERT OR REPLACE INTO corrections VALUES (?, ?, ?, ?, ?)",
                       (key, version, json.dumps(positive), json.dumps(negative),
                        datetime.now(timezone.utc).isoformat()))
    finally:
        db.close()


def undo_correction(path, key, version):
    db = _connect(path)
    try:
        with db:
            db.execute("DELETE FROM corrections WHERE review_key=? AND rules_version=?",
                       (key, version))
    finally:
        db.close()


def load_corrections(path, version):
    if not Path(path).exists():
        return {}
    db = _connect(path)
    try:
        rows = db.execute(
            "SELECT review_key, positive, negative, saved_at FROM corrections "
            "WHERE rules_version=?", (version,)).fetchall()
        result = {}
        for key, positive, negative, saved_at in rows:
            positive, negative = _validate(json.loads(positive), json.loads(negative))
            result[key] = dict(themes_pos=positive, themes_neg=negative,
                               rules_version=version, saved_at=saved_at)
        return result
    finally:
        db.close()


def apply_corrections(raw, tagged, file_path, corrections):
    """Return effective analysis; leave the cached rule frame and evidence untouched."""
    out = tagged.copy(deep=True)
    out["correction_key"] = [review_key(file_path, r) for r in raw.to_dict("records")]
    out["rule_output"] = [
        {k: row[k] for k in ("themes_pos", "themes_neg", "needs_review",
                             "review_reasons", "urgency", "sentiment")}
        for row in tagged.to_dict("records")
    ]
    out["manager_correction"] = None
    out["tag_source"] = "local_rules"
    out["rules_version"] = E.LOCAL_ANALYZER_VERSION
    for index, row in out.iterrows():
        decision = corrections.get(row["correction_key"])
        if decision is None:
            continue
        if decision["rules_version"] != E.LOCAL_ANALYZER_VERSION:
            continue
        pos, neg = _validate(decision["themes_pos"], decision["themes_neg"])
        effective = E.effective_tag_fields(row["text"], row["rating"], pos, neg)
        for field, value in effective.items():
            out.at[index, field] = value
        out.at[index, "needs_review"] = False
        out.at[index, "manager_correction"] = decision
        out.at[index, "tag_source"] = "manager"
        out.at[index, "reply_draft"] = E.draft_reply_offline(out.loc[index].to_dict())
    return out
