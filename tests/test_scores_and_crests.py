"""Scores (sli/1.7) and crest references together: both must stay aligned when events merge and sides swap."""
import json

from sportsliveinfo import feed, linking, providers
from test_crest_refs import _row
from test_live_tiers_corroboration import NOW, StoreCase
from test_scores import day_events, row, seed
from test_feed import load_schema, validate


def api_sports_final(home, away, home_id, away_id, goals):
    payload = json.dumps({"paging": {"current": 1, "total": 1}, "response": [{
        "fixture": {"id": 1, "date": "2026-11-14T15:00:00+00:00", "status": {"short": "FT"}},
        "league": {"id": 39, "name": "Premier League", "country": "England"},
        "teams": {"home": _row(home_id, home), "away": _row(away_id, away)},
        "goals": {"home": goals[0], "away": goals[1]}}]}).encode()
    event, = providers.api_sports_events(payload)
    return event


class CombinedTests(StoreCase):
    def contributors(self):
        # football_data is primary and lists Tottenham first; API-Sports lists Chelsea first (sides swapped) and is the
        # only contributor that carries crest references. Its own score is Chelsea 2, Tottenham 1.
        primary = row("football_data", "football-data:1", ["Tottenham Hotspur FC", "Chelsea FC"])
        other = api_sports_final("Chelsea", "Tottenham Hotspur", 49, 47, (2, 1))
        other["status_observed_at"] = "2026-11-14T17:00:00+00:00"
        return primary, other

    def test_merge_aligns_scores_and_crests_to_the_primary_order_together(self):
        primary, other = self.contributors()
        self.assertEqual(other["score"]["home"], 2)
        merged, = linking.merge_events([primary, other])
        self.assertEqual(merged["participants"], ["Tottenham Hotspur FC", "Chelsea FC"])
        self.assertEqual([c["ref"] for c in merged["participant_crests"]], ["football/teams/47", "football/teams/49"])
        aligned = merged["scores"][other["id"]]
        self.assertEqual((aligned["home"], aligned["away"]), (1, 2))
        self.assertEqual(merged["score_align"][other["id"]], -1)
        self.assertNotIn("score", merged)

    def test_feed_publishes_both_when_both_are_enabled(self):
        primary, other = self.contributors()
        seed(self.store, {"football_data": [primary], "api_sports": [other]},
             score_approvals=["api_sports", "football_data"], publish_crest_refs=True)
        manifest, files = feed.build_feed(self.store, now=NOW)
        for capability in ("scores", "team_crests"):
            self.assertIn(capability, manifest["capabilities"])
        self.assertEqual(manifest["rights"]["scores"], {"approved_sources": ["api_sports", "football_data"]})
        self.assertTrue(manifest["rights"]["crests"]["sources"]["apisports"]["enabled"])
        event, = day_events(files, manifest).values()
        self.assertEqual(event["participants"], ["Tottenham Hotspur FC", "Chelsea FC"])
        self.assertEqual([c["ref"] for c in event["participant_crests"]], ["football/teams/47", "football/teams/49"])
        self.assertEqual((event["score"]["home"], event["score"]["away"]), (1, 2))
        schema = load_schema("sli.events-day/1")
        validate(event, schema["properties"]["events"]["items"], schema)
        schema = load_schema("sli.manifest/1")
        validate(manifest, schema, schema)

    def test_scores_only_and_crests_only_do_not_leak_into_each_other(self):
        primary, other = self.contributors()
        seed(self.store, {"football_data": [primary], "api_sports": [other]}, score_approvals=["api_sports"])
        manifest, files = feed.build_feed(self.store, now=NOW)
        event, = day_events(files, manifest).values()
        self.assertIn("score", event)
        self.assertNotIn("participant_crests", event)
        self.assertNotIn("team_crests", manifest["capabilities"])
        self.assertTrue(manifest["rights"]["crests"]["monogram_only"])
        self.store.configure({"score_approvals": [], "publish_crest_refs": True})
        manifest, files = feed.build_feed(self.store, now=NOW)
        event, = day_events(files, manifest).values()
        self.assertNotIn("score", event)
        self.assertIn("participant_crests", event)
        self.assertNotIn("scores", manifest["rights"])
