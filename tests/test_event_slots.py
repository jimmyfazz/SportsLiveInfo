import unittest
from datetime import datetime, timezone

from sportsliveinfo import event_slots as es

NOW = datetime(2026, 11, 14, 16, 0, tzinfo=timezone.utc)   # Saturday


def parse(name, tz="Europe/London"):
    return es.parse_slot(name, now=NOW, default_tz=tz)


EVENTS = [
    {"id": "a", "participants": ["Northtown United", "Southport Rovers"], "start_utc": "2026-11-14T17:30:00+00:00"},
    {"id": "b", "participants": ["Lake City", "River Wanderers"], "start_utc": "2026-11-15T00:15:00+00:00"},
    # The same two teams on consecutive days (a series): a clock time alone cannot tell them apart.
    {"id": "c1", "participants": ["Hill Hawks", "Bay Bears"], "start_utc": "2026-11-14T22:00:00+00:00"},
    {"id": "c2", "participants": ["Hill Hawks", "Bay Bears"], "start_utc": "2026-11-15T22:00:00+00:00"},
    {"id": "d", "participants": ["Tapa (Est)", "Vilnius (Ltu)"], "start_utc": "2026-11-15T12:00:00+00:00"},
]


class EventSlotParserTests(unittest.TestCase):
    def test_provider_formats(self):
        cases = [
            ("22. EPL 05 | Northtown United vs Southport Rovers (Sat 17:30 UK)", "Europe/London",
             "EPL 05", ["Northtown United", "Southport Rovers"], "2026-11-14T17:30:00Z", "datetime"),
            ("CA-DAZN 52: Premier League| Northtown United vs. Southport Rovers| Sat 14 Nov 12:30 PM",
             "America/New_York", "CA-DAZN 52", ["Northtown United", "Southport Rovers"], "2026-11-14T17:30:00Z",
             "datetime"),
            ("PL+ 017|  Northtown United v Southport Rovers - Player Cam (2026-11-14 17:30:00)", "Europe/London",
             "PL+ 017", ["Northtown United", "Southport Rovers"], "2026-11-14T17:30:00Z", "datetime"),
            ("National League 8 | Northtown United vs Southport Rovers // UK Sat 14 Nov 5:30pm // ET Sat 14 Nov "
             "12:30pm", "America/New_York", "National League 8", ["Northtown United", "Southport Rovers"],
             "2026-11-14T17:30:00Z", "datetime"),
            ("NFL 01: 7:15PM River Wanderers @ Lake City", "America/New_York", "NFL 01",
             ["River Wanderers", "Lake City"], "2026-11-15T00:15:00Z", "time"),
            ("MLB 01 |  Lake City x River Wanderers start:2026-11-15 00:15:00 stop:2026-11-15 03:00:00",
             "America/New_York", "MLB 01", ["Lake City", "River Wanderers"], "2026-11-15T00:15:00Z", "datetime"),
            ("Fite TV 3 HD: TrillerTV-Example League 2025/26: Lake City vs River Wanderers - Sat,14 Nov 19:15 ET",
             "Europe/London", "Fite TV 3 HD", ["Lake City", "River Wanderers"], "2026-11-15T00:15:00Z", "datetime"),
            ("Lake City vs River Wanderers (Lake) @ Nov 14 7:15 PM :NBA  04", "America/New_York", "NBA  04",
             ["Lake City", "River Wanderers"], "2026-11-15T00:15:00Z", "datetime"),
            ("PPV EVENT 09: Lake City vs. River Wanderers (11.14 7:15 PM ET)", "Europe/London", "PPV EVENT 09",
             ["Lake City", "River Wanderers"], "2026-11-15T00:15:00Z", "datetime"),
            ("NCAAF 02 Lake City vs River Wanderers 715PM", "America/New_York", "NCAAF 02",
             ["Lake City", "River Wanderers"], "2026-11-15T00:15:00Z", "time"),
        ]
        for name, tz, slot, participants, start, precision in cases:
            with self.subTest(name=name):
                parsed = parse(name, tz)
                self.assertEqual((parsed["slot"], parsed["participants"], parsed["start_utc"], parsed["precision"]),
                                 (slot, participants, start, precision))

    def test_competition_and_qualifiers(self):
        parsed = parse("Fite TV 1 HD (D): TrillerTV-Example Cricket: Northland vs Southland, 3rd ODI - "
                       "Sat,14 Nov 07:50 ET")
        self.assertEqual(parsed["participants"], ["Northland", "Southland"])
        self.assertIn("Example Cricket", parsed["competition"])
        parsed = parse("CA-DAZN 63: MVP| Lake City vs. River Wanderers: Prelims| Sat 14 Nov 4:00 PM", "America/New_York")
        self.assertEqual((parsed["competition"], parsed["participants"]), ("MVP", ["Lake City", "River Wanderers"]))
        parsed = parse("Player A, Ann vs Player B, Bea @ Nov 14 21:00 PM - WTA Finals :Tennis  05", "America/New_York")
        self.assertEqual((parsed["competition"], parsed["participants"]), ("WTA Finals", ["Player A, Ann", "Player B, Bea"]))

    def test_channel_names_are_not_fixtures(self):
        for name in ("NO: V SPORT 1 HD", "AL: X Premium 2 HD", "CA V Montreal (FL)", "Sky Sports Main Event",
                     "SPORTSCENTRE A @ Nov 9 03:00 :TSN+  01", "(TO) NDTV 24 x 7"):
            with self.subTest(name=name):
                self.assertIsNone(parse(name))
        self.assertEqual(parse("L1 Pass 03 | PSG vs Troyes (Sat 20:05 UK)")["participants"], ["PSG", "Troyes"])


class EventSlotMatchTests(unittest.TestCase):
    def match(self, name, tz="Europe/London"):
        found = es.match_slot(parse(name, tz), EVENTS, now=NOW)
        return found and found["id"]

    def test_links_only_to_one_event_with_both_sides_and_time(self):
        self.assertEqual(self.match("EPL 05 | Northtown Utd vs Southport Rovers (Sat 17:30 UK)"), "a")
        self.assertEqual(self.match("NFL 01: 7:15PM River Wanderers @ Lake City", "America/New_York"), "b")  # away @ home
        self.assertIsNone(self.match("EPL 05 | Northtown United vs Southport Rovers (Sun 17:30 UK)"))   # a day out
        self.assertIsNone(self.match("EPL 05 | Northtown United vs Lake City (Sat 17:30 UK)"))         # one side only
        self.assertEqual(self.match("Event 2 | Tapa vs Vilnius (Sun 12:00 UK)"), "d")                  # "(Est)" ignored

    def test_clock_time_alone_never_picks_between_two_meetings(self):
        self.assertIsNone(self.match("NHL 01: 5:00PM Bay Bears @ Hill Hawks", "America/New_York"))
        self.assertEqual(self.match("NHL 01 | Bay Bears @ Hill Hawks (Sat 22:00 UK)"), "c1")


if __name__ == "__main__":
    unittest.main()
