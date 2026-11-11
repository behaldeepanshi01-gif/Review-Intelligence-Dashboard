"""Owner authority is explicit, revocable, and independent of location grants."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import dataset_store as D
import manager_identity as M
from dashboard_access import DashboardAccess


class OwnerDatasetTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        storage = patch.object(M, "DB_PATH", self.root / "accounts.sqlite")
        storage.start()
        self.addCleanup(storage.stop)
        self.content = b"location,date,rating,text\nCafe,2026-01-01,5,Good food\n"
        sample = self.root / "sample.csv"
        sample.write_bytes(self.content)
        self.store = D.DatasetStore(self.root / "uploads", sample)
        self.target = self.store.save_snapshot("a.csv", self.content)
        self.other = self.store.save_snapshot("b.csv", self.content)
        self.rows = [{"dataset_tag": "old.csv", "location": "Cafe", "baseline": {"count": 3}}]
        M.set_account("owner", "synthetic-owner-password", {}, is_owner=True)
        self.session = M.authenticate("owner", "synthetic-owner-password")
        self.access = DashboardAccess(self.session)
        M.set_account("manager", "synthetic-manager-password",
                      {self.target["dataset_id"]: ["Cafe"]})
        self.manager = M.authenticate("manager", "synthetic-manager-password")

    def test_registration_confirmation_validation_and_no_implicit_grants(self):
        before = self.store.list_datasets(True)
        with self.assertRaises(ValueError):
            self.access.register_dataset(self.store, "a.csv", self.content)
        with self.assertRaises(ValueError):
            self.access.register_dataset(self.store, "a.csv", b"bad\ncsv\n", confirmed=True)
        self.assertEqual(before, self.store.list_datasets(True))
        created = self.access.register_dataset(self.store, "a.csv", self.content, confirmed=True)
        self.assertNotEqual(created["dataset_id"], self.target["dataset_id"])
        self.assertIsNone(created["legacy_tag"])
        self.assertEqual(Path(created["path"]).read_bytes(), self.content)
        self.assertEqual(self.store.get(self.target["dataset_id"]), self.target)
        self.assertEqual(self.access.datasets(self.store, True), [])
        self.assertFalse(M.permits(self.session, created["dataset_id"], ["Cafe"]))

    def test_manager_and_invalid_sessions_denied_without_mutations(self):
        before = self.store.list_datasets(True)
        for session in [self.manager, None, {}, dict(self.session, expires=0)]:
            access = DashboardAccess(session)
            for operation in [
                lambda: access.owner_datasets(self.store),
                lambda: access.owner_actions("unused"),
                lambda: access.register_dataset(self.store, "x.csv", self.content, confirmed=True),
                lambda: self.store.save_snapshot("x.csv", self.content, session=session),
                lambda: self.store.claim_legacy_history(
                    self.target["dataset_id"], "old.csv", self.rows, session=session),
                lambda: self.store.correct_legacy_history(
                    self.target["dataset_id"], "old.csv", expected_source_revision=0, session=session),
            ]:
                with self.assertRaises(PermissionError):
                    operation()
        self.assertEqual(before, self.store.list_datasets(True))
        self.assertEqual(self.store.history_link_events(self.target["dataset_id"]), [])

    def test_claim_transfer_unlink_stale_and_revocation(self):
        source = self.store.claim_legacy_history(
            self.target["dataset_id"], "old.csv", self.rows,
            expected_revision=0, session=self.session)
        self.store.correct_legacy_history(
            source["dataset_id"], "old.csv", expected_source_revision=source["history_revision"],
            target_id=self.other["dataset_id"], expected_target_revision=0, session=self.session)
        with self.assertRaises(ValueError):
            self.store.correct_legacy_history(
                source["dataset_id"], "old.csv", expected_source_revision=source["history_revision"],
                session=self.session)
        target = self.store.get(self.other["dataset_id"])
        M.set_account("owner", "synthetic-owner-password", {}, is_owner=False)
        with self.assertRaises(PermissionError):
            self.store.correct_legacy_history(
                target["dataset_id"], "old.csv",
                expected_source_revision=target["history_revision"], session=self.session)
        self.assertEqual(self.store.get(target["dataset_id"]), target)
        for dataset in [source, target]:
            self.assertEqual(Path(dataset["path"]).read_bytes(), self.content)

    def test_legacy_account_schema_never_promotes_users(self):
        with sqlite3.connect(M.DB_PATH) as db:
            db.execute("ALTER TABLE managers DROP COLUMN is_owner")
        self.assertFalse(DashboardAccess(self.session).is_owner())
        M.set_account("new-owner", "synthetic-owner-password", {}, is_owner=True)
        self.assertFalse(DashboardAccess(self.session).is_owner())
        self.assertTrue(DashboardAccess(M.authenticate(
            "new-owner", "synthetic-owner-password")).is_owner())


if __name__ == "__main__":
    unittest.main()
