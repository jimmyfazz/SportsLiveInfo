"""GitHub token onboarding must not publish or leak credentials."""
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sportsliveinfo.engine import Engine
from sportsliveinfo.server import UI
from sportsliveinfo.storage import Store


class _Response:
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def read(self, limit=-1):
        return json.dumps(self.payload).encode("utf-8")


class GitHubOnboardingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "state.sqlite3")
        self.engine = Engine(self.store)

    def tearDown(self):
        self.temp.cleanup()

    def test_no_token_never_attempts_network_or_publishing(self):
        with patch("sportsliveinfo.engine.urllib.request.urlopen") as request:
            with self.assertRaisesRegex(ValueError, "Save your GitHub token"):
                self.engine.test_github_destination()
            request.assert_not_called()
        self.assertFalse(self.store.config()["github"]["enabled"])

    def test_token_read_check_does_not_write_or_enable_publication(self):
        self.store.configure({"github": {"token": "dummy-secret"}})
        payloads = [
            _Response({"full_name": "jimmyfazz/LiveSports-EPG",
                       "private": False, "permissions": {"push": True}}),
            _Response({"ref": "refs/heads/main"}),
        ]
        with patch("sportsliveinfo.engine.urllib.request.urlopen", side_effect=payloads) as urlopen:
            result = self.engine.test_github_destination()
        self.assertIn("Read-only check passed", result)
        self.assertEqual(urlopen.call_count, 2)
        for call in urlopen.call_args_list:
            request = call.args[0]
            self.assertEqual(request.get_method(), "GET")
            self.assertNotIn("dummy-secret", request.full_url)
        self.assertFalse(self.store.config()["github"]["enabled"])
        self.assertFalse(self.store.config()["github"]["auto_publish"])

    def test_wrong_repository_permissions_and_private_destination_are_denied(self):
        self.store.configure({"github": {"token": "dummy-secret"}})
        for payload, reason in [
            ({"full_name": "someone/other-repo", "private": False}, "different repository"),
            ({"full_name": "jimmyfazz/LiveSports-EPG", "private": True}, "must be a public"),
            ({"full_name": "jimmyfazz/LiveSports-EPG", "private": False,
              "permissions": {"push": False}}, "write permission"),
        ]:
            with self.subTest(reason=reason), patch(
                    "sportsliveinfo.engine.urllib.request.urlopen", return_value=_Response(payload)):
                with self.assertRaisesRegex(ValueError, reason):
                    self.engine.test_github_destination()

    def test_bad_token_gives_sanitised_error(self):
        self.store.configure({"github": {"token": "dummy-secret"}})
        err = urllib.error.HTTPError("https://api.github.com/redacted", 401, "denied", {}, io.BytesIO())
        with patch("sportsliveinfo.engine.urllib.request.urlopen", side_effect=err):
            with self.assertRaisesRegex(ValueError, "rejected the saved token") as issue:
                self.engine.test_github_destination()
        self.assertNotIn("dummy-secret", str(issue.exception))

    def test_publishing_ui_has_a_real_step_by_step_creation_guide(self):
        handler = UI.__new__(UI)
        handler.server = SimpleNamespace(store=self.store, csrf="dummy-csrf")
        markup = handler.publishing(self.store.config())
        for expected in [
            "settings/personal-access-tokens/new",
            "Only select repositories",
            "LiveSports-EPG",
            "Contents: Read and write",
            "Save GitHub settings",
            "Test saved GitHub connection",
            'name="action" value="test_github"',
        ]:
            self.assertIn(expected, markup)
        self.assertNotIn("dummy-secret", markup)


if __name__ == "__main__":
    unittest.main()
