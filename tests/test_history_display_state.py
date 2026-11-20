"""Feed contract section 4.5: yesterday's history asset, display_state, competition_id and the status/time guarantees."""
import json
import tempfile
import unittest
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from sportsliveinfo import feed
from sportsliveinfo.engine import Engine, LONDON
from sportsliveinfo.storage import Store

NOW = datetime(2026, 11, 14, 14, 0, tzinfo=timezone.utc)


def parse(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def row(**kw):
    base = {"status_normalized": "scheduled", "start_utc": "2026-11-14T15:00:00+00:00",
            "start_precision": "scheduled", "expected_end_utc": "2026-11-14T17:00:00+00:00",
            "status_observed_at": "2026-11-14T12:00:00Z"}
    base.update(kw)
    return base


class DisplayStateRuleTests(unittest.TestCase):
    """The table in contract section 4.5, case by case (start 15:00, expected end 17:00, grace 30 min)."""

    def state(self, at, **kw):
        return feed.display_state(row(**kw), parse(at))

    def test_clock_states_in_order(self):
        self.assertEqual(self.state("2026-11-14T14:29:59Z"),
                         {"display_state": "upcoming", "state_until_utc": "2026-11-14T14:30:00Z"})
        self.assertEqual(self.state("2026-11-14T14:30:00Z"),
                         {"display_state": "starting_soon", "state_until_utc": "2026-11-14T15:00:00Z"})
        self.assertEqual(self.state("2026-11-14T15:00:00Z"),
                         {"display_state": "should_be_on", "state_until_utc": "2026-11-14T17:30:00Z"})
        self.assertEqual(self.state("2026-11-14T17:29:59Z")["display_state"], "should_be_on")
        # past the expected end plus grace with no final status: probably finished, no finished_at_utc
        self.assertEqual(self.state("2026-11-14T17:30:00Z"), {"display_state": "finished"})

    def test_live_is_trusted_only_inside_live_until(self):
        live = dict(status_normalized="live", live_until_utc="2026-11-14T16:15:00Z", status_observed_at="2026-11-14T15:30:00Z")
        self.assertEqual(self.state("2026-11-14T15:40:00Z", **live),
                         {"display_state": "live", "state_until_utc": "2026-11-14T16:15:00Z"})
        # an expired or unobserved live falls back to the clock: "should be on", never LIVE
        self.assertEqual(self.state("2026-11-14T16:15:00Z", **live)["display_state"], "should_be_on")
        self.assertEqual(self.state("2026-11-14T15:40:00Z", status_normalized="live")["display_state"], "should_be_on")

    def test_final_statuses_win_over_the_clock(self):
        self.assertEqual(self.state("2026-11-14T10:00:00Z", status_normalized="postponed"), {"display_state": "postponed"})
        self.assertEqual(self.state("2026-11-14T16:00:00Z", status_normalized="cancelled"), {"display_state": "cancelled"})
        self.assertEqual(self.state("2026-11-14T16:00:00Z", status_normalized="finished"),
                         {"display_state": "finished", "finished_at_utc": "2026-11-14T12:00:00Z"})

    def test_unconfirmed_time_is_tbc_until_the_end_of_that_london_day(self):
        tbc = dict(start_precision="date_only", start_utc="2026-11-16T00:00:00+00:00",
                   expected_end_utc="2026-11-16T04:00:00+00:00")
        self.assertEqual(self.state("2026-11-14T14:00:00Z", **tbc),
                         {"display_state": "tbc", "state_until_utc": "2026-11-17T00:00:00Z"})
        self.assertEqual(self.state("2026-11-18T14:00:00Z", **tbc), {"display_state": "tbc"})
        # summer: London midnight is 23:00Z the evening before; the day ends 23:00Z
        summer = dict(tbc, start_precision="time_tbc", start_utc="2026-07-14T23:00:00+00:00",
                      expected_end_utc="2026-07-15T03:00:00+00:00")
        self.assertEqual(feed.display_state(row(**summer), parse("2026-07-10T09:00:00Z")),
                         {"display_state": "tbc", "state_until_utc": "2026-07-15T23:00:00Z"})

    def test_a_row_without_what_the_rule_needs_has_no_state(self):
        self.assertIsNone(feed.display_state({"status_normalized": "scheduled"}, NOW))
        self.assertIsNone(feed.display_state(row(expected_end_utc=None), NOW))

    def test_every_state_is_in_the_published_enum(self):
        seen = set()
        for at in ("10:00", "14:45", "16:00", "18:00"):
            seen.add(self.state("2026-11-14T%s:00Z" % at)["display_state"])
        for status in ("postponed", "cancelled", "finished"):
            seen.add(self.state("2026-11-14T16:00:00Z", status_normalized=status)["display_state"])
        seen.add(self.state("2026-11-14T10:00:00Z", start_precision="date_only")["display_state"])
        seen.add(self.state("2026-11-14T15:10:00Z", status_normalized="live", live_until_utc="2026-11-14T15:40:00Z")["display_state"])
        self.assertEqual(seen, set(feed.DISPLAY_STATES))


class TimePrecisionAndGuaranteeTests(unittest.TestCase):
    def event(self, **kw):
        base = {"id": "x:1", "sport": "football", "sport_label": "Football", "category_id": "football.other",
                "title": "A v B", "participants": ["A", "B"], "start_utc": "2026-11-16T15:00:00+00:00",
                "start_precision": "scheduled", "broadcasts": [], "source_id": "api_sports"}
        base.update(kw)
        return base

    def test_london_midnight_convention_winter_summer_and_idempotent(self):
        self.assertEqual(feed.london_midnight_utc("2026-11-16T12:00:00+00:00"), "2026-11-16T00:00:00+00:00")
        self.assertEqual(feed.london_midnight_utc("2026-07-15T12:00:00+00:00"), "2026-07-14T23:00:00+00:00")
        once = feed.london_midnight_utc("2026-07-15T12:00:00+00:00")
        self.assertEqual(feed.london_midnight_utc(once), once)
        self.assertIsNone(feed.london_midnight_utc("not a time"))

    def test_date_only_and_time_tbc_never_carry_a_clock_start(self):
        for precision in ("date_only", "time_tbc"):
            out = feed._event_public(self.event(start_precision=precision, start_utc="2026-07-15T12:00:00+00:00",
                                                end_utc="2026-07-15T14:00:00+00:00"), at=NOW)
            self.assertEqual(out["start_utc"], "2026-07-14T23:00:00+00:00", precision)     # 00:00 on 15 July, London
            self.assertNotIn("end_utc", out)
            self.assertEqual(out["expected_end_utc"], "2026-07-15T01:00:00Z")              # sport default placeholder
            self.assertEqual(out["display_state"], "tbc")
        confirmed = feed._event_public(self.event(start_utc="2026-07-15T12:00:00+00:00"))
        self.assertEqual(confirmed["start_utc"], "2026-07-15T12:00:00+00:00")             # scheduled times untouched

    def test_status_competition_and_expected_end_are_always_present(self):
        out = feed._event_public(self.event(competition="Liga Nacional", competition_id=None))
        self.assertEqual((out["status_normalized"], out["competition_id"]), ("scheduled", "football.other"))
        self.assertIn("expected_end_utc", out)
        known = feed._event_public(self.event(competition_id="football.premier_league", status_normalized=""))
        self.assertEqual((known["status_normalized"], known["competition_id"]), ("scheduled", "football.premier_league"))
        other = feed._event_public(self.event(sport="tennis", competition_id=None))
        self.assertEqual(other["competition_id"], "tennis.other")

    def test_the_catch_all_competition_does_not_make_an_event_core(self):
        out = feed._event_public(self.event(sport="football", competition="Liga Nacional", competition_country="Honduras",
                                            competition_id=None, category_id="football.other"))
        self.assertEqual(out["tier"], "extra")


class GoldenHistoryTests(unittest.TestCase):
    """Against the golden fixture (14 Nov 2026 14:00 UTC; yesterday is 13 Nov)."""
    ROOT = Path(__file__).resolve().parents[1] / "schemas" / "fixtures" / "sli-v1"

    def setUp(self):
        self.manifest = json.loads((self.ROOT / "v1" / "manifest.json").read_text())

    def asset(self, kind):
        entry = next(a for a in self.manifest["assets"] if a["kind"] == kind)
        return entry, json.loads((self.ROOT / entry["path"]).read_text())

    def test_manifest_declares_history_and_the_asset_is_optional(self):
        self.assertEqual(self.manifest["window"], {"from": "2026-11-14", "to": "2026-11-21", "history_from": "2026-11-13"})
        entry, doc = self.asset("events:2026-11-13")
        self.assertFalse(entry["required"])
        self.assertTrue(entry["history"])
        self.assertEqual((doc["schema"], doc["date"]), ("sli.events-day/1", "2026-11-13"))
        self.assertEqual(self.manifest["format"], "sli/1.6")
        self.assertEqual(self.manifest["compatibility"]["min_reader_minor"], 0)
        self.assertTrue({"event_history", "display_state"} <= set(self.manifest["capabilities"]))
        required = [a["kind"] for a in self.manifest["assets"] if a["required"] and a["kind"].startswith("events:")]
        self.assertEqual(required, ["events:2026-11-14"])

    def test_yesterday_keeps_status_final_marker_and_channel_link(self):
        _, doc = self.asset("events:2026-11-13")
        event, = doc["events"]
        self.assertEqual(event["id"], "api-sports:9010")
        self.assertEqual((event["status_normalized"], event["display_state"]), ("finished", "finished"))
        self.assertEqual(event["finished_at_utc"], "2026-11-14T04:00:00Z")
        self.assertNotIn("state_until_utc", event)
        self.assertEqual(event["broadcast_links"][0]["canonical_channel_id"], "gb.sky.sports.main_event")

    def test_yesterday_is_never_in_today(self):
        _, today = self.asset("today")
        referenced = {i for g in today["groups"] for c in g["categories"] for i in c["event_ids"]}
        self.assertNotIn("api-sports:9010", referenced)
        _, today_events = self.asset("events:2026-11-14")
        self.assertNotIn("api-sports:9010", {e["id"] for e in today_events["events"]})
        self.assertEqual(self.manifest["coverage"]["today"], len(referenced))

    def test_every_event_has_the_guaranteed_fields(self):
        count = 0
        for a in self.manifest["assets"]:
            if a["kind"].split(":")[0] in ("events", "events_extra"):
                for e in json.loads((self.ROOT / a["path"]).read_text())["events"]:
                    count += 1
                    for field in ("status_normalized", "expected_end_utc", "competition_id", "display_state"):
                        self.assertTrue(e.get(field), (e["id"], field))
        self.assertEqual(count, self.manifest["coverage"]["events"])

    def test_date_only_event_uses_the_london_midnight_convention(self):
        _, doc = self.asset("events:2026-11-16")
        event = next(e for e in doc["events"] if e["id"] == "thesportsdb:6002")
        self.assertEqual((event["start_precision"], event["start_utc"], event["display_state"]),
                         ("date_only", "2026-11-16T00:00:00+00:00", "tbc"))
        self.assertEqual(event["state_until_utc"], "2026-11-17T00:00:00Z")

    def test_unknown_competition_gets_the_catch_all(self):
        _, doc = self.asset("events_extra:2026-11-14")
        self.assertEqual(doc["events"][0]["competition_id"], "football.other")

    def test_live_row_carries_display_state(self):
        _, live = self.asset("live")
        self.assertEqual(live["events"][0]["display_state"], "live")
        self.assertEqual(live["events"][0]["state_until_utc"], live["events"][0]["live_until_utc"])


class HistoryCollectionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = Store(Path(temp.name) / "h.sqlite3")
        self.engine = Engine(self.store)
        self.today = datetime.now(LONDON).date()

    def test_first_full_discovery_adds_yesterday_to_api_sports_only(self):
        days = self.engine._days("api_sports", None, self.today)
        self.assertEqual(days[0], self.today - timedelta(days=1))
        self.assertEqual(len(days), 8)
        fresh = {"data": {"full_discovery_at": datetime.now(timezone.utc).isoformat()}, "updated_at": "x"}
        self.assertEqual(self.engine._days("api_sports", fresh, self.today), [self.today])     # later runs: today only
        self.assertEqual(self.engine._days("thesportsdb", None, self.today), [self.today])    # no extra day elsewhere

    def test_the_learned_free_plan_window_decides_whether_yesterday_is_requested(self):
        self.store._put("plan_window:api_sports", {"first": 0, "last": 1,
                                                  "learned_at": datetime.now(timezone.utc).isoformat()})
        self.assertEqual(self.engine._days("api_sports", None, self.today), [self.today, self.today + timedelta(days=1)])

    def test_football_data_asks_from_yesterday(self):
        self.store.configure({"keys": {"football_data": "synthetic"}})
        item, = self.engine._plan("football_data", self.store.config(), self.today)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(item["url"]).query)
        self.assertEqual(query["dateFrom"], [(self.today - timedelta(days=1)).isoformat()])
        self.assertEqual(query["dateTo"], [(self.today + timedelta(days=7)).isoformat()])

    def test_source_records_are_retained_for_three_days(self):
        self.store.configure({"keys": {"api_sports": "synthetic"}, "sports": {"api_sports": True}})
        stamp = lambda days: (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
        old = [{"id": "api-sports:%d" % i, "start_utc": stamp(days), "sport": "football"}
               for i, days in ((1, 2.5), (2, 3.5))]
        self.store.save_snapshot("sports:api_sports", {"events": old, "source_id": "api_sports"})
        with patch.object(Engine, "_request", return_value=[]), patch.object(Engine, "_pace"):
            self.assertTrue(self.engine._collect_sport("api_sports", self.store.config()))
        kept = {e["id"] for e in self.store.snapshot("sports:api_sports")["data"]["events"]}
        self.assertEqual(kept, {"api-sports:1"})          # 2.5 days old stays (day before yesterday), 3.5 is dropped

    def test_yesterday_stays_in_the_snapshot_but_not_in_todays_rail(self):
        def ev(i, start):
            return {"id": "api-sports:%d" % i, "source_id": "api_sports", "sport": "football", "competition": "Premier League",
                    "competition_country": "England", "title": "T%d v U%d" % (i, i), "participants": ["T%d" % i, "U%d" % i],
                    "start_utc": start, "start_precision": "scheduled", "status_normalized": "scheduled", "broadcasts": [],
                    "broadcast_verified": False}
        events = [ev(1, "2026-11-12T15:00:00+00:00"), ev(2, "2026-11-13T15:00:00+00:00"),
                  ev(3, "2026-11-14T15:00:00+00:00"), ev(4, "2026-11-21T15:00:00+00:00"), ev(5, "2026-11-22T15:00:00+00:00")]
        self.store.configure({"setup_complete": True, "sports": {"api_sports": True}, "publication_approvals": ["api_sports"]})
        self.store.save_snapshot("sports:api_sports", {"events": events, "source_id": "api_sports"})
        self.engine._materialize(now=NOW)
        ids = {e["id"] for e in self.store.snapshot("sports")["data"]["events"]}
        self.assertEqual(ids, {"api-sports:2", "api-sports:3", "api-sports:4"})        # day-2 and day+8 are out
        today = self.store.snapshot("today")["data"]
        self.assertEqual(today["count"], 1)
        manifest, files = feed.build_feed(self.store, now=NOW)
        history = next(a for a in manifest["assets"] if a["kind"] == "events:2026-11-13")
        self.assertEqual([e["id"] for e in json.loads(files[history["path"]])["events"]], ["api-sports:2"])
        self.assertEqual(manifest["coverage"]["today"], 1)


if __name__ == "__main__":
    unittest.main()
