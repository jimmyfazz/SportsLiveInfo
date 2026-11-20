import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from sportsliveinfo import guide, providers
from sportsliveinfo.engine import Engine, LONDON
from sportsliveinfo.storage import Store


class SourceRefreshTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = Store(Path(temp.name) / "sports.sqlite3")
        self.engine = Engine(self.store)

    def test_manual_guide_request_preserves_scheduled_budget(self):
        self.store.configure({"schedule": ["04:00", "12:00", "17:00"]})
        now = datetime(2026, 11, 13, 0, 0, tzinfo=timezone.utc)
        with patch("sportsliveinfo.engine.datetime", wraps=datetime) as clock, patch.object(providers, "fetch") as fetch:
            clock.now.return_value = now
            self.store.increment("epg:farleyflex", 4)
            self.assertFalse(self.engine._collect_epg("farleyflex"))
            fetch.assert_not_called()
            job = self.store.recent_jobs(1)[0]
            self.assertEqual(job["state"], "deferred")
            self.assertIn("reserved for scheduled refreshes", job["details"])
            self.engine._reserve_epg("farleyflex", scheduled=True)
        self.assertEqual(self.store.usage()["epg:farleyflex"], 2)

    def test_collection_reports_deferral_when_every_guide_is_deferred(self):
        self.store.configure({"setup_complete": True, "schedule": [], "epg": {"farleyflex": True}})
        for _ in range(providers.EPG_DAILY_REQUEST_LIMIT):
            self.store.increment("epg:farleyflex", providers.EPG_DAILY_REQUEST_LIMIT)
        with patch.object(providers, "fetch") as fetch:
            self.assertFalse(self.engine._collect_locked("epg"))
        fetch.assert_not_called()
        self.assertEqual(self.store.recent_jobs(1, provider="collector")[0]["state"], "deferred")

    def test_304_retains_the_guide_and_timestamp(self):
        self.store.configure({"schedule": []})
        now = datetime.now(timezone.utc)
        guide_xml = ('<tv><channel id="a"><display-name>BBC One</display-name></channel>'
                     '<programme channel="a" start="%s" stop="%s"><title>News</title></programme></tv>'
                     % (now.strftime("%Y%m%d%H%M%S +0000"),
                        (now + timedelta(hours=2)).strftime("%Y%m%d%H%M%S +0000"))).encode()
        def download(url, headers, *, max_bytes, response_headers):
            if headers:
                self.assertEqual(headers, {"If-None-Match": '"guide-1"'})
                return None
            response_headers["ETag"] = '"guide-1"'
            return guide_xml

        with patch.object(providers, "fetch", side_effect=download):
            self.assertTrue(self.engine._collect_epg("farleyflex"))
            previous = self.store.snapshot("epg:farleyflex")
            self.assertTrue(self.engine._collect_epg("farleyflex"))
        self.assertEqual(self.store.snapshot("epg:farleyflex"), previous)
        self.assertEqual(self.store.recent_jobs(1)[0]["state"], "unchanged")

    def test_throttle_defers_following_scopes_and_survives_engine_restart(self):
        self.store.configure({"keys": {"api_sports": "synthetic"}})
        with patch.object(providers, "fetch", side_effect=providers.UpstreamHTTPError(429, "120")) as fetch, patch.object(Engine, "_pace"):
            self.assertFalse(self.engine._collect_sport("api_sports", self.store.config()))
            self.assertFalse(Engine(self.store)._collect_sport("api_sports", self.store.config()))
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(self.store.recent_jobs(1)[0]["state"], "deferred")

    def test_partial_discovery_retries_missing_dates_and_today_only(self):
        self.store.configure({"keys": {"api_sports": "synthetic"}})
        conf = self.store.config()
        planned = self.engine._plan("api_sports", conf, datetime.now(LONDON).date())
        failure = planned[2]["scope"]
        def request(name, item, limit):
            if item["scope"] == failure:
                raise providers.ProviderRejected("Provider plan or season restriction")
            return []

        with patch.object(self.engine, "_plan", return_value=planned), patch.object(self.engine, "_request", side_effect=request) as fetch:
            self.assertTrue(self.engine._collect_sport("api_sports", conf))
            self.assertEqual(fetch.call_count, 8)   # yesterday (history) + 7 days
            fetch.reset_mock()
            self.assertTrue(self.engine._collect_sport("api_sports", conf))
            self.assertEqual([call.args[1]["scope"] for call in fetch.call_args_list], [planned[1]["scope"], failure])   # yesterday is cached
        self.assertIn("Provider plan or season restriction", self.store.recent_jobs(1)[0]["details"])

    def test_free_plan_date_window_is_learned_and_not_requested_again(self):
        """API-Sports free keys read only a few days; dates outside are not failures and are skipped next time."""
        self.store.configure({"keys": {"api_sports": "synthetic"}})
        conf = self.store.config()
        today = datetime.now(LONDON).date()
        refusal = {"errors": {"plan": "Free plans do not have access to this date, try from %s to %s."
                              % ((today - timedelta(days=1)).isoformat(), (today + timedelta(days=1)).isoformat())},
                   "response": []}
        ok = {"errors": [], "paging": {"current": 1, "total": 1}, "response": []}
        def fetch(url, headers=None, max_bytes=None, response_headers=None):
            day = url.split("date=")[1].split("&")[0]
            inside = (datetime.fromisoformat(day).date() - today).days <= 1
            return json.dumps(ok if inside else refusal).encode()

        with patch.object(providers, "fetch", side_effect=fetch) as calls, patch.object(Engine, "_pace"):
            self.assertTrue(self.engine._collect_sport("api_sports_rugby", conf))
            # today and tomorrow succeed; day 3 is refused and teaches the window; days 4-7 are never requested
            self.assertEqual(calls.call_count, 4)   # yesterday, today, tomorrow; day 3 is refused
        job = self.store.recent_jobs(1)[0]
        self.assertEqual(job["state"], "no_events_reported")
        self.assertIn("outside the provider plan", job["details"])
        self.assertEqual(self.engine._plan_window("api_sports_rugby"), (-1, 1))
        # The next full discovery plans only the allowed days.
        days = self.engine._days("api_sports_rugby", None, today)
        self.assertEqual(days, [today - timedelta(days=1), today, today + timedelta(days=1)])
        snapshot = self.store.snapshot("sports:api_sports_rugby")["data"]
        self.assertIsNotNone(snapshot["full_discovery_at"])

    def test_plan_window_parser_reads_only_two_dates(self):
        window = providers.api_sports_plan_window({"errors": {"plan": "Free plans … try from 2026-11-14 to 2026-11-16."}})
        self.assertEqual([d.isoformat() for d in window], ["2026-11-14", "2026-11-16"])
        self.assertIsNone(providers.api_sports_plan_window({"errors": {"plan": "Upgrade your plan"}}))
        self.assertIsNone(providers.api_sports_plan_window({"errors": {"token": "2026-11-14 2026-11-16"}}))
        self.assertIsNone(providers.api_sports_plan_window({"errors": {"plan": "from 2026-11-16 to 2026-11-14"}}))
        self.assertIsNone(providers.api_sports_plan_window({"errors": []}))

    def test_a_learned_window_is_forgotten_so_an_upgraded_plan_is_noticed(self):
        self.store._put("plan_window:api_sports", {"first": -1, "last": 1,
                                                  "learned_at": (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()})
        self.assertIsNone(self.engine._plan_window("api_sports"))
        today = datetime.now(LONDON).date()
        self.assertEqual(len(self.engine._days("api_sports", None, today)), 8)

    def test_thesportsdb_competitions_cover_the_week_once_a_day(self):
        """Per-competition day requests fill the week ahead; later runs the same day ask for today only."""
        self.store.configure({"options": {"thesportsdb_sports": ["Rugby"], "thesportsdb_leagues": ["5852"]}})
        conf = self.store.config()
        today = datetime.now(LONDON).date()
        saturday = today + timedelta(days=6)
        def fetch(url, headers=None, max_bytes=None, response_headers=None):
            query = dict(p.split("=", 1) for p in url.split("?", 1)[1].split("&"))
            if query.get("l") == "5852" and query["d"] == saturday.isoformat():
                return json.dumps({"events": [{"idEvent": "9001", "strSport": "Rugby", "strLeague": "Nations Championship",
                                               "strHomeTeam": "Ireland Rugby", "strAwayTeam": "South Africa Rugby",
                                               "strEvent": "Ireland Rugby vs South Africa Rugby",
                                               "strTimestamp": saturday.isoformat() + "T16:40:00", "dateEvent": saturday.isoformat(),
                                               "strTime": "16:40:00", "strStatus": "Not Started"}]}).encode()
            return b'{"events": null}'

        with patch.object(providers, "fetch", side_effect=fetch) as calls, patch.object(Engine, "_pace"):
            self.assertTrue(self.engine._collect_sport("thesportsdb", conf))
            self.assertEqual(calls.call_count, 1 + 7)          # Rugby today + the competition on each of 7 days
            urls = [c.args[0] for c in calls.call_args_list]
            self.assertTrue(all("123/eventsday.php" in u for u in urls))
            calls.reset_mock()
            self.assertTrue(self.engine._collect_sport("thesportsdb", conf))
            self.assertEqual(calls.call_count, 2)               # later run: today only (sport + competition)
        events = self.store.snapshot("sports:thesportsdb")["data"]["events"]
        self.assertEqual([e["id"] for e in events], ["thesportsdb:9001"])
        self.assertEqual(events[0]["start_utc"][:10], saturday.isoformat())

    def test_tennis_connection_checks_upcoming_tours_as_well_as_live(self):
        self.store.configure({"keys": {"tennis_api": "synthetic"}})
        with patch.object(providers, "tennis_api_events", return_value=[]), patch.object(
            providers, "fetch", side_effect=[b"[]", providers.UpstreamHTTPError(403), b"[]"]
        ) as fetch:
            result = self.engine.test_source("sports", "tennis_api")
        self.assertEqual(fetch.call_count, 3)
        self.assertIn("upcoming/atp: successful", result)
        self.assertIn("upcoming/wta: HTTP 403", result)
        self.assertIn("live: successful", result)
        self.assertEqual(self.store.recent_jobs(1)[0]["state"], "test_partial")
        self.assertIsNone(self.store.snapshot("sports:tennis_api"))

    def test_bha_calendar_meetings_and_year_boundary(self):
        day = datetime(2026, 1, 1)
        entries = []
        for offset in range(300):
            stamp = (day + timedelta(days=offset)).strftime("%Y%m%d")
            entries.append(f"BEGIN:VEVENT\r\nUID:{offset}\r\nDTSTART;VALUE=DATE:{stamp}\r\n"
                           "SUMMARY:Ascot (Afternoon Jump) / Lingfield (Eveni\r\n ng Flat)\r\nEND:VEVENT\r\n")
        calendar = ("BEGIN:VCALENDAR\r\nX-WR-CALNAME:British Horseracing Authority Fixture List 2026\r\n"
                    + "".join(entries) + "END:VCALENDAR\r\n")
        events = providers.bha_racing_events(calendar.encode(), year=2026)
        self.assertEqual(len(events), 600)
        self.assertEqual(events[1]["title"], "Lingfield (Evening Flat)")
        self.assertEqual(events[1]["start_precision"], "date_only")
        self.assertFalse(events[1]["broadcast_verified"])
        with self.assertRaisesRegex(ValueError, "incomplete"):
            providers.bha_racing_events(calendar.replace("".join(entries[1:]), "").encode(), year=2026)
        plan = self.engine._plan("bha_racing", self.store.config(), datetime(2026, 12, 30).date())
        self.assertEqual([item["scope"] for item in plan], ["season:2026", "season:2027"])
        self.assertFalse(self.store.config()["sports"]["bha_racing"])

    def test_contribution_counts_a_shared_fixture_and_shared_channel_once_per_source(self):
        sports = [{"id": "p1"}, {"id": "p2"}]
        guides = [{"id": "g1"}, {"id": "g2"}]
        events = [
            {"sources": ["p1", "p2"], "broadcast_candidates": [{"epg_sources": ["g1", "g2"]}]},
            {"sources": ["p1"], "broadcast_candidates": [{"epg_sources": ["g2"]}]},
        ]
        self.engine._measure_source_contribution(events, sports, guides)
        self.assertEqual([(s["window_fixtures"], s["exclusive_fixtures"]) for s in sports], [(2, 1), (1, 0)])
        self.assertEqual([(g["window_matches"], g["exclusive_matches"]) for g in guides], [(1, 0), (2, 1)])

    def test_openboxing_keeps_the_bout_date_without_inventing_time_or_ppv(self):
        rows = [{"boutId": 27, "date": "2026-11-14", "status": "SCHEDULED",
                 "boxers": {"boxerA": {"name": {"first": "A", "last": "B"}}, "boxerB": {"name": "C D"}},
                 "weight": {"class": "Flyweight"}}]
        plan = self.engine._plan("openboxing", self.store.config(), datetime.now(LONDON).date())
        [event] = plan[0]["decode"](json.dumps(rows).encode())
        self.assertEqual(event["id"], "openboxing:27")
        self.assertEqual(event["participants"], ["A B", "C D"])
        self.assertEqual(event["start_precision"], "date_only")
        self.assertEqual(event["weight_class"], "Flyweight")
        self.assertFalse(event["broadcast_verified"])
        self.assertFalse(self.store.config()["sports"]["openboxing"])

    def test_pandascore_preserves_fixture_identity_and_does_not_infer_broadcast(self):
        rows = [{"id": 27, "name": "A vs B", "begin_at": "2026-11-14T19:30:00+01:00",
                 "league": {"name": "BLAST Premier"},
                 "opponents": [{"opponent": {"name": "A"}}, {"opponent": {"name": "B"}}]}]
        [event] = providers.pandascore_events(json.dumps(rows).encode())
        self.assertEqual((event["id"], event["start_utc"]), ("pandascore:27", "2026-11-14T18:30:00+00:00"))
        self.assertEqual(event["participants"], ["A", "B"])
        self.assertFalse(event["broadcast_verified"])
        self.assertFalse(self.store.config()["sports"]["pandascore"])

    def test_source_specific_services_do_not_match_other_feeds_or_alternates(self):
        self.assertEqual(guide.canonical_channel("iptv_epg_gb", "TNTSports8.uk", "UK - TNT Sports 8"), "gb.tnt.sports.8")
        # The UK name resolves in UK guides only (0.3.12 added TNT Sports 5-10 to the UK registry).
        self.assertEqual(guide.canonical_channel("epgtalk_uk", "", "UK - TNT Sports 8"), "gb.tnt.sports.8")
        self.assertIsNone(guide.canonical_channel("epgshare_us", "", "TNT Sports 8"))
        self.assertEqual(guide.canonical_channel("epgshare_ca", "TSN.4.HD.ca2", "TSN 4 HD"), "ca.tsn.4")
        self.assertIsNone(guide.canonical_channel("epgshare_us", "ESPN2.(Alternate).us2", "ESPN2 (Alternate)"))
