import unittest
from urllib.request import Request

from sportsliveinfo import engine, providers
from sportsliveinfo.guide import COUNTRY_BY_SOURCE


class MattHuismanGuideTests(unittest.TestCase):
    def test_working_guides_use_final_raw_host_and_retired_uk_source_is_not_offered(self):
        self.assertEqual(
            providers.EPG["mjh_nz"][1],
            "https://raw.githubusercontent.com/matthuisman/i.mjh.nz/master/nz/epg.xml.gz",
        )
        self.assertEqual(
            providers.EPG["mjh_au_sydney"][1],
            "https://raw.githubusercontent.com/matthuisman/i.mjh.nz/master/au/Sydney/epg.xml.gz",
        )
        self.assertNotIn("mjh_sky_uk", providers.EPG)
        self.assertNotIn("mjh_sky_uk", providers.EPG_LIMITS)
        self.assertEqual(COUNTRY_BY_SOURCE["mjh_sky_uk"], "GB")
        for source in ("mjh_nz", "mjh_au_sydney"):
            url = providers.EPG[source][1]
            providers.verify_url(url)
            self.assertIn("raw.githubusercontent.com", providers.ALLOW_HOSTS)
            self.assertEqual(providers.EPG_LIMITS[source], (5_000_000, 50_000))
            self.assertGreater(providers.EPG_EXPANDED_LIMITS[source], 7_000_000)

    def test_cross_origin_redirect_remains_blocked(self):
        handler = providers.RedirectGuard()
        request = Request("https://i.mjh.nz/nz/epg.xml.gz")
        with self.assertRaisesRegex(ValueError, "^Cross-origin provider redirect blocked$"):
            handler.redirect_request(request, None, 302, "Found", {},
                                     "https://raw.githubusercontent.com/matthuisman/i.mjh.nz/master/nz/epg.xml.gz")

    def test_known_source_safety_failures_are_diagnostic(self):
        self.assertEqual(engine._guide_failure(ValueError("Cross-origin provider redirect blocked")),
                         "Cross-origin provider redirect blocked")
        self.assertEqual(engine._guide_failure(ValueError("Source URL is not on the approved HTTPS provider list")),
                         "Source URL is not on the approved HTTPS provider list")


    def test_sport_guides_are_opt_in_and_map_to_canonical_services(self):
        for source, market in (("mjh_skysportnow_nz", "NZ"), ("mjh_kayo_au", "AU")):
            providers.verify_url(providers.EPG[source][1])
            self.assertIn("raw.githubusercontent.com/matthuisman/i.mjh.nz/master/", providers.EPG[source][1])
            self.assertEqual(providers.EPG_FAMILY[source], "mjh")
            self.assertEqual(COUNTRY_BY_SOURCE[source], market)
        from sportsliveinfo.guide import canonical_channel
        self.assertEqual(canonical_channel("mjh_skysportnow_nz", "341", "Sky Sport 1"), "nz.sky.sport.1")
        self.assertEqual(canonical_channel("mjh_skysportnow_nz", "355", "Sky Sport Premier League"),
                         "nz.sky.sport.premier_league")
        self.assertEqual(canonical_channel("mjh_kayo_au", "53211", "Fox Sports 503"), "au.fox.sports.503")
        # "Sky Sport 1" in a German or UK guide is never the NZ channel.
        self.assertIsNone(canonical_channel("iptv_epg_de", "x", "Sky Sport 1"))

    def test_xz_guides_decode_with_the_same_bounds(self):
        import lzma
        xml = (b'<?xml version="1.0"?><tv><channel id="SkyExample.uk@HD"><display-name>Sky Example HD</display-name>'
               b'</channel><programme channel="SkyExample.uk@HD" start="20261114120000 +0000" '
               b'stop="20261114130000 +0000"><title>Live Example</title></programme></tv>')
        guide = providers.decode_xmltv(lzma.compress(xml), "m3upt_sky")
        self.assertEqual(guide["channels"], {"SkyExample.uk@HD": "Sky Example HD"})
        self.assertEqual(len(guide["programmes"]), 1)
        with self.assertRaises(ValueError):                    # expansion limit applies to xz too
            providers.decode_xmltv(lzma.compress(xml + b" " * 5000), "m3upt_sky", max_expanded=1000)

    def test_second_pass_sources_are_registered_and_off_by_default(self):
        from sportsliveinfo.storage import DEFAULT as DEFAULT_CONFIG
        new = ("m3upt_sky", "m3upt_sky_it", "m3upt_freeview_uk", "epgtalk_us", "epgtalk_us_local", "epgtalk_latino",
               "epgtalk_freetv", "mjh_roku_us", "mjh_plex_us", "mjh_dstv_za", "mjh_samsung_in", "mjh_au_all",
               "mjh_skygo_nz")
        for source in new:
            providers.verify_url(providers.EPG[source][1])
            self.assertIn(source, providers.EPG_FAMILY)
            self.assertIn(source, providers.EPG_LIMITS)
            self.assertFalse(DEFAULT_CONFIG.get("epg", {}).get(source, False))
        from sportsliveinfo.guide import canonical_channel
        # The multi-country Sky file: UK ids are GB services; German/Italian ids never are.
        self.assertEqual(canonical_channel("m3upt_sky", "SkySportsMainEvent.uk@HD", "Sky Sports Main Event HD"),
                         "gb.sky.sports.main_event")
        self.assertIsNone(canonical_channel("m3upt_sky", "SkySport1.de@HD", "Sky Sport 1 HD"))


if __name__ == "__main__":
    unittest.main()
