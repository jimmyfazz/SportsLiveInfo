"""v0.3 source expansion, sports taxonomy, fusion, today view and broadcast candidates."""
import json
import tempfile
import unittest
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from ingress_test_support import IngressTestClient

from sportsliveinfo import linking, providers, taxonomy
from sportsliveinfo.engine import Engine
from sportsliveinfo.guide import analyze_guide, canonical_channel, channel_families, normalized_name
from sportsliveinfo.storage import Store

NOW = datetime(2026, 11, 14, 14, 0, tzinfo=timezone.utc)  # 14:00 GMT, a Saturday


def ev(**kw):
    base = {"id": "x:1", "sport": "football", "competition": "", "participants": [], "title": "",
            "start_utc": "2026-11-14T15:00:00+00:00", "start_precision": "scheduled", "source_id": "api_sports",
            "broadcasts": [], "broadcast_verified": False}
    base.update(kw)
    return base


class TaxonomyTests(unittest.TestCase):
    def cat(self, **kw):
        return taxonomy.classify(ev(**kw))["category_id"]

    def test_england_and_home_nation_internationals_get_their_own_rows(self):
        self.assertEqual(self.cat(competition="World Cup - Qualification Europe", competition_country="World",
                                  participants=["England", "Serbia"]), "football.intl.england")
        self.assertEqual(self.cat(competition="Friendlies", competition_country="World",
                                  participants=["Spain", "England W"]), "football.intl.england_women")
        self.assertEqual(self.cat(competition="UEFA Nations League", participants=["Wales", "Iceland"]), "football.intl.home_nations")
        self.assertEqual(self.cat(competition="Euro U21 Qualification", participants=["England U21", "Latvia U21"]), "football.intl.england_u21")
        tags = taxonomy.classify(ev(competition="Friendlies", participants=["England", "Brazil"]))["tags"]
        self.assertIn("team:england", tags)

    def test_club_competitions_and_country_qualified_names(self):
        self.assertEqual(self.cat(competition="Premier League", competition_code="fd:PL"), "football.premier_league")
        self.assertEqual(self.cat(competition="Premier League", competition_country="England"), "football.premier_league")
        self.assertEqual(self.cat(competition="Premier League", competition_country="Egypt"), "football.other")
        self.assertEqual(self.cat(competition="UEFA Champions League", competition_country="World"), "football.champions_league")
        self.assertEqual(self.cat(competition="UEFA Europa League", competition_country="World"), "football.europa_league")
        self.assertEqual(self.cat(competition="UEFA Europa Conference League", competition_country="World"), "football.conference_league")
        self.assertEqual(self.cat(competition="FA Cup", competition_country="England"), "football.fa_cup")
        self.assertEqual(self.cat(competition="FA Cup", competition_country="Scotland"), "football.scottish_cup")
        self.assertEqual(self.cat(competition="League Cup", competition_country="England"), "football.efl_cup")
        self.assertEqual(self.cat(competition="League Cup", competition_country="Scotland"), "football.scottish_league_cup")
        self.assertEqual(self.cat(competition="Championship", competition_country="Scotland"), "football.other")
        self.assertEqual(self.cat(competition="Serie A", competition_country="Brazil"), "football.brasileirao")
        self.assertEqual(self.cat(competition="1. Bundesliga", competition_code="old:bl1"), "football.bundesliga")

    def test_sport_scoped_ambiguous_names(self):
        rugby = taxonomy.classify(ev(sport="rugby", competition="Six Nations", participants=["England", "France"]))
        self.assertEqual((rugby["sport"], rugby["category_id"]), ("rugby_union", "rugby_union.six_nations"))
        self.assertIn("team:england", rugby["tags"])
        self.assertEqual(taxonomy.classify(ev(sport="rugby", competition="Super League", competition_country="England"))["sport"], "rugby_league")
        self.assertEqual(taxonomy.classify(ev(sport="rugby", competition="Mystery Cup"))["sport"], "rugby")
        self.assertEqual(self.cat(sport="Darts", competition="Premier League"), "darts.premier_league")
        self.assertEqual(self.cat(sport="golf", competition="US Open"), "golf.majors")
        self.assertEqual(self.cat(sport="tennis", competition="US Open"), "tennis.us_open")
        self.assertEqual(self.cat(sport="Ice Hockey", competition="NHL", competition_country="USA"), "ice_hockey.nhl")
        self.assertEqual(self.cat(sport="basketball", competition="WNBA", competition_country="USA"), "basketball.wnba")
        self.assertEqual(self.cat(sport="cricket", competition="Big Bash League"), "cricket.big_bash")
        self.assertEqual(self.cat(sport="cricket", participants=["England", "Australia"], competition="Ashes Series"), "cricket.intl.england")

    def test_ppv_tag_for_combat_sports(self):
        tags = taxonomy.classify(ev(sport="boxing", title="Fury v Usyk 3 — Sky Sports Box Office PPV"))["tags"]
        self.assertIn("ppv", tags)
        self.assertNotIn("ppv", taxonomy.classify(ev(sport="football", title="PPV Arsenal"))["tags"])


class NewDecoderTests(unittest.TestCase):
    def test_api_sports_games_rugby_and_nested_nfl(self):
        rugby = {"errors": [], "response": [{"id": 77, "timestamp": 1763132400, "status": {"short": "NS"},
                 "country": {"name": "World"}, "league": {"id": 51, "name": "Six Nations"},
                 "teams": {"home": {"name": "England"}, "away": {"name": "France"}}}]}
        rows = providers.api_sports_games_events(json.dumps(rugby).encode(), "api_sports_rugby", "rugby")
        self.assertEqual(rows[0]["start_utc"], "2025-11-14T15:00:00+00:00")
        self.assertEqual((rows[0]["id"], rows[0]["competition_country"]), ("api-sports-rugby:77", "World"))
        nfl = {"response": [{"game": {"id": 9, "date": {"timestamp": 1763132400}, "status": {"short": "NS"}, "venue": {"name": "Tottenham"}},
                             "league": {"id": 1, "name": "NFL"}, "teams": {"home": {"name": "Jets"}, "away": {"name": "Bills"}}}]}
        row = providers.api_sports_games_events(json.dumps(nfl).encode(), "api_sports_nfl", "american_football")[0]
        self.assertEqual((row["venue"], row["title"]), ("Tottenham", "Jets v Bills"))
        with self.assertRaises(ValueError):
            providers.api_sports_games_events(b'{"errors":{"token":"bad"}}', "api_sports_rugby", "rugby")

    def test_mma_openf1_thesportsdb_and_cricket(self):
        mma = {"response": [{"id": 5, "timestamp": 1763164800, "slug": "UFC 330", "is_main": True, "category": "Heavyweight",
                             "status": {"short": "NS"}, "fighters": {"first": {"name": "A"}, "second": {"name": "B"}}}]}
        self.assertEqual(providers.api_sports_mma_events(json.dumps(mma).encode())[0]["event_type"], "main_event")
        f1 = [{"session_key": 1, "session_name": "Race", "date_start": "2026-11-22T06:00:00+00:00",
               "date_end": "2026-11-22T08:00:00+00:00", "country_name": "Qatar"},
              {"session_key": 2, "session_name": "Day 1", "date_start": "2026-02-01T08:00:00+00:00"}]
        rows = providers.openf1_events(json.dumps(f1).encode())
        self.assertEqual([(r["session"], r["end_utc"]) for r in rows], [("race", "2026-11-22T08:00:00+00:00")])
        self.assertEqual(providers.thesportsdb_events(b'{"events": null}'), [])
        tsdb = {"events": [{"idEvent": "1", "strSport": "Darts", "strLeague": "Premier League", "strEvent": "Littler vs Humphries",
                            "strTimestamp": "2026-11-14T19:00:00", "strStatus": "Not Started"},
                           {"idEvent": "2", "strSport": "Soccer", "strHomeTeam": "A", "strAwayTeam": "B",
                            "dateEvent": "2026-11-14", "strPostponed": "yes"}]}
        rows = providers.thesportsdb_events(json.dumps(tsdb).encode())
        self.assertEqual(rows[0]["start_utc"], "2026-11-14T19:00:00+00:00")
        self.assertEqual((rows[1]["start_precision"], rows[1]["status_normalized"]), ("date_only", "postponed"))
        with self.assertRaises(ValueError):
            providers.thesportsdb_events(b'[]')
        cricket = {"status": "success", "apikey": "never-stored", "data": [
            {"id": "t1", "name": "England vs Australia, 1st Test, The Ashes 2026-27", "matchType": "test",
             "dateTimeGMT": "2026-11-20T23:30:00", "teams": ["England", "Australia"], "matchStarted": False, "matchEnded": False},
            {"id": "o1", "name": "India vs New Zealand, 2nd ODI", "matchType": "odi", "dateTimeGMT": "2026-11-15T08:00:00",
             "teams": ["India", "New Zealand"], "matchStarted": True, "matchEnded": False}]}
        rows = providers.cricketdata_events(json.dumps(cricket).encode())
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[0]["competition"], "The Ashes 2026-27")
        self.assertEqual([r["start_precision"] for r in rows[:2]], ["scheduled", "not_before"])
        self.assertEqual(rows[4]["title"], "England v Australia — Day 5")
        self.assertEqual(rows[5]["status_normalized"], "live")
        self.assertNotIn("never-stored", json.dumps(rows))
        with self.assertRaises(ValueError):
            providers.cricketdata_events(b'{"status":"failure","reason":"Invalid API Key"}')

    def test_football_data_precision_and_status_normaliser(self):
        payload = {"matches": [{"id": 1, "utcDate": "2026-11-29T15:00:00Z", "status": "SCHEDULED",
                                "competition": {"name": "FA Cup", "code": "FAC"}, "homeTeam": {"name": "A FC", "shortName": "A"},
                                "awayTeam": {"name": "B FC"}}]}
        row = providers.football_data_events(json.dumps(payload).encode())[0]
        self.assertEqual((row["start_precision"], row["competition_code"], row["participants_short"]), ("provisional", "fd:FAC", ["A", "B FC"]))
        for raw, state in [("FT", "finished"), ("2H", "live"), ("PST", "postponed"), ("CANC", "cancelled"),
                           ("TIMED", "scheduled"), ("IN_PLAY", "live"), ("weird", "unknown")]:
            self.assertEqual(providers.status_of(raw), state, raw)

    def test_xmltv_carries_live_repeat_subtitle_categories_and_icons(self):
        xml = (b'<tv><channel id="s1"><display-name lang="fr">Sky Un</display-name><display-name lang="en">Sky Sports Main Event</display-name>'
               b'<icon src="https://logo.example/s1.png"/></channel>'
               b'<programme channel="s1" start="20261114150000Z" stop="20261114170000 +0000"><title>Live Premier League</title>'
               b'<sub-title>Arsenal v Manchester City</sub-title><category>Sport</category><category>Football</category><live/></programme>'
               b'<programme channel="ghost" start="20261114170000 +0000" stop="20261114180000 +0000"><title>Classic</title><previously-shown/></programme></tv>')
        guide = providers.decode_xmltv(xml, "farleyflex")
        first, second = guide["programmes"]
        self.assertEqual(guide["channels"]["s1"], "Sky Sports Main Event")
        self.assertEqual(guide["channel_icons"]["s1"], "https://logo.example/s1.png")
        self.assertEqual((first["start_utc"], first["subtitle"], first["categories"], first["is_live"]),
                         ("2026-11-14T15:00:00+00:00", "Arsenal v Manchester City", ["Sport", "Football"], True))
        self.assertTrue(second["is_repeat"])
        self.assertEqual(guide["orphaned_programmes"], 1)


class ChannelIdentityTests(unittest.TestCase):
    def test_b1g_farleyflex_ids_and_international_markets(self):
        self.assertEqual(canonical_channel("farleyflex", "skysportspremiereleague.uk", "anything"), "gb.sky.sports.premier_league")
        self.assertEqual(canonical_channel("epgshare_my", "", "MYS | Astro Premier League FHD"), "my.astro.premier_league")
        self.assertEqual(canonical_channel("iptv_epg_ge", "", "Setanta Sports 1 HD"), "ge.setanta.sports.1")
        self.assertEqual(canonical_channel("epgshare_hk", "", "HK: Now Sports Premier League"), "hk.now.sports.premier_league")
        self.assertEqual(canonical_channel("mjh_sky_uk", "", "ITV1"), "gb.itv.one")
        self.assertIsNone(canonical_channel("epgshare_uk", "", "Setanta Sports 1"))
        self.assertIsNone(canonical_channel("epgshare_uk", "", "Sky Sports+ 3"))
        self.assertIsNone(canonical_channel("epgtalk_sports", "", "Sky Sports Main Event"), "multi-country guide has no market")
        self.assertEqual(normalized_name("SPORTS | beIN MAX 4"), "bein max 4")

    def test_lineup_families_from_owner_categories(self):
        self.assertIn("now_sports_hk", channel_families("Now Sports Premier League 2"))
        self.assertIn("peacock", channel_families("Peacock 05: NFL Sunday"))
        self.assertIn("setanta", channel_families("Setanta Sports 2"))
        self.assertIn("bein", channel_families("beIN MAX 4"))
        self.assertIn("sky_sports_plus", channel_families("UK | Sky Sports+ 7"))
        self.assertNotIn("us_networks", channel_families("TNT Sports 1"))
        self.assertIn("us_team_channels", channel_families("NBA League Pass 3"))
        guide = {"source_id": "epgshare_hk", "channels": {"a": "Now Sports Premier League", "b": "beIN Sports 1"}, "programmes": []}
        families = analyze_guide(guide, now=NOW)["families"]
        self.assertEqual((families["now_sports_hk"]["channels"], families["bein"]["channels"]), (1, 1))


class FusionTests(unittest.TestCase):
    def test_same_fixture_from_two_providers_is_corroborated(self):
        a = taxonomy.classify(ev(id="football-data:1", source_id="football_data", competition="Premier League", competition_code="fd:PL",
                                 participants=["Manchester City FC", "Tottenham Hotspur FC"], start_precision="scheduled"))
        b = taxonomy.classify(ev(id="api-sports:9", source_id="api_sports", competition="Premier League", competition_country="England",
                                 participants=["Man City", "Spurs"], start_utc="2026-11-14T15:05:00+00:00"))
        c = taxonomy.classify(ev(id="api-sports:10", source_id="api_sports", participants=["Manchester United", "Everton"]))
        merged = linking.merge_events([a, b, c])
        self.assertEqual(len(merged), 2)
        city = [m for m in merged if m["id"] == "football-data:1"][0]
        self.assertEqual((city["fixture_confidence"], city["corroboration"], city["sources"]), ("corroborated", 2, ["api_sports", "football_data"]))
        self.assertFalse(city["start_conflict"])

    def test_no_merge_for_different_sides_variants_or_tbc(self):
        rows = [ev(id="a:1", source_id="football_data", participants=["Manchester City", "Arsenal"]),
                ev(id="b:1", source_id="api_sports", participants=["Manchester United", "Arsenal"]),
                ev(id="c:1", source_id="thesportsdb", participants=["England", "Spain"]),
                ev(id="d:1", source_id="football_data", participants=["England Women", "Spain Women"]),
                ev(id="e:1", source_id="api_sports", participants=["TBC", "TBC"]),
                ev(id="f:1", source_id="thesportsdb", participants=["TBC", "TBC"])]
        self.assertEqual(len(linking.merge_events([taxonomy.classify(r) for r in rows])), 6)

    def test_f1_sessions_merge_and_keep_openf1_end_time(self):
        jolpica = taxonomy.classify(ev(id="f1:2026:23:race", source_id="jolpica", sport="motorsport", competition="Formula 1",
                                       session="race", title="Qatar Grand Prix", start_utc="2026-11-29T16:00:00+00:00"))
        openf1 = taxonomy.classify(ev(id="openf1:1", source_id="openf1", sport="motorsport", competition="Formula 1", session="race",
                                      start_utc="2026-11-29T16:00:00+00:00", end_utc="2026-11-29T18:00:00+00:00"))
        quali = taxonomy.classify(ev(id="openf1:2", source_id="openf1", sport="motorsport", competition="Formula 1", session="qualifying",
                                     start_utc="2026-11-28T17:00:00+00:00"))
        merged = linking.merge_events([jolpica, openf1, quali])
        race = [m for m in merged if m["session"] == "race"][0]
        self.assertEqual((len(merged), race["id"], race["end_utc"]), (2, "f1:2026:23:race", "2026-11-29T18:00:00+00:00"))

    def test_start_time_disagreement_is_flagged(self):
        merged = linking.merge_events([taxonomy.classify(ev(id="a:1", source_id="football_data", participants=["Celtic", "Rangers"])),
                                       taxonomy.classify(ev(id="b:1", source_id="api_sports", participants=["Celtic", "Rangers"],
                                                            start_utc="2026-11-14T17:30:00+00:00"))])
        self.assertTrue(merged[0]["start_conflict"])
        self.assertEqual(set(merged[0]["start_alternatives"]), {"football_data", "api_sports"})


def _guide(source, channel_id, name, programmes):
    return {"source_id": source, "channels": {channel_id: name},
            "programmes": [{"channel_id": channel_id, "subtitle": "", "is_live": False, "is_repeat": False, **p} for p in programmes]}


class TodayAndBroadcastTests(unittest.TestCase):
    def setUp(self):
        self.match = taxonomy.classify(ev(id="m1", competition="Premier League", competition_code="fd:PL",
                                          participants=["Arsenal", "Manchester City"], start_utc="2026-11-14T15:00:00+00:00"))
        self.ko = {"start_utc": "2026-11-14T14:30:00+00:00", "end_utc": "2026-11-14T17:15:00+00:00"}

    def test_single_and_multi_guide_candidates_never_verified(self):
        farley = _guide("farleyflex", "skysportsmainevent.uk", "Sky Sports Main Event",
                        [dict(self.ko, title="Live Premier League", subtitle="Arsenal v Man City", is_live=True)])
        result = linking.broadcast_candidates([self.match], {"farleyflex": farley}, NOW)
        status, candidates = result["m1"]
        self.assertEqual((status, candidates[0]["canonical_channel_id"], candidates[0]["epg_live_flag"]),
                         ("single_guide_match", "gb.sky.sports.main_event", True))
        mjh = _guide("mjh_sky_uk", "SkyMain", "Sky Sports Main Event HD", [dict(self.ko, title="Arsenal v Manchester City")])
        status, candidates = linking.broadcast_candidates([self.match], {"farleyflex": farley, "mjh_sky_uk": mjh}, NOW)["m1"]
        self.assertEqual(status, "multi_guide_match")
        self.assertEqual(sorted(candidates[0]["epg_sources"]), ["farleyflex", "mjh_sky_uk"])
        today = linking.build_today([self.match], NOW, {"farleyflex": farley})
        self.assertFalse(today["sports"][0]["categories"][0]["events"][0]["broadcast_verified"])

    def test_hard_negatives_highlights_repeats_wrong_team_and_unknown_channel(self):
        guides = {
            "farleyflex": _guide("farleyflex", "skysportsmainevent.uk", "Sky Sports Main Event", [
                dict(self.ko, title="Arsenal v Manchester City Highlights"),
                dict(self.ko, title="Arsenal v Manchester United")]),
            "mjh_sky_uk": _guide("mjh_sky_uk", "x", "Sky Sports+ 4", [dict(self.ko, title="Arsenal v Manchester City")]),
            "epgshare_uk": {"source_id": "epgshare_uk", "channels": {"y": "TNT Sports 1"}, "programmes": [
                dict(self.ko, channel_id="y", title="Arsenal v Manchester City", subtitle="", is_live=False, is_repeat=True)]},
        }
        self.assertEqual(linking.broadcast_candidates([self.match], guides, NOW), {})

    def test_today_groups_by_sport_category_with_featured_and_live_state(self):
        events = [self.match,
                  taxonomy.classify(ev(id="e1", competition="Friendlies", participants=["England", "Japan"], start_utc="2026-11-14T19:45:00+00:00")),
                  taxonomy.classify(ev(id="r1", sport="rugby", competition="Autumn Nations Series", participants=["Scotland", "Fiji"],
                                       start_utc="2026-11-14T13:10:00+00:00", source_id="api_sports_rugby")),
                  taxonomy.classify(ev(id="tomorrow", competition="Premier League", competition_code="fd:PL",
                                       participants=["Chelsea", "Everton"], start_utc="2026-11-15T14:00:00+00:00"))]
        today = linking.build_today(events, NOW)
        self.assertEqual(today["count"], 3)
        football = today["sports"][0]
        self.assertEqual(football["sport"], "football")
        self.assertEqual([c["id"] for c in football["categories"]], ["football.intl.england", "football.premier_league"])
        self.assertEqual([e["id"] for e in today["featured"]], ["r1", "e1"])
        states = {e["id"]: e["live_state"] for s in today["sports"] for c in s["categories"] for e in c["events"]}
        self.assertEqual(states, {"m1": "upcoming", "e1": "upcoming", "r1": "live_probable"})
        self.assertEqual(today["live_now"], 1)


class EngineExpansionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "state.sqlite3")

    def tearDown(self):
        self.temp.cleanup()

    def test_new_sources_default_disabled_and_options_present(self):
        cfg = self.store.config()
        self.assertTrue(cfg["sports"]["jolpica"])
        self.assertFalse(any(v for k, v in cfg["sports"].items() if k != "jolpica"))
        self.assertFalse(any(cfg["epg"].values()))
        self.assertIn("epgshare_hk", cfg["epg"])
        self.assertIn("Darts", cfg["options"]["thesportsdb_sports"])

    def test_day_scoped_partial_failure_keeps_other_days(self):
        self.store.configure({"setup_complete": True, "sports": {"jolpica": False, "api_sports_rugby": True}, "keys": {"api_sports": "k"}})
        today = datetime.now(linking.LONDON).date()
        old_day = (today + timedelta(days=2)).isoformat()
        self.store.save_snapshot("sports:api_sports_rugby", {"events": [
            {"id": "old", "start_utc": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(timespec="seconds"),
             "fetch_scope": old_day, "source_id": "api_sports_rugby", "sport": "rugby"}]})
        with self.store._db() as db:  # stale snapshot forces full seven-day discovery
            db.execute("UPDATE snapshots SET updated_at='2000-01-01T00:00:00+00:00'")
        calls = []

        def fake_fetch(url, headers=None, max_bytes=0):
            day = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["date"][0]
            calls.append(day)
            if day == old_day:
                raise RuntimeError("HTTP 500 from upstream")
            stamp = int(datetime.fromisoformat(day + "T15:00:00+00:00").timestamp())
            return json.dumps({"response": [{"id": day, "timestamp": stamp, "league": {"name": "Premiership Rugby"},
                                             "teams": {"home": {"name": "Bath"}, "away": {"name": "Saracens"}}}]}).encode()

        with patch("sportsliveinfo.providers.fetch", side_effect=fake_fetch), patch("sportsliveinfo.engine.time.sleep"):
            Engine(self.store).collect()
        self.assertEqual(len(calls), 7)
        events = self.store.snapshot("sports:api_sports_rugby")["data"]["events"]
        ids = {e["id"] for e in events}
        self.assertIn("old", ids, "failed day keeps its previous fixtures")
        self.assertEqual(len(ids), 7)
        self.assertTrue(any(j["state"] == "partial" for j in self.store.recent_jobs()))

    def test_quota_exhaustion_mid_plan_saves_completed_scopes(self):
        self.store.configure({"setup_complete": True, "sports": {"jolpica": False, "thesportsdb": True},
                              "options": {"thesportsdb_sports": ["Soccer", "Darts"]}})
        for _ in range(118):
            self.store.increment("thesportsdb", 120)
        with patch("sportsliveinfo.providers.fetch", return_value=b'{"events": null}') as fetch, patch("sportsliveinfo.engine.time.sleep"):
            Engine(self.store).collect()
        self.assertEqual(fetch.call_count, 2)
        snap = self.store.snapshot("sports:thesportsdb")["data"]
        self.assertEqual(len(snap["scopes_ok"]), 2)
        self.assertEqual(len(snap["scopes_failed"]), 4)

    def test_materialize_writes_classified_deduplicated_today_snapshot(self):
        self.store.configure({"setup_complete": True, "sports": {"football_data": True, "api_sports": True}, "epg": {"farleyflex": True}})
        self.store.save_snapshot("sports:football_data", {"events": [ev(id="football-data:1", source_id="football_data", competition="Premier League",
                                 competition_code="fd:PL", participants=["Arsenal FC", "Manchester City FC"])]})
        self.store.save_snapshot("sports:api_sports", {"events": [ev(id="api-sports:2", competition="Premier League", competition_country="England",
                                 participants=["Arsenal", "Manchester City"]),
                                 ev(id="api-sports:3", competition="FA Cup", competition_country="England", participants=["Leeds", "Hull"],
                                    start_utc="2026-11-14T12:30:00+00:00")]})
        self.store.save_snapshot("epg:farleyflex", _guide("farleyflex", "tntsports1.uk", "TNT Sports 1", [
            {"start_utc": "2026-11-14T14:00:00+00:00", "end_utc": "2026-11-14T17:00:00+00:00", "title": "Arsenal v Manchester City"}]))
        Engine(self.store)._materialize(now=NOW)
        today = self.store.snapshot("today")["data"]
        football = today["sports"][0]
        self.assertEqual([c["id"] for c in football["categories"]], ["football.premier_league", "football.fa_cup"])
        pl = football["categories"][0]["events"][0]
        self.assertEqual((pl["fixture_confidence"], pl["broadcast_candidates"][0]["canonical_channel_id"]),
                         ("corroborated", "gb.tnt.sports.1"))
        sports = self.store.snapshot("sports")["data"]["events"]
        self.assertEqual(len(sports), 2)

    def test_publish_strips_private_epg_derived_fields(self):
        self.store.configure({"setup_complete": True, "publication_approvals": ["openligadb"],
                              "github": {"enabled": True, "owner": "o", "repository": "feed", "branch": "main", "token": "t"}})
        self.store.save_snapshot("sports", {"events": [ev(id="openligadb:1", source_id="openligadb", broadcast_status="single_guide_match",
                                                          broadcast_candidates=[{"channel_name": "Private"}], fetch_scope="league:bl1")]})
        commits = []
        with patch.object(Engine, "_github_commit", side_effect=lambda *a: commits.append(a)):
            Engine(self.store).publish()
        uploads = commits[0][4]
        payload = b"".join(d for p, d in uploads.items() if "/assets/events/" in p).decode()
        self.assertIn("openligadb:1", payload)
        self.assertIn("v1/manifest.json", uploads)
        for private in ("broadcast_candidates", "Private", "fetch_scope", "broadcast_status"):
            self.assertNotIn(private, payload)


class IngressExpansionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "state.sqlite3")
        self.client = IngressTestClient(self.store, "csrf-test")
        self.base = self.client.base

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def get(self, query):
        with self.client.open(self.base + query, timeout=3) as response:
            return response.read().decode()

    def post(self, fields):
        body = urllib.parse.urlencode(dict(fields, csrf="csrf-test"), doseq=True).encode()
        with self.client.open(urllib.request.Request(self.base, body, method="POST"), timeout=3) as response:
            return response.read().decode()

    def test_shared_api_sports_key_and_source_options(self):
        self.post({"action": "sports", "provider": "api_sports_rugby", "enabled": "on", "key": "shared-secret"})
        cfg = self.store.config()
        self.assertEqual(cfg["keys"], {"api_sports": "shared-secret"})
        self.assertTrue(cfg["sports"]["api_sports_rugby"])
        self.post({"action": "options", "tsdb": ["Darts", "Snooker", "NotASport"], "old": ["bl2"]})
        self.assertEqual(self.store.config()["options"], {"thesportsdb_sports": ["Darts", "Snooker"], "openligadb_leagues": ["bl2"]})
        sources = self.get("?page=sources")
        self.assertNotIn("shared-secret", sources)
        self.assertIn("EPG Share HK1", sources)
        self.assertIn("Setanta", sources)

    def test_today_and_filtered_events_pages(self):
        self.store.configure({"setup_complete": True})
        events = [taxonomy.classify(ev(id="e1", competition="Friendlies", participants=["England", "Japan"])),
                  taxonomy.classify(ev(id="p1", competition="Premier League", competition_code="fd:PL", participants=["Arsenal", "Chelsea"]))]
        self.store.save_snapshot("today", linking.build_today(events, NOW))
        self.store.save_snapshot("sports", {"events": events})
        page = self.get("?page=today")
        self.assertIn("Featured: England", page)
        self.assertIn("England (men) internationals", page)
        filtered = self.get("?page=events&sport=football&category=football.premier_league")
        self.assertIn("1 of 2 events", filtered)


if __name__ == "__main__":
    unittest.main()
