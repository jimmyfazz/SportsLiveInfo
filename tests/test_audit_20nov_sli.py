"""SLI-side findings of the 20 Nov 2026 combined audit: CA-06 collected_at, CA-03 dictionary size budget, CA-12
crest preview. (CA-08 is in test_f1_practice_dedupe.py, CA-07 in test_republish_revision.py.)"""
import json
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingress_test_support import IngressTestClient  # noqa: E402
from sportsliveinfo import feed  # noqa: E402
from sportsliveinfo.storage import Store  # noqa: E402

UTC = timezone.utc
COLLECTED = datetime(2026, 11, 20, 12, 0, 5, tzinfo=UTC)


def api_sports_event(i, crests=True):
    row = {"id": "api-sports:%d" % i, "source_id": "api_sports", "sport": "football", "competition": "Premier League",
           "competition_id": "football.premier_league", "title": "A%d v B%d" % (i, i), "participants": ["A%d" % i, "B%d" % i],
           "start_utc": "2026-11-21T15:00:00+00:00", "start_precision": "scheduled", "status_normalized": "scheduled",
           "broadcasts": [], "broadcast_verified": False}
    if crests:
        row["participant_crests"] = [{"src": "apisports", "ref": "football/teams/%d" % (40 + i)},
                                     {"src": "apisports", "ref": "football/teams/%d" % (50 + i)}]
    return row


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "s.sqlite3")
        self.store.configure({"setup_complete": True, "publication_approvals": ["api_sports"]})


class CollectedAtTests(StoreCase):
    def test_collected_at_is_the_collection_time_and_survives_a_later_publish(self):
        self.store.save_snapshot("sports", {"events": [api_sports_event(1)], "generated_at": COLLECTED.isoformat()})
        first, _ = feed.build_feed(self.store, now=COLLECTED + timedelta(minutes=2))
        later, files = feed.build_feed(self.store, now=COLLECTED + timedelta(hours=20))      # e.g. a live-lane publish
        for manifest in (first, later):
            self.assertEqual(manifest["refresh"]["collected_at"], "2026-11-20T12:00:05Z")
            self.assertIn("collection stale", manifest["refresh"]["collected_at_expected"])
        self.assertNotEqual(first["generated_at"], later["generated_at"])        # generated_at moves, collected_at does not
        health = json.loads(files[next(a["path"] for a in later["assets"] if a["kind"] == "health")])
        self.assertEqual(health["collected_at"], "2026-11-20T12:00:05Z")

    def test_absent_without_a_collection(self):
        manifest, _ = feed.build_feed(self.store, now=COLLECTED)
        self.assertNotIn("collected_at", manifest["refresh"])


class DictionaryBudgetTests(unittest.TestCase):
    # Live feed 20 Nov 2026 (manifest sli/1.7, publisher 0.3.25): the dictionary asset was 6,969,653 bytes.
    RECORDED_DICTIONARY_BYTES = 6_969_653
    RECORDED_ON = "2026-11-20"

    def test_recorded_dictionary_is_inside_the_cap_but_already_alerting(self):
        cap = feed.MAX_READER_ASSET_BYTES
        self.assertLess(self.RECORDED_DICTIONARY_BYTES, cap)
        percent = 100.0 * self.RECORDED_DICTIONARY_BYTES / cap
        self.assertAlmostEqual(percent, 83.1, delta=0.1)
        budget = feed.asset_budget([{"kind": "dictionary", "bytes": self.RECORDED_DICTIONARY_BYTES}])
        self.assertEqual([r["kind"] for r in budget["near_limit"]], ["dictionary"])     # the 80% alert fires today
        self.assertEqual(budget["alert_percent"], 80)

    def test_part_target_is_below_the_alert_so_a_part_never_alerts(self):
        self.assertLess(feed.PART_TARGET_FRACTION, feed.ASSET_ALERT_FRACTION)

    def test_headroom_budget_fails_loudly_when_growth_is_nearly_used_up(self):
        # CI-visible: recorded size plus 15% growth must still fit. When a real dictionary needs more than that,
        # update RECORDED_DICTIONARY_BYTES from the live manifest and check readers can take parts (contract §2.3).
        self.assertLess(self.RECORDED_DICTIONARY_BYTES * 1.15, feed.MAX_READER_ASSET_BYTES)

    def test_a_dictionary_of_recorded_size_plus_a_quarter_splits_into_parts_and_keeps_the_alias(self):
        rows = [{"id": "C%06d.%s" % (i, c.lower()), "name": "n" * 120, "country": c}
                for c in ("GB", "FR", "DE") for i in range(9000)]
        rows += [{"id": "W%06d.us" % i, "name": "w" * 120, "country": "US"} for i in range(30000)]
        document = {"schema": "sli.dictionary/1", "source": {}, "scope": "t", "regions": ["north_america"],
                    "market_countries": {}, "bare_market_codes": {}, "rules": {}, "channels": rows}
        self.assertGreater(len(feed._json(document)), self.RECORDED_DICTIONARY_BYTES)
        parts = feed.dictionary_parts(document)
        self.assertEqual(parts[0][0], "dictionary:uk-eu")
        self.assertTrue(all(len(feed._json(doc)) <= feed.MAX_READER_ASSET_BYTES for _, doc, _ in parts))
        self.assertEqual(sum(len(doc["channels"]) for _, doc, _ in parts), len(rows))
        # uk-eu fits in one part, so build_feed gives deployed readers a plain "dictionary" alias of it.
        self.assertFalse(any(kind.startswith("dictionary:uk-eu-") for kind, _, _ in parts))


class CrestPreviewTests(StoreCase):
    def test_counts_only_valid_api_sports_references(self):
        bad = dict(api_sports_event(3), participant_crests=[{"src": "apisports", "ref": "../x"}, None])
        events = [api_sports_event(1), api_sports_event(2, crests=False), bad]
        self.assertEqual(feed.crest_preview(events), 1)
        self.assertEqual(feed.crest_preview(None), 0)

    def page(self):
        with closing(IngressTestClient(self.store, "c")) as client:
            with client.open(client.base + "?page=publishing") as response:
                return response.read().decode()

    def test_publishing_page_shows_off_with_the_would_carry_count(self):
        self.store.configure({"publish_crest_refs": False})
        self.store.save_snapshot("sports", {"events": [api_sports_event(1), api_sports_event(2), api_sports_event(3, crests=False)]})
        self.assertIn("Crest references: OFF — 2 of 3 collected events would carry crests.", self.page())

    def test_publishing_page_shows_on_once_enabled_and_approved(self):
        self.store.configure({"publish_crest_refs": True})
        self.store.save_snapshot("sports", {"events": [api_sports_event(1)]})
        self.assertIn("Crest references: ON — 1 of 1 collected events carry crests.", self.page())

    def test_enabled_without_an_approved_source_still_says_off(self):
        self.store.configure({"publish_crest_refs": True, "publication_approvals": []})
        self.store.save_snapshot("sports", {"events": [api_sports_event(1)]})
        page = self.page()
        self.assertIn("Crest references: OFF — 1 of 1 collected events would carry crests.", page)
        self.assertIn("approve an API-Sports source", page)


if __name__ == "__main__":
    unittest.main()
