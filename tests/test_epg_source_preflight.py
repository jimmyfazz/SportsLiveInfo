"""A parseable XMLTV feed is not useful if every programme is expired."""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from sportsliveinfo.engine import Engine
from sportsliveinfo.storage import Store


def guide_for(start, end):
    st = start.strftime("%Y%m%d%H%M%S +0000")
    en = end.strftime("%Y%m%d%H%M%S +0000")
    return ('<tv><channel id="demo"><display-name>Demo</display-name></channel>'
            '<programme channel="demo" start="%s" stop="%s">'
            '<title>Example broadcast</title></programme></tv>' % (st, en)).encode("utf-8")


class EpgSourcePreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "state.sqlite3")

    def tearDown(self):
        self.tmp.cleanup()

    def test_expired_guide_cannot_claim_success(self):
        now = datetime.now(timezone.utc)
        raw = guide_for(now - timedelta(days=10), now - timedelta(days=9))
        with patch("sportsliveinfo.providers.fetch", return_value=raw) as request:
            result = Engine(self.store).test_source("epg", "farleyflex")
        request.assert_called_once()
        self.assertIn("unsuccessful", result)
        self.assertEqual(self.store.recent_jobs(1)[0]["state"], "test_failed")
        self.assertIsNone(self.store.snapshot("epg:farleyflex"))
        self.assertEqual(self.store.usage()["epg:farleyflex"], 1)

    def test_stale_feed_skips_expensive_coverage_analysis(self):
        now = datetime.now(timezone.utc)
        raw = guide_for(now - timedelta(days=7), now - timedelta(days=6))
        with patch("sportsliveinfo.providers.fetch", return_value=raw), patch(
                "sportsliveinfo.engine.analyze_guide") as analyse:
            refreshed = Engine(self.store)._collect_epg("farleyflex")
        self.assertFalse(refreshed)
        analyse.assert_not_called()
        self.assertIsNone(self.store.snapshot("epg-quality:farleyflex"))
        self.assertEqual(self.store.recent_jobs(1)[0]["state"], "stale")

    def test_accepted_guide_persists_private_coverage_diagnostics(self):
        now = datetime.now(timezone.utc)
        raw = guide_for(now - timedelta(minutes=30), now + timedelta(hours=4))
        with patch("sportsliveinfo.providers.fetch", return_value=raw):
            refreshed = Engine(self.store)._collect_epg("farleyflex")
        self.assertTrue(refreshed)
        self.assertIsNotNone(self.store.snapshot("epg:farleyflex"))
        self.assertIsNotNone(self.store.snapshot("epg-quality:farleyflex"))

    def test_current_guide_reports_forward_rows_without_saving_snapshot(self):
        now = datetime.now(timezone.utc)
        raw = guide_for(now + timedelta(minutes=10), now + timedelta(hours=2))
        with patch("sportsliveinfo.providers.fetch", return_value=raw):
            result = Engine(self.store).test_source("epg", "farleyflex")
        self.assertIn("connection successful", result)
        self.assertIn("current programmes", result)
        self.assertEqual(self.store.recent_jobs(1)[0]["state"], "test_ok")
        self.assertIsNone(self.store.snapshot("epg:farleyflex"))


if __name__ == "__main__":
    unittest.main()
