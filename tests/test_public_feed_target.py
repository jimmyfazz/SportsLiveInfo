"""Known public static-feed destination; publishing stays opt-in and rights-gated."""
import tempfile
import unittest
from pathlib import Path

from sportsliveinfo.storage import Store
from sportsliveinfo.engine import Engine


class PublicDestinationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "data.sqlite3")

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_install_prefills_public_feed_but_cannot_publish(self):
        target = self.store.config()["github"]
        self.assertEqual((target["owner"], target["repository"], target["branch"]),
                         ("jimmyfazz", "LiveSports-EPG", "main"))
        self.assertFalse(target["enabled"])
        self.assertFalse(target["auto_publish"])
        self.assertEqual(target["token"], "")
        self.assertEqual(self.store.config()["publication_approvals"], [])
        with self.assertRaisesRegex(ValueError, "first-run setup"):
            Engine(self.store).publish()

    def test_legacy_empty_placeholder_migrates_without_changing_other_fields(self):
        legacy = self.store.config()
        legacy["github"]["repository"] = ""
        legacy["github"]["token"] = "existing-local-test-token"
        legacy["github"]["auto_publish"] = False
        legacy["keys"]["football_data"] = "existing-local-provider-key"
        self.store._put("config", legacy)
        actual = Store(self.store.path).config()
        self.assertEqual(actual["github"]["repository"], "LiveSports-EPG")
        self.assertEqual(actual["github"]["token"], "existing-local-test-token")
        self.assertEqual(actual["keys"]["football_data"], "existing-local-provider-key")
        self.assertFalse(actual["github"]["enabled"])

    def test_existing_custom_destination_remains_unmodified(self):
        self.store.configure({"github": {"owner": "another-owner",
                                         "repository": "another-feed", "branch": "release"}})
        actual = Store(self.store.path).config()["github"]
        self.assertEqual((actual["owner"], actual["repository"], actual["branch"]),
                         ("another-owner", "another-feed", "release"))

    def test_another_owner_blank_repo_is_not_silently_retargeted(self):
        self.store.configure({"github": {"owner": "different-owner", "repository": ""}})
        self.assertEqual(self.store.config()["github"]["repository"], "")


if __name__ == "__main__":
    unittest.main()
