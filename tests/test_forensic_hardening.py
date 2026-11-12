"""Independent regression suite for Claude branch integration and security hardening."""
import gzip
import json
import tempfile
import unittest
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from sportsliveinfo import feed, providers, taxonomy
from sportsliveinfo.engine import Engine
from sportsliveinfo.storage import Store


def item(event_id, origin, sources=None, **extra):
    obj = {
        "id": event_id, "source_id": origin, "sport": "football",
        "competition": "Test Competition", "participants": ["Alpha", "Beta"],
        "start_utc": (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat(),
        "start_precision": "scheduled", "status_normalized": "scheduled",
        "broadcasts": [], "broadcast_verified": False,
    }
    if sources is not None:
        obj["sources"] = sources
    obj.update(extra)
    return obj


class DurableStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "state.sqlite3"
        self.store = Store(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_quota_is_atomic_across_independent_store_instances(self):
        stores = [Store(self.path) for _ in range(8)]
        def try_call(i):
            try:
                return stores[i % len(stores)].increment("example", 5)
            except RuntimeError:
                return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            counts = list(pool.map(try_call, range(32)))
        self.assertEqual(sorted(x for x in counts if x is not None), [1, 2, 3, 4, 5])
        self.assertEqual(Store(self.path).usage()["example"], 5)

    def test_scheduler_slot_claim_persists_and_is_releasable(self):
        slot = "2026-11-12 17:00"
        self.assertTrue(self.store.claim_scheduler_slot(slot))
        self.assertFalse(Store(self.path).claim_scheduler_slot(slot))
        self.store.release_scheduler_slot(slot)
        self.assertTrue(Store(self.path).claim_scheduler_slot(slot))
        with self.assertRaises(ValueError):
            self.store.claim_scheduler_slot("unsafe")

    def test_invalid_configuration_cannot_break_provider_maps(self):
        for update in ({"sports": "broken"}, {"epg": {"fake": True}},
                       {"sports": {"jolpica": "yes"}}, {"schedule": ["28:00"]},
                       {"publication_approvals": ["fake-provider"]}):
            with self.assertRaises(ValueError):
                self.store.configure(update)
        self.assertIsInstance(self.store.config()["sports"], dict)

    def test_failing_every_source_does_not_mark_fresh_or_publish(self):
        self.store.configure({
            "setup_complete": True, "sports": {"jolpica": False},
            "epg": {"farleyflex": True},
            "github": {"enabled": True, "auto_publish": True},
            "publication_approvals": ["jolpica"],
        })
        self.store.save_snapshot("epg:farleyflex", {
            "source_id": "farleyflex", "channels": {}, "programmes": []
        })
        old = self.store.snapshot("epg:farleyflex")
        with patch.object(Engine, "publish") as publish, patch(
                "sportsliveinfo.providers.fetch", side_effect=RuntimeError("offline")):
            result = Engine(self.store).collect()
        self.assertFalse(result)
        publish.assert_not_called()
        self.assertEqual(self.store.snapshot("epg:farleyflex"), old)
        self.assertEqual(self.store.recent_jobs()[0]["state"], "failed")

    def test_api_sports_multiple_pages_use_quota_and_keep_all_rows(self):
        engine = Engine(self.store)
        engine._pace = lambda name: None
        pages = [
            json.dumps({"response": [{"id": 1}], "paging": {"current": 1, "total": 2}}).encode(),
            json.dumps({"response": [{"id": 2}], "paging": {"current": 2, "total": 2}}).encode(),
        ]
        item = {"url": "https://v3.football.api-sports.io/fixtures?date=2026-11-12",
                "headers": {"x-apisports-key": "redacted-test-key"},
                "max_bytes": 1000,
                "decode": lambda b: json.loads(b)["response"]}
        with patch("sportsliveinfo.providers.fetch", side_effect=pages) as fetch:
            rows = engine._request("api_sports", item, 4)
        self.assertEqual([r["id"] for r in rows], [1, 2])
        self.assertEqual(self.store.usage()["api_sports"], 2)
        self.assertIn("page=2", fetch.call_args_list[1].args[0])

    def test_api_sports_missing_later_page_never_claims_a_complete_day(self):
        engine = Engine(self.store)
        engine._pace = lambda name: None
        one = json.dumps({"response": [{"id": 1}], "paging": {"current": 1, "total": 2}}).encode()
        bad = json.dumps({"response": [], "paging": {"current": 2, "total": 3}}).encode()
        item = {"url": "https://v3.football.api-sports.io/fixtures?date=2026-11-12",
                "headers": {}, "max_bytes": 1000, "decode": lambda b: json.loads(b)["response"]}
        with patch("sportsliveinfo.providers.fetch", side_effect=[one, bad]):
            with self.assertRaises(ValueError):
                engine._request("api_sports", item, 4)
        self.assertEqual(self.store.usage()["api_sports"], 2)

    def test_successful_empty_provider_does_not_delete_known_fixture(self):
        self.store.configure({"setup_complete": True, "sports": {
            "jolpica": False, "openligadb": True}})
        event = item("openligadb:1", "openligadb", ["openligadb"])
        event["fetch_scope"] = "league:bl1"
        self.store.save_snapshot("sports:openligadb", {"events": [event]})
        with patch("sportsliveinfo.providers.fetch", return_value=b"[]"):
            self.assertTrue(Engine(self.store)._collect_sport("openligadb", self.store.config()))
        ids = {e["id"] for e in self.store.snapshot("sports:openligadb")["data"]["events"]}
        self.assertIn(event["id"], ids)

    def test_guide_coverage_collapse_keeps_previous_schedule(self):
        now = datetime.now(timezone.utc)
        start = now + timedelta(minutes=5)
        def row(i):
            return {
                "channel_id": "sky", "title": "Programme %d" % i,
                "start_utc": (start + timedelta(minutes=20*i)).isoformat(),
                "end_utc": (start + timedelta(minutes=20*(i+1))).isoformat(),
            }
        old = {"source_id": "farleyflex", "channels": {"sky": "Sky Sports Main Event"},
               "programmes": [row(i) for i in range(40)]}
        fresh = {"source_id": "farleyflex", "channels": {"sky": "Sky Sports Main Event"},
                 "programmes": [row(i) for i in range(2)],
                 "invalid_programmes": 0}
        self.store.save_snapshot("epg:farleyflex", old)
        with patch("sportsliveinfo.providers.fetch", return_value=b"<tv/>"), patch(
                "sportsliveinfo.providers.decode_xmltv", return_value=fresh):
            self.assertFalse(Engine(self.store)._collect_epg("farleyflex"))
        self.assertEqual(self.store.snapshot("epg:farleyflex")["data"], old)
        self.assertTrue(any(j["state"] == "coverage_collapse" for j in self.store.recent_jobs()))


class XmltvAndNetworkTests(unittest.TestCase):
    def test_gzip_stream_preserves_epg_fields_and_limits_expansion(self):
        raw = (b'<tv><channel id="BBCOne.uk"><display-name lang="en">BBC One</display-name></channel>'
               b'<programme channel="BBCOne.uk" start="20261112170000 +0000" '
               b'stop="20261112180000 +0000"><title lang="en">Fixture</title>'
               b'<sub-title>Alpha v Beta</sub-title><category>Sports</category>'
               b'<live/><previously-shown/><episode-num system="xmltv_ns">1.2.</episode-num>'
               b'</programme></tv>')
        guide = providers.decode_xmltv(gzip.compress(raw), "farleyflex")
        self.assertEqual(guide["programmes"][0]["subtitle"], "Alpha v Beta")
        self.assertTrue(guide["programmes"][0]["is_repeat"])
        self.assertEqual(guide["programmes"][0]["categories"], ["Sports"])
        with self.assertRaises(ValueError):
            providers.decode_xmltv(gzip.compress(raw), "farleyflex", max_expanded=40)

    def test_dtd_split_across_boundaries_is_rejected(self):
        payload = b"<tv>" + b" " * 65520 + b"<!DOC" + b"TYPE tv><channel id='a'/></tv>"
        with self.assertRaises(ValueError):
            providers.decode_xmltv(payload, "fr_xmltv")

    def test_credentials_not_sent_across_allowed_provider_hosts(self):
        req = urllib.request.Request(
            "https://api.jolpi.ca/ergast/f1/current.json",
            headers={"X-Auth-Token": "never-forward"},
        )
        with self.assertRaisesRegex(ValueError, "Cross-origin"):
            providers.RedirectGuard().redirect_request(
                req, None, 302, "redirect", {},
                "https://api.openligadb.de/getmatchdata/bl1",
            )


class PublicFeedRightsTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 14, 14, tzinfo=timezone.utc)
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "feed.sqlite3")
        self.store.configure({"publication_approvals": ["jolpica"]})

    def fixture(self, event_id, sources, **extra):
        # The aggregate cache contains classified records, not raw adapter rows.
        return taxonomy.classify(item(
            event_id, "jolpica", sources, title="Alpha v Beta",
            start_utc=(self.now + timedelta(hours=4)).isoformat(), **extra,
        ))

    def tearDown(self):
        self.temp.cleanup()

    def test_fused_event_mixed_with_unapproved_provider_is_not_public(self):
        mixed = self.fixture("fused:1", ["jolpica", "openf1"])
        clean = self.fixture("clean:1", ["jolpica"])
        self.store.save_snapshot("sports", {"events": [mixed, clean]})
        manifest, files = feed.build_feed(self.store, now=self.now)
        rows = []
        for asset in manifest["assets"]:
            if asset["kind"].startswith("events:"):
                rows.extend(json.loads(files[asset["path"]])["events"])
        self.assertEqual({e["id"] for e in rows}, {"clean:1"})
        self.assertIn("openf1", manifest["rights"]["events"]["omitted_unapproved_sources"])

    def test_boolean_only_does_not_authorise_a_broadcast_claim(self):
        event = self.fixture("clean:2", ["jolpica"], broadcast_verified=True,
                     broadcasts=[{"canonical_channel_id": "gb.sky.sports.main_event"}])
        self.store.save_snapshot("sports", {"events": [event]})
        manifest, files = feed.build_feed(self.store, now=self.now)
        rows = [e for a in manifest["assets"] if a["kind"].startswith("events:")
                for e in json.loads(files[a["path"]])["events"]]
        self.assertFalse(rows[0]["broadcast_verified"])
        self.assertNotIn("broadcasts", rows[0])


if __name__ == "__main__":
    unittest.main()
