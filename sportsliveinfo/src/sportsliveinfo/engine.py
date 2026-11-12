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
            conf = self.store.config()
            if not conf["setup_complete"]:
                self.store.job("collector", "skipped", "Setup not completed")
                return False
            self.store.job("collector", "started")
            # Each source has its own last-good snapshot and failure state.
            for name, enabled in conf["sports"].items():
                if enabled and name in providers.SPORTS:
                    self._collect_sport(name, conf)
            for name, enabled in conf["epg"].items():
                if enabled and name in providers.EPG:
                    self._collect_epg(name)
            self._materialize()
            self.store.job("collector", "finished")
            return True
        finally:
            self._busy.release()

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
            elif name == "football_data":
                start = datetime.now(ZoneInfo("Europe/London")).date()
                end = start + timedelta(days=7)
                query = urllib.parse.urlencode({"dateFrom": start.isoformat(), "dateTo": end.isoformat()})
                headers = {"X-Auth-Token": key}
                events = providers.football_data_events(providers.fetch(base + "?" + query, headers, max_bytes=5_000_000))
            else:
                # One date at a time to bound API-Sports daily quota; 7 days
                # are fetched at the FIRST refresh slot, then one current day
                # at midday/evening. Quota reservation is before each send.
                today = datetime.now(ZoneInfo("Europe/London")).date()
                all_events = []
                for offset in range(7):
                    if offset:
                        self.store.increment(name, daily_limit)
                    day = (today + timedelta(days=offset)).isoformat()
                    query = urllib.parse.urlencode({"date": day, "timezone": "Europe/London"})
                    all_events += providers.api_sports_events(providers.fetch(base + "?" + query, {"x-apisports-key": key}, max_bytes=7_000_000))
                events = all_events
            # Zero events for an off-season or a specific provider may be real, but
            # never erase the last-good dataset from another successful source.
            self.store.save_snapshot("sports:" + name, {"events": events, "source_id": name, "complete": bool(events), "observed_at": utcnow()})
            self.store.job(name, "ok" if events else "empty", "%d event records" % len(events))
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
            self.store.save_snapshot("epg:" + name, parsed)
            self.store.job(name, "ok", "%d channels; %d programmes; %d invalid" % (
                len(parsed["channels"]), len(parsed["programmes"]), parsed["invalid_programmes"]))
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
                guides.append({"id": name, "channels": len(payload["channels"]), "programmes": len(payload["programmes"]), "last_success": entry["updated_at"], "public_redistribution": False})
        self.store.save_snapshot("epg", {"schema_version": "0.1", "generated_at": utcnow(), "sources": guides, "note": "Private source-specific schedules; publication rights not cleared"})

    def start_collection(self):
        thread = threading.Thread(target=self.collect, name="sportsliveinfo-collect", daemon=True)
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
