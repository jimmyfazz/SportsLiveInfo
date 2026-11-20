"""League standings asset (sli.standings/1): decoders, collection budgets and reserves, kill switch, feed publication."""
import json
import tempfile
import urllib.parse
import urllib.request
from contextlib import closing
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from sportsliveinfo import feed, providers, standings
from sportsliveinfo.engine import Engine
from sportsliveinfo.storage import Store
from ingress_test_support import IngressTestClient

NOW = datetime(2026, 11, 20, 4, 0, tzinfo=timezone.utc)
STAMP = "2026-11-20T04:00:00Z"
REAL_FD_BUDGET = standings.FD_DAILY_BUDGET
TEAMS = ["Team %02d" % i for i in range(1, 37)]


def fd_row(position, name, **kw):
    row = {"position": position, "team": {"id": 100 + position, "name": name, "shortName": name[:4], "tla": "T%02d" % position},
           "playedGames": 10, "form": "W,D,L", "won": 5, "draw": 3, "lost": 2, "points": 18, "goalsFor": 15,
           "goalsAgainst": 9, "goalDifference": 6}
    row.update(kw)
    return row


def fd_payload(code, teams, *, stage="REGULAR_SEASON", group=None, extra=None, start="2026-08-15", end="2027-05-23"):
    blocks = [{"stage": stage, "type": "TOTAL", "group": group, "table": [fd_row(i, t) for i, t in enumerate(teams, 1)]}]
    blocks += extra or []
    return json.dumps({"filters": {"season": "2026"}, "competition": {"code": code},
                       "season": {"startDate": start, "endDate": end, "currentMatchday": 10},
                       "standings": blocks}).encode()


def as_payload(league_id, tables):
    return json.dumps({"errors": [], "response": [{"league": {"id": league_id, "standings": [
        [{"rank": i, "team": {"id": 50 + i, "name": t}, "points": 20, "goalsDiff": 4, "group": g, "form": "WWDLW",
          "all": {"played": 10, "win": 6, "draw": 2, "lose": 2, "goals": {"for": 14, "against": 10}}}
         for i, t in enumerate(teams, 1)] for g, teams in tables]}}]}).encode()


class DecoderTests(unittest.TestCase):
    def test_football_data_league_table(self):
        away = {"stage": "REGULAR_SEASON", "type": "AWAY", "group": None, "table": [fd_row(1, "Wrong Away")]}
        doc = standings.football_data_standings(fd_payload("PL", TEAMS[:20], extra=[away]), "football.premier_league", STAMP)
        self.assertEqual((doc["schema"], doc["competition_id"], doc["season"], doc["season_start_year"], doc["matchday"]),
                         ("sli.standings/1", "football.premier_league", "2026-27", 2026, 10))
        self.assertEqual((doc["teams"], doc["expected_teams"], doc["table_complete"], doc["source"], doc["observed_at"]),
                         (20, 20, True, "football_data", STAMP))
        self.assertEqual(len(doc["groups"]), 1)
        self.assertIsNone(doc["groups"][0]["name"])
        self.assertNotIn("Wrong Away", json.dumps(doc))              # only the TOTAL table is read
        first = doc["groups"][0]["rows"][0]
        self.assertEqual(first, {"position": 1, "participant": "Team 01", "participant_short": "Team", "participant_id": "fd:101",
                                 "played": 10, "won": 5, "drawn": 3, "lost": 2, "goals_for": 15, "goals_against": 9,
                                 "goal_diff": 6, "points": 18, "form": "WDL"})

    def test_partial_and_malformed_tables_are_never_complete(self):
        self.assertFalse(standings.football_data_standings(fd_payload("PL", TEAMS[:19]), "football.premier_league", STAMP)["table_complete"])
        payload = json.loads(fd_payload("PL", TEAMS[:20]))
        payload["standings"][0]["table"][3]["points"] = None          # one unreadable row is dropped
        doc = standings.football_data_standings(json.dumps(payload).encode(), "football.premier_league", STAMP)
        self.assertEqual((doc["teams"], doc["table_complete"]), (19, False))
        payload = json.loads(fd_payload("PL", TEAMS[:20]))
        payload["standings"][0]["table"][5]["position"] = 99          # positions must run 1..n
        doc = standings.football_data_standings(json.dumps(payload).encode(), "football.premier_league", STAMP)
        self.assertEqual((doc["teams"], doc["table_complete"]), (20, False))

    def test_cup_groups_and_new_format_champions_league(self):
        blocks = [{"stage": "GROUP_STAGE", "type": "TOTAL", "group": "GROUP_B", "table": [fd_row(1, "B1"), fd_row(2, "B2")]},
                  {"stage": "GROUP_STAGE", "type": "TOTAL", "group": "Group A", "table": [fd_row(1, "A1"), fd_row(2, "A2")]}]
        raw = json.dumps({"competition": {"code": "CL"}, "season": {"startDate": "2026-09-01", "endDate": "2027-05-30"},
                          "standings": blocks}).encode()
        doc = standings.football_data_standings(raw, "football.champions_league", STAMP)
        self.assertEqual([g["name"] for g in doc["groups"]], ["Group B", "Group A"])
        self.assertEqual((doc["groups"][0]["stage"], doc["teams"], doc["table_complete"]), ("GROUP_STAGE", 4, False))
        self.assertNotIn("matchday", doc)
        league = standings.football_data_standings(fd_payload("CL", TEAMS, stage="LEAGUE_STAGE"), "football.champions_league", STAMP)
        self.assertEqual((league["teams"], league["table_complete"], league["groups"][0]["name"]), (36, True, None))

    def test_rejects_other_competition_and_non_standings_payloads(self):
        for raw in (fd_payload("PD", TEAMS[:20]), b'{"matches":[]}', b'{"standings":[]}', b"[]",
                    json.dumps({"competition": {"code": "PL"}, "standings": [{"type": "TOTAL", "table": [{"position": 1}]}],
                                "season": {"startDate": "2026-08-15"}}).encode()):
            with self.assertRaises(ValueError):
                standings.football_data_standings(raw, "football.premier_league", STAMP)

    def test_form_is_letters_only(self):
        payload = json.loads(fd_payload("PL", TEAMS[:20]))
        payload["standings"][0]["table"][0]["form"] = "W;<b>"
        payload["standings"][0]["table"][1]["form"] = None
        rows = standings.football_data_standings(json.dumps(payload).encode(), "football.premier_league", STAMP)["groups"][0]["rows"]
        self.assertNotIn("form", rows[0])
        self.assertNotIn("form", rows[1])

    def test_api_sports_table(self):
        doc = standings.api_sports_standings(as_payload(39, [("Premier League", TEAMS[:20])]), "football.premier_league", STAMP, 2026)
        self.assertEqual((doc["source"], doc["teams"], doc["table_complete"], doc["season"], doc["groups"][0]["name"]),
                         ("api_sports", 20, True, "2026-27", None))
        self.assertEqual(doc["groups"][0]["rows"][0]["participant_id"], "as:51")
        self.assertEqual(doc["groups"][0]["rows"][0]["form"], "WWDLW")
        groups = standings.api_sports_standings(as_payload(2, [("Group A", TEAMS[:4]), ("Group B", TEAMS[4:8])]),
                                                "football.champions_league", STAMP, 2026)
        self.assertEqual([g["name"] for g in groups["groups"]], ["Group A", "Group B"])
        with self.assertRaises(ValueError):
            standings.api_sports_standings(as_payload(140, [("x", TEAMS[:20])]), "football.premier_league", STAMP, 2026)
        with self.assertRaises(ValueError):
            standings.api_sports_standings(b'{"response":[]}', "football.premier_league", STAMP, 2026)

    def test_every_competition_maps_to_a_taxonomy_id_and_the_codes_the_taxonomy_uses(self):
        from sportsliveinfo import taxonomy
        entries = {c["id"]: c for c in taxonomy.COMPETITIONS["football"]}
        for cid, spec in standings.COMPETITIONS.items():
            self.assertIn(cid, entries, cid)
            codes = entries[cid]["codes"] if "codes" in entries[cid] else entries[cid].get("code", [])
            self.assertIn("fd:" + spec["fd"], codes, cid)
            self.assertIn("as:%d" % spec["as"], codes, cid)
        for league in ("premier_league", "la_liga", "serie_a", "bundesliga", "ligue_1", "champions_league"):
            self.assertIn("football." + league, standings.COMPETITIONS)       # the six B1G tabs
        self.assertEqual({k: v["expected"] for k, v in standings.COMPETITIONS.items() if k.split(".")[1] in
                          ("champions_league", "premier_league", "la_liga", "serie_a", "bundesliga", "ligue_1")},
                         {"football.champions_league": 36, "football.premier_league": 20, "football.la_liga": 20,
                          "football.serie_a": 20, "football.bundesliga": 18, "football.ligue_1": 18})


class CollectionCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "s.sqlite3")
        self.store.configure({"setup_complete": True, "keys": {"football_data": "fdk"},
                              "sports": {"jolpica": False, "football_data": True}})
        self.engine = Engine(self.store)
        self.calls = []
        pace = patch.object(Engine, "_pace", lambda self, name: None)
        pace.start()
        self.addCleanup(pace.stop)
        self.answers = {}
        # The counters follow the real clock while tests move the simulated one: lift the cap except where it is tested.
        cap = patch.object(standings, "FD_DAILY_BUDGET", 100)
        cap.start()
        self.addCleanup(cap.stop)

    def conf(self, **update):
        if update:
            self.store.configure(update)
        return self.store.config()

    def collect(self, now=NOW, **update):
        def fetch(url, headers=None, max_bytes=0, response_headers=None):
            self.calls.append((url, dict(headers or {})))
            answer = next((v for k, v in self.answers.items() if k in url), None)
            if isinstance(answer, Exception):
                raise answer
            if answer is None:
                raise providers.UpstreamHTTPError(404, None)
            return answer
        with patch("sportsliveinfo.providers.fetch", side_effect=fetch):
            return standings.collect(self.engine, self.conf(**update), now=now)

    def answer(self, code, value):
        self.answers["/competitions/%s/standings" % code] = value

    def stub_all(self):
        for cid, spec in standings.COMPETITIONS.items():
            teams = TEAMS[:spec["expected"]]
            self.answers["/competitions/%s/standings" % spec["fd"]] = fd_payload(spec["fd"], teams)

    def held(self):
        return (self.store.snapshot("standings") or {}).get("data", {}).get("competitions", {})


class CollectTests(CollectionCase):
    def test_collects_every_competition_with_the_key_and_counts_calls(self):
        self.stub_all()
        summary = self.collect()
        n = len(standings.COMPETITIONS)
        self.assertIn("%d calls" % n, summary)
        self.assertEqual(len(self.calls), n)
        self.assertEqual({h["X-Auth-Token"] for _, h in self.calls}, {"fdk"})
        self.assertTrue(self.calls[0][0].startswith("https://api.football-data.org/v4/competitions/CL/standings"))
        usage = self.store.usage()
        self.assertEqual((usage["standings:football_data"], usage["football_data"]), (n, n))
        self.assertTrue(all(d["table_complete"] for d in self.held().values()))
        self.assertLessEqual(n, REAL_FD_BUDGET)
        self.assertEqual(self.store.recent_jobs(1, provider="standings")[0]["state"], "ok")

    def test_once_per_day_then_again_after_the_day_changes(self):
        self.stub_all()
        self.collect()
        self.calls.clear()
        self.assertIsNone(self.collect(now=NOW + timedelta(hours=8)))     # same London day, all complete: no calls
        self.assertEqual(self.calls, [])
        self.collect(now=NOW + timedelta(days=1))
        self.assertEqual(len(self.calls), len(standings.COMPETITIONS))

    def test_off_without_key_source_or_with_the_kill_switch(self):
        self.stub_all()
        self.assertIsNone(self.collect(publish_standings=False))
        self.assertIsNone(self.collect(publish_standings=True, keys={"football_data": ""}))
        self.assertIsNone(self.collect(keys={"football_data": "fdk"}, sports={"football_data": False}))
        self.assertEqual(self.calls, [])
        self.assertEqual(self.held(), {})
        self.assertTrue(standings.enabled({}))                           # default on
        self.assertTrue(self.store.config()["publish_standings"])
        self.assertFalse(self.store.config()["standings_api_sports"])

    def test_own_budget_caps_the_day(self):
        self.stub_all()
        with patch.object(standings, "FD_DAILY_BUDGET", 4):
            summary = self.collect()
        self.assertEqual(len(self.calls), 4)
        self.assertIn("daily standings budget (4) used", summary)
        self.assertEqual(len(self.held()), 4)

    def test_reserve_keeps_football_data_calls_for_fixtures(self):
        self.stub_all()
        limit = providers.SPORTS["football_data"][3]
        for _ in range(limit - standings.FD_RESERVE):
            self.store.increment("football_data", limit)
        summary = self.collect()
        self.assertEqual(self.calls, [])
        self.assertIn("kept for scheduled refreshes", summary)
        self.assertEqual(self.store.usage()["football_data"], limit - standings.FD_RESERVE)

    def test_rate_limit_backs_off_and_stops_the_pass(self):
        self.stub_all()
        self.answer("CL", providers.UpstreamHTTPError(429, "120"))
        summary = self.collect()
        self.assertEqual(len(self.calls), 1)
        self.assertIn("rate limit", summary)
        self.assertGreater(self.store._get("sports_backoff:football_data"), NOW.isoformat())
        self.calls.clear()
        later = datetime.now(timezone.utc) + timedelta(hours=3)
        self.assertIn("0 calls", self.collect(now=later) or "")           # the shared backoff still holds
        self.assertEqual(self.calls, [])

    def test_plan_refusal_skips_only_that_competition_for_days(self):
        self.stub_all()
        self.answer("ELC", providers.UpstreamHTTPError(403, None))
        self.collect()
        self.assertNotIn("football.championship", self.held())
        self.assertEqual(len(self.held()), len(standings.COMPETITIONS) - 1)
        self.calls.clear()
        self.collect(now=NOW + timedelta(days=1))
        self.assertFalse(any("/ELC/" in u for u, _ in self.calls))
        self.calls.clear()
        self.collect(now=NOW + timedelta(days=standings.SKIP_DAYS + 1))
        self.assertTrue(any("/ELC/" in u for u, _ in self.calls))

    def test_bad_payload_keeps_the_last_good_table(self):
        self.stub_all()
        self.collect()
        before = json.dumps(self.held()["football.premier_league"], sort_keys=True)
        self.answer("PL", b'{"unexpected": true}')
        self.collect(now=NOW + timedelta(days=1))
        self.assertEqual(json.dumps(self.held()["football.premier_league"], sort_keys=True), before)

    def test_an_incomplete_answer_never_replaces_a_complete_table_of_the_same_season(self):
        self.stub_all()
        self.collect()
        self.answer("PL", fd_payload("PL", TEAMS[:7]))
        self.collect(now=NOW + timedelta(days=1))
        self.assertEqual(self.held()["football.premier_league"]["teams"], 20)
        self.assertEqual(self.held()["football.premier_league"]["observed_at"], STAMP)

    def test_a_failed_competition_is_not_retried_within_two_hours(self):
        self.answer("CL", fd_payload("CL", TEAMS[:3]))     # incomplete
        with patch.object(standings, "COMPETITIONS", {"football.champions_league": standings.COMPETITIONS["football.champions_league"]}):
            self.collect()
            self.assertEqual(len(self.calls), 1)
            self.collect(now=NOW + timedelta(minutes=30))
            self.assertEqual(len(self.calls), 1)
            self.collect(now=NOW + timedelta(hours=3))
            self.assertEqual(len(self.calls), 2)

    def test_api_sports_is_off_by_default_and_never_called(self):
        self.store.configure({"keys": {"football_data": "fdk", "api_sports": "ask"}})
        self.answers["/standings?"] = as_payload(39, [("x", TEAMS[:20])])
        self.collect()                                                    # football-data fails 404 everywhere
        self.assertFalse(any("api-sports" in u for u, _ in self.calls))

    def test_api_sports_fills_only_what_football_data_could_not(self):
        self.stub_all()
        self.answer("ELC", providers.UpstreamHTTPError(403, None))
        self.answers["https://v3.football.api-sports.io/standings"] = as_payload(40, [("Championship", TEAMS[:24])])
        summary = self.collect(keys={"football_data": "fdk", "api_sports": "ask"}, standings_api_sports=True)
        api = [(u, h) for u, h in self.calls if "api-sports" in u]
        self.assertEqual(len(api), 1)
        self.assertIn("league=40&season=2026", api[0][0])
        self.assertEqual(api[0][1], {"x-apisports-key": "ask"})
        self.assertEqual(self.held()["football.championship"]["source"], "api_sports")
        self.assertEqual(self.held()["football.premier_league"]["source"], "football_data")
        usage = self.store.usage()
        self.assertEqual((usage["standings:api_sports"], usage["api_sports"]), (1, 1))
        self.assertIn("calls", summary)

    def test_api_sports_has_its_own_small_cap_and_respects_the_live_reserve(self):
        for cid, spec in standings.COMPETITIONS.items():
            self.answer(spec["fd"], providers.UpstreamHTTPError(403, None))
            self.answers["league=%d&" % spec["as"]] = as_payload(spec["as"], [("x", TEAMS[:spec["expected"]])])
        self.collect(keys={"football_data": "fdk", "api_sports": "ask"}, standings_api_sports=True)
        self.assertEqual(self.store.usage()["standings:api_sports"], standings.AS_DAILY_BUDGET)
        self.assertEqual(len(self.held()), standings.AS_DAILY_BUDGET)
        # reserve: with the product already at limit - LIVE_RESERVE nothing is called
        from sportsliveinfo.engine import LIVE_RESERVE
        with self.store._db() as db:
            db.execute("DELETE FROM requests")
        limit = providers.SPORTS["api_sports"][3]
        for _ in range(limit - LIVE_RESERVE):
            self.store.increment("api_sports", limit)
        self.calls.clear()
        self.collect(now=NOW + timedelta(days=1))
        self.assertFalse(any("api-sports" in u for u, _ in self.calls))


class FeedTests(CollectionCase):
    def build(self, now=NOW + timedelta(hours=1)):
        manifest, files = feed.build_feed(self.store, now=now)
        return manifest, files

    def assets(self, manifest):
        return [a for a in manifest["assets"] if a["kind"].startswith("standings:")]

    def test_published_with_capability_rights_and_attribution(self):
        self.stub_all()
        self.collect()
        manifest, files = self.build()
        assets = self.assets(manifest)
        self.assertEqual([a["kind"] for a in assets], ["standings:" + cid for cid in standings.COMPETITIONS])
        self.assertTrue(all(not a["required"] and a["schema"] == "sli.standings/1" and a["path"] in files for a in assets))
        self.assertLess(max(a["bytes"] for a in assets), 100_000)
        self.assertIn("standings", manifest["capabilities"])
        self.assertEqual(manifest["format"], "sli/1.6")                   # additive, no format minor change
        rights = manifest["rights"]["standings"]
        self.assertEqual((rights["enabled"], rights["max_age_days"]), (True, standings.MAX_AGE_DAYS))
        self.assertEqual(rights["sources"], [{"source": "football_data", "text": "Football data provided by the Football-Data.org API",
                                              "licence": "football-data.org terms"}])
        self.assertTrue(manifest["compatibility"]["standings"]["enabled"])
        self.assertIn("football_data", {a["source"] for a in manifest["rights"]["attribution"]})
        doc = json.loads(files[assets[0]["path"]])
        self.assertEqual(doc["competition_id"], "football.champions_league")

    def test_nothing_published_before_a_collection_and_revision_is_stable_after(self):
        manifest, _ = self.build()
        self.assertEqual(self.assets(manifest), [])
        self.assertNotIn("standings", manifest["capabilities"])
        self.assertNotIn("standings", manifest["rights"])
        self.stub_all()
        self.collect()
        first, _ = self.build()
        again, _ = self.build(now=NOW + timedelta(hours=2))
        self.assertEqual(first["revision"], again["revision"])             # time passing alone is no new revision
        self.assertNotEqual(first["revision"], manifest["revision"])       # new data is

    def test_kill_switch_removes_assets_capability_and_rights(self):
        self.stub_all()
        self.collect()
        before, _ = self.build()
        self.store.configure({"publish_standings": False})
        manifest, _ = self.build()
        self.assertEqual(self.assets(manifest), [])
        for part in (manifest["capabilities"], manifest["rights"], manifest["compatibility"]):
            self.assertNotIn("standings", part)
        self.assertNotEqual(before["revision"], manifest["revision"])

    def test_a_table_older_than_the_age_limit_is_dropped(self):
        self.stub_all()
        self.collect()
        manifest, _ = self.build(now=NOW + timedelta(days=standings.MAX_AGE_DAYS, minutes=1))
        self.assertEqual(self.assets(manifest), [])
        self.assertNotIn("standings", manifest["capabilities"])

    def test_private_feed_carries_the_same_tables(self):
        self.stub_all()
        self.collect()
        manifest, _ = feed.build_feed(self.store, now=NOW + timedelta(hours=1), private=True)
        self.assertEqual(len(self.assets(manifest)), len(standings.COMPETITIONS))

    def test_stored_garbage_is_ignored(self):
        self.store.save_snapshot("standings", {"competitions": {"football.premier_league": {"schema": "other"},
                                                                 "football.serie_a": "x", "bogus.id": {}}})
        manifest, _ = self.build()
        self.assertEqual(self.assets(manifest), [])


class IngressTests(CollectionCase):
    def test_scheduler_page_shows_and_switches_the_kill_switch(self):
        with closing(IngressTestClient(self.store, "csrf-test")) as client:
            with client.open(client.base + "?page=scheduler") as response:
                page = response.read().decode()
            self.assertIn("League tables", page)
            self.assertIn("football-data.org", page)
            body = urllib.parse.urlencode({"csrf": "csrf-test", "action": "standings", "api_sports": "on"}).encode()
            with client.open(urllib.request.Request(client.base, body, method="POST")) as response:
                response.read()
            config = self.store.config()
            self.assertEqual((config["publish_standings"], config["standings_api_sports"]), (False, True))
            with client.open(client.base + "?page=scheduler") as response:
                self.assertIn("Switched off.", response.read().decode())


if __name__ == "__main__":
    unittest.main()
