"""Browser-free Streamlit script checks using synthetic data only."""

from pathlib import Path
from datetime import date, datetime, timedelta
import unittest
import tempfile
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest
import engine as E
import action_tracker as A
from dataset_store import SAMPLE_ID
from location_settings import LocationSettings


APP = Path(__file__).with_name("app.py")


class LocalAppTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        settings = LocationSettings(Path(directory.name) / "calendars.sqlite")
        store = patch("location_settings.LocationSettings", return_value=settings)
        mocked_store = store.start()
        mocked_store.default.side_effect = LocationSettings.default
        self.addCleanup(store.stop)
        # Existing date-based fixtures and app evaluation share a fixed clock.
        clock = patch.object(A, "restaurant_today", return_value=date.today())
        clock.start()
        self.addCleanup(clock.stop)

    def test_timezone_setting_controls_action_calendar_and_rejects_invalid_names(self):
        real_today = self._real_today
        instant = datetime.fromisoformat("2026-01-02T00:00:00+00:00")
        with patch.object(A, "restaurant_today",
                          side_effect=lambda zone: real_today(zone, now=instant)):
            app = AppTest.from_file(str(APP), default_timeout=30).run()
            second_manager = AppTest.from_file(str(APP), default_timeout=30).run()
            self.assertFalse(app.exception)
            self.assertTrue(any("Action calendar: 2026-01-01" in c.value for c in app.caption))
            setting = next(t for t in app.text_input if t.label == "Restaurant timezone")
            setting.set_value("Asia/Kolkata")
            next(b for b in app.button if b.label == "Save location timezone").click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any("Action calendar: 2026-01-02" in c.value for c in app.caption))
            next(t for t in second_manager.text_input
                 if t.label == "Restaurant timezone").set_value("UTC")
            next(b for b in second_manager.button
                 if b.label == "Save location timezone").click().run()
            self.assertTrue(any("Another manager changed" in e.value
                                for e in second_manager.error))
            next(b for b in second_manager.button
                 if b.label == "Reload saved timezone").click().run()
            self.assertEqual(next(t for t in second_manager.text_input
                                  if t.label == "Restaurant timezone").value, "Asia/Kolkata")
            self.assertTrue(any("2026-01-02 · Asia/Kolkata" in c.value
                                for c in second_manager.caption))
            next(t for t in app.text_input if t.label == "Restaurant timezone").set_value("Invalid/Zone")
            next(b for b in app.button if b.label == "Save location timezone").click().run()
            self.assertTrue(any("valid IANA timezone" in e.value for e in app.error))

    _real_today = staticmethod(A.restaurant_today)

    def test_midnight_refresh_updates_overdue_views_without_rekeying_editors(self):
        sample = E.load_reviews(APP.parent / "data" / "sample_reviews.csv")
        action = {
            "dataset_tag": SAMPLE_ID, "action_id": "midnight",
            "location": sample.iloc[0]["location"], "theme": "Service speed",
            "status": "Planned", "start_date": "2026-01-01",
            "due_date": "2026-01-01", "action_text": "Check handoffs.",
        }
        with patch.object(A, "load_actions", return_value=[action]), patch.object(
            A, "restaurant_today", return_value=date(2026, 1, 1)
        ) as clock:
            app = AppTest.from_file(str(APP), default_timeout=30).run()
            app.radio(key="action_status_filter").set_value("Overdue only").run()
            self.assertTrue(any("No overdue action plans" in i.value for i in app.info))
            self.assertFalse(any("OVERDUE" in c.value for c in app.code))
            editor = next(t for t in app.text_area
                          if t.key and t.key.startswith("update_text_"))
            editor_key = editor.key
            clock.return_value = date(2026, 1, 2)
            app.run()
            self.assertFalse(app.exception)
            self.assertTrue(any("Showing 1 of 1" in c.value for c in app.caption))
            self.assertTrue(any("Overdue —" in w.value for w in app.warning))
            self.assertTrue(any("OVERDUE" in c.value for c in app.code))
            # AppTest.run is a full rerun, not a browser timer event. Check
            # stable identity here; test_midnight_browser.cjs covers unsent input.
            self.assertEqual(app.text_area(key=editor_key).key, editor_key)

    def test_timers_never_render_edit_forms_or_trigger_full_reruns(self):
        # AppTest cannot emulate browser timer events. Guard the isolation
        # boundary here; browser testing verifies unsubmitted frontend input.
        import ast
        tree = ast.parse(APP.read_text())
        fragments = [
            node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
            and any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                    and d.func.attr == "fragment" for d in node.decorator_list)
        ]
        self.assertEqual(len(fragments), 3)
        for fragment in fragments:
            calls = [n for n in ast.walk(fragment) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Attribute)]
            self.assertFalse({"form", "rerun"} & {n.func.attr for n in calls})
            decorator = fragment.decorator_list[0]
            self.assertTrue(any(k.arg == "run_every" and k.value.value == "30s"
                                for k in decorator.keywords))

    def test_action_status_filter_preserves_scope_and_handles_empty_results(self):
        sample = E.load_reviews(APP.parent / "data" / "sample_reviews.csv")
        location = sample.iloc[0]["location"]
        base = {
            "dataset_tag": SAMPLE_ID, "location": location,
            "theme": "Service speed", "status": "Planned",
            "start_date": (date.today() - timedelta(days=10)).isoformat(),
            "due_date": (date.today() - timedelta(days=1)).isoformat(),
            "action_text": "Check handoffs.",
        }
        actions = [
            dict(base, action_id="late"),
            dict(base, action_id="progress", status="In progress"),
            dict(base, action_id="done", status="Done"),
            dict(base, action_id="today", due_date=date.today().isoformat()),
            dict(base, action_id="future", due_date=(date.today() + timedelta(days=1)).isoformat()),
            dict(base, action_id="missing", due_date=None),
            dict(base, action_id="invalid", due_date="invalid"),
            dict(base, action_id="other_dataset", dataset_tag="unrelated"),
            dict(base, action_id="other_location", location="Unselected restaurant"),
        ]
        for action in actions:
            action["owner"] = action["action_id"]
        with patch.object(E, "load_reviews", return_value=sample), patch.object(
            A, "load_actions", return_value=actions
        ), patch("os.listdir", return_value=[]):
            app = AppTest.from_file(str(APP), default_timeout=30).run()

            def shown():
                self.assertEqual(list(app.exception), [])
                return {
                    item.value.split("Owner: ", 1)[1].split(" | Due:", 1)[0]
                    for item in app.caption if item.value.startswith("Status:")
                }

            self.assertEqual(shown(), {"late", "progress", "today", "future", "missing", "invalid"})
            app.radio(key="action_status_filter").set_value("Overdue only").run()
            self.assertEqual(shown(), {"late", "progress"})
            # Editors are deliberately independent of the live status filter.
            self.assertEqual(
                {item.key.removeprefix("update_text_").rsplit("_", 1)[0]
                 for item in app.text_area
                 if item.key and item.key.startswith("update_text_")},
                {"late", "progress", "done", "today", "future", "missing", "invalid"},
            )
            app.radio(key="action_status_filter").set_value("Completed plans").run()
            self.assertEqual(shown(), {"done"})
            actions[:] = [row for row in actions if row["action_id"] != "done"]
            app.run()
            self.assertEqual(shown(), set())
            self.assertTrue(any("No completed action plans" in item.value for item in app.info))
            for row in actions:
                row["due_date"] = date.today().isoformat()
            app.radio(key="action_status_filter").set_value("Overdue only").run()
            self.assertEqual(shown(), set())
            self.assertTrue(any("No overdue action plans" in item.value for item in app.info))
            for row in actions:
                row["status"] = "Done"
            app.radio(key="action_status_filter").set_value("All active actions").run()
            self.assertEqual(shown(), set())
            self.assertTrue(any("No active action plans" in item.value for item in app.info))
            actions.clear()
            app.run()
            self.assertTrue(any("No action plans saved" in item.value for item in app.info))

    def test_overdue_warning_and_summary_exclude_completed_actions(self):
        sample = E.load_reviews(APP.parent / "data" / "sample_reviews.csv")
        base = {
            "dataset_tag": SAMPLE_ID, "location": sample.iloc[0]["location"],
            "theme": "Service speed", "status": "Planned",
            "start_date": (date.today() - timedelta(days=10)).isoformat(),
            "due_date": (date.today() - timedelta(days=1)).isoformat(),
            "action_text": "Check handoffs.",
        }
        actions = [
            dict(base, action_id="late"),
            dict(base, action_id="done", status="Done", action_text="Finished plan"),
            dict(base, action_id="today", due_date=date.today().isoformat()),
        ]
        with patch.object(E, "load_reviews", return_value=sample), patch.object(
            A, "load_actions", return_value=actions
        ), patch("os.listdir", return_value=[]):
            app = AppTest.from_file(str(APP), default_timeout=30).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(sum("Overdue" in item.value for item in app.warning), 1)
        summary = next(item.value for item in app.code if "Manager actions:" in item.value)
        self.assertEqual(summary.count("OVERDUE"), 1)
        self.assertNotIn("Finished plan", summary)

    def test_default_engine_has_evidence_and_no_ollama_controls(self):
        sample = E.load_reviews(APP.parent / "data" / "sample_reviews.csv")
        with patch.object(E, "load_reviews", return_value=sample), patch(
            "urllib.request.urlopen", side_effect=AssertionError("Network forbidden")
        ):
            app = AppTest.from_file(str(APP), default_timeout=30).run()
        self.assertEqual(len(app.exception), 0)
        engine = next(radio for radio in app.sidebar.radio if radio.label == "Analysis engine")
        self.assertTrue(engine.value.startswith("Local Review Analyzer"))
        self.assertFalse(any("Ollama" in option for option in engine.options))
        self.assertTrue(any(item.label == "Why these tags?" for item in app.expander))
        self.assertTrue(any("Reviews needing manager review" in item.label
                            for item in app.expander))

    def test_no_theme_dataset_renders_without_chart_failure(self):
        df = pd.DataFrame([
            {"location": "Demo Cafe", "review_id": str(index), "reviewer": "Guest",
             "date": pd.Timestamp(f"2026-10-0{index + 1}"), "rating": 3,
             "text": "Visited yesterday."}
            for index in range(2)
        ])
        with patch.object(E, "load_reviews", return_value=df):
            app = AppTest.from_file(str(APP), default_timeout=30).run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any("No clear praise" in info.value for info in app.info))


if __name__ == "__main__":
    unittest.main()
