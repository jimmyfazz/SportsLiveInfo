"""0.3.23 (feed sli/1.6): honest live state, the live-status lane, approved-only public merge, tiers and
guide-corroborated broadcast links (audit 15 Nov 2026: C1, C2, C6, C9; contract sections 1-4)."""
import json
import tempfile
import threading
import unittest
import urllib.parse
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from ingress_test_support import IngressTestClient
from sportsliveinfo import engine as engine_module, feed, linking, providers, taxonomy
from sportsliveinfo.engine import Engine
from sportsliveinfo.storage import Store

NOW = datetime(2026, 11, 14, 15, 30, tzinfo=timezone.utc)     # Saturday afternoon, London = UTC


def iso(moment):
    return moment.isoformat(timespec="seconds")


def ev(**kw):
    base = {"id": "x:1", "sport": "football", "competition": "", "participants": [], "title": "",
            "start_utc": "2026-11-14T15:00:00+00:00", "start_precision": "scheduled", "source_id": "api_sports"}
    base.update(kw)
    return base


class FixedClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz is None else NOW.astimezone(tz)


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "s.sqlite3")

    def tearDown(self):
        self.temp.cleanup()


# ---- C6: API-Sports live codes ---------------------------------------------------------------------------------
class ApiSportsLiveCodeTests(unittest.TestCase):
    def games(self, name, short):
        payload = {"errors": [], "response": [{"id": 7, "timestamp": int(NOW.timestamp()), "status": {"short": short},
                                               "teams": {"home": {"name": "A"}, "away": {"name": "B"}},
                                               "league": {"id": 1, "name": "L"}}]}
        event, = providers.api_sports_games_events(json.dumps(payload), source_id=name,
                                                   sport=providers.API_SPORTS_SPORT[name])
        return event["status_normalized"]

    def test_every_product_maps_its_in_play_codes_to_live(self):
        cases = {"api_sports_rugby": ["1H", "2H", "HT", "ET", "BT", "PT"],
                 "api_sports_basketball": ["Q1", "Q2", "Q3", "Q4", "OT", "BT", "HT"],
                 "api_sports_hockey": ["P1", "P2", "P3", "OT", "PT", "BT"],
                 "api_sports_nfl": ["Q1", "Q2", "Q3", "Q4", "OT", "HT"],
                 "api_sports_baseball": ["IN1", "IN5", "IN9", "IN10"],
                 "api_sports_handball": ["1H", "2H", "HT", "ET", "BT", "PT"],
                 "api_sports_volleyball": ["S1", "S2", "S3", "S4", "S5"],
                 "api_sports_afl": ["Q1", "Q2", "QT", "Q3", "HT", "Q4"]}
        for name, codes in cases.items():
            for code in codes:
                self.assertEqual(self.games(name, code), "live", (name, code))
            self.assertEqual(self.games(name, "NS"), "scheduled", name)
            self.assertEqual(self.games(name, "FT"), "finished", name)

    def test_nfl_nested_game_object(self):
        payload = {"errors": [], "response": [{"game": {"id": 3, "date": {"timestamp": int(NOW.timestamp())},
                                                        "status": {"short": "Q3"}},
                                               "teams": {"home": {"name": "A"}, "away": {"name": "B"}}}]}
        event, = providers.api_sports_games_events(json.dumps(payload), source_id="api_sports_nfl",
                                                   sport="american_football")
        self.assertEqual(event["status_normalized"], "live")

    def test_football_and_mma(self):
        for short in ("1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT"):
            payload = {"errors": [], "paging": {"current": 1, "total": 1}, "response": [
                {"fixture": {"id": 1, "date": iso(NOW), "status": {"short": short}},
                 "teams": {"home": {"name": "A"}, "away": {"name": "B"}}, "league": {"id": 39, "name": "Premier League"}}]}
            event, = providers.api_sports_events(json.dumps(payload))
            self.assertEqual(event["status_normalized"], "live", short)
        for short, state in (("IN", "live"), ("EOR", "live"), ("NS", "scheduled"), ("FT", "finished")):
            payload = {"errors": [], "response": [{"id": 1, "timestamp": int(NOW.timestamp()), "status": {"short": short},
                                                   "fighters": {"first": {"name": "A"}, "second": {"name": "B"}}}]}
            event, = providers.api_sports_mma_events(json.dumps(payload))
            self.assertEqual(event["status_normalized"], state, short)

    def test_product_codes_do_not_leak_into_other_sources(self):
        self.assertEqual(providers.status_of("IN"), "unknown")               # only the MMA API means "in progress"
        self.assertEqual(providers.status_of("P2"), "unknown")
        self.assertEqual(providers.status_of("IN", "ice_hockey"), "unknown")
        self.assertEqual(providers.status_of("P2", "ice_hockey"), "live")


# ---- C2: honest live state --------------------------------------------------------------------------------------
class HonestLiveStateTests(unittest.TestCase):
    def test_only_the_current_test_day_is_live(self):
        start = NOW - timedelta(days=2, hours=4)
        payload = {"status": "success", "data": [{"id": "t1", "dateTimeGMT": start.strftime("%Y-%m-%dT%H:%M:%S"),
                                                  "name": "England v India, 1st Test, India tour", "matchType": "test",
                                                  "teams": ["England", "India"], "matchStarted": True,
                                                  "matchEnded": False}]}
        days = providers.cricketdata_events(json.dumps(payload), now=NOW)
        self.assertEqual([d["status_normalized"] for d in days], ["finished", "finished", "live", "scheduled", "scheduled"])
        before = providers.cricketdata_events(json.dumps(payload), now=start - timedelta(hours=1))
        self.assertEqual(before[0]["status_normalized"], "live")       # provider says started: day 1 only
        self.assertEqual({d["status_normalized"] for d in before[1:]}, {"scheduled"})

    def test_expected_durations_follow_the_contract(self):
        cases = [(dict(sport="football"), 120), (dict(sport="rugby_union"), 120), (dict(sport="rugby_league"), 120),
                 (dict(sport="tennis"), 180), (dict(sport="cricket", match_type="t20"), 240),
                 (dict(sport="cricket", match_type="t20i"), 240), (dict(sport="cricket", match_type="odi"), 480),
                 (dict(sport="cricket", match_type="test", day_number=2), 450),
                 (dict(sport="motorsport", session="race"), 150), (dict(sport="golf"), 360), (dict(sport="darts"), 240),
                 (dict(sport="snooker"), 240), (dict(sport="boxing"), 240), (dict(sport="basketball"), 150),
                 (dict(sport="ice_hockey"), 165), (dict(sport="american_football"), 210), (dict(sport="baseball"), 210),
                 (dict(sport="handball"), 100), (dict(sport="motorsport", session="qualifying"), 90),
                 (dict(sport="horse_racing"), 300), (dict(sport="cycling"), 300), (dict(sport="mma"), 240),
                 (dict(sport="aussie_rules"), 150), (dict(sport="netball"), 90), (dict(sport="volleyball"), 120)]
        for event, minutes in cases:
            self.assertEqual(taxonomy.expected_minutes(event), minutes, event)
        self.assertEqual(linking.expected_end(ev()), datetime(2026, 11, 14, 17, 0, tzinfo=timezone.utc))
        self.assertEqual(linking.expected_end(ev(end_utc="2026-11-14T16:00:00+00:00")),
                         datetime(2026, 11, 14, 16, 0, tzinfo=timezone.utc))

    def test_live_is_trusted_only_when_fresh_and_in_the_window(self):
        live = taxonomy.classify(ev(status_normalized="live", status_observed_at=iso(NOW - timedelta(minutes=10))))
        self.assertEqual(linking.live_state(live, NOW), "live")
        self.assertEqual(linking.live_state(live, NOW + timedelta(minutes=40)), "unknown")   # observation 50 min old
        fresh_late = dict(live, status_observed_at=iso(NOW + timedelta(hours=2)))
        self.assertEqual(linking.live_state(fresh_late, NOW + timedelta(hours=2)), "live")    # 17:30 = end + 30
        fresh_later = dict(live, status_observed_at=iso(NOW + timedelta(hours=2, minutes=5)))
        self.assertNotEqual(linking.live_state(fresh_later, NOW + timedelta(hours=2, minutes=5)), "live")
        early = dict(live, status_observed_at=iso(NOW - timedelta(hours=1)))
        self.assertNotEqual(linking.live_state(early, NOW - timedelta(hours=1)), "live")     # before kick-off


# ---- C9: merged status ------------------------------------------------------------------------------------------
class MergedStatusTests(unittest.TestCase):
    def pair(self, fd_status, fd_seen, as_status, as_seen):
        fd = taxonomy.classify(ev(id="football-data:1", source_id="football_data", competition="Premier League",
                                  competition_code="fd:PL", participants=["Arsenal", "Chelsea"], status=fd_status.upper(),
                                  status_normalized=providers.status_of(fd_status), status_observed_at=fd_seen))
        api = taxonomy.classify(ev(id="api-sports:1", competition="Premier League", competition_code="as:39",
                                   participants=["Arsenal", "Chelsea"], status=as_status,
                                   status_normalized=providers.status_of(as_status), status_observed_at=as_seen))
        merged, = linking.merge_events([fd, api])
        return merged

    def test_most_advanced_then_most_recent_status_wins(self):
        merged = self.pair("timed", "2026-11-14T15:20:00+00:00", "1H", "2026-11-14T15:20:00+00:00")
        self.assertEqual((merged["id"], merged["status_normalized"], merged["status"]),
                         ("football-data:1", "live", "1H"))       # primary record kept, status from API-Sports
        merged = self.pair("finished", "2026-11-14T17:00:00+00:00", "2H", "2026-11-14T16:30:00+00:00")
        self.assertEqual(merged["status_normalized"], "finished")
        merged = self.pair("timed", "2026-11-14T17:05:00+00:00", "2H", "2026-11-14T16:45:00+00:00")
        self.assertEqual((merged["status_normalized"], merged["status_observed_at"]),
                         ("live", "2026-11-14T16:45:00+00:00"))   # a delayed "TIMED" never hides play in progress
        merged = self.pair("timed", "2026-11-14T12:00:00+00:00", "NS", "2026-11-14T12:05:00+00:00")
        self.assertEqual((merged["status_normalized"], merged["status_observed_at"]),
                         ("scheduled", "2026-11-14T12:05:00+00:00"))


# ---- C1: approved-only public merge -----------------------------------------------------------------------------
class ApprovedOnlyPublicMergeTests(StoreCase):
    def setUp(self):
        super().setUp()
        self.store.configure({"setup_complete": True, "sports": {"jolpica": False, "football_data": True, "api_sports": True},
                              "publication_approvals": ["football_data"]})
        common = dict(competition="Premier League", participants=["Arsenal", "Chelsea"], title="Arsenal v Chelsea",
                      start_utc="2026-11-14T17:30:00+00:00", status_normalized="scheduled")
        self.store.save_snapshot("sports:football_data", {"events": [
            ev(id="football-data:1", source_id="football_data", competition_code="fd:PL", **common)]})
        self.store.save_snapshot("sports:api_sports", {"events": [
            ev(id="api-sports:1", competition_code="as:39", **common),
            ev(id="api-sports:2", competition="Premier League", competition_code="as:39", participants=["Spurs", "Leeds"],
               title="Spurs v Leeds", start_utc="2026-11-14T20:00:00+00:00")]})
        Engine(self.store)._materialize(now=NOW)

    def published(self, private=False):
        manifest, files = feed.build_feed(self.store, now=NOW, private=private)
        events = {}
        for asset in manifest["assets"]:
            if asset["kind"].split(":")[0] in ("events", "events_extra"):
                events.update({e["id"]: e for e in json.loads(files[asset["path"]])["events"]})
        return manifest, events

    def test_unapproved_corroboration_no_longer_removes_an_approved_fixture(self):
        private = self.store.snapshot("sports")["data"]["events"]
        self.assertEqual(next(e for e in private if e["id"] == "football-data:1")["sources"], ["api_sports", "football_data"])
        manifest, events = self.published()
        self.assertEqual(set(events), {"football-data:1"})
        event = events["football-data:1"]
        self.assertEqual((event["sources"], event["fixture_confidence"]), (["football_data"], "reported"))
        self.assertEqual(manifest["rights"]["events"]["omitted_unapproved_sources"], ["api_sports"])
        self.assertNotIn("api-sports", json.dumps(events))
        _, private_events = self.published(private=True)
        self.assertEqual(private_events["football-data:1"]["sources"], ["api_sports", "football_data"])
        self.assertIn("api-sports:2", private_events)

    def test_changed_approvals_fall_back_to_the_fail_closed_filter(self):
        self.store.configure({"publication_approvals": ["football_data", "openligadb"]})
        _, events = self.published()
        self.assertEqual(events, {})          # the mixed fixture is not published until the next collection
        self.store.configure({"publication_approvals": ["football_data", "api_sports"]})
        _, events = self.published()
        self.assertEqual(set(events), {"football-data:1", "api-sports:2"})


# ---- Tiers (contract §3) ----------------------------------------------------------------------------------------
class TierTests(StoreCase):
    def test_core_and_extra_rules(self):
        def tier(**kw):
            return feed.event_tier(taxonomy.classify(ev(**kw)))
        self.assertEqual(tier(competition="Premier League", competition_code="fd:PL", competition_country="England"), "core")
        self.assertEqual(tier(competition="National League", competition_country="England"), "core")
        self.assertEqual(tier(competition="League of Ireland Premier Division", competition_country="Ireland"), "core")
        self.assertEqual(tier(competition="Ligue 2", competition_country="France"), "core")
        self.assertEqual(tier(competition="Premiership 2", competition_country="Scotland"), "core")
        self.assertEqual(tier(competition="Premier League 2", competition_country="England"), "extra")      # youth
        self.assertEqual(tier(competition="U18 Premier League", competition_country="England"), "extra")
        self.assertEqual(tier(competition="Liga Nacional", competition_country="Honduras"), "extra")
        self.assertEqual(tier(competition="Friendlies", competition_country="World", participants=["England", "Japan"]), "core")
        self.assertEqual(tier(sport="tennis", competition="ITF M15 Example"), "extra")      # CA-17: minor tours
        self.assertEqual(tier(sport="cricket", competition="Ranji Trophy"), "core")
        self.assertEqual(tier(sport="horse_racing", competition="Kempton"), "core")
        self.assertEqual(tier(sport="boxing", competition="Fight night", title="Main event PPV"), "core")
        self.assertEqual(tier(sport="basketball", competition="NBA", competition_country="USA"), "core")
        self.assertEqual(tier(sport="basketball", competition="ACB", competition_country="Spain"), "extra")
        self.assertEqual(tier(sport="ice_hockey", competition="KHL", competition_country="Russia"), "extra")
        self.assertEqual(feed.event_tier({"origin": "guide_listing", "sport": "football", "category_id": "football.other"}),
                         "core")

    def test_extra_events_leave_the_day_assets_and_an_oversized_asset_is_reported(self):
        self.store.configure({"publication_approvals": ["api_sports"]})
        rows = [taxonomy.classify(ev(id="api-sports:%d" % i, competition="Liga Nacional", competition_country="Honduras",
                                     title="Team %d v Other %d" % (i, i), participants=["Team %d" % i, "Other %d" % i],
                                     start_utc="2026-11-14T20:00:00+00:00", sources=["api_sports"]))
                for i in range(40)]
        rows.append(taxonomy.classify(ev(id="api-sports:999", competition="Premier League", competition_code="as:39",
                                         competition_country="England", participants=["Arsenal", "Chelsea"],
                                         sources=["api_sports"])))
        self.store.save_snapshot("sports", {"events": rows, "generated_at": iso(NOW)})
        manifest, files = feed.build_feed(self.store, now=NOW)
        kinds = {a["kind"]: a for a in manifest["assets"]}
        day = json.loads(files[kinds["events:2026-11-14"]["path"]])["events"]
        extra = json.loads(files[kinds["events_extra:2026-11-14"]["path"]])["events"]
        self.assertEqual([e["id"] for e in day], ["api-sports:999"])
        self.assertEqual(len(extra), 40)
        self.assertEqual(manifest["coverage"]["tiers"], {"core": 1, "extra": 40})
        self.assertEqual((manifest["coverage"]["today"], manifest["coverage"]["today_extra"]), (1, 40))
        limit = len(files[kinds["events_extra:2026-11-14"]["path"]]) - 1
        small = {"schema": "sli.taxonomy/1"}
        with patch.object(feed, "MAX_READER_ASSET_BYTES", limit), \
                patch.object(feed, "taxonomy_document", return_value=small), \
                patch.object(feed, "channels_document", return_value={"schema": "sli.channels/1"}):
            manifest, _ = feed.build_feed(self.store, now=NOW)
        self.assertNotIn("events_extra:2026-11-14", {a["kind"] for a in manifest["assets"]})
        self.assertTrue(any("events_extra:2026-11-14" in n for n in manifest["notices"]))


# ---- Guide-corroborated links (contract §4) ---------------------------------------------------------------------
class GuideCorroborationTests(unittest.TestCase):
    EVENT = {"broadcast_status": "multi_guide_match", "start_utc": "2026-11-14T15:00:00+00:00",
             "start_precision": "scheduled", "status_normalized": "scheduled"}
    CANDIDATE = {"canonical_channel_id": "gb.sky.sports.main_event", "channel_identity_method": "registry",
                 "match_confidence": "high", "programme_start_utc": "2026-11-14T14:30:00+00:00",
                 "epg_sources": ["farleyflex", "epgtalk_uk"]}

    def check(self, event=None, **candidate):
        return linking.guide_corroborated(dict(self.EVENT, **(event or {})), dict(self.CANDIDATE, **candidate))

    def test_rule_and_hard_negatives(self):
        self.assertTrue(self.check())
        self.assertTrue(self.check(programme_start_utc="2026-11-14T14:00:00+00:00"))      # kick-off - 60 min
        self.assertTrue(self.check(programme_start_utc="2026-11-14T15:20:00+00:00"))      # kick-off + 20 min
        self.assertTrue(self.check(channel_identity_method="identity_registry"))
        self.assertFalse(self.check(programme_start_utc="2026-11-14T13:59:00+00:00"))
        self.assertFalse(self.check(programme_start_utc="2026-11-14T15:21:00+00:00"))
        self.assertFalse(self.check(channel_identity_method="dictionary"))                # dictionary-only id
        self.assertFalse(self.check(channel_identity_method="identity_dictionary"))
        self.assertFalse(self.check(epg_sources=["farleyflex"]))
        # S2: both from Sky's own EPG is ONE family, so it is not independent evidence (own_epg off) ...
        self.assertFalse(linking.guide_corroborated(dict(self.EVENT), dict(self.CANDIDATE, epg_sources=["uk_freeview", "m3upt_sky"]),
                                                    own_epg=False))
        # ... but Sky's own EPG is first-hand for Sky's own channel (broadcaster_own_epg_v1), and only for it.
        self.assertTrue(self.check(epg_sources=["uk_freeview", "m3upt_sky"]))
        self.assertTrue(self.check(epg_sources=["uk_freeview"]))
        self.assertFalse(self.check(epg_sources=["uk_freeview"], canonical_channel_id="gb.itv.one"))   # carriage listing
        self.assertFalse(self.check(epg_sources=["uk_freeview"], canonical_channel_id="gb.tnt.sports.1"))
        self.assertFalse(self.check(epg_sources=["uk_freeview"], channel_identity_method="dictionary"))
        self.assertFalse(self.check(epg_sources=["uk_freeview"], programme_start_utc="2026-11-14T13:59:00+00:00"))
        self.assertFalse(self.check(epg_sources=["epgshare_uk"]))                          # unverified lineage never counts
        self.assertFalse(self.check(epg_sources=["m3upt_sky_it"], canonical_channel_id="it.sky.sport"))
        self.assertFalse(self.check(epg_sources=["epgtalk_uk", "epgtalk_sports"]))         # one publisher
        self.assertFalse(self.check(epg_sources=["farleyflex", "epgshare_uk"]))            # unverified lineage
        self.assertFalse(self.check(epg_sources=["farleyflex", "iptv_epg_gb", "fr_mena_grab"]))
        self.assertTrue(self.check(epg_sources=["uk_freeview", "farleyflex"]))
        self.assertFalse(self.check({"broadcast_status": "guide_listing_match"}))         # the loose matcher
        self.assertFalse(self.check({"broadcast_status": "guide_listed", "origin": "guide_listing"}))
        self.assertFalse(self.check({"status_normalized": "postponed"}))
        self.assertFalse(self.check({"start_precision": "time_tbc"}))

    def test_published_link_is_corroborated_but_never_verified(self):
        event = dict(self.EVENT, broadcast_candidates=[dict(self.CANDIDATE)], broadcast_verified=True,
                     id="e", sport="football", category_id="football.premier_league", title="t")
        link, = feed._broadcast_links(event)
        self.assertEqual((link["status"], link["verification"], link["guides"]),
                         ("guide_corroborated", "independent_guides_v1", 2))
        self.assertFalse(feed._event_public(event)["broadcast_verified"])
        single = dict(event, broadcast_candidates=[dict(self.CANDIDATE, epg_sources=["farleyflex"])])
        self.assertEqual(feed._broadcast_links(single)[0]["status"], "guide_listed_unverified")
        self.assertNotIn("verification", feed._broadcast_links(single)[0])

    def test_lineage_audit(self):
        family = providers.EPG_FAMILY
        self.assertEqual(family["farleyflex"], "mytelly")
        self.assertEqual(len({family[g] for g in ("uk_freeview", "m3upt_sky", "m3upt_sky_it", "m3upt_freeview_uk",
                                                  "pt_m3upt")}), 1)
        self.assertEqual({family[g] for g in providers.EPG if g.startswith("epgtalk")}, {"schedules_direct"})
        self.assertEqual({family[g] for g in providers.EPG if g.startswith("mjh_")}, {"mjh"})
        for guide in providers.EPG:
            self.assertIn(guide, family)
            if guide.startswith(("epgshare_", "iptv_epg_")) or guide in ("fr_mena_grab", "es_doblem"):
                self.assertIn(family[guide], providers.UNVERIFIED_LINEAGE_FAMILIES, guide)
        self.assertEqual(linking.independent_guide_families(["farleyflex", "uk_freeview", "epgtalk_uk", "epgshare_uk"]),
                         {"mytelly", "sky_epg", "schedules_direct"})


# ---- Live-status lane (contract §2) -----------------------------------------------------------------------------
def board(*rows):
    return json.dumps({"errors": [], "paging": {"current": 1, "total": 1}, "response": [
        {"fixture": {"id": fid, "date": "2026-11-14T15:00:00+00:00", "status": {"short": short}},
         "teams": {"home": {"name": "Arsenal"}, "away": {"name": "Chelsea"}},
         "league": {"id": 39, "name": "Premier League"}} for fid, short in rows]}).encode()


class LiveLaneBase(StoreCase):
    def setUp(self):
        super().setUp()
        self.store.configure({"setup_complete": True, "keys": {"api_sports": "k"},
                              "sports": {"jolpica": False, "api_sports": True, "api_sports_hockey": True},
                              "publication_approvals": ["api_sports", "api_sports_hockey"],
                              "github": {"enabled": True, "auto_publish": True, "owner": "o", "repository": "feed",
                                         "branch": "main", "token": "t"}})
        self.engine = Engine(self.store)
        self.urls = []
        pace = patch.object(Engine, "_pace", lambda self, name: None)
        pace.start()
        self.addCleanup(pace.stop)

    def snapshot(self, start="2026-11-14T15:00:00+00:00", hockey=False):
        self.store.save_snapshot("sports:api_sports", {"events": [
            ev(id="api-sports:1", competition="Premier League", competition_code="as:39", competition_country="England",
               participants=["Arsenal", "Chelsea"], title="Arsenal v Chelsea", start_utc=start, status="NS",
               status_normalized="scheduled", status_observed_at="2026-11-14T12:00:00+00:00")]})
        if hockey:
            self.store.save_snapshot("sports:api_sports_hockey", {"events": [
                ev(id="api-sports-hockey:5", sport="ice_hockey", source_id="api_sports_hockey", competition="NHL",
                   competition_country="USA", participants=["Rangers", "Bruins"], title="Rangers v Bruins",
                   start_utc="2026-11-14T15:00:00+00:00", status_normalized="scheduled",
                   status_observed_at="2026-11-14T12:00:00+00:00")]})
        self.engine._materialize(now=NOW)

    def run_lane(self, payload, now=NOW):
        def fetch(url, headers=None, max_bytes=0, response_headers=None):
            self.urls.append(url)
            return payload(url) if callable(payload) else payload
        with patch("sportsliveinfo.providers.fetch", side_effect=fetch):
            return self.engine.live_lane(now=now)


class LiveLaneTests(LiveLaneBase):
    def test_no_calls_when_nothing_is_in_play(self):
        self.snapshot(start="2026-11-14T20:00:00+00:00")
        self.assertEqual(self.run_lane(board()), 0)
        self.assertEqual(self.urls, [])
        self.snapshot(start="2026-11-14T12:30:00+00:00")             # expected end 14:30 + 30 min grace < 15:30
        self.assertEqual(self.run_lane(board()), 0)
        self.assertEqual(self.urls, [])

    def test_live_board_updates_status_within_budget_and_quota(self):
        self.snapshot()
        self.assertEqual(self.run_lane(board((1, "2H"))), 1)
        self.assertEqual(self.urls, ["https://v3.football.api-sports.io/fixtures?live=all"])
        observation = self.store._get("live_observations")["events"]["api-sports:1"]
        self.assertEqual((observation["status_normalized"], observation["status_observed_at"]), ("live", iso(NOW)))
        usage = self.store.usage()
        self.assertEqual((usage["live:api_sports"], usage["api_sports"]), (1, 1))   # shares the product's quota
        # Unchanged and confirmed 14 minutes ago: no new observation, so no new asset or commit.
        self.assertEqual(self.run_lane(board((1, "2H")), now=NOW + timedelta(minutes=14)), 0)
        # CA-18 (owner, 20 Nov 2026): an unchanged live status is re-stamped every 15 minutes (LIVE_REFRESH), so a
        # reader polling every 15 minutes through a 5 minute CDN cache never sees it older than 45 minutes.
        self.assertEqual(engine_module.LIVE_REFRESH, timedelta(minutes=15))
        self.assertLess(engine_module.LIVE_REFRESH + timedelta(minutes=5) + timedelta(minutes=15), feed.LIVE_MAX_AGE)
        self.assertEqual(self.run_lane(board((1, "2H")), now=NOW + timedelta(minutes=15)), 1)
        self.assertEqual(self.store._get("live_observations")["events"]["api-sports:1"]["status_observed_at"],
                         iso(NOW + timedelta(minutes=15)))
        self.assertEqual(self.run_lane(board((1, "2H")), now=NOW + timedelta(minutes=29)), 0)
        # Left the live board: not claimed finished, only "unknown".
        self.assertEqual(self.run_lane(board(), now=NOW + timedelta(minutes=30)), 1)
        self.assertEqual(self.store._get("live_observations")["events"]["api-sports:1"]["status_normalized"], "unknown")
        self.assertEqual(self.store.usage()["live:api_sports"], 5)

    def test_games_products_use_the_games_live_board(self):
        self.snapshot(hockey=True)

        def payload(url):
            if "hockey" in url:
                return json.dumps({"errors": [], "response": [{"id": 5, "timestamp": int(NOW.timestamp()),
                                                               "status": {"short": "P2"}, "teams": {}}]}).encode()
            return board()
        self.assertEqual(self.run_lane(payload), 1)
        self.assertIn("https://v1.hockey.api-sports.io/games?live=all", self.urls)
        self.assertEqual(self.store._get("live_observations")["events"]["api-sports-hockey:5"]["status_normalized"], "live")

    def test_budget_reserve_backoff_plan_window_and_switch(self):
        self.snapshot()
        for _ in range(engine_module.LIVE_DAILY_BUDGET):
            self.store.increment("live:api_sports", engine_module.LIVE_DAILY_BUDGET)
        self.assertEqual(self.run_lane(board((1, "2H"))), 0)
        self.assertEqual(self.urls, [])
        self.assertIn("daily live budget", self.store._get("live_lane")["summary"])
        with self.store._db() as db:
            db.execute("DELETE FROM requests WHERE provider='live:api_sports'")
        for _ in range(providers.SPORTS["api_sports"][3]):
            self.store.increment("api_sports", 1000)
        self.assertEqual(self.run_lane(board((1, "2H"))), 0)       # calls kept for the scheduled refreshes
        with self.store._db() as db:
            db.execute("DELETE FROM requests")
        self.store._put("sports_backoff:api_sports", iso(NOW + timedelta(hours=1)))
        with patch.object(engine_module, "datetime", FixedClock):
            self.assertEqual(self.run_lane(board((1, "2H"))), 0)
        self.store._put("sports_backoff:api_sports", "")
        self.store._put("plan_window:api_sports", {"first": 1, "last": 3, "learned_at": datetime.now(timezone.utc).isoformat()})
        self.assertEqual(self.run_lane(board((1, "2H"))), 0)
        self.store._put("plan_window:api_sports", None)
        self.assertEqual(self.urls, [])
        self.store.configure({"live_status": False})
        self.assertFalse(Engine.live_lane_enabled(self.store.config()))
        self.assertEqual(self.run_lane(board((1, "2H"))), 0)
        self.assertEqual(self.urls, [])
        self.store.configure({"live_status": True, "keys": {"api_sports": ""}})
        self.assertFalse(Engine.live_lane_enabled(self.store.config()))

    def test_rate_limit_defers_and_a_refused_board_is_not_asked_again(self):
        self.snapshot()
        refused = json.dumps({"errors": {"live": "The Live field is not supported"}, "response": []}).encode()
        self.assertEqual(self.run_lane(refused), 0)
        self.assertEqual(self.run_lane(refused, now=NOW + timedelta(minutes=15)), 0)
        self.assertEqual(len(self.urls), 1)
        self.store._put("live_unsupported:api_sports", "")
        limited = json.dumps({"errors": {"requests": "You have reached the request limit"}, "response": []}).encode()
        self.assertEqual(self.run_lane(limited), 0)
        self.assertGreater(self.store._get("sports_backoff:api_sports"), datetime.now(timezone.utc).isoformat())

    def test_live_publish_uploads_only_the_live_asset_and_manifests(self):
        self.snapshot()
        commits = []
        with patch.object(Engine, "_github_commit", side_effect=lambda *a, **k: commits.append(a)), \
                patch("sportsliveinfo.feed.datetime", FixedClock):
            first = self.engine.publish()
            self.assertEqual(self.run_lane(board((1, "1H"))), 1)
            self.engine._publish_live()
            second = self.store._get("feed_state")["last_revision"]
            self.engine._publish_live()                               # nothing changed: nothing committed
        self.assertNotEqual(first, second)
        self.assertEqual(len(commits), 2)
        uploads = commits[1][4]
        live_paths = [p for p in uploads if p.startswith("v1/assets/")]
        self.assertEqual(len(live_paths), 1)
        self.assertTrue(live_paths[0].startswith("v1/assets/live/"))
        self.assertEqual(set(uploads) - set(live_paths), {"v1/manifest.json", "v1/manifests/%s.json" % second})
        live = json.loads(uploads[live_paths[0]])
        self.assertEqual(live["events"], [{"id": "api-sports:1", "status_normalized": "live",
                                           "status_observed_at": "2026-11-14T15:30:00Z",
                                           "live_until_utc": "2026-11-14T16:15:00Z",
                                           "display_state": "live", "state_until_utc": "2026-11-14T16:15:00Z"}])
        manifest = json.loads(uploads["v1/manifest.json"])
        self.assertIn("live_status", manifest["capabilities"])
        self.assertNotIn("score", uploads[live_paths[0]].decode())

    def test_next_collection_folds_observations_and_drops_the_live_asset(self):
        self.snapshot()
        self.run_lane(board((1, "2H")))
        manifest, _ = feed.build_feed(self.store, now=NOW)
        self.assertIn("live", {a["kind"] for a in manifest["assets"]})
        self.engine._materialize(now=NOW + timedelta(minutes=5))
        event = next(e for e in self.store.snapshot("sports")["data"]["events"] if e["id"] == "api-sports:1")
        self.assertEqual((event["status_normalized"], event["status_observed_at"]), ("live", iso(NOW)))
        manifest, files = feed.build_feed(self.store, now=NOW + timedelta(minutes=5))
        self.assertNotIn("live", {a["kind"] for a in manifest["assets"]})
        day = next(a for a in manifest["assets"] if a["kind"] == "events:2026-11-14")
        published, = json.loads(files[day["path"]])["events"]
        self.assertEqual((published["status_normalized"], published["status_observed_at"]), ("live", "2026-11-14T15:30:00Z"))

    def test_scheduler_runs_the_lane_at_most_every_15_minutes_and_not_beside_a_refresh(self):
        self.snapshot()
        calls = []
        local = NOW.astimezone(engine_module.LONDON)
        with patch.object(Engine, "live_lane", side_effect=lambda: calls.append(1) or 0):
            self.engine._live_tick(self.store.config(), local)
            for thread in threading.enumerate():
                if thread.name == "sportsliveinfo-live":
                    thread.join(timeout=3)
            self.assertEqual(calls, [1])
            self.store._put("live_lane", {"last_run": datetime.now(timezone.utc).isoformat()})
            self.engine._live_tick(self.store.config(), local)
            self.assertEqual(calls, [1])
            self.store._put("live_lane", {})
            self.store.configure({"schedule": ["15:32"]})
            self.engine._live_tick(self.store.config(), local)
            self.assertEqual(calls, [1])
        self.assertTrue(self.engine._busy.acquire(blocking=False))     # the lane released the collector lock
        self.engine._busy.release()


class LiveExpiryAndPublishGateTests(LiveLaneBase):
    """Live-lane expiry (stale "live" must not outlive its evidence) and the pre-publish regression gate."""

    def test_live_asset_drops_rows_past_live_until(self):
        self.snapshot()
        self.run_lane(board((1, "2H")))                                   # live, observed 15:30, until 16:15
        fresh, _ = feed.build_feed(self.store, now=NOW + timedelta(minutes=30))
        self.assertIn("live", {a["kind"] for a in fresh["assets"]})
        expired, _ = feed.build_feed(self.store, now=NOW + timedelta(minutes=50))
        self.assertNotIn("live", {a["kind"] for a in expired["assets"]})
        self.assertNotIn("live_status", expired["capabilities"])

    def test_stale_live_is_downgraded_without_an_api_call_and_counts_as_a_change(self):
        self.snapshot()
        self.run_lane(board((1, "2H")))
        calls = len(self.urls)
        later = NOW + timedelta(hours=3)                                   # nothing in play any more
        self.assertEqual(self.run_lane(board(), now=later), 1)
        self.assertEqual(len(self.urls), calls)                            # no provider call
        observation = self.store._get("live_observations")["events"]["api-sports:1"]
        self.assertEqual((observation["status_normalized"], observation["status_observed_at"]),
                         ("unknown", iso(later)))
        self.assertEqual(self.run_lane(board(), now=later + timedelta(minutes=15)), 0)   # settled, no republish

    def test_fresh_live_is_not_downgraded(self):
        self.snapshot()
        self.run_lane(board((1, "2H")))
        self.assertEqual(self.run_lane(board((1, "2H")), now=NOW + timedelta(minutes=44)), 1)   # re-confirmed
        self.assertEqual(self.store._get("live_observations")["events"]["api-sports:1"]["status_normalized"], "live")

    def test_manifest_declares_the_lane_and_stays_backward_compatible(self):
        self.snapshot()
        self.run_lane(board((1, "2H")))
        manifest, _ = feed.build_feed(self.store, now=NOW)
        refresh = manifest["refresh"]
        self.assertEqual(refresh["live_stale_after_minutes"], 45)
        self.assertEqual(refresh["live_lane"], {"enabled": True, "interval_minutes": 15,
                                                "active_only_while_events_in_play": True,
                                                "quiet_slots_guard_minutes": 3, "last_run_utc": "2026-11-14T15:30:00Z"})
        self.assertLessEqual(manifest["compatibility"]["min_reader_minor"], 6)
        self.assertEqual(manifest["compatibility"]["min_reader_minor"], 0)
        self.assertIn("live_stale_after_minutes", json.loads(
            (Path(__file__).resolve().parents[1] / "schemas" / "sli-manifest.schema.json").read_text())
            ["properties"]["refresh"]["properties"])

    def test_regression_rule(self):
        manifest = {"coverage": {"events": 79, "guide_corroborated_broadcasts": 10}}
        rule = engine_module.publish_regression
        self.assertIsNone(rule(None, manifest))
        self.assertIsNone(rule({"events": 100, "corroborated_bindings": 12}, {"coverage": {
            "events": 80, "guide_corroborated_broadcasts": 10}}))              # exactly 20% down: allowed
        self.assertIn("events fell from 100 to 79", rule({"events": 100, "corroborated_bindings": 10}, manifest))
        self.assertIn("corroborated bindings fell from 20 to 10",
                      rule({"events": 79, "corroborated_bindings": 20}, manifest))
        self.assertIsNone(rule({"events": 3, "corroborated_bindings": 3}, {"coverage": {
            "events": 0, "guide_corroborated_broadcasts": 0}}))                 # tiny baseline ignored

    def test_automatic_publish_is_refused_on_regression_and_manual_overrides(self):
        self.snapshot()
        commits = []
        with patch.object(Engine, "_github_commit", side_effect=lambda *a, **k: commits.append(a)), \
                patch("sportsliveinfo.feed.datetime", FixedClock):
            self.engine.publish()
            self.assertEqual(len(commits), 1)
            state = self.store._get("feed_state")
            self.assertEqual(state["stats"]["events"], 1)
            self.store._put("feed_state", dict(state, stats={"events": 50, "corroborated_bindings": 0},
                                               last_revision="0" * 20))
            self.assertIsNone(self.engine._publish_job("automatic"))
            self.assertEqual(len(commits), 1)                              # nothing committed
            status = self.store._get("publish_status")
            self.assertEqual(status["state"], "failed")
            self.assertIn("events fell from 50 to 1", status["message"])
            self.assertEqual(self.store.recent_jobs(1, provider="publisher")[0]["state"], "blocked")
            self.assertIn("events fell", self.store._get("publish_gate")["reason"])
            self.assertIsNotNone(self.engine._publish_job("manual"))      # manual publish overrides
            self.assertEqual(len(commits), 2)


class LiveLaneIngressTests(StoreCase):
    def test_scheduler_and_diagnostics_show_and_switch_the_lane(self):
        self.store.configure({"setup_complete": True})
        with closing(IngressTestClient(self.store, "csrf-test")) as client:
            with client.open(client.base + "?page=scheduler") as response:
                page = response.read().decode()
            self.assertIn("Live status lane", page)
            self.assertIn("needs a saved API-Sports key", page)
            body = urllib.parse.urlencode({"csrf": "csrf-test", "action": "live_status"}).encode()
            with client.open(urllib.request.Request(client.base, body, method="POST")) as response:
                response.read()
            self.assertFalse(self.store.config()["live_status"])
            with client.open(client.base + "?page=health") as response:
                self.assertIn("Switched off", response.read().decode())


if __name__ == "__main__":
    unittest.main()
