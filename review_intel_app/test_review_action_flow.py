"""Verify the real CSV loader and action lifecycle using only synthetic data."""

import csv
from datetime import date, timedelta
import io
from pathlib import Path
import tempfile
import unittest
import copy
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

import action_tracker as A
import dataset_store as D
import engine as E
import manager_corrections as C
from dataset_store import DatasetStore, SAMPLE_ID


SAMPLE = Path(__file__).parent / "data" / "sample_reviews.csv"


class ActionProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "synthetic.csv"
        self.db = self.root / "decisions.sqlite"
        self.raw = pd.DataFrame([
            {"review_id": str(i), "location": "Demo Cafe",
             "date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=i),
             "rating": 1, "text": "Service was slow."}
            for i in range(8)
        ])
        self.version = E.LOCAL_ANALYZER_VERSION

    def provenance(self, raw=None, version=None):
        version = version or self.version
        return C.tagging_provenance(
            self.raw if raw is None else raw, self.path,
            C.load_corrections(self.db, version), version)

    def action(self, provenance):
        action = A.create_action(
            "synthetic", {"location": "Demo Cafe", "theme": "Service speed",
                          "recent_share": 60, "recent_mentions": 3},
            "service_speed", "Check handoffs.", "Manager",
            date(2026, 1, 2), date(2026, 1, 20), date(2026, 1, 2),
            tagging_provenance=provenance,
        )
        action["status"] = "In progress"
        return action

    def compare(self, action, provenance):
        tagged = C.apply_corrections(
            self.raw, E.analyze_offline(self.raw), self.path,
            C.load_corrections(self.db, self.version))
        return A.follow_up(
            action, tagged.to_dict("records"), current_provenance=provenance)

    def test_correction_changes_undo_and_rules_upgrade_preserve_saved_baseline(self):
        action = self.action(self.provenance())
        log = str(self.root / "actions.json")
        A.save_actions(log, [action])
        original = Path(log).read_bytes()
        action = A.load_actions(log)[0]
        self.assertEqual(self.compare(action, self.provenance())["provenance_status"],
                         "unchanged")
        key = C.review_key(self.path, self.raw.iloc[3])
        C.save_correction(self.db, key, [], [], self.version)
        corrected = self.compare(action, self.provenance())
        self.assertTrue(corrected["ready"])
        self.assertEqual(corrected["mentions"], 5)
        self.assertEqual(corrected["provenance_status"], "changed")
        self.assertIn("manager decisions changed", corrected["provenance_message"])
        C.undo_correction(self.db, key, self.version)
        self.assertEqual(self.compare(action, self.provenance())["provenance_status"],
                         "unchanged")

        C.save_correction(self.db, key, [], [], self.version)
        corrected_action = self.action(self.provenance())
        C.save_correction(self.db, key, [], ["service_speed"], self.version)
        self.assertEqual(self.compare(corrected_action, self.provenance())[
            "provenance_status"], "changed")
        C.save_correction(self.db, key, [], [], self.version)
        self.assertEqual(self.compare(corrected_action, self.provenance())[
            "provenance_status"], "unchanged")
        C.undo_correction(self.db, key, self.version)
        self.assertEqual(self.compare(corrected_action, self.provenance())[
            "provenance_status"], "changed")
        with patch.object(E, "LOCAL_ANALYZER_VERSION", "synthetic-upgrade"):
            upgraded = self.compare(action, self.provenance(version="synthetic-upgrade"))
        self.assertEqual(upgraded["provenance_status"], "changed")
        self.assertIn("local rules changed", upgraded["provenance_message"])
        self.assertEqual(action["baseline_share"], 60)
        self.assertEqual(Path(log).read_bytes(), original)

    def test_fingerprint_ignores_timestamps_order_and_unrelated_decisions(self):
        key = C.review_key(self.path, self.raw.iloc[0])
        C.save_correction(self.db, key, ["service_speed", "price"], [], self.version)
        first = self.provenance()
        C.save_correction(self.db, key, ["price", "service_speed", "price"], [], self.version)
        self.assertEqual(self.provenance(), first)
        self.assertEqual(self.provenance(raw=self.raw.iloc[::-1]), first)
        unrelated = self.raw.iloc[0].copy()
        unrelated["location"] = "Other Cafe"
        C.save_correction(self.db, C.review_key(self.path, unrelated), [], [], self.version)
        C.save_correction(self.db, C.review_key(self.root / "other.csv", self.raw.iloc[0]),
                          [], [], self.version)
        C.save_correction(self.db, key, [], [], "older-version")
        self.assertEqual(self.provenance(), first)
        appended = pd.concat([self.raw, self.raw.iloc[[0]].assign(review_id="new")])
        self.assertEqual(self.provenance(raw=appended), first)

    def test_unknown_provenance_and_editing_do_not_backfill_history(self):
        action = self.action(self.provenance())
        del action["baseline_provenance"]
        original = copy.deepcopy(action)
        for current in (self.provenance(), None):
            result = self.compare(action, current)
            self.assertEqual(result["provenance_status"], "unknown")
            self.assertIn("Baseline tagging provenance unknown", result["provenance_message"])
        updated = A.update_action(
            action, "Check preparation.", "Manager", "Done",
            date(2026, 1, 2), date(2026, 1, 20))
        self.assertNotIn("baseline_provenance", updated)
        self.assertEqual(action, original)
        known = self.action(self.provenance())
        self.assertEqual(self.compare(known, None)["provenance_status"], "unknown")
        waiting = A.follow_up(known, [], current_provenance=self.provenance(
            version="synthetic-upgrade"))
        self.assertFalse(waiting["ready"])
        self.assertEqual(waiting["provenance_status"], "changed")

    def test_weekly_summary_labels_each_comparison(self):
        known = self.action(self.provenance())
        changed = copy.deepcopy(known)
        changed["baseline_provenance"]["rules_version"] = "earlier-rules"
        older = copy.deepcopy(known)
        del older["baseline_provenance"]
        reviews = E.analyze_offline(self.raw).to_dict("records")
        text = "\n".join(A.weekly_action_summary(
            [known, changed, older], "synthetic", ["Demo Cafe"], reviews,
            provenance_by_location={"Demo Cafe": self.provenance()}))
        self.assertIn("Tagging provenance unchanged", text)
        self.assertIn("Tagging changed", text)
        self.assertIn("Baseline tagging provenance unknown", text)
        self.assertEqual(text.count("Follow-up:"), 3)

    def test_action_tracker_renders_known_changed_and_legacy_provenance(self):
        raw = E.load_reviews(SAMPLE)
        location = raw.iloc[0]["location"]
        provenance = C.tagging_provenance(
            raw[raw["location"] == location], SAMPLE, {}, self.version)
        base = self.action(provenance)
        base.update(dataset_tag=SAMPLE_ID, location=location)
        changed = copy.deepcopy(base)
        changed["action_id"] = "changed"
        changed["baseline_provenance"]["rules_version"] = "earlier-rules"
        legacy = dict(base, action_id="legacy")
        del legacy["baseline_provenance"]
        with patch.object(A, "load_actions", return_value=[base, changed, legacy]), \
                patch.object(C, "load_corrections", return_value={}), \
                patch.object(C, "load_prior_corrections", return_value={}):
            app = AppTest.from_file(str(SAMPLE.parent.parent / "app.py"),
                                   default_timeout=30).run()
        self.assertEqual(list(app.exception), [])
        self.assertTrue(any("Tagging provenance unchanged" in item.value
                            for item in app.caption))
        self.assertTrue(any("Tagging changed" in item.value for item in app.warning))
        self.assertTrue(any("Baseline tagging provenance unknown" in item.value
                            for item in app.warning))

    def test_saving_action_from_warning_captures_location_provenance(self):
        actions = []

        def save(_path, action, **_kwargs):
            actions.append(action)

        with patch.object(A, "load_actions", side_effect=lambda *_: list(actions)), \
                patch.object(A, "append_action", side_effect=save), \
                patch.object(C, "load_corrections", return_value={}), \
                patch.object(C, "load_prior_corrections", return_value={}):
            app = AppTest.from_file(str(SAMPLE.parent.parent / "app.py"),
                                   default_timeout=30).run()
            self.assertEqual(list(app.exception), [])
            next(button for button in app.button
                 if button.label == "Save action plan").click().run()
            self.assertEqual(list(app.exception), [])
        self.assertEqual(len(actions), 1)
        action = actions[0]
        raw = E.load_reviews(SAMPLE)
        expected = C.tagging_provenance(
            raw[raw["location"] == action["location"]], SAMPLE, {}, self.version)
        self.assertEqual(action["baseline_provenance"], expected)
        self.assertTrue(any("Tagging provenance unchanged" in item.value
                            for item in app.caption))


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
            ], expected_actions=all_actions)
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
