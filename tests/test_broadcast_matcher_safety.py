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

    def test_regional_service_helper_groups_only_explicit_regions(self):
        regions = {"north", "west"}
        args = {"market": "GB", "base_name": "example one", "regions": regions,
                "canonical_id": "gb.example.one"}
        self.assertEqual(linking._regional_service_id("farleyflex", "Example One North", **args), "gb.example.one")
        self.assertEqual(linking._regional_service_id("farleyflex", "Example One West", **args), "gb.example.one")
        self.assertIsNone(linking._regional_service_id("farleyflex", "Example One East", **args))
        self.assertIsNone(linking._regional_service_id("epgshare_fr", "Example One North", **args))


if __name__ == "__main__":
    unittest.main()
