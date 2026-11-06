"""Shared location calendars, owned by stable dataset identity + exact location."""

import sqlite3
from contextlib import contextmanager

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
        if not identity.permits(self.session, dataset_id, locations):
            raise PermissionError("You do not have calendar access to this restaurant. "
                                  "Sign in again or ask the app owner for access.")

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
            self.require_access(dataset_id, [location])
            if db.execute(
                "SELECT 1 FROM calendar_renames WHERE dataset_id=? AND old_location=?",
                (dataset_id, location),
            ).fetchone():
                raise SettingsConflictError(
                    "This calendar was renamed. Reload and use its current location.")
            row = db.execute(
                "SELECT revision FROM location_calendars WHERE dataset_id=? AND location=?",
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
