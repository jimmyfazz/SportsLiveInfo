"""Synthetic regression cases for sport-to-guide matching; no owner lineup data."""
import unittest
from datetime import datetime, timedelta, timezone

from sportsliveinfo import linking

UTC = timezone.utc
START = datetime(2026, 11, 14, 15, 0, tzinfo=UTC)


def fixture(**extra):
    row = {
        "id": "synthetic:event:1", "sport": "football", "title": "North Harbor v Westshire",
        "competition": "Synthetic Cup", "participants": ["North Harbor FC", "Westshire United"],
        "participants_short": ["Harbor", "Westshire"], "start_utc": START.isoformat(),
        "start_precision": "scheduled", "category_priority": 1,
    }
    row.update(extra)
    return row


def programme(title, channel_id="example-sports", channel_name="Example Sports Network", **extra):
    row = {
        "channel_id": channel_id,
        "start_utc": (START - timedelta(minutes=10)).isoformat(),
        "end_utc": (START + timedelta(hours=2)).isoformat(),
        "title": title, "subtitle": "", "is_live": True, "is_repeat": False,
    }
    row.update(extra)
    return row


def guide(rows, channels=None):
    return {"source_id": "farleyflex", "channels": channels or {"example-sports": "Example Sports Network"},
            "programmes": rows}


SPORTS_IDENTITY = {"channels": [{"id": "gb.example.sports", "curated": True,
                                  "members": [{"source_id": "farleyflex", "channel_id": "example-sports"}]}]}


class BroadcastMatcherSafetyTests(unittest.TestCase):
    def test_short_alias_and_distinctive_tokens_match_without_generic_word_false_positive(self):
        event = fixture()
        good = linking.broadcast_candidates([event], {"farleyflex": guide([programme("Harbor v Westshire")])}, START,
                                            identity_document=SPORTS_IDENTITY)
        self.assertIn(event["id"], good)
        weak = linking.broadcast_candidates(
            [event], {"farleyflex": guide([programme("North v West")])}, START,
            identity_document=SPORTS_IDENTITY)
        self.assertNotIn(event["id"], weak)
        self.assertFalse(linking._fixture_in("North v West", linking.team_key("North Harbor"),
                                             linking.team_key("Westshire United"), set()))

    def test_womens_and_u21_markers_must_agree_with_the_guide_title(self):
        womens = fixture(title="North Harbor Women v Westshire Women",
                         participants=["North Harbor Women", "Westshire Women"], participants_short=[])
        no_gender = guide([programme("North Harbor v Westshire")])
        correct_gender = guide([programme("North Harbor Women v Westshire Women")])
        self.assertNotIn(womens["id"], linking.broadcast_candidates(
            [womens], {"farleyflex": no_gender}, START, identity_document=SPORTS_IDENTITY))
        self.assertIn(womens["id"], linking.broadcast_candidates(
            [womens], {"farleyflex": correct_gender}, START, identity_document=SPORTS_IDENTITY))

        u21 = fixture(title="U21 Synthetic Cup", competition="U21 Synthetic Cup")
        age_missing = guide([programme("North Harbor v Westshire")])
        age_present = guide([programme("U21 North Harbor v U21 Westshire")])
        self.assertNotIn(u21["id"], linking.broadcast_candidates(
            [u21], {"farleyflex": age_missing}, START, identity_document=SPORTS_IDENTITY))
        self.assertIn(u21["id"], linking.broadcast_candidates(
            [u21], {"farleyflex": age_present}, START, identity_document=SPORTS_IDENTITY))

    def test_radio_shopping_and_wrong_sport_services_are_rejected(self):
        event = fixture()
        for name in ("Example Sports Radio", "Example Sports Shop", "Example Cricket Network"):
            with self.subTest(name=name):
                result = linking.broadcast_candidates(
                    [event], {"farleyflex": guide([programme("North Harbor v Westshire")],
                                                   {"example-sports": name})}, START,
                    identity_document=SPORTS_IDENTITY)
                self.assertNotIn(event["id"], result)
        self.assertTrue(linking._channel_sport_eligible("football", "Example Sports Network"))

    def test_dictionary_maps_regional_aliases_to_one_stable_channel_id(self):
        document = {"channels": [{"id": "example_network.uk", "name": "Example Sports Network",
                                  "country": "UK", "alt_names": ["Example Sports Network North",
                                                                     "Example Sports Network West"],
                                  "categories": ["Sports"]}]}
        guides = {"farleyflex": guide([
            programme("North Harbor v Westshire", "north", "Example Sports Network North"),
            programme("North Harbor v Westshire", "west", "Example Sports Network West"),
        ], {"north": "Example Sports Network North", "west": "Example Sports Network West"})}
        result = linking.broadcast_candidates([fixture()], guides, START, dictionary_document=document)
        self.assertEqual(result["synthetic:event:1"][1][0]["canonical_channel_id"], "example_network.uk")
        self.assertEqual(result["synthetic:event:1"][1][0]["channel_identity_method"], "dictionary")

    def test_curated_identity_maps_an_unlisted_synthetic_guide_channel(self):
        identity = {"channels": [{"id": "gb.example.sports", "curated": True,
                                  "members": [{"source_id": "farleyflex", "channel_id": "example-sports"}]}]}
        result = linking.broadcast_candidates(
            [fixture()], {"farleyflex": guide([programme("North Harbor v Westshire")])}, START,
            identity_document=identity)
        self.assertEqual(result["synthetic:event:1"][1][0]["canonical_channel_id"], "gb.example.sports")
        self.assertEqual(result["synthetic:event:1"][1][0]["channel_identity_method"], "identity_registry")

    def test_regional_names_resolve_to_their_own_service(self):
        expected = {
            "BBC One Scotland HD": "gb.bbc.one.scotland", "UK - BBC One Scotlad": "gb.bbc.one.scotland",
            "BBC One London HD": "gb.bbc.one", "UK - BBC One Y&L HD": "gb.bbc.one", "BBC Two NI HD": "gb.bbc.two.ni",
            "ITV1 Anglia (West) HD": "gb.itv.one", "UK - ITV HD Yorkshire west": "gb.itv.one",
            "ITV1 Wales HD": "gb.itv.one.wales", "UK - ITV1 Border Scotland HD": "gb.itv.one.border_scotland",
            "STV Central HD": "gb.stv", "UTV": "gb.utv", "ITV2 HD": "gb.itv.two",
            "Sky Sports+ HD": "gb.sky.sports.plus", "UK - BBC ALBA HD": "gb.bbc.alba", "TG4": "ie.tg4",
        }
        for name, service in expected.items():
            with self.subTest(name=name):
                self.assertEqual(linking._registry_channel_id("farleyflex", "x", name), service)
        for name in ("BBC One Narnia", "ITV1 Atlantis HD", "Example One North"):
            self.assertIsNone(linking._registry_channel_id("farleyflex", "x", name))
        # Regional rules apply to UK guides only.
        self.assertIsNone(linking._registry_channel_id("epgshare_fr", "x", "BBC One Scotland"))

    def test_timeshift_channels_are_never_live_candidates(self):
        event = fixture()
        for name in ("Example Sports Network +1", "Example Sports Network Plus 1"):
            with self.subTest(name=name):
                self.assertFalse(linking._channel_sport_eligible("football", name))
                result = linking.broadcast_candidates(
                    [event], {"farleyflex": guide([programme("North Harbor v Westshire")], {"example-sports": name})},
                    START, identity_document=SPORTS_IDENTITY)
                self.assertNotIn(event["id"], result)
        # A dictionary timeshift feed must not resolve to its base channel id.
        document = {"channels": [{"id": "ExampleNetwork.uk", "name": "Example Sports Network", "country": "UK",
                                  "categories": ["Sports"],
                                  "feeds": [{"id": "SD", "name": "SD", "main": True, "areas": ["UK"]},
                                            {"id": "Plus1", "name": "+1", "areas": ["UK"]}]}]}
        from sportsliveinfo import dictionary
        resolver = dictionary.Resolver(document)
        self.assertEqual(linking._dictionary_hit(resolver, "farleyflex", "Example Sports Network")[0],
                         "ExampleNetwork.uk")
        self.assertIsNone(linking._dictionary_hit(resolver, "farleyflex", "Example Sports Network +1"))

    def test_registry_and_dictionary_ids_unify_to_one_service_id(self):
        document = {"channels": [{"id": "ExampleOne.uk", "name": "ITV1", "country": "UK",
                                  "alt_names": ["Example Regional One"], "categories": ["General"]}]}
        guides = {"farleyflex": guide([
            programme("North Harbor v Westshire", "itv1", "ITV1"),
            programme("North Harbor v Westshire", "regional", "Example Regional One"),
        ], {"itv1": "ITV1", "regional": "Example Regional One"})}
        result = linking.broadcast_candidates([fixture()], guides, START, dictionary_document=document)
        ids = [row["canonical_channel_id"] for row in result["synthetic:event:1"][1]]
        self.assertEqual(ids, ["gb.itv.one"])

    def test_guide_dates_tags_and_league_badges_are_ignored(self):
        event = fixture()
        for title, subtitle in (("Live Football", "North Harbor v Westshire 14.11"),
                                ("Live: Synthetic Cup [NEW]", "North Harbor v Westshire"),
                                ("Live: Synthetic Cup", "\u26bd [EPL] North Harbor v \u26bd [EPL] Westshire")):
            with self.subTest(subtitle=subtitle):
                result = linking.broadcast_candidates(
                    [event], {"farleyflex": guide([programme(title, subtitle=subtitle)])}, START,
                    identity_document=SPORTS_IDENTITY)
                self.assertIn(event["id"], result)

    def test_womens_only_competition_name_implies_the_womens_variant(self):
        womens = fixture(title="North Harbor W v Westshire W", competition="Synthetic Women's League",
                         participants=["North Harbor W", "Westshire W"], participants_short=[])
        for title in ("Live: WSL", "Live: NWSL"):
            with self.subTest(title=title):
                result = linking.broadcast_candidates(
                    [womens], {"farleyflex": guide([programme(title, subtitle="North Harbor v Westshire")])}, START,
                    identity_document=SPORTS_IDENTITY)
                self.assertIn(womens["id"], result)
        mens = fixture()
        result = linking.broadcast_candidates(
            [mens], {"farleyflex": guide([programme("Live: WSL", subtitle="North Harbor v Westshire")])}, START,
            identity_document=SPORTS_IDENTITY)
        self.assertNotIn(mens["id"], result)

    def test_guide_may_add_a_club_suffix_but_not_change_it(self):
        event = fixture(title="Harbor v Westshire", participants=["Harbor", "Westshire"], participants_short=[])
        result = linking.broadcast_candidates(
            [event], {"farleyflex": guide([programme("Live: Harbor Town v Westshire & Hove Albion")])}, START,
            identity_document=SPORTS_IDENTITY)
        self.assertIn(event["id"], result)
        city = fixture(title="Harbor City v Westshire", participants=["Harbor City", "Westshire"],
                       participants_short=[])
        result = linking.broadcast_candidates(
            [city], {"farleyflex": guide([programme("Live: Harbor United v Westshire")])}, START,
            identity_document=SPORTS_IDENTITY)
        self.assertNotIn(city["id"], result)

    def _regional_guide(self, listings):
        """listings: [(channel name, title)] all starting 10 minutes before kickoff."""
        channels = {"c%d" % i: name for i, (name, _) in enumerate(listings)}
        rows = [programme(title, "c%d" % i) for i, (_, title) in enumerate(listings)]
        return {"farleyflex": guide(rows, channels)}

    def test_event_on_every_nation_is_allocated_to_the_network_service(self):
        guides = self._regional_guide([("BBC One London HD", "Live: North Harbor v Westshire"),
                                       ("BBC One Scotland HD", "Live: North Harbor v Westshire"),
                                       ("BBC One Wales HD", "Live: North Harbor v Westshire")])
        rows = linking.broadcast_candidates([fixture()], guides, START)["synthetic:event:1"][1]
        self.assertEqual([(r["canonical_channel_id"], r["coverage"]) for r in rows], [("gb.bbc.one", "network")])
        self.assertNotIn("not_on", rows[0])
        self.assertEqual(rows[0]["channel_name"], "BBC One London HD")

    def test_event_on_one_nation_only_is_allocated_to_that_nation(self):
        guides = self._regional_guide([("BBC One HD", "Evening Magazine"),
                                       ("BBC One Wales HD", "Live: North Harbor v Westshire")])
        rows = linking.broadcast_candidates([fixture()], guides, START)["synthetic:event:1"][1]
        self.assertEqual([(r["canonical_channel_id"], r["coverage"], r["parent_channel_id"]) for r in rows],
                         [("gb.bbc.one.wales", "regional", "gb.bbc.one")])

    def test_nations_showing_something_else_are_listed_as_not_on(self):
        guides = self._regional_guide([("BBC Two HD", "Live: North Harbor v Westshire"),
                                       ("BBC Two Wales HD", "Soap Opera"),
                                       ("BBC Two NI HD", "Soap Opera")])
        rows = linking.broadcast_candidates([fixture()], guides, START)["synthetic:event:1"][1]
        self.assertEqual(rows[0]["canonical_channel_id"], "gb.bbc.two")
        self.assertEqual(rows[0]["coverage"], "network")
        self.assertEqual(rows[0]["not_on"], ["gb.bbc.two.ni", "gb.bbc.two.wales"])

    def test_same_slot_shortened_title_counts_as_simulcast(self):
        guides = self._regional_guide([("ITV1 London HD", "North Harbor v Westshire: Synthetic Cup"),
                                       ("STV Central HD", "Synthetic Cup"),
                                       ("UTV", "Quiz Night Special")])
        rows = linking.broadcast_candidates([fixture()], guides, START)["synthetic:event:1"][1]
        self.assertEqual(rows[0]["canonical_channel_id"], "gb.itv.one")
        self.assertEqual(rows[0]["not_on"], ["gb.utv"])          # STV simulcasts; UTV opted out

    def test_fixture_after_a_competition_prefix_matches(self):
        for subtitle in ("Northern Series: North Harbor v Westshire", "Synthetic Cup, Group A4: North Harbor v Westshire"):
            with self.subTest(subtitle=subtitle):
                result = linking.broadcast_candidates(
                    [fixture()], {"farleyflex": guide([programme("Live: Synthetic Cup", subtitle=subtitle)])}, START,
                    identity_document=SPORTS_IDENTITY)
                self.assertIn("synthetic:event:1", result)

    def test_welsh_home_nation_names_match(self):
        event = fixture(title="Wales v Westshire", participants=["Wales", "Westshire"], participants_short=[])
        result = linking.broadcast_candidates(
            [event], {"farleyflex": guide([programme("Sgorio: Cymru v Westshire")])}, START,
            identity_document=SPORTS_IDENTITY)
        self.assertIn(event["id"], result)

    def test_radio_commentary_on_a_tv_channel_is_never_a_candidate(self):
        event = fixture()
        for title in ("Live: Radio Commentary", "Live Audio Commentary"):
            with self.subTest(title=title):
                result = linking.broadcast_candidates(
                    [event], {"farleyflex": guide([programme(title, subtitle="Synthetic Cup: North Harbor v Westshire")])},
                    START, identity_document=SPORTS_IDENTITY)
                self.assertNotIn(event["id"], result)
        found = []
        linking.broadcast_candidates([], {"farleyflex": guide([programme("Live: Radio Commentary",
                                                                         subtitle="North Harbor v Westshire")])},
                                     START - timedelta(hours=1), guide_events=found)
        self.assertEqual(found, [])


class ForeignGuideIdTests(unittest.TestCase):
    """0.3.18 hard negative: a mixed guide's foreign id never becomes this market's service."""

    def test_mena_bein_in_a_french_guide_is_not_bein_france(self):
        from sportsliveinfo.guide import canonical_channel
        self.assertIsNone(canonical_channel("fr_mena_grab", "beINSports1.qa@MENA", "beIN SPORTS 1"))
        self.assertIsNone(canonical_channel("fr_mena_grab", "CanalPlusSport.ch", "Canal+ Sport"))
        self.assertEqual(canonical_channel("fr_mena_grab", "beINSPORTS1.fr", "FR - beIN SPORTS 1"), "fr.bein.sports.1")
        # Irish channels in UK guides and source-specific ids keep working.
        self.assertEqual(canonical_channel("iptv_epg_gb", "RTEOne.ie", "RTE One"), "ie.rte.one")
        self.assertEqual(canonical_channel("epgshare_ca", "TSN.4.HD.ca2", "TSN 4 HD"), "ca.tsn.4")


if __name__ == "__main__":
    unittest.main()
