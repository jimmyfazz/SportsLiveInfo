"""Event metadata (contract 4.3): icons and sport order, short names, participant ids, competition logos, feature_rank,
ordering, PPV, F1 weekends, tag publication and the extra tier. Examples are real fixtures or payload shapes."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from sportsliveinfo import feed, linking, metadata, providers, taxonomy
from sportsliveinfo.storage import Store
from test_crest_refs import api_payload, apisports
from test_feed import fixtures_tool, load_schema, validate

NOW = datetime(2026, 11, 14, 14, 0, tzinfo=timezone.utc)
SCHEMA = load_schema("sli.events-day/1")
EVENT_SCHEMA = SCHEMA["properties"]["events"]["items"]


def ev(event_id, source="football_data", **kw):
    row = {"id": event_id, "source_id": source, "sport": "football", "competition": "Premier League",
           "competition_country": "England", "event_type": "match", "title": "A v B", "participants": ["A", "B"],
           "start_utc": "2026-11-14T15:00:00+00:00", "start_precision": "scheduled", "status_normalized": "scheduled",
           "broadcasts": [], "broadcast_verified": False}
    row.update(kw)
    return row


class Builder(unittest.TestCase):
    def build(self, events, approvals=("football_data", "api_sports", "jolpica", "api_sports_rugby", "openf1",
                                      "thesportsdb"), **conf):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "s.sqlite3")
            store.configure(dict({"setup_complete": True, "publication_approvals": list(approvals)}, **conf))
            store.save_snapshot("sports", {"events": linking.merge_events([taxonomy.classify(e) for e in events])})
            manifest, files = feed.build_feed(store, now=NOW)
        rows, extra, today = {}, {}, None
        for path, data in files.items():
            doc = json.loads(data)
            if "/assets/events/" in path:
                rows.update({e["id"]: e for e in doc["events"]})
            elif "/assets/events_extra/" in path:
                extra.update({e["id"]: e for e in doc["events"]})
            elif "/assets/today/" in path:
                today = doc
        return manifest, rows, extra, today


class TaxonomyMetadataTests(unittest.TestCase):
    def setUp(self):
        self.doc = feed.taxonomy_document()

    def test_every_sport_has_icon_key_and_order(self):
        for sport in self.doc["sports"]:
            self.assertTrue(sport["icon_key"], sport["id"])
            self.assertIsInstance(sport["order"], int)
        self.assertEqual({s["id"] for s in self.doc["sports"]}, set(taxonomy.SPORTS))

    def test_competition_icon_keys_only_where_available(self):
        by_id = {c["id"]: c for c in self.doc["competitions"]}
        self.assertEqual(by_id["football.premier_league"]["icon_key"], "premier_league")
        self.assertEqual(by_id["motorsport.f1"]["icon_key"], "formula_1")
        self.assertNotIn("icon_key", by_id["football.liga_3"])
        self.assertTrue(set(metadata.COMPETITION_ICON_KEYS) <= set(by_id))
        self.assertTrue(set(metadata.FEATURED_COMPETITION_IDS) <= set(by_id))

    def test_default_sport_order_has_the_eight_groups_b1g_lacks_and_matches_priority_groups(self):
        order = self.doc["default_sport_order"]
        for group in ("Horse racing", "Handball", "Volleyball", "Esports", "Bowling", "Netball",
                      "Australian rules football", "Other sport"):
            self.assertIn(group, order)
        self.assertEqual(len(order), len(set(order)))
        groups = {s["b1g_priority_group"] for s in self.doc["sports"]} | \
                 {c["b1g_priority_group"] for c in self.doc["competitions"]}
        self.assertEqual(set(order), groups)             # b1g_priority_group stays in step with the published order
        self.assertEqual(order[0], "Football")
        self.assertLess(order.index("Formula 1"), order.index("Rugby"))   # taxonomy order: motorsport 15 before rugby 20

    def test_taxonomy_validates_and_manifest_publishes_the_same_order(self):
        schema = load_schema("sli.taxonomy/1")
        validate(self.doc, schema, schema)
        manifest, _files = fixtures_tool.build()
        self.assertEqual(manifest["display_policy"]["sport_order"], self.doc["default_sport_order"])
        self.assertIn("football.premier_league", manifest["display_policy"]["featured_competition_ids"])
        for cap in ("taxonomy_icons", "participant_metadata", "feature_rank"):
            self.assertIn(cap, manifest["capabilities"])


class ShortNameAndIdTests(Builder):
    def test_short_names_are_deterministic(self):
        cases = [("Manchester City FC", None, "Man City"), ("Arsenal FC", None, "Arsenal"), ("FC Barcelona", None, "Barcelona"),
                 ("The Wanderers", None, "Wanderers"), ("Tottenham Hotspur", None, "Spurs"), ("England", None, "England"),
                 ("Luke Littler", "darts", "Littler"), ("Alex de Minaur", "tennis", "de Minaur"),
                 ("Michael van Gerwen", "darts", "van Gerwen"), ("A. Murray / J. Skupski", "tennis", "Murray / Skupski"),
                 ("TBC", None, "TBC"), ("", None, "TBC"), ("Fury", "boxing", "Fury")]
        for name, sport, expected in cases:
            self.assertEqual(metadata.short_name(name, sport), expected, name)
            self.assertEqual(metadata.short_name(name, sport), metadata.short_name(name, sport))

    def test_source_short_names_are_kept_and_the_rest_derived_for_every_event(self):
        a = ev("football-data:1", participants=["Arsenal FC", "Manchester City FC"], participants_short=["Arsenal", "Man City"])
        b = ev("api-sports:2", source="api_sports", participants=["Chelsea FC", "Brentford FC"],
               start_utc="2026-11-14T17:30:00+00:00")
        c = ev("football-data:3", participants=["A", "B"], participants_short=["only one"])     # length mismatch: derive
        _m, rows, _x, _t = self.build([a, b, c])
        self.assertEqual(rows["football-data:1"]["participants_short"], ["Arsenal", "Man City"])
        self.assertEqual(rows["api-sports:2"]["participants_short"], ["Chelsea", "Brentford"])
        self.assertEqual(rows["football-data:3"]["participants_short"], ["A", "B"])
        for row in rows.values():
            self.assertEqual(len(row["participants_short"]), len(row["participants"]))
            validate(row, EVENT_SCHEMA, SCHEMA)

    def test_every_golden_event_has_aligned_short_names_and_ids(self):
        manifest, files = fixtures_tool.build()
        count = 0
        for path, data in files.items():
            if "/assets/events" in path:
                for row in json.loads(data)["events"]:
                    if row.get("participants"):
                        count += 1
                        self.assertEqual(len(row["participants_short"]), len(row["participants"]), row["id"])
                        self.assertEqual(len(row["participant_ids"]), len(row["participants"]), row["id"])
        self.assertGreater(count, 8)

    def test_participant_ids_use_provider_ids_then_normalised_keys(self):
        event = apisports("Arsenal", "Chelsea")
        self.assertEqual(metadata.participant_ids(event), ["apisports:football:42", "apisports:football:50"])
        self.assertEqual(metadata.participant_ids(ev("x", participants=["Arsenal FC", "Manchester City FC"])),
                         ["key:arsenal", "key:manchester-city"])
        self.assertEqual(metadata.participant_ids(ev("x", participants=["Arsenal", "Man City"])),
                         ["key:arsenal", "key:manchester-city"])          # same key whatever the source's spelling
        self.assertEqual(metadata.participant_ids(ev("x", participants=["Arsenal", "TBC"])), ["key:arsenal", None])
        self.assertIsNone(metadata.participant_ids(ev("x", participants=[])))
        crest = [{"src": "apisports", "ref": "football/teams/42"}, None]
        self.assertEqual(metadata.participant_ids(ev("x", participants=["Arsenal", "Chelsea"], participant_crests=crest)),
                         ["apisports:football:42", "key:chelsea"])

    def test_merged_fixture_takes_the_provider_id_from_the_source_that_has_one(self):
        merged = linking.merge_events([apisports("Arsenal", "Chelsea"), ev("fd:1", participants=["Arsenal FC", "Chelsea FC"],
                                                                           start_utc="2026-11-14T15:00:00+00:00")])
        self.assertEqual(len(merged), 1)
        self.assertEqual(metadata.participant_ids(merged[0]), ["apisports:football:42", "apisports:football:50"])


class CompetitionLogoTests(Builder):
    LEAGUE = {"id": 39, "name": "Premier League", "country": "England", "logo": "https://media.api-sports.io/football/leagues/39.png"}

    def football(self):
        payload = json.loads(api_payload({"id": 42, "name": "Arsenal"}, {"id": 50, "name": "Chelsea"}))
        payload["response"][0]["league"] = self.LEAGUE
        return providers.api_sports_events(json.dumps(payload).encode())[0]

    def test_decoder_carries_a_reference_never_the_logo_url(self):
        event = self.football()
        self.assertEqual(event["competition_logo"], {"src": "apisports", "ref": "football/leagues/39"})
        self.assertNotIn("http", json.dumps(event["competition_logo"]))
        data = json.dumps({"response": [{"id": 7, "timestamp": 1794000000, "status": {"short": "NS"},
                                         "league": {"id": 16, "name": "Six Nations", "logo": "u"},
                                         "country": {"name": "World"}, "teams": {"home": {"id": 3, "name": "Scotland"},
                                                                                "away": {"id": 4, "name": "Fiji"}}}]}).encode()
        rugby = providers.api_sports_games_events(data, "api_sports_rugby", "rugby")[0]
        self.assertEqual(rugby["competition_logo"]["ref"], "rugby/leagues/16")
        no_id = json.loads(data)
        no_id["response"][0]["league"] = {"name": "X"}
        self.assertNotIn("competition_logo", providers.api_sports_games_events(json.dumps(no_id).encode(), "api_sports_rugby", "rugby")[0])

    def test_published_only_with_the_crest_switch_and_capability_follows(self):
        event = self.football()
        manifest, rows, _x, _t = self.build([event], approvals=("api_sports",), publish_crest_refs=False)
        self.assertNotIn("competition_logo", rows[event["id"]])
        self.assertNotIn("competition_logos", manifest["capabilities"])
        manifest, rows, _x, _t = self.build([event], approvals=("api_sports",), publish_crest_refs=True)
        row = rows[event["id"]]
        self.assertEqual(row["competition_logo"], {"src": "apisports", "ref": "football/leagues/39"})
        self.assertIn("competition_logos", manifest["capabilities"])
        self.assertIn("{ref}", manifest["rights"]["crests"]["sources"]["apisports"]["url_template"])
        validate(row, EVENT_SCHEMA, SCHEMA)

    def test_unapproved_source_never_publishes_a_logo(self):
        _m, rows, _x, _t = self.build([self.football()], approvals=("football_data",), publish_crest_refs=True)
        self.assertEqual(rows, {})

    def test_malformed_logo_reference_is_dropped(self):
        for bad in ({"src": "apisports", "ref": "../leagues/1"}, {"src": "other", "ref": "football/leagues/1"},
                    {"src": "apisports", "ref": "football/leagues/0"}, "football/leagues/1"):
            self.assertIsNone(metadata.competition_logo_public({"competition_logo": bad}))

    def test_merge_gives_the_logo_to_the_same_named_competition_from_any_source(self):
        fd = ev("fd:1", participants=["Arsenal FC", "Chelsea FC"], start_utc="2026-11-14T15:00:00+00:00")
        merged = linking.merge_events([taxonomy.classify(fd), taxonomy.classify(self.football())])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["competition_logo"]["ref"], "football/leagues/39")


class RankTests(Builder):
    def rank(self, **kw):
        row = {"sport": "football", "category_id": "football.premier_league", "category_priority": 5,
               "competition_id": "football.premier_league", "tier": "core", "start_precision": "scheduled"}
        row.update(kw)
        return metadata.feature_rank(row)

    def test_rank_is_bounded_and_ordered_by_the_documented_rule(self):
        base = self.rank()
        self.assertEqual(base, 20 + 35 + 5)
        self.assertEqual(self.rank(corroboration=2), base + 5)
        self.assertEqual(self.rank(broadcast_links=[{"binds": True}]), base + 5)
        self.assertEqual(self.rank(broadcast_links=[{"binds": False}]), base + 2)
        self.assertEqual(self.rank(start_precision="date_only"), base - 10)
        self.assertEqual(self.rank(tier="extra"), base - 15)
        self.assertEqual(self.rank(tags=["team:england"]), base + 20)
        self.assertEqual(self.rank(tags=["team:wales", "team:france"]), base + 15)
        self.assertEqual(self.rank(tags=["team:england", "ppv"], corroboration=3, broadcast_links=[{"binds": True}]), 100)
        self.assertEqual(self.rank(category_id="football.other", category_priority=90, competition_id=None, tier="extra"), 5)
        self.assertEqual(metadata.feature_rank({}), 3 - 0)

    def test_ranking_examples_from_the_fixture_day(self):
        _m, rows, _x, today = self.build_fixture_rows()
        rank = {k: v["feature_rank"] for k, v in rows.items()}
        self.assertGreater(rank["api-sports:9002"], rank["football-data:5001"])           # England beats a league fixture
        self.assertGreater(rank["api-sports-mma:77"], rank["football-data:5001"])         # PPV card
        self.assertGreater(rank["football-data:5001"], rank["api-sports:9006"])           # PL over National League
        self.assertEqual(rank["api-sports:9006"] > 0, True)

    def build_fixture_rows(self):
        manifest, files = fixtures_tool.build()
        rows, today = {}, None
        for path, data in files.items():
            doc = json.loads(data)
            if "/assets/events" in path:
                rows.update({e["id"]: e for e in doc["events"]})
            if "/assets/today/" in path:
                today = doc
        return manifest, rows, None, today

    def test_f1_sessions_rank_race_above_qualifying_above_practice(self):
        race = dict(sport="motorsport", category_id="motorsport.f1", category_priority=1, competition_id="motorsport.f1")
        ranks = [metadata.feature_rank(dict(race, session=s)) for s in ("race", "qualifying", "practice1")]
        self.assertEqual(ranks, sorted(ranks, reverse=True))
        self.assertEqual(len(set(ranks)), 3)

    def test_today_orders_best_first_and_features_the_top_ten(self):
        events = [ev("football-data:%d" % i, participants=["Home %d" % i, "Away %d" % i], title="H v A",
                     start_utc="2026-11-14T%02d:00:00+00:00" % (12 + i % 8), competition="National League",
                     competition_country="England") for i in range(1, 13)]
        events.append(ev("football-data:99", participants=["England", "Japan"], competition="Friendlies",
                         competition_country="World", start_utc="2026-11-14T19:45:00+00:00"))
        events.append(ev("football-data:98", participants=["Arsenal", "Chelsea"], start_utc="2026-11-14T16:00:00+00:00"))
        manifest, rows, _x, today = self.build(events)
        self.assertEqual(len(today["featured_event_ids"]), 10)
        self.assertEqual(today["featured_event_ids"], today["ordered_event_ids"][:10])
        self.assertEqual(today["ordered_event_ids"][0], "football-data:99")      # England friendly first
        self.assertEqual(today["ordered_event_ids"][1], "football-data:98")      # then the Premier League fixture
        ranks = [rows[i]["feature_rank"] for i in today["ordered_event_ids"]]
        self.assertEqual(ranks, sorted(ranks, reverse=True))
        self.assertEqual(set(today["ordered_event_ids"]), set(rows))
        # ties break by start time then id, so the order is reproducible
        tied = [i for i in today["ordered_event_ids"] if rows[i]["feature_rank"] == ranks[-1]]
        self.assertEqual(tied, sorted(tied, key=lambda i: (rows[i]["start_utc"], i)))
        again = self.build(events)[3]
        self.assertEqual(again, today)
        validate(today, load_schema("sli.today/1"), load_schema("sli.today/1"))


class TagAndPpvTests(Builder):
    def test_nation_tags_survive_common_source_spellings(self):
        for name, tag in [("England", "team:england"), ("England Rugby", "team:england"), ("England XV", "team:england"),
                          ("England Men", "team:england"), ("England W", "team:england_women"),
                          ("England Women", "team:england_women"), ("Scotland (W)", "team:scotland_women"),
                          ("England Under 21", "team:england_u21"), ("England U21", "team:england_u21"),
                          ("Wales Rugby", "team:wales"), ("Republic of Ireland", "team:ireland")]:
            self.assertEqual(["team:" + n for n in taxonomy.nation_tags([name, "Japan"])], [tag], name)
        for name in ("Wales Bonner FC", "New England Revolution", "England Rose", "Ireland Wolfhounds XV"):
            self.assertEqual(taxonomy.nation_tags([name, "Japan"]), [], name)

    def test_tags_reach_the_public_rows_and_drive_the_featured_ranks(self):
        events = [ev("api-sports-rugby:1", source="api_sports_rugby", sport="rugby", competition="Autumn Nations Series",
                     competition_country="World", participants=["England Rugby", "Argentina"],
                     start_utc="2026-11-14T15:10:00+00:00"),
                  ev("api-sports-mma:2", source="football_data", sport="mma", competition="UFC 330",
                     title="UFC 330 PPV: A v B", participants=["Champion", "Challenger"])]
        _m, rows, _x, today = self.build(events, approvals=("api_sports_rugby", "football_data"))
        self.assertEqual(rows["api-sports-rugby:1"]["tags"], ["team:england"])
        self.assertEqual(rows["api-sports-mma:2"]["tags"], ["ppv"])
        self.assertEqual(set(today["featured_event_ids"]), set(rows))

    def test_ppv_boolean_and_label_only_for_boxing_and_mma_ppv(self):
        events = [ev("football-data:1", sport="mma", competition="UFC 330", title="UFC 330 PPV: A v B"),
                  ev("football-data:2", sport="boxing", competition="Sky Sports Box Office", title="Fury v Usyk 3 — Box Office PPV"),
                  ev("football-data:3", sport="boxing", competition="Premium boxing", title="Premium boxing: A v B"),
                  ev("football-data:4", sport="football", title="PPV Arsenal v Chelsea")]
        manifest, rows, _x, _t = self.build(events, approvals=("football_data",))
        self.assertEqual((rows["football-data:1"]["ppv"], rows["football-data:1"]["ppv_label"]), (True, "UFC 330 PPV"))
        self.assertEqual((rows["football-data:2"]["ppv"], rows["football-data:2"]["ppv_label"]), (True, "Boxing PPV"))
        for event_id in ("football-data:3", "football-data:4"):
            self.assertNotIn("ppv", rows[event_id])
            self.assertNotIn("ppv_label", rows[event_id])
        self.assertIn("ppv_flag", manifest["capabilities"])
        validate(rows["football-data:1"], EVENT_SCHEMA, SCHEMA)


class F1Tests(Builder):
    JOLPICA = json.dumps({"MRData": {"RaceTable": {"Races": [{
        "season": "2026", "round": "22", "raceName": "Las Vegas Grand Prix",
        "Circuit": {"circuitName": "Las Vegas Strip Circuit", "circuitId": "vegas", "Location": {"country": "USA"}},
        "date": "2026-11-16", "time": "06:00:00Z",
        "FirstPractice": {"date": "2026-11-14", "time": "18:30:00Z"},
        "Qualifying": {"date": "2026-11-15", "time": "04:00:00Z"},
        "Sprint": {"date": "2026-11-15", "time": "00:30:00Z"}}]}}}).encode()
    OPENF1 = json.dumps([{"session_key": 9001, "meeting_key": 1250, "session_name": "Qualifying", "country_name": "United States",
                          "date_start": "2026-11-15T04:00:00+00:00", "date_end": "2026-11-15T05:00:00+00:00",
                          "location": "Las Vegas", "circuit_short_name": "Las Vegas"}]).encode()

    def test_weekend_id_is_shared_by_every_session_and_labels_follow_the_session(self):
        events = providers.f1_events(self.JOLPICA)
        _m, rows, extra, _t = self.build(events, approvals=("jolpica",))
        by_session = {r["session"]: r for r in list(rows.values()) + list(extra.values())}
        self.assertEqual({r["weekend_id"] for r in by_session.values()}, {"f1:2026:22"})
        self.assertEqual({k: v["session_label"] for k, v in by_session.items()},
                         {"race": "Race", "practice1": "Practice 1", "qualifying": "Qualifying", "sprint": "Sprint"})
        self.assertEqual(by_session["race"]["title"], "Las Vegas Grand Prix — Race")
        manifest = self.build(events, approvals=("jolpica",))[0]
        self.assertIn("f1_weekends", manifest["capabilities"])
        for row in by_session.values():
            validate(row, EVENT_SCHEMA, SCHEMA)

    def test_weekend_id_is_stable_whichever_source_is_primary(self):
        jolpica = [e for e in providers.f1_events(self.JOLPICA) if e["session"] == "qualifying"]
        openf1 = providers.openf1_events(self.OPENF1, now=NOW)
        self.assertEqual(openf1[0]["weekend_key"], "1250")
        only_openf1 = self.build(openf1, approvals=("openf1",))[1]
        self.assertEqual(only_openf1["openf1:9001"]["weekend_id"], "f1:openf1:1250")
        for order in (jolpica + openf1, openf1 + jolpica):
            _m, rows, extra, _t = self.build(order, approvals=("jolpica", "openf1"))
            merged = [r for r in list(rows.values()) + list(extra.values()) if r["session"] == "qualifying"]
            self.assertEqual(len(merged), 1)
            self.assertEqual(merged[0]["weekend_id"], "f1:2026:22")
            self.assertEqual(merged[0]["session_label"], "Qualifying")

    def test_non_f1_motorsport_has_neither_field(self):
        event = ev("jolpica:x", source="jolpica", sport="motorsport", competition="MotoGP", session="race",
                   participants=[], title="Valencia GP — Race")
        row = self.build([event], approvals=("jolpica",))[1]["jolpica:x"]
        self.assertNotIn("weekend_id", row)
        self.assertNotIn("session_label", row)


class ExtraTierTests(Builder):
    def events(self):
        return [ev("api-sports:1", source="api_sports", competition="Primera Division Reserves", competition_country="Spain",
                   title="Real Madrid Castilla v Barca Atletic", participants=["Real Madrid Castilla", "Barca Atletic"]),
                ev("api-sports:2", source="api_sports", competition="U19 League", competition_country="Germany",
                   participants=["Bayern U19", "Dortmund U19"], start_utc="2026-11-14T11:00:00+00:00"),
                ev("api-sports:3", source="api_sports", competition="Premier League 2", competition_country="England",
                   participants=["Spurs U21", "Villa U21"], start_utc="2026-11-14T12:00:00+00:00"),
                ev("football-data:4", participants=["Arsenal", "Chelsea"])]

    def test_youth_and_reserve_football_stays_extra_is_never_dropped_and_ids_are_stable(self):
        manifest, rows, extra, today = self.build(self.events())
        self.assertEqual(sorted(extra), ["api-sports:1", "api-sports:2", "api-sports:3"])
        self.assertEqual(list(rows), ["football-data:4"])
        self.assertTrue(all(r["tier"] == "extra" for r in extra.values()))
        self.assertEqual(manifest["coverage"]["events"], 4)
        self.assertEqual(manifest["coverage"]["today_extra"], 3)
        # same ids on a second build, whatever the order of the source records
        again = self.build(list(reversed(self.events())))
        self.assertEqual(sorted(again[2]), sorted(extra))
        self.assertEqual(again[3], today)

    def test_today_summarises_extra_events_and_keeps_them_out_of_the_core_lists(self):
        _m, rows, extra, today = self.build(self.events())
        self.assertEqual(set(today["today_extra_ids"]), set(extra))
        self.assertEqual(today["today_extra_summary"], {"count": 3, "by_sport": {"football": 3}})
        self.assertFalse(set(today["today_extra_ids"]) & set(today["ordered_event_ids"]))
        ranks = [extra[i]["feature_rank"] for i in today["today_extra_ids"]]
        self.assertEqual(ranks, sorted(ranks, reverse=True))
        self.assertTrue(all(extra[i]["feature_rank"] < rows["football-data:4"]["feature_rank"] for i in extra))

    def test_no_extra_events_gives_an_empty_summary(self):
        _m, _rows, extra, today = self.build([ev("football-data:4", participants=["Arsenal", "Chelsea"])])
        self.assertEqual((extra, today["today_extra_ids"], today["today_extra_summary"]),
                         ({}, [], {"count": 0, "by_sport": {}}))


if __name__ == "__main__":
    unittest.main()
