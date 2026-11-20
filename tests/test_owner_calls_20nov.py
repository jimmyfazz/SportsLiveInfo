"""Owner decisions of 20 Nov 2026: CA-16 (wrestling and sumo removed), CA-17 (tennis lapse + extra tier),
CA-18 (15 minute live re-stamp and the separate live commit budget). CA-09 is deliberately unchanged."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sportsliveinfo import engine as engine_module, feed, providers, taxonomy
from sportsliveinfo.engine import Engine
from sportsliveinfo.storage import Store

UTC = timezone.utc
NOW = datetime(2026, 11, 20, 14, 0, tzinfo=UTC)


def sdb_row(event_id, title, league, sport="Fighting", stamp="2026-11-20T00:00:00", **kw):
    row = {"idEvent": str(event_id), "strEvent": title, "strLeague": league, "strSport": sport, "strTimestamp": stamp,
           "dateEvent": stamp[:10], "strStatus": "Not Started", "strHomeTeam": None, "strAwayTeam": None}
    row.update(kw)
    return row


def decode(*rows):
    return providers.thesportsdb_events(json.dumps({"events": list(rows)}))


class WrestlingAndSumoRemovedTests(unittest.TestCase):
    def test_the_decoder_drops_wrestling_and_sumo_and_keeps_real_combat_sports(self):
        events = decode(
            sdb_row(1, "SmackDown #1422", "WWE"),
            sdb_row(2, "Kyushu Basho Day 13", "Grand Sumo Tournament", sport="Sumo"),
            sdb_row(3, "NXT Deadline", "WWE NXT"),
            sdb_row(4, "Dynamite", "AEW"),
            sdb_row(5, "Impact", "TNA Wrestling"),
            sdb_row(6, "Raw", "Professional Wrestling", sport="Wrestling"),
            sdb_row(7, "BKFC Fight Night Myrtle Beach", "BKFC"),
            sdb_row(8, "UFC Fight Night: Smith vs Jones", "UFC"),
            sdb_row(9, "Kickboxing Glory 99", "Glory Kickboxing"),
            sdb_row(10, "Smith v Jones", "Boxing", stamp="2026-11-20T20:00:00"))
        self.assertEqual(sorted(e["id"] for e in events),
                         ["thesportsdb:10", "thesportsdb:7", "thesportsdb:8", "thesportsdb:9"])

    def test_real_fighting_rows_keep_their_existing_time_rules(self):
        by_id = {e["id"]: e for e in decode(sdb_row(7, "BKFC Fight Night Myrtle Beach", "BKFC"),
                                            sdb_row(8, "UFC 999", "UFC", stamp="2026-11-21T02:00:00"))}
        self.assertEqual((by_id["thesportsdb:7"]["start_utc"], by_id["thesportsdb:7"]["start_precision"]),
                         ("2026-11-20T00:00:00+00:00", "scheduled"))        # midnight rule unchanged for fighting
        self.assertEqual(by_id["thesportsdb:8"]["sport"], "Fighting")
        self.assertEqual(taxonomy.classify(by_id["thesportsdb:8"])["sport"], "mma")

    def test_no_name_that_merely_contains_the_letters_matches(self):
        for league in ("Tnafc Cup", "Sumoto League", "Anxt Series"):
            self.assertFalse(providers.is_not_carried("Soccer", league, "A v B"), league)
        self.assertTrue(providers.is_not_carried("", "wwe raw", ""))
        self.assertTrue(providers.is_not_carried("", "", "Natsu BASHO Day 1"))

    def test_a_stored_snapshot_from_before_the_upgrade_never_reaches_an_asset(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / "s.sqlite3")
            store.configure({"setup_complete": True, "sports": {"thesportsdb": True},
                             "publication_approvals": ["thesportsdb"]})
            stored = []
            for e in decode(sdb_row(1, "SmackDown #1422", "WWE"), sdb_row(7, "BKFC Fight Night Myrtle Beach", "BKFC"),
                            sdb_row(8, "UFC 999", "UFC")):
                stored.append(e)
            # Simulate an old snapshot that still holds a wrestling row.
            stored.append(dict(stored[0], id="thesportsdb:99", title="SmackDown #1422", competition="WWE", sport="mma"))
            store.save_snapshot("sports:thesportsdb", {"events": stored, "source_id": "thesportsdb"})
            Engine(store)._materialize(now=NOW)
            manifest, files = feed.build_feed(store, now=NOW)
            text = "".join(data.decode() for path, data in files.items() if "/events" in path)
            self.assertIn("BKFC Fight Night Myrtle Beach", text)
            self.assertIn("UFC 999", text)
            self.assertNotIn("SmackDown", text)


def tennis(i, competition, start, status="scheduled", **kw):
    e = {"id": "tennis-api:atp:%d-1-1-1" % i, "source_id": "tennis_api", "sport": "tennis", "competition": competition,
         "event_type": "match", "title": "P%d v Q%d" % (i, i), "participants": ["P%d" % i, "Q%d" % i],
         "start_utc": start, "start_precision": "scheduled", "status_normalized": status,
         "broadcasts": [], "broadcast_verified": False}
    e.update(kw)
    return e


class TennisTests(unittest.TestCase):
    def tier(self, competition):
        return feed.event_tier(taxonomy.classify(tennis(1, competition, "2026-11-20T10:00:00+00:00")))

    def test_core_only_for_the_top_of_the_sport(self):
        for name in ("Wimbledon", "Australian Open", "Roland Garros", "US Open", "ATP Finals", "Nitto ATP Finals",
                     "WTA Finals", "Davis Cup", "Billie Jean King Cup", "United Cup", "ATP Paris Masters",
                     "ATP 250 Stockholm", "WTA 1000 Beijing", "Olympic Games Tennis"):
            self.assertEqual(self.tier(name), "core", name)

    def test_minor_exhibition_and_unknown_tours_are_extra(self):
        for name in ("ATP Challenger Tour Rome", "ITF M15 Antalya", "ITF W25 Monastir", "UTR Pro Tennis Series",
                     "WTA 125 Colina", "Exhibition Abu Dhabi", "Unknown Cup", ""):
            self.assertEqual(self.tier(name), "extra", name)

    def test_a_guide_listed_private_row_stays_core(self):
        self.assertEqual(feed.event_tier({"origin": "guide_listing", "sport": "tennis"}), "core")

    def test_lapse_rule(self):
        # tennis 3 h typical + 30 min grace = 13:30 -> 16:30 for a 10:00 start
        old = tennis(1, "ATP Paris Masters", "2026-11-20T10:00:00+00:00")
        self.assertFalse(feed.tennis_lapsed(old, datetime(2026, 11, 20, 13, 29, tzinfo=UTC)))
        self.assertTrue(feed.tennis_lapsed(old, datetime(2026, 11, 20, 13, 30, tzinfo=UTC)))
        for status in ("live", "finished", "postponed", "cancelled"):
            self.assertFalse(feed.tennis_lapsed(dict(old, status_normalized=status), NOW), status)
        self.assertFalse(feed.tennis_lapsed(dict(old, sport="football"), NOW))
        self.assertFalse(feed.tennis_lapsed(dict(old, start_precision="date_only"), NOW))

    def test_lapsed_rows_leave_every_asset_but_nothing_is_published_finished(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / "t.sqlite3")
            store.configure({"setup_complete": True, "sports": {"tennis_api": True},
                             "publication_approvals": ["tennis_api"]})
            events = [tennis(1, "ATP Paris Masters", "2026-11-19T10:00:00+00:00"),       # yesterday, never settled
                      tennis(2, "ATP Paris Masters", "2026-11-20T08:00:00+00:00"),       # today, long over
                      tennis(3, "ATP Paris Masters", "2026-11-20T10:30:00+00:00", status="live"),
                      tennis(4, "ATP Paris Masters", "2026-11-20T11:30:00+00:00", status="finished"),
                      tennis(5, "ATP Paris Masters", "2026-11-20T16:00:00+00:00"),       # later today
                      tennis(6, "ITF M15 Antalya", "2026-11-20T16:00:00+00:00")]         # minor: extra tier
            store.save_snapshot("sports:tennis_api", {"events": events, "source_id": "tennis_api"})
            Engine(store)._materialize(now=NOW)
            manifest, files = feed.build_feed(store, now=NOW)
            by_kind = {a["kind"]: json.loads(files[a["path"]]) for a in manifest["assets"] if a["kind"].startswith("events")}
            ids = lambda kind: sorted(e["id"].split(":")[-1] for e in by_kind.get(kind, {}).get("events", []))
            self.assertEqual(ids("events:2026-11-19"), [])
            self.assertEqual(ids("events:2026-11-20"), ["3-1-1-1", "4-1-1-1", "5-1-1-1"])
            self.assertEqual(ids("events_extra:2026-11-20"), ["6-1-1-1"])
            published = [e for doc in by_kind.values() for e in doc["events"]]
            self.assertEqual({e["id"]: e["status_normalized"] for e in published}["tennis-api:atp:4-1-1-1"], "finished")
            self.assertNotIn("tennis-api:atp:2-1-1-1", {e["id"] for e in published})


class LiveBudgetTests(unittest.TestCase):
    def ledger(self, regular, live, size=10_000, days=7):
        rows = []
        for d in range(days):
            for k in range(regular):
                rows.append({"at": (NOW - timedelta(days=d, minutes=k + 1)).isoformat(), "bytes": size, "files": 3})
            for k in range(live):
                rows.append({"at": (NOW - timedelta(days=d, minutes=10 * k + 1)).isoformat(), "bytes": 500, "files": 2,
                             "kind": "live"})
        return rows

    def test_the_cadence_constants(self):
        self.assertEqual(engine_module.LIVE_REFRESH, timedelta(minutes=15))
        self.assertEqual(engine_module.LIVE_INTERVAL, timedelta(minutes=15))
        self.assertEqual(feed.LIVE_MAX_AGE, timedelta(minutes=45))
        self.assertEqual(feed.LIVE_LANE_INTERVAL_MINUTES, 15)
        self.assertEqual(engine_module.LIVE_DAILY_BUDGET, 40)        # CA-09: owner said no change

    def test_a_busy_live_day_does_not_trip_the_daily_budget_but_runaway_live_does(self):
        busy = feed.growth_report(self.ledger(3, 40), NOW)               # 40 live commits a day, ten hours in play
        self.assertEqual(busy["over_budget"], [])
        self.assertEqual(busy["live_commits"], 280)
        self.assertAlmostEqual(busy["live_per_day"], 40, delta=6)
        self.assertAlmostEqual(busy["per_day"], 3, delta=0.5)
        runaway = feed.growth_report(self.ledger(3, 90), NOW)
        self.assertEqual(runaway["over_budget"], ["live_commits_per_day"])
        regular = feed.growth_report(self.ledger(12, 0), NOW)
        self.assertEqual(regular["over_budget"], ["commits_per_day"])

    def test_the_commit_path_marks_live_commits(self):
        ledger = feed.growth_record([], "2026-11-20T12:00:00Z", 5, 2, live=True)
        ledger = feed.growth_record(ledger, "2026-11-20T12:15:00Z", 5, 2)
        self.assertEqual([r.get("kind") for r in ledger], ["live", None])

    def test_a_commit_made_by_the_live_lane_is_recorded_as_live(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / "s.sqlite3")
            engine = Engine(store)
            manifest = {"revision": "r1", "coverage": {"events": 1, "guide_corroborated_broadcasts": 0}}
            for trigger, revision in (("live", "r1"), ("auto", "r2")):
                manifest["revision"] = revision
                engine._tls.trigger = trigger
                with patch.object(Engine, "_github_commit", return_value="sha"):
                    engine._commit_feed("o", "r", "main", "t", manifest, {"v1/assets/x/%s.json" % revision: b"1"},
                                        {"revisions": []}, "feed_state", "publisher", "label", private=False)
            self.assertEqual([r.get("kind") for r in store._get("feed_growth")["ledger"]], ["live", None])


if __name__ == "__main__":
    unittest.main()
