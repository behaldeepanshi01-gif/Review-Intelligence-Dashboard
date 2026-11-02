"""Shared location calendars, owned by stable dataset identity + exact location."""

import sqlite3
from contextlib import contextmanager

from action_tracker import DEFAULT_RESTAURANT_TIMEZONE, restaurant_today


class SettingsConflictError(ValueError):
    pass


class LocationSettings:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS location_calendars (
                dataset_id TEXT NOT NULL, location TEXT NOT NULL,
                timezone TEXT NOT NULL, revision INTEGER NOT NULL,
                PRIMARY KEY (dataset_id, location))""")

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
        with self.connect() as db:
            return {
                location: {"timezone": zone, "revision": revision}
                for location, zone, revision in db.execute(
                    "SELECT location, timezone, revision FROM location_calendars "
                    "WHERE dataset_id = ?", (dataset_id,))
            }

    @staticmethod
    def default():
        return {"timezone": DEFAULT_RESTAURANT_TIMEZONE, "revision": 0}

    def save(self, dataset_id, location, timezone, *, expected_revision):
        timezone = timezone.strip()
        restaurant_today(timezone)  # Validate before touching persistent state.
        if not dataset_id or not location:
            raise ValueError("A dataset and location are required.")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
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
