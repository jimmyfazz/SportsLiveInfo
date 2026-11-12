"""Offline operator UI regression tests for the HAOS Ingress control plane."""
import html
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace

from sportsliveinfo.engine import Engine
from sportsliveinfo.server import UI, e, freshness
from sportsliveinfo.storage import Store


class OperatorDashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "ui.sqlite3")
        self.engine = Engine(self.store)
        self.ui = UI.__new__(UI)
        self.ui.server = SimpleNamespace(store=self.store, engine=self.engine, csrf="test-csrf")

    def tearDown(self):
        self.tmp.cleanup()

    def test_zero_is_visible_and_untrusted_html_escaped(self):
        self.assertEqual(e(0), "0")
        self.assertEqual(e(False), "False")
        self.assertEqual(e('<script>alert("x")</script>'), '&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;')
        dashboard = self.ui.dashboard(self.store.config())
        self.assertGreaterEqual(dashboard.count('<div class="metric">0</div>'), 3)
        self.assertIn("No successful refresh", dashboard)

    def test_accessible_navigation_and_readiness_at_first_run(self):
        page = self.ui.render("dashboard", self.store.config(), "")
        self.assertIn('aria-label="Main navigation"', page)
        self.assertIn('href="#content"', page)
        self.assertIn('aria-label="First-run setup"', page)
        self.assertIn("1 · Select and test sources", page)
        self.assertIn("2 · Choose refresh times", page)
        self.assertIn('class="active" aria-current="page" href="?page=dashboard"', page)
        self.assertIn("System readiness", page)
        self.assertIn("Needs attention", page)
        self.assertNotIn('name="token" type="text"', page)

    def test_collapsible_source_catalogue_and_filters(self):
        conf = self.store.config()
        all_sources = self.ui.sources(conf)
        self.assertIn('class="provider-group"', all_sources)
        self.assertIn('kind=epg', all_sources)
        self.assertIn('value="test_source"', all_sources)
        self.assertIn("No API key required", all_sources)
        self.assertIn("UK", all_sources)
        only_epg = self.ui.sources(conf, {"kind": "epg"})
        self.assertIn("International television EPG sources", only_epg)
        self.assertNotIn("Sporting event APIs</h2>", only_epg)
        only_sports = self.ui.sources(conf, {"kind": "sports"})
        self.assertIn("Sporting event APIs", only_sports)
        self.assertNotIn("International television EPG sources", only_sports)

    def test_source_status_and_key_do_not_leak(self):
        self.store.configure({"keys": {"football_data": "never-show-secret"}})
        self.store.job("football_data", "test_failed", "Safe network error")
        markup = self.ui.sources(self.store.config(), {"kind": "sports"})
        self.assertIn("Test Failed", markup)
        self.assertNotIn("Safe network error", markup)
        self.assertNotIn("never-show-secret", markup)
        self.assertIn("Key stored privately", markup)

    def test_world_sports_event_pagination_cannot_hide_later_events(self):
        records = [
            {"id": str(i), "sport": "football", "category_id": "football.premier_league",
             "category_label": "Premier League", "competition": "Premier League",
             "title": "Fixture %d" % i, "start_utc": "2026-11-13T20:00:00+00:00",
             "source_id": "fixture", "broadcast_verified": False, "broadcasts": []}
            for i in range(235)
        ]
        self.store.save_snapshot("sports", {"events": records})
        page1 = self.ui.events({})
        page2 = self.ui.events({"p": "2"})
        page3 = self.ui.events({"p": "3"})
        self.assertIn("Page 1 of 3", page1)
        self.assertIn("Next page", page1)
        self.assertNotIn("Previous page", page1)
        self.assertIn("Page 2 of 3", page2)
        self.assertIn("Previous page", page2)
        self.assertIn("Next page", page2)
        self.assertEqual(page3.count("<tr><td>"), 35)
        self.assertIn("Fixture 99", page3)
        self.assertNotIn("Next page", page3)
        self.assertEqual(self.ui.events({"p": "oops"}).count("Page 1 of 3"), 1)
        self.assertIn("Page 3 of 3", self.ui.events({"p": "999999"}))

    def test_uk_day_filter_uses_calendar_date_and_escapes_search(self):
        self.store.save_snapshot("sports", {"events": [
            {"id": "a", "title": "Evening Match", "sport": "football",
             "competition": "Demo", "start_utc": "2026-07-03T23:30:00+00:00",
             "source_id": "fixture", "broadcasts": [], "broadcast_verified": False}
        ]})
        page = self.ui.events({"date": "2026-07-04"})
        self.assertIn("1 of 1 events", page)  # BST: 23:30 UTC is 00:30 next day
        filtered = self.ui.events({"date": "2026-07-03"})
        self.assertIn("0 of 1 events", filtered)
        malicious = self.ui.events({"q": '<img src=x onerror=alert(1)>'})
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", malicious)
        self.assertNotIn('<img src=x onerror=alert(1)>', malicious)

    def test_guide_meter_clamped_and_xss_safe(self):
        self.store.save_snapshot("epg-quality:farleyflex", {
            "channels": 10,
            "country": "GB",
            "analysed_at": datetime.now(timezone.utc).isoformat(),
            "full_coverage_channels": {"24h": 100, "72h": -10, "168h": 3},
            "families": {},
            "channels_needing_attention": [
                {"name": "<private>", "canonical_id": "uk.demo", "coverage_hours": {"24h": 2}}
            ],
        })
        markup = self.ui.guide()
        self.assertIn('aria-valuenow="100"', markup)
        self.assertIn('aria-valuenow="0"', markup)
        self.assertIn('style="width:100%"', markup)
        self.assertNotIn("<private>", markup)
        self.assertIn(html.escape("<private>"), markup)

    def test_health_separates_failures_and_quota(self):
        self.store.job("farleyflex", "failed", "Provider unavailable")
        self.store.increment("demo", 5)
        markup = self.ui.health()
        self.assertIn("Failed operations", markup)
        self.assertIn("Provider unavailable", markup)
        self.assertIn("UTC-day quota reservations", markup)
        self.assertIn('class="state critical">Failed</span>', markup)

    def test_publication_action_disabled_before_prerequisites(self):
        markup = self.ui.publishing(self.store.config())
        self.assertIn('type="submit" disabled>Publish feed now</button>', markup)
        self.assertIn("Only select repositories", markup)
        self.assertNotIn('type="submit" disabled>Build feed preview', markup)

    def test_freshness_indicates_stale_snapshot_without_guessing(self):
        now = datetime(2026, 11, 12, tzinfo=timezone.utc)
        self.assertEqual(freshness(None), ("Not collected", "warn"))
        result = freshness({"updated_at": (now - timedelta(days=2)).isoformat()}, now)
        self.assertEqual(result, ("Last updated 2 days ago", "warn"))
        result = freshness({"updated_at": (now - timedelta(minutes=35)).isoformat()}, now)
        self.assertEqual(result, ("Updated within 1 hour", "ok"))
        self.assertEqual(freshness({"updated_at": "broken"}, now), ("Timestamp unavailable", "warn"))


if __name__ == "__main__":
    unittest.main()
