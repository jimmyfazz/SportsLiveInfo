"""Keep the socket-free handler path covered even on unrestricted CI runners."""
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from ingress_test_support import IngressTestClient
from sportsliveinfo.storage import Store


class MemoryIngressTests(unittest.TestCase):
    def test_csrf_rejection_and_successful_redirect_reach_real_handler(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / "state.sqlite3")
            client = IngressTestClient(store, "csrf-fixture", memory=True)
            try:
                for csrf, expected in (("wrong", 403), ("csrf-fixture", 200)):
                    data = urllib.parse.urlencode({"action": "finish", "csrf": csrf}).encode()
                    request = urllib.request.Request(client.base, data, method="POST")
                    if expected == 403:
                        with self.assertRaises(urllib.error.HTTPError) as denied:
                            client.open(request)
                        self.assertEqual(denied.exception.code, 403)
                        denied.exception.close()
                        self.assertFalse(store.config()["setup_complete"])
                    else:
                        with client.open(request) as response:
                            self.assertEqual(response.status, 200)
                            self.assertIn(b"SportsLiveInfo", response.read())
                        self.assertTrue(store.config()["setup_complete"])
            finally:
                client.close()

    def test_other_origins_cannot_be_dispatched_as_trusted_ingress(self):
        with tempfile.TemporaryDirectory() as temp:
            client = IngressTestClient(Store(Path(temp) / "state.sqlite3"), "csrf", memory=True)
            try:
                with self.assertRaises(ValueError):
                    client.open("https://example.invalid/")
            finally:
                client.close()
