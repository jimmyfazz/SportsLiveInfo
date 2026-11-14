"""One identity rule for dictionary hits on SLI and on the TV: regional feeds keep their region."""
import unittest

from sportsliveinfo import coverage, dictionary, linking

DOCUMENT = {"channels": [
    {"id": "France3.fr", "name": "France 3", "country": "FR", "categories": ["General"],
     "feeds": [{"id": "SD", "name": "SD", "main": True, "areas": ["FR"]},
               {"id": "Alsace", "name": "Alsace", "areas": ["FR"]},
               {"id": "AlsaceHD", "name": "Alsace HD", "areas": ["FR"]}]},
]}


def hit(*ids, confidence="high"):
    return {"ids": list(ids), "method": "exact", "confidence": confidence}


class ServiceIdentityTest(unittest.TestCase):
    def test_main_quality_region_timeshift_and_ambiguity(self):
        self.assertEqual(dictionary.service_identity(hit(("RTL.de", None), ("RTL.de", "HD"))), "RTL.de")
        self.assertEqual(dictionary.service_identity(hit(("X.uk", "UKHD"))), "X.uk")
        self.assertEqual(dictionary.service_identity(hit(("BBCOne.uk", "Wales"), ("BBCOne.uk", "WalesHD"))),
                         "BBCOne.uk@Wales")
        self.assertIsNone(dictionary.service_identity(hit(("ITV1.uk", "Plus1"))))
        self.assertIsNone(dictionary.service_identity(hit(("A.uk", None), ("B.uk", None))))
        self.assertIsNone(dictionary.service_identity(hit(("BBCOne.uk", "Wales"), ("BBCOne.uk", "Scotland"))))
        self.assertIsNone(dictionary.service_identity(hit(("RTL.de", None), confidence="medium")))
        self.assertIsNone(dictionary.service_identity(None))

    def test_a_regional_guide_channel_is_never_the_national_service(self):
        resolver = dictionary.Resolver(DOCUMENT)
        regional = linking._dictionary_hit(resolver, "fr_xmltv", "France 3 Alsace", "f3alsace")
        national = linking._dictionary_hit(resolver, "fr_xmltv", "France 3", "f3")
        self.assertEqual(regional[0], "France3.fr@Alsace")
        self.assertEqual(national[0], "France3.fr")


class ChooseGuideChannelsTest(unittest.TestCase):
    MAP = {"service_aliases": {"BBCOne.uk": "gb.bbc.one"}, "guides": [
        {"source_id": "a", "channels": [
            {"id": "bbcone", "service": "gb.bbc.one", "programmes_7d": 10},
            {"id": "BBCOne.uk@HD", "programmes_7d": 30},
            {"id": "BBCOne.uk@WalesHD", "programmes_7d": 50},
            {"id": "BBCOne.uk@LondonEast", "programmes_7d": 50},
            {"id": "BBCOne.uk@Plus1", "programmes_7d": 50},
            {"id": "BBCOne.uk@GermanyHD", "programmes_7d": 50},
            {"id": "dead", "service": "gb.bbc.one", "programmes_7d": 0}]},
        {"source_id": "b", "channels": [{"id": "BBCOne.uk", "service": "gb.bbc.two", "programmes_7d": 99}]}]}

    def test_national_never_takes_a_region_timeshift_foreign_feed_or_empty_channel(self):
        how, hits = coverage.choose_guide_channels(self.MAP, "gb.bbc.one", market="GB")
        self.assertEqual(how, "service")
        self.assertEqual(hits, [("a", "BBCOne.uk@HD", 30), ("a", "bbcone", 10)])

    def test_region_must_agree_exactly(self):
        self.assertEqual(coverage.choose_guide_channels(self.MAP, "BBCOne.uk@Wales", market="GB"),
                         ("dictionary_id", [("a", "BBCOne.uk@WalesHD", 50)]))
        self.assertEqual(coverage.choose_guide_channels(self.MAP, "BBCOne.uk@London", market="GB"), (None, []))

    def test_provider_id_first_and_disabled_guides_ignored(self):
        self.assertEqual(coverage.choose_guide_channels(self.MAP, "gb.bbc.one", tvg_id="BBCOne.uk@Plus1"),
                         ("provider_id", [("a", "BBCOne.uk@Plus1", 50)]))
        self.assertEqual(coverage.choose_guide_channels(self.MAP, "gb.bbc.one", enabled={"b"}), (None, []))


if __name__ == "__main__":
    unittest.main()
