"""Public-domain channel identity dictionary (iptv-org database) for UK and Europe."""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sportsliveinfo import dictionary, feed
from sportsliveinfo.engine import Engine
from sportsliveinfo.server import UI
from sportsliveinfo.storage import Store

CHANNELS = """id,name,alt_names,network,owners,country,categories,is_nsfw,launched,closed,replaced_by,website
SkySportsMainEvent.uk,Sky Sports Main Event,,,Sky,UK,sports,FALSE,,,,https://www.skysports.com
BBCOne.uk,BBC One,BBC 1,,BBC,UK,general,FALSE,,,,https://www.bbc.co.uk
CanalPlusSport.fr,Canal+ Sport,,,Canal+,FR,sports,FALSE,1998-08-31,,,https://www.canalplus.com
LEquipe21.fr,L'Equipe 21,,,,FR,sports,FALSE,,2016-01-01,LEquipe.fr,
LEquipe.fr,L'Equipe,L'Équipe,,,FR,sports,FALSE,,,,
ChasseEtPeche.fr,Chasse & Peche,,,,FR,outdoor,FALSE,,,,
TV2.dk,TV 2,,,,DK,general,FALSE,,,,
TV2.no,TV 2,,,,NO,general,FALSE,,,,
beINSports1.qa,beIN Sports 1,,,beIN Media Group,QA,sports,FALSE,,,,
OnlyAsia.cn,Only Asia,,,,CN,general,FALSE,,,,
Adult.de,Adult,,,,DE,xxx,TRUE,,,,
Viasat.se,Viasat History,,,,SE,documentary,FALSE,,,,
"""
FEEDS = """channel,id,name,alt_names,is_main,broadcast_area,timezones,languages,format
BBCOne.uk,HD,HD,,TRUE,c/UK,Europe/London,eng,1080i
BBCOne.uk,Scotland,Scotland,,FALSE,c/UK,Europe/London,eng,576i
beINSports1.qa,MENA,MENA,,TRUE,r/MENA,Asia/Qatar,ara,1080i
beINSports1.qa,France,France,,FALSE,c/FR,Europe/Paris,fra,1080i
OnlyAsia.cn,SD,SD,,TRUE,c/CN,Asia/Shanghai,zho,576i
Viasat.se,Nordic,Nordic,,TRUE,r/NORD,Europe/Stockholm,swe,1080i
"""
REGIONS = """code,name,countries
MENA,Middle East and North Africa,AE;QA;SA
NORD,Nordics,DK;FI;IS;NO;SE
"""


class DictionaryTests(unittest.TestCase):
    def setUp(self):
        self.doc = dictionary.build_document(CHANNELS, FEEDS, REGIONS)
        self.resolver = dictionary.Resolver(self.doc)

    def ids(self, name, market):
        hit = self.resolver.resolve(name, market)
        return [cid for cid, _ in hit["ids"]] if hit else None

    def test_scope_is_uk_europe_plus_feeds_broadcasting_into_europe(self):
        ids = {c["id"] for c in self.doc["channels"]}
        self.assertIn("beINSports1.qa", ids)            # France feed broadcasts into Europe
        self.assertNotIn("OnlyAsia.cn", ids)
        self.assertNotIn("Adult.de", ids)               # NSFW never included
        bein = next(c for c in self.doc["channels"] if c["id"] == "beINSports1.qa")
        self.assertEqual([f["id"] for f in bein["feeds"]], ["France"])
        viasat = next(c for c in self.doc["channels"] if c["id"] == "Viasat.se")
        self.assertEqual(viasat["feeds"][0]["areas"], ["DK", "FI", "IS", "NO", "SE"])   # region expanded
        self.assertEqual(self.doc["source"]["licence"], "Unlicense (public domain)")

    def test_provider_names_resolve_within_their_market(self):
        self.assertEqual(self.ids("UK-Sky Sports Main Event FHD 50FPS", "GB"), ["SkySportsMainEvent.uk"])
        self.assertEqual(self.ids("UK: BBC 1 HD", "GB"), ["BBCOne.uk"])
        self.assertEqual(self.ids("FR | Canal+ Sport FHD", "FR"), ["CanalPlusSport.fr"])
        self.assertEqual(self.ids("FR | beIN SPORTS 1 HD", "FR"), ["beINSports1.qa"])           # broadcast area
        self.assertEqual(self.resolver.resolve("FR | beIN SPORTS 1 HD", "FR")["method"], "broadcast_area")
        self.assertEqual(self.ids("Chasse et Pêche", "FR"), ["ChasseEtPeche.fr"])              # et == &
        self.assertEqual(self.ids("FR | L'Équipe HD", "FR"), ["LEquipe.fr"])

    def test_market_gating_and_own_country_first(self):
        self.assertEqual(self.ids("|DK| TV 2 HD", "DK"), ["TV2.dk"])
        self.assertEqual(self.ids("|NO| TV 2 HD", "NO"), ["TV2.no"])
        self.assertIsNone(self.resolver.resolve("Canal+ Sport", "GB"))
        self.assertEqual(self.ids("|SW| Viasat History", "SE"), ["Viasat.se"])

    def test_regional_feed_is_identity_not_decoration(self):
        hit = self.resolver.resolve("BBC One Scotland HD", "GB")
        self.assertEqual(hit["ids"][0], ("BBCOne.uk", "Scotland"))

    def test_closed_channels_explain_but_never_resolve(self):
        self.assertIsNone(self.resolver.resolve("L'Equipe 21", "FR"))
        self.assertEqual(self.resolver.describe("LEquipe21.fr")["replaced_by"], "LEquipe.fr")
        self.assertEqual(self.resolver.describe("CanalPlusSport.fr")["categories"], ["sports"])

    def test_ambiguity_is_reported_not_hidden(self):
        doc = dictionary.build_document(CHANNELS + "TV2b.dk,TV 2,,,,DK,general,FALSE,,,,\n", FEEDS, REGIONS)
        hit = dictionary.Resolver(doc).resolve("TV 2", "DK")
        self.assertEqual(hit["confidence"], "ambiguous")


class DictionaryRefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "s.sqlite3")

    def tearDown(self):
        self.tmp.cleanup()

    def big(self):
        rows = "".join("C%d.de,Channel %d,,,,DE,general,FALSE,,,,\n" % (i, i) for i in range(1100))
        return CHANNELS.replace("Adult.de", "AdultX.de") + rows

    def test_refresh_daily_conditional_and_keeps_last_good(self):
        calls = []
        def fetch(url, headers, max_bytes, response_headers):
            calls.append((url, dict(headers)))
            response_headers["ETag"] = '"v1"'
            body = {"channels.csv": self.big(), "feeds.csv": FEEDS, "regions.csv": REGIONS}[url.rsplit("/", 1)[1]]
            return body.encode()
        now = datetime(2026, 11, 14, 4, 0, tzinfo=timezone.utc)
        self.assertEqual(dictionary.refresh(self.store, now=now, fetch=fetch), "updated")
        self.assertEqual(len(calls), 3)
        self.assertEqual(dictionary.refresh(self.store, now=now + timedelta(hours=2), fetch=fetch), "fresh")
        self.assertEqual(len(calls), 3)
        def unchanged(url, headers, max_bytes, response_headers):
            self.assertEqual(headers, {"If-None-Match": '"v1"'})
            return None
        self.assertEqual(dictionary.refresh(self.store, now=now + timedelta(hours=25), fetch=unchanged), "unchanged")
        def broken(url, headers, max_bytes, response_headers):
            return b"id,name\n"
        with self.assertRaises(ValueError):
            dictionary.refresh(self.store, now=now + timedelta(hours=50), fetch=broken)
        self.assertGreater(self.store.snapshot("channel-dictionary")["data"]["meta"]["channels"], 1000)

    def test_opt_in_only_and_published_with_attribution(self):
        self.assertFalse(self.store.config()["dictionary"]["iptvorg"])
        self.store.save_snapshot("channel-dictionary", {"document": dictionary.build_document(CHANNELS, FEEDS, REGIONS),
                                                        "meta": {"channels": 11}})
        self.assertIsNone(feed.dictionary_document(self.store, self.store.config()))
        self.store.configure({"dictionary": {"iptvorg": True}})
        self.assertTrue(feed.dictionary_document(self.store, self.store.config())["channels"])
        with self.assertRaises(ValueError):
            self.store.configure({"dictionary": {"other": True}})

    def test_engine_refresh_failure_is_recorded_and_isolated(self):
        engine = Engine(self.store)
        with patch("sportsliveinfo.dictionary.refresh", side_effect=RuntimeError("Upstream network request failed")):
            engine._refresh_dictionary()
        job = self.store.recent_jobs(1)[0]
        self.assertEqual((job["provider"], job["state"]), ("dictionary", "failed"))

    def test_sources_page_offers_the_toggle(self):
        handler = UI.__new__(UI)
        handler.server = SimpleNamespace(store=self.store, csrf="x")
        self.assertIn("Channel identity dictionary (UK and Europe)", handler._dictionary_card(self.store.config()))

    def test_retired_guides_disappear_from_saved_choices(self):
        raw = self.store._get("config")
        raw["epg"]["fr_programmetv"] = True
        self.store._put("config", raw)
        self.assertNotIn("fr_programmetv", self.store.config()["epg"])


if __name__ == "__main__":
    unittest.main()
