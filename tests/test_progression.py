"""Deterministic v0.2 international EPG, provider completeness and ingress tests."""
import json
import os
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from ingress_test_support import IngressTestClient

from sportsliveinfo.guide import analyze_guide, canonical_channel, normalized_name
from sportsliveinfo.providers import (
    api_sports_events, football_data_events, f1_events, openligadb_events,
)
from sportsliveinfo.engine import Engine
from sportsliveinfo.storage import Store


class InternationalEpgTests(unittest.TestCase):
    def test_canonical_uk_and_french_names_are_strict(self):
        self.assertEqual(normalized_name("UK | SKY SPORTS MAIN EVENT FHD"), "sky sports main event")
        self.assertEqual(canonical_channel("farleyflex", "", "UK | Sky Sports Main Event FHD"), "gb.sky.sports.main_event")
        self.assertEqual(canonical_channel("fr_programmetv", "", "FR: Canal+ Sport HD"), "fr.canal.sport")
        self.assertEqual(canonical_channel("farleyflex", "", "BBC 1"), "gb.bbc.one")
        for bad in ["BBC One Scotland", "BBC One +1", "Sky Sports+", "Sky Sports News +1", "Sky News", "Sky Sports Premier League UHD +1"]:
            self.assertIsNone(canonical_channel("farleyflex", "", bad), bad)
        for bad in ["Canal+ Sport 360 +1", "beIN Sports 4", "beIN Sports 1 +1", "RMC Sport 2 UHD +1"]:
            self.assertIsNone(canonical_channel("fr_programmetv", "", bad), bad)
        self.assertIsNone(canonical_channel("fr_telerama", "", "Sky Sports Main Event"))
        self.assertIsNone(canonical_channel("farleyflex", "", "France 2"))

    def test_coverage_merges_overlaps_and_does_not_fake_full_day(self):
        t = datetime(2026, 11, 12, 0, 0, tzinfo=timezone.utc)
        rows = [
            ("2026-11-12T00:00:00+00:00", "2026-11-12T10:00:00+00:00", "Live Football"),
            ("2026-11-12T08:00:00+00:00", "2026-11-12T12:00:00+00:00", "Team A v Team B"),
            ("2026-11-12T12:00:00+00:00", "2026-11-13T00:00:00+00:00", "Sport programme"),
        ]
        guide = {"source_id": "farleyflex", "channels": {"SKY1": "Sky Sports Main Event"},
                 "programmes": [{"channel_id": "SKY1", "start_utc": a, "end_utc": b, "title": title} for a,b,title in rows],
                 "invalid_programmes": 0}
        data = analyze_guide(guide, now=t)
        self.assertEqual(data["full_coverage_channels"]["24h"], 1)
        self.assertEqual(data["full_coverage_channels"]["72h"], 0)
        self.assertEqual(data["generic_programmes"], 1)
        self.assertEqual(data["channels_needing_attention"][0]["coverage_hours"]["24h"], 24.0)
        self.assertEqual(data["channels_needing_attention"][0]["canonical_id"], "gb.sky.sports.main_event")
        self.assertNotIn("Team A", json.dumps(data), "diagnostics should not include programme text")

    def test_ambiguous_source_is_not_assigned_to_unknown_stream(self):
        self.assertIsNone(canonical_channel("different_source", "SKY1", "Sky Sports Main Event"))


class SportsAdapterTests(unittest.TestCase):
    def test_openligadb_no_key_source_with_safe_utc_date(self):
        payload = [{"matchID": 1234, "matchDateTimeUTC": "2026-11-22T17:30:00Z",
                    "team1": {"teamName": "Home"}, "team2": {"teamName": "Away"},
                    "leagueName": "Bundesliga", "matchIsFinished": False,
                    "location": {"locationStadium": "Stadium"}},
                   {"matchID": 2, "matchDateTimeUTC": None, "team1": {}, "team2": {}}]
        events = openligadb_events(json.dumps(payload).encode())
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["id"], "openligadb:1234")
        self.assertEqual(events[0]["title"], "Home v Away")
        self.assertEqual(events[0]["broadcasts"], [])
        with self.assertRaises(ValueError):
            openligadb_events(b'{}')

    def test_f1_sprint_shootout_supported(self):
        payload = {"MRData": {"RaceTable": {"Races": [{"season": "2026", "round": "10",
            "date": "2026-06-05", "time": "15:00:00Z", "raceName": "Example GP",
            "Circuit": {"circuitName": "Track"},
            "SprintShootout": {"date": "2026-06-04", "time": "12:00:00Z"}}]}}}
        names = {r["event_type"] for r in f1_events(json.dumps(payload).encode())}
        self.assertEqual(names, {"race", "SprintShootout"})
        with self.assertRaises(ValueError):
            f1_events(b'{}')

    def test_failed_and_paginated_fixture_responses_are_not_empty_days(self):
        for payload in [
            {"errors": {"token": "invalid"}, "response": []},
            {"paging": {"current": 1, "total": 2}, "response": []},
            {"response": "not-an-array"},
        ]:
            with self.assertRaises(ValueError):
                api_sports_events(json.dumps(payload).encode())
        self.assertEqual(api_sports_events(b'{"response":[],"paging":{"current":1,"total":1}}'), [])
        with self.assertRaises(ValueError):
            football_data_events(b'{"errorCode":403}')


class EngineProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "state.sqlite3"
        self.store = Store(self.path)
    def tearDown(self):
        self.temp.cleanup()

    def test_ingress_pages_and_form_csrf(self):
        client = IngressTestClient(self.store, "test-csrf-only-for-local-unit-test")
        base = client.base
        try:
            for page, expected in [("guide", "International EPG coverage"),
                                   ("events", "Sporting events"),
                                   ("sources", "Test connection"),
                                   ("health", "Provider health")]:
                with client.open(base + "?page=" + page, timeout=3) as response:
                    self.assertIn(expected, response.read().decode("utf-8"))
            body = urllib.parse.urlencode({"action": "finish", "csrf": "wrong"}).encode()
            with self.assertRaises(urllib.error.HTTPError) as rejected:
                client.open(urllib.request.Request(base, body, method="POST"), timeout=3)
            self.assertEqual(rejected.exception.code, 403)
            self.assertFalse(self.store.config()["setup_complete"])
            body = urllib.parse.urlencode({"action": "finish", "csrf": client.server.csrf}).encode()
            with client.open(urllib.request.Request(base, body, method="POST"), timeout=3) as response:
                self.assertIn("SportsLiveInfo", response.read().decode("utf-8"))
            self.assertTrue(self.store.config()["setup_complete"])
        finally:
            client.close()

    def test_legacy_settings_gain_new_source_without_replacing_saved_credentials(self):
        self.store._put("config", {"setup_complete": True, "sports": {"jolpica": False},
                                   "keys": {"api_sports": "secret"}})
        cfg = Store(self.path).config()
        self.assertIn("openligadb", cfg["sports"])
        self.assertFalse(cfg["sports"]["openligadb"])
        self.assertFalse(cfg["sports"]["jolpica"])
        self.assertEqual(cfg["keys"], {"api_sports": "secret"})

    def test_one_source_connection_probe_and_quota_count(self):
        valid = {"MRData": {"RaceTable": {"Races": []}}}
        with patch("sportsliveinfo.providers.fetch", return_value=json.dumps(valid).encode()) as fetch:
            msg = Engine(self.store).test_source("sports", "jolpica")
        self.assertIn("successful", msg)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(self.store.usage()["jolpica"], 1)
        self.assertIsNone(self.store.snapshot("sports:jolpica"), "test must not write collection results")

    def test_overlapping_manual_refresh_rejected(self):
        engine = Engine(self.store)
        engine._busy.acquire()
        try:
            self.assertFalse(engine.start_collection())
        finally:
            engine._busy.release()

    def test_stale_epg_does_not_replace_last_good(self):
        self.store.configure({"setup_complete": True, "sports": {"jolpica": False}, "epg": {"farleyflex": True}})
        old = {"source_id": "farleyflex", "channels": {"x": "BBC One"}, "programmes": [
            {"title": "Good", "channel_id": "x", "start_utc": "2026-11-12T00:00:00+00:00", "end_utc": "2026-11-12T01:00:00+00:00"}]}
        self.store.save_snapshot("epg:farleyflex", old)
        stale = b'<tv><channel id="x"><display-name>BBC One</display-name></channel><programme channel="x" start="20000101000000 +0000" stop="20000101010000 +0000"><title>Stale</title></programme></tv>'
        with patch("sportsliveinfo.providers.fetch", return_value=stale):
            Engine(self.store).collect()
        self.assertEqual(self.store.snapshot("epg:farleyflex")["data"], old)
        self.assertTrue(any(j["state"] == "stale" for j in self.store.recent_jobs()))

    def test_successful_epg_creates_coverage_snapshot(self):
        self.store.configure({"setup_complete": True, "sports": {"jolpica": False}, "epg": {"farleyflex": True}})
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        st = (now - timedelta(minutes=10)).strftime("%Y%m%d%H%M%S +0000")
        en = (now + timedelta(hours=26)).strftime("%Y%m%d%H%M%S +0000")
        payload = f'<tv><channel id="y"><display-name>BBC One</display-name></channel><programme channel="y" start="{st}" stop="{en}"><title>Broadcast</title></programme></tv>'.encode()
        with patch("sportsliveinfo.providers.fetch", return_value=payload):
            Engine(self.store).collect()
        q = self.store.snapshot("epg-quality:farleyflex")["data"]
        self.assertEqual(q["full_coverage_channels"]["24h"], 1)
        self.assertEqual(q["channels_needing_attention"][0]["canonical_id"], "gb.bbc.one")


if __name__ == '__main__':
    unittest.main()
