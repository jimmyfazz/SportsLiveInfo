"""The baseline B1G provider EPG is never modified by SportsLiveInfo."""
import copy
import unittest

from sportsliveinfo.supplement import suggest_programme_enrichment


class SupplementTests(unittest.TestCase):
    def setUp(self):
        self.baseline = {"title": "Live Football", "canonical_channel_id": "gb.sky.sports.main_event",
                         "start_utc": "2026-11-14T14:30:00+00:00",
                         "end_utc": "2026-11-14T17:30:00+00:00"}
        self.candidate = {"title": "Arsenal v Manchester City",
                          "canonical_channel_id": "gb.sky.sports.main_event",
                          "canonical_event_id": "match:123",
                          "start_utc": "2026-11-14T14:00:00+00:00",
                          "end_utc": "2026-11-14T17:15:00+00:00",
                          "source_id": "farleyflex"}
        self.event = {"id": "match:123", "start_utc": "2026-11-14T15:00:00+00:00",
                      "broadcast_verified": True, "broadcast_verification_rule": "approved_v1",
                      "broadcasts": [{"canonical_channel_id": "gb.sky.sports.main_event",
                                      "territory": "GB", "transmission": "live",
                                      "evidence": "verified_programme"}]}

    def propose(self, **changes):
        return suggest_programme_enrichment(
            self.baseline, self.candidate, self.event,
            expected_channel=changes.pop("expected_channel", "gb.sky.sports.main_event"),
            territory=changes.pop("territory", "GB"), **changes)

    def test_approved_proposal_never_mutates_original_schedule(self):
        original = copy.deepcopy(self.baseline)
        result = self.propose()
        self.assertEqual(result["status"], "suggestion_only")
        self.assertEqual(result["display_title"], "Arsenal v Manchester City")
        self.assertEqual(self.baseline, original)
        self.assertEqual(self.baseline["title"], "Live Football")

    def test_manual_and_hidden_channels_are_never_overlaid(self):
        self.assertIsNone(self.propose(hidden=True))
        self.assertIsNone(self.propose(user_override=True))

    def test_wrong_broadcaster_country_or_event_is_rejected(self):
        self.assertIsNone(self.propose(expected_channel="gb.sky.sports.f1"))
        self.assertIsNone(self.propose(territory="FR"))
        self.candidate["canonical_event_id"] = "wrong:456"
        self.assertIsNone(self.propose())

    def test_guide_match_without_approved_independent_evidence_is_not_enough(self):
        self.event["broadcast_verification_rule"] = "not_reviewed"
        self.assertIsNone(self.propose())

    def test_highlights_replay_and_unverified_flags_rejected(self):
        self.event["transmission"] = "highlights"
        self.assertIsNone(self.propose())
        self.event["transmission"] = "live"
        self.event["broadcast_verified"] = False
        self.assertIsNone(self.propose())

    def test_conflicting_or_missing_intervals_rejected(self):
        self.candidate["start_utc"] = "2026-11-14T18:00:00+00:00"
        self.assertIsNone(self.propose())
        self.candidate["start_utc"] = "2026-11-14T14:00:00+00:00"
        self.baseline["start_utc"] = "unqualified"
        self.assertIsNone(self.propose())


if __name__ == "__main__":
    unittest.main()
