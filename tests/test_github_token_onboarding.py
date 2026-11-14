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
        with patch("sportsliveinfo.engine._github_open") as request:
            with self.assertRaisesRegex(ValueError, "Save your GitHub token"):
                self.engine.test_github_destination()
            request.assert_not_called()
        self.assertFalse(self.store.config()["github"]["enabled"])

    def test_private_feed_settings_accept_a_link_owner_slash_name_or_a_bare_name(self):
        import urllib.parse, urllib.request
        from ingress_test_support import IngressTestClient
        self.store.configure({"setup_complete": True})
        client = IngressTestClient(self.store, "csrf-test", memory=True)
        for typed in ("https://github.com/jimmyfazz/LiveSports-EPG-private", "jimmyfazz/LiveSports-EPG-private",
                      "LiveSports-EPG-private", " https://github.com/jimmyfazz/LiveSports-EPG-private.git/ "):
            with self.subTest(typed=typed):
                self.store.configure({"private_feed": {"repository": "", "enabled": False}})
                body = urllib.parse.urlencode({"action": "private_feed", "csrf": "csrf-test", "owner": "jimmyfazz",
                                               "repository": typed, "branch": "main", "enabled": "on"}).encode()
                with client.open(urllib.request.Request(client.base, body, method="POST")) as response:
                    page = response.read().decode()
                self.assertIn("Private feed settings saved and enabled", page)
                self.assertEqual(self.store.config()["private_feed"],
                                 {"owner": "jimmyfazz", "repository": "LiveSports-EPG-private", "branch": "main",
                                  "enabled": True})
        body = urllib.parse.urlencode({"action": "private_feed", "csrf": "csrf-test", "owner": "jimmyfazz",
                                       "repository": "bad name!", "branch": "main", "enabled": "on"}).encode()
        with client.open(urllib.request.Request(client.base, body, method="POST")) as response:
            self.assertIn("Invalid GitHub repository name", response.read().decode())

    def test_private_feed_check_refuses_a_public_repository_and_accepts_a_private_one(self):
        self.store.configure({"github": {"token": "dummy-secret"},
                              "private_feed": {"repository": "LiveSports-EPG-private", "enabled": True}})
        public = [_Response({"full_name": "jimmyfazz/LiveSports-EPG-private", "private": False,
                             "permissions": {"push": True}})]
        with patch("sportsliveinfo.engine._github_open", side_effect=public):
            with self.assertRaisesRegex(ValueError, "PRIVATE repository"):
                self.engine.test_github_destination(private=True)
        private = [_Response({"full_name": "jimmyfazz/LiveSports-EPG-private", "private": True,
                              "permissions": {"push": True}}),
                   _Response({"ref": "refs/heads/main"}), _Response({"sha": "0123abcd"})]
        with patch("sportsliveinfo.engine._github_open", side_effect=private):
            self.assertIn("confirmed private", self.engine.test_github_destination(private=True))

    def test_token_check_proves_write_without_committing_or_enabling_publication(self):
        self.store.configure({"github": {"token": "dummy-secret"}})
        payloads = [
            _Response({"full_name": "jimmyfazz/LiveSports-EPG",
                       "private": False, "permissions": {"push": True}}),
            _Response({"ref": "refs/heads/main"}),
            _Response({"sha": "0123abcd"}),
        ]
        with patch("sportsliveinfo.engine._github_open", side_effect=payloads) as urlopen:
            result = self.engine.test_github_destination()
        self.assertIn("write access confirmed", result)
        self.assertIn("no commit or file was created", result)
        methods = [call.args[0].get_method() for call in urlopen.call_args_list]
        self.assertEqual(methods, ["GET", "GET", "POST"])
        # The only write is an unreferenced blob: never a tree, commit or ref update.
        self.assertTrue(urlopen.call_args_list[2].args[0].full_url.endswith("/git/blobs"))
        for call in urlopen.call_args_list:
            self.assertNotIn("dummy-secret", call.args[0].full_url)
        self.assertFalse(self.store.config()["github"]["enabled"])
        self.assertFalse(self.store.config()["github"]["auto_publish"])

    def test_read_only_token_is_reported_before_publication(self):
        self.store.configure({"github": {"token": "dummy-secret"}})
        denied = urllib.error.HTTPError("https://api.github.com/redacted", 403, "denied", {}, io.BytesIO())
        payloads = [
            _Response({"full_name": "jimmyfazz/LiveSports-EPG", "private": False}),
            _Response({"ref": "refs/heads/main"}),
            denied,
        ]
        with patch("sportsliveinfo.engine._github_open", side_effect=payloads):
            with self.assertRaisesRegex(ValueError, "cannot write") as issue:
                self.engine.test_github_destination()
        self.assertIn("Contents must be Read and write", str(issue.exception))
        self.assertNotIn("dummy-secret", str(issue.exception))

    def test_wrong_repository_permissions_and_private_destination_are_denied(self):
        self.store.configure({"github": {"token": "dummy-secret"}})
        for payload, reason in [
            ({"full_name": "someone/other-repo", "private": False}, "different repository"),
            ({"full_name": "jimmyfazz/LiveSports-EPG", "private": True}, "must be a public"),
            ({"full_name": "jimmyfazz/LiveSports-EPG", "private": False,
              "permissions": {"push": False}}, "write permission"),
        ]:
            with self.subTest(reason=reason), patch(
                    "sportsliveinfo.engine._github_open", return_value=_Response(payload)):
                with self.assertRaisesRegex(ValueError, reason):
                    self.engine.test_github_destination()

    def test_redirect_guard_refuses_forwarding_bearer_token(self):
        from sportsliveinfo.engine import _NoGitHubRedirect
        from urllib.request import Request
        request = Request("https://api.github.com/repos/jimmyfazz/LiveSports-EPG",
                          headers={"Authorization": "Bearer dummy-secret"})
        with self.assertRaisesRegex(ValueError, "refusing to forward"):
            _NoGitHubRedirect().redirect_request(
                request, None, 302, "redirected", {},
                "https://example.com/steal-token")

    def test_bad_token_gives_sanitised_error(self):
        self.store.configure({"github": {"token": "dummy-secret"}})
        err = urllib.error.HTTPError("https://api.github.com/redacted", 401, "denied", {}, io.BytesIO())
        with patch("sportsliveinfo.engine._github_open", side_effect=err):
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
