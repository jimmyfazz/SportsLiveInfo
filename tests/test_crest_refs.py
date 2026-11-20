"""Team crest references (capability team_crests): decoders, merge alignment, kill switch, manifest block."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from sportsliveinfo import feed, linking, providers
from sportsliveinfo.storage import Store
from test_feed import load_schema, validate

NOW = datetime(2026, 11, 14, 14, 0, tzinfo=timezone.utc)


def _row(team_id, name):
    return {"id": team_id, "name": name, "logo": "https://media.api-sports.io/football/teams/%s.png" % team_id}


def api_payload(home, away, fixture_id=1, start="2026-11-14T15:00:00+00:00"):
    return json.dumps({"paging": {"current": 1, "total": 1}, "response": [{
        "fixture": {"id": fixture_id, "date": start, "status": {"short": "NS"}},
        "league": {"id": 39, "name": "Premier League", "country": "England"},
        "teams": {"home": home, "away": away}}]}).encode()


def other(source_id, home, away, event_id, start="2026-11-14T15:05:00+00:00"):
    return {"id": event_id, "source_id": source_id, "sport": "football", "title": "%s v %s" % (home, away),
            "participants": [home, away], "start_utc": start, "start_precision": "scheduled",
            "status_normalized": "scheduled"}


def apisports(home, away, home_id=42, away_id=50):
    return providers.api_sports_events(api_payload(_row(home_id, home), _row(away_id, away)))[0]


class DecoderTests(unittest.TestCase):
    def test_football_decoder_carries_team_ids_as_references_not_logo_urls(self):
        event = apisports("Arsenal", "Manchester City")
        self.assertEqual(event["participant_crests"], [{"src": "apisports", "ref": "football/teams/42"},
                                                       {"src": "apisports", "ref": "football/teams/50"}])
        self.assertNotIn("http", json.dumps(event["participant_crests"]))

    def test_missing_id_gives_null_and_no_ids_gives_no_field(self):
        event = providers.api_sports_events(api_payload({"name": "Arsenal"}, _row(50, "Chelsea")))[0]
        self.assertEqual(event["participant_crests"], [None, {"src": "apisports", "ref": "football/teams/50"}])
        self.assertNotIn("participant_crests", providers.api_sports_events(api_payload({"name": "A"}, {"name": "B"}))[0])

    def test_games_decoder_uses_the_product_path(self):
        data = json.dumps({"response": [{"id": 7, "timestamp": 1794000000, "status": {"short": "NS"},
                                         "league": {"id": 1, "name": "L"}, "country": {"name": "World"},
                                         "teams": {"home": {"id": 3, "name": "Scotland"},
                                                   "away": {"id": 4, "name": "Fiji"}}}]}).encode()
        rugby = providers.api_sports_games_events(data, "api_sports_rugby", "rugby")[0]
        self.assertEqual(rugby["participant_crests"][0], {"src": "apisports", "ref": "rugby/teams/3"})
        nfl = providers.api_sports_games_events(data, "api_sports_nfl", "american_football")[0]
        self.assertEqual(nfl["participant_crests"][1]["ref"], "american-football/teams/4")


class MergeAlignmentTests(unittest.TestCase):
    def merged(self, *events):
        out = linking.merge_events(list(events))
        self.assertEqual(len(out), 1)
        return out[0]

    def test_single_source_keeps_its_own_order(self):
        self.assertEqual([c["ref"] for c in self.merged(apisports("Arsenal", "Chelsea"))["participant_crests"]],
                         ["football/teams/42", "football/teams/50"])

    def test_merge_with_same_order_aligns(self):
        event = self.merged(apisports("Arsenal", "Chelsea"), other("football_data", "Arsenal FC", "Chelsea FC", "fd:1"))
        self.assertEqual(event["sources"], ["api_sports", "football_data"])
        self.assertEqual([c["ref"] for c in event["participant_crests"]], ["football/teams/42", "football/teams/50"])

    def test_home_away_swapped_primary_gets_swapped_crests(self):
        # football_data has the better start precision rank, so it is primary and lists Chelsea first.
        fd = other("football_data", "Chelsea", "Arsenal", "fd:2")
        event = self.merged(apisports("Arsenal", "Chelsea"), fd)
        self.assertEqual(event["participants"], ["Chelsea", "Arsenal"])
        self.assertEqual([c["ref"] for c in event["participant_crests"]], ["football/teams/50", "football/teams/42"])

    def test_primary_is_the_apisports_record_when_swapped_source_is_secondary(self):
        fd = other("openligadb", "Chelsea", "Arsenal", "ol:2")
        event = self.merged(fd, apisports("Arsenal", "Chelsea"))
        for index, name in enumerate(event["participants"]):
            expected = {"Arsenal": "football/teams/42", "Chelsea": "football/teams/50"}[name]
            self.assertEqual(event["participant_crests"][index]["ref"], expected)

    def test_conflicting_crests_for_one_side_give_null_for_that_side(self):
        event = self.merged(apisports("Arsenal", "Chelsea"), apisports("Arsenal", "Chelsea", 42, 99) | {
            "id": "api-sports-rugby:1", "source_id": "api_sports_rugby"})
        self.assertEqual(event["participant_crests"][0]["ref"], "football/teams/42")
        self.assertIsNone(event["participant_crests"][1])

    def test_uncertain_orientation_gives_no_crests(self):
        # Both sides share a name stem, so straight and swapped both match: orientation is unknowable.
        a = apisports("Real", "Real")
        b = other("football_data", "Real", "Real", "fd:3")
        self.assertNotIn("participant_crests", self.merged(a, b))

    def test_event_without_crest_sources_has_no_field(self):
        self.assertNotIn("participant_crests", self.merged(other("football_data", "Arsenal", "Chelsea", "fd:4")))


class FeedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "s.sqlite3")
        self.addCleanup(self.temp.cleanup)
        event = dict(apisports("Arsenal", "Chelsea"), category_id="football.premier_league",
                     participants_short=["Arsenal", "Chelsea"])
        self.store.save_snapshot("sports", {"events": [event]})

    def configure(self, approvals, flag, **extra):
        self.store.configure(dict({"setup_complete": True, "publication_approvals": approvals,
                                   "publish_crest_refs": flag}, **extra))

    def build(self):
        manifest, files = feed.build_feed(self.store, now=NOW)
        rows = [e for path, data in files.items() if "/assets/events/" in path for e in json.loads(data)["events"]]
        return manifest, rows

    def test_default_off_publishes_no_crests_and_manifest_says_monogram_only(self):
        self.configure(["api_sports"], False)
        manifest, rows = self.build()
        self.assertTrue(rows)
        self.assertTrue(all("participant_crests" not in row for row in rows))
        crests = manifest["rights"]["crests"]
        self.assertTrue(crests["monogram_only"])
        self.assertFalse(crests["sources"]["apisports"]["enabled"])
        self.assertNotIn("team_crests", manifest["capabilities"])
        validate(manifest, load_schema("sli.manifest/1"), load_schema("sli.manifest/1"))

    def test_revision_is_unchanged_by_the_kill_switch_when_off(self):
        self.configure(["api_sports"], False)
        off = self.build()[0]["revision"]
        self.configure(["api_sports"], False, crest_device_lookup_thesportsdb=True)
        self.assertEqual(self.build()[0]["revision"], off)

    def test_enabled_publishes_aligned_references_and_capability(self):
        self.configure(["api_sports"], True)
        manifest, rows = self.build()
        self.assertEqual([c["ref"] for c in rows[0]["participant_crests"]], ["football/teams/42", "football/teams/50"])
        self.assertEqual(len(rows[0]["participant_crests"]), len(rows[0]["participants"]))
        self.assertIn("team_crests", manifest["capabilities"])
        crests = manifest["rights"]["crests"]
        self.assertFalse(crests["monogram_only"])
        self.assertEqual(crests["sources"]["apisports"]["url_template"], "https://media.api-sports.io/{ref}.png")
        self.assertEqual(manifest["compatibility"]["min_reader_minor"], 0)
        schema = load_schema("sli.events-day/1")
        for row in rows:
            validate(row, schema["properties"]["events"]["items"], schema)
        validate(manifest, load_schema("sli.manifest/1"), load_schema("sli.manifest/1"))

    def test_flag_without_approval_publishes_nothing(self):
        self.configure(["openligadb"], True)
        manifest, rows = self.build()
        self.assertFalse(manifest["rights"]["crests"]["sources"]["apisports"]["enabled"])
        self.assertNotIn("team_crests", manifest["capabilities"])
        self.assertTrue(all("participant_crests" not in row for row in rows))

    def test_malformed_references_are_dropped(self):
        self.assertIsNone(feed._crests_public({"participants": ["A", "B"], "participant_crests": [
            {"src": "apisports", "ref": "../x"}, {"src": "other", "ref": "football/teams/1"}]}))
        self.assertIsNone(feed._crests_public({"participants": ["A"], "participant_crests": [None, None]}))
        self.assertEqual(feed._crests_public({"participants": ["A", "B"], "participant_crests": [
            {"src": "apisports", "ref": "football/teams/1"}, None]}),
            [{"src": "apisports", "ref": "football/teams/1"}, None])


if __name__ == "__main__":
    unittest.main()
