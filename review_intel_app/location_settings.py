"""Shared location calendars, owned by stable dataset identity + exact location."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from action_tracker import DEFAULT_RESTAURANT_TIMEZONE, restaurant_today
import manager_identity as identity


class SettingsConflictError(ValueError):
    pass


class LocationSettings:
    def __init__(self, path, *, session=None):
        self.path = str(path)
        self.session = session
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS location_calendars (
                dataset_id TEXT NOT NULL, location TEXT NOT NULL,
                timezone TEXT NOT NULL, revision INTEGER NOT NULL,
                PRIMARY KEY (dataset_id, location))""")
            db.execute("""CREATE TABLE IF NOT EXISTS calendar_renames (
                dataset_id TEXT NOT NULL, old_location TEXT NOT NULL,
                new_location TEXT NOT NULL,
                PRIMARY KEY (dataset_id, old_location))""")
            # The mutable alias map is not evidence of when a change happened.
            # Existing links deliberately receive no synthetic audit records.
            db.execute("""CREATE TABLE IF NOT EXISTS calendar_rename_history (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                dataset_id TEXT NOT NULL, old_location TEXT NOT NULL,
                new_location TEXT NOT NULL, timezone TEXT NOT NULL,
                changed_at TEXT NOT NULL, change_kind TEXT NOT NULL)""")
            db.execute("""CREATE INDEX IF NOT EXISTS calendar_rename_history_dataset
                ON calendar_rename_history(dataset_id, event_id)""")
            for operation in ("UPDATE", "DELETE"):
                db.execute(f"""CREATE TRIGGER IF NOT EXISTS calendar_history_no_{operation.lower()}
                    BEFORE {operation} ON calendar_rename_history
                    BEGIN SELECT RAISE(ABORT, 'Calendar rename history is append-only'); END""")
            db.execute("""CREATE TABLE IF NOT EXISTS calendar_timezone_history (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                dataset_id TEXT NOT NULL, location TEXT NOT NULL,
                manager TEXT NOT NULL, changed_at TEXT NOT NULL,
                previous_timezone TEXT NOT NULL, new_timezone TEXT NOT NULL,
                revision INTEGER NOT NULL)""")
            db.execute("""CREATE INDEX IF NOT EXISTS calendar_timezone_history_dataset
                ON calendar_timezone_history(dataset_id, event_id)""")
            for operation in ("UPDATE", "DELETE"):
                db.execute(f"""CREATE TRIGGER IF NOT EXISTS timezone_history_no_{operation.lower()}
                    BEFORE {operation} ON calendar_timezone_history
                    BEGIN SELECT RAISE(ABORT, 'Timezone history is append-only'); END""")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def load(self, dataset_id):
        # Deliberately uncached: every manager rerun reads shared settings.
        account = identity.current_account(self.session)
        if account is None:
            raise PermissionError("Sign in to read restaurant calendars.")
        allowed = account["grants"].get(dataset_id, [])
        with self.connect() as db:
            return {
                location: {"timezone": zone, "revision": revision}
                for location, zone, revision in db.execute(
                    "SELECT location, timezone, revision FROM location_calendars "
                    "WHERE dataset_id = ?", (dataset_id,))
                if location in allowed
            }

    def require_access(self, dataset_id, locations):
        account = identity.current_account(self.session)
        if not account or not locations or not set(locations).issubset(
                set(account["grants"].get(dataset_id, []))):
            raise PermissionError("You do not have calendar access to this restaurant. "
                                  "Sign in again or ask the app owner for access.")
        return account

    def timezone_history(self, dataset_id, location):
        """Include prior names only when both original and current names are allowed."""
        self.require_access(dataset_id, [location])
        with self.connect() as db:
            owners = self._ownership(db, dataset_id)
            owner = owners.get(location, location)
            self.require_access(dataset_id, [owner])
            columns = ("event_id", "location", "manager", "changed_at",
                       "previous_timezone", "new_timezone", "revision")
            rows = db.execute(
                "SELECT event_id, location, manager, changed_at, previous_timezone, "
                "new_timezone, revision FROM calendar_timezone_history "
                "WHERE dataset_id=? ORDER BY event_id DESC", (dataset_id,)).fetchall()
            return [dict(zip(columns, row)) for row in rows
                    if owners.get(row[1], row[1]) == owner
                    and identity.permits(self.session, dataset_id, [row[1], owner])]

    @staticmethod
    def _record_timezone(db, dataset_id, location, manager, previous, new, revision):
        db.execute(
            "INSERT INTO calendar_timezone_history "
            "(dataset_id, location, manager, changed_at, previous_timezone, new_timezone, revision) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (dataset_id, location, manager, datetime.now(timezone.utc).isoformat(),
             previous, new, revision))

    @staticmethod
    def _ownership(db, dataset_id):
        """Resolve legacy chains without treating a retired name as available."""
        links = dict(db.execute(
            "SELECT old_location, new_location FROM calendar_renames WHERE dataset_id=?",
            (dataset_id,)))
        owners = {}
        for source in links:
            current, seen = source, set()
            while current in links:
                if current in seen:
                    raise SettingsConflictError("Calendar links are inconsistent. Ask the app owner for help.")
                seen.add(current)
                current = links[current]
            owners[source] = current
        return owners

    def ownership(self, dataset_id):
        """Expose only links whose retired name and current owner are accessible."""
        self.load(dataset_id)  # Require a live session even when there are no links.
        with self.connect() as db:
            return {old: owner for old, owner in self._ownership(db, dataset_id).items()
                    if identity.permits(self.session, dataset_id, [old, owner])}

    def rename_history(self, dataset_id):
        """Read only events whose names and current owner are still accessible."""
        self.load(dataset_id)
        with self.connect() as db:
            owners = self._ownership(db, dataset_id)
            rows = db.execute(
                "SELECT event_id, old_location, new_location, timezone, changed_at, change_kind "
                "FROM calendar_rename_history WHERE dataset_id=? ORDER BY event_id",
                (dataset_id,)).fetchall()
            return [
                dict(zip(("event_id", "old_location", "new_location", "timezone",
                          "changed_at", "change_kind"), row))
                for row in rows
                if identity.permits(self.session, dataset_id,
                                    [row[1], row[2], owners.get(row[2], row[2])])
            ]

    @staticmethod
    def _record_rename(db, dataset_id, old, new, zone, kind):
        db.execute(
            "INSERT INTO calendar_rename_history "
            "(dataset_id, old_location, new_location, timezone, changed_at, change_kind) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (dataset_id, old, new, zone, datetime.now(timezone.utc).isoformat(), kind))

    def correct_link(self, dataset_id, current_location, new_location, *,
                     expected_revision, confirmed=False):
        """Explicitly move an existing linked calendar, including back to an alias."""
        self.require_access(dataset_id, [current_location, new_location])
        if not confirmed:
            raise ValueError("Confirm this calendar ownership correction.")
        if not dataset_id or not new_location or current_location == new_location:
            raise ValueError("Choose two different location names in one dataset.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.require_access(dataset_id, [current_location, new_location])
            owners = self._ownership(db, dataset_id)
            aliases = [old for old, owner in owners.items() if owner == current_location]
            row = db.execute(
                "SELECT timezone, revision FROM location_calendars WHERE dataset_id=? AND location=?",
                (dataset_id, current_location)).fetchone()
            if not aliases or row is None or row[1] != expected_revision:
                raise SettingsConflictError("Calendar ownership or timezone changed. Reload and review again.")
            if (new_location in owners and owners[new_location] != current_location) or db.execute(
                "SELECT 1 FROM location_calendars WHERE dataset_id=? AND location=?",
                (dataset_id, new_location)).fetchone():
                raise SettingsConflictError("The destination belongs to another calendar. Calendars cannot be merged.")
            # Only the new active name is released. All other aliases remain
            # reserved and point directly to the new owner (no cycles).
            db.execute("DELETE FROM calendar_renames WHERE dataset_id=? AND old_location=?",
                       (dataset_id, new_location))
            for alias in set(aliases + [current_location]) - {new_location}:
                db.execute("INSERT INTO calendar_renames VALUES (?, ?, ?) "
                           "ON CONFLICT(dataset_id, old_location) DO UPDATE SET new_location=excluded.new_location",
                           (dataset_id, alias, new_location))
            db.execute("DELETE FROM location_calendars WHERE dataset_id=? AND location=?",
                       (dataset_id, current_location))
            db.execute("INSERT INTO location_calendars VALUES (?, ?, ?, ?)",
                       (dataset_id, new_location, row[0], row[1] + 1))
            self._record_rename(db, dataset_id, current_location, new_location,
                                row[0], "correction")

    @staticmethod
    def default():
        return {"timezone": DEFAULT_RESTAURANT_TIMEZONE, "revision": 0}

    def save(self, dataset_id, location, timezone, *, expected_revision):
        self.require_access(dataset_id, [location])
        timezone = timezone.strip()
        restaurant_today(timezone)  # Validate before touching persistent state.
        if not dataset_id or not location:
            raise ValueError("A dataset and location are required.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            account = self.require_access(dataset_id, [location])
            if db.execute(
                "SELECT 1 FROM calendar_renames WHERE dataset_id=? AND old_location=?",
                (dataset_id, location),
            ).fetchone():
                raise SettingsConflictError(
                    "This calendar was renamed. Reload and use its current location.")
            row = db.execute(
                "SELECT revision, timezone FROM location_calendars WHERE dataset_id=? AND location=?",
                (dataset_id, location)).fetchone()
            if (row[0] if row else 0) != expected_revision:
                raise SettingsConflictError(
                    "Another manager changed this location's timezone. "
                    "Reload the saved timezone before saving again.")
            db.execute(
                "INSERT INTO location_calendars VALUES (?, ?, ?, ?) "
                "ON CONFLICT(dataset_id, location) DO UPDATE SET "
                "timezone=excluded.timezone, revision=excluded.revision",
                (dataset_id, location, timezone, expected_revision + 1))
            self._record_timezone(
                db, dataset_id, location, account["username"],
                row[1] if row else DEFAULT_RESTAURANT_TIMEZONE,
                timezone, expected_revision + 1)

    def rename(self, dataset_id, old_location, new_location, *, expected_revision,
               confirmed=False):
        """Move one calendar, never merge calendars or infer dataset continuity."""
        self.require_access(dataset_id, [old_location, new_location])
        if not confirmed:
            raise ValueError("Confirm that both names refer to the same restaurant.")
        if not dataset_id or not old_location or not new_location or old_location == new_location:
            raise ValueError("Choose two different location names in one dataset.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.require_access(dataset_id, [old_location, new_location])
            if db.execute(
                "SELECT 1 FROM location_calendars WHERE dataset_id=? AND location=? "
                "UNION ALL SELECT 1 FROM calendar_renames "
                "WHERE dataset_id=? AND old_location=?",
                (dataset_id, new_location, dataset_id, new_location),
            ).fetchone():
                raise SettingsConflictError(
                    "The destination already owns a calendar or was previously renamed. "
                    "Calendars cannot be overwritten or merged.")
            row = db.execute(
                "SELECT timezone, revision FROM location_calendars "
                "WHERE dataset_id=? AND location=?", (dataset_id, old_location),
            ).fetchone()
            if row is None or row[1] != expected_revision:
                raise SettingsConflictError("The source calendar changed. Reload and review again.")
            db.execute("DELETE FROM location_calendars WHERE dataset_id=? AND location=?",
                       (dataset_id, old_location))
            db.execute("INSERT INTO location_calendars VALUES (?, ?, ?, ?)",
                       (dataset_id, new_location, row[0], row[1] + 1))
            db.execute("INSERT INTO calendar_renames VALUES (?, ?, ?)",
                       (dataset_id, old_location, new_location))
            self._record_rename(db, dataset_id, old_location, new_location, row[0], "rename")
