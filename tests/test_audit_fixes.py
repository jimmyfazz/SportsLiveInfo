"""Regression tests for the 13 Nov 2026 code audit (server/GUI, engine, feed/publisher, matching)."""
import gzip
from contextlib import closing
import io
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from ingress_test_support import IngressTestClient
from sportsliveinfo import engine as engine_module, feed, linking, providers, taxonomy
from sportsliveinfo.engine import Engine, validate_github_target
from sportsliveinfo.server import UI, e
from sportsliveinfo.storage import Store

NOW = datetime(2026, 11, 14, 14, 0, tzinfo=timezone.utc)


def ev(**kw):
    base = {"id": "x:1", "sport": "football", "competition": "", "participants": [], "title": "",
            "start_utc": "2026-11-14T15:00:00+00:00", "start_precision": "scheduled", "source_id": "api_sports"}
    base.update(kw)
    return taxonomy.classify(base)


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "s.sqlite3")

    def tearDown(self):
        self.temp.cleanup()


class ServerAndGuiTests(StoreCase):
    def client(self):
        return closing(IngressTestClient(self.store, "csrf-test"))

    def post(self, client, fields):
        body = urllib.parse.urlencode(dict(fields), doseq=True).encode()
        with client.open(urllib.request.Request(client.base, body, method="POST")) as response:
            return response.read().decode()

    def get(self, client, query=""):
        with client.open(client.base + query) as response:
            return response.read().decode()

    def test_zero_values_render(self):
        self.assertEqual(e(0), "0")
        self.assertEqual(e(False), "False")
        self.assertEqual(e(None), "")
        self.store.configure({"setup_complete": True})
        self.store.save_snapshot("epg-quality:farleyflex", {"country": "GB", "channels": 3, "valid_programmes": 0,
                                                            "generic_programmes": 0, "invalid_programmes": 0,
                                                            "full_coverage_channels": {"24h": 0, "72h": 0, "168h": 0},
                                                            "channels_needing_attention": []})
        with self.client() as client:
            page = self.get(client, "?page=guide")
        self.assertIn("0 / 3", page)
        self.assertIn("0 generic titles", page)

    def test_non_ascii_csrf_is_403_not_a_dropped_connection(self):
        with self.client() as client:
            with self.assertRaises(urllib.error.HTTPError) as denied:
                self.post(client, {"action": "finish", "csrf": "é"})
        self.assertEqual(denied.exception.code, 403)

    def test_query_string_message_cannot_spoof_an_app_alert(self):
        with self.client() as client:
            page = self.get(client, "?page=sources&message=Token+expired+paste+at+evil.example")
            self.assertNotIn("evil.example", page)
            self.assertNotIn("evil", self.get(client, "?page=sources&m=forged"))
            page = self.post(client, {"action": "schedule", "times": "04:00", "csrf": "csrf-test"})
        self.assertIn("Settings saved", page)

    def test_unexpected_action_error_still_redirects_with_notice(self):
        self.store.configure({"setup_complete": True})
        with self.client() as client, patch.object(Engine, "publish", side_effect=KeyError("boom")):
            page = self.post(client, {"action": "publish", "csrf": "csrf-test"})
        self.assertIn("Unexpected error (KeyError)", page)
        self.assertTrue(any(j["provider"] == "ui" and j["state"] == "error" for j in self.store.recent_jobs()))

    def test_rights_register_requires_attestation_and_records_changes(self):
        with self.client() as client:
            page = self.post(client, {"action": "approvals", "approve": ["openligadb", "jolpica"], "csrf": "csrf-test"})
            self.assertIn("Confirm you have reviewed", page)
            self.assertEqual(self.store.config()["publication_approvals"], [])
            self.post(client, {"action": "approvals", "approve": ["openligadb", "jolpica", "bogus"], "attest": "on", "csrf": "csrf-test"})
            self.assertEqual(self.store.config()["publication_approvals"], ["jolpica", "openligadb"])
            self.post(client, {"action": "approvals", "csrf": "csrf-test"})
        self.assertEqual(self.store.config()["publication_approvals"], [])
        self.assertEqual(len(self.store._get("approval_log")), 2)

    def test_publish_button_disabled_with_reasons(self):
        with self.client() as client:
            page = self.get(client, "?page=publishing")
        self.assertIn("Publishing is unavailable because publishing is not enabled", page)
        self.assertIn('<button type="submit" disabled>Publish feed now</button>', page)
        self.assertIn("Publication rights register", page)

    def test_github_target_validation_and_key_remove_conflict(self):
        for bad in [("..", "r", "main"), ("o", "..", "main"), ("o", "r", "-x"), ("-o", "r", "main"), ("o", "r", "a..b")]:
            with self.assertRaises(ValueError):
                validate_github_target(*bad)
        self.assertEqual(validate_github_target("jimmyfazz", "LiveSports-EPG", "main"), ("jimmyfazz", "LiveSports-EPG", "main"))
        with self.client() as client:
            page = self.post(client, {"action": "github", "owner": "..", "repository": "r", "branch": "main", "csrf": "csrf-test"})
            self.assertIn("Invalid GitHub owner", page)
            page = self.post(client, {"action": "sports", "provider": "football_data", "enabled": "on", "key": "k",
                                      "remove": "on", "csrf": "csrf-test"})
        self.assertIn("not both", page)
        self.assertEqual(self.store.config()["keys"].get("football_data", ""), "")

    def test_icon_and_healthz_routes(self):
        with self.client() as client:
            with client.open(client.base + "icon.png") as response:
                self.assertEqual(response.headers["Content-Type"], "image/png")
                self.assertEqual(response.read()[:4], b"\x89PNG")
            with client.open(client.base + "healthz") as response:
                self.assertTrue(json.loads(response.read())["ok"])

    def test_today_live_state_is_recomputed_at_view_time(self):
        self.store.configure({"setup_complete": True})
        match = ev(id="m1", competition="Premier League", competition_code="fd:PL", participants=["Arsenal", "Chelsea"])
        self.store.save_snapshot("today", linking.build_today([match], NOW - timedelta(hours=3)))  # collected at 11:00
        later = NOW + timedelta(hours=1, minutes=30)  # 15:30, mid-match

        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return later if tz is None else later.astimezone(tz)
        with self.client() as client, patch("sportsliveinfo.server.datetime", Clock):
            page = self.get(client, "?page=today")
        self.assertIn("Probably live", page)
        self.assertNotIn(">Upcoming<", page)

    def test_events_page_labels_sport_and_hides_duplicate_competition(self):
        self.store.configure({"setup_complete": True})
        self.store.save_snapshot("sports", {"events": [
            ev(id="c", sport="cricket", competition="The Ashes", participants=["Australia", "England"]),
            ev(id="p", competition="Premier League", competition_code="fd:PL", participants=["A", "B"])]})
        with self.client() as client:
            page = self.get(client, "?page=events")
        self.assertIn("Cricket · England (men) internationals", page)
        self.assertNotIn("<small>Premier League</small>", page)


class EngineTests(StoreCase):
    def test_full_discovery_runs_once_per_day_not_every_12h(self):
        engine = Engine(self.store)
        today = datetime.now(linking.LONDON).date()
        fresh = {"data": {"full_discovery_at": datetime.now(timezone.utc).isoformat()}, "updated_at": "x"}
        old = {"data": {"full_discovery_at": (datetime.now(timezone.utc) - timedelta(hours=26)).isoformat()}}
        legacy = {"updated_at": datetime.now(timezone.utc).isoformat(), "data": {}}
        self.assertEqual(len(engine._days("api_sports", fresh, today)), 1)
        self.assertEqual(len(engine._days("api_sports", old, today)), 7)
        self.assertEqual(len(engine._days("api_sports", legacy, today)), 7, "a recent today-only write must not suppress discovery")

    def test_withdrawn_fixture_removed_after_two_successful_absences(self):
        self.store.configure({"setup_complete": True, "sports": {"jolpica": False, "openf1": True}})
        rows = [{"session_key": 1, "session_name": "Race", "date_start": "2026-11-22T06:00:00+00:00"},
                {"session_key": 2, "session_name": "Qualifying", "date_start": "2026-11-21T06:00:00+00:00"}]
        engine = Engine(self.store)
        with patch("sportsliveinfo.providers.fetch", return_value=json.dumps(rows).encode()):
            engine._collect_sport("openf1", self.store.config())
        ids = lambda: {x["id"] for x in self.store.snapshot("sports:openf1")["data"]["events"]}
        with patch("sportsliveinfo.providers.fetch", return_value=json.dumps(rows[:1]).encode()):
            engine._collect_sport("openf1", self.store.config())
            self.assertIn("openf1:2", ids(), "one absence may be a partial upstream response")
            engine._collect_sport("openf1", self.store.config())
        self.assertNotIn("openf1:2", ids())
        self.assertIn("openf1:1", ids())

    def test_pacing_does_not_block_other_providers(self):
        engine = Engine(self.store)
        engine._last_call["thesportsdb"] = time.monotonic()
        waiter = threading.Thread(target=engine._pace, args=("thesportsdb",))
        waiter.start()
        time.sleep(0.05)
        started = time.monotonic()
        engine._pace("openf1")
        self.assertLess(time.monotonic() - started, 0.5)
        waiter.join()

    def test_corrupt_guide_does_not_stop_the_epg_lane(self):
        self.store.configure({"setup_complete": True, "sports": {"jolpica": False}, "epg": {"farleyflex": True, "uk_freeview": True}})
        now = datetime.now(timezone.utc)
        good = ('<tv><channel id="a"><display-name>BBC One</display-name></channel><programme channel="a" start="%s" stop="%s"><title>X</title></programme></tv>'
                % ((now - timedelta(hours=1)).strftime("%Y%m%d%H%M%S +0000"), (now + timedelta(hours=30)).strftime("%Y%m%d%H%M%S +0000"))).encode()

        def fetch(url, headers=None, max_bytes=0):
            return b"\x1f\x8b" + b"corrupt-gzip" if "farleyflex" in url else good
        with patch("sportsliveinfo.providers.fetch", side_effect=fetch):
            Engine(self.store).collect()
        self.assertIsNotNone(self.store.snapshot("epg:uk_freeview"))
        self.assertTrue(any(j["provider"] == "farleyflex" and j["state"] == "failed" for j in self.store.recent_jobs()))

    def test_scheduler_survives_exceptions(self):
        engine = Engine(self.store)
        ticks = iter([False, False, True])
        with patch.object(engine._scheduler_stop, "wait", side_effect=lambda _: next(ticks)), \
             patch.object(engine, "_scheduler_tick", side_effect=[RuntimeError("database is locked"), None]) as tick:
            engine.run_scheduler()
        self.assertEqual(tick.call_count, 2)
        self.assertTrue(any(j["provider"] == "scheduler" for j in self.store.recent_jobs()))

    def test_materialize_crash_is_recorded(self):
        self.store.configure({"setup_complete": True, "sports": {"jolpica": True}})
        with patch("sportsliveinfo.providers.fetch", return_value=b'{"MRData":{"RaceTable":{"Races":[]}}}'), \
             patch.object(Engine, "_materialize", side_effect=TypeError("bad")):
            self.assertFalse(Engine(self.store).collect())
        self.assertEqual(self.store.recent_jobs()[0]["state"], "failed")


class FeedAndPublisherTests(StoreCase):
    def setUp(self):
        super().setUp()
        self.store.configure({"setup_complete": True, "publication_approvals": ["openligadb"],
                              "github": {"enabled": True, "owner": "o", "repository": "feed", "branch": "main", "token": "t"}})
        self.store.save_snapshot("sports", {"events": [ev(id="openligadb:1", source_id="openligadb", sources=["openligadb", "api_sports"])]})

    def test_revision_ignores_health_churn_but_tracks_settings(self):
        first, _ = feed.build_feed(self.store, now=NOW)
        self.store.job("openligadb", "ok", "refreshed")
        second, _ = feed.build_feed(self.store, now=NOW)
        self.assertEqual(first["revision"], second["revision"])
        self.store.configure({"schedule": ["06:00"]})
        third, _ = feed.build_feed(self.store, now=NOW)
        self.assertNotEqual(first["revision"], third["revision"])

    def test_omitted_sources_lists_only_unapproved(self):
        self.store.configure({"publication_approvals": ["openligadb"]})
        manifest, _ = feed.build_feed(self.store, now=NOW)
        self.assertEqual(manifest["rights"]["events"]["omitted_unapproved_sources"], ["api_sports"])

    def test_unchanged_revision_republished_only_to_renew_expiry(self):
        commits = []
        with patch.object(Engine, "_github_commit", side_effect=lambda *a, **k: commits.append(a)):
            engine = Engine(self.store)
            engine.publish()
            engine.publish()
            self.assertEqual(len(commits), 1)
            state = self.store._get("feed_state")
            state["published_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
            self.store._put("feed_state", state)
            engine.publish()
        self.assertEqual(len(commits), 2)
        self.assertEqual(len(self.store._get("feed_state")["revisions"]), 1, "renewal must not duplicate history")

    def test_github_commit_uses_remote_tree_and_singular_ref(self):
        calls = []

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def opener(request, timeout=0):
            path = urllib.parse.urlsplit(request.full_url).path + ("?" + urllib.parse.urlsplit(request.full_url).query if urllib.parse.urlsplit(request.full_url).query else "")
            method = request.get_method()
            calls.append((method, path))
            body = json.loads(request.data) if request.data else None
            if method == "GET" and "/git/ref/heads/" in path:
                return Response(json.dumps({"object": {"sha": "head"}}).encode())
            if method == "GET" and "/git/commits/" in path:
                return Response(json.dumps({"tree": {"sha": "tree"}}).encode())
            if method == "GET" and "/git/trees/" in path:
                return Response(json.dumps({"truncated": False, "tree": [{"path": "v1/old.json", "type": "blob"}]}).encode())
            if method == "POST" and path.endswith("/git/blobs"):
                return Response(json.dumps({"sha": "blob"}).encode())
            if method == "POST" and path.endswith("/git/trees"):
                calls.append(("TREE", json.dumps(body["tree"])))
                return Response(json.dumps({"sha": "newtree"}).encode())
            if method == "POST" and path.endswith("/git/commits"):
                return Response(json.dumps({"sha": "commit"}).encode())
            if method == "PATCH":
                raise urllib.error.HTTPError(request.full_url, 422, "race", {}, io.BytesIO(b""))
            raise AssertionError((method, path))

        with patch.object(engine_module, "_github_open", side_effect=opener):
            with self.assertRaisesRegex(RuntimeError, "branch changed during publication"):
                Engine._github_commit("o", "feed", "main", "t", {"v1/manifest.json": b"{}"},
                                      ["v1/old.json", "v1/gone.json"], "msg", required={"v1/assets/x.json": b"{}"})
        tree = json.loads(next(c[1] for c in calls if c[0] == "TREE"))
        paths = {entry["path"]: entry["sha"] for entry in tree}
        self.assertIn("v1/assets/x.json", paths, "asset missing remotely is uploaded")
        self.assertIsNone(paths["v1/old.json"])
        self.assertNotIn("v1/gone.json", paths, "never delete a path absent from the remote tree")
        self.assertTrue(any("/git/ref/heads/main" in p for m, p in calls if m == "GET"))

    def test_network_failure_maps_to_runtime_error(self):
        with patch.object(engine_module, "_github_open", side_effect=urllib.error.URLError("dns")):
            with self.assertRaisesRegex(RuntimeError, "Could not reach GitHub"):
                Engine._github_commit("o", "feed", "main", "t", {}, [], "msg")


class MatchingAndParsingTests(unittest.TestCase):
    def test_standard_xmltv_doctype_accepted_internal_subset_rejected(self):
        ok = (b'<?xml version="1.0"?><!DOCTYPE tv SYSTEM "xmltv.dtd"><tv><channel id="a"><display-name>A</display-name></channel>'
              b'<programme channel="a" start="20261114150000 +0000" stop="20261114160000 +0000"><title>T</title></programme></tv>')
        self.assertEqual(len(providers.decode_xmltv(ok, "x")["programmes"]), 1)
        self.assertEqual(len(providers.decode_xmltv(gzip.compress(ok), "x")["programmes"]), 1)
        for bad in [b'<!DOCTYPE tv [<!ELEMENT tv ANY>]><tv/>', b'<!DOCTYPE tv SYSTEM "x"><tv><!DOCTYPE again></tv>']:
            with self.assertRaises(ValueError):
                providers.decode_xmltv(bad, "x")

    def test_provider_payload_edge_cases(self):
        rows = providers.api_sports_events(b'{"response":[{"fixture":{"id":1,"date":"2026-11-14T15:00:00+00:00","status":{"short":"NS"}},'
                                           b'"teams":{"home":null,"away":{"name":"B"}},"league":{"name":"L"}}]}')
        self.assertEqual(rows[0]["title"], "TBC v B")
        rows = providers.thesportsdb_events(b'{"events":[{"idEvent":"1","strSport":"Soccer","dateEvent":"2026-11-14","strTime":"TBC"}]}')
        self.assertEqual(rows[0]["start_precision"], "date_only")
        self.assertEqual(providers.status_of("Match Postponed"), "postponed")

    def test_taxonomy_fixes(self):
        self.assertEqual(ev(sport="aussie_rules", competition="AFL", competition_country="Australia")["category_id"], "aussie_rules.afl")
        women = ev(competition="UEFA Women's Euro", participants=["England", "Spain"])
        self.assertEqual((women["category_id"], women["tags"]), ("football.intl.england_women", ["team:england_women"]))
        self.assertEqual(ev(competition="Friendlies Clubs", participants=["England", "X"])["category_id"], "football.other")
        self.assertEqual(ev(sport="rugby", competition="Championship", competition_country="England")["sport"], "rugby")
        self.assertEqual(ev(sport="Fighting", competition="Boxing", title="Usyk vs Fury")["sport"], "boxing")
        self.assertEqual(ev(competition="English FA Cup")["category_id"], "football.fa_cup")

    def test_team_identity_is_strict(self):
        k = linking.team_key
        for a, b in [("Inter", "Inter Miami"), ("Paris FC", "Paris Saint-Germain"), ("Rangers", "Queens Park Rangers"),
                     ("Ireland", "Northern Ireland"), ("Jong Ajax", "Ajax"), ("United", "Manchester United")]:
            self.assertFalse(linking.same_team(k(a), k(b)), (a, b))
        for a, b in [("Leeds", "Leeds United"), ("Spurs", "Tottenham Hotspur"), ("Man City", "Manchester City FC")]:
            self.assertTrue(linking.same_team(k(a), k(b)), (a, b))

    def test_fusion_respects_competition_and_dedupes_ids(self):
        pl = ev(id="a", source_id="football_data", competition="Premier League", competition_country="England", participants=["Arsenal", "Chelsea"], start_utc="2026-11-14T17:30:00+00:00")
        wsl = ev(id="b", competition="Women's Super League", competition_country="England", participants=["Arsenal", "Chelsea"])
        self.assertEqual(len(linking.merge_events([pl, wsl])), 2)
        self.assertEqual(len(linking.merge_events([pl, dict(pl, start_utc="2026-11-14T18:00:00+00:00")])), 1)

    def test_provider_live_flag_is_time_bounded(self):
        stale = ev(status_normalized="live", start_utc="2026-11-10T15:00:00+00:00")
        self.assertEqual(linking.live_state(stale, NOW), "probably_finished")
        self.assertEqual(linking.live_state(ev(status_normalized="live"), NOW + timedelta(hours=1, minutes=10)), "live")

    def test_broadcast_candidates_need_the_fixture_phrase(self):
        def guide(title, channel="Sky Sports Main Event", hours=3):
            end = (datetime(2026, 11, 14, 14, tzinfo=timezone.utc) + timedelta(hours=hours)).isoformat()
            return {"mjh_sky_uk": {"channels": {"c": channel}, "programmes": [
                {"channel_id": "c", "start_utc": "2026-11-14T14:00:00+00:00", "end_utc": end, "title": title, "subtitle": ""}]}}
        match = ev(id="m", competition="Friendlies", participants=["Ireland", "Wales"])
        self.assertTrue(linking.broadcast_candidates([match], guide("Live International: Ireland v Wales"), NOW))
        for title, kw in [("Northern Ireland v Wales", {}), ("Ireland v Wales", {"hours": 30}),
                          ("Ireland v Wales", {"channel": "Sky Sports News"}), ("Ireland Women v Wales Women", {})]:
            self.assertFalse(linking.broadcast_candidates([match], guide(title, **kw), NOW), (title, kw))

    def test_channel_name_decorations_and_families(self):
        from sportsliveinfo.guide import canonical_channel, channel_families
        self.assertEqual(canonical_channel("mjh_sky_uk", "", "Sky Sports Main Event [VIP]"), "gb.sky.sports.main_event")
        self.assertEqual(canonical_channel("mjh_sky_uk", "", "BBC One (Backup)"), "gb.bbc.one")
        self.assertNotIn("sky_sport_nz", channel_families("Sky Sport 1 Germany"))
        self.assertIn("sky_sport_nz", channel_families("NZ: Sky Sport 1"))
        self.assertNotIn("us_networks", channel_families("TNT Sports Ultimate"))

    def test_guide_horizon_reported(self):
        from sportsliveinfo.guide import analyze_guide
        guide = {"source_id": "farleyflex", "channels": {"a": "BBC One"},
                 "programmes": [{"channel_id": "a", "start_utc": "2026-11-14T00:00:00+00:00", "end_utc": "2026-11-17T14:00:00+00:00", "title": "X"}]}
        self.assertEqual(analyze_guide(guide, now=NOW)["horizon_hours"], 72.0)


if __name__ == "__main__":
    unittest.main()
