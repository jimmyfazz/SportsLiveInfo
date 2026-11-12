"""Bounded broadcaster-candidate indexing preserves exact conservative matching."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sportsliveinfo import linking

UTC = timezone.utc
BASE = datetime(2026, 11, 14, 15, 0, tzinfo=UTC)


def event(key, start=BASE):
    return {"id": key, "sport": "football", "participants": ["Arsenal", "Manchester City"],
            "start_utc": start.isoformat(), "start_precision": "scheduled"}


def programme(start, end, title="Arsenal v Manchester City", subtitle=""):
    return {"channel_id": "skysportsmainevent.uk", "start_utc": start.isoformat(),
            "end_utc": end.isoformat(), "title": title, "subtitle": subtitle,
            "is_live": True, "is_repeat": False}


def guide(rows):
    return {"source_id": "farleyflex",
            "channels": {"skysportsmainevent.uk": "Sky Sports Main Event"},
            "programmes": rows}


class CandidateIndexTests(unittest.TestCase):
    def test_hour_boundary_and_long_programme_are_not_dropped(self):
        for start, end in [
            (BASE + timedelta(minutes=20), BASE + timedelta(minutes=30)),
            (BASE - timedelta(hours=36), BASE + timedelta(hours=30)),
            (BASE - timedelta(minutes=30), BASE + timedelta(minutes=31)),
        ]:
            with self.subTest(start=start):
                result = linking.broadcast_candidates([event("e")], {"farleyflex": guide([
                    programme(start, end)])}, BASE)
                self.assertIn("e", result)
                self.assertEqual(result["e"][0], "single_guide_match")
                self.assertEqual(result["e"][1][0]["canonical_channel_id"], "gb.sky.sports.main_event")
                self.assertTrue(result["e"][1][0]["epg_live_flag"])

    def test_excludes_nonoverlapping_or_highlights_and_sanitises_bad_start(self):
        rows = [
            programme(BASE - timedelta(hours=1), BASE + timedelta(minutes=29)),
            programme(BASE + timedelta(minutes=21), BASE + timedelta(hours=1)),
            programme(BASE - timedelta(minutes=30), BASE + timedelta(hours=1),
                      "Arsenal v Manchester City Highlights"),
        ]
        invalid = {"id": "bad", "start_utc": "not-a-date", "sport": "football"}
        actual = linking.broadcast_candidates([event("ok"), invalid],
                                             {"farleyflex": guide(rows)}, BASE)
        self.assertEqual(actual, {})

    def test_large_guide_avoids_full_cross_product(self):
        # 480 slots over 120 hours, 30 events (old code did ~14,400
        # _matches calls). Every event is given a matching EPG row.
        rows = [programme(BASE + timedelta(minutes=15 * i - 30),
                          BASE + timedelta(minutes=15 * i + 60))
                for i in range(480)]
        evs = [event(str(i), BASE + timedelta(hours=4 * i)) for i in range(30)]
        original = linking._matches
        with patch("sportsliveinfo.linking._matches", wraps=original) as match:
            result = linking.broadcast_candidates(evs, {"farleyflex": guide(rows)}, BASE)
        self.assertEqual(len(result), len(evs))
        self.assertLess(match.call_count, 1800, "index must avoid event × programme scans")
        self.assertTrue(all(status == "single_guide_match" for status, _ in result.values()))

    def test_only_distinct_source_families_count_as_multiple_guides(self):
        g = guide([programme(BASE - timedelta(minutes=10), BASE + timedelta(hours=2))])
        same_family = {"epgshare_uk": dict(g, source_id="epgshare_uk"),
                       "epgshare_fr": dict(g, source_id="epgshare_fr")}
        # No canonical mapping for the FR variant under this source namespace
        # should be treated as a verified broadcaster.
        result = linking.broadcast_candidates([event("e")], same_family, BASE)
        self.assertFalse(any(
            status == "multi_guide_match" for status, _ in result.values()))


if __name__ == "__main__":
    unittest.main()
