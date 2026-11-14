"""Public-domain channel identity dictionary (iptv-org database) for UK and Europe."""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sportsliveinfo import guide, dictionary, feed
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

    def test_closed_channels_resolve_only_to_a_live_successor(self):
        # 0.3.18: a rebrand recorded as replaced_by gives the successor's guide (the provider stream
        # carries it now); a closure without a successor still never resolves (see the fallback tests).
        self.assertEqual(self.resolver.resolve("L'Equipe 21", "FR"),
                         {"ids": [("LEquipe.fr", None)], "method": "replaced_by", "confidence": "high"})
        self.assertEqual(self.resolver.describe("LEquipe21.fr")["replaced_by"], "LEquipe.fr")
        self.assertEqual(self.resolver.describe("CanalPlusSport.fr")["categories"], ["sports"])

    def test_ambiguity_is_reported_not_hidden(self):
        doc = dictionary.build_document(CHANNELS + "TV2b.dk,TV 2,,,,DK,general,FALSE,,,,\n", FEEDS, REGIONS)
        hit = dictionary.Resolver(doc).resolve("TV 2", "DK")
        self.assertEqual(hit["confidence"], "ambiguous")


class DictionaryFallbackTests(unittest.TestCase):
    """0.3.15 fallbacks: aliases, singular/plural, language variants, closed channels (synthetic brands)."""
    CH = """id,name,alt_names,network,owners,country,categories,is_nsfw,launched,closed,replaced_by,website
NationalGeographicWild.fr,National Geographic Wild,,,,FR,documentary,FALSE,,,,
TF1SeriesFilms.fr,TF1 Series Films,,,,FR,general,FALSE,,,,
ExampleSport1.fr,Example Sport 1,,,,FR,sports,FALSE,,,,
ExampleCinemas.fr,Example Cinemas,,,,FR,movies,FALSE,,,,
ExampleNewsFrench.fr,Examplenews French,,,,FR,news,FALSE,,,,
GlobeNews.fr,Globe News,,,,FR,news,FALSE,,,,
GlobeNewsFrench.fr,Globe News French,,,,FR,news,FALSE,,,,
OldChannel.fr,Old Channel,,,,FR,general,FALSE,,2025-03-01,NewChannel.fr,
"""
    FD = "channel,id,name,alt_names,is_main,broadcast_area,timezones,languages,format\n"

    def setUp(self):
        self.resolver = dictionary.Resolver(dictionary.build_document(self.CH, self.FD, ""))

    def ids(self, name, market="FR"):
        hit = self.resolver.resolve(name, market)
        return (hit["ids"][0][0], hit["method"]) if hit else None

    def test_aliases_singular_plural_and_uhd_markers(self):
        self.assertEqual(self.ids("FR | Nat Geo Wild HD"), ("NationalGeographicWild.fr", "alias:exact"))
        self.assertEqual(self.ids("HD1"), ("TF1SeriesFilms.fr", "alias:exact"))
        # Plural only on a final word, except the sport word (0.3.18: sport/sports/spor anywhere).
        self.assertEqual(self.ids("Example Sports 1 FHD"), ("ExampleSport1.fr", "sport_word:exact"))
        self.assertEqual(self.ids("Example Cinema")[0], "ExampleCinemas.fr")
        self.assertEqual(self.ids("FR | Example Sport 1 4K Ultra")[0], "ExampleSport1.fr")
        self.assertEqual(self.ids("Example Sport 1 (UHD/4K)")[0], "ExampleSport1.fr")
        # Aliases are scoped: the French-only HD1 rule does not apply in another market.
        self.assertIsNone(self.ids("HD1", "DE"))

    def test_language_variant_needs_a_market_code_or_a_distinctive_unknown_name(self):
        self.assertEqual(self.ids("Examplenews"), ("ExampleNewsFrench.fr", "language_variant"))
        self.assertEqual(self.ids("Globe News"), ("GlobeNews.fr", "exact"))          # the plain channel wins
        self.assertEqual(self.ids("Globe News FR"), ("GlobeNewsFrench.fr", "language_variant"))  # explicit market code
        self.assertIsNone(self.ids("XYZ"))                                       # short names never guess

    def test_closed_channels_are_explained_never_matched(self):
        self.assertIsNone(self.ids("Old Channel"))
        explained = self.resolver.explain_closed("FR | Old Channel HD", "FR")
        self.assertEqual(explained, [{"id": "OldChannel.fr", "name": "Old Channel", "closed": "2025-03-01",
                                      "replaced_by": "NewChannel.fr"}])

    def test_rules_are_published_for_the_reader(self):
        document = dictionary.build_document(self.CH, self.FD, "")
        self.assertIn({"pattern": "^hd1$", "replacement": "tf1 series films"}, document["aliases"]["FR"])
        self.assertIn("french", document["language_variants"]["FR"])
        self.assertIn("fallbacks", document["rules"])


class WorldResolutionTests(unittest.TestCase):
    """0.3.18: optional world regions, provider grammar, callsigns, country tags, scripts, successors (synthetic)."""
    CH = """id,name,alt_names,network,owners,country,categories,is_nsfw,launched,closed,replaced_by,website
ExampleNet.us,Example Net,,,,US,general,FALSE,,,,
ExampleKids.us,Example Kids,,,,US,kids,FALSE,,,,
SunExample.in,Sun Example,,,,IN,general,FALSE,,,,
AzteExample.mx,Azte Example,,,,MX,general,FALSE,,,,
CaribNews.tt,Carib News,,,,TT,news,FALSE,,,,
PeakNational.ng,Peak National,PNT,,,NG,news,FALSE,,,,
PeakTV.gh,PNT TV,,,,GH,news,FALSE,,,,
DesertOne.iq,Desert One,,,,IQ,general,FALSE,,,,
DesertOne.sa,Desert One,,,,SA,general,FALSE,,,,
Rodina1.ru,Rodina 1,Родина 1,,,RU,general,FALSE,,,,
Ellas1.gr,ELT1,ΕΛΤ1,,,GR,general,FALSE,,,,
OldBrand.tr,Old Brand,,,,TR,general,FALSE,,2024-02-12,NewBrand.tr,
NewBrand.tr,New Brand,,,,TR,general,FALSE,,,,
Gone.tr,Gone,,,,TR,general,FALSE,,2025-01-01,,
"""
    FD = """channel,id,name,alt_names,is_main,broadcast_area,timezones,languages,format
ExampleNet.us,KXMP,KXMP,,FALSE,ct/USXYZ,America/Chicago,eng,1080i
ExampleKids.us,KXMP,KXMP,,FALSE,ct/USXYZ,America/Chicago,eng,480i
ExampleNet.us,WXMQ,WXMQ-TV,,FALSE,ct/USABC,America/New_York,eng,1080i
"""
    REG = "code,name,countries\n"

    def setUp(self):
        regions = list(dictionary.REGIONS)
        self.resolver = dictionary.Resolver(dictionary.build_document(self.CH, self.FD, self.REG, regions))

    def ids(self, name, market):
        hit = self.resolver.resolve(name, market)
        return (hit["ids"][0], hit["method"], hit["confidence"]) if hit else None

    def test_world_regions_are_opt_in(self):
        europe = dictionary.build_document(self.CH, self.FD, self.REG)
        self.assertNotIn("ExampleNet.us", {c["id"] for c in europe["channels"]})
        self.assertEqual(europe["regions"], [])
        world = dictionary.build_document(self.CH, self.FD, self.REG, ["north_america"])
        self.assertIn("ExampleNet.us", {c["id"] for c in world["channels"]})
        self.assertNotIn("SunExample.in", {c["id"] for c in world["channels"]})
        self.assertIn("North America", world["scope"])

    def test_provider_grammar_of_world_sections(self):
        self.assertEqual(self.ids("US Example Net HD", "US")[0][0], "ExampleNet.us")
        self.assertEqual(self.ids("IN-TM | Sun Example FHD", "IN")[0][0], "SunExample.in")
        self.assertEqual(self.ids("(MX) (IZ) Azte Example", "LATAM")[0][0], "AzteExample.mx")
        self.assertEqual(self.ids("Claro Azte Example", "LATAM")[0][0], "AzteExample.mx")
        self.assertEqual(self.ids("Carib (FLOW) Carib News", "CARIB")[0][0], "CaribNews.tt")
        self.assertEqual(guide.market_key("Al Jazeera", "AL"), "al jazeera")          # other markets' codes kept
        self.assertEqual(guide.market_key("CA CBC Example (FL)", "CA"), "cbc example")

    def test_callsigns_pick_the_named_network(self):
        self.assertEqual(self.ids("US Example Net 5 (KXMP) Springfield", "US"),
                         (("ExampleNet.us", "KXMP"), "callsign", "high"))
        self.assertEqual(self.ids("US Example Kids (KXMP)", "US")[0][0], "ExampleKids.us")
        self.assertEqual(self.ids("US Other 7 (KXMP) Springfield", "US")[2], "ambiguous")   # name says neither
        self.assertEqual(self.ids("US Example 9 (WXMQ-TV) Town", "US")[0], ("ExampleNet.us", "WXMQ"))
        self.assertIsNone(self.ids("Example 9 (WXMQ) Town", "GB"))                    # US/CA/Caribbean only

    def test_country_tag_narrows_group_markets(self):
        self.assertEqual(self.ids("|NIGERIA| PNT", "AFRICA")[0][0], "PeakNational.ng")   # never Ghana's PNT TV
        self.assertEqual(self.ids("IRQ: Desert One HD", "MENA")[0][0], "DesertOne.iq")
        self.assertEqual(self.ids("SA: Desert One", "MENA")[0][0], "DesertOne.sa")
        self.assertEqual(self.ids("Desert One", "MENA")[2], "ambiguous")                  # untagged: owner review

    def test_cyrillic_and_greek_names_match_latin_spellings(self):
        self.assertEqual(self.ids("RU | RODINA 1 HD", "RU")[0][0], "Rodina1.ru")
        self.assertIn("rodina 1", [t.lower() for t in dictionary.transliterate("Родина 1")])
        self.assertIn("ELT1", dictionary.transliterate("ΕΛΤ1"))
        self.assertEqual(self.ids("GR | ELT 1", "GR")[0][0], "Ellas1.gr")

    def test_successor_only_when_the_closure_names_a_live_one(self):
        self.assertEqual(self.ids("TR | Old Brand HD", "TR"), (("NewBrand.tr", None), "replaced_by", "high"))
        self.assertIsNone(self.ids("TR | Gone", "TR"))
        self.assertEqual(self.resolver.explain_closed("TR | Gone", "TR")[0]["id"], "Gone.tr")

    def test_sport_spellings_implicit_first_number_and_plain_not_4k(self):
        ch = """id,name,alt_names,network,owners,country,categories,is_nsfw,launched,closed,replaced_by,website
NovaSports1.gr,Novasports 1,,,,GR,sports,FALSE,,,,
ArenaSport.bg,Arena Sport,,,,BG,sports,FALSE,,,,
ArenaSport2.bg,Arena Sport 2,,,,BG,sports,FALSE,,,,
SoloSport.bg,Solo Sport,,,,BG,sports,FALSE,,,,
EightSports1.pl,Eight Sports 1,,,,PL,sports,FALSE,,,,
EightSports14K.pl,Eight Sports 1 4K,,,,PL,sports,FALSE,,,,
StarSports1.qa,Star Sports 1,,,,QA,sports,FALSE,,,,
StarSports1Turk.tr,Star Sports 1 Turk,,,,TR,sports,FALSE,,,,
"""
        fd = ("channel,id,name,alt_names,is_main,broadcast_area,timezones,languages,format\n"
              "StarSports1.qa,MENA,MENA,,TRUE,c/QA;c/TR,Asia/Qatar,ara,1080i\n")
        r = dictionary.Resolver(dictionary.build_document(ch, fd, ""))
        def first(name, market):
            hit = r.resolve(name, market)
            return (hit["ids"][0][0], hit["method"], hit["confidence"]) if hit else None
        self.assertEqual(first("GR | NOVA SPORT 1", "GR")[0], "NovaSports1.gr")
        self.assertEqual(first("BG | Arena Sport 1", "BG")[:2], ("ArenaSport.bg", "implicit_1:exact"))
        self.assertIsNone(first("BG | Solo Sport 1", "BG"))                 # no "Solo Sport 2": not a series
        self.assertEqual(first("PL | Eight Sports 1", "PL"), ("EightSports1.pl", "exact:plain_not_4k", "high"))
        self.assertEqual(first("PL | Eight Sports 1 4K", "PL")[2], "ambiguous")   # the 4K name is not decided here
        self.assertEqual(first("TR | Star Sport 1", "TR")[0], "StarSports1Turk.tr")
        # The Qatari channel also broadcasts into Turkey; the Turkish version still wins for a Turkish list.
        self.assertEqual(first("TR | Star Sports 1", "TR")[:2], ("StarSports1Turk.tr", "numbered_variant:exact"))
        self.assertEqual(first("TR | StarSports 1", "TR")[0], "StarSports1Turk.tr")
        self.assertIsNone(first("Star Sport 1", "PL"))                      # foreign variants are never taken

    def test_own_market_suffix(self):
        self.assertEqual(self.ids("US Example Net HD US", "US")[0][0], "ExampleNet.us")


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
        self.assertIn("Channel identity dictionary</h3>", handler._dictionary_card(self.store.config()))

    def test_retired_guides_disappear_from_saved_choices(self):
        raw = self.store._get("config")
        raw["epg"]["fr_programmetv"] = True
        self.store._put("config", raw)
        self.assertNotIn("fr_programmetv", self.store.config()["epg"])


if __name__ == "__main__":
    unittest.main()
