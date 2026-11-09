"""Private, local manager decisions layered over (never written into) rule results."""

from datetime import datetime, timedelta, timezone
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
        # Serialize additive migration across sessions; never recreate local data.
        with db:
            db.execute("BEGIN IMMEDIATE")
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
            columns = {row[1] for row in db.execute("PRAGMA table_info(corrections)")}
            for name, definition in (
                ("decision_origin", "TEXT NOT NULL DEFAULT 'legacy'"),
                ("source_rules_version", "TEXT"),
                ("source_decision_revision", "TEXT"),
            ):
                if name not in columns:
                    db.execute(f"ALTER TABLE corrections ADD COLUMN {name} {definition}")
            db.execute("""
                CREATE TABLE IF NOT EXISTS correction_revisions (
                    review_key TEXT NOT NULL,
                    rules_version TEXT NOT NULL,
                    positive TEXT NOT NULL,
                    negative TEXT NOT NULL,
                    saved_at TEXT NOT NULL,
                    decision_origin TEXT NOT NULL,
                    source_rules_version TEXT,
                    source_decision_revision TEXT,
                    PRIMARY KEY (review_key, rules_version, saved_at)
                )
            """)
            # Preserve surviving legacy decisions verbatim, including their revision
            # references. Decisions removed before this migration cannot be recovered.
            db.execute("""
                INSERT OR IGNORE INTO correction_revisions
                SELECT review_key, rules_version, positive, negative, saved_at,
                       decision_origin, source_rules_version, source_decision_revision
                FROM corrections
            """)
            for operation in ("UPDATE", "DELETE"):
                db.execute(f"""
                    CREATE TRIGGER IF NOT EXISTS correction_revisions_no_{operation.lower()}
                    BEFORE {operation} ON correction_revisions
                    BEGIN
                        SELECT RAISE(ABORT, 'Tag revision archive is append-only');
                    END
                """)
    except Exception:
        db.close()
        raise
    return db


def _validate(positive, negative, *, allow_obsolete=False):
    if (not isinstance(positive, list) or not isinstance(negative, list)
            or any(not isinstance(t, str) or (not allow_obsolete and t not in E.THEMES)
                   for t in positive + negative)):
        raise ValueError("Correction contains unsupported theme tags.")
    return sorted(set(positive)), sorted(set(negative))


def _next_revision(db, key, version):
    """Keep saved-at references unique even if the clock repeats or moves back."""
    instant = datetime.now(timezone.utc)
    for (saved_at,) in db.execute(
            "SELECT saved_at FROM correction_revisions "
            "WHERE review_key=? AND rules_version=?", (key, version)):
        try:
            previous = datetime.fromisoformat(saved_at)
            if previous.tzinfo is not None and previous >= instant:
                instant = previous + timedelta(microseconds=1)
        except ValueError:
            pass  # Legacy revision strings remain valid lookup keys.
    return instant.isoformat()


def _archive_current(db, key, version):
    db.execute("""
        INSERT OR IGNORE INTO correction_revisions
        SELECT review_key, rules_version, positive, negative, saved_at,
               decision_origin, source_rules_version, source_decision_revision
        FROM corrections WHERE review_key=? AND rules_version=?
    """, (key, version))


def save_correction(path, key, positive, negative, version):
    positive, negative = _validate(positive, negative)
    db = _connect(path)
    try:
        with db:
            db.execute("BEGIN IMMEDIATE")
            _archive_current(db, key, version)
            revision = _next_revision(db, key, version)
            db.execute(
                "INSERT OR REPLACE INTO corrections "
                "(review_key, rules_version, positive, negative, saved_at, "
                "decision_origin, source_rules_version, source_decision_revision) "
                "VALUES (?, ?, ?, ?, ?, 'correction', NULL, NULL)",
                       (key, version, json.dumps(positive), json.dumps(negative),
                        revision))
            _archive_current(db, key, version)
    finally:
        db.close()


def undo_correction(path, key, version):
    db = _connect(path)
    try:
        with db:
            db.execute("BEGIN IMMEDIATE")
            _archive_current(db, key, version)
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
            "SELECT review_key, positive, negative, saved_at, decision_origin, "
            "source_rules_version, source_decision_revision FROM corrections "
            "WHERE rules_version=?", (version,)).fetchall()
        result = {}
        for key, positive, negative, saved_at, origin, source_version, source_revision in rows:
            positive, negative = _validate(json.loads(positive), json.loads(negative))
            result[key] = dict(themes_pos=positive, themes_neg=negative,
                               rules_version=version, saved_at=saved_at,
                               decision_origin=origin, source_rules_version=source_version,
                               source_decision_revision=source_revision)
        return result
    finally:
        db.close()


def load_prior_corrections(path, version):
    """History only, newest saved first; never use this mapping as effective tags."""
    if not Path(path).exists():
        return {}
    db = _connect(path)
    try:
        rows = db.execute(
            "SELECT review_key, rules_version, positive, negative, saved_at, "
            "decision_origin, source_rules_version, source_decision_revision "
            "FROM corrections WHERE rules_version != ? "
            "ORDER BY saved_at DESC, rules_version DESC", (version,)).fetchall()
        result = {}
        for (key, prior_version, positive, negative, saved_at, origin,
             source_version, source_revision) in rows:
            # Retired themes are valid history, not valid current decisions.
            positive, negative = _validate(json.loads(positive), json.loads(negative),
                                           allow_obsolete=True)
            result.setdefault(key, []).append(dict(
                themes_pos=positive, themes_neg=negative,
                rules_version=prior_version, saved_at=saved_at, decision_origin=origin,
                source_rules_version=source_version,
                source_decision_revision=source_revision))
        return result
    finally:
        db.close()


def load_correction_revisions(path, key):
    """Read-only history for one exact review; never an approval candidate list."""
    if not Path(path).exists():
        return []
    db = _connect(path)
    try:
        rows = db.execute(
            "SELECT rules_version, positive, negative, saved_at, decision_origin, "
            "source_rules_version, source_decision_revision FROM correction_revisions "
            "WHERE review_key=? ORDER BY saved_at DESC, rules_version DESC",
            (key,)).fetchall()
        result = []
        for version, pos, neg, revision, origin, source_version, source_revision in rows:
            pos, neg = _validate(json.loads(pos), json.loads(neg), allow_obsolete=True)
            result.append(dict(
                rules_version=version, themes_pos=pos, themes_neg=neg,
                saved_at=revision, decision_origin=origin,
                source_rules_version=source_version,
                source_decision_revision=source_revision))
        return result
    finally:
        db.close()


def find_correction_revision(revisions, version, saved_at):
    """Resolve the exact source reference, never the latest decision for its rules."""
    return next((r for r in revisions if r["rules_version"] == version
                 and r["saved_at"] == saved_at), None)


def decision_origin_label(decision):
    """Describe recorded origin, without inferring provenance for legacy rows."""
    if decision.get("decision_origin") == "renewal":
        return (
            "Renewed approval — source rules: "
            f"{decision['source_rules_version']} | "
            f"Source decision revision (saved at): {decision['source_decision_revision']}"
        )
    if decision.get("decision_origin") == "correction":
        return "Newly entered manager correction — not a renewed approval."
    return "Legacy manager decision — origin not recorded."


def renewal_queue(raw, file_path, current, prior):
    """Only exact source matches without an existing current-version decision."""
    keys = dict.fromkeys(review_key(file_path, row) for row in raw.to_dict("records"))
    return {key: prior[key] for key in keys if key in prior and key not in current}


def tagging_provenance(raw, file_path, corrections, version):
    """Fingerprint applicable decisions in a location, excluding save timestamps.

    Pass the full location, not a date-filtered dashboard view, so changing UI
    filters cannot invalidate a comparison. New uncorrected reviews do not change
    this fingerprint; corrections on unrelated locations/datasets are excluded.
    """
    keys = {review_key(file_path, row) for row in raw.to_dict("records")}
    decisions = {}
    for key in sorted(keys):
        decision = corrections.get(key)
        if decision is None or decision["rules_version"] != version:
            continue
        positive, negative = _validate(decision["themes_pos"], decision["themes_neg"])
        decisions[key] = {"positive": positive, "negative": negative}
    fingerprint = hashlib.sha256(
        json.dumps(decisions, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    # No review text, guest identity, save timestamps or source paths in action logs.
    return {"rules_version": version, "decisions_fingerprint": fingerprint,
            "decisions_version": 1, "decisions": decisions}


def approve_prior_correction(path, file_path, row, decision, version):
    """Explicitly approve one displayed historical decision for this exact review.

    Re-read history inside the write transaction so a stale screen cannot approve
    an edited/deleted decision or overwrite a current decision.
    """
    if decision["rules_version"] == version:
        raise ValueError("Choose a decision from an earlier rules version.")
    key = review_key(file_path, row)
    positive, negative = _validate(decision["themes_pos"], decision["themes_neg"])
    db = _connect(path)
    try:
        with db:
            db.execute("BEGIN IMMEDIATE")
            saved = db.execute(
                "SELECT positive, negative, saved_at FROM corrections "
                "WHERE review_key=? AND rules_version=?",
                (key, decision["rules_version"])).fetchone()
            if (saved is None or json.loads(saved[0]) != positive
                    or json.loads(saved[1]) != negative
                    or saved[2] != decision["saved_at"]):
                raise ValueError("The earlier decision changed. Refresh and review it again.")
            if db.execute(
                    "SELECT 1 FROM corrections WHERE review_key=? AND rules_version=?",
                    (key, version)).fetchone():
                raise ValueError("This review already has a current decision. Refresh to see it.")
            # saved_at is the existing decision revision used by stale-screen
            # validation. Capture the selected source, not the latest history.
            db.execute(
                "INSERT INTO corrections "
                "(review_key, rules_version, positive, negative, saved_at, "
                "decision_origin, source_rules_version, source_decision_revision) "
                "VALUES (?, ?, ?, ?, ?, 'renewal', ?, ?)",
                       (key, version, json.dumps(positive), json.dumps(negative),
                        _next_revision(db, key, version),
                        decision["rules_version"], saved[2]))
            _archive_current(db, key, version)
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
