"""Verify the real CSV loader and action lifecycle using only synthetic data."""

import csv
from datetime import date, timedelta
import io
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import action_tracker as A
import dataset_store as D
import engine as E
from dataset_store import DatasetStore, SAMPLE_ID


SAMPLE = Path(__file__).parent / "data" / "sample_reviews.csv"


class ReviewActionFlowTests(unittest.TestCase):
    def test_upload_controls_keep_new_uploads_and_explicit_updates_separate(self):
        content = (
            b"location,date,rating,text\n"
            b"Demo Cafe,2026-01-01,1,Service was slow.\n"
            b"Demo Cafe,2026-01-02,5,Quick service.\n"
        )
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sample = root / "sample.csv"
            sample.write_bytes(content)
            store = DatasetStore(root / "uploads", sample)
            upload = SimpleNamespace(name="sample.csv", file_id="first",
                                     getvalue=lambda: content)
            analyze = E.analyze_offline
            # Keep this UI check focused on upload controls, not the unrelated
            # manager-correction selectbox's AppTest formatter state.
            with patch.object(D, "DatasetStore", return_value=store), patch(
                "streamlit.delta_generator.DeltaGenerator.file_uploader",
                return_value=upload,
            ) as uploader, patch.object(A, "load_actions", return_value=[]), patch.object(
                E, "analyze_offline",
                side_effect=lambda raw: analyze(raw).assign(engine="upload_ui_fixture"),
            ):
                app = AppTest.from_file(str(SAMPLE.parent.parent / "app.py"),
                                       default_timeout=30).run()

                def radio(label):
                    return next(item for item in app.sidebar.radio if item.label == label)

                def save():
                    next(item for item in app.sidebar.button
                         if item.label == "Save CSV").click().run()
                    self.assertEqual(list(app.exception), [])

                radio("Data").set_value("Upload my reviews (CSV)").run()
                self.assertEqual(len(store.list_datasets()), 0)
                save()
                first = store.list_datasets()[0]
                app.run()
                self.assertEqual(len(store.list_datasets()), 1)

                uploader.return_value = SimpleNamespace(
                    name="sample.csv", file_id="unrelated", getvalue=lambda: content
                )
                app.run()
                save()
                self.assertEqual(len(store.list_datasets()), 2)
                self.assertEqual(store.get(first["dataset_id"]), first)

                newer = content + b"Demo Cafe,2026-01-03,5,Quick service.\n"
                uploader.return_value = SimpleNamespace(
                    name="newer.csv", file_id="update", getvalue=lambda: newer
                )
                radio("Upload purpose").set_value("Update an existing dataset").run()
                next(item for item in app.sidebar.selectbox
                     if item.label == "Dataset to update").set_value(first["dataset_id"]).run()
                save()
                updated = store.get(first["dataset_id"])
                self.assertEqual(len(store.list_datasets()), 2)
                self.assertEqual(Path(updated["path"]).read_bytes(), newer)
                self.assertEqual(Path(first["path"]).read_bytes(), content)

                uploader.return_value = SimpleNamespace(
                    name="newer.csv", file_id="bad", getvalue=lambda: b"wrong,columns\n1,2\n"
                )
                app.run()
                save()
                self.assertTrue(any("Couldn't save that CSV" in item.value for item in app.error))
                self.assertEqual(store.get(first["dataset_id"]), updated)

                radio("Data").set_value("Saved file").run()
                next(item for item in app.sidebar.selectbox
                     if item.label == "Dataset").set_value(first["dataset_id"]).run()
                self.assertEqual(list(app.exception), [])
                self.assertTrue(any(first["dataset_id"] in item.value
                                    for item in app.sidebar.caption))
                self.assertEqual(sample.read_bytes(), content)

    def test_colliding_uploads_and_explicit_updates_use_real_csv_follow_up(self):
        original = (
            "review_id,location,date,rating,text\n"
            "r1,Demo Cafe,2026-01-01,1,Service was slow.\n"
        ).encode()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sample = root / "sample.csv"
            sample.write_bytes(original)
            store = DatasetStore(root / "uploads", sample)
            first = store.save_snapshot("sample.csv", original)
            unrelated = store.save_snapshot("sample.csv", original)
            action = A.create_action(
                first["dataset_id"],
                {"location": "Demo Cafe", "theme": "Service speed",
                 "recent_share": 100, "recent_mentions": 1},
                "service_speed", "Check handoffs.", "Manager",
                date(2026, 1, 1), date(2026, 1, 10), date(2026, 1, 1),
            )
            action["status"] = "In progress"
            log = str(root / "actions.json")
            A.save_actions(log, [action])
            original_log = Path(log).read_bytes()
            appended = original + "".join(
                f"new{i},Demo Cafe,2026-01-0{i + 2},5,Quick service.\n"
                for i in range(5)
            ).encode()
            updated = store.save_snapshot("snapshot.csv", appended, first["dataset_id"])
            # A corrected existing review is also a legitimate replacement.
            corrected = appended.replace(b"Service was slow.", b"Quick service.")
            updated = store.save_snapshot("corrected.csv", corrected, updated["dataset_id"])
            restarted = DatasetStore(root / "uploads", sample)
            saved = A.load_actions(log, restarted.get(first["dataset_id"])["dataset_id"])[0]
            tagged = E.analyze_offline(E.load_reviews(updated["path"]))
            result = A.follow_up(saved, tagged.to_dict("records"))
            self.assertTrue(result["ready"])
            self.assertEqual(result["review_count"], 5)
            self.assertEqual(result["mentions"], 0)
            self.assertEqual(result["baseline_share"], 100)
            self.assertEqual(A.load_actions(log, unrelated["dataset_id"]), [])
            self.assertEqual(A.load_actions(log, SAMPLE_ID), [])
            self.assertEqual(Path(log).read_bytes(), original_log)
            self.assertEqual(Path(first["path"]).read_bytes(), original)

    def test_sample_loads_without_changing_its_columns_or_source_file(self):
        original = SAMPLE.read_bytes()
        columns = next(csv.reader(io.StringIO(original.decode("utf-8"))))
        loaded = E.load_reviews(SAMPLE)

        self.assertEqual(list(loaded.columns), columns)
        self.assertEqual(len(loaded), 930)
        self.assertEqual(set(loaded["source"]), {"synthetic"})
        self.assertEqual(SAMPLE.read_bytes(), original)

    def test_alert_action_update_and_follow_up_stay_with_the_dataset(self):
        reviews = E.load_reviews(SAMPLE)
        tagged = E.analyze_offline(reviews)
        alerts = E.early_warnings(tagged)
        alert = alerts[alerts["theme"] == "Service speed"].iloc[0].to_dict()
        start = reviews["date"].max().date()
        action = A.create_action(
            "sample", alert, "service_speed", "Check service handoffs.",
            "", start, start + timedelta(days=7), start,
        )
        self.assertEqual(A.follow_up(action, [])["reason"], "not_started")
        updated = A.update_action(
            action, "Review the handoff checklist.", "Manager", "In progress",
            start, start + timedelta(days=10),
        )
        other_action = A.create_action(
            "another-file", alert, "service_speed", "Check service handoffs.",
            "", start, start + timedelta(days=7), start,
        )

        with tempfile.TemporaryDirectory() as folder:
            log = str(Path(folder) / "actions.json")
            A.save_actions(log, [action, other_action])
            all_actions = A.load_actions(log)
            A.save_actions(log, [
                updated if row["action_id"] == action["action_id"] else row
                for row in all_actions
            ])
            saved = A.load_actions(log, "sample")[0]
            self.assertEqual(saved, updated)
            self.assertEqual(A.load_actions(log, "another-file"), [other_action])
            self.assertEqual(saved["baseline_share"], action["baseline_share"])
            self.assertEqual(saved["alert_end_date"], action["alert_end_date"])
            self.assertEqual(saved["status"], "In progress")
            self.assertEqual(action["status"], "Planned")

        with SAMPLE.open(newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            columns = reader.fieldnames
            rows = list(reader)
        for i in range(5):
            rows.append({
                "review_id": f"synthetic-follow-up-{i}",
                "location": saved["location"],
                "date": (start + timedelta(days=i + 1)).isoformat(),
                "rating": 1 if i == 0 else 5,
                "reviewer": "Guest",
                "text": "Service was slow." if i == 0 else "Quick service.",
                "source": "synthetic",
            })

        def check(rows_to_load):
            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows_to_load)
            buffer.seek(0)
            newer = E.analyze_offline(E.load_reviews(buffer))
            return A.follow_up(saved, newer.to_dict("records"))

        waiting = check(rows[:-1])
        self.assertFalse(waiting["ready"])
        self.assertEqual(waiting["review_count"], 4)
        ready = check(rows)
        self.assertTrue(ready["ready"])
        self.assertEqual(ready["review_count"], 5)
        self.assertEqual(ready["mentions"], 1)
        self.assertEqual(ready["share"], 20.0)
        self.assertEqual(ready["direction"], "lower")
        self.assertEqual(ready["baseline_share"], saved["baseline_share"])


if __name__ == "__main__":
    unittest.main()
