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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from functools import partial
from zoneinfo import ZoneInfo

from . import linking, providers, taxonomy
from .storage import utcnow
from .guide import analyze_guide

LOGGER = logging.getLogger(__name__)
LONDON = ZoneInfo("Europe/London")
# Minimum seconds between calls to one provider (published per-minute limits).
PACING = {"thesportsdb": 2.1, "football_data": 6.5, **{n: 6.1 for n in providers.SPORTS if n.startswith("api_sports")}}
DAY_HORIZON = {**{n: 7 for n in providers.SPORTS if n.startswith("api_sports")}, "thesportsdb": 3}
SAFE_ERRORS = (ValueError, RuntimeError, TimeoutError, OSError, json.JSONDecodeError)
# Fields derived from private EPG data; never exported.
PRIVATE_FIELDS = ("broadcast_candidates", "broadcast_status", "fetch_scope", "live_state")


class QuotaExhausted(RuntimeError):
    pass


class Engine:
    def __init__(self, store):
        self.store = store
        self._busy = threading.Lock()
        self._last_slot = None
        self._scheduler_stop = threading.Event()
        self._last_call = {}

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
        sports = [n for n, on in conf["sports"].items() if on and n in providers.SPORTS]
        guides = [n for n, on in conf["epg"].items() if on and n in providers.EPG]
        # Each sports provider is its own lane; EPG guides share one sequential
        # lane so several large XMLTV parses never run at once on the mini PC.
        with ThreadPoolExecutor(max_workers=max(1, min(6, len(sports) + 1)), thread_name_prefix="sli-lane") as pool:
            futures = [pool.submit(self._collect_sport, name, conf) for name in sports]
            if guides:
                futures.append(pool.submit(lambda: [self._collect_epg(name) for name in guides]))
            for future in futures:
                try:
                    future.result()
                except Exception as exc:  # A lane bug must not stop the others or the materialiser.
                    LOGGER.error("Collector lane failed (%s)", type(exc).__name__)
                    self.store.job("collector", "lane_error", type(exc).__name__)
        self._materialize()
        self.store.job("collector", "finished")
        return True

    # ---- request planning -------------------------------------------------
    def _days(self, name, previous, today):
        try:
            recent = previous is not None and datetime.now(timezone.utc) - datetime.fromisoformat(previous["updated_at"]) < timedelta(hours=12)
        except (ValueError, TypeError, KeyError):
            recent = False
        # Full multi-day discovery at most twice a day; otherwise today only.
        return [today] if recent else [today + timedelta(days=i) for i in range(DAY_HORIZON.get(name, 1))]

    def _plan(self, name, conf, today, previous=None):
        """Return request dicts: url, headers, max_bytes, decode, scope."""
        _, base, key_name, _ = providers.SPORTS[name]
        key = conf["keys"].get(key_name, "") if key_name else ""
        options = conf.get("options", {})
        plan = []
        if name == "jolpica":
            plan.append(dict(url=base, scope="season:current", decode=providers.f1_events, max_bytes=3_000_000))
            if today.month >= 10:
                root = base.rsplit("/", 1)[0]
                plan.append(dict(url="%s/%d.json" % (root, today.year + 1), scope="season:next",
                                 decode=providers.f1_events, max_bytes=3_000_000))
        elif name == "openf1":
            plan.append(dict(url=base + "?" + urllib.parse.urlencode({"year": today.year}), scope="year:%d" % today.year,
                             decode=providers.openf1_events, max_bytes=3_000_000))
        elif name == "openligadb":
            season = today.year if today.month >= 7 else today.year - 1
            leagues = [l for l in options.get("openligadb_leagues", providers.OPENLIGADB_LEAGUES) if l in providers.OPENLIGADB_LEAGUES]
            for league in leagues:
                plan.append(dict(url="%s/%s/%d" % (base, league, season), scope="league:" + league,
                                 decode=partial(providers.openligadb_events, league=league), max_bytes=7_000_000))
        elif name == "football_data":
            query = urllib.parse.urlencode({"dateFrom": today.isoformat(), "dateTo": (today + timedelta(days=7)).isoformat()})
            plan.append(dict(url=base + "?" + query, headers={"X-Auth-Token": key}, scope="range",
                             decode=providers.football_data_events, max_bytes=5_000_000))
        elif name.startswith("api_sports"):
            sport = providers.API_SPORTS_SPORT[name]
            if name == "api_sports":
                decode = providers.api_sports_events
            elif name == "api_sports_mma":
                decode = partial(providers.api_sports_mma_events, source_id=name)
            else:
                decode = partial(providers.api_sports_games_events, source_id=name, sport=sport)
            for day in self._days(name, previous, today):
                query = urllib.parse.urlencode({"date": day.isoformat(), "timezone": "Europe/London"})
                plan.append(dict(url=base + "?" + query, headers={"x-apisports-key": key}, scope=day.isoformat(),
                                 decode=decode, max_bytes=7_000_000))
        elif name == "thesportsdb":
            chosen = [s for s in options.get("thesportsdb_sports", providers.THESPORTSDB_SPORTS) if s in providers.THESPORTSDB_SPORTS]
            for day in self._days(name, previous, today):
                for sport in chosen:
                    query = urllib.parse.urlencode({"d": day.isoformat(), "s": sport})
                    plan.append(dict(url=base + "?" + query, scope="%s|%s" % (day.isoformat(), sport),
                                     decode=providers.thesportsdb_events, max_bytes=3_000_000))
        elif name == "cricketdata":
            for offset in (0, 25):
                # Provider requires the key as a query parameter; URLs are never logged.
                query = urllib.parse.urlencode({"apikey": key, "offset": offset})
                plan.append(dict(url=base + "?" + query, scope="list", decode=providers.cricketdata_events, max_bytes=3_000_000))
        for item in plan:
            item.setdefault("headers", {})
        return plan

    def _pace(self, name):
        gap = PACING.get(name)
        if gap:
            wait = self._last_call.get(name, 0) + gap - time.monotonic()
            if wait > 0:
                time.sleep(wait)
        self._last_call[name] = time.monotonic()

    def _request(self, name, item, limit):
        try:
            self.store.increment(name, limit)
        except RuntimeError as exc:
            raise QuotaExhausted(str(exc)) from None
        self._pace(name)
        return item["decode"](providers.fetch(item["url"], item["headers"], max_bytes=item["max_bytes"]))

    @staticmethod
    def _legacy_scope(name, event):
        if name.startswith("api_sports"):
            try:
                return datetime.fromisoformat(event["start_utc"]).astimezone(LONDON).date().isoformat()
            except (KeyError, ValueError, TypeError):
                return None
        return "*"

    def _collect_sport(self, name, conf):
        _, _, key_name, daily_limit = providers.SPORTS[name]
        if key_name and not conf["keys"].get(key_name):
            self.store.job(name, "needs_key", "Add a provider API key in Sources")
            return
        today = datetime.now(LONDON).date()
        previous = self.store.snapshot("sports:" + name)
        plan = self._plan(name, conf, today, previous)
        scopes, failed, errors = {}, set(), []
        for item in plan:
            scope = item["scope"]
            if scope in failed:
                continue
            try:
                rows = self._request(name, item, daily_limit)
                scopes.setdefault(scope, []).extend(dict(r, fetch_scope=scope) for r in rows)
            except QuotaExhausted:
                errors.append("quota")
                failed.update(i["scope"] for i in plan if i["scope"] not in scopes)
                break
            except SAFE_ERRORS as exc:
                # Safe errors: do not log request URLs or authentication-bearing payloads.
                errors.append(type(exc).__name__)
                failed.add(scope)
                scopes.pop(scope, None)
        succeeded = {s for s in scopes if s not in failed}
        if not succeeded:
            self.store.job(name, "failed", "%s: source unavailable, invalid or over budget" % (errors[0] if errors else "NoRequest"))
            LOGGER.warning("Sports source %s failed (%s)", name, errors[0] if errors else "no request")
            return
        cutoff = datetime.now(timezone.utc) - timedelta(days=2)
        kept = []
        for event in (previous["data"]["events"] if previous else []):
            scope = event.get("fetch_scope") or self._legacy_scope(name, event)
            if scope == "*" or scope in succeeded:
                continue
            try:
                if datetime.fromisoformat(event["start_utc"]) < cutoff:
                    continue
            except (KeyError, ValueError, TypeError):
                continue
            kept.append(event)
        events = kept + [e for s in succeeded for e in scopes[s]]
        # A successful zero-result response might be valid offseason or the
        # limits of free coverage. Never declare zero sport everywhere.
        self.store.save_snapshot("sports:" + name, {"events": events, "source_id": name, "complete": "unknown",
                                                    "observed_at": utcnow(), "scopes_ok": sorted(succeeded),
                                                    "scopes_failed": sorted(failed)})
        state = "partial" if failed else ("ok" if events else "no_events_reported")
        self.store.job(name, state, "%d event records; %d/%d request scopes refreshed (provider coverage not guaranteed)" % (
            len(events), len(succeeded), len(succeeded) + len(failed)))

    def _collect_epg(self, name):
        _, url = providers.EPG[name]
        max_bytes, max_programmes = providers.EPG_LIMITS.get(name, providers.DEFAULT_EPG_LIMIT)
        try:
            self.store.increment("epg:" + name, 4)
            raw = providers.fetch(url, max_bytes=max_bytes)
            parsed = providers.decode_xmltv(raw, name, max_programmes=max_programmes)
            if not parsed["programmes"]:
                self.store.job(name, "empty", "Guide contains no valid programme rows; retaining old data")
                return
            # Enrichment/coverage report is local only and non-destructive;
            # no guessed EPG ID is ever exposed as an IPTV playable stream.
            quality = analyze_guide(parsed)
            now = datetime.now(timezone.utc)
            has_future = any(
                datetime.fromisoformat(p["end_utc"]) > now and datetime.fromisoformat(p["start_utc"]) < now + timedelta(days=1)
                for p in parsed["programmes"])
            # A guide with no programme in the next 24h is not a successful forward update.
            if not has_future:
                self.store.job(name, "stale", "No guide programmes cover the next 24h; retaining last-good")
                return
            self.store.save_snapshot("epg:" + name, parsed)
            self.store.save_snapshot("epg-quality:" + name, quality)
            self.store.job(name, "ok", "%d channels; %d programmes; %d invalid; %d with 24h guide; %d recognised services" % (
                len(parsed["channels"]), len(parsed["programmes"]), parsed["invalid_programmes"],
                quality["full_coverage_channels"]["24h"], len(quality["matched_canonical_channels"])))
        except (ValueError, RuntimeError, TimeoutError, OSError, EOFError, json.JSONDecodeError, ET.ParseError) as exc:
            self.store.job(name, "failed", type(exc).__name__ + ": source unavailable or invalid")
            LOGGER.warning("EPG source %s failed (%s)", name, type(exc).__name__)

    # ---- materialisation --------------------------------------------------
    def _materialize(self, now=None):
        now = now or datetime.now(timezone.utc)
        conf = self.store.config()
        raw, sources = [], []
        for name, enabled in conf["sports"].items():
            if not enabled:
                continue
            entry = self.store.snapshot("sports:" + name)
            if entry:
                sources.append({"id": name, "last_success": entry["updated_at"], "events": len(entry["data"]["events"])})
                raw.extend(entry["data"]["events"])
        merged = linking.merge_events([taxonomy.classify(e) for e in raw])
        # A rolling window prevents stale earlier-season races appearing on a TV's 'today' rail.
        london_today = now.astimezone(LONDON).date()
        eligible = []
        for event in merged:
            try:
                local_day = datetime.fromisoformat(event["start_utc"]).astimezone(LONDON).date()
                if london_today <= local_day <= london_today + timedelta(days=7):
                    eligible.append(event)
            except (ValueError, KeyError, TypeError):
                continue
        guides, epg_data = [], {}
        for name, enabled in conf["epg"].items():
            entry = self.store.snapshot("epg:" + name) if enabled else None
            if entry:
                payload = entry["data"]
                epg_data[name] = payload
                quality = self.store.snapshot("epg-quality:" + name)
                summary = quality["data"] if quality else {}
                guides.append({"id": name, "channels": len(payload["channels"]),
                    "programmes": len(payload["programmes"]), "last_success": entry["updated_at"],
                    "country": summary.get("country", "unknown"),
                    "covered_24h": summary.get("full_coverage_channels", {}).get("24h", 0),
                    "unmatched": summary.get("unmatched_canonical_channels", 0),
                    "recognised_services": len(summary.get("matched_canonical_channels", [])),
                    "public_redistribution": False})
        today = linking.build_today(eligible, now, epg_data)
        links = {e["id"]: e for group in today["sports"] for c in group["categories"] for e in c["events"]}
        for event in eligible:
            linked = links.get(event["id"])
            if linked:
                event["broadcast_status"] = linked["broadcast_status"]
                event["broadcast_candidates"] = linked["broadcast_candidates"]
        self.store.save_snapshot("sports", {"schema_version": "0.3", "events": eligible, "sources": sources,
                                            "generated_at": utcnow(), "broadcast_status": "not_verified"})
        self.store.save_snapshot("today", today)
        self.store.save_snapshot("epg", {"schema_version": "0.3", "generated_at": utcnow(), "sources": guides,
                                         "note": "Private source-specific schedules; publication rights not cleared"})

    def test_source(self, kind, name):
        """Probe exactly one provider request; reserve one unit in its quota ledger.

        Never accept a user-supplied URL or echo credential-bearing errors.
        Test results do not replace last-good data or enable publication.
        """
        conf = self.store.config()
        if kind == "sports" and name in providers.SPORTS:
            _, _, key_name, limit = providers.SPORTS[name]
            if key_name and not conf["keys"].get(key_name):
                raise ValueError("Save this provider API key before testing")
            item = self._plan(name, conf, datetime.now(LONDON).date())[0]
            self.store.increment(name, limit)
            try:
                rows = item["decode"](providers.fetch(item["url"], headers=item["headers"], max_bytes=item["max_bytes"]))
                self.store.job(name, "test_ok", "Connection valid; %d event records (coverage not guaranteed)" % len(rows))
                return "%s connection successful (%d events returned; coverage not guaranteed)" % (name, len(rows))
            except SAFE_ERRORS as exc:
                self.store.job(name, "test_failed", type(exc).__name__ + ": source unavailable or invalid")
                return "%s test unsuccessful; see Diagnostics" % name
        if kind == "epg" and name in providers.EPG:
            _, url = providers.EPG[name]
            max_bytes, max_programmes = providers.EPG_LIMITS.get(name, providers.DEFAULT_EPG_LIMIT)
            self.store.increment("epg:" + name, 4)
            try:
                guide = providers.decode_xmltv(providers.fetch(url, max_bytes=max_bytes), name, max_programmes=max_programmes)
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
            local = datetime.now(LONDON)
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
        events = [{k: v for k, v in x.items() if k not in PRIVATE_FIELDS}
                  for x in snap["data"]["events"] if x["source_id"] in allowed]
        if not events:
            raise ValueError("No rights-approved events to publish")
        owner, repository, branch, token = (target.get(n, "") for n in ("owner", "repository", "branch", "token"))
        if not owner or not repository or not branch or not token:
            raise ValueError("GitHub destination/token incomplete")
        if not all(v.replace("-", "").replace("_", "").isalnum() for v in [owner, repository, branch]):
            raise ValueError("Invalid GitHub repository address")
        payload = json.dumps({"schema_version": "0.3", "generated_at": utcnow(), "events": events}, separators=(",", ":"), ensure_ascii=False).encode()
        revision = hashlib.sha256(payload).hexdigest()[:20]
        asset = "data/revisions/%s/events.json" % revision
        self._github_write(owner, repository, branch, token, asset, payload)
        manifest = {"schema_version": "0.3", "revision": revision, "generated_at": utcnow(), "assets": [{"kind": "sports", "path": asset, "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}], "epg": "not_published_pending_rights"}
        self._github_write(owner, repository, branch, token, "data/manifest.json", json.dumps(manifest, separators=(",", ":")).encode())
        self.store.job("publisher", "submitted", "Sports snapshot committed; verify published static endpoint separately")
        return revision

    @staticmethod
    def _github_write(owner, repository, branch, token, path, data):
        endpoint = "https://api.github.com/repos/%s/%s/contents/%s" % (owner, repository, path)
        def request(method, body=None):
            req = urllib.request.Request(endpoint + "?ref=" + urllib.parse.quote(branch), method=method,
                 headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json", "User-Agent": "SportsLiveInfo/0.3", "Content-Type": "application/json"}, data=body)
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
