"""Publishing-page crest toggles, the read-only link-policy line, and the owner override of the seeded hint tables."""
import json
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from contextlib import closing
from pathlib import Path

from ingress_test_support import IngressTestClient
from sportsliveinfo import feed, hints
from sportsliveinfo.storage import Store


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "s.sqlite3")
        self.store.configure({"setup_complete": True})

    def tearDown(self):
        self.temp.cleanup()


class CrestToggleTests(StoreCase):
    def post(self, client, action="crest_settings", **fields):
        body = urllib.parse.urlencode(dict({"csrf": "c", "action": action}, **fields), doseq=True).encode()
        return client.open(urllib.request.Request(client.base, body, method="POST")).read().decode()

    def page(self, client):
        with client.open(client.base + "?page=publishing") as response:
            return response.read().decode()

    def test_page_shows_state_effect_kill_switch_and_policy_line(self):
        with closing(IngressTestClient(self.store, "c")) as client:
            page = self.page(client)
        for text in ("Team crests", "media.api-sports.io", "Kill switch", "TheSportsDB", "Channel link policy",
                     "Binding rule: <strong>narrow</strong>", "Rights-holder prior links: <strong>off</strong>",
                     "built-in seed"):
            self.assertIn(text, page)
        self.assertIn("nothing is published until an API-Sports source is approved", page)   # default on, none approved

    def test_enabling_needs_attestation_and_off_does_not(self):
        self.store.configure({"publish_crest_refs": False, "crest_device_lookup_thesportsdb": False})
        with closing(IngressTestClient(self.store, "c")) as client:
            self.assertIn("Confirm you have read", self.post(client, publish_crest_refs="on"))
            conf = self.store.config()
            self.assertEqual((conf["publish_crest_refs"], conf["crest_device_lookup_thesportsdb"]), (False, False))
            self.post(client, publish_crest_refs="on", crest_device_lookup_thesportsdb="on", attest_crests="on")
            conf = self.store.config()
            self.assertEqual((conf["publish_crest_refs"], conf["crest_device_lookup_thesportsdb"]), (True, True))
            self.assertIn("TheSportsDB device lookup: on", self.page(client))
            self.post(client)                                    # kill switch: both unticked, no attestation needed
            conf = self.store.config()
            self.assertEqual((conf["publish_crest_refs"], conf["crest_device_lookup_thesportsdb"]), (False, False))
            self.assertIn("off: the feed carries no crest references", self.page(client))
        log = self.store._get("approval_log")
        self.assertEqual(log[-1]["crest_refs"], False)

    def test_policy_line_follows_config(self):
        self.store.configure({"binds_rule": "legacy", "rights_holder_prior": True})
        with closing(IngressTestClient(self.store, "c")) as client:
            page = self.page(client)
        self.assertIn("Binding rule: <strong>legacy</strong>", page)
        self.assertIn("Rights-holder prior links: <strong>published</strong>", page)

    def test_override_form_saves_validates_and_clears(self):
        good = json.dumps({"football": ["tnt_sports", "sky_sports"]})
        with closing(IngressTestClient(self.store, "c")) as client:
            self.post(client, "hint_overrides", rank_override=good, prior_override="")
            self.assertEqual(self.store.config()[hints.RANK_KEY], good)
            self.assertIn("owner override for football", self.page(client))
            self.assertIn("is not valid JSON", self.post(client, "hint_overrides", rank_override="{", prior_override=""))
            self.assertEqual(self.store.config()[hints.RANK_KEY], good)       # refused whole: nothing changed
            self.post(client, "hint_overrides", rank_override="", prior_override="")
            self.assertEqual(self.store.config()[hints.RANK_KEY], "")


EVENT = {"id": "e", "sport": "football", "competition_id": "football.premier_league", "start_utc": "2026-11-21T17:30:00+00:00",
         "start_precision": "scheduled", "status_normalized": "scheduled"}
BLACKOUT_EVENT = dict(EVENT, start_utc="2026-11-21T15:00:00+00:00")


class OverrideTests(StoreCase):
    def test_absent_override_is_byte_identical_to_builtin(self):
        absent = hints.tables_from_config({})
        self.assertIs(absent, hints.BUILTIN_TABLES)
        for conf in ({}, {hints.RANK_KEY: "", hints.PRIOR_KEY: ""}, self.store.config()):
            tables = hints.tables_from_config(conf)
            self.assertEqual(feed._json(hints.channel_hints_document(tables)), feed._json(hints.channel_hints_document()))
            self.assertIsNone(feed.link_policy(conf).hint_tables)
            for event in (EVENT, BLACKOUT_EVENT, dict(EVENT, competition_id="motorsport.f1")):
                self.assertEqual(hints.rights_holder_prior(event, tables), hints.rights_holder_prior(event))
        # an override that restates the built-in values changes nothing either
        same = {hints.RANK_KEY: json.dumps({k: v for k, v in hints.BROADCASTER_RANK.items()})}
        self.assertEqual(feed._json(hints.channel_hints_document(hints.tables_from_config(same))),
                         feed._json(hints.channel_hints_document()))

    def test_valid_rank_override_replaces_only_named_sports(self):
        conf = {hints.RANK_KEY: json.dumps({"football": ["tnt_sports", "sky_sports"], "default": ["bbc"]})}
        doc = hints.channel_hints_document(hints.tables_from_config(conf))
        self.assertEqual(doc["broadcaster_rank"]["football"], ["tnt_sports", "sky_sports"])
        self.assertEqual(doc["broadcaster_rank"]["default"], ["bbc"])
        self.assertEqual(doc["broadcaster_rank"]["cricket"], hints.BROADCASTER_RANK["cricket"])
        self.assertEqual(hints.BROADCASTER_RANK["football"][0], "sky_sports")      # built-ins are never mutated

    def test_prior_override_replaces_removes_and_toggles_blackout(self):
        conf = {hints.PRIOR_KEY: json.dumps({
            "football.premier_league": {"channels": ["gb.tnt.sports.1"], "blackout": False},
            "motorsport.f1": {"channels": []}})}
        tables = hints.tables_from_config(conf)
        self.assertEqual(hints.rights_holder_prior(EVENT, tables), ["gb.tnt.sports.1"])
        self.assertEqual(hints.rights_holder_prior(BLACKOUT_EVENT, tables), ["gb.tnt.sports.1"])   # blackout off
        self.assertEqual(hints.rights_holder_prior(dict(EVENT, competition_id="motorsport.f1"), tables), [])
        self.assertEqual(hints.rights_holder_prior(BLACKOUT_EVENT), [])                            # built-in unchanged
        self.assertEqual(hints.rights_holder_prior(dict(EVENT, competition_id="football.champions_league"), tables),
                         ["gb.tnt.sports.1"])
        add = hints.tables_from_config({hints.PRIOR_KEY: json.dumps(
            {"football.efl_championship": {"channels": ["gb.sky.sports.football"], "blackout": True}})})
        self.assertEqual(hints.rights_holder_prior(dict(EVENT, competition_id="football.efl_championship"), add),
                         ["gb.sky.sports.football"])
        self.assertEqual(hints.rights_holder_prior(dict(BLACKOUT_EVENT, competition_id="football.efl_championship"), add), [])

    def test_validation_rejects_bad_overrides(self):
        bad_rank = ["", "{", "[]", "{}", '{"Football": ["sky_sports"]}', '{"football": []}', '{"football": "sky_sports"}',
                    '{"football": ["sky_sports", "sky_sports"]}', '{"football": ["nonexistent"]}', '{"football": [1]}',
                    "x" * (hints.MAX_OVERRIDE_BYTES + 1), '{"football": ["sky_sports"]}' + " " * 0 + "junk"]
        for text in bad_rank:
            with self.assertRaises(ValueError, msg=text[:30]):
                hints.validate_rank_override(text)
        bad_prior = ["", "{", '{"premier_league": {"channels": []}}', '{"football.x": ["gb.tnt.sports.1"]}',
                     '{"football.x": {"channels": ["gb.tnt.sports.1"], "extra": 1}}', '{"football.x": {}}',
                     '{"football.x": {"channels": ["gb.made.up.channel"]}}',
                     '{"football.x": {"channels": ["gb.tnt.sports.1"], "blackout": "yes"}}',
                     '{"football.x": {"channels": ["gb.tnt.sports.1", "gb.tnt.sports.1"]}}',
                     '{"football.x": {"channels": "gb.tnt.sports.1"}}']
        for text in bad_prior:
            with self.assertRaises(ValueError, msg=text[:30]):
                hints.validate_prior_override(text)
        hints.validate_prior_override('{"football.x": {"channels": ["gb.tnt.sports.1"], "blackout": true}}')

    def test_store_validates_on_save_and_bad_stored_value_falls_back(self):
        with self.assertRaises(ValueError):
            self.store.configure({hints.RANK_KEY: '{"football": ["nope"]}'})
        with self.assertRaises(ValueError):
            self.store.configure({hints.PRIOR_KEY: "not json"})
        self.assertEqual(self.store.config()[hints.RANK_KEY], "")
        self.store.configure({hints.RANK_KEY: '{"golf": ["bbc"]}'})
        self.assertEqual(hints.tables_from_config(self.store.config()).rank["golf"], ["bbc"])
        self.store.configure({hints.RANK_KEY: ""})
        self.assertIs(hints.tables_from_config(self.store.config()), hints.BUILTIN_TABLES)
        self.assertIs(hints.tables_from_config({hints.RANK_KEY: "garbage", hints.PRIOR_KEY: "[1]"}), hints.BUILTIN_TABLES)

    def test_builtin_prior_channels_pass_the_validator(self):
        text = json.dumps({c: {"channels": ch} for c, ch in hints.COMPETITION_RIGHTS.items()})
        hints.validate_prior_override(text)

    def test_feed_uses_the_override(self):
        conf = dict(self.store.config(), rights_holder_prior=True,
                    **{hints.PRIOR_KEY: json.dumps({"football.premier_league": {"channels": ["gb.tnt.sports.1"], "blackout": False}})})
        links = feed._broadcast_links(EVENT, False, feed.link_policy(conf))
        self.assertEqual([l["canonical_channel_id"] for l in links], ["gb.tnt.sports.1"])
        links = feed._broadcast_links(EVENT, False, feed.link_policy(dict(conf, **{hints.PRIOR_KEY: ""})))
        self.assertEqual([l["canonical_channel_id"] for l in links][0], "gb.sky.sports.premier_league")


if __name__ == "__main__":
    unittest.main()
