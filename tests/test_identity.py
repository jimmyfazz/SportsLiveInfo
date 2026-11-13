"""Channel identity across guides by schedule fingerprints (sli.identity/1)."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sportsliveinfo import feed, identity
from sportsliveinfo.engine import Engine
from sportsliveinfo.server import UI
from sportsliveinfo.storage import Store

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
TITLES = ["Antiques Roadshow Special", "Countryfile Autumn Diaries", "Gardeners World Weekend", "Pointless Celebrities",
          "Strictly Come Dancing Results", "Match Of The Day Review", "Doctor Who Christmas Preview", "Question Time Debate",
          "Panorama Investigation Tonight", "Springwatch Highlights Programme", "Mastermind Grand Final", "Bargain Hunt Auction"]


def schedule(channel, titles=TITLES, offset=0, start=NOW):
    rows = []
    for i, title in enumerate(titles):
        begin = start + timedelta(hours=i, minutes=offset)
        rows.append({"channel_id": channel, "title": title, "start_utc": begin.isoformat(),
                     "end_utc": (begin + timedelta(minutes=55)).isoformat()})
    return rows


def guide(channels, programmes):
    return {"channels": channels, "programmes": programmes}


def resolve(guides):
    start, end = NOW - timedelta(hours=1), NOW + timedelta(hours=identity.WINDOW_HOURS)
    return identity.resolve({name: identity.fingerprint_guide(name, g, start, end) for name, g in guides.items()})


def cluster_of(document, source, channel):
    for row in document["channels"]:
        if {"source_id": source, "channel_id": channel} in row["members"]:
            return row
    return None


class IdentityTests(unittest.TestCase):
    def test_same_service_with_different_names_and_ids_is_linked_to_curated_identity(self):
        doc, report = resolve({
            "farleyflex": guide({"skysportsmainevent.uk": "Sky Sports Main Event"}, schedule("skysportsmainevent.uk")),
            "epgtalk_uk": guide({"SkySpMainEvHD.uk": "UK - Sky Sports Main Event HD"}, schedule("SkySpMainEvHD.uk")),
        })
        row = cluster_of(doc, "epgtalk_uk", "SkySpMainEvHD.uk")
        self.assertEqual(row["id"], "gb.sky.sports.main_event")
        self.assertTrue(row["curated"])
        self.assertIn({"source_id": "farleyflex", "channel_id": "skysportsmainevent.uk"}, row["members"])

    def test_plus_one_is_a_timeshift_never_a_merge(self):
        doc, _ = resolve({
            "uk_freeview": guide({"c4": "Channel 4"}, schedule("c4")),
            "epgtalk_uk": guide({"c4p1": "Channel 4 +1"}, schedule("c4p1", offset=60)),
        })
        self.assertIsNone(cluster_of(doc, "epgtalk_uk", "c4p1"))
        self.assertEqual(doc["timeshifts"], [{"source_id": "epgtalk_uk", "channel_id": "c4p1", "offset_minutes": 60,
                                              "base": {"source_id": "uk_freeview", "channel_id": "c4"},
                                              "base_id": "gb.c4.channel4"}])

    def test_regional_language_plus_and_numbered_variants_are_never_merged(self):
        regional = TITLES[:10] + ["Reporting Scotland Late", "Debate Night Scotland"]
        for a_name, b_name, b_titles in [
            ("BBC One", "BBC One Scotland HD", regional),
            ("Al Jazeera", "Al Jazeera Arabic", TITLES),
            ("Sky Sports", "Sky Sports+ HD", TITLES),
            ("TNT Sports 1", "TNT Sports 2", TITLES),
            ("Channel 4", "Channel 4 ROI", TITLES),
        ]:
            with self.subTest(b=b_name):
                doc, report = resolve({
                    "uk_freeview": guide({"a": a_name}, schedule("a")),
                    "epgtalk_uk": guide({"b": b_name}, schedule("b", b_titles)),
                })
                a, b = cluster_of(doc, "uk_freeview", "a"), cluster_of(doc, "epgtalk_uk", "b")
                self.assertFalse(a and b and a["id"] == b["id"], (a_name, b_name))
                self.assertEqual(report["suggestions"], [])

    def test_plus_spelling_variants_are_the_same_service(self):
        doc, _ = resolve({
            "uk_freeview": guide({"a": "Sky Sports Plus"}, schedule("a")),
            "epgtalk_uk": guide({"b": "Sky Sports+ HD"}, schedule("b")),
        })
        self.assertEqual(cluster_of(doc, "uk_freeview", "a")["id"], cluster_of(doc, "epgtalk_uk", "b")["id"])

    def test_different_names_with_identical_schedules_go_to_owner_review_only(self):
        doc, report = resolve({
            "uk_freeview": guide({"a": "Dave"}, schedule("a")),
            "epgtalk_uk": guide({"b": "U&Dave"}, schedule("b")),
        })
        self.assertIsNone(cluster_of(doc, "uk_freeview", "a"))
        self.assertEqual(len(report["suggestions"]), 1)
        self.assertEqual({report["suggestions"][0]["a_name"], report["suggestions"][0]["b_name"]}, {"Dave", "U&Dave"})

    def test_same_name_with_disagreeing_schedules_is_not_linked(self):
        other = ["Completely Different Show %d Episode" % i for i in range(12)]
        doc, _ = resolve({
            "uk_freeview": guide({"a": "Quest"}, schedule("a")),
            "epgtalk_uk": guide({"b": "Quest"}, schedule("b", other)),
        })
        self.assertIsNone(cluster_of(doc, "uk_freeview", "a"))

    def test_generic_filler_titles_never_create_links(self):
        filler = ["News", "Close", "Teleshopping", "To Be Announced"] * 3
        doc, report = resolve({
            "uk_freeview": guide({"a": "Shop TV"}, schedule("a", filler)),
            "epgtalk_uk": guide({"b": "Shop TV"}, schedule("b", filler)),
        })
        self.assertEqual(doc["channels"], [])
        self.assertEqual(report["stats"]["channels_fingerprinted"], 0)

    def test_hd_sd_duplicates_in_one_guide_join_but_different_channels_of_one_guide_never_do(self):
        doc, _ = resolve({
            "uk_freeview": guide({"q": "Quest", "qhd": "Quest HD"}, schedule("q") + schedule("qhd")),
            "epgtalk_uk": guide({"x": "Quest", "y": "Really"}, schedule("x") + schedule("y")),
        })
        quest = cluster_of(doc, "uk_freeview", "q")
        self.assertEqual({(m["source_id"], m["channel_id"]) for m in quest["members"]},
                         {("uk_freeview", "q"), ("uk_freeview", "qhd"), ("epgtalk_uk", "x")})
        self.assertIsNone(cluster_of(doc, "epgtalk_uk", "y"))

    def test_two_curated_identities_are_never_merged(self):
        doc, _ = resolve({
            "farleyflex": guide({"skysportsmainevent.uk": "Sky Sports Main Event"}, schedule("skysportsmainevent.uk")),
            "epgtalk_uk": guide({"pl": "Sky Sports Premier League"}, schedule("pl")),
        })
        a = cluster_of(doc, "farleyflex", "skysportsmainevent.uk")
        b = cluster_of(doc, "epgtalk_uk", "pl")
        self.assertNotEqual(a["id"], b["id"])

    def test_published_document_contains_no_programme_data(self):
        doc, _ = resolve({
            "farleyflex": guide({"skysportsmainevent.uk": "Sky Sports Main Event"}, schedule("skysportsmainevent.uk")),
            "epgtalk_uk": guide({"m": "Sky Sports Main Event HD", "m1": "Sky Sports Main Event +1"},
                                schedule("m") + schedule("m1", offset=60)),
        })
        text = json.dumps(doc)
        for title in TITLES:
            self.assertNotIn(title, text)
        self.assertNotIn("start_utc", text)
        self.assertTrue(doc["channels"] and doc["timeshifts"])


class IdentityIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "s.sqlite3")

    def tearDown(self):
        self.tmp.cleanup()

    def seed(self):
        self.store.save_snapshot("epg:farleyflex", guide({"skysportsmainevent.uk": "Sky Sports Main Event"},
                                                         schedule("skysportsmainevent.uk")))
        self.store.save_snapshot("epg:epgtalk_uk", guide({"m": "UK - Sky Sports Main Event HD"}, schedule("m")))

    def test_build_from_store_feed_asset_and_capability(self):
        self.seed()
        document, report = identity.build_from_store(self.store, ["farleyflex", "epgtalk_uk", "missing"], now=NOW)
        self.store.save_snapshot("channel-identity", {"document": document, "report": report})
        published = feed.identity_document(self.store)
        self.assertEqual({s["source_id"] for s in published["sources"]}, {"farleyflex", "epgtalk_uk"})
        self.assertTrue(all(s["source_url"].startswith("https://") for s in published["sources"]))
        self.assertEqual(report["stats"]["guides"], 2)

    def test_no_identity_asset_without_links(self):
        self.assertIsNone(feed.identity_document(self.store))
        self.store.save_snapshot("channel-identity", {"document": {"channels": []}, "report": {}})
        self.assertIsNone(feed.identity_document(self.store))

    def test_identity_failure_never_breaks_collection_and_is_recorded(self):
        engine = Engine(self.store)
        with patch("sportsliveinfo.identity.build_from_store", side_effect=MemoryError()):
            engine._refresh_identity(["farleyflex"])
        job = self.store.recent_jobs(1)[0]
        self.assertEqual((job["provider"], job["state"]), ("identity", "failed"))

    def test_identity_runs_only_when_a_guide_refreshed(self):
        self.store.configure({"setup_complete": True, "epg": {"farleyflex": True}, "sports": {"jolpica": False}})
        engine = Engine(self.store)
        with patch.object(Engine, "_collect_epg", return_value=False), \
                patch.object(Engine, "_refresh_identity") as refresh:
            engine.collect()
        refresh.assert_not_called()
        with patch.object(Engine, "_collect_epg", return_value=True), \
                patch.object(Engine, "_refresh_identity") as refresh, patch.object(Engine, "_materialize"):
            engine.collect()
        refresh.assert_called_once_with(["farleyflex"])

    def test_coverage_page_shows_identity_and_review_queue(self):
        self.seed()
        comedy = ["Taskmaster Champion Of Champions", "Would I Lie To You", "Top Gear Classic Episode", "Mock The Week Again",
                  "QI XL Extended Edition", "Red Dwarf Remastered", "Have I Got News", "Room 101 Specials",
                  "Live At The Apollo", "Dave Gorman Modern Life", "Comedy Store Sessions", "Rick Stein Holiday"]
        self.store.save_snapshot("epg:uk_freeview", guide({"d": "Dave"}, schedule("d", comedy)))
        self.store.save_snapshot("epg:iptv_epg_gb", guide({"u": "U&Dave"}, schedule("u", comedy)))
        document, report = identity.build_from_store(self.store, ["farleyflex", "epgtalk_uk", "uk_freeview", "iptv_epg_gb"], now=NOW)
        self.store.save_snapshot("channel-identity", {"document": document, "report": report})
        handler = UI.__new__(UI)
        handler.server = SimpleNamespace(store=self.store, csrf="x")
        html = handler.guide()
        self.assertIn("Channel identity across guides", html)
        self.assertIn("gb.sky.sports.main_event", html)
        self.assertIn("Needs your review (1)", html)


if __name__ == "__main__":
    unittest.main()
