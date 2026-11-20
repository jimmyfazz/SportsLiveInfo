"""Settle pass: events that ended are settled only by an explicit provider final status, one date= call per product
per hour, on its own capped counter, never into the product's reserve."""
import json
import unittest
from datetime import timedelta
from unittest.mock import patch

import test_live_tiers_corroboration as live
from test_live_tiers_corroboration import NOW, StoreCase, board, iso
from sportsliveinfo import engine as engine_module, feed, providers
from sportsliveinfo.engine import Engine

LATER = NOW + timedelta(minutes=150)      # 18:00: kick-off 15:00 + 2 h + 30 min grace has passed


class SettlePassTests(StoreCase):
    snapshot = live.LiveLaneTests.snapshot       # same collected feed as the live-lane tests

    def setUp(self):
        super().setUp()
        self.store.configure({"setup_complete": True, "keys": {"api_sports": "k"},
                              "sports": {"jolpica": False, "api_sports": True, "api_sports_hockey": True},
                              "publication_approvals": ["api_sports", "api_sports_hockey"]})
        self.engine = Engine(self.store)
        self.urls = []
        pace = patch.object(Engine, "_pace", lambda self, name: None)
        pace.start()
        self.addCleanup(pace.stop)

    def settle(self, payload, now=LATER):
        def fetch(url, headers=None, max_bytes=0, response_headers=None):
            self.urls.append(url)
            return payload(url) if callable(payload) else payload
        with patch("sportsliveinfo.providers.fetch", side_effect=fetch):
            return self.engine.settle_pass(now=now)

    def observation(self, sid="api-sports:1"):
        return (self.store._get("live_observations") or {}).get("events", {}).get(sid)

    def test_final_status_produces_a_finished_row(self):
        self.snapshot()
        self.assertEqual(self.settle(board((1, "FT"))), 1)
        self.assertEqual(self.urls, ["https://v3.football.api-sports.io/fixtures?date=2026-11-14&timezone=Europe%2FLondon"])
        self.assertEqual(self.observation()["status_normalized"], "finished")
        events = self.store.snapshot("sports")["data"]["events"]
        with patch("sportsliveinfo.feed.datetime", engine_module.datetime):
            doc = feed.live_document(self.store, events)
        self.assertEqual(doc["events"], [{"id": "api-sports:1", "status_normalized": "finished",
                                          "status_observed_at": iso(LATER).replace("+00:00", "Z"),
                                          "display_state": "finished",
                                          "finished_at_utc": iso(LATER).replace("+00:00", "Z")}])
        usage = self.store.usage()
        self.assertEqual((usage["settle:api_sports"], usage["api_sports"]), (1, 1))
        self.assertNotIn("live:api_sports", usage)
        self.assertIn("1 settled", self.store._get("settle_lane")["summary"])

    def test_postponed_and_cancelled_are_settled(self):
        for code, expected in (("PST", "postponed"), ("CANC", "cancelled"), ("AET", "finished"), ("PEN", "finished")):
            with self.store._db() as db:
                db.execute("DELETE FROM requests")
            self.store._put("live_observations", None)
            self.store._put("settle_last:api_sports", "")
            self.snapshot()
            self.assertEqual(self.settle(board((1, code))), 1, code)
            self.assertEqual(self.observation()["status_normalized"], expected, code)

    def test_still_in_progress_or_unlisted_is_never_finished(self):
        self.snapshot()
        for payload in (board((1, "2H")), board((1, "NS")), board((99, "FT")), board()):
            self.store._put("settle_last:api_sports", "")
            self.assertEqual(self.settle(payload), 0)
            self.assertIsNone(self.observation())
        self.assertEqual(len(self.urls), 4)

    def test_no_call_when_final_not_yet_due_too_old_or_not_collected(self):
        self.snapshot()
        self.assertEqual(self.settle(board((1, "FT")), now=NOW), 0)                       # still inside start..end+30
        self.assertEqual(self.settle(board((1, "FT")), now=NOW + timedelta(hours=15)), 0)  # past the 12 h window
        self.assertEqual(self.urls, [])
        self.store._put("live_observations", {"events": {"api-sports:1": {
            "status": "FT", "status_normalized": "finished", "status_observed_at": iso(LATER - timedelta(minutes=5))}}})
        self.assertEqual(self.settle(board((1, "FT"))), 0)                                 # already final
        self.assertEqual(self.urls, [])
        self.store.save_snapshot("sports:api_sports", {"events": []})
        self.engine._materialize(now=NOW)
        self.assertEqual(self.settle(board()), 0)                                          # nothing to settle
        self.assertEqual(self.urls, [])

    def test_all_events_final_in_the_collected_feed_make_no_call(self):
        self.snapshot()
        self.store.save_snapshot("sports:api_sports", {"events": [dict(
            self.store.snapshot("sports")["data"]["events"][0], id="api-sports:1", status_normalized="finished",
            status_observed_at="2026-11-14T17:00:00+00:00")]})
        self.engine._materialize(now=NOW)
        self.assertEqual(self.settle(board((1, "FT"))), 0)
        self.assertEqual(self.urls, [])

    def test_one_call_per_product_per_hour_and_the_scheduler_hook(self):
        self.snapshot()
        self.assertEqual(self.settle(board((1, "2H"))), 0)
        self.assertEqual(self.settle(board((1, "FT")), now=LATER + timedelta(minutes=30)), 0)
        self.assertEqual(len(self.urls), 1)
        self.assertEqual(self.settle(board((1, "FT")), now=LATER + timedelta(minutes=61)), 1)
        self.assertEqual(len(self.urls), 2)

    def test_separate_counter_is_capped_and_live_budget_is_untouched(self):
        self.snapshot()
        for _ in range(engine_module.SETTLE_DAILY_BUDGET):
            self.store.increment("settle:api_sports", engine_module.SETTLE_DAILY_BUDGET)
        self.assertEqual(self.settle(board((1, "FT"))), 0)
        self.assertEqual(self.urls, [])
        self.assertIn("daily settle budget", self.store._get("settle_lane")["summary"])
        # live calls do not consume the settle counter
        with self.store._db() as db:
            db.execute("DELETE FROM requests")
        for _ in range(engine_module.LIVE_DAILY_BUDGET):
            self.store.increment("live:api_sports", engine_module.LIVE_DAILY_BUDGET)
        self.assertEqual(self.settle(board((1, "FT"))), 1)

    def test_reserve_backoff_and_plan_window_skip(self):
        self.snapshot()
        for _ in range(providers.SPORTS["api_sports"][3] - engine_module.LIVE_RESERVE):
            self.store.increment("api_sports", 1000)
        self.assertEqual(self.settle(board((1, "FT"))), 0)
        self.assertIn("kept for scheduled refreshes", self.store._get("settle_lane")["summary"])
        with self.store._db() as db:
            db.execute("DELETE FROM requests")
        self.store._put("sports_backoff:api_sports", iso(LATER + timedelta(hours=1)))
        with patch("sportsliveinfo.engine.datetime") as dt:
            dt.now.return_value = LATER
            dt.fromisoformat = type(NOW).fromisoformat
            self.assertEqual(self.settle(board((1, "FT"))), 0)
        self.store._put("sports_backoff:api_sports", "")
        self.store._put("plan_window:api_sports", {"first": 1, "last": 3, "learned_at": iso(LATER)})
        with patch("sportsliveinfo.engine.datetime") as dt:
            dt.now.return_value = LATER
            dt.fromisoformat = type(NOW).fromisoformat
            self.assertEqual(self.settle(board((1, "FT"))), 0)
        self.assertEqual(self.urls, [])
        self.assertEqual(self.store.usage().get("settle:api_sports", 0), 0)

    def test_provider_error_is_noted_and_nothing_is_claimed(self):
        self.snapshot()
        limited = json.dumps({"errors": {"requests": "You have reached the request limit"}, "response": []}).encode()
        self.assertEqual(self.settle(limited), 0)
        self.assertIsNone(self.observation())
        self.assertGreater(self.store._get("sports_backoff:api_sports"), "")

    def test_settled_status_is_folded_by_the_next_collection(self):
        self.snapshot()
        self.settle(board((1, "FT")))
        self.engine._materialize(now=LATER)
        event = next(e for e in self.store.snapshot("sports")["data"]["events"] if e["id"] == "api-sports:1")
        self.assertEqual(event["status_normalized"], "finished")

    def test_scheduler_worker_runs_the_settle_pass(self):
        self.snapshot()
        with patch.object(Engine, "live_lane", return_value=0), \
                patch.object(Engine, "settle_pass", return_value=0) as settle:
            import threading
            self.engine._live_tick(self.store.config(), NOW.astimezone(engine_module.LONDON))
            for thread in threading.enumerate():
                if thread.name == "sportsliveinfo-live":
                    thread.join(timeout=3)
        settle.assert_called_once()


if __name__ == "__main__":
    unittest.main()
