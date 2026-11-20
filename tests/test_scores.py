"""sli/1.7 scores: per-source rights flag (default off), decoders, alignment to participants order, publication in the
day and live assets, the kill switch, byte-identical output when disabled, live republish on a score change and the
final score from the settle pass."""
import json
import unittest
import urllib.parse
import urllib.request
from contextlib import closing
from datetime import timedelta
from unittest.mock import patch

import test_live_tiers_corroboration as live
from test_live_tiers_corroboration import NOW, StoreCase, ev, iso
from ingress_test_support import IngressTestClient
from sportsliveinfo import feed, linking, providers
from sportsliveinfo.engine import Engine
from test_feed import fixtures_tool, load_schema, validate

Z = lambda moment: iso(moment).replace("+00:00", "Z")


# ---- decoders --------------------------------------------------------------------------------------------------
def football_row(fid, short, home=None, away=None, **extra):
    return dict({"fixture": {"id": fid, "date": "2026-11-14T15:00:00+00:00", "status": {"short": short}},
                 "teams": {"home": {"name": "Arsenal"}, "away": {"name": "Chelsea"}},
                 "league": {"id": 39, "name": "Premier League"}, "goals": {"home": home, "away": away}}, **extra)


def football(*rows):
    return json.dumps({"errors": [], "paging": {"current": 1, "total": 1}, "response": list(rows)}).encode()


def games(source, row):
    base = {"id": 7, "timestamp": int(NOW.timestamp()), "teams": {"home": {"name": "A"}, "away": {"name": "B"}},
            "league": {"id": 1, "name": "L"}}
    base.update(row)
    event, = providers.api_sports_games_events(json.dumps({"errors": [], "response": [base]}), source_id=source,
                                               sport=providers.API_SPORTS_SPORT[source])
    return event


class DecoderTests(unittest.TestCase):
    def one(self, *rows):
        return providers.api_sports_events(football(*rows))[0]

    def test_football_live_and_final_scores_with_periods(self):
        for short, period in (("1H", "1H"), ("HT", "HT"), ("2H", "2H"), ("ET", "ET"), ("P", "PEN"), ("BT", None),
                              ("LIVE", None), ("FT", "FT"), ("AET", "AET"), ("PEN", "PEN")):
            event = self.one(football_row(1, short, 2, 1))
            self.assertEqual(event["score"], {"home": 2, "away": 1, "period": period}, short)

    def test_football_no_score_when_not_certain(self):
        for short, home, away in (("NS", None, None), ("FT", None, 1), ("2H", 1, None), ("PST", 0, 0), ("CANC", None, None),
                                  ("ABD", 1, 0), ("AWD", 3, 0), ("WO", 3, 0), ("TBD", None, None), ("1H", -1, 0),
                                  ("1H", True, 0), ("1H", 1.5, 0)):
            self.assertNotIn("score", self.one(football_row(1, short, home, away)), (short, home, away))
        self.assertEqual(self.one(football_row(1, "1H", 0, 0))["score"]["home"], 0)      # 0-0 is a score, null is not
        self.assertNotIn("score", self.one({"fixture": {"id": 2, "date": "2026-11-14T15:00:00+00:00",
                                                       "status": {"short": "2H"}}, "teams": {}, "league": {}}))

    def test_games_products(self):
        cases = [
            ("api_sports_rugby", {"status": {"short": "2H"}, "scores": {"home": 17, "away": 10}}, (17, 10, "2H")),
            ("api_sports_rugby", {"status": {"short": "AET"}, "scores": {"home": 20, "away": 20}}, (20, 20, "AET")),
            ("api_sports_basketball", {"status": {"short": "Q3"}, "scores": {
                "home": {"quarter_1": 20, "total": 71}, "away": {"quarter_1": 22, "total": 68}}}, (71, 68, "Q3")),
            ("api_sports_basketball", {"status": {"short": "AOT"}, "scores": {
                "home": {"total": 120}, "away": {"total": 118}}}, (120, 118, "AET")),
            ("api_sports_hockey", {"status": {"short": "P2"}, "scores": {"home": 2, "away": 1}}, (2, 1, "P2")),
            ("api_sports_hockey", {"status": {"short": "AP"}, "scores": {"home": 3, "away": 2}}, (3, 2, "PEN")),
            ("api_sports_nfl", {"game": {"status": {"short": "Q4"}}, "scores": {
                "home": {"total": 21}, "away": {"total": 17}}}, (21, 17, "Q4")),
            ("api_sports_baseball", {"status": {"short": "IN5"}, "scores": {
                "home": {"hits": 4, "innings": {"1": 0}, "total": 3}, "away": {"total": 2}}}, (3, 2, None)),
            ("api_sports_handball", {"status": {"short": "FT"}, "scores": {"home": 30, "away": 28}}, (30, 28, "FT")),
            ("api_sports_volleyball", {"status": {"short": "S4"}, "scores": {"home": 2, "away": 1}}, (2, 1, None)),
            ("api_sports_afl", {"status": {"short": "Q2"}, "scores": {
                "home": {"goals": 5, "behinds": 3, "score": 33}, "away": {"score": 40}}}, (33, 40, "Q2")),
        ]
        for source, row, (home, away, period) in cases:
            row = dict(row)
            if source == "api_sports_nfl":
                row["game"] = dict(row["game"], id=7, date={"timestamp": int(NOW.timestamp())})
            event = games(source, row)
            self.assertEqual(event.get("score"), {"home": home, "away": away, "period": period}, (source, row))
        self.assertNotIn("score", games("api_sports_rugby", {"status": {"short": "NS"}, "scores": {"home": None, "away": None}}))
        self.assertNotIn("score", games("api_sports_rugby", {"status": {"short": "2H"}}))

    def test_mma_decoder_carries_no_score(self):
        row = {"id": 1, "timestamp": int(NOW.timestamp()), "status": {"short": "IN"}, "fighters": {
            "first": {"name": "A"}, "second": {"name": "B"}}, "scores": {"home": 1, "away": 0}}
        event, = providers.api_sports_mma_events(json.dumps({"errors": [], "response": [row]}))
        self.assertNotIn("score", event)

    def test_football_data_finals_only_and_regular_time_only(self):
        def match(status, duration, home=2, away=1, mid=1):
            return {"id": mid, "utcDate": "2026-11-14T15:00:00Z", "status": status, "homeTeam": {"name": "A"},
                    "awayTeam": {"name": "B"}, "competition": {"name": "L", "code": "PL"},
                    "score": {"duration": duration, "fullTime": {"home": home, "away": away}}}
        payload = json.dumps({"matches": [
            match("FINISHED", "REGULAR", mid=1), match("IN_PLAY", "REGULAR", mid=2), match("FINISHED", "EXTRA_TIME", mid=3),
            match("FINISHED", "PENALTY_SHOOTOUT", mid=4), match("FINISHED", "REGULAR", None, None, mid=5),
            match("TIMED", "REGULAR", mid=6)]})
        scores = {e["id"]: e.get("score") for e in providers.football_data_events(payload)}
        self.assertEqual(scores, {"football-data:1": {"home": 2, "away": 1, "period": "FT"}, "football-data:2": None,
                                  "football-data:3": None, "football-data:4": None, "football-data:5": None,
                                  "football-data:6": None})

    def test_eligibility_table(self):
        for never in ("thesportsdb", "jolpica", "openf1", "api_sports_mma", "cricketdata", "pandascore"):
            self.assertNotIn(never, providers.SCORE_ELIGIBLE)
        self.assertEqual(providers.SCORE_ELIGIBLE["football_data"], "final")
        for excluded in ("tennis", "cricket", "golf", "motorsport", "boxing", "mma"):
            self.assertNotIn(excluded, providers.SCORE_SPORTS)


# ---- alignment ---------------------------------------------------------------------------------------------------
def row(source, sid, participants, score=None, status="finished", observed="2026-11-14T17:00:00+00:00", sport="football",
        start="2026-11-14T15:00:00+00:00"):
    out = ev(id=sid, source_id=source, sport=sport, participants=participants, title=" v ".join(participants),
             start_utc=start, status_normalized=status, status_observed_at=observed)
    if score:
        out["score"] = score
    return out


class AlignmentTests(unittest.TestCase):
    def merge(self, *rows):
        merged = linking.merge_events(list(rows))
        self.assertEqual(len(merged), 1)
        return merged[0]

    def test_swapped_contributor_is_re_expressed_in_the_primary_order(self):
        primary = row("football_data", "football-data:1", ["Tottenham Hotspur FC", "Chelsea FC"])
        other = row("api_sports", "api-sports:1", ["Chelsea", "Tottenham Hotspur"], {"home": 2, "away": 1, "period": "FT"})
        merged = self.merge(primary, other)
        self.assertEqual(merged["participants"], ["Tottenham Hotspur FC", "Chelsea FC"])
        self.assertEqual((merged["scores"]["api-sports:1"]["home"], merged["scores"]["api-sports:1"]["away"]), (1, 2))
        self.assertEqual(merged["score_align"], {"football-data:1": 1, "api-sports:1": -1})
        self.assertNotIn("score", merged)

    def test_same_order_is_kept_and_primary_own_score_is_aligned_to_itself(self):
        primary = row("football_data", "football-data:1", ["Arsenal FC", "Chelsea FC"], {"home": 3, "away": 0, "period": "FT"})
        other = row("api_sports", "api-sports:1", ["Arsenal", "Chelsea"], {"home": 3, "away": 0, "period": "FT"})
        merged = self.merge(primary, other)
        self.assertEqual({k: (v["home"], v["away"]) for k, v in merged["scores"].items()},
                         {"football-data:1": (3, 0), "api-sports:1": (3, 0)})
        self.assertEqual(merged["score_align"], {"football-data:1": 1, "api-sports:1": 1})

    def test_us_away_at_home_title_order_follows_participants_not_roles(self):
        # A source that lists the visitor first ("Away @ Home") is simply another order of the same two names.
        primary = row("api_sports", "api-sports:1", ["Boston Celtics", "Los Angeles Lakers"])          # preferred source
        other = row("api_sports_basketball", "api-sports-basketball:1", ["Los Angeles Lakers", "Boston Celtics"],
                    {"home": 99, "away": 104, "period": "FT"}, sport="basketball")
        primary["sport"] = "basketball"
        merged = self.merge(primary, other)
        mine = merged["scores"]["api-sports-basketball:1"]
        self.assertEqual(merged["participants"][0], "Boston Celtics")
        self.assertEqual((mine["home"], mine["away"]), (104, 99))               # Celtics (participants[0]) scored 104

    def test_uncertain_pairing_emits_nothing(self):
        # Two sides whose names reduce to the same key make both orders plausible: no alignment, no score.
        primary = row("football_data", "football-data:1", ["Manchester FC", "Manchester FC"])
        other = row("api_sports", "api-sports:1", ["Manchester", "Manchester"], {"home": 1, "away": 0, "period": "FT"})
        merged = self.merge(primary, other)
        self.assertNotIn("scores", merged)
        self.assertEqual(merged["score_align"], {"football-data:1": 1})
        # Fewer than two participants: no alignment either.
        solo = row("football_data", "football-data:2", ["Only"], None)
        two = row("api_sports", "api-sports:2", ["Only"], {"home": 1, "away": 0, "period": "FT"})
        merged = linking.merge_events([solo, two])
        self.assertTrue(all("scores" not in event for event in merged))

    def test_single_source_event_has_no_alignment_clutter(self):
        merged = self.merge(row("api_sports", "api-sports:1", ["Arsenal", "Chelsea"], {"home": 1, "away": 0, "period": "FT"}))
        self.assertNotIn("score_align", merged)
        self.assertEqual(merged["scores"]["api-sports:1"]["source"], "api_sports")


# ---- feed ------------------------------------------------------------------------------------------------------
def seed(store, events_by_source, **config):
    store.configure(dict({"setup_complete": True, "sports": {name: True for name in events_by_source} | {"jolpica": False},
                          "publication_approvals": sorted(events_by_source)}, **config))
    for name, events in events_by_source.items():
        store.save_snapshot("sports:" + name, {"events": events})
    Engine(store)._materialize(now=NOW)


def day_events(manifest_files, manifest):
    out = {}
    for asset in manifest["assets"]:
        if asset["kind"].split(":")[0] in ("events", "events_extra"):
            for event in json.loads(manifest_files[asset["path"]])["events"]:
                out[event["id"]] = event
    return out


def live_rows(files, manifest):
    for asset in manifest["assets"]:
        if asset["kind"] == "live":
            return {r["id"]: r for r in json.loads(files[asset["path"]])["events"]}
    return {}


class FeedScoreTests(StoreCase):
    def final_events(self):
        return {"football_data": [row("football_data", "football-data:1", ["Tottenham Hotspur FC", "Chelsea FC"],
                                      {"home": 1, "away": 2, "period": "FT"})],
                "api_sports": [row("api_sports", "api-sports:1", ["Chelsea", "Tottenham Hotspur"],
                                   {"home": 2, "away": 1, "period": "FT"})]}

    def build(self):
        return feed.build_feed(self.store, now=NOW)

    def test_disabled_by_default_no_field_same_revision_and_still_sli_1_6(self):
        seed(self.store, self.final_events())
        manifest, files = self.build()
        stripped = {n: [{k: v for k, v in e.items() if k != "score"} for e in rows] for n, rows in self.final_events().items()}
        import tempfile
        from pathlib import Path
        from sportsliveinfo.storage import Store
        with tempfile.TemporaryDirectory() as tmp:
            bare = Store(Path(tmp) / "b.sqlite3")
            seed(bare, stripped)
            bare_manifest, bare_files = feed.build_feed(bare, now=NOW)
        self.assertEqual(manifest["revision"], bare_manifest["revision"])
        self.assertEqual(files, bare_files)
        self.assertEqual(feed._json(manifest), feed._json(bare_manifest))
        self.assertEqual((manifest["format"], manifest["format_minor"]), ("sli/1.6", 6))
        self.assertNotIn("scores", manifest["capabilities"])
        self.assertNotIn("scores", manifest["compatibility"])
        self.assertNotIn("scores", manifest["rights"])
        self.assertTrue(all("score" not in e for e in day_events(files, manifest).values()))

    def test_golden_fixture_without_scores_is_untouched(self):
        manifest, _ = fixtures_tool.build()
        self.assertEqual(manifest["format"], "sli/1.6")
        self.assertNotIn("scores", manifest["compatibility"])

    def test_enabled_publishes_aligned_final_score_and_declares_the_capability(self):
        seed(self.store, self.final_events(), score_approvals=["api_sports", "football_data"])
        manifest, files = self.build()
        self.assertEqual((manifest["format"], manifest["format_minor"]), ("sli/1.7", 7))
        self.assertEqual(manifest["compatibility"]["min_reader_minor"], 0)
        self.assertIn("scores", manifest["capabilities"])
        self.assertTrue(manifest["compatibility"]["scores"]["enabled"])
        self.assertEqual(manifest["rights"]["scores"], {"approved_sources": ["api_sports", "football_data"]})
        event, = day_events(files, manifest).values()
        self.assertEqual(event["participants"], ["Tottenham Hotspur FC", "Chelsea FC"])
        self.assertEqual({k: event["score"][k] for k in ("home", "away", "period")}, {"home": 1, "away": 2, "period": "FT"})
        self.assertIn(event["score"]["source"], ("api_sports", "football_data"))
        for asset in manifest["assets"]:
            if asset["kind"].startswith("events:"):
                schema = load_schema("sli.events-day/1")
                validate(json.loads(files[asset["path"]]), schema, schema)
        schema = load_schema("sli.manifest/1")
        validate(manifest, schema, schema)

    def test_enabling_changes_the_revision_and_removing_approvals_is_the_kill_switch(self):
        seed(self.store, self.final_events())
        off_manifest, off_files = self.build()
        self.store.configure({"score_approvals": ["api_sports"]})
        on_manifest, _ = self.build()
        self.assertNotEqual(on_manifest["revision"], off_manifest["revision"])
        self.store.configure({"score_approvals": []})
        again_manifest, again_files = self.build()
        self.assertEqual(again_manifest["revision"], off_manifest["revision"])
        self.assertEqual(again_files, off_files)
        self.assertNotIn("scores", again_manifest["compatibility"])

    def test_only_approved_sources_publish_and_disagreeing_finals_publish_nothing(self):
        events = self.final_events()
        seed(self.store, events, score_approvals=["football_data"])
        manifest, files = self.build()
        event, = day_events(files, manifest).values()
        self.assertEqual(event["score"]["source"], "football_data")
        # Both approved but the two sources disagree about the final: uncertain, so no score.
        events["api_sports"][0]["score"] = {"home": 0, "away": 3, "period": "FT"}
        seed(self.store, events, score_approvals=["football_data", "api_sports"])
        manifest, files = self.build()
        self.assertNotIn("score", next(iter(day_events(files, manifest).values())))
        # An approved source that is not publication-approved never reaches the public feed at all.
        self.store.configure({"publication_approvals": ["api_sports"], "score_approvals": ["football_data"]})
        Engine(self.store)._materialize(now=NOW)
        manifest, files = self.build()
        self.assertTrue(all("score" not in e for e in day_events(files, manifest).values()))

    def test_not_started_and_live_events_carry_no_score_in_day_assets(self):
        events = {"api_sports": [
            row("api_sports", "api-sports:1", ["Arsenal", "Chelsea"], status="scheduled", start="2026-11-14T19:00:00+00:00"),
            row("api_sports", "api-sports:2", ["Leeds United", "Hull City"], {"home": 1, "away": 0, "period": "2H"},
                status="live", observed="2026-11-14T15:25:00+00:00")]}
        seed(self.store, events, score_approvals=["api_sports"])
        manifest, files = self.build()
        self.assertTrue(all("score" not in e for e in day_events(files, manifest).values()))

    def test_excluded_sports_never_carry_a_score(self):
        for sport in ("tennis", "cricket", "golf", "motorsport", "boxing", "mma"):
            event = row("api_sports", "api-sports:1", ["A One", "B Two"], {"home": 1, "away": 0, "period": "FT"}, sport=sport)
            self.assertIsNone(feed.published_score(event, [{"home": 1, "away": 0, "period": "FT", "source": "api_sports",
                                                            "observed_at": "2026-11-14T17:00:00Z", "status": "finished"}],
                                                   frozenset({"api_sports"}), "finished", final_only=True), sport)
        self.assertIsNotNone(feed.published_score(
            {"sport": "football", "participants": ["A", "B"]}, [{"home": 1, "away": 0, "period": "FT", "source": "api_sports",
                                                                "observed_at": "2026-11-14T17:00:00Z", "status": "finished"}],
            frozenset({"api_sports"}), "finished", final_only=True))
        # Unknown period values are published as null, never passed through.
        score = feed.published_score(
            {"sport": "football", "participants": ["A", "B"]}, [{"home": 1, "away": 0, "period": "XX", "source": "api_sports",
                                                                "observed_at": "2026-11-14T17:00:00Z", "status": "finished"}],
            frozenset({"api_sports"}), "finished", final_only=True)
        self.assertIsNone(score["period"])

    def test_score_approvals_validation_rejects_ineligible_sources(self):
        for bad in ("thesportsdb", "jolpica", "openf1", "api_sports_mma", "nope"):
            with self.assertRaises(ValueError):
                self.store.configure({"score_approvals": [bad]})
        self.assertEqual(self.store.config()["score_approvals"], [])
        self.store.configure({"score_approvals": ["api_sports", "football_data"]})
        # An ineligible name that slipped into saved config is still ignored by the feed.
        self.assertEqual(feed.score_approvals({"score_approvals": ["thesportsdb", "api_sports"]}), frozenset({"api_sports"}))

    def test_golden_scores_variant_matches_code(self):
        manifest, files = fixtures_tool.build(scores=True)
        root = fixtures_tool.SCORES_OUT
        self.assertEqual(feed._json(manifest), (root / "v1" / "manifest.json").read_bytes())
        for path, data in files.items():
            self.assertEqual(data, (root / path).read_bytes(), path)
        self.assertEqual(manifest["format"], "sli/1.7")
        for asset in manifest["assets"]:
            if asset["kind"] == "live":
                schema = load_schema("sli.live/1")
                validate(json.loads(files[asset["path"]]), schema, schema)
        scored = {e["id"]: e["score"] for e in day_events(files, manifest).values() if "score" in e}
        self.assertEqual(list(scored), ["football-data:5008"])
        self.assertEqual(live_rows(files, manifest)["api-sports-rugby:301"]["score"]["period"], "2H")


# ---- live lane and settle pass -----------------------------------------------------------------------------------
class LaneScoreTests(live.LiveLaneBase):
    def setUp(self):
        super().setUp()
        self.store.configure({"score_approvals": ["api_sports"]})

    def board(self, status, home, away):
        return football(football_row(1, status, home, away))

    def obs(self):
        return self.store._get("live_observations")["events"]["api-sports:1"]

    def test_score_is_stored_and_a_changed_score_republishes_but_an_unchanged_one_does_not(self):
        self.snapshot()
        self.assertEqual(self.run_lane(self.board("1H", 0, 0)), 1)
        self.assertEqual(self.obs()["score"], {"home": 0, "away": 0, "period": "1H"})
        # Same status, same score, 15 minutes later: nothing new (no extra commit).
        self.assertEqual(self.run_lane(self.board("1H", 0, 0), now=NOW + timedelta(minutes=15)), 0)
        # A goal: same status but a new observation, so the live asset is republished.
        self.assertEqual(self.run_lane(self.board("1H", 1, 0), now=NOW + timedelta(minutes=16)), 1)
        self.assertEqual(self.obs()["score"], {"home": 1, "away": 0, "period": "1H"})
        self.assertEqual(self.obs()["status_observed_at"], iso(NOW + timedelta(minutes=16)))
        # A period change with the same goals is also news.
        self.assertEqual(self.run_lane(self.board("HT", 1, 0), now=NOW + timedelta(minutes=17)), 1)
        # Left the board: status unknown, the score is not carried.
        self.assertEqual(self.run_lane(football(), now=NOW + timedelta(minutes=40)), 1)
        self.assertNotIn("score", self.obs())

    def test_live_asset_row_carries_the_score_only_when_approved(self):
        self.snapshot()
        self.run_lane(self.board("2H", 2, 1))
        events = self.store.snapshot("sports-public")["data"]["events"]
        with patch("sportsliveinfo.feed.datetime", live.FixedClock):
            doc = feed.live_document(self.store, events, now=NOW)
        score = doc["events"][0]["score"]
        self.assertEqual({k: score[k] for k in ("home", "away", "period", "source")},
                         {"home": 2, "away": 1, "period": "2H", "source": "api_sports"})
        self.assertEqual(score["observed_at"], Z(NOW))
        self.store.configure({"score_approvals": []})
        with patch("sportsliveinfo.feed.datetime", live.FixedClock):
            doc = feed.live_document(self.store, events, now=NOW)
        self.assertNotIn("score", doc["events"][0])

    def test_disabled_lane_stores_no_score_and_ignores_score_only_changes(self):
        self.store.configure({"score_approvals": []})
        self.snapshot()
        self.assertEqual(self.run_lane(self.board("1H", 0, 0)), 1)
        self.assertNotIn("score", self.obs())
        self.assertEqual(self.run_lane(self.board("1H", 1, 0), now=NOW + timedelta(minutes=15)), 0)

    def test_older_score_is_not_published_with_a_newer_status(self):
        self.snapshot()
        self.run_lane(self.board("1H", 1, 0))
        # A newer observation without a score (for example read from a source that gave none) hides the older score.
        later = NOW + timedelta(minutes=20)
        self.store._put("live_observations", {"events": {"api-sports:1": {
            "status": "2H", "status_normalized": "live", "status_observed_at": iso(later)}}})
        events = self.store.snapshot("sports-public")["data"]["events"]
        with patch("sportsliveinfo.feed.datetime", live.FixedClock):
            doc = feed.live_document(self.store, events, now=later)
        self.assertNotIn("score", doc["events"][0])

    def test_swapped_second_source_live_score_is_aligned(self):
        # football-data is the primary (first in SOURCE_PREFERENCE) and lists the sides the other way round.
        self.store.configure({"sports": {"football_data": True}, "publication_approvals": ["api_sports", "football_data"]})
        self.store.save_snapshot("sports:football_data", {"events": [
            ev(id="football-data:9", source_id="football_data", participants=["Chelsea FC", "Arsenal FC"],
               title="Chelsea FC v Arsenal FC", start_utc="2026-11-14T15:00:00+00:00", status="TIMED",
               status_normalized="scheduled", status_observed_at="2026-11-14T12:00:00+00:00",
               competition="Premier League", competition_country="England")]})
        self.snapshot()
        events = self.store.snapshot("sports-public")["data"]["events"]
        self.assertEqual(events[0]["participants"], ["Chelsea FC", "Arsenal FC"])
        self.run_lane(self.board("2H", 2, 1))                # API-Sports: Arsenal (home) 2, Chelsea 1
        with patch("sportsliveinfo.feed.datetime", live.FixedClock):
            doc = feed.live_document(self.store, events, now=NOW)
        row_, = doc["events"]
        self.assertEqual((row_["score"]["home"], row_["score"]["away"]), (1, 2))      # participants[0] is Chelsea


class SettleScoreTests(live.LiveLaneBase):
    def setUp(self):
        super().setUp()
        self.store.configure({"score_approvals": ["api_sports"]})

    def settle(self, payload, now):
        with patch("sportsliveinfo.providers.fetch", side_effect=lambda url, headers=None, max_bytes=0, response_headers=None: payload):
            return self.engine.settle_pass(now=now)

    def test_final_score_is_stored_with_the_final_status_and_published_in_the_live_asset(self):
        self.snapshot()
        later = NOW + timedelta(minutes=150)
        self.assertEqual(self.settle(football(football_row(1, "FT", 3, 1)), later), 1)
        stored = self.store._get("live_observations")["events"]["api-sports:1"]
        self.assertEqual((stored["status_normalized"], stored["score"]), ("finished", {"home": 3, "away": 1, "period": "FT"}))
        events = self.store.snapshot("sports-public")["data"]["events"]
        with patch("sportsliveinfo.feed.datetime", live.FixedClock):
            doc = feed.live_document(self.store, events, now=later)
        self.assertEqual(doc["events"][0]["status_normalized"], "finished")
        self.assertEqual((doc["events"][0]["score"]["home"], doc["events"][0]["score"]["away"]), (3, 1))
        self.assertNotIn("live_until_utc", doc["events"][0])

    def test_postponed_and_awarded_never_get_a_score(self):
        for code in ("PST", "AWD"):
            self.store._put("live_observations", None)
            self.store._put("settle_last:api_sports", "")
            self.snapshot()
            self.settle(football(football_row(1, code, 3, 0)), NOW + timedelta(minutes=150))
            self.assertNotIn("score", self.store._get("live_observations")["events"].get("api-sports:1", {}), code)

    def test_disabled_settle_stores_no_score(self):
        self.store.configure({"score_approvals": []})
        self.snapshot()
        self.assertEqual(self.settle(football(football_row(1, "FT", 3, 1)), NOW + timedelta(minutes=150)), 1)
        self.assertNotIn("score", self.store._get("live_observations")["events"]["api-sports:1"])

    def test_materialisation_folds_the_final_score_into_the_day_asset(self):
        self.snapshot()
        later = NOW + timedelta(minutes=150)
        self.settle(football(football_row(1, "FT", 3, 1)), later)
        self.engine._materialize(now=later)
        manifest, files = feed.build_feed(self.store, now=later)
        event, = day_events(files, manifest).values()
        self.assertEqual(event["status_normalized"], "finished")
        self.assertEqual((event["score"]["home"], event["score"]["away"], event["score"]["period"]), (3, 1, "FT"))


class IngressTests(StoreCase):
    def post(self, client, **fields):
        body = urllib.parse.urlencode(dict({"csrf": "c", "action": "score_approvals"}, **fields), doseq=True).encode()
        return client.open(urllib.request.Request(client.base, body, method="POST"))

    def test_score_approvals_form_requires_attestation_and_rejects_ineligible_sources(self):
        self.store.configure({"setup_complete": True})
        with closing(IngressTestClient(self.store, "c")) as client:
            with client.open(client.base + "?page=publishing") as response:
                page = response.read().decode()
            self.assertIn("Score approvals", page)
            self.assertIn("none (no score is published)", page)
            try:
                self.post(client, approve_score=["api_sports"]).read()          # no attestation: refused
            except Exception:
                pass
            self.assertEqual(self.store.config()["score_approvals"], [])
            self.post(client, approve_score=["api_sports", "thesportsdb"], attest_scores="on").read()
            self.assertEqual(self.store.config()["score_approvals"], ["api_sports"])     # ineligible ids are dropped
            self.post(client).read()                                                        # withdraw all
            self.assertEqual(self.store.config()["score_approvals"], [])
            with client.open(client.base + "?page=scheduler") as response:
                self.assertNotIn("No scores are kept", response.read().decode())


if __name__ == "__main__":
    unittest.main()
