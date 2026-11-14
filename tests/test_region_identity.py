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


class ReconcileChannelTest(unittest.TestCase):
    """The TV's per-channel order of work (coverage.reconcile_channel)."""
    MAP = {"guides": [{"source_id": "a", "channels": [
        {"id": "France3.fr@Alsace", "service": "France3.fr@Alsace", "programmes_7d": 70},
        {"id": "France3.fr", "service": "France3.fr", "programmes_7d": 70},
        {"id": "f3plus", "service": "France3.fr", "programmes_7d": 5}]}]}

    def setUp(self):
        self.resolver = dictionary.Resolver(DOCUMENT)

    def reconcile(self, **entry):
        return coverage.reconcile_channel(entry, resolver=self.resolver, guide_map=self.MAP)

    def test_regional_name_gets_the_regional_guide(self):
        row = self.reconcile(category="FR| GENERAL", name="FR: France 3 Alsace HD")
        self.assertEqual((row["identity"], row["state"], row["guide_channel"]),
                         ("France3.fr@Alsace", "guide", "France3.fr@Alsace"))

    def test_provider_id_wins_and_names_the_service(self):
        row = self.reconcile(category="FR| GENERAL", name="Something else", tvg_id="France3.fr@AlsaceHD")
        self.assertEqual((row["identity"], row["identity_method"]), ("France3.fr@Alsace", "provider_id"))
        timeshift = self.reconcile(category="FR| GENERAL", name="Unknown", tvg_id="France3.fr@Plus1")
        self.assertEqual(timeshift["identity"], "")

    def test_vod_radio_adult_and_loops_are_skipped(self):
        for category, name in (("VOD Movies", "France 3"), ("Radio FR", "France 3"), ("XXX", "x"), ("24/7 Films", "y")):
            self.assertEqual(self.reconcile(category=category, name=name)["state"], "skipped")

    def test_columns_are_the_tv_export_columns(self):
        self.assertEqual(list(self.reconcile(category="FR", name="France 3")), coverage.TV_FIELDS)


class CompareTvExportTest(unittest.TestCase):
    def test_conforming_export_passes_and_a_region_swap_is_serious(self):
        resolver = dictionary.Resolver(DOCUMENT)
        lineup = [{"category": "FR| GENERAL", "name": "France 3 Alsace", "tvg_id": ""},
                  {"category": "FR| GENERAL", "name": "France 3", "tvg_id": ""}]
        rows = [coverage.reconcile_channel(e, resolver=resolver, guide_map=ReconcileChannelTest.MAP) for e in lineup]
        good = coverage.compare_tv_export(lineup, rows, resolver=resolver, guide_map=ReconcileChannelTest.MAP)
        self.assertTrue(good["passes"])
        self.assertEqual(good["identity_agreement"], 100.0)
        rows[0] = dict(rows[0], identity="France3.fr")                      # B1G merged the region: serious
        bad = coverage.compare_tv_export(lineup, rows, resolver=resolver, guide_map=ReconcileChannelTest.MAP)
        self.assertFalse(bad["passes"])
        self.assertEqual(bad["counts"]["wrong_region"], 1)
        self.assertEqual(bad["differences"][0]["field"], "identity")

    def test_parse_rejects_other_files(self):
        with self.assertRaises(ValueError):
            coverage.parse_tv_export("a,b\n1,2\n")
