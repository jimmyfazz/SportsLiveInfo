"""Offline HTTP-form controller tests: errors cannot partly mutate private state."""
import io
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sportsliveinfo.engine import Engine
from sportsliveinfo.server import UI
from sportsliveinfo.storage import Store


class AtomicSettingsPostTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "settings.sqlite3")
        self.engine = Engine(self.store)
        self.csrf = "synthetic-test-csrf"

    def tearDown(self):
        self.tmp.cleanup()

    def post(self, action, **fields):
        payload = urllib.parse.urlencode(dict(fields, action=action, csrf=self.csrf)).encode()
        ui = UI.__new__(UI)
        ui.server = SimpleNamespace(store=self.store, engine=self.engine, csrf=self.csrf)
        ui.rfile = io.BytesIO(payload)
        ui.wfile = io.BytesIO()
        ui.headers = {"Content-Length": str(len(payload))}
        response = {"status": None, "headers": {}}
        ui.send_response = lambda code: response.update(status=code)
        ui.send_header = lambda name, value: response["headers"].__setitem__(name, value)
        ui.end_headers = lambda: None
        with patch.object(UI, "_allowed", return_value=True):
            ui.do_POST()
        return response

    def test_invalid_key_does_not_enable_provider_or_save_credentials(self):
        before = self.store.config()
        response = self.post("sports", provider="football_data", enabled="on", key="x" * 513)
        self.assertEqual(response["status"], 303)
        location = urllib.parse.unquote(response["headers"]["Location"])
        self.assertIn("page=sources", location)
        self.assertIn("level=error", location)
        self.assertNotIn("x" * 100, location)
        after = self.store.config()
        self.assertEqual(after["sports"], before["sports"])
        self.assertEqual(after["keys"], before["keys"])

    def test_valid_save_combines_provider_switch_and_secret_atomically(self):
        self.store.configure({"keys": {"api_sports": "unrelated-key"}})
        response = self.post("sports", provider="football_data", enabled="on", key="valid")
        self.assertIn("level=info", response["headers"]["Location"])
        conf = self.store.config()
        self.assertTrue(conf["sports"]["football_data"])
        self.assertEqual(conf["keys"]["football_data"], "valid")
        self.assertEqual(conf["keys"]["api_sports"], "unrelated-key")

    def test_explicit_remove_wins_over_replacement_without_affecting_others(self):
        self.store.configure({"keys": {"football_data": "old-key", "api_sports": "other"}})
        self.post("sports", provider="football_data", enabled="on", key="replacement", remove="on")
        conf = self.store.config()
        self.assertEqual(conf["keys"]["football_data"], "")
        self.assertEqual(conf["keys"]["api_sports"], "other")

    def test_invalid_schedule_and_github_fields_return_to_original_tab(self):
        old = self.store.config()
        schedule = self.post("schedule", times="99:30")
        github = self.post("github", owner="bad/owner", repository="LiveSports-EPG", branch="main")
        self.assertIn("page=scheduler", schedule["headers"]["Location"])
        self.assertIn("page=publishing", github["headers"]["Location"])
        self.assertIn("level=error", schedule["headers"]["Location"])
        self.assertIn("level=error", github["headers"]["Location"])
        self.assertEqual(self.store.config()["schedule"], old["schedule"])
        self.assertEqual(self.store.config()["github"], old["github"])

    def test_unknown_source_does_not_redirect_to_overview(self):
        self.store.configure({"setup_complete": True})
        response = self.post("epg", provider="not-registered", enabled="on")
        self.assertIn("page=sources", response["headers"]["Location"])
        self.assertIn("level=error", response["headers"]["Location"])


if __name__ == "__main__":
    unittest.main()
