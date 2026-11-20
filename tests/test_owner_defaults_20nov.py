"""Owner statement of 20 Nov 2026 (docs/RIGHTS_RECORD.md): fresh-install defaults for scores and crest references.

Covers: the fresh-install defaults and their eligibility, that publication stays a separate owner decision, the kill
switches (empty list, false) restoring the legacy output, and that a configuration saved before these keys existed
keeps the legacy values on upgrade.
"""
import tempfile
import unittest
from pathlib import Path

from sportsliveinfo import feed, providers
from sportsliveinfo.storage import Store
from test_live_tiers_corroboration import NOW, StoreCase
from test_scores import day_events, row, seed


def final_events():
    return {"football_data": [row("football_data", "football-data:1", ["Tottenham Hotspur FC", "Chelsea FC"],
                                  {"home": 1, "away": 2, "period": "FT"})],
            "api_sports": [row("api_sports", "api-sports:1", ["Chelsea", "Tottenham Hotspur"],
                               {"home": 2, "away": 1, "period": "FT"})]}


class FreshInstallDefaultsTests(StoreCase):
    def test_defaults_are_the_eligible_football_pair_with_crests_on(self):
        config = self.store.config()
        self.assertEqual(config["score_approvals"], ["api_sports", "football_data"])
        self.assertIs(config["publish_crest_refs"], True)
        for name in config["score_approvals"]:
            self.assertIn(name, providers.SCORE_ELIGIBLE)
        for excluded in ("thesportsdb", "jolpica", "openf1", "api_sports_mma", "cricketdata"):
            self.assertNotIn(excluded, config["score_approvals"])

    def test_publication_and_publishing_switches_stay_off_by_default(self):
        config = self.store.config()
        self.assertEqual(config["publication_approvals"], [])
        self.assertFalse(config["github"]["enabled"])
        self.assertFalse(config["github"]["auto_publish"])

    def test_scores_publish_for_publication_approved_events(self):
        seed(self.store, final_events())            # seed approves both sources for publication
        manifest, files = feed.build_feed(self.store, now=NOW)
        self.assertEqual((manifest["format"], manifest["format_minor"]), ("sli/1.7", 7))
        self.assertEqual(manifest["rights"]["scores"], {"approved_sources": ["api_sports", "football_data"]})
        event, = day_events(files, manifest).values()
        self.assertEqual((event["score"]["home"], event["score"]["away"]), (1, 2))
        self.assertTrue(manifest["rights"]["crests"]["sources"]["apisports"]["enabled"])

    def test_nothing_is_published_until_a_source_is_publication_approved(self):
        seed(self.store, final_events())
        self.store.configure({"publication_approvals": []})
        manifest, files = feed.build_feed(self.store, now=NOW)
        self.assertEqual(day_events(files, manifest), {})
        self.assertFalse(any(b'"score"' in data or b"participant_crests" in data for data in files.values()))

    def test_flags_keep_their_types_and_eligibility_is_still_enforced(self):
        with self.assertRaises(ValueError):
            self.store.configure({"publish_crest_refs": "yes"})
        with self.assertRaises(ValueError):
            self.store.configure({"score_approvals": ["thesportsdb"]})
        self.assertEqual(self.store.config()["score_approvals"], ["api_sports", "football_data"])


class KillSwitchTests(StoreCase):
    def test_empty_list_and_false_restore_the_legacy_output_byte_for_byte(self):
        seed(self.store, final_events())
        self.store.configure({"score_approvals": [], "publish_crest_refs": False})
        manifest, files = feed.build_feed(self.store, now=NOW)
        self.assertEqual((manifest["format"], manifest["format_minor"]), ("sli/1.6", 6))
        for section in ("capabilities", "compatibility", "rights"):
            self.assertNotIn("scores", manifest[section])
        self.assertNotIn("team_crests", manifest["capabilities"])
        self.assertTrue(manifest["rights"]["crests"]["monogram_only"])
        self.assertTrue(all("score" not in e and "participant_crests" not in e for e in day_events(files, manifest).values()))
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Store(Path(tmp) / "legacy.sqlite3")
            seed(legacy, final_events(), score_approvals=[], publish_crest_refs=False)
            legacy_manifest, legacy_files = feed.build_feed(legacy, now=NOW)
        self.assertEqual(feed._json(manifest), feed._json(legacy_manifest))
        self.assertEqual(files, legacy_files)

    def test_crest_flag_alone_switches_crest_references_off(self):
        seed(self.store, final_events())
        self.store.configure({"publish_crest_refs": False})
        manifest, _ = feed.build_feed(self.store, now=NOW)
        self.assertNotIn("team_crests", manifest["capabilities"])
        self.assertTrue(manifest["rights"]["crests"]["monogram_only"])
        self.assertIn("scores", manifest["capabilities"])      # the score switch is independent


class UpgradeTests(unittest.TestCase):
    def test_configuration_saved_before_the_keys_existed_keeps_them_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.sqlite3"
            store = Store(path)
            saved = store._get("config")
            del saved["score_approvals"], saved["publish_crest_refs"]
            store._put("config", saved)
            reopened = Store(path)
            self.assertEqual(reopened.config()["score_approvals"], [])
            self.assertIs(reopened.config()["publish_crest_refs"], False)
            reopened.configure({"setup_complete": True})        # any save writes the legacy values explicitly
            written = Store(path)._get("config")
            self.assertEqual(written["score_approvals"], [])
            self.assertIs(written["publish_crest_refs"], False)

    def test_saved_values_are_respected_on_upgrade(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "saved.sqlite3"
            store = Store(path)
            store.configure({"score_approvals": ["api_sports"], "publish_crest_refs": True})
            reopened = Store(path)
            self.assertEqual(reopened.config()["score_approvals"], ["api_sports"])
            self.assertIs(reopened.config()["publish_crest_refs"], True)


if __name__ == "__main__":
    unittest.main()
