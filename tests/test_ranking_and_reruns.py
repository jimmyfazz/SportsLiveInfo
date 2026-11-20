"""0.3.24: channel ranking, re-run listings, FAST guide identities, rugby suffix merging and reader decisions in the feed.

Cases from the owner's report on 15 Nov 2026: Scotland v Australia and Spain v England listed an Irish or Asian
channel before ITV1 (found by five guides, corroborated for Spain v England), and Pluto's Rugby Pass TV re-run of
"England v Samoa - Rugby World Cup 2023" showed as "probably live".
"""
import unittest
from datetime import datetime, timezone

from sportsliveinfo import feed, linking


def candidate(cid, sources, method="registry", confidence="high", start="2026-11-15T19:30:00+00:00", coverage=None):
    row = {"canonical_channel_id": cid, "epg_sources": list(sources), "channel_identity_method": method,
           "match_confidence": confidence, "programme_start_utc": start}
    if coverage:
        row["coverage"] = coverage
    return row


SPAIN_ENGLAND = {"id": "api-sports:1", "title": "Spain v England", "sport": "football",
                 "start_utc": "2026-11-15T19:45:00+00:00", "start_precision": "scheduled",
                 "status_normalized": "scheduled", "broadcast_status": "multi_guide_match"}


class ChannelMarketTests(unittest.TestCase):
    def test_curated_and_dictionary_ids(self):
        self.assertEqual(linking.channel_market("gb.itv.one"), "gb")
        self.assertEqual(linking.channel_market("nz.sky.sport.1"), "nz")
        self.assertEqual(linking.channel_market("VirginMediaTwo.ie"), "ie")
        self.assertEqual(linking.channel_market("PremierSports1Asia.ie"), "ie")
        self.assertEqual(linking.channel_market("BBCOne.uk@London"), "gb")
        self.assertEqual(linking.channel_market(""), "")


class CandidateRankTests(unittest.TestCase):
    def test_itv_first_for_spain_v_england(self):
        """The old id sort put "VirginMediaTwo.ie" (capital V) before "gb.itv.one"."""
        found = [candidate("VirginMediaTwo.ie", ["epgshare_ie"], method="dictionary"),
                 candidate("gb.itv.one", ["farleyflex", "uk_freeview", "epgtalk_uk", "m3upt_sky", "epgshare_uk"])]
        ranked = linking.rank_candidates(found, SPAIN_ENGLAND)
        self.assertEqual([c["canonical_channel_id"] for c in ranked], ["gb.itv.one", "VirginMediaTwo.ie"])

    def test_corroborated_beats_home_market(self):
        event = dict(SPAIN_ENGLAND)
        found = [candidate("gb.channel.four", ["farleyflex"]),
                 candidate("ie.rte.two", ["farleyflex", "epgtalk_uk"])]
        corroborated = [c for c in found if linking.guide_corroborated(event, c)]
        self.assertEqual([c["canonical_channel_id"] for c in corroborated], ["ie.rte.two"])
        self.assertEqual(linking.rank_candidates(found, event)[0]["canonical_channel_id"], "ie.rte.two")

    def test_home_market_then_curated_then_guides(self):
        found = [candidate("nz.sky.sport.1", ["mjh_nz", "epgshare_nz"]),
                 candidate("PremierSports1Asia.ie", ["epgshare_ie"], method="dictionary"),
                 candidate("ie.virgin.one", ["epgshare_ie"]),
                 candidate("gb.itv.one", ["farleyflex"])]
        ranked = [c["canonical_channel_id"] for c in linking.rank_candidates(found)]
        self.assertEqual(ranked[0], "gb.itv.one")
        self.assertEqual(ranked[-1], "PremierSports1Asia.ie")       # dictionary-only id, one guide
        self.assertLess(ranked.index("nz.sky.sport.1"), ranked.index("ie.virgin.one"))  # more guides

    def test_network_before_regional_and_stable_tie_break(self):
        found = [candidate("gb.bbc.one.wales", ["farleyflex"], coverage="regional"),
                 candidate("gb.bbc.one", ["farleyflex"])]
        self.assertEqual(linking.rank_candidates(found)[0]["canonical_channel_id"], "gb.bbc.one")
        same = [candidate("gb.b", ["farleyflex"]), candidate("gb.a", ["farleyflex"])]
        self.assertEqual([c["canonical_channel_id"] for c in linking.rank_candidates(same)], ["gb.a", "gb.b"])


class PublishedLinkTests(unittest.TestCase):
    def test_links_best_first_with_rank_and_binds(self):
        event = dict(SPAIN_ENGLAND, broadcast_candidates=[
            candidate("VirginMediaTwo.ie", ["epgshare_ie"], method="dictionary", confidence="medium"),
            candidate("gb.itv.one", ["farleyflex", "uk_freeview", "epgtalk_uk"])])
        links = feed._broadcast_links(event)
        self.assertEqual([link["canonical_channel_id"] for link in links], ["gb.itv.one", "VirginMediaTwo.ie"])
        self.assertEqual([link["rank"] for link in links], [1, 2])
        self.assertEqual(links[0]["status"], "guide_corroborated")
        self.assertEqual([link["binds"] for link in links], [True, False])


class LiveUntilTests(unittest.TestCase):
    def test_live_until_is_the_earlier_of_age_and_end_limits(self):
        self.assertEqual(feed.live_until("live", "2026-11-15T15:30:00Z", "2026-11-15T15:00:00Z",
                                         "2026-11-15T17:00:00+00:00"), "2026-11-15T16:15:00Z")
        self.assertEqual(feed.live_until("live", "2026-11-15T17:20:00Z", "2026-11-15T15:00:00Z",
                                         "2026-11-15T17:00:00+00:00"), "2026-11-15T17:30:00Z")

    def test_no_live_until_unless_live_and_observed(self):
        self.assertIsNone(feed.live_until("scheduled", "2026-11-15T15:30:00Z", "2026-11-15T15:00:00Z",
                                          "2026-11-15T17:00:00Z"))
        self.assertIsNone(feed.live_until("live", None, "2026-11-15T15:00:00Z", "2026-11-15T17:00:00Z"))
        # An observation long before kick-off never makes a window.
        self.assertIsNone(feed.live_until("live", "2026-11-15T13:00:00Z", "2026-11-15T15:00:00Z",
                                          "2026-11-15T17:00:00Z"))

    def test_event_row_carries_live_until(self):
        event = {"id": "x", "title": "A v B", "sport": "football", "start_utc": "2026-11-15T15:00:00+00:00",
                 "start_precision": "scheduled", "status_normalized": "live",
                 "status_observed_at": "2026-11-15T15:40:00Z", "participants": ["A", "B"]}
        row = feed._event_public(event)
        self.assertEqual(row["live_until_utc"], "2026-11-15T16:25:00Z")
        self.assertNotIn("live_until_utc", feed._event_public(dict(event, status_normalized="scheduled")))


class RerunTests(unittest.TestCase):
    def test_past_year_and_seasons(self):
        self.assertTrue(linking.names_past_year("England v Samoa", "Rugby World Cup 2023, Pool D", 2026))
        self.assertTrue(linking.names_past_year("Highlights", "2023-24 season", 2026))
        self.assertFalse(linking.names_past_year("Premiership Rugby", "2025/26", 2026))
        self.assertFalse(linking.names_past_year("Champions League", "2026-2027", 2026))
        self.assertFalse(linking.names_past_year("World Darts Championship 2027", "", 2026))
        self.assertFalse(linking.names_past_year("Live: Arsenal v Spurs", "Kick-off 20:00", 2026))
        # Season-boundary cases: 2024/25 is a past season when current_year=2026
        self.assertTrue(linking.names_past_year("Premier League", "2024/25 Season", 2026))
        self.assertTrue(linking.names_past_year("FA Cup", "2024-25", 2026))
        # Current and future seasons must not be filtered
        self.assertFalse(linking.names_past_year("FA Cup", "2026/27", 2026))
        self.assertFalse(linking.names_past_year("Premier League", "2026/27 Season", 2026))

    def test_rerun_never_becomes_a_guide_listed_live_event(self):
        now = datetime(2026, 11, 15, 9, 0, tzinfo=timezone.utc)
        guide = {"channels": {"ss1": "Sky Sports Main Event"}, "programmes": [
            {"channel_id": "ss1", "title": "Live: England v Samoa", "subtitle": "Rugby World Cup 2023, Pool D",
             "start_utc": "2026-11-15T09:11:00+00:00", "end_utc": "2026-11-15T11:00:00+00:00", "is_live": True},
            {"channel_id": "ss1", "title": "Live: England v Japan", "subtitle": "Nations Championship",
             "start_utc": "2026-11-15T12:00:00+00:00", "end_utc": "2026-11-15T14:00:00+00:00", "is_live": True}]}
        guide_events = []
        linking.broadcast_candidates([], {"farleyflex": guide}, now, guide_events=guide_events)
        titles = [event["title"] for event in guide_events]
        self.assertFalse(any("Samoa" in title for title in titles), titles)
        self.assertTrue(any("Japan" in title for title in titles), titles)


class FastGuideTests(unittest.TestCase):
    def test_fast_guides_never_use_the_dictionary(self):
        self.assertTrue(linking.is_fast_guide("mjh_pluto_gb"))
        self.assertTrue(linking.is_fast_guide("mjh_samsung_gb"))
        self.assertFalse(linking.is_fast_guide("farleyflex"))

        class Resolver:
            channels = {"PremierSports1Asia.ie": {}}

            def resolve(self, name, market):
                return {"confidence": "high", "id": "PremierSports1Asia.ie", "channel": "PremierSports1Asia.ie"}

        self.assertIsNone(linking._dictionary_hit(Resolver(), "mjh_pluto_gb", "Rugby Pass TV", "66f137cb"))


class RugbySuffixMergeTests(unittest.TestCase):
    def rugby(self, eid, source, title, home, away, start="2026-11-15T15:10:00+00:00"):
        return {"id": eid, "source_id": source, "sport": "rugby", "title": title, "participants": [home, away],
                "start_utc": start, "start_precision": "scheduled", "status_normalized": "scheduled"}

    def test_thesportsdb_rugby_names_merge(self):
        merged = linking.merge_events([
            self.rugby("a:1", "api_sports_rugby", "Scotland v Australia", "Scotland", "Australia"),
            self.rugby("t:1", "thesportsdb", "Scotland Rugby vs Australia Rugby", "Scotland Rugby", "Australia Rugby"),
            self.rugby("a:2", "api_sports_rugby", "Worcester Warriors v Ampthill", "Worcester Warriors", "Ampthill",
                       "2026-11-15T16:00:00+00:00"),
            self.rugby("t:2", "thesportsdb", "Worcester Warriors vs Ampthill RUFC", "Worcester Warriors",
                       "Ampthill RUFC", "2026-11-15T16:00:00+00:00")])
        self.assertEqual(len(merged), 2)
        self.assertTrue(all(event["fixture_confidence"] == "corroborated" for event in merged))

    def test_different_clubs_and_football_unchanged(self):
        merged = linking.merge_events([
            self.rugby("a:1", "api_sports_rugby", "Bath v Gloucester", "Bath", "Gloucester"),
            self.rugby("t:1", "thesportsdb", "Bath Rugby vs Leicester Tigers", "Bath Rugby", "Leicester Tigers")])
        self.assertEqual(len(merged), 2)
        football = [dict(self.rugby("f:1", "api_sports", "Lens v Lille", "Lens", "Lille"), sport="football"),
                    dict(self.rugby("f:2", "football_data", "RC Lens v Lille", "RC Lens", "Lille"), sport="football")]
        self.assertEqual(len(linking.merge_events(football)), 2)     # rugby words stay rugby-only


if __name__ == "__main__":
    unittest.main()
