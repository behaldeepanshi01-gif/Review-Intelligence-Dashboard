"""Session-only action drafts survive deliberate dashboard navigation."""
from datetime import date
from pathlib import Path
import tempfile
import unittest

from streamlit.testing.v1 import AppTest

import action_tracker as A
import dataset_store as D
import engine as E
from calendar_test_support import manager_session


class ActionDraftTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "data").mkdir()
        sample = Path(__file__).parent / "data/sample_reviews.csv"
        (self.root / "data/sample_reviews.csv").write_bytes(sample.read_bytes())
        store = D.DatasetStore(self.root / "data/uploads",
                               self.root / "data/sample_reviews.csv")
        self.other = store.save_snapshot("other.csv", sample.read_bytes())["dataset_id"]
        locations = sorted(E.load_reviews(sample)["location"].unique())
        self.location, self.away = locations[:2]
        day = date(2026, 1, 1)
        action = A.create_action(
            D.SAMPLE_ID, dict(location=self.location, theme="Service speed",
                              recent_share=40, recent_mentions=4),
            "service_speed", "Original plan", "Original owner", day, day, day, today=day)
        self.action_id = action["action_id"]
        # Even matching action IDs must not share fields across dataset identities.
        self.log = self.root / "data/action_log.json"
        A.save_actions(self.log, [action, dict(action, dataset_tag=self.other,
                                               action_text="Other dataset plan")])
        self.before = self.log.read_bytes()
        session = manager_session(self, self.root, {
            D.SAMPLE_ID: locations, self.other: locations})
        source = Path(__file__).with_name("app.py").read_text().replace(
            "BASE_DIR = os.path.dirname(os.path.abspath(__file__))",
            f"BASE_DIR = {str(self.root)!r}")
        # AppTest caches selectbox display mappings when two datasets have the
        # same review labels but different internal correction IDs. Use raw IDs
        # for this unrelated selector in the fixture; real browser tests retain
        # the production label formatter.
        source = source.replace(
            '''format_func=lambda key: (
                f"{inspection.loc[inspection['correction_key'] == key, 'review_id'].iloc[0]} | "
                f"{inspection.loc[inspection['correction_key'] == key, 'location'].iloc[0]}")''',
            "format_func=str")
        self.app = AppTest.from_string(source, default_timeout=30)
        self.app.session_state["_manager_report_grant"] = session
        self.app.session_state["data_source"] = "Sample data (synthetic)"
        self.app.run()
        self.assertFalse(self.app.exception)

    def widget(self, collection, prefix):
        return next(w for w in getattr(self.app, collection)
                    if w.key and w.key.startswith(prefix))

    def edit(self):
        for collection, prefix, value in [
            ("text_area", "update_text_", "Private unsaved plan"),
            ("text_input", "update_owner_", "Draft owner"),
            ("selectbox", "update_status_", "In progress"),
            ("date_input", "update_start_", date(2026, 2, 2)),
            ("date_input", "update_due_", date(2026, 2, 9)),
        ]:
            self.widget(collection, prefix).set_value(value).run()
            self.assertFalse(self.app.exception)

    def assert_draft(self):
        self.assertEqual(self.widget("text_area", "update_text_").value, "Private unsaved plan")
        self.assertEqual(self.widget("text_input", "update_owner_").value, "Draft owner")
        self.assertEqual(self.widget("selectbox", "update_status_").value, "In progress")
        self.assertEqual(self.widget("date_input", "update_start_").value, date(2026, 2, 2))
        self.assertEqual(self.widget("date_input", "update_due_").value, date(2026, 2, 9))
        self.assertEqual(self.log.read_bytes(), self.before)
        self.assertFalse(self.app.exception)

    def test_filters_datasets_and_upload_preview_preserve_without_saving(self):
        self.edit()
        locations = next(w for w in self.app.multiselect if w.label == "Locations")
        selected = locations.value
        locations.set_value([self.away]).run()
        self.assertFalse(any(w.key and w.key.startswith("update_text_")
                             for w in self.app.text_area))
        next(w for w in self.app.multiselect if w.label == "Locations").set_value(selected).run()
        self.assert_draft()
        period = next(w for w in self.app.slider if w.label == "Date range")
        original = period.value
        period.set_value((original[1], original[1])).run()
        self.app.run()
        next(w for w in self.app.slider if w.label == "Date range").set_value(original).run()
        self.assert_draft()
        self.app.radio(key="data_source").set_value("Saved file").run()
        self.assertEqual(self.widget("text_area", "update_text_").value, "Other dataset plan")
        self.widget("text_area", "update_text_").set_value("Other private draft").run()
        self.app.radio(key="data_source").set_value("Sample data (synthetic)").run()
        self.assert_draft()
        self.app.radio(key="data_source").set_value("Upload my reviews (CSV)").run()
        self.app.run()
        self.app.radio(key="data_source").set_value("Sample data (synthetic)").run()
        self.assert_draft()
        self.app.radio(key="data_source").set_value("Saved file").run()
        self.assertEqual(self.widget("text_area", "update_text_").value, "Other private draft")
        self.assertEqual(self.log.read_bytes(), self.before)

    def test_explicit_save_and_lock(self):
        # Real persisted action IDs are unique; duplicate fixture IDs above only
        # stress the UI namespace and are correctly rejected by the save guard.
        original = A.load_actions(self.log)
        saved = [dict(row) for row in original]
        saved[1]["action_id"] = "other-unique-id"
        A.save_actions(self.log, saved, expected_actions=original)
        self.edit()
        next(b for b in self.app.button if b.label == "Save updates").click().run()
        saved = A.load_actions(self.log)
        self.assertEqual(saved[0]["action_text"], "Private unsaved plan")
        self.assertEqual(saved[1]["action_text"], "Other dataset plan")
        next(b for b in self.app.button
             if b.label == "Lock restaurant dashboard").click().run()
        self.assertFalse(any(k.startswith(("update_", "action_snapshot_"))
                             for k in self.app.session_state))

    def test_new_alert_draft_keeps_its_identity_when_hidden(self):
        text = self.widget("text_area", "action_text_")
        suffix = text.key.removeprefix("action_text_")
        text.set_value("New alert draft, not a saved plan").run()
        self.app.text_input(key=f"action_owner_{suffix}").set_value("New draft owner").run()
        self.app.date_input(key=f"start_date_{suffix}").set_value(date(2026, 3, 2)).run()
        self.app.date_input(key=f"due_date_{suffix}").set_value(date(2026, 3, 9)).run()
        locations = next(w for w in self.app.multiselect if w.label == "Locations")
        original = locations.value
        locations.set_value([]).run()
        self.app.run()  # hidden for more than one cleanup cycle
        next(w for w in self.app.multiselect if w.label == "Locations").set_value(original).run()
        self.assertEqual(self.app.text_area(key=f"action_text_{suffix}").value,
                         "New alert draft, not a saved plan")
        self.assertEqual(self.app.text_input(key=f"action_owner_{suffix}").value, "New draft owner")
        self.assertEqual(self.app.date_input(key=f"start_date_{suffix}").value, date(2026, 3, 2))
        self.assertEqual(self.app.date_input(key=f"due_date_{suffix}").value, date(2026, 3, 9))
        self.assertEqual(self.log.read_bytes(), self.before)
        self.assertFalse(self.app.exception)

    def discard(self, prefix):
        self.widget("button", prefix).click().run()
        self.assertFalse(self.app.exception)

    def test_discard_saved_is_confirmed_scoped_and_read_only(self):
        self.edit()
        self.app.radio(key="data_source").set_value("Saved file").run()
        self.widget("text_area", "update_text_").set_value("Other private draft").run()
        self.app.radio(key="data_source").set_value("Sample data (synthetic)").run()
        new = self.widget("text_area", "action_text_")
        new_key = new.key
        new.set_value("Unrelated new draft").run()
        self.discard("discard_saved_")
        self.assert_draft()
        self.discard("cancel_discard_saved_")
        self.assert_draft()
        self.discard("discard_saved_")
        self.discard("confirm_discard_saved_")
        self.assertEqual(self.widget("text_area", "update_text_").value, "Original plan")
        self.assertEqual(self.app.text_area(key=new_key).value, "Unrelated new draft")
        self.app.radio(key="data_source").set_value("Saved file").run()
        self.assertEqual(self.widget("text_area", "update_text_").value, "Other private draft")
        self.assertEqual(self.log.read_bytes(), self.before)

    def test_discard_rechecks_concurrent_saves_before_reset(self):
        self.edit()
        self.discard("discard_saved_")
        rows = A.load_actions(self.log)
        latest = [dict(row) for row in rows]
        latest[0]["action_text"] = "Another manager's latest plan"
        A.save_actions(self.log, latest, expected_actions=rows)
        after_save = self.log.read_bytes()
        self.discard("confirm_discard_saved_")
        self.assertEqual(self.widget("text_area", "update_text_").value, "Private unsaved plan")
        self.discard("confirm_discard_saved_")
        self.assertEqual(self.widget("text_area", "update_text_").value,
                         "Another manager's latest plan")
        self.assertEqual(self.log.read_bytes(), after_save)
        # Old retained snapshot keys must not survive this editor's reset.
        keys = [k for k in self.app.session_state if k.startswith(
            f"update_text_{self.action_id}_{D.SAMPLE_ID}_")]
        self.assertEqual(len(keys), 1)

    def test_discard_new_keeps_existing_and_other_new_drafts(self):
        self.edit()
        editors = [w for w in self.app.text_area if w.key and w.key.startswith("action_text_")]
        first_key, initial = editors[0].key, editors[0].value
        suffix = first_key.removeprefix("action_text_")
        editors[0].set_value("Discard only this").run()
        self.app.radio(key="data_source").set_value("Saved file").run()
        other = self.widget("text_area", "action_text_")
        other_key = other.key
        other.set_value("Keep this alert draft").run()
        self.app.radio(key="data_source").set_value("Sample data (synthetic)").run()
        self.app.button(key=f"discard_new_{suffix}").click().run()
        self.assertEqual(self.app.text_area(key=first_key).value, "Discard only this")
        self.app.button(key=f"confirm_discard_new_{suffix}").click().run()
        self.assertEqual(self.app.text_area(key=first_key).value, initial)
        self.assert_draft()
        self.app.radio(key="data_source").set_value("Saved file").run()
        self.assertEqual(self.app.text_area(key=other_key).value, "Keep this alert draft")
        self.assertEqual(self.log.read_bytes(), self.before)


if __name__ == "__main__":
    unittest.main()
