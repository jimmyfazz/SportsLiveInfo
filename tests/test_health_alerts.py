"""Stall alerting: thresholds, hysteresis, de-duplication, recovery, notify failures, /healthz codes. No network."""
import json
import os
import tempfile
import unittest
import urllib.error
import urllib.request
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from ingress_test_support import IngressTestClient
from sportsliveinfo import health
from sportsliveinfo.storage import Store

D = lambda h, m=0, day=20: datetime(2026, 11, day, h, m, tzinfo=timezone.utc)   # November: London == UTC
START = D(0, 0, 19)
SETTINGS = {"stall_hours": 3.0}


def iso(t):
    return t.isoformat(timespec="seconds")


class HealthCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "s.sqlite3")
        self.store.configure({"setup_complete": True,
                              "github": {"enabled": True, "auto_publish": True, "token": "ghp_SECRETTOKEN"},
                              "publication_approvals": ["jolpica"]})
        health._TOKEN_EXPIRY.update(seen=False, value=None)
        health._LAST_TICK.clear()

    def tearDown(self):
        self.temp.cleanup()

    def beat(self, t):
        self.store._put("scheduler_heartbeat", iso(t))

    def published(self, t):
        self.store._put("feed_state", {"last_revision": "r", "revisions": [], "published_at": iso(t)})

    def evaluate(self, now):
        self.beat(now)           # healthy scheduler unless a test says otherwise
        return health.evaluate(self.store, now, settings=SETTINGS, started_at=START)

    def codes(self, report):
        return [i["code"] for i in report["incidents"]]


class ThresholdTests(HealthCase):
    def test_20_nov_case_manifest_overdue_after_grace(self):
        self.published(D(3, 42))
        self.assertTrue(self.evaluate(D(6, 59))["ok"])               # 04:00 slot is not yet 3 h old
        report = self.evaluate(D(7, 5))
        self.assertFalse(report["ok"])
        self.assertEqual(self.codes(report), ["manifest_overdue"])
        self.assertIn("04:00", report["reasons"][0]["message"].replace("T04:00:00+00:00", " 04:00"))

    def test_quiet_period_between_slots_is_not_stalled(self):
        self.published(D(17, 2))
        self.assertTrue(self.evaluate(D(23))["ok"])                  # 17:00 run published; next slot 04:00
        self.assertTrue(self.evaluate(D(3, 30, 21))["ok"])

    def test_unchanged_publish_attempt_counts_as_activity(self):
        self.published(D(2))
        self.store.job("publisher", "unchanged", "Feed revision r already published")
        with patch("sportsliveinfo.health.snapshot", wraps=health.snapshot):
            row_time = self.store.recent_jobs(1)[0]["time"]
        now = datetime.fromisoformat(row_time) + timedelta(minutes=5)
        self.beat(now)
        self.store._put("feed_state", {"last_revision": "r", "revisions": [], "published_at": iso(now - timedelta(hours=30))})
        report = health.evaluate(self.store, now, settings=SETTINGS, started_at=START)
        self.assertNotIn("manifest_old", self.codes(report))

    def test_hard_ceiling_when_no_schedule_slot_applies(self):
        self.store.configure({"schedule": ["04:00"]})
        self.published(D(4, 5, 19))
        self.assertEqual(self.codes(self.evaluate(D(1, 0, 21))), ["manifest_overdue"])   # slot 04:00 on 20th missed too

    def test_not_alerted_when_publishing_not_expected_or_never_published(self):
        self.assertTrue(self.evaluate(D(23))["ok"])                  # never published
        self.published(D(1))
        self.store.configure({"github": {"auto_publish": False}})
        self.assertTrue(self.evaluate(D(23))["ok"])

    def test_scheduler_heartbeat_stale_and_restart_grace(self):
        self.store._put("scheduler_heartbeat", iso(D(10)))
        report = health.evaluate(self.store, D(10, 4), settings=SETTINGS, started_at=START)
        self.assertEqual([r["code"] for r in report["reasons"]], ["scheduler_stalled"])
        self.store._put("health_state", {})
        fresh = health.evaluate(self.store, D(10, 4), settings=SETTINGS, started_at=D(10, 3))   # process just restarted
        self.assertTrue(fresh["ok"])

    def test_failing_source_publish_blocked_and_token_expiry_are_advisory(self):
        for _ in range(3):
            self.store.job("jolpica", "failed", "boom")
        for _ in range(2):
            self.store.job("publisher", "failed", "GitHub HTTP 401")
        health._TOKEN_EXPIRY.update(seen=True, value=D(12) + timedelta(days=3))
        report = self.evaluate(D(12))
        self.assertEqual(self.codes(report), ["publish_blocked", "source_failing:jolpica", "token_expiring"])
        self.assertTrue(report["ok"])                                # advisory: /healthz stays 200
        self.assertEqual(report["snapshot"]["token_days_left"], 3.0)

    def test_threshold_setting(self):
        self.assertEqual(health.stall_threshold_hours(env={"SLI_STALL_HOURS": "5"}), 5.0)
        self.assertEqual(health.stall_threshold_hours(env={"SLI_STALL_HOURS": "junk"}), 3.0)
        self.assertEqual(health.stall_threshold_hours(env={"SLI_STALL_HOURS": "0"}), 3.0)
        path = Path(self.temp.name) / "options.json"
        path.write_text(json.dumps({"stall_threshold_hours": 6}))
        self.assertEqual(health.stall_threshold_hours(options_path=path, env={}), 6.0)
        self.assertEqual(health.stall_threshold_hours(options_path=Path(self.temp.name) / "none.json", env={}), 3.0)

    def test_github_expiry_header_parsed(self):
        class R:
            headers = {"github-authentication-token-expiration": "2026-12-01 00:00:00 UTC"}
        health.note_github_response(R())
        self.assertEqual(health._TOKEN_EXPIRY["value"], datetime(2026, 12, 1, tzinfo=timezone.utc))
        health.note_github_response(object())                        # never raises
        health.note_github_response(type("R", (), {"headers": {}})())
        self.assertIsNone(health._TOKEN_EXPIRY["value"])


class HysteresisTests(HealthCase):
    def test_stall_latches_and_clears_only_after_hold(self):
        self.published(D(3, 42))
        self.assertFalse(self.evaluate(D(7, 10))["ok"])
        self.published(D(7, 12))                                     # publication recovers the condition
        report = self.evaluate(D(7, 13))
        self.assertTrue(report["ok"] is False or report["incidents"][0]["recovering"])
        self.assertTrue(self.evaluate(D(7, 13))["incidents"][0]["recovering"])
        self.assertEqual(self.codes(self.evaluate(D(7, 20))), ["manifest_overdue"])   # 7 min < 10 min hold
        self.assertEqual(self.codes(self.evaluate(D(7, 24))), [])

    def test_recovery_then_relapse_restarts_the_hold(self):
        self.published(D(3, 42))
        self.evaluate(D(7, 10))
        self.published(D(7, 11))
        self.evaluate(D(7, 12))
        self.published(D(3, 42))                                     # condition returns inside the hold
        report = self.evaluate(D(7, 15))
        self.assertFalse(report["incidents"][0].get("recovering"))
        self.assertEqual(report["incidents"][0]["since"], iso(D(7, 10)))   # same incident, not a new one

    def test_heartbeat_uses_separate_enter_and_leave_thresholds(self):
        self.store._put("scheduler_heartbeat", iso(D(10)))
        now = D(10, 3, )
        self.assertFalse(health.evaluate(self.store, now + timedelta(seconds=1), settings=SETTINGS, started_at=START)["ok"])  # 181 s
        self.store._put("scheduler_heartbeat", iso(now - timedelta(seconds=100)))     # 100 s: below enter, above leave
        report = health.evaluate(self.store, now, settings=SETTINGS, started_at=START)
        self.assertEqual([r["code"] for r in report["incidents"]], ["scheduler_stalled"])
        self.assertFalse(report["incidents"][0].get("recovering"))


class NotifierTests(HealthCase):
    def setUp(self):
        super().setUp()
        self.calls = []
        self.notifier = health.Notifier(self.store, post=lambda service, payload: self.calls.append((service, payload)))

    def sync(self, now):
        return self.notifier.sync(self.evaluate(now)["incidents"], now)

    def test_one_notification_per_incident_then_dismissed(self):
        self.published(D(3, 42))
        self.sync(D(7, 10))
        self.sync(D(7, 11))
        self.sync(D(9, 0))
        creates = [c for c in self.calls if c[0] == "create"]
        self.assertEqual(len(creates), 1)
        self.assertEqual(creates[0][1]["notification_id"], "sportsliveinfo_feed_stalled")
        self.assertNotIn("SECRET", json.dumps(self.calls))
        self.published(D(9, 5))
        self.sync(D(9, 6))
        self.assertEqual(len([c for c in self.calls if c[0] == "dismiss"]), 0)    # still inside the hold
        self.sync(D(9, 20))
        self.assertEqual([c for c in self.calls if c[0] == "dismiss"],
                         [("dismiss", {"notification_id": "sportsliveinfo_feed_stalled"})])
        self.assertEqual(self.store._get("health_alerts"), {})
        self.sync(D(9, 25))
        self.assertEqual(len(self.calls), 2)

    def test_new_incident_after_recovery_notifies_again(self):
        self.published(D(3, 42))
        self.sync(D(7, 10))
        self.published(D(7, 11)); self.sync(D(7, 12)); self.sync(D(7, 30))
        self.published(D(7, 31))
        self.published(D(7, 31))
        self.sync(D(12, 5))                                          # 12:00 slot overdue? due at 15:00, so not yet
        self.assertEqual(len([c for c in self.calls if c[0] == "create"]), 1)
        self.sync(D(15, 5))
        self.assertEqual(len([c for c in self.calls if c[0] == "create"]), 2)

    def test_notify_failure_is_swallowed_logged_and_retried_later(self):
        def broken(service, payload):
            raise urllib.error.URLError("token=ghp_SECRETTOKEN refused")
        notifier = health.Notifier(self.store, post=broken)
        self.published(D(3, 42))
        with self.assertLogs("sportsliveinfo.health", level="WARNING") as logs:
            ledger = notifier.sync(self.evaluate(D(7, 10))["incidents"], D(7, 10))
        self.assertFalse(ledger["sportsliveinfo_feed_stalled"]["notified"])
        self.assertNotIn("SECRET", "\n".join(logs.output))
        self.assertIn("URLError", "\n".join(logs.output))
        notifier._post = lambda s, p: self.calls.append((s, p))
        notifier.sync(self.evaluate(D(7, 12))["incidents"], D(7, 12))        # inside the retry interval
        self.assertEqual(self.calls, [])
        notifier.sync(self.evaluate(D(7, 30))["incidents"], D(7, 30))
        self.assertEqual(len(self.calls), 1)

    def test_dismiss_failure_keeps_ledger_for_retry(self):
        self.published(D(3, 42))
        self.sync(D(7, 10))
        self.published(D(7, 11)); self.sync(D(7, 12))
        self.notifier._post = lambda s, p: (_ for _ in ()).throw(OSError("down"))
        self.sync(D(7, 30))
        self.assertTrue(self.store._get("health_alerts")["sportsliveinfo_feed_stalled"]["dismiss_pending"])
        self.notifier._post = lambda s, p: self.calls.append((s, p))
        self.sync(D(7, 50))
        self.assertEqual(self.calls[-1][0], "dismiss")
        self.assertEqual(self.store._get("health_alerts"), {})

    def test_disabled_without_supervisor_token(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SUPERVISOR_TOKEN", None)
            notifier = health.Notifier(self.store)
        self.assertFalse(notifier.enabled)
        self.published(D(3, 42))
        self.assertEqual(notifier.sync(self.evaluate(D(7, 10))["incidents"], D(7, 10)), {})

    def test_supervisor_request_shape_and_no_proxy(self):
        seen = {}

        class Opener:
            def open(self, request, timeout=0):
                seen.update(url=request.full_url, auth=request.get_header("Authorization"), body=json.loads(request.data))
                return type("R", (), {"read": lambda self, n: b"", "__enter__": lambda s: s, "__exit__": lambda *a: None})()
        with patch("urllib.request.build_opener", return_value=Opener()):
            health._supervisor_post("create", {"notification_id": "x"}, "TOKEN")
        self.assertEqual(seen["url"], "http://supervisor/core/api/services/persistent_notification/create")
        self.assertEqual(seen["auth"], "Bearer TOKEN")

    def test_tick_is_throttled_and_never_raises(self):
        self.published(D(3, 42))
        self.beat(D(7, 10))
        first = health.tick(self.store, D(7, 10), notifier=self.notifier)
        self.assertIsNotNone(first)
        self.assertIsNone(health.tick(self.store, D(7, 10, ) + timedelta(seconds=30), notifier=self.notifier))
        with patch("sportsliveinfo.health.evaluate", side_effect=RuntimeError("x")):
            self.assertIsNone(health.tick(self.store, D(8), notifier=self.notifier))

    def test_no_network_at_import(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network")), \
             patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("network")):
            import importlib
            importlib.reload(health)


class HealthzTests(HealthCase):
    def get(self, path):
        with closing(IngressTestClient(self.store, "csrf")) as client:
            try:
                with client.open(client.base + path) as response:
                    return response.status, json.loads(response.read())
            except urllib.error.HTTPError as exc:
                return exc.code, json.loads(exc.read())

    def test_200_when_healthy_and_503_with_reason_when_stalled(self):
        now = datetime.now(timezone.utc)
        self.beat(now)
        self.published(now - timedelta(minutes=5))
        status, body = self.get("healthz")
        self.assertEqual((status, body["ok"]), (200, True))
        self.assertIn("manifest_age_s", body)
        self.store._put("scheduler_heartbeat", iso(now - timedelta(minutes=30)))
        with patch("sportsliveinfo.health.PROCESS_START", now - timedelta(hours=1)):
            status, body = self.get("healthz")
            self.assertEqual(status, 503)
            self.assertFalse(body["ok"])
            self.assertIn("heartbeat", body["reason"])
            self.assertEqual(body["reasons"], ["scheduler_stalled"])
            self.assertEqual(self.get("healthz?scope=liveness")[0], 503)

    def test_manifest_overdue_is_503_but_liveness_stays_200(self):
        now = datetime.now(timezone.utc)
        self.beat(now)
        self.store.configure({"schedule": [(now - timedelta(hours=5)).astimezone(health.LONDON).strftime("%H:%M")]})
        self.published(now - timedelta(hours=9))
        status, body = self.get("healthz")
        self.assertEqual(status, 503)
        self.assertEqual(body["reasons"], ["manifest_overdue"])
        self.assertEqual(self.get("healthz?scope=liveness")[0], 200)

    def test_healthz_survives_health_failure(self):
        with patch("sportsliveinfo.health.evaluate", side_effect=RuntimeError("boom")):
            status, body = self.get("healthz")
        self.assertEqual(status, 200)
        self.assertEqual(body["health_check_error"], "RuntimeError")

    def test_status_page_shows_service_health(self):
        now = datetime.now(timezone.utc)
        self.beat(now)
        with closing(IngressTestClient(self.store, "csrf")) as client:
            with client.open(client.base + "?page=health") as response:
                page = response.read().decode()
        self.assertIn("Service health", page)
        self.assertIn("Last successful collection", page)
        self.assertNotIn("SECRETTOKEN", page)


class PackagingTests(unittest.TestCase):
    def test_config_declares_http_watchdog_and_ha_api(self):
        config = (Path(__file__).resolve().parents[1] / "sportsliveinfo" / "config.yaml").read_text()
        self.assertIn('watchdog: "http://[HOST]:[PORT:8099]/healthz?scope=liveness"', config)
        self.assertIn("homeassistant_api: true", config)
        self.assertIn("stall_threshold_hours", config)


if __name__ == "__main__":
    unittest.main()


class PublishGateBlockedTests(HealthCase):
    """A refusal by the pre-publish regression gate (job state 'blocked') used to raise no alert at all."""

    def block(self):
        self.store.job("publisher", "blocked", "Automatic publish refused: events fell from 100 to 50")
        self.store._put("publish_gate", {"blocked_at": iso(D(12)), "reason": "events fell from 100 to 50 (more than 20%)",
                                         "events_before": 100, "events_after": 50,
                                         "bindings_before": 40, "bindings_after": 38})

    def now(self):
        return datetime.fromisoformat(self.store.recent_jobs(1)[0]["time"]) + timedelta(minutes=1)

    def test_blocked_publish_is_an_advisory_incident_with_override_text(self):
        self.block()
        self.published(self.now() - timedelta(minutes=10))
        now = self.now()
        report = self.evaluate(now)
        self.assertEqual(self.codes(report), ["publish_gate_blocked"])
        self.assertTrue(report["ok"])                                # advisory: no 503
        message = report["incidents"][0]["message"]
        for text in ("events 100 -> 50", "bindings 40 -> 38", "Publish feed now", "previous feed stays live"):
            self.assertIn(text, message)
        code, body = health.healthz(self.store, "x", now=now, started_at=START)
        self.assertEqual(code, 200)
        self.assertEqual(body["advisories"][0]["code"], "publish_gate_blocked")
        self.assertNotIn("reasons", body)

    def test_notification_is_sent_once_and_dismissed_on_recovery(self):
        self.block()
        self.published(self.now() - timedelta(minutes=10))
        sent = []
        notifier = health.Notifier(self.store, post=lambda service, payload: sent.append((service, payload)))
        now = self.now()
        for step in range(3):
            self.beat(now + timedelta(minutes=step))
            notifier.sync(health.evaluate(self.store, now + timedelta(minutes=step), settings=SETTINGS, started_at=START)["incidents"],
                          now + timedelta(minutes=step))
        creates = [p for s, p in sent if s == "create"]
        self.assertEqual(len(creates), 1)
        self.assertEqual(creates[0]["notification_id"], "sportsliveinfo_publish_gate_blocked")
        self.assertIn("Publish feed now", creates[0]["message"])
        self.assertIn("events 100 -> 50", creates[0]["message"])
        self.store.job("publisher", "submitted", "Feed committed")          # manual override succeeded
        later = now + timedelta(minutes=20)
        for at in (later, later + timedelta(minutes=11)):
            self.beat(at)
            notifier.sync(health.evaluate(self.store, at, settings=SETTINGS, started_at=START)["incidents"], at)
        self.assertEqual([p["notification_id"] for s, p in sent if s == "dismiss"], ["sportsliveinfo_publish_gate_blocked"])

    def test_preview_row_does_not_clear_it_and_failure_chain_unaffected(self):
        self.block()
        self.published(self.now() - timedelta(minutes=10))
        self.store.job("publisher", "preview", "built locally")
        now = self.now()
        self.assertEqual(self.codes(self.evaluate(now)), ["publish_gate_blocked"])
