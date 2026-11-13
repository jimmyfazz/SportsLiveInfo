"""Guide-listed live sport: private events for live listings no event source has (synthetic data only)."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sportsliveinfo import feed, linking
from sportsliveinfo.engine import Engine
from sportsliveinfo.storage import Store

UTC = timezone.utc
NOW = datetime(2026, 11, 14, 10, 0, tzinfo=UTC)
KICKOFF = datetime(2026, 11, 14, 15, 0, tzinfo=UTC)


def listing(channel_id, title, subtitle="", start=KICKOFF, hours=2, **extra):
    row = {"channel_id": channel_id, "start_utc": start.isoformat(), "end_utc": (start + timedelta(hours=hours)).isoformat(),
           "title": title, "subtitle": subtitle, "is_live": False, "is_repeat": False}
    row.update(extra)
    return row


def guide(source_id, channels, rows):
    return {"source_id": source_id, "channels": channels, "programmes": rows}


def run(guides, events=()):
    found = []
    result = linking.broadcast_candidates(list(events), guides, NOW, guide_events=found, gaps={})
    return result, found


class GuideListedEventTests(unittest.TestCase):
    def test_live_fixture_without_a_feed_event_becomes_a_private_event_with_its_channel(self):
        _, found = run({"farleyflex": guide("farleyflex", {"ss": "Sky Sports Football"},
                                            [listing("ss", "Live: Synthetic Cup", "North Harbor v Westshire")])})
        self.assertEqual(len(found), 1)
        event = found[0]
        self.assertEqual((event["title"], event["sport"], event["competition"]),
                         ("North Harbor v Westshire", "football", "Synthetic Cup"))
        self.assertEqual(event["participants"], ["North Harbor", "Westshire"])
        self.assertEqual((event["origin"], event["sources"]), ("guide_listing", ["guide_listing"]))
        self.assertEqual([c["canonical_channel_id"] for c in event["broadcast_candidates"]], ["gb.sky.sports.football"])
        self.assertFalse(event["broadcast_verified"])

    def test_not_live_repeats_and_non_sport_listings_are_ignored(self):
        rows = [listing("ss", "Synthetic Cup", "North Harbor v Westshire"),                      # not marked live
                listing("ss", "Live: Synthetic Cup", "Harbor v Eastvale", start=KICKOFF + timedelta(hours=3), is_repeat=True),
                listing("c4", "Live: Weekend Brunch")]                                         # live but not sport
        _, found = run({"farleyflex": guide("farleyflex", {"ss": "Sky Sports Football", "c4": "Channel 4"}, rows)})
        self.assertEqual(found, [])

    def test_a_broadcast_already_matched_to_a_feed_event_is_not_duplicated(self):
        event = {"id": "feed:1", "sport": "football", "title": "North Harbor v Westshire", "competition": "Synthetic Cup",
                 "participants": ["North Harbor", "Westshire"], "start_utc": KICKOFF.isoformat(),
                 "start_precision": "scheduled"}
        result, found = run({"farleyflex": guide("farleyflex", {"ss": "Sky Sports Football"},
                                                 [listing("ss", "Live: Synthetic Cup", "North Harbor v Westshire")])}, [event])
        self.assertIn("feed:1", result)
        self.assertEqual(found, [])

    def test_loosely_named_listing_attaches_its_channel_to_the_feed_event(self):
        event = {"id": "feed:2", "sport": "ice_hockey", "title": "Harbor Herons v New York Comets",
                 "participants": ["Harbor Herons", "New York Comets"], "start_utc": KICKOFF.isoformat(),
                 "start_precision": "scheduled"}
        result, found = run({"farleyflex": guide("farleyflex", {"p2": "Premier Sports 2"},
                                                 [listing("p2", "Live NHL Ice Hockey", "NY Comets at Harbor")])}, [event])
        self.assertEqual(result["feed:2"][0], "guide_listing_match")
        self.assertEqual(result["feed:2"][1][0]["canonical_channel_id"], "gb.premier.sports.2")
        self.assertEqual(found, [])

    def test_the_same_broadcast_in_several_guides_and_channels_is_one_event(self):
        guides = {
            "farleyflex": guide("farleyflex", {"me": "Sky Sports Main Event", "gf": "Sky Sports Golf"}, [
                listing("me", "Live Synthetic Tour Golf", "2026 Synthetic Championship Day 3"),
                listing("gf", "Live Synthetic Tour Golf", "2026 Synthetic Championship Day 3")]),
            "epgtalk_uk": guide("epgtalk_uk", {"gf": "Sky Sports Golf"}, [
                listing("gf", "Live: Golf [NEW]", "Synthetic Championship: Day 3")]),
        }
        _, found = run(guides)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["sport"], "golf")
        self.assertEqual(sorted(c["canonical_channel_id"] for c in found[0]["broadcast_candidates"]),
                         ["gb.sky.sports.golf", "gb.sky.sports.main_event"])
        self.assertEqual(found[0]["epg_sources"], ["epgtalk_uk", "farleyflex"])

    def test_north_american_at_listings_and_v_listings_merge(self):
        guides = {"farleyflex": guide("farleyflex", {"a": "Sky Sports Action"},
                                      [listing("a", "Live NFL", "Harbor Herons v Westshire Wolves")]),
                  "epgtalk_uk": guide("epgtalk_uk", {"a": "Sky Sports Action"},
                                      [listing("a", "Live: NFL Football", "Westshire  Wolves at Harbor  Herons")])}
        _, found = run(guides)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["sport"], "american_football")
        # "at" is not a fixture separator outside North American sports.
        title, _, participants = linking._guide_listing("Live Racing", "Racing at Westshire", "horse_racing")
        self.assertEqual(participants, [])

    def test_sport_comes_from_the_listing_and_misc_sports_are_not_football(self):
        self.assertEqual(linking._guide_sport("live women s alpine skiing world cup", "TNT Sports 1"), "other")
        self.assertEqual(linking._guide_sport("live gaa beo munster club hurling championship", "TG4"), "other")
        self.assertEqual(linking._guide_sport("live grand slam of darts day 1", "Sky Sports Main Event"), "darts")
        self.assertEqual(linking._guide_sport("live 2026 synthetic open", "Sky Sports Golf"), "golf")

    def test_display_titles_drop_dates_tags_and_repeated_titles(self):
        self.assertEqual(linking._guide_listing("Live Synthetic Racing", "14/11/2026")[0], "Synthetic Racing")
        self.assertEqual(linking._guide_listing("Live Darts", "Darts Masters D1 S1")[0], "Darts Masters D1 S1")
        self.assertEqual(linking._guide_listing("Live Tennis", "Synthetic Finals Day 2")[0], "Synthetic Finals Day 2")
        self.assertEqual(linking._guide_listing("Live: Synthetic Open Badminton", "Finals")[0],
                         "Synthetic Open Badminton: Finals")
        self.assertEqual(linking._guide_listing("[LIVE]: [Cycling] Synthetic Criterium", "")[0], "Synthetic Criterium")

    def test_regional_allocation_applies_to_guide_listed_events(self):
        # A general channel needs a sport word in the listing ("Nations League"); a sports channel does not.
        rows = [listing("one", "Evening Magazine"), listing("wal", "Live: Nations League", "Westshire v North Harbor")]
        _, found = run({"uk_freeview": guide("uk_freeview", {"one": "BBC One HD", "wal": "BBC One Wales HD"}, rows)})
        self.assertEqual([(c["canonical_channel_id"], c["coverage"]) for c in found[0]["broadcast_candidates"]],
                         [("gb.bbc.one.wales", "regional")])

    def test_womens_and_mens_fixtures_between_the_same_teams_stay_separate(self):
        rows = [listing("p1", "Live Women's Rugby League World Cup", "Westshire v North Harbor"),
                listing("p1", "Live Men's Rugby League World Cup", "Westshire v North Harbor",
                        start=KICKOFF + timedelta(hours=3, minutes=30))]
        _, found = run({"farleyflex": guide("farleyflex", {"p1": "Premier Sports 1"}, rows)})
        self.assertEqual(len(found), 2)
        self.assertEqual({e["sport"] for e in found}, {"rugby_league"})


class GuideListedPrivacyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "state.sqlite3")

    def tearDown(self):
        self.temp.cleanup()

    def test_engine_keeps_guide_listed_events_locally_and_the_feed_never_publishes_them(self):
        # "guide_listing" cannot even be approved for publication (the config store rejects it).
        with self.assertRaises(ValueError):
            self.store.configure({"publication_approvals": ["guide_listing"]})
        self.store.configure({"setup_complete": True, "sports": {}, "epg": {"farleyflex": True}})
        self.store.save_snapshot("epg:farleyflex", guide("farleyflex", {"ss": "Sky Sports Football"},
                                                         [listing("ss", "Live: Synthetic Cup", "North Harbor v Westshire")]))
        Engine(self.store)._materialize(now=NOW)
        events = self.store.snapshot("sports")["data"]["events"]
        self.assertEqual([(e["title"], e["origin"], e["category_id"]) for e in events],
                         [("North Harbor v Westshire", "guide_listing", "football.other")])
        manifest, files = feed.build_feed(self.store, now=NOW)
        self.assertEqual(manifest["coverage"]["events"], 0)
        self.assertNotIn("guide_listing", manifest["rights"]["events"]["omitted_unapproved_sources"])
        self.assertFalse(any(b"North Harbor" in data for data in files.values()))


if __name__ == "__main__":
    unittest.main()
