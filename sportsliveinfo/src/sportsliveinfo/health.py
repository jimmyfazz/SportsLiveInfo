"""Stall detection, /healthz verdicts and Home Assistant persistent notifications.

Background: on 20 Nov 2026 the published manifest stayed at 03:42Z for 3.5+ hours and nobody was told. This module
computes one health report from state the App already keeps (jobs table, ``feed_state``, ``publish_status``,
``scheduler_heartbeat``, request ledger), decides whether the service is *stalled*, and tells the owner through a
Home Assistant persistent notification (Supervisor API) once per incident.

Design rules
- No network call at import time. The only network call is the Supervisor notification POST, made from the
  scheduler thread, never from an HTTP request handler.
- Every failure to notify is swallowed and logged as an exception *type* only: no token, URL body or response text.
- "Manifest is old" is judged against the owner's refresh schedule, not a flat clock: the feed legitimately stays
  unchanged between the 04:00/12:00/17:00 runs (and an unchanged revision is only recommitted after 24 h). A manifest
  is overdue when a scheduled slot passed more than ``stall_threshold_hours`` ago with no publication activity since.
  Between a slot's grace period and the next slot there is no separate "quiet period" to configure; the hard ceiling
  ``MAX_MANIFEST_AGE`` (30 h, before the 48 h expiry) catches anything else.
- Hysteresis: a stall latches when first seen and clears only after the condition has been false for a hold time
  (10 min for the manifest, 2 min for the scheduler), and the scheduler heartbeat uses different enter (180 s) and
  leave (60 s) thresholds, so a borderline value cannot flap the verdict or the notification.
"""
import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

LOGGER = logging.getLogger("sportsliveinfo.health")
LONDON = ZoneInfo("Europe/London")
PROCESS_START = datetime.now(timezone.utc)

DEFAULT_STALL_HOURS = 3.0
HEARTBEAT_ENTER = timedelta(seconds=180)   # scheduler ticks every 10 s
HEARTBEAT_LEAVE = timedelta(seconds=60)
HOLD = {"scheduler_stalled": timedelta(minutes=2)}
DEFAULT_HOLD = timedelta(minutes=10)
MAX_MANIFEST_AGE = timedelta(hours=30)
COLLECT_HANG = timedelta(minutes=90)
TOKEN_WARN_DAYS = 7
SOURCE_FAIL_THRESHOLD = 3
PUBLISH_FAIL_THRESHOLD = 2
NOTIFY_RETRY = timedelta(minutes=15)
TICK_INTERVAL = timedelta(seconds=60)
NOTIFY_URL = "http://supervisor/core/api/services/persistent_notification/%s"
# Reasons that make /healthz answer 503. ``scheduler_stalled`` is also the only reason for the liveness scope used by
# the Supervisor watchdog (restarting cannot fix a stale manifest caused by a revoked token or a failing source).
STALL_CODES = ("scheduler_stalled", "manifest_overdue", "manifest_old")
NON_SOURCE_JOBS = {"collector", "publisher", "private_publisher", "scheduler", "ui", "dictionary", "identity", "live_status"}

_TOKEN_EXPIRY = {"seen": False, "value": None}


# ---- settings --------------------------------------------------------------------------------------------------
def stall_threshold_hours(options_path=None, env=None):
    """Grace after a scheduled slot before the manifest counts as overdue (App option, env override, default 3 h)."""
    env = os.environ if env is None else env
    value = env.get("SLI_STALL_HOURS")
    if value is None:
        try:
            path = Path(options_path or (Path(env.get("SLI_DATA_DIR", "/data")) / "options.json"))
            value = json.loads(path.read_text()).get("stall_threshold_hours")
        except (OSError, ValueError, AttributeError):
            value = None
    try:
        hours = float(value)
    except (TypeError, ValueError):
        return DEFAULT_STALL_HOURS
    return hours if 0.5 <= hours <= 48 else DEFAULT_STALL_HOURS


def _parse(stamp):
    try:
        value = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _iso(value):
    return value.isoformat(timespec="seconds") if value else None


def _age(then, now):
    return None if then is None else max(0.0, (now - then).total_seconds())


# ---- GitHub token expiry (header GitHub sends on authenticated responses of expiring fine-grained tokens) ---------
def note_github_response(response):
    """Remember the token expiry GitHub reports; called from ``engine._github_open``. Never raises."""
    try:
        raw = response.headers.get("github-authentication-token-expiration")
        value = None
        if raw:
            value = datetime.strptime(raw.strip().replace(" UTC", ""), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        _TOKEN_EXPIRY.update(seen=True, value=value)
    except Exception:
        pass


# ---- snapshot ----------------------------------------------------------------------------------------------------
def _consecutive_failures(rows):
    fails = 0
    for row in rows:
        if row["state"] in ("failed", "test_failed"):
            fails += 1
        elif row["state"] not in ("deferred", "needs_key"):
            break
    return fails


def publish_expected(conf):
    github = conf.get("github") or {}
    return bool(conf.get("setup_complete") and github.get("enabled") and github.get("auto_publish")
                and github.get("token") and conf.get("publication_approvals"))


def snapshot(store, now=None, *, started_at=None):
    """Plain-data health report. Reads local state only."""
    now = now or datetime.now(timezone.utc)
    started_at = started_at or PROCESS_START
    conf = store.config()
    jobs = store.recent_jobs(300)
    beat = _parse(store._get("scheduler_heartbeat"))
    effective_beat = max(beat, started_at) if beat else started_at   # grace window right after a restart

    def latest(provider, states):
        for row in jobs:
            if row["provider"] == provider and row["state"] in states:
                return _parse(row["time"])
        return None

    collector = [r for r in jobs if r["provider"] == "collector"]
    last_collect_ok = latest("collector", ("finished", "degraded"))
    collect_hung_since = None
    if collector and collector[0]["state"] == "started":
        collect_hung_since = _parse(collector[0]["time"])
    feed_state = store._get("feed_state") or {}
    published_at = _parse(feed_state.get("published_at"))
    publish_activity = max([t for t in (published_at, latest("publisher", ("unchanged", "submitted"))) if t], default=None)
    status = store._get("publish_status") or {}
    publisher_rows = [r for r in jobs if r["provider"] == "publisher"]
    publish_failures = 0
    for row in publisher_rows:
        if row["state"] == "failed":
            publish_failures += 1
        else:
            break
    sources = []
    by_source = {}
    for row in jobs:
        if row["provider"] not in NON_SOURCE_JOBS and not row["state"].startswith("test_"):
            by_source.setdefault(row["provider"], []).append(row)
    for name, rows in sorted(by_source.items()):
        fails = _consecutive_failures(rows)
        if fails:
            sources.append({"name": name, "consecutive_failures": fails, "last_failure": rows[0]["time"]})
    expiry = _TOKEN_EXPIRY["value"] if _TOKEN_EXPIRY["seen"] else _parse(store._get("github_token_expiry"))
    budgets = {}
    try:
        from .engine import LIVE_DAILY_BUDGET
        budgets = {"live_daily_budget": LIVE_DAILY_BUDGET,
                   "live_calls_today": {k[5:]: v for k, v in store.usage().items() if k.startswith("live:")}}
    except Exception:
        pass
    return {
        "now": _iso(now),
        "scheduler_heartbeat": _iso(beat),
        "scheduler_heartbeat_age_s": _age(effective_beat, now),
        "last_collect_ok": _iso(last_collect_ok),
        "last_collect_state": collector[0]["state"] if collector else None,
        "collect_running_since": _iso(collect_hung_since),
        "last_publish": _iso(published_at),
        "manifest_age_s": _age(published_at, now),
        "last_publish_activity": _iso(publish_activity),
        "publish_status": {"state": status.get("state"), "at": status.get("at")},
        "publish_consecutive_failures": publish_failures,
        "publish_expected": publish_expected(conf),
        "schedule": list(conf.get("schedule") or []),
        "failing_sources": sources,
        "token_expires_at": _iso(expiry),
        "token_days_left": None if expiry is None else round((expiry - now).total_seconds() / 86400, 1),
        "budgets": budgets,
    }


def _latest_slot_due(schedule, now, grace):
    """Most recent London schedule slot that passed at least ``grace`` ago."""
    cutoff = now - grace
    best = None
    local = now.astimezone(LONDON).date()
    for back in (0, 1, 2):
        day = local - timedelta(days=back)
        for slot in schedule:
            try:
                at = datetime(day.year, day.month, day.day, int(slot[:2]), int(slot[3:5]), tzinfo=LONDON)
            except (TypeError, ValueError):
                continue
            at = at.astimezone(timezone.utc)
            if at <= cutoff and (best is None or at > best):
                best = at
    return best


def raw_reasons(snap, now, settings, active=()):
    """Conditions true right now: ``[{code, message, stall}]``. ``active`` = codes already latched (leave thresholds)."""
    hours = settings.get("stall_hours", DEFAULT_STALL_HOURS)
    grace = timedelta(hours=hours)
    out = []

    def add(code, message):
        out.append({"code": code, "message": message, "stall": code in STALL_CODES})

    beat_age = snap["scheduler_heartbeat_age_s"]
    limit = HEARTBEAT_LEAVE if "scheduler_stalled" in active else HEARTBEAT_ENTER
    if beat_age is not None and beat_age > limit.total_seconds():
        add("scheduler_stalled", "Scheduler heartbeat is %d s old (limit %d s)" % (beat_age, limit.total_seconds()))
    if snap["publish_expected"]:
        activity = _parse(snap["last_publish_activity"])
        if activity is not None:
            slot = _latest_slot_due(snap["schedule"], now, grace)
            if slot is not None and activity < slot:
                add("manifest_overdue", "No publication since %s although the %s UTC refresh was due more than %g h ago (last collection: %s)" % (
                    snap["last_publish_activity"], _iso(slot), hours, snap["last_collect_state"] or "none"))
            elif now - activity > MAX_MANIFEST_AGE:
                add("manifest_old", "Manifest is older than %d h (last publication activity %s)" % (
                    MAX_MANIFEST_AGE.total_seconds() // 3600, snap["last_publish_activity"]))
    started = _parse(snap["collect_running_since"])
    if started is not None and now - started > COLLECT_HANG:
        add("collector_hung", "A collection started at %s has not finished" % snap["collect_running_since"])
    if snap["publish_expected"] and snap["publish_consecutive_failures"] >= PUBLISH_FAIL_THRESHOLD:
        add("publish_blocked", "Publishing failed %d times in a row (see Diagnostics on the Home Assistant page)" % snap["publish_consecutive_failures"])
    left = snap["token_days_left"]
    if left is not None and left <= TOKEN_WARN_DAYS:
        add("token_expiring", "The GitHub publishing token %s" % (
            "has expired" if left <= 0 else "expires in %.0f day(s)" % left))
    for source in snap["failing_sources"]:
        if source["consecutive_failures"] >= SOURCE_FAIL_THRESHOLD:
            add("source_failing:" + source["name"], "Source %s failed %d refreshes in a row" % (source["name"], source["consecutive_failures"]))
    return out


def evaluate(store, now=None, *, settings=None, started_at=None):
    """Snapshot + hysteresis latch. Returns the report: snapshot, active incidents and the /healthz verdict."""
    now = now or datetime.now(timezone.utc)
    settings = settings or {"stall_hours": stall_threshold_hours()}
    snap = snapshot(store, now, started_at=started_at)
    latch = store._get("health_state") or {}
    latch = {c: dict(v) for c, v in latch.items() if isinstance(v, dict)}
    raws = {r["code"]: r for r in raw_reasons(snap, now, settings, active=set(latch))}
    for code, reason in raws.items():
        entry = latch.setdefault(code, {"since": _iso(now)})
        entry.pop("clear_since", None)
        entry["message"] = reason["message"]
    for code in list(latch):
        if code in raws:
            continue
        entry = latch[code]
        entry.setdefault("clear_since", _iso(now))
        hold = HOLD.get(code, DEFAULT_HOLD)
        if now - (_parse(entry["clear_since"]) or now) >= hold:
            del latch[code]
    store._put("health_state", latch)
    incidents = [{"code": c, "since": v.get("since"), "message": v.get("message", ""), "stall": c in STALL_CODES,
                  "recovering": "clear_since" in v} for c, v in sorted(latch.items())]
    stalled = [i for i in incidents if i["stall"]]
    return {"ok": not stalled, "reasons": stalled, "incidents": incidents, "snapshot": snap,
            "settings": settings}


def liveness(store, now=None, *, started_at=None):
    """Supervisor-watchdog verdict: scheduler heartbeat only, no latch (a restart must not be punished for 10 minutes)."""
    now = now or datetime.now(timezone.utc)
    snap = snapshot(store, now, started_at=started_at)
    age = snap["scheduler_heartbeat_age_s"]
    bad = age is not None and age > HEARTBEAT_ENTER.total_seconds()
    reasons = [{"code": "scheduler_stalled", "message": "Scheduler heartbeat is %d s old" % age}] if bad else []
    return {"ok": not bad, "reasons": reasons}


def healthz(store, version, scope="", now=None, *, started_at=None):
    """``(http_status, body_dict)`` for /healthz. 503 = stalled, 200 = healthy (advisory incidents stay 200)."""
    try:
        if scope == "liveness":
            report = liveness(store, now, started_at=started_at)
            snap = {}
        else:
            report = evaluate(store, now, started_at=started_at)
            snap = report["snapshot"]
    except Exception as exc:  # a broken health check must not take the service down
        LOGGER.warning("Health evaluation failed (%s)", type(exc).__name__)
        return 200, {"ok": True, "version": version, "health_check_error": type(exc).__name__}
    body = {"ok": report["ok"], "version": version, "scheduler_heartbeat": snap.get("scheduler_heartbeat")}
    if not report["ok"]:
        body["reason"] = "; ".join(r["message"] for r in report["reasons"])
        body["reasons"] = [r["code"] for r in report["reasons"]]
    if scope != "liveness":
        body["incidents"] = [i["code"] for i in report["incidents"]]
        body["manifest_age_s"] = snap.get("manifest_age_s")
        body["last_publish"] = snap.get("last_publish")
        body["last_collect_ok"] = snap.get("last_collect_ok")
    return (200 if report["ok"] else 503), body


# ---- Home Assistant notifications --------------------------------------------------------------------------------
TITLES = {
    "scheduler_stalled": "SportsLiveInfo: scheduler stopped",
    "manifest_overdue": "SportsLiveInfo: feed not published",
    "manifest_old": "SportsLiveInfo: feed not published",
    "collector_hung": "SportsLiveInfo: collection stuck",
    "publish_blocked": "SportsLiveInfo: publishing is failing",
    "token_expiring": "SportsLiveInfo: GitHub token expiring",
}


def notification_id(code):
    """Stable id per incident kind. The stall codes share one notification."""
    if code in ("manifest_overdue", "manifest_old"):
        code = "feed_stalled"
    return "sportsliveinfo_" + "".join(ch if ch.isalnum() else "_" for ch in code)


def _supervisor_post(path, payload, token, timeout=10):
    """POST to the Supervisor's Home Assistant Core proxy. Fixed URL; ignores proxy environment variables."""
    request = urllib.request.Request(
        NOTIFY_URL % path, method="POST", data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        response.read(2000)


class Notifier:
    """De-duplicated persistent notifications: one per incident, dismissed on recovery.

    ``post(service, payload)`` is injectable for tests. Without SUPERVISOR_TOKEN (development, tests) it does nothing.
    """

    def __init__(self, store, post=None, token=None):
        self.store = store
        self.token = os.environ.get("SUPERVISOR_TOKEN") if token is None else token
        self._post = post

    @property
    def enabled(self):
        return bool(self._post or self.token)

    def _send(self, service, payload):
        try:
            if self._post:
                self._post(service, payload)
            else:
                _supervisor_post(service, payload, self.token)
            return True
        except urllib.error.HTTPError as exc:
            LOGGER.warning("Home Assistant notification %s failed (HTTP %d)", service, exc.code)
        except Exception as exc:  # never raise out of alerting; never log the token or the response
            LOGGER.warning("Home Assistant notification %s failed (%s)", service, type(exc).__name__)
        return False

    def sync(self, incidents, now=None):
        """Create a notification for each new incident, dismiss those that recovered. Returns the persisted ledger."""
        now = now or datetime.now(timezone.utc)
        if not self.enabled:
            return {}
        ledger = self.store._get("health_alerts") or {}
        desired = {}
        for incident in incidents:
            if incident.get("recovering"):
                continue                      # latched but already clear: keep the notification until it is dismissed
            nid = notification_id(incident["code"])
            desired.setdefault(nid, incident)
        latched = {notification_id(i["code"]) for i in incidents}
        for nid, incident in desired.items():
            entry = ledger.setdefault(nid, {"since": _iso(now), "notified": False})
            if entry.get("notified"):
                continue
            last = _parse(entry.get("last_try"))
            if last and now - last < NOTIFY_RETRY:
                continue
            entry["last_try"] = _iso(now)
            code = incident["code"].split(":")[0]
            title = TITLES.get(code, "SportsLiveInfo: source failing" if code == "source_failing" else "SportsLiveInfo alert")
            if self._send("create", {"notification_id": nid, "title": title,
                                     "message": "%s. Since %s UTC. Open SportsLiveInfo > Diagnostics for details." % (
                                         incident["message"], incident.get("since") or _iso(now))}):
                entry["notified"] = True
        for nid in list(ledger):
            if nid in latched:
                continue                      # recovering: wait for the hold time before dismissing
            entry = ledger[nid]
            if not entry.get("notified"):
                del ledger[nid]               # never sent: nothing to dismiss
                continue
            last = _parse(entry.get("last_try"))
            if entry.get("dismiss_pending") and last and now - last < NOTIFY_RETRY:
                continue
            entry["dismiss_pending"], entry["last_try"] = True, _iso(now)
            if self._send("dismiss", {"notification_id": nid}):
                del ledger[nid]
        self.store._put("health_alerts", ledger)
        return ledger


# ---- scheduler hook ----------------------------------------------------------------------------------------------
_LAST_TICK = {}


def tick(store, now=None, *, notifier=None, force=False):
    """Called from the scheduler thread each loop; evaluates at most once a minute. Never raises."""
    try:
        now = now or datetime.now(timezone.utc)
        key = str(getattr(store, "path", id(store)))
        last = _LAST_TICK.get(key)
        if not force and last and now - last < TICK_INTERVAL:
            return None
        _LAST_TICK[key] = now
        if _TOKEN_EXPIRY["seen"]:
            store._put("github_token_expiry", _iso(_TOKEN_EXPIRY["value"]))
        report = evaluate(store, now)
        (notifier or Notifier(store)).sync(report["incidents"], now)
        return report
    except Exception as exc:
        LOGGER.warning("Health tick failed (%s)", type(exc).__name__)
        return None
