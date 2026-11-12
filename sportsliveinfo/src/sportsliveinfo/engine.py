"""Independent collector lanes with last-good snapshots, quotas and private defaults."""
import base64
import hashlib
import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import providers
from .storage import utcnow
from .guide import analyze_guide

LOGGER = logging.getLogger(__name__)


class Engine:
    def __init__(self, store):
        self.store = store
        self._busy = threading.Lock()
        self._last_slot = None
        self._scheduler_stop = threading.Event()

    def collect(self):
        if not self._busy.acquire(blocking=False):
            return False
        try:
            return self._collect_locked()
        finally:
            self._busy.release()

    def _collect_locked(self):
        conf = self.store.config()
        if not conf["setup_complete"]:
            self.store.job("collector", "skipped", "Setup not completed")
            return False
        self.store.job("collector", "started")
        for name, enabled in conf["sports"].items():
            if enabled and name in providers.SPORTS:
                self._collect_sport(name, conf)
        for name, enabled in conf["epg"].items():
            if enabled and name in providers.EPG:
                self._collect_epg(name)
        self._materialize()
        self.store.job("collector", "finished")
        return True

    def _collect_sport(self, name, conf):
        _, base, key_name, daily_limit = providers.SPORTS[name]
        key = conf["keys"].get(key_name, "") if key_name else ""
        if key_name and not key:
            self.store.job(name, "needs_key", "Add a provider API key in Sources")
            return
        try:
            self.store.increment(name, daily_limit)
            if name == "jolpica":
                events = providers.f1_events(providers.fetch(base, max_bytes=3_000_000))
            elif name == "openligadb":
                now = datetime.now(ZoneInfo("Europe/Berlin"))
                season = now.year if now.month >= 7 else now.year - 1
                events = providers.openligadb_events(providers.fetch(
                    base + "/" + str(season), max_bytes=7_000_000))
            elif name == "football_data":
                start = datetime.now(ZoneInfo("Europe/London")).date()
                end = start + timedelta(days=7)
                query = urllib.parse.urlencode({"dateFrom": start.isoformat(), "dateTo": end.isoformat()})
                headers = {"X-Auth-Token": key}
                events = providers.football_data_events(providers.fetch(base + "?" + query, headers, max_bytes=5_000_000))
            else:
                # Full seven-day discovery once per 12 hours, then today's
                # fixtures only. Retain future fixtures from the previous page
                # cache; do not spend 7 calls at all three refresh slots.
                today = datetime.now(ZoneInfo("Europe/London")).date()
                previous = self.store.snapshot("sports:" + name)
                try:
                    previous_at = datetime.fromisoformat(previous["updated_at"]) if previous else None
                    recent = previous_at is not None and datetime.now(timezone.utc) - previous_at < timedelta(hours=12)
                except (ValueError, TypeError, KeyError):
                    recent = False
                day_count = 1 if recent else 7
                merged = {evt["id"]: evt for evt in (previous["data"]["events"] if previous else [])}
                for offset in range(day_count):
                    if offset:
                        self.store.increment(name, daily_limit)
                    day = (today + timedelta(days=offset)).isoformat()
                    query = urllib.parse.urlencode({"date": day, "timezone": "Europe/London"})
                    fresh = providers.api_sports_events(providers.fetch(
                        base + "?" + query, {"x-apisports-key": key}, max_bytes=7_000_000))
                    # A confirmed successful empty day should remove this
                    # day's old fixtures, but cannot imply other days empty.
                    for event_id, old_event in list(merged.items()):
                        try:
                            if datetime.fromisoformat(old_event["start_utc"]).astimezone(ZoneInfo("Europe/London")).date() == today + timedelta(days=offset):
                                del merged[event_id]
                        except (ValueError, TypeError, KeyError):
                            del merged[event_id]
                    merged.update((evt["id"], evt) for evt in fresh)
                events = list(merged.values())
            # A successful zero-result response might be valid offseason or
            # represent the limits of this provider's free competitions. Never
            # declare zero independently confirmed scheduled sport everywhere.
            self.store.save_snapshot("sports:" + name, {"events": events, "source_id": name,
                "complete": "unknown", "observed_at": utcnow()})
            self.store.job(name, "ok" if events else "no_events_reported", "%d event records (provider coverage not guaranteed)" % len(events))
        except (ValueError, RuntimeError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            # Safe errors: do not log request URLs or authentication-bearing payloads.
            self.store.job(name, "failed", type(exc).__name__ + ": source unavailable or invalid")
            LOGGER.warning("Sports source %s failed (%s)", name, type(exc).__name__)

    def _collect_epg(self, name):
        _, url = providers.EPG[name]
        try:
            self.store.increment("epg:" + name, 4)
            raw = providers.fetch(url)
            parsed = providers.decode_xmltv(raw, name)
            if not parsed["programmes"]:
                self.store.job(name, "empty", "Guide contains no valid programme rows; retaining old data")
                return
            # Enrichment/coverage report is local only and non-destructive;
            # no guessed EPG ID is ever exposed as an IPTV playable stream.
            quality = analyze_guide(parsed)
            # A guide with no programme in the next 24h is not a successful
            # forward EPG update. Preserve the previous source snapshot.
            if not any(row["coverage_hours"]["24h"] > 0 for row in quality["channels_needing_attention"]):
                # Analysis details are deliberately bounded to 30 channels,
                # so rely on source-independent full-row time check as well.
                now = datetime.now(timezone.utc)
                has_future = any(
                    datetime.fromisoformat(p["end_utc"]) > now and
                    datetime.fromisoformat(p["start_utc"]) < now + timedelta(days=1)
                    for p in parsed["programmes"]
                )
                if not has_future:
                    self.store.job(name, "stale", "No guide programmes cover the next 24h; retaining last-good")
                    return
            self.store.save_snapshot("epg:" + name, parsed)
            self.store.save_snapshot("epg-quality:" + name, quality)
            self.store.job(name, "ok", "%d channels; %d programmes; %d invalid; %d with 24h guide" % (
                len(parsed["channels"]), len(parsed["programmes"]),
                parsed["invalid_programmes"], quality["full_coverage_channels"]["24h"]))
        except (ValueError, RuntimeError, TimeoutError, OSError, EOFError, json.JSONDecodeError, ET.ParseError) as exc:
            self.store.job(name, "failed", type(exc).__name__ + ": source unavailable or invalid")
            LOGGER.warning("EPG source %s failed (%s)", name, type(exc).__name__)

    def _materialize(self):
        conf = self.store.config()
        events = {}
        sources = []
        for name, enabled in conf["sports"].items():
            if not enabled:
                continue
            entry = self.store.snapshot("sports:" + name)
            if entry:
                sources.append({"id": name, "last_success": entry["updated_at"], "events": len(entry["data"]["events"])})
                for event in entry["data"]["events"]:
                    events[event["id"]] = event
        # A rolling window prevents stale earlier-season races appearing on a TV's 'today' rail.
        london_today = datetime.now(ZoneInfo("Europe/London")).date()
        eligible = []
        for event in events.values():
            try:
                local_day = datetime.fromisoformat(event["start_utc"]).astimezone(ZoneInfo("Europe/London")).date()
                if london_today <= local_day <= london_today + timedelta(days=7):
                    eligible.append(event)
            except (ValueError, KeyError, TypeError):
                continue
        self.store.save_snapshot("sports", {"schema_version": "0.1", "events": sorted(eligible, key=lambda e: e.get("start_utc", "")), "sources": sources, "generated_at": utcnow(), "broadcast_status": "not_verified"})
        guides = []
        for name, enabled in conf["epg"].items():
            entry = self.store.snapshot("epg:" + name) if enabled else None
            if entry:
                payload = entry["data"]
                quality = self.store.snapshot("epg-quality:" + name)
                summary = quality["data"] if quality else {}
                guides.append({"id": name, "channels": len(payload["channels"]),
                    "programmes": len(payload["programmes"]), "last_success": entry["updated_at"],
                    "country": summary.get("country", "unknown"),
                    "covered_24h": summary.get("full_coverage_channels", {}).get("24h", 0),
                    "unmatched": summary.get("unmatched_canonical_channels", 0),
                    "public_redistribution": False})
        self.store.save_snapshot("epg", {"schema_version": "0.1", "generated_at": utcnow(), "sources": guides, "note": "Private source-specific schedules; publication rights not cleared"})

    def test_source(self, kind, name):
        """Probe exactly one provider; reserve one request in its quota ledger.

        Never accept a user-supplied URL or echo credential-bearing errors.
        Test results do not replace last-good data or enable publication.
        """
        conf = self.store.config()
        if kind == "sports" and name in providers.SPORTS:
            _, url, key_name, limit = providers.SPORTS[name]
            key = conf["keys"].get(key_name, "") if key_name else ""
            if key_name and not key:
                raise ValueError("Save this provider API key before testing")
            headers = {}
            if name == "jolpica":
                decoder = providers.f1_events
            elif name == "openligadb":
                now = datetime.now(ZoneInfo("Europe/Berlin"))
                season = now.year if now.month >= 7 else now.year - 1
                url += "/" + str(season)
                decoder = providers.openligadb_events
            elif name == "football_data":
                headers = {"X-Auth-Token": key}
                today = datetime.now(ZoneInfo("Europe/London")).date().isoformat()
                url += "?" + urllib.parse.urlencode({"dateFrom": today, "dateTo": today})
                decoder = providers.football_data_events
            else:
                headers = {"x-apisports-key": key}
                today = datetime.now(ZoneInfo("Europe/London")).date().isoformat()
                url += "?" + urllib.parse.urlencode({"date": today, "timezone": "Europe/London"})
                decoder = providers.api_sports_events
            self.store.increment(name, limit)
            try:
                rows = decoder(providers.fetch(url, headers=headers, max_bytes=7_000_000))
                self.store.job(name, "test_ok", "Connection valid; %d event records (coverage not guaranteed)" % len(rows))
                return "%s connection successful (%d events returned; coverage not guaranteed)" % (name, len(rows))
            except (ValueError, RuntimeError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                self.store.job(name, "test_failed", type(exc).__name__ + ": source unavailable or invalid")
                return "%s test unsuccessful; see Diagnostics" % name
        if kind == "epg" and name in providers.EPG:
            _, url = providers.EPG[name]
            self.store.increment("epg:" + name, 4)
            try:
                guide = providers.decode_xmltv(providers.fetch(url), name)
                if not guide["programmes"]:
                    raise ValueError("Empty EPG programme list")
                self.store.job(name, "test_ok", "EPG parsed, %d programme records (no stored changes)" % len(guide["programmes"]))
                return "%s EPG connection successful (%d programmes)" % (name, len(guide["programmes"]))
            except (ValueError, RuntimeError, TimeoutError, OSError, EOFError, ET.ParseError) as exc:
                self.store.job(name, "test_failed", type(exc).__name__ + ": guide unavailable or invalid")
                return "%s EPG test unsuccessful; see Diagnostics" % name
        raise ValueError("Unknown provider")

    def start_collection(self):
        # Reserve the job slot before threading: multiple UI presses must not
        # incorrectly report that additional refreshes have been scheduled.
        if not self._busy.acquire(blocking=False):
            return False
        def worker():
            try:
                self._collect_locked()
            finally:
                self._busy.release()
        thread = threading.Thread(target=worker, name="sportsliveinfo-collect", daemon=True)
        thread.start()
        return True

    def run_scheduler(self):
        """Run from a daemon thread. DST-aware and no catch-up request storm."""
        while not self._scheduler_stop.wait(10):
            conf = self.store.config()
            if not conf["setup_complete"]:
                continue
            local = datetime.now(ZoneInfo("Europe/London"))
            key = local.strftime("%Y-%m-%d %H:%M")
            if local.strftime("%H:%M") in conf.get("schedule", []) and self._last_slot != key:
                self._last_slot = key
                self.start_collection()

    def publish(self):
        """Upload only explicitly rights-approved sport source records; EPG never copied.

        Disabled by default. A candidate manifest can only be published if at least
        one sports-source licence is independently approved for public export.
        """
        conf = self.store.config()
        target = conf["github"]
        if not conf["setup_complete"] or not target.get("enabled"):
            raise ValueError("Public publishing is disabled")
        allowed = set(conf.get("publication_approvals", []))
        # No approval is supplied by default; the app cannot invent redistribution rights.
        if not allowed:
            raise ValueError("No sport source has an approved public redistribution licence")
        snap = self.store.snapshot("sports")
        if not snap:
            raise ValueError("No valid sports snapshot yet")
        events = [x for x in snap["data"]["events"] if x["source_id"] in allowed]
        if not events:
            raise ValueError("No rights-approved events to publish")
        owner, repository, branch, token = (target.get(n, "") for n in ("owner", "repository", "branch", "token"))
        if not owner or not repository or not branch or not token:
            raise ValueError("GitHub destination/token incomplete")
        if not all(v.replace("-", "").replace("_", "").isalnum() for v in [owner, repository, branch]):
            raise ValueError("Invalid GitHub repository address")
        payload = json.dumps({"schema_version": "0.1", "generated_at": utcnow(), "events": events}, separators=(",", ":"), ensure_ascii=False).encode()
        revision = hashlib.sha256(payload).hexdigest()[:20]
        asset = "data/revisions/%s/events.json" % revision
        self._github_write(owner, repository, branch, token, asset, payload)
        manifest = {"schema_version": "0.1", "revision": revision, "generated_at": utcnow(), "assets": [{"kind": "sports", "path": asset, "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}], "epg": "not_published_pending_rights"}
        self._github_write(owner, repository, branch, token, "data/manifest.json", json.dumps(manifest, separators=(",", ":")).encode())
        self.store.job("publisher", "submitted", "Sports snapshot committed; verify published static endpoint separately")
        return revision

    @staticmethod
    def _github_write(owner, repository, branch, token, path, data):
        endpoint = "https://api.github.com/repos/%s/%s/contents/%s" % (owner, repository, path)
        def request(method, body=None):
            req = urllib.request.Request(endpoint + "?ref=" + urllib.parse.quote(branch), method=method,
                 headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json", "User-Agent": "SportsLiveInfo/0.1", "Content-Type": "application/json"}, data=body)
            try:
                with urllib.request.urlopen(req, timeout=20) as res:
                    return json.loads(res.read(200_000))
            except urllib.error.HTTPError as exc:
                raise RuntimeError("GitHub API rejected request (%d)" % exc.code) from None
        sha = None
        try:
            sha = request("GET").get("sha")
        except RuntimeError:
            pass  # New object or inaccessible target; PUT will report the real failure.
        body = {"message": "SportsLiveInfo: update validated snapshot", "branch": branch, "content": base64.b64encode(data).decode()}
        if sha:
            body["sha"] = sha
        request("PUT", json.dumps(body).encode())
