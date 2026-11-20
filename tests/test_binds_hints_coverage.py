"""S2: the narrow binds rule (and its dry run and kill switch), channel hints, slot hints, the rights-holder prior,
the link-coverage histogram and the name aliases that close guide-title gaps (contract §4.3).

Cases come from the owner's report: weak foreign links (NBCUniverso.us for Bayern v Köln, hk.bein.* for a German
third-tier match, nz.sky.sport.* for a European fixture) must not name the channel showing the event.
"""
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from sportsliveinfo import feed, hints, link_report, linking
from sportsliveinfo.storage import Store

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("link_report_tool", ROOT / "tools" / "link_report.py")
TOOL = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(TOOL)

NOW = datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc)
KICKOFF = "2026-11-21T17:30:00+00:00"          # Saturday 17:30 London


def event(**kw):
    row = {"id": "e1", "sport": "football", "title": "Bayern Munich v 1. FC Koeln",
           "participants": ["Bayern Munich", "1. FC Koeln"], "competition": "Bundesliga",
           "competition_country": "Germany", "competition_id": "football.bundesliga", "start_utc": KICKOFF,
           "start_precision": "scheduled", "status_normalized": "scheduled", "tags": [],
           "broadcast_status": "single_guide_match"}
    row.update(kw)
    return row


def candidate(cid, sources, method="registry", confidence="high", start=KICKOFF):
    return {"canonical_channel_id": cid, "epg_sources": list(sources), "channel_identity_method": method,
            "match_confidence": confidence, "programme_start_utc": start, "coverage": "network"}


def guide(source_id, channel_id, name, title, start=KICKOFF):
    return {"source_id": source_id, "channels": {channel_id: name},
            "programmes": [{"channel_id": channel_id, "title": title, "subtitle": "", "start_utc": start,
                            "end_utc": "2026-11-21T19:30:00+00:00", "is_live": True}]}


# The weak foreign set from the report: one guide each, identified well ("high"), but not the owner's market.
BAYERN_KOLN = event(broadcast_candidates=[
    candidate("NBCUniverso.us", ["epgshare_us"], method="dictionary"),
    candidate("hk.bein.sports.1", ["epgshare_hk"]),
    candidate("nz.sky.sport.1", ["mjh_nz"]),
    candidate("gb.sky.sports.main_event", ["farleyflex"])])


class NarrowBindsRuleTests(unittest.TestCase):
    def links(self, row, rule="narrow", **policy):
        return {link["canonical_channel_id"]: link for link in feed._broadcast_links(
            row, False, feed.LinkPolicy(rule, **policy))}

    def test_weak_foreign_links_do_not_bind(self):
        links = self.links(BAYERN_KOLN)
        for weak in ("NBCUniverso.us", "hk.bein.sports.1", "nz.sky.sport.1"):
            self.assertFalse(links[weak]["binds"], weak)
            self.assertFalse(links[weak]["home_market"], weak)
        # The owner's market, curated, high confidence: still binds (single guide, not corroborated).
        self.assertTrue(links["gb.sky.sports.main_event"]["binds"])
        self.assertTrue(links["gb.sky.sports.main_event"]["home_market"])
        self.assertEqual(links["gb.sky.sports.main_event"]["status"], "guide_listed_unverified")

    def test_legacy_rule_is_the_kill_switch(self):
        links = self.links(BAYERN_KOLN, "legacy")
        self.assertEqual({cid: link["binds"] for cid, link in links.items()},
                         {"NBCUniverso.us": True, "hk.bein.sports.1": True, "nz.sky.sport.1": True,
                          "gb.sky.sports.main_event": True})

    def test_dictionary_only_id_never_binds_even_in_a_home_market(self):
        row = event(competition_country="England", broadcast_candidates=[
            candidate("BBCOne.uk@London", ["farleyflex"], method="dictionary")])
        self.assertFalse(self.links(row)["BBCOne.uk@London"]["binds"])
        self.assertTrue(self.links(row, "legacy")["BBCOne.uk@London"]["binds"])

    def test_event_home_market_binds_a_curated_channel(self):
        row = event(competition_country="France", broadcast_candidates=[candidate("fr.canal.sport", ["epgshare_fr"])])
        self.assertTrue(self.links(row)["fr.canal.sport"]["binds"])
        self.assertEqual(linking.event_home_markets(row), {"gb", "fr"})
        # The same channel for a German fixture is a foreign channel.
        self.assertFalse(self.links(dict(row, competition_country="Germany"))["fr.canal.sport"]["binds"])
        # National teams: England v France adds France through the tags; "World" adds nothing.
        self.assertEqual(linking.event_home_markets(event(competition_country="World", tags=["team:ireland"])),
                         {"gb", "ie"})
        self.assertEqual(linking.event_home_markets(event(competition_country="World")), {"gb"})

    def test_corroborated_links_bind_whatever_the_market(self):
        row = event(competition_country="World", broadcast_status="multi_guide_match", broadcast_candidates=[
            candidate("ie.rte.two", ["farleyflex", "epgtalk_uk"])])
        link = self.links(row)["ie.rte.two"]
        self.assertEqual(link["status"], "guide_corroborated")
        self.assertTrue(link["binds"])
        self.assertFalse(link["home_market"])

    def test_medium_confidence_never_binds(self):
        row = event(broadcast_candidates=[candidate("gb.itv.one", ["farleyflex"], confidence="medium")])
        self.assertFalse(self.links(row)["gb.itv.one"]["binds"])

    def test_rank_order_is_unchanged(self):
        self.assertEqual([c["canonical_channel_id"] for c in linking.rank_candidates(BAYERN_KOLN["broadcast_candidates"], BAYERN_KOLN)][0],
                         "gb.sky.sports.main_event")

    def test_policy_from_config(self):
        self.assertEqual(feed.link_policy({}), feed.LinkPolicy("narrow", True, False))
        self.assertEqual(feed.link_policy({"binds_rule": "legacy"}).binds_rule, "legacy")
        self.assertEqual(feed.link_policy({"binds_rule": "bogus"}).binds_rule, "narrow")     # never silently loosened
        self.assertFalse(feed.link_policy({"own_epg_corroboration": False}).own_epg)
        self.assertTrue(feed.link_policy({"rights_holder_prior": True}).rights_prior)

    def test_end_to_end_from_guides(self):
        """Real matcher path: three guides list Bayern v Köln (feed 'Koeln', guides 'Köln'/'Cologne')."""
        guides = {"epgshare_hk": guide("epgshare_hk", "beinsports1.hk", "beIN Sports 1", "Live: Bayern v Cologne"),
                  "mjh_nz": guide("mjh_nz", "ss1.nz", "Sky Sport 1", "Bayern Munich v Köln"),
                  "farleyflex": guide("farleyflex", "skysportsmainevent.uk", "Sky Sports Main Event",
                                      "Bayern Munich v FC Köln")}
        row = event()
        gaps = {}
        status, found = linking.broadcast_candidates([row], guides, NOW, gaps=gaps)["e1"]
        self.assertEqual({c["canonical_channel_id"] for c in found},
                         {"gb.sky.sports.main_event", "nz.sky.sport.1", "hk.bein.sports.1"})
        row = dict(row, broadcast_status=status, broadcast_candidates=found)
        narrow, legacy = self.links(row), self.links(row, "legacy")
        self.assertEqual({k: v["binds"] for k, v in legacy.items()},
                         {"gb.sky.sports.main_event": True, "nz.sky.sport.1": True, "hk.bein.sports.1": True})
        self.assertEqual({k: v["binds"] for k, v in narrow.items()},
                         {"gb.sky.sports.main_event": True, "nz.sky.sport.1": False, "hk.bein.sports.1": False})


class OwnEpgCorroborationTests(unittest.TestCase):
    def test_sky_own_epg_corroborates_sky_channel_only(self):
        row = event(competition_country="England", broadcast_status="single_guide_match")
        sky = candidate("gb.sky.sports.main_event", ["uk_freeview"])
        itv = candidate("gb.itv.one", ["uk_freeview"])
        self.assertEqual(linking.corroboration_rule(row, sky), linking.OWN_EPG_RULE)
        self.assertIsNone(linking.corroboration_rule(row, itv))
        self.assertIsNone(linking.corroboration_rule(row, sky, own_epg=False))
        link, = feed._broadcast_links(dict(row, broadcast_candidates=[sky]))
        self.assertEqual((link["status"], link["verification"], link["binds"]),
                         ("guide_corroborated", "broadcaster_own_epg_v1", True))
        off, = feed._broadcast_links(dict(row, broadcast_candidates=[sky]), False,
                                     feed.LinkPolicy(own_epg=False))
        self.assertEqual(off["status"], "guide_listed_unverified")
        # Two independent families keep the original rule label.
        both = candidate("gb.sky.sports.main_event", ["uk_freeview", "farleyflex"])
        self.assertEqual(linking.corroboration_rule(row, both), linking.CORROBORATION_RULE)


class DryRunTests(unittest.TestCase):
    """The dry run on a stored snapshot (what 'narrow' changes before it is on)."""

    def snapshot_events(self):
        third_tier = event(id="e2", title="Saarbruecken v Ulm", participants=["Saarbruecken", "Ulm"],
                           competition="3. Liga", competition_id=None, broadcast_candidates=[
                               candidate("hk.bein.sports.2", ["epgshare_hk"]),
                               candidate("gb.tnt.sports.1", ["farleyflex", "epgtalk_uk"])],
                           broadcast_status="multi_guide_match")
        epl = event(id="e3", title="Arsenal v Chelsea", participants=["Arsenal", "Chelsea"], competition="Premier League",
                    competition_country="England", competition_id="football.premier_league", broadcast_candidates=[
                        candidate("gb.sky.sports.premier_league", ["farleyflex"]),
                        candidate("ie.virgin.one", ["epgshare_ie"])])
        unlinked = event(id="e4", broadcast_status="none", broadcast_candidates=[], broadcast_gap="no_recognised_guide_slot")
        return [BAYERN_KOLN, third_tier, epl, unlinked]

    def test_report_counts_and_lists_demoted_links(self):
        report = link_report.dry_run_binds(self.snapshot_events(), titles=True)
        self.assertEqual((report["events"], report["links"]), (4, 8))
        self.assertEqual(report["false_to_true"], 0)                 # narrow never binds more than legacy
        self.assertGreater(report["binds_legacy"], report["binds_narrow"])
        self.assertEqual(report["true_to_false"], report["binds_legacy"] - report["binds_narrow"])
        self.assertEqual(report["true_to_false_by_market"], {"hk": 2, "ie": 1, "nz": 1, "us": 1})
        self.assertEqual(report["true_to_false_by_reason"], {"foreign_market": 4, "not_curated_channel": 1})
        demoted = {(row["event_id"], row["channel"]) for row in report["demoted"]}
        self.assertEqual(demoted, {("e1", "NBCUniverso.us"), ("e1", "hk.bein.sports.1"), ("e1", "nz.sky.sport.1"), ("e2", "hk.bein.sports.2"),
                                   ("e3", "ie.virgin.one")})
        self.assertEqual(report["events_with_binding"], {"legacy": 3, "narrow": 3})
        # The tool-facing copy may carry titles; the health copy never does.
        self.assertTrue(all("title" in row for row in report["demoted"]))
        self.assertFalse(any("title" in row for row in link_report.dry_run_binds(self.snapshot_events())["demoted"]))

    def test_dry_run_on_a_stored_snapshot_and_in_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "s.sqlite3")
            store.save_snapshot("sports", {"events": self.snapshot_events(), "generated_at": "2026-11-20T09:00:00+00:00"})
            report = TOOL.report_from_store(store)
            self.assertEqual(report["binds_dry_run"]["true_to_false"], 5)
            self.assertEqual(report["link_coverage"]["gaps"], {"no_recognised_guide_slot": 1})
            print("\nS2 dry run (stored snapshot):", json.dumps(
                {k: report["binds_dry_run"][k] for k in ("links", "binds_legacy", "binds_narrow", "true_to_false",
                                                         "true_to_false_by_market", "true_to_false_by_reason")}))

    def test_health_asset_carries_the_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "s.sqlite3")
            document = feed.health_document(store, store.config(), {}, self.snapshot_events(), private=True)
            self.assertEqual(document["binds_dry_run"]["true_to_false"], 5)
            self.assertEqual(document["binds_dry_run"]["active_rule"], "narrow")
            self.assertEqual(document["link_coverage"]["linked"], 3)
            self.assertNotIn("binds_dry_run", feed.health_document(store, store.config(), {}))   # still optional

    def test_default_is_narrow_and_kill_switch_reaches_the_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "s.sqlite3")
            self.assertEqual(store.config()["binds_rule"], "narrow")
            self.assertEqual(feed.build_feed(store, now=NOW)[0]["compatibility"]["binds_rule"], "narrow")
            store.configure({"binds_rule": "legacy"})
            self.assertEqual(feed.build_feed(store, now=NOW)[0]["compatibility"]["binds_rule"], "legacy")
            with self.assertRaises(ValueError):
                store.configure({"binds_rule": "loose"})


class LinkCoverageTests(unittest.TestCase):
    def test_gap_histogram_by_tier(self):
        rows = [event(id="a", broadcast_candidates=[candidate("gb.itv.one", ["farleyflex"])]),
                event(id="b", broadcast_gap="fixture_title_unmatched", broadcast_candidates=[]),
                event(id="c", broadcast_gap="fixture_title_unmatched", broadcast_candidates=[]),
                event(id="d", broadcast_gap="outside_guide_dates", broadcast_candidates=[], competition_id=None,
                      category_id="football.other", competition="Liga Nacional", competition_country="Honduras"),
                event(id="g", origin="guide_listing", broadcast_candidates=[candidate("gb.itv.one", ["farleyflex"])]),
                event(id="u", broadcast_candidates=[])]
        report = link_report.link_coverage(rows, tier_of=feed.event_tier)
        self.assertEqual((report["events"], report["linked"]), (5, 1))
        self.assertEqual(report["gaps"], {"fixture_title_unmatched": 2, "outside_guide_dates": 1, "unknown": 1})
        self.assertEqual(report["by_tier"]["extra"]["gaps"], {"outside_guide_dates": 1})
        self.assertEqual(report["by_tier"]["core"]["linked"], 1)

    def test_public_feed_excludes_loose_matcher_links(self):
        row = event(broadcast_status="guide_listing_match", broadcast_candidates=[candidate("gb.itv.one", ["farleyflex"])])
        self.assertEqual(link_report.link_coverage([row], private=False)["linked"], 0)
        self.assertEqual(link_report.link_coverage([row], private=True)["linked"], 1)


class NameAliasTests(unittest.TestCase):
    """Labelled guide-title cases through the real matcher: (feed home, feed away, guide title, should link)."""
    CASES = [
        ("Bayern Munich", "1. FC Koeln", "Live: Bayern v Köln", True),
        ("FC Bayern München", "1. FC Köln", "Bayern Munich v Cologne", True),
        ("Borussia Mönchengladbach", "FC Augsburg", "Gladbach v Augsburg", True),
        ("1. FC Nürnberg", "Fortuna Düsseldorf", "Nuremberg v Fortuna Duesseldorf", True),
        ("Borussia Dortmund", "Eintracht Frankfurt", "Dortmund v Frankfurt", True),
        ("Bayer 04 Leverkusen", "1. FSV Mainz 05", "Leverkusen v Mainz", True),
        ("Hannover 96", "Greuther Fürth", "Hanover v Greuther Fuerth", True),
        ("Paris Saint-Germain", "Olympique Marseille", "PSG v Marseille", True),
        ("Dynamo Kyiv", "Club Brugge", "Dynamo Kiev v Club Bruges", True),
        ("SC Paderborn 07", "SV Darmstadt 98", "Paderborn v Darmstadt", True),
        ("TSG 1899 Hoffenheim", "RB Leipzig", "Hoffenheim v Leipzig", True),
        ("Sporting CP", "Benfica", "Sporting Lisbon v Benfica", True),
        ("Hertha BSC", "Karlsruher SC", "Hertha Berlin v Karlsruhe", True),
        ("Sparta Praha", "Rapid Wien", "Sparta Prague v Rapid Vienna", True),
        # Must stay different teams.
        ("Bayern Munich", "Mainz", "Bayern Munich II v Mainz", False),
        ("Borussia Dortmund", "Bayern Munich", "Borussia Monchengladbach v Bayern Munich", False),
        ("Inter Miami", "Orlando City", "Inter v Orlando City", False),
        ("Real Madrid", "Barcelona", "Real Madrid Castilla v Barcelona", False),
        ("Olympique Lyonnais", "Paris Saint-Germain", "Olympique Marseille v PSG", False),
        ("RB Leipzig", "Bayern Munich", "RB Salzburg v Bayern Munich", False),
        ("Bayer 04 Leverkusen", "Mainz", "Bayern v Mainz", False),
        ("Mainz 05", "Arsenal", "Mainz v Arsenal 20 00", False),         # clock fragments are not club numbers
        ("Eintracht Frankfurt", "Arsenal", "Eintracht Braunschweig v Arsenal", False),
    ]

    def linked(self, home, away, title):
        row = event(id="n", participants=[home, away], title="%s v %s" % (home, away))
        guides = {"farleyflex": guide("farleyflex", "skysportsmainevent.uk", "Sky Sports Main Event", title)}
        return "n" in linking.broadcast_candidates([row], guides, NOW)

    def test_labelled_cases(self):
        wrong = [case for case in self.CASES if self.linked(*case[:3]) != case[3]]
        self.assertEqual(wrong, [])

    def test_labelled_accuracy_is_reported(self):
        hits = sum(self.linked(*case[:3]) == case[3] for case in self.CASES)
        print("\nS2 name aliases: %d/%d labelled guide-title cases correct" % (hits, len(self.CASES)))
        self.assertEqual(hits, len(self.CASES))


class ChannelHintsTests(unittest.TestCase):
    def setUp(self):
        self.doc = hints.channel_hints_document()

    def test_every_registry_service_has_a_hint_and_known_class(self):
        from sportsliveinfo.guide import REGIONAL_PARENTS, SERVICES
        ids = {cid for table in SERVICES.values() for cid in table.values()} | set(REGIONAL_PARENTS)
        self.assertEqual(set(self.doc["channels"]), ids)
        for cid, row in self.doc["channels"].items():
            self.assertIn(row["sports_class"], ("sports", "general", "news", "other"), cid)
            self.assertIn(row["tier"], (1, 2, 3, 4, 5), cid)

    def test_classes_and_tiers(self):
        c = self.doc["channels"]
        self.assertEqual((c["gb.sky.sports.main_event"]["sports_class"], c["gb.sky.sports.main_event"]["tier"]), ("sports", 1))
        self.assertEqual((c["gb.bbc.one"]["sports_class"], c["gb.bbc.one"]["tier"]), ("general", 2))
        self.assertEqual((c["gb.itv.one"]["sports_class"], c["gb.itv.one"]["tier"]), ("general", 2))
        self.assertEqual((c["gb.bbc.three"]["sports_class"], c["gb.bbc.three"]["tier"]), ("general", 3))
        self.assertEqual(c["gb.bbc.news"]["sports_class"], "news")
        self.assertEqual(c["gb.sky.sports.news"]["sports_class"], "news")
        self.assertEqual(c["gb.sky.mix"]["sports_class"], "general")
        self.assertEqual(c["gb.sky.sports.f1"]["sports"], ["motorsport"])
        self.assertEqual(c["gb.sky.sports.f1"]["broadcaster"], "sky_sports")
        self.assertEqual(c["gb.bbc.one.wales"]["parent"], "gb.bbc.one")
        self.assertEqual(c["gb.bbc.one.wales"]["tier"], 2)
        self.assertEqual(c["gb.tnt.sports.1"]["broadcaster"], "tnt_sports")

    def test_broadcaster_rank_tables(self):
        ids = {b["id"] for b in self.doc["broadcasters"]}
        for sport, order in self.doc["broadcaster_rank"].items():
            self.assertEqual(len(order), len(set(order)), sport)
            for bid in order:
                self.assertIn(bid, {b[0] for b in hints.BROADCASTERS}, (sport, bid))
        football = self.doc["broadcaster_rank"]["football"]
        self.assertEqual(football[:5], ["sky_sports", "tnt_sports", "bbc", "itv", "premier_sports"])
        self.assertIn("default", self.doc["broadcaster_rank"])
        self.assertLessEqual({"sky_sports", "tnt_sports", "bbc", "itv", "premier_sports"}, ids)

    def test_document_is_deterministic_and_compact(self):
        self.assertEqual(feed._json(hints.channel_hints_document()), feed._json(self.doc))
        self.assertLess(len(feed._json(self.doc)), 24_000)

    def test_asset_is_published_and_optional(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest, files = feed.build_feed(Store(Path(tmp) / "s.sqlite3"), now=NOW)
        asset, = [a for a in manifest["assets"] if a["kind"] == "channel_hints"]
        self.assertFalse(asset["required"])
        self.assertEqual(asset["schema"], "sli.channel-hints/1")
        self.assertIn("channel_hints", manifest["capabilities"])
        self.assertEqual(json.loads(files[asset["path"]])["schema"], "sli.channel-hints/1")


class SlotHintTests(unittest.TestCase):
    def test_window_matches_the_corroboration_window(self):
        hint = hints.slot_hint(event(start_utc="2026-11-14T15:00:00+00:00"))
        self.assertEqual(hint, {"starts_from_utc": "2026-11-14T14:00:00Z", "starts_to_utc": "2026-11-14T15:20:00Z",
                                "match": "teams"})
        self.assertEqual(hints.slot_hint(event(sport="motorsport", participants=[]))["match"], "session")
        self.assertEqual(hints.slot_hint(event(participants=[]))["match"], "tournament")

    def test_none_when_the_slot_cannot_be_said(self):
        self.assertIsNone(hints.slot_hint(event(start_precision="date_only")))
        self.assertIsNone(hints.slot_hint(event(start_precision="time_tbc")))
        self.assertIsNone(hints.slot_hint(event(status_normalized="postponed")))
        self.assertIsNone(hints.slot_hint(event(start_utc="garbage")))

    def test_published_only_on_events_with_links(self):
        linked = feed._event_public(event(broadcast_candidates=[candidate("gb.itv.one", ["farleyflex"])]))
        self.assertEqual(linked["slot_hint"]["match"], "teams")
        self.assertNotIn("slot_hint", feed._event_public(event()))


class RightsHolderPriorTests(unittest.TestCase):
    PL = dict(competition_id="football.premier_league", category_id="football.premier_league",
              competition="Premier League", competition_country="England",
              participants=["Arsenal", "Chelsea"], title="Arsenal v Chelsea")

    def test_off_by_default_feed_is_unchanged(self):
        row = event(**self.PL, start_utc="2026-11-22T16:30:00+00:00")           # Sunday
        self.assertEqual(feed._broadcast_links(row), [])
        self.assertEqual(feed._event_public(row).get("broadcast_links"), None)

    def test_prior_links_never_bind_and_rank_last(self):
        row = event(**self.PL, start_utc="2026-11-22T16:30:00+00:00")
        links = feed._broadcast_links(row, False, feed.LinkPolicy(rights_prior=True))
        self.assertEqual([l["canonical_channel_id"] for l in links],
                         ["gb.sky.sports.premier_league", "gb.sky.sports.main_event", "gb.tnt.sports.1"])
        for link in links:
            self.assertEqual((link["status"], link["binds"], link["confidence"], link["guides"]),
                             ("rights_holder_prior", False, "medium", 0))
            self.assertTrue(link["home_market"])
        self.assertEqual([l["rank"] for l in links], [1, 2, 3])

    def test_saturday_3pm_blackout_and_unconfirmed_times_get_no_prior(self):
        policy = feed.LinkPolicy(rights_prior=True)
        blackout = event(**self.PL, start_utc="2026-11-21T15:00:00+00:00")
        self.assertEqual(feed._broadcast_links(blackout, False, policy), [])
        self.assertEqual(feed._broadcast_links(dict(blackout, start_utc="2026-11-21T12:30:00+00:00"), False, policy)[0]["status"],
                         "rights_holder_prior")
        self.assertEqual(feed._broadcast_links(dict(blackout, start_precision="date_only"), False, policy), [])
        self.assertEqual(feed._broadcast_links(dict(blackout, start_utc="2026-11-22T16:30:00+00:00",
                                                    status_normalized="postponed"), False, policy), [])

    def test_no_prior_when_a_real_link_binds_or_competition_unknown(self):
        policy = feed.LinkPolicy(rights_prior=True)
        row = event(**self.PL, start_utc="2026-11-22T16:30:00+00:00",
                    broadcast_candidates=[candidate("gb.sky.sports.premier_league", ["farleyflex"])])
        links = feed._broadcast_links(row, False, policy)
        self.assertEqual([l["status"] for l in links], ["guide_listed_unverified"])
        self.assertEqual(feed._broadcast_links(event(), False, policy), [])      # Bundesliga: no prior
        weak = dict(row, broadcast_candidates=[candidate("hk.bein.sports.1", ["epgshare_hk"])])
        self.assertEqual([l["status"] for l in feed._broadcast_links(weak, False, policy)],
                         ["guide_listed_unverified"] + ["rights_holder_prior"] * 3)
        self.assertFalse(any(l["binds"] for l in feed._broadcast_links(weak, False, policy)))


if __name__ == "__main__":
    unittest.main()
