"""F1 practice sessions were published twice (jolpica/OpenF1 and TheSportsDB) on 20 Nov 2026 (audit CA-08).

Titles are the real ones from the live `events:2026-11-20` asset: TheSportsDB names the weekend, not the session."""
import unittest

from sportsliveinfo import linking


def row(eid, source, title, start, session=None, **kw):
    out = {"id": eid, "source_id": source, "sport": "motorsport", "competition_id": "motorsport.f1",
           "participants": [], "title": title, "start_utc": start, "start_precision": "scheduled"}
    if session:
        out["session"] = session
    out.update(kw)
    return out


FP1 = "2026-11-20T00:30:00+00:00"
FP2 = "2026-11-20T04:00:00+00:00"


class F1DedupeTests(unittest.TestCase):
    def test_practice_sessions_merge_with_thesportsdb_weekend_title(self):
        rows = [
            row("f1:2026:21:FirstPractice", "jolpica", "Las Vegas Grand Prix — Practice 1", FP1, "practice1"),
            row("openf1:9001", "openf1", "Formula 1 United States — Practice 1", FP1, "practice1", weekend_key="1270"),
            row("thesportsdb:2408212", "thesportsdb", "Las Vegas Grand Prix", FP1),
            row("f1:2026:21:SecondPractice", "jolpica", "Las Vegas Grand Prix — Practice 2", FP2, "practice2"),
            row("thesportsdb:2408213", "thesportsdb", "Las Vegas Grand Prix", FP2),
        ]
        merged = linking.merge_events(rows)
        self.assertEqual(len(merged), 2)
        self.assertEqual(sorted(e["session"] for e in merged), ["practice1", "practice2"])

    def test_title_naming_the_session_merges_by_session(self):
        merged = linking.merge_events([
            row("f1:2026:21:FirstPractice", "jolpica", "Las Vegas Grand Prix — Practice 1", FP1, "practice1"),
            row("thesportsdb:1", "thesportsdb", "Las Vegas Grand Prix Practice 1", "2026-11-20T00:50:00+00:00")])
        self.assertEqual(len(merged), 1)

    def test_other_session_in_title_stays_separate(self):
        # "Reverse Grid Race" at the same minute as Practice 1 is a different session.
        merged = linking.merge_events([
            row("f1:2026:21:FirstPractice", "jolpica", "Las Vegas Grand Prix — Practice 1", FP1, "practice1"),
            row("thesportsdb:2411615", "thesportsdb", "Las Vegas Reverse Grid Race", FP1)])
        self.assertEqual(len(merged), 2)

    def test_sessionless_row_far_from_any_session_stays_separate(self):
        merged = linking.merge_events([
            row("f1:2026:21:FirstPractice", "jolpica", "Las Vegas Grand Prix — Practice 1", FP1, "practice1"),
            row("thesportsdb:2", "thesportsdb", "Las Vegas Grand Prix", "2026-11-20T01:30:00+00:00")])
        self.assertEqual(len(merged), 2)

    def test_two_sessionless_rows_do_not_merge_and_other_competition_stays(self):
        self.assertEqual(len(linking.merge_events([
            row("a:1", "jolpica", "Grand Prix", FP1), row("b:1", "thesportsdb", "Grand Prix", FP1)])), 2)
        self.assertEqual(len(linking.merge_events([
            row("a:1", "jolpica", "X — Practice 1", FP1, "practice1"),
            row("b:1", "thesportsdb", "X", FP1, competition_id="motorsport.motogp")])), 2)


if __name__ == "__main__":
    unittest.main()
