"""Server-side dashboard scopes, using the existing local manager accounts."""
import io
import pandas as pd

import action_tracker as actions
import engine
import manager_identity as identity


class DashboardAccess:
    def __init__(self, session):
        self.session = session

    def grants(self):
        account = identity.current_account(self.session)
        if not account:
            raise PermissionError("Dashboard access expired or was removed. Sign in again.")
        return account["grants"]

    def require(self, dataset_id, locations=None):
        grants = self.grants()
        allowed = grants.get(dataset_id, [])
        if not allowed or (locations is not None and (
                not locations or not set(locations).issubset(allowed))):
            raise PermissionError("You are not assigned to this dataset and restaurant.")
        return allowed

    def datasets(self, store, include_sample=False):
        grants = self.grants()
        return [row for row in store.list_datasets(include_sample=include_sample)
                if grants.get(row["dataset_id"])]

    def reviews(self, dataset):
        allowed = self.require(dataset["dataset_id"])
        frame = engine.load_reviews(dataset["path"])
        self.require(dataset["dataset_id"])
        return frame[frame["location"].isin(allowed)].copy()

    def actions(self, path, dataset):
        allowed = self.require(dataset["dataset_id"])
        rows = actions.load_actions(path)
        self.require(dataset["dataset_id"])
        return [row for row in rows
                if actions.matches_dataset(row, dataset["dataset_id"], dataset["legacy_tag"])
                and row.get("location") in allowed]

    def validate_replacement(self, store, dataset_id, content):
        """Replacing a snapshot affects every location, including rejected CSV rows."""
        self.require(dataset_id)
        dataset = store.get(dataset_id)
        for source in (dataset["path"], io.BytesIO(content)):
            frame = pd.read_csv(source)
            if "location" not in frame or frame["location"].isna().any():
                raise ValueError("Every uploaded row must have an assigned location.")
            self.require(dataset_id, frame["location"].astype(str).tolist())
        return dataset["path"]

    def save_snapshot(self, store, name, content, dataset_id):
        # No implicit grant creation, wildcard permissions or filename ownership.
        checked_path = self.validate_replacement(store, dataset_id, content)
        self.require(dataset_id)
        return store.save_snapshot(
            name, content, dataset_id, expected_path=checked_path)
