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
            self.assertEqual(fetch.call_count, 7)
            fetch.reset_mock()
            self.assertTrue(self.engine._collect_sport("api_sports", conf))
            self.assertEqual([call.args[1]["scope"] for call in fetch.call_args_list], [planned[0]["scope"], failure])
        self.assertIn("Provider plan or season restriction", self.store.recent_jobs(1)[0]["details"])

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
        self.assertIsNone(guide.canonical_channel("mjh_sky_uk", "TNTSports8.uk", "UK - TNT Sports 8"))
        self.assertEqual(guide.canonical_channel("epgshare_ca", "TSN.4.HD.ca2", "TSN 4 HD"), "ca.tsn.4")
        self.assertIsNone(guide.canonical_channel("epgshare_us", "ESPN2.(Alternate).us2", "ESPN2 (Alternate)"))
