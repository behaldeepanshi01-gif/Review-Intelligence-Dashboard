"""Local identities shared by protected features. No implicit dataset grants."""
import hashlib
import hmac
import json
from contextlib import closing
from pathlib import Path
import secrets
import sqlite3
import time

DB_PATH = Path(__file__).parent / "data" / "manager_accounts.sqlite"
SESSION_SECONDS = 1800


def _read(username):
    # Reads never create a database. Missing or broken storage fails closed.
    try:
        with closing(sqlite3.connect(f"{DB_PATH.resolve().as_uri()}?mode=ro", uri=True)) as db:
            return db.execute("SELECT salt, digest, grants, revision FROM managers "
                              "WHERE username=?", (username,)).fetchone()
    except sqlite3.Error:
        return None


def configured():
    try:
        with closing(sqlite3.connect(f"{DB_PATH.resolve().as_uri()}?mode=ro", uri=True)) as db:
            return bool(db.execute("SELECT 1 FROM managers LIMIT 1").fetchone())
    except sqlite3.Error:
        return False


def set_account(username, password, grants):
    """Trusted local operator only. Replaces exact grants and revokes old sessions."""
    if not username or username != username.strip() or len(password) < 16:
        raise ValueError("Use a manager ID and a password of at least 16 characters.")
    if not isinstance(grants, dict) or any(
        not isinstance(dataset, str) or not dataset or not isinstance(locations, list)
        or any(not isinstance(loc, str) or not loc for loc in locations)
        for dataset, locations in grants.items()
    ):
        raise ValueError("Permissions must map dataset IDs to lists of exact location names.")
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt),
                            n=16384, r=8, p=1).hex()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(DB_PATH)) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS managers "
                   "(username TEXT PRIMARY KEY, salt TEXT, digest TEXT, grants TEXT, revision TEXT)")
        db.execute("INSERT OR REPLACE INTO managers VALUES (?, ?, ?, ?, ?)",
                   (username, salt, digest, json.dumps(grants), secrets.token_hex(32)))
    DB_PATH.chmod(0o600)


def remove_account(username):
    if DB_PATH.exists():
        with closing(sqlite3.connect(DB_PATH)) as db, db:
            db.execute("DELETE FROM managers WHERE username=?", (username,))


def authenticate(username, password):
    row = _read(username)
    salt = row[0] if row else "0" * 32
    try:
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt),
                                n=16384, r=8, p=1).hex()
        if row and hmac.compare_digest(digest, row[1]):
            return {"username": username, "revision": row[3],
                    "expires": time.time() + SESSION_SECONDS}
    except (ValueError, TypeError):
        pass
    return None


def current_account(session):
    if not isinstance(session, dict):
        return None
    try:
        if time.time() >= session.get("expires", 0):
            return None
        row = _read(session.get("username", ""))
        if row and hmac.compare_digest(row[3], session.get("revision", "")):
            return {"username": session["username"], "grants": json.loads(row[2])}
    except (ValueError, TypeError):
        pass
    return None


def permits(session, dataset_id, locations):
    """Exact dataset ID, no filename fallback, wildcard, or partial-selection access."""
    account = current_account(session)
    if not account or not locations:
        return False
    return set(locations).issubset(set(account["grants"].get(dataset_id, [])))
