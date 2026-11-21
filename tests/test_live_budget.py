"""0.3.28 (CA-09, 21 Nov 2026): the live lane polls only for core-tier events, the daily live budget is computed from the
plan, a time-of-day reserve keeps the evening, back-off stretches the interval when the budget runs low, and an
advisory says when the budget is spent. Built from the real case: on 21 Nov live publishes stopped at 11:13 UTC while
six events were live at 12:00."""
import json
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from ingress_test_support import IngressTestClient
from sportsliveinfo import engine as engine_module, health, providers
from sportsliveinfo.engine import Engine, live_allowance, live_daily_budget
from test_live_tiers_corroboration import LiveLaneBase, ev

DAY = datetime(2026, 11, 21, tzinfo=timezone.utc)      # Saturday, London = UTC
LIMIT = providers.SPORTS["api_sports"][3]


def at(hour, minute=0):
    return DAY + timedelta(hours=hour, minutes=minute)


def iso(moment):
    return moment.isoformat(timespec="seconds")


def board_of(ids, short="2H"):
    return json.dumps({"errors": [], "paging": {"current": 1, "total": 1}, "response": [
        {"fixture": {"id": fid, "date": "2026-11-21T12:00:00+00:00", "status": {"short": short}},
         "teams": {"home": {"name": "A"}, "away": {"name": "B"}}, "league": {"id": 39, "name": "x"}}
        for fid in ids]}).encode()


class LiveBudgetBase(LiveLaneBase):
    def put(self, core=(), extra=(), start=at(11)):
        rows = []
        for fid in core:
            rows.append(ev(id="api-sports:%d" % fid, competition="Premier League", competition_code="as:39",
                           competition_country="England", participants=["A%d" % fid, "B%d" % fid],
                           title="A%d v B%d" % (fid, fid), start_utc=iso(start), status="NS",
                           status_normalized="scheduled", status_observed_at=iso(start - timedelta(hours=1))))
        for fid in extra:
            rows.append(ev(id="api-sports:%d" % fid, competition="Copa Local", competition_country="Peru",
                           participants=["C%d" % fid, "D%d" % fid], title="C%d v D%d" % (fid, fid),
                           start_utc=iso(start), status="NS", status_normalized="scheduled",
                           status_observed_at=iso(start - timedelta(hours=1))))
        self.store.save_snapshot("sports:api_sports", {"events": rows})
        self.engine._materialize(now=start)

    def lane(self, ids, now):
        return self.run_lane(board_of(ids), now=now)


class CoreOnlyTests(LiveBudgetBase):
    def test_extra_only_candidates_make_no_call(self):
        self.put(extra=(1, 2))
        self.assertEqual(self.lane((1, 2), at(12)), 0)
        self.assertEqual(self.urls, [])
        self.assertEqual(self.store.usage().get("live:api_sports", 0), 0)
        self.assertIn("only extra-tier", self.store._get("live_lane")["summary"])
        row = self.store._get("live_budget")["products"]["api_sports"]
        self.assertEqual((row["core"], row["extra"], row["used"]), (0, 2, 0))

    def test_a_core_event_triggers_the_call_and_extra_events_ride_along(self):
        self.put(core=(1,), extra=(2,))
        self.assertEqual(self.lane((1, 2), at(12)), 2)
        self.assertEqual(len(self.urls), 1)
        events = self.store._get("live_observations")["events"]
        self.assertEqual({events["api-sports:1"]["status_normalized"], events["api-sports:2"]["status_normalized"]},
                         {"live"})
        row = self.store._get("live_budget")["products"]["api_sports"]
        self.assertEqual((row["core"], row["extra"], row["used"], row["limit"]), (1, 1, 1, LIMIT - engine_module.LIVE_RESERVE))
        self.assertEqual(row["last_call"], iso(at(12)))


class AllowanceTests(unittest.TestCase):
    def test_budget_is_computed_from_the_plan(self):
        self.assertEqual(live_daily_budget(80), 60)
        self.assertEqual(engine_module.LIVE_DAILY_BUDGET, live_daily_budget(LIMIT))
        self.assertEqual(live_daily_budget(10), 0)

    def test_evening_reserve_is_held_until_17_utc(self):
        ok, reason, detail = live_allowance(at(12), 80, 44, 56)           # 16 of 60 left, 18 held for the evening
        self.assertEqual((ok, reason), (False, "evening_reserve"))
        self.assertEqual(detail["evening_reserve"], 18)
        self.assertTrue(live_allowance(at(17), 80, 44, 56)[0])            # the same numbers are fine in the evening
        self.assertTrue(live_allowance(at(12), 80, 30, 42)[0])           # plenty left in the morning
        self.assertEqual(live_allowance(at(12), 80, 60, 60)[1], "exhausted")

    def test_backoff_below_a_quarter_stretches_to_30_minutes_and_needs_a_live_core_event(self):
        # evening, budget 60, 48 used: 12 left (< 15 = 25%)
        ok, reason, detail = live_allowance(at(19, 15), 80, 48, 20, last_call=at(19), active_core=True)
        self.assertEqual((ok, reason, detail["backoff"]), (False, "backoff_spacing", True))
        self.assertTrue(live_allowance(at(19, 30), 80, 48, 20, last_call=at(19), active_core=True)[0])
        self.assertEqual(live_allowance(at(19, 30), 80, 48, 20, last_call=at(19), active_core=False)[1], "backoff_idle")
        self.assertFalse(live_allowance(at(19, 15), 80, 30, 20, last_call=at(19))[2]["backoff"])   # plenty left: 15 min


class DaySimulationTests(LiveBudgetBase):
    def simulate(self, core, extra):
        """15 minute ticks 06:00-23:45 UTC; scheduled refreshes use API calls at 04:00, 12:00 and 17:00."""
        calls_at = []
        for _ in range(4):
            self.store.increment("api_sports", 1000)
        for minutes in range(6 * 60, 24 * 60, 15):
            now = at(minutes // 60, minutes % 60)
            if minutes in (12 * 60, 17 * 60):
                for _ in range(6 if minutes == 12 * 60 else 4):
                    self.store.increment("api_sports", 1000)
            if minutes in (9 * 60, 14 * 60, 18 * 60, 20 * 60):            # the settle pass: 4 calls a day at most
                self.store.increment("api_sports", 1000)
            before = len(self.urls)
            self.lane(core + extra, now)
            if len(self.urls) > before:
                calls_at.append(now)
        return calls_at

    def test_a_saturday_of_15_minute_polling_lasts_through_the_evening(self):
        # Kick-offs every two hours from 06:00 keep six events in play all day, as on 21 Nov; extras alongside.
        self.store.save_snapshot("sports:api_sports", {"events": []})
        rows = []
        for k, hour in enumerate(range(6, 23, 2)):
            for fid, (comp, country) in ((100 + k, ("Premier League", "England")), (200 + k, ("Copa Local", "Peru"))):
                rows.append(ev(id="api-sports:%d" % fid, competition=comp, competition_country=country,
                               competition_code="as:39" if comp == "Premier League" else "",
                               participants=["A%d" % fid, "B%d" % fid], title="A%d v B%d" % (fid, fid),
                               start_utc=iso(at(hour)), status="NS", status_normalized="scheduled",
                               status_observed_at=iso(at(hour) - timedelta(hours=1))))
        self.store.save_snapshot("sports:api_sports", {"events": rows})
        self.engine._materialize(now=at(6))
        ids = [100 + k for k in range(9)] + [200 + k for k in range(9)]
        calls = self.simulate(ids, [])
        budget = live_daily_budget(LIMIT)
        usage = self.store.usage()
        self.assertLessEqual(usage["live:api_sports"], budget)
        self.assertLessEqual(usage["api_sports"], LIMIT)       # live 60 + scheduled and settle 18 fit the 80 a day
        evening = [c for c in calls if 17 <= c.hour < 23]
        self.assertGreaterEqual(len([c for c in calls if c.hour >= 17]), 0.30 * budget)   # reserve kept (18 of 60)
        self.assertGreaterEqual(len(evening), 15)                        # 17:00-23:00: 3 at 15 min, then every 30
        self.assertGreaterEqual(max(calls), at(22))                      # still polling at the end of the evening
        self.assertTrue(any(c.hour < 12 for c in calls))                 # and the morning was served too
        gap = max(b - a for a, b in zip(calls, calls[1:]) if a.hour >= 17 and b.hour < 23)
        self.assertLessEqual(gap, timedelta(minutes=30))                 # back-off never exceeds 30 minutes
        self.assertEqual(usage["live:api_sports"], len(calls))

    def test_extra_only_day_makes_no_calls_at_all(self):
        rows = [ev(id="api-sports:%d" % (300 + k), competition="Copa Local", competition_country="Peru",
                   participants=["C", "D%d" % k], title="C v D%d" % k, start_utc=iso(at(8 + 2 * k)), status="NS",
                   status_normalized="scheduled", status_observed_at=iso(at(7))) for k in range(8)]
        self.store.save_snapshot("sports:api_sports", {"events": rows})
        self.engine._materialize(now=at(8))
        calls = self.simulate([300 + k for k in range(8)], [])
        self.assertEqual(calls, [])
        self.assertEqual(self.store.usage().get("live:api_sports", 0), 0)


class AdvisoryTests(LiveBudgetBase):
    START = datetime(2026, 11, 21, 3, 0, tzinfo=timezone.utc)

    def evaluate(self, now):
        self.store._put("scheduler_heartbeat", iso(now))
        return health.evaluate(self.store, now, settings={"stall_hours": 3}, started_at=at(0))

    def exhaust(self):
        for _ in range(live_daily_budget(LIMIT)):
            self.store.increment("live:api_sports", 1000)

    def test_advisory_fires_names_the_numbers_stays_200_and_clears_at_midnight(self):
        now = datetime.now(timezone.utc).replace(hour=13, minute=0, second=0, microsecond=0)
        self.put(core=(1,), start=now - timedelta(hours=1))
        self.exhaust()
        self.assertEqual(self.lane((1,), now), 0)
        self.assertEqual(self.urls, [])
        report = self.evaluate(now)
        codes = [i["code"] for i in report["incidents"]]
        self.assertEqual(codes, ["live_budget_exhausted:api_sports"])
        message = report["incidents"][0]["message"]
        self.assertIn("api_sports", message)
        self.assertIn("60 of 60", message)
        self.assertIn("%s 00:00 UTC" % (now + timedelta(days=1)).date().isoformat(), message)
        self.assertTrue(report["ok"])                                    # advisory only
        code, body = health.healthz(self.store, "x", now=now, started_at=at(0))
        self.assertEqual(code, 200)
        self.assertEqual(body["advisories"][0]["code"], "live_budget_exhausted:api_sports")
        self.assertEqual(report["snapshot"]["live_budget"][0]["used"], 60)
        # one persistent notification, naming product and reset time, not repeated
        sent = []
        notifier = health.Notifier(self.store, post=lambda service, payload: sent.append((service, payload)))
        for step in range(3):
            later = now + timedelta(minutes=step)
            notifier.sync(self.evaluate(later)["incidents"], later)
        creates = [p for s, p in sent if s == "create"]
        self.assertEqual(len(creates), 1)
        self.assertIn("live status budget", creates[0]["title"])
        self.assertIn("60 of 60", creates[0]["message"])
        # The next UTC day: the counters are for yesterday, so the advisory is gone at once and is dismissed.
        tomorrow = now + timedelta(days=1, hours=-12, minutes=5)
        self.assertEqual(self.evaluate(tomorrow)["incidents"], [])
        notifier.sync([], tomorrow)
        self.assertEqual([s for s, _ in sent], ["create", "dismiss"])

    def test_advisory_clears_when_the_budget_recovers(self):
        now = datetime.now(timezone.utc).replace(hour=13, minute=0, second=0, microsecond=0)
        self.put(core=(1,), start=now - timedelta(hours=1))
        self.exhaust()
        self.lane((1,), now)
        self.assertEqual(len(self.evaluate(now)["incidents"]), 1)
        with self.store._db() as db:
            db.execute("DELETE FROM requests WHERE provider='live:api_sports'")
        self.assertEqual(self.evaluate(now + timedelta(minutes=1))["incidents"], [])

    def test_no_advisory_for_extra_only_or_unspent_budget(self):
        now = datetime.now(timezone.utc).replace(hour=13, minute=0, second=0, microsecond=0)
        self.put(extra=(2,), start=now - timedelta(hours=1))
        self.exhaust()
        self.lane((2,), now)
        self.assertEqual(self.evaluate(now)["incidents"], [])

    def test_service_health_card_and_scheduler_card_show_the_counters(self):
        now = datetime.now(timezone.utc).replace(hour=13, minute=0, second=0, microsecond=0)
        self.put(core=(1,), extra=(2,), start=now - timedelta(hours=1))
        self.lane((1, 2), now)
        with closing(IngressTestClient(self.store, "csrf-test")) as client:
            with client.open(client.base + "?page=scheduler") as response:
                page = response.read().decode()
            with client.open(client.base + "?page=health") as response:
                diagnostics = response.read().decode()
        self.assertIn("api_sports 1/60", page)
        self.assertIn("core 1, extra 1", page)
        self.assertIn("1/60, core 1 / extra 1", diagnostics)


if __name__ == "__main__":
    unittest.main()
