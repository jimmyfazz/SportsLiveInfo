"""Event titles, status defaults, date-only starts and expected durations (chore: event titles and durations).

Backward compatible: no contract field is added. Titles and durations change only where a source gave too little
to tell sessions or placeholder fixtures apart, and a missing status is published as "scheduled".
"""
import json
import unittest
from datetime import datetime, timedelta, timezone

from sportsliveinfo import feed, providers, taxonomy

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def _jolpica(*races):
    return json.dumps({"MRData": {"RaceTable": {"Races": list(races)}}}).encode()


class F1TitleAndStatusTests(unittest.TestCase):
    def setUp(self):
        self.race = {"season": "2026", "round": "22", "raceName": "Example Grand Prix", "date": "2026-11-22", "time": "15:00:00Z",
                     "Circuit": {"circuitName": "Example Circuit", "circuitId": "example", "Location": {"country": "Example"}},
                     "FirstPractice": {"date": "2026-11-20", "time": "11:30:00Z"},
                     "Qualifying": {"date": "2026-11-21", "time": "15:00:00Z"}}

    def test_session_titles_name_the_session_and_keep_the_session_field(self):
        events = {e["event_type"]: e for e in providers.f1_events(_jolpica(self.race))}
        self.assertEqual(events["race"]["title"], "Example Grand Prix — Race")
        self.assertEqual(events["FirstPractice"]["title"], "Example Grand Prix — Practice 1")
        self.assertEqual(events["Qualifying"]["title"], "Example Grand Prix — Qualifying")
        self.assertEqual((events["FirstPractice"]["session"], events["Qualifying"]["session"], events["race"]["session"]),
                         ("practice1", "qualifying", "race"))

    def test_jolpica_sessions_are_always_scheduled(self):
        events = providers.f1_events(_jolpica(self.race))
        self.assertEqual({e["status_normalized"] for e in events}, {"scheduled"})
        self.assertEqual(len(events), 3)

    def test_openf1_finished_only_when_its_end_time_has_passed(self):
        rows = [{"session_key": 1, "session_name": "Race", "date_start": "2026-11-01T13:00:00+00:00",
                 "date_end": "2026-11-01T15:00:00+00:00", "country_name": "Example"},
                {"session_key": 2, "session_name": "Race", "date_start": "2026-11-22T13:00:00+00:00",
                 "date_end": "2026-11-22T15:00:00+00:00", "country_name": "Example"},
                {"session_key": 3, "session_name": "Practice 1", "date_start": "2026-11-20T11:30:00+00:00",
                 "country_name": "Example"}]
        events = {e["id"]: e for e in providers.openf1_events(json.dumps(rows).encode(), now=NOW)}
        self.assertEqual(events["openf1:1"]["status_normalized"], "finished")
        self.assertEqual(events["openf1:2"]["status_normalized"], "scheduled")
        self.assertEqual(events["openf1:3"]["status_normalized"], "scheduled")   # no provider end time: never "finished"

    def test_publishing_defaults_a_missing_status_to_scheduled(self):
        event = {"id": "x:1", "sport": "football", "event_type": "match", "title": "A v B", "participants": ["A", "B"],
                 "start_utc": "2026-11-22T15:00:00+00:00", "start_precision": "scheduled", "source_id": "x", "broadcasts": []}
        row = feed._event_public(event)
        self.assertEqual(row["status_normalized"], "scheduled")
        self.assertEqual(feed._event_public(dict(event, status_normalized="live"))["status_normalized"], "live")


class CricketPlaceholderTests(unittest.TestCase):
    def _rows(self, name, teams):
        payload = {"status": "success", "data": [{"id": "c1", "name": name, "matchType": "odi", "series": "Tri-Series",
                                                  "dateTimeGMT": "2026-11-25T08:00:00", "teams": teams,
                                                  "matchStarted": False, "matchEnded": False}]}
        return providers.cricketdata_events(json.dumps(payload), now=NOW)

    def test_both_placeholder_teams_use_the_name_and_no_participants(self):
        rows = self._rows("Ireland v Scotland, 1st ODI, Tri-Series", ["TBC", "Tba"])
        self.assertEqual(rows[0]["title"], "Ireland v Scotland")
        self.assertEqual(rows[0]["participants"], [])

    def test_placeholder_name_falls_back_to_the_competition(self):
        rows = self._rows("TBC v TBC, 3rd ODI, Tri-Series", ["To be confirmed", "TBC"])
        self.assertEqual(rows[0]["title"], "Tri-Series")
        self.assertEqual(rows[0]["participants"], [])

    def test_one_placeholder_keeps_the_known_team(self):
        rows = self._rows("India vs TBC, 2nd ODI, Tri-Series", ["India", "TBC"])
        self.assertEqual(rows[0]["title"], "India v TBC")
        self.assertEqual(rows[0]["participants"], ["India", "TBC"])


class TheSportsDbDayOnlyTests(unittest.TestCase):
    def test_midnight_stamp_is_date_only_for_day_only_sports(self):
        rows = [{"idEvent": str(i), "strSport": sport, "strEvent": "Event", "strTimestamp": stamp}
                for i, (sport, stamp) in enumerate([("Golf", "2026-11-22T00:00:00"), ("Darts", "2026-11-22T00:00:00Z"),
                                                    ("Motorsport", "2026-11-22T00:00:00"), ("Snooker", "2026-11-22T19:00:00"),
                                                    ("Ice Hockey", "2026-11-22T00:00:00")])]
        out = providers.thesportsdb_events(json.dumps({"events": rows}).encode())
        self.assertEqual([(e["sport"], e["start_precision"]) for e in out],
                         [("Golf", "date_only"), ("Darts", "date_only"), ("Motorsport", "date_only"),
                          ("Snooker", "scheduled"), ("Ice Hockey", "scheduled")])
        self.assertEqual(out[0]["start_utc"], "2026-11-22T12:00:00+00:00")     # date_only at noon, as elsewhere
        self.assertEqual(out[4]["start_utc"], "2026-11-22T00:00:00+00:00")     # other sports keep the stated time


class ExpectedDurationTests(unittest.TestCase):
    def test_new_durations(self):
        cases = [
            (dict(sport="motorsport", session="practice1", event_type="FirstPractice"), 90),
            (dict(sport="motorsport", session="practice3"), 90),
            (dict(sport="motorsport", session="qualifying"), 90),
            (dict(sport="motorsport", session="sprint_qualifying"), 90),
            (dict(sport="motorsport", session="race", event_type="race"), 150),
            (dict(sport="motorsport", session="sprint"), 180),                 # unchanged default for other sessions
            (dict(sport="handball"), 120),
            (dict(sport="volleyball"), 150),
            (dict(sport="football", stage="ROUND_OF_16"), 150),
            (dict(sport="football", stage="QUARTER_FINALS"), 150),
            (dict(sport="football", stage="Semi-finals"), 150),
            (dict(sport="football", stage="FINAL"), 150),
            (dict(sport="football", stage="Round of 32"), 150),
            (dict(sport="football", stage="GROUP_STAGE"), 120),
            (dict(sport="football", stage="REGULAR_SEASON"), 120),
            (dict(sport="football", stage=""), 120),
            (dict(sport="golf"), 360),                                         # unchanged
            (dict(sport="unlisted_sport"), 180),                               # the default is unchanged
        ]
        for event, minutes in cases:
            self.assertEqual(taxonomy.expected_minutes(event), minutes, event)


if __name__ == "__main__":
    unittest.main()
