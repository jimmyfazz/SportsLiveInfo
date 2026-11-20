"""Operations hardening (audit 15 Nov: O1, O3, C4, C10, release mechanics): deadlines, bounded parsing and memory,
asset size parts and alerts, feed growth budget, version agreement, dead-man workflow. No network, no real sleeping."""
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import unittest
import weakref
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from sportsliveinfo import dictionary, feed, health, linking, providers
from sportsliveinfo.engine import Engine
from sportsliveinfo.storage import Store

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc
BASE = datetime(2026, 11, 14, 15, 0, tzinfo=UTC)
GUIDE_URL = providers.EPG["farleyflex"][1]


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class DripResponse:
    """A response that returns one byte per read and takes ``step`` (fake) seconds to do so."""

    def __init__(self, clock, step, total=10_000_000):
        self.clock, self.step, self.left, self.reads = clock, step, total, 0
        self.headers = {}
        self.fp = None

    def read(self, size=-1):
        self.reads += 1
        self.clock.now += self.step
        if self.left <= 0:
            return b""
        self.left -= 1
        return b"x"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    def __init__(self, response):
        self.response, self.timeouts = response, []

    def open(self, request, timeout=None):
        self.timeouts.append(timeout)
        return self.response


class RequestDeadlineTests(unittest.TestCase):
    def fetch(self, step, **kwargs):
        clock = FakeClock()
        response = DripResponse(clock, step, **kwargs)
        opener = FakeOpener(response)
        with patch.object(providers, "_clock", clock), patch.object(providers.urllib.request, "build_opener",
                                                                  return_value=opener):
            try:
                return providers.fetch(GUIDE_URL, max_bytes=50_000_000), response, opener
            except providers.DeadlineExceeded as exc:
                return exc, response, opener

    def test_slow_drip_is_cut_at_the_overall_deadline_not_per_read(self):
        # 20 s per byte is well inside the 30 s per-read timeout, so before 0.3.25 this never ended.
        result, response, opener = self.fetch(step=20.0)
        self.assertIsInstance(result, providers.DeadlineExceeded)
        self.assertIsInstance(result, TimeoutError)            # engine SAFE_ERRORS and failure texts already cover it
        self.assertLessEqual(response.reads, int(providers.REQUEST_DEADLINE // 20) + 2)
        self.assertLessEqual(opener.timeouts[0], 30.0)

    def test_a_fast_response_is_unaffected_and_headers_are_kept(self):
        clock = FakeClock()

        class Fast(DripResponse):
            def read(self, size=-1):
                self.reads += 1
                if self.left <= 0:
                    return b""
                chunk, self.left = b"y" * min(size, self.left), self.left - min(size, self.left)
                return chunk

        response = Fast(clock, 0.0, total=200_000)
        response.headers = {"ETag": '"abc"'}
        got = {}
        with patch.object(providers, "_clock", clock), patch.object(providers.urllib.request, "build_opener",
                                                                  return_value=FakeOpener(response)):
            data = providers.fetch(GUIDE_URL, max_bytes=1_000_000, response_headers=got)
        self.assertEqual(len(data), 200_000)
        self.assertEqual(got, {"ETag": '"abc"'})
        self.assertGreater(response.reads, 3)                  # read in chunks, not in one blocking call

    def test_size_limit_still_applies_while_chunking(self):
        result, response, _ = self.fetch(step=0.0, total=5_000)
        clock = FakeClock()
        with patch.object(providers, "_clock", clock), patch.object(
                providers.urllib.request, "build_opener", return_value=FakeOpener(DripResponse(clock, 0.0, total=5_000))):
            with self.assertRaises(ValueError):
                providers.fetch(GUIDE_URL, max_bytes=1_000)

    def test_a_source_collection_deadline_is_tighter_than_one_request(self):
        clock = FakeClock()
        response = DripResponse(clock, 10.0)
        with patch.object(providers, "_clock", clock), patch.object(
                providers.urllib.request, "build_opener", return_value=FakeOpener(response)):
            with providers.deadline_scope(35.0):
                with self.assertRaises(providers.DeadlineExceeded):
                    providers.fetch(GUIDE_URL, max_bytes=50_000_000)
        self.assertLessEqual(response.reads, 5)
        self.assertIsNone(providers.current_deadline())        # scope restored

    def test_the_xmltv_parse_honours_the_source_deadline(self):
        clock = FakeClock()
        raw = b"<tv>" + b"<channel id='a'><display-name>A</display-name></channel>" * 4000 + b"</tv>"
        with patch.object(providers, "_clock", clock):
            with providers.deadline_scope(5.0):
                clock.now += 10.0
                with self.assertRaises(providers.DeadlineExceeded):
                    providers.decode_xmltv(raw, "farleyflex")

    def test_deadline_failure_text_is_actionable(self):
        from sportsliveinfo.engine import _guide_failure, _sports_failure
        exc = providers.DeadlineExceeded("x")
        self.assertIn("too slow", _guide_failure(exc))
        self.assertIn("too slow", _sports_failure(exc))


class StuckCollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "s.sqlite3")
        self.store.configure({"setup_complete": True, "sports": {"jolpica": True}})
        self.release = threading.Event()

    def tearDown(self):
        self.release.set()
        self.temp.cleanup()

    def test_a_hung_lane_is_abandoned_frees_the_lock_and_reaches_health(self):
        engine = Engine(self.store)
        started = threading.Event()

        def hang(name, conf):
            started.set()
            self.release.wait(20)
            return True

        with patch.object(Engine, "_collect_sport", side_effect=hang), patch("sportsliveinfo.engine.COLLECTION_DEADLINE", 0.4):
            began = datetime.now()
            self.assertTrue(engine._busy.acquire(blocking=False))
            try:
                result = engine._collect_locked()
            finally:
                engine._busy.release()
            took = (datetime.now() - began).total_seconds()
        self.assertTrue(started.is_set())
        self.assertFalse(result)
        self.assertLess(took, 5.0)                             # returned at the deadline, not after the 20 s hang
        job = self.store.recent_jobs(5)[0]
        self.assertEqual((job["provider"], job["state"]), ("collector", "stuck"))
        self.assertTrue(engine._busy.acquire(blocking=False))  # the lock is free: the next run can start
        engine._busy.release()
        report = health.evaluate(self.store, datetime.now(UTC), settings={"stall_hours": 3.0})
        self.assertIn("collector_stuck", [i["code"] for i in report["incidents"]])
        self.assertTrue(report["ok"])                          # advisory: a stale manifest is what turns /healthz red

    def test_a_collection_that_finishes_is_not_marked_stuck(self):
        engine = Engine(self.store)
        with patch.object(Engine, "_collect_sport", return_value=False):
            engine._collect_locked()
        self.assertNotEqual(self.store.recent_jobs(5)[0]["state"], "stuck")


class ParseGateTests(unittest.TestCase):
    def run_parses(self, limit, count=5):
        gate = providers._ParseGate(limit)
        lock, state = threading.Lock(), {"now": 0}

        def fake(raw, source, *args):
            with lock:
                state["now"] += 1
                gate_peak.append(state["now"])
            threading.Event().wait(0.03)
            with lock:
                state["now"] -= 1
            return {"source_id": source}

        gate_peak = []
        with patch.object(providers, "PARSE_GATE", gate), patch.object(providers, "_decode_xmltv", side_effect=fake):
            threads = [threading.Thread(target=providers.decode_xmltv, args=(b"<tv/>", "s%d" % i)) for i in range(count)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(10)
        return gate, max(gate_peak)

    def test_only_one_guide_is_parsed_at_a_time_by_default(self):
        gate, peak = self.run_parses(providers.PARSE_CONCURRENCY)
        self.assertEqual(providers.PARSE_CONCURRENCY, 1)
        self.assertEqual(peak, 1)
        self.assertEqual((gate.active, gate.peak), (0, 1))

    def test_the_limit_is_a_real_bound_and_not_just_serial(self):
        gate, peak = self.run_parses(2, count=6)
        self.assertEqual(peak, 2)
        self.assertEqual(gate.active, 0)

    def test_a_parse_that_cannot_get_a_slot_fails_cleanly(self):
        gate = providers._ParseGate(1)
        gate.acquire(1)
        with patch.object(providers, "PARSE_GATE", gate), patch.object(providers, "PARSE_WAIT", 0.2), \
                patch.object(providers, "_decode_xmltv", side_effect=AssertionError("must not run")):
            with self.assertRaises(providers.DeadlineExceeded):
                providers.decode_xmltv(b"<tv/>", "x")
        self.assertEqual(gate.active, 1)                       # the failed waiter did not take or leak a slot

    def test_the_slot_is_released_when_the_parse_fails(self):
        gate = providers._ParseGate(1)
        with patch.object(providers, "PARSE_GATE", gate), patch.object(providers, "_decode_xmltv", side_effect=ValueError("bad")):
            with self.assertRaises(ValueError):
                providers.decode_xmltv(b"<tv/>", "x")
        self.assertEqual(gate.active, 0)

    def test_programme_records_are_slim(self):
        raw = (b"<tv><channel id='a'><display-name>A</display-name></channel><programme start='20261114150000 +0000' "
               b"stop='20261114160000 +0000' channel='a'><title>T</title><desc>" + b"d" * 900 + b"</desc></programme></tv>")
        parsed = providers.decode_xmltv(raw, "farleyflex")
        self.assertEqual(parsed["programmes"][0]["description"], "")
        self.assertEqual(parsed["programmes"][0]["title"], "T")


class Tracked(dict):
    """A guide that can be watched for garbage collection."""


class GuideStreamTests(unittest.TestCase):
    def guides(self):
        def rows(offset):
            return [{"channel_id": "skysportsmainevent.uk", "start_utc": (BASE + timedelta(minutes=offset)).isoformat(),
                     "end_utc": (BASE + timedelta(minutes=offset + 120)).isoformat(), "title": "Arsenal v Manchester City",
                     "subtitle": "", "is_live": True, "is_repeat": False, "description": "d" * 1000,
                     "categories": ["Sport"], "episode_num": "1", "language": "en", "source_id": "x"}
                    for _ in range(1)]
        old = {"channel_id": "skysportsmainevent.uk", "start_utc": (BASE - timedelta(days=30)).isoformat(),
               "end_utc": (BASE - timedelta(days=30) + timedelta(hours=1)).isoformat(), "title": "Old", "subtitle": "",
               "is_live": False, "is_repeat": False}
        channels = {"skysportsmainevent.uk": "Sky Sports Main Event"}
        return {"farleyflex": {"channels": channels, "programmes": [old] + rows(0)},
                "epgtalk_sports": {"channels": channels, "programmes": rows(5)}}

    def test_stream_gives_the_same_links_guide_map_and_gaps_as_the_dict(self):
        guides = self.guides()
        events = [{"id": "e", "sport": "football", "participants": ["Arsenal", "Manchester City"],
                   "start_utc": BASE.isoformat(), "start_precision": "scheduled"},
                  {"id": "late", "sport": "football", "participants": ["Leeds", "Hull"],
                   "start_utc": (BASE - timedelta(days=20)).isoformat(), "start_precision": "scheduled"}]
        results = []
        for source in (guides, linking.GuideStream(list(guides), lambda n: guides[n], BASE)):
            gaps, gmap = {}, {}
            links = linking.broadcast_candidates(events, source, BASE, gaps=gaps, guide_map=gmap)
            results.append((links, gaps, gmap))
        self.assertEqual(results[0], results[1])
        self.assertIn("e", results[1][0])

    def test_only_one_guide_is_alive_at_a_time_and_records_are_slim(self):
        guides = self.guides()
        refs = []
        alive_at_load = []

        def loader(name):
            alive_at_load.append(sum(ref() is not None for ref in refs))
            guide = Tracked(guides[name])
            refs.append(weakref.ref(guide))
            return guide

        stream = linking.GuideStream(list(guides), loader, BASE)
        seen = []
        for name, slim in stream.items():
            seen.append(slim)
            self.assertLessEqual(set(slim["programmes"][0]), set(linking.SLIM_FIELDS))
            self.assertNotIn("description", slim["programmes"][0])
        self.assertEqual(stream.loaded, 2)
        self.assertEqual(max(alive_at_load), 0)                # the previous guide was gone before the next loaded
        self.assertEqual(len(seen[0]["programmes"]), 1)        # the 30-day-old programme is outside [now-3d, now+10d]
        self.assertEqual(seen[0]["_coverage"][0], BASE - timedelta(days=30))   # but the full span is preserved

    def test_engine_guide_sources_returns_a_stream_and_summaries(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / "s.sqlite3")
            store.configure({"setup_complete": True, "epg": {"farleyflex": True}})
            store.save_snapshot("epg:farleyflex", {"source_id": "farleyflex", "channels": {"a": "A"}, "programmes": []})
            summaries = []
            stream = Engine(store)._guide_sources(store.config(), summaries, True, BASE)
            self.assertIsInstance(stream, linking.GuideStream)
            self.assertEqual([s["id"] for s in summaries], ["farleyflex"])
            self.assertEqual(stream.loaded, 0)                 # nothing is loaded until linking iterates
            self.assertIsNone(Engine(store)._guide_sources(store.config(), [], False, BASE))


def fake_dictionary(channels, regions=()):
    return {"schema": "sli.dictionary/1", "source": {"name": "x", "licence": "y", "url": "z"}, "scope": "UK and Europe",
            "regions": sorted(regions), "market_countries": {"GB": ["GB"]}, "bare_market_codes": {},
            "rules": {"lookup": "l", "confidence": "c", "closed": "c", "precedence": "p"}, "channels": channels}


def channel(i, country, pad=60):
    return {"id": "C%05d.%s" % (i, country.lower()), "name": "n" * pad, "country": country}


class AssetPartsTests(unittest.TestCase):
    def build(self, document, cap):
        import importlib
        spec = importlib.util.spec_from_file_location("gen", ROOT / "tools" / "generate_feed_fixtures.py")
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        with patch.object(feed, "MAX_READER_ASSET_BYTES", cap), patch.object(feed, "dictionary_document", return_value=document):
            return tool.build()

    def mixed(self, per_country=250):
        rows, n = [], 0
        for country in ("GB", "FR", "DE", "US", "CA", "IN", "AU", "NG"):
            for _ in range(per_country):
                rows.append(channel(n, country))
                n += 1
        return rows

    def test_parts_are_regional_each_under_the_cap_and_cover_every_channel_once(self):
        rows = self.mixed()
        cap = 60_000
        manifest, files = self.build(fake_dictionary(rows, ["north_america", "south_asia", "asia_pacific", "africa"]), cap)
        parts = [a for a in manifest["assets"] if a["kind"].startswith("dictionary:")]
        self.assertTrue(parts)
        self.assertTrue(all(a["bytes"] <= cap for a in manifest["assets"]), [(a["kind"], a["bytes"]) for a in manifest["assets"]])
        kinds = {a["kind"] for a in parts}
        self.assertIn("dictionary:uk-eu", kinds)
        self.assertIn("dictionary:uk-eu-2", kinds)             # a group over the part target is cut again
        self.assertTrue(any(k.startswith("dictionary:world-north_america") for k in kinds))
        self.assertTrue(any(k.startswith("dictionary:world-south_asia") for k in kinds))
        seen = []
        for asset in parts:
            document = json.loads(files[asset["path"]])
            self.assertEqual(document["schema"], "sli.dictionary/1")
            self.assertEqual(document["part"]["id"], asset["kind"].split(":", 1)[1])
            self.assertEqual(asset["part"]["of"], len(parts))
            self.assertIn("rules", document)
            seen.extend(c["id"] for c in document["channels"])
        self.assertEqual(sorted(seen), sorted(c["id"] for c in rows))        # nothing dropped, nothing doubled
        self.assertIn("channel_dictionary_parts", manifest["capabilities"])
        self.assertTrue(any("regional parts" in n for n in manifest["notices"]))

    def test_a_dictionary_that_fits_stays_a_single_dictionary_asset(self):
        manifest, _ = self.build(fake_dictionary([channel(i, "GB") for i in range(50)]), 8 * 1024 * 1024)
        kinds = [a["kind"] for a in manifest["assets"]]
        self.assertIn("dictionary", kinds)
        self.assertFalse([k for k in kinds if k.startswith("dictionary:")])
        self.assertNotIn("channel_dictionary_parts", manifest["capabilities"])

    def test_old_readers_keep_a_uk_eu_dictionary_when_that_part_fits(self):
        rows = [channel(i, "GB") for i in range(40)] + [channel(100 + i, "US", pad=400) for i in range(400)]
        manifest, files = self.build(fake_dictionary(rows, ["north_america"]), 60_000)
        by_kind = {a["kind"]: a for a in manifest["assets"]}
        self.assertIn("dictionary", by_kind)
        self.assertEqual(by_kind["dictionary"]["path"], by_kind["dictionary:uk-eu"]["path"])    # same file
        self.assertEqual(by_kind["dictionary"]["sha256"], by_kind["dictionary:uk-eu"]["sha256"])
        ids = {c["id"] for c in json.loads(files[by_kind["dictionary"]["path"]])["channels"]}
        self.assertTrue(ids and all(i.endswith(".gb") for i in ids))

    def test_alert_at_80_percent_of_the_cap_and_none_below(self):
        cap = 100_000
        rows = [channel(i, "GB", pad=100) for i in range(560)]       # about 80-85% of the cap
        manifest, _ = self.build(fake_dictionary(rows), cap)
        dictionary_asset = next(a for a in manifest["assets"] if a["kind"] == "dictionary")
        self.assertGreaterEqual(dictionary_asset["bytes"], 0.8 * cap)
        self.assertLessEqual(dictionary_asset["bytes"], cap)
        self.assertTrue(any("dictionary is" in n and "% of the" in n for n in manifest["notices"]), manifest["notices"])
        health_asset = next(a for a in manifest["assets"] if a["kind"] == "health")
        # the health asset says so too, and the stored budget feeds the /healthz incident
        quiet, _ = self.build(fake_dictionary(rows[:100]), cap)
        self.assertFalse([n for n in quiet["notices"] if "% of the" in n])
        self.assertIn("dictionary", json.dumps([a["kind"] for a in manifest["assets"]]))
        self.assertTrue(health_asset)

    def test_health_incident_and_asset_budget_report(self):
        assets = [{"kind": "dictionary", "bytes": int(0.9 * feed.MAX_READER_ASSET_BYTES)}, {"kind": "today", "bytes": 10}]
        budget = feed.asset_budget(assets, ["events:2026-11-14"])
        self.assertEqual([r["kind"] for r in budget["near_limit"]], ["dictionary"])
        self.assertEqual(budget["skipped"], ["events:2026-11-14"])
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / "s.sqlite3")
            store._put("asset_budget", budget)
            snap = health.snapshot(store, datetime.now(UTC))
            reasons = health.raw_reasons(snap, datetime.now(UTC), {"stall_hours": 3.0})
            self.assertIn("asset_size", [r["code"] for r in reasons])
            self.assertFalse([r for r in reasons if r["code"] == "asset_size" and r["stall"]])

    def test_guide_map_over_the_cap_is_published_in_parts(self):
        guides = [{"source_id": "g%d" % i, "source_url": "https://x/%d" % i, "market": "GB",
                   "channels": [{"id": "c%d" % j, "name": "n" * 40, "programmes_7d": j} for j in range(60)]} for i in range(12)]
        document = {"schema": "sli.guide-map/1", "generated_at": "2026-11-14T14:00:00+00:00", "guides": guides,
                    "service_aliases": {"a": "b"}, "rules": {"use": "u"}}
        parts = feed.guide_map_parts(document)
        self.assertEqual(sorted(k for k, _, _ in parts), sorted("guide_map:%d" % i for i in range(1, len(parts) + 1)))
        merged = [g["source_id"] for _, doc, _ in parts for g in doc["guides"]]
        self.assertEqual(merged, [g["source_id"] for g in guides])
        for _, doc, info in parts:
            self.assertEqual(doc["service_aliases"], {"a": "b"})
            self.assertEqual(info["of"], len(parts))

    def test_real_dictionary_region_split_matches_country_membership(self):
        self.assertIsNone(feed._dictionary_group("GB"))
        self.assertEqual(feed._dictionary_group("US"), "north_america")
        self.assertEqual(feed._dictionary_group("IN"), "south_asia")
        self.assertIsNone(feed._dictionary_group("ZZ"))
        self.assertEqual(set(dictionary.REGIONS), {"north_america", "latin_america_caribbean", "middle_east_north_africa",
                                                   "south_asia", "africa", "asia_pacific"})


class FeedGrowthTests(unittest.TestCase):
    NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)

    def ledger(self, per_day, size, days=7):
        rows = []
        for d in range(days):
            for k in range(per_day):
                at = self.NOW - timedelta(days=d, hours=k * (24 // max(per_day, 1)) % 24, minutes=1)
                rows.append({"at": at.isoformat(), "bytes": size, "files": 3})
        return sorted(rows, key=lambda r: r["at"])

    def test_the_documented_budget_is_three_commits_a_day_within_limits(self):
        report = feed.growth_report(self.ledger(3, 600_000), self.NOW)
        self.assertEqual(report["over_budget"], [])
        self.assertEqual(report["commits"], 21)
        self.assertAlmostEqual(report["per_day"], 3.0, delta=0.5)

    def test_too_many_commits_or_too_many_bytes_alert(self):
        many = feed.growth_report(self.ledger(12, 1_000), self.NOW)
        self.assertEqual(many["over_budget"], ["commits_per_day"])
        big = feed.growth_report(self.ledger(3, 9_000_000), self.NOW)         # 27 MB a day is about 9.9 GB a year
        self.assertEqual(big["over_budget"], ["bytes_per_year"])
        self.assertGreater(big["projected_bytes_per_year"], feed.GROWTH_BYTES_PER_YEAR_BUDGET)

    def test_not_enough_history_makes_no_projection_and_no_alert(self):
        short = [{"at": (self.NOW - timedelta(hours=2)).isoformat(), "bytes": 10 ** 9, "files": 1}]
        report = feed.growth_report(short, self.NOW)
        self.assertIsNone(report["projected_bytes_per_year"])
        self.assertEqual(report["over_budget"], [])
        self.assertEqual(feed.growth_report([], self.NOW)["commits"], 0)
        self.assertEqual(feed.growth_report([{"at": "garbage"}, {}], self.NOW)["commits"], 0)

    def test_the_ledger_is_bounded_and_old_commits_leave_the_window(self):
        rows = []
        for i in range(feed.GROWTH_LEDGER_MAX + 50):
            rows = feed.growth_record(rows, (self.NOW - timedelta(days=30)).isoformat(), 1, 1)
        self.assertEqual(len(rows), feed.GROWTH_LEDGER_MAX)
        self.assertEqual(feed.growth_report(rows, self.NOW)["commits"], 0)

    def test_health_raises_feed_growth_and_the_commit_path_records_it(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / "s.sqlite3")
            store._put("feed_growth", {"ledger": [], "report": feed.growth_report(self.ledger(12, 1_000), self.NOW)})
            snap = health.snapshot(store, self.NOW)
            self.assertIn("feed_growth", [r["code"] for r in health.raw_reasons(snap, self.NOW, {"stall_hours": 3.0})])
            engine = Engine(store)
            manifest = {"revision": "r1", "coverage": {"events": 1, "guide_corroborated_broadcasts": 0}}
            with patch.object(Engine, "_github_commit", return_value="sha"):
                engine._commit_feed("o", "r", "main", "t", manifest, {"v1/assets/x/1.json": b"12345"},
                                    {"revisions": []}, "feed_state", "publisher", "label", private=False)
            saved = store._get("feed_growth")
            self.assertEqual(saved["ledger"][-1]["files"], 3)               # asset + two manifest copies
            self.assertGreaterEqual(saved["ledger"][-1]["bytes"], 5)
            self.assertIn("per_day", saved["report"])


class VersionToolTests(unittest.TestCase):
    def load_tool(self):
        spec = importlib.util.spec_from_file_location("bump_version", ROOT / "tools" / "bump_version.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_the_three_version_files_agree(self):
        tool = self.load_tool()
        versions = tool.read_versions(ROOT)
        self.assertTrue(tool.versions_agree(versions), versions)
        from sportsliveinfo import __version__
        self.assertEqual(versions["__init__.py"], __version__)
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")

    def copy_tree(self, target):
        for path in ("sportsliveinfo/config.yaml", "sportsliveinfo/Dockerfile", "sportsliveinfo/CHANGELOG.md",
                     "sportsliveinfo/src/sportsliveinfo/__init__.py"):
            destination = Path(target, path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(Path(ROOT, path).read_text(encoding="utf-8"), encoding="utf-8")

    def test_bump_updates_all_three_files_and_the_changelog_heading(self):
        tool = self.load_tool()
        with tempfile.TemporaryDirectory() as temp:
            self.copy_tree(temp)
            changed = tool.bump(temp, "9.8.7", "Test release")
            self.assertEqual(len(changed), 4)
            versions = tool.read_versions(temp)
            self.assertEqual(set(versions.values()), {"9.8.7"})
            log = Path(temp, "sportsliveinfo/CHANGELOG.md").read_text(encoding="utf-8")
            self.assertIn("## 9.8.7 — Test release", log)
            head = log.split("## 0.3.24")[0]
            self.assertNotIn("## Unreleased", head)               # nested under the release as ### topics
            self.assertIn("### Scores per source behind a rights flag", head)
            self.assertEqual(tool.bump(temp, "9.8.7"), [])        # idempotent
            self.assertEqual(tool.bump(temp, "9.8.8", dry_run=True)[:3], [
                "sportsliveinfo/config.yaml", "sportsliveinfo/Dockerfile", "sportsliveinfo/src/sportsliveinfo/__init__.py"])
            self.assertEqual(set(tool.read_versions(temp).values()), {"9.8.7"})      # dry run wrote nothing
            with self.assertRaises(ValueError):
                tool.bump(temp, "not-a-version")

    def test_disagreement_is_detected(self):
        tool = self.load_tool()
        with tempfile.TemporaryDirectory() as temp:
            self.copy_tree(temp)
            docker = Path(temp, "sportsliveinfo/Dockerfile")
            docker.write_text(re.sub(r"BUILD_VERSION=\S+", "BUILD_VERSION=0.0.1", docker.read_text()))
            self.assertFalse(tool.versions_agree(tool.read_versions(temp)))

    def test_check_mode_exit_codes(self):
        run = subprocess.run([sys.executable, str(ROOT / "tools" / "bump_version.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)


class DeadManWorkflowTests(unittest.TestCase):
    PATH = ROOT / "docs" / "examples" / "liveSports-epg-deadman.yml"

    def script(self):
        text = self.PATH.read_text(encoding="utf-8")
        body = text.split("# DEADMAN-SCRIPT-BEGIN\n")[1].split("# DEADMAN-SCRIPT-END")[0]
        return "\n".join(line[10:] if line.startswith(" " * 10) else line for line in body.split("\n"))

    def judge(self, manifest, now, **env):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp, "manifest.json")
            if manifest is not None:
                path.write_text(json.dumps(manifest), encoding="utf-8")
            code = Path(temp, "script.py")
            code.write_text(self.script(), encoding="utf-8")
            result = subprocess.run([sys.executable, "-I", str(code)], capture_output=True, text=True,
                                    env={"MANIFEST": str(path), "DEADMAN_NOW": now.isoformat(), "PATH": os.environ.get("PATH", ""), **env})
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def manifest(self, generated, slots=("04:00", "12:00", "17:00")):
        return {"generated_at": generated.isoformat(), "refresh": {"schedule_europe_london": list(slots)}}

    def test_the_workflow_is_valid_yaml_scheduled_every_30_minutes_and_installed_nowhere(self):
        text = self.PATH.read_text(encoding="utf-8")
        self.assertRegex(text, r'cron: "\d+,\d+ \* \* \* \*"')
        self.assertIn("issues: write", text)
        self.assertNotIn("contents: write", text)
        self.assertFalse(list((ROOT / ".github" / "workflows").glob("*dead*")))
        try:
            import yaml
        except ImportError:
            return
        data = yaml.safe_load(text)
        self.assertIn("deadman", data["jobs"])

    def test_the_20_november_stall_is_detected_and_not_before_the_grace(self):
        stale = self.manifest(datetime(2026, 11, 20, 3, 42, tzinfo=UTC))
        self.assertFalse(self.judge(stale, datetime(2026, 11, 20, 6, 59, tzinfo=UTC))["stale"])    # 04:00 slot is < 3 h old
        verdict = self.judge(stale, datetime(2026, 11, 20, 7, 1, tzinfo=UTC))
        self.assertTrue(verdict["stale"])
        self.assertIn("04:00", verdict["message"])

    def test_a_fresh_manifest_is_healthy_and_a_late_one_after_a_later_slot_is_not(self):
        self.assertFalse(self.judge(self.manifest(datetime(2026, 11, 20, 12, 5, tzinfo=UTC)),
                                    datetime(2026, 11, 20, 14, 0, tzinfo=UTC))["stale"])
        self.assertTrue(self.judge(self.manifest(datetime(2026, 11, 20, 12, 5, tzinfo=UTC)),
                                   datetime(2026, 11, 20, 20, 30, tzinfo=UTC))["stale"])         # 17:00 slot missed

    def test_london_summer_time_slots_are_judged_in_london_time(self):
        manifest = self.manifest(datetime(2026, 7, 1, 2, 30, tzinfo=UTC))           # 04:00 BST is 03:00 UTC
        self.assertTrue(self.judge(manifest, datetime(2026, 7, 1, 6, 30, tzinfo=UTC))["stale"])
        self.assertFalse(self.judge(manifest, datetime(2026, 7, 1, 5, 30, tzinfo=UTC))["stale"])

    def test_missing_or_broken_manifest_and_no_schedule(self):
        now = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
        self.assertTrue(self.judge(None, now)["stale"])
        self.assertTrue(self.judge({"nope": 1}, now)["stale"])
        no_schedule = {"generated_at": (now - timedelta(hours=31)).isoformat()}
        self.assertTrue(self.judge(no_schedule, now)["stale"])
        self.assertFalse(self.judge({"generated_at": (now - timedelta(hours=5)).isoformat()}, now)["stale"])


class CiWorkflowTests(unittest.TestCase):
    def test_verify_workflow_runs_the_new_gates(self):
        text = (ROOT / ".github" / "workflows" / "verify.yml").read_text(encoding="utf-8")
        for needle in ("generate_feed_fixtures.py", "git diff --exit-code", "schemas", "pyflakes", "bump_version.py --check",
                       "unittest discover"):
            self.assertIn(needle, text)

    def test_every_schema_file_is_json(self):
        files = sorted((ROOT / "schemas").glob("*.json"))
        self.assertGreaterEqual(len(files), 10)
        for path in files:
            json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
