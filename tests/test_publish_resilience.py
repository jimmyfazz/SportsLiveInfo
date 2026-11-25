"""Publication resilience (owner report 25 Nov 2026).

- The regression gate must not read the London-midnight window shift (today's extra tier leaving as the day becomes
  the history day) as a loss: from 00:11 to 03:41 every live publish was refused.
- One network drop at 04:11 failed both feeds and nothing tried again: GitHub requests are now retried on transient
  errors, and a publication that still failed for such a reason is retried by the scheduler.
"""
import io
import json
import tempfile
import threading
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from sportsliveinfo import engine as engine_module
from sportsliveinfo.engine import Engine
from sportsliveinfo.storage import Store


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, limit=-1):
        return json.dumps(self.payload).encode("utf-8")


def gate_manifest(days, window_from, extra=None, bindings=10):
    assets = [{"kind": "events:" + d, "date": d, "records": n} for d, n in days.items()]
    assets += [{"kind": "events_extra:" + d, "date": d, "records": n} for d, n in (extra or {}).items()]
    return {"coverage": {"events": 2000, "guide_corroborated_broadcasts": bindings}, "assets": assets,
            "window": {"from": window_from}}


class MidnightGateTests(unittest.TestCase):
    def test_today_becoming_the_history_day_is_not_a_regression(self):
        # 23:41 on 24 Nov: today (24th) carries core and extra events.
        before = engine_module.publish_stats(gate_manifest(
            {"2026-11-23": 300, "2026-11-24": 120, "2026-11-25": 40, "2026-11-26": 30},
            "2026-11-24", extra={"2026-11-24": 600, "2026-11-25": 20}))
        # 00:11 on 25 Nov: the 24th is the history day (core only); the 25th is today with its extra tier.
        after = gate_manifest({"2026-11-24": 110, "2026-11-25": 40, "2026-11-26": 30, "2026-11-27": 25},
                              "2026-11-25", extra={"2026-11-25": 500, "2026-11-26": 15})
        self.assertIsNone(engine_module.publish_regression(before, after))
        compared = engine_module.publish_comparison(before, after)["events"]
        self.assertEqual(compared[:2], (40 + 20 + 30, 40 + 500 + 30 + 15))
        self.assertIn("2026-11-25 to 2026-11-26", compared[3])

    def test_a_real_loss_on_forward_days_still_blocks(self):
        before = engine_module.publish_stats(gate_manifest({"2026-11-25": 100, "2026-11-26": 100}, "2026-11-25"))
        after = gate_manifest({"2026-11-25": 30, "2026-11-26": 30}, "2026-11-25")
        self.assertIn("events fell from 200 to 60", engine_module.publish_regression(before, after))


class GitHubRetryTests(unittest.TestCase):
    def fake_github(self, failures):
        """Fake API: the first ``failures`` blob uploads raise ``failures``' errors, everything else answers."""
        calls = []
        errors = list(failures)

        def respond(request, timeout=30):
            url, method = request.full_url, request.get_method()
            calls.append((method, url))
            if url.endswith("/git/blobs") and errors:
                raise errors.pop(0)
            if "/git/ref/heads/" in url:
                return _Response({"object": {"sha": "head"}})
            if url.endswith("/git/commits/head"):
                return _Response({"tree": {"sha": "tree"}})
            if "/git/trees/tree" in url:
                return _Response({"tree": []})
            if url.endswith("/git/blobs"):
                return _Response({"sha": "blob"})
            if url.endswith("/git/trees"):
                return _Response({"sha": "newtree"})
            if url.endswith("/git/commits"):
                return _Response({"sha": "commit"})
            return _Response({})
        return respond, calls

    def commit(self):
        return Engine._github_commit("owner", "repo", "main", "dummy", {"v1/a.json": b"{}"}, [], "msg")

    def test_transient_network_errors_are_retried_within_one_publication(self):
        respond, calls = self.fake_github([urllib.error.URLError("down"), TimeoutError()])
        with patch.object(engine_module, "GITHUB_RETRY_DELAYS", (0, 0)), \
                patch("sportsliveinfo.engine._github_open", side_effect=respond):
            self.assertEqual(self.commit(), "commit")
        self.assertEqual(sum(1 for m, u in calls if u.endswith("/git/blobs")), 3)

    def test_server_errors_are_retried_but_a_persistent_outage_reports_the_attempts(self):
        busy = urllib.error.HTTPError("https://api.github.com/x", 502, "bad gateway", {}, io.BytesIO())
        respond, _ = self.fake_github([busy])
        with patch.object(engine_module, "GITHUB_RETRY_DELAYS", (0, 0)), \
                patch("sportsliveinfo.engine._github_open", side_effect=respond):
            self.assertEqual(self.commit(), "commit")
        respond, _ = self.fake_github([urllib.error.URLError("down")] * 3)
        with patch.object(engine_module, "GITHUB_RETRY_DELAYS", (0, 0)), \
                patch("sportsliveinfo.engine._github_open", side_effect=respond):
            with self.assertRaisesRegex(RuntimeError, r"Could not reach GitHub while uploading feed files \(URLError, 3 attempts\)"):
                self.commit()

    def test_permission_errors_are_not_retried(self):
        denied = urllib.error.HTTPError("https://api.github.com/x", 403, "denied", {}, io.BytesIO())
        respond, calls = self.fake_github([denied])
        with patch.object(engine_module, "GITHUB_RETRY_DELAYS", (0, 0)), \
                patch("sportsliveinfo.engine._github_open", side_effect=respond):
            with self.assertRaisesRegex(RuntimeError, "GitHub HTTP 403"):
                self.commit()
        self.assertEqual(sum(1 for m, u in calls if u.endswith("/git/blobs")), 1)


class ScheduledPublishRetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "state.sqlite3")
        self.store.configure({"setup_complete": True, "publication_approvals": ["football_data"],
                              "github": {"enabled": True, "auto_publish": True, "token": "dummy"}})
        self.engine = Engine(self.store)
        self.runs = []

    def tearDown(self):
        self.temp.cleanup()

    def failed(self, message, minutes_ago, trigger="automatic"):
        at = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()
        self.store._put("publish_status", {"state": "failed", "message": message, "trigger": trigger, "at": at})

    def tick(self):
        done = threading.Event()

        def fake_job(trigger):
            self.runs.append(trigger)
            done.set()
        with patch.object(self.engine, "_publish_job", side_effect=fake_job):
            self.engine._publish_retry_tick(self.store.config())
            done.wait(0.5)

    def test_a_network_failure_is_retried_after_the_interval(self):
        self.failed("Could not reach GitHub while uploading feed files (URLError, 3 attempts); publish again", 3)
        self.tick()
        self.assertEqual(self.runs, [])                                   # too soon
        self.failed("Could not reach GitHub while uploading feed files (URLError, 3 attempts); publish again", 11)
        self.tick()
        self.assertEqual(self.runs, ["retry"])
        self.assertEqual(self.store._get("publish_retry")["count"], 1)

    def test_a_private_feed_network_failure_is_retried_too(self):
        self.failed("Feed abc committed to GitHub; private feed failed: Could not reach GitHub while checking the "
                    "repository (URLError, 3 attempts); publish again", 11)
        self.tick()
        self.assertEqual(self.runs, ["retry"])

    def test_gate_refusals_and_other_failures_are_never_retried(self):
        self.failed("Automatic publish refused: events fell from 100 to 50 (more than 20%); the previous feed stays "
                    "live. Publish manually to override", 30)
        self.tick()
        self.failed("GitHub HTTP 403 while uploading feed files: the token cannot write here", 30)
        self.tick()
        self.assertEqual(self.runs, [])

    def test_retries_stop_after_the_maximum_and_a_new_failure_starts_again(self):
        message = "Could not reach GitHub while reading the feed branch (TimeoutError, 3 attempts); publish again"
        for _ in range(engine_module.PUBLISH_RETRY_MAX + 2):
            self.failed(message, 11, trigger="retry")
            self.tick()
        self.assertEqual(len(self.runs), engine_module.PUBLISH_RETRY_MAX)
        retry = self.store._get("publish_retry")                          # the series ended 20 minutes ago ...
        self.store._put("publish_retry", dict(retry, last=(datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()))
        self.failed(message, 11, trigger="live")                          # ... and a later live publish failed afresh
        self.tick()
        self.assertEqual(len(self.runs), engine_module.PUBLISH_RETRY_MAX + 1)

    def test_success_clears_the_retry_series(self):
        self.store._put("publish_retry", {"count": 3, "last": "2026-11-25T04:30:00+00:00"})
        self.store._put("publish_status", {"state": "succeeded", "message": "Feed abc committed to GitHub",
                                           "trigger": "retry", "at": datetime.now(timezone.utc).isoformat()})
        self.tick()
        self.assertEqual(self.store._get("publish_retry"), {})
        self.assertEqual(self.runs, [])

    def test_no_retry_while_publishing_is_off(self):
        self.store.configure({"github": {"auto_publish": False}})
        self.failed("Could not reach GitHub while uploading feed files (URLError, 3 attempts); publish again", 30)
        self.tick()
        self.assertEqual(self.runs, [])


if __name__ == "__main__":
    unittest.main()
