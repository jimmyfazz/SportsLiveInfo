"""Independent collector lanes with last-good snapshots, quotas and private defaults."""
import base64
import json
import logging
import os
import re
import shutil
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path
from zoneinfo import ZoneInfo

from . import feed, linking, providers, taxonomy
from .storage import utcnow
from .guide import analyze_guide

LOGGER = logging.getLogger(__name__)
LONDON = ZoneInfo("Europe/London")
# Minimum seconds between calls to one provider (published per-minute limits).
PACING = {"thesportsdb": 2.1, "football_data": 6.5, **{n: 6.1 for n in providers.SPORTS if n.startswith("api_sports")}}
DAY_HORIZON = {**{n: 7 for n in providers.SPORTS if n.startswith("api_sports")}, "thesportsdb": 3}
SAFE_ERRORS = (ValueError, RuntimeError, TimeoutError, OSError, EOFError,
               json.JSONDecodeError, TypeError, KeyError, OverflowError, ET.ParseError)
FEED_RETAIN = 10  # published manifests (and the assets they reference) kept for slow/offline TVs


class _NoGitHubRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward a GitHub publishing token through an HTTP redirect."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Unexpected GitHub API redirect; refusing to forward publishing credentials")


def _github_open(request, timeout=30):
    """Authenticated GitHub API request without following any redirects."""
    return urllib.request.build_opener(_NoGitHubRedirect()).open(request, timeout=timeout)


class QuotaExhausted(RuntimeError):
    pass


def _guide_failure(exc):
    """Translate known failures without storing raw exception text."""
    detail = str(exc)
    http = re.fullmatch(r"HTTP ([1-5][0-9]{2}) from upstream", detail)
    if http:
        return "Upstream returned HTTP " + http[1]
    if detail == "Configured daily call budget exhausted":
        return "Local daily request budget exhausted"
    if detail == "Upstream network request failed" or isinstance(exc, TimeoutError):
        return "Upstream connection failed or timed out"
    if detail in ("Provider response exceeded configured size limit", "XMLTV decompressed past safety limit",
                  "XMLTV channel count exceeded safety limit", "XMLTV programme count exceeded safety limit"):
        return "Guide exceeded an import size or record limit"
    if isinstance(exc, (ValueError, EOFError, ET.ParseError)):
        return "Guide was empty, invalid or blocked by source safety checks"
    return "Guide request or import failed"


class Engine:
    def __init__(self, store):
        self.store = store
        self._busy = threading.Lock()
        self._scheduler_stop = threading.Event()
        self._last_call = {}
        self._pace_lock = threading.Lock()

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
        successes = 0
        with ThreadPoolExecutor(max_workers=max(1, min(6, len(sports) + 1)), thread_name_prefix="sli-lane") as pool:
            futures = [pool.submit(self._collect_sport, name, conf) for name in sports]
            if guides:
                futures.append(pool.submit(lambda: [self._collect_epg(name) for name in guides]))
            for future in futures:
                try:
                    result = future.result()
                    if isinstance(result, list):
                        successes += sum(bool(item) for item in result)
                    else:
                        successes += bool(result)
                except Exception as exc:  # A crashed lane must not mask missing data.
                    LOGGER.error("Collector lane failed (%s)", type(exc).__name__)
                    self.store.job("collector", "lane_error", type(exc).__name__)
        attempted = len(sports) + len(guides)
        if not successes:
            state = "failed" if attempted else "no_sources"
            self.store.job("collector", state, "%d of %d enabled sources refreshed; last-good retained" %
                           (successes, attempted))
            return False
        self._materialize()
        state = "finished" if successes == attempted else "degraded"
        self.store.job("collector", state, "%d of %d sources refreshed; older last-good retained as needed" %
                       (successes, attempted))
        github = conf["github"]
        if github.get("enabled") and github.get("auto_publish") and conf.get("publication_approvals"):
            try:
                self.publish()
            except (ValueError, RuntimeError, OSError) as exc:
                self.store.job("publisher", "failed", str(exc)[:140])
        return bool(successes)

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
        # Protect rate pacing across parallel provider lanes, including those
        # using the same API-Sports key under different product endpoints.
        family = providers.SPORT_FAMILY.get(name, name)
        gap = PACING.get(name)
        with self._pace_lock:
            if gap:
                wait = self._last_call.get(family, 0) + gap - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
            self._last_call[family] = time.monotonic()

    def _request(self, name, item, limit):
        try:
            self.store.increment(name, limit)
        except RuntimeError as exc:
            raise QuotaExhausted(str(exc)) from None
        self._pace(name)
        raw = providers.fetch(item["url"], item["headers"], max_bytes=item["max_bytes"])
        # API-Sports responses can advertise multiple pages. Collect them
        # completely (within quota), or reject the scope and retain last-good;
        # never pass an incomplete free-plan page off as a full schedule.
        if name.startswith("api_sports"):
            payload = json.loads(raw)
            paging = payload.get("paging", {}) if isinstance(payload, dict) else {}
            if isinstance(paging, dict):
                current, total = int(paging.get("current") or 1), int(paging.get("total") or 1)
                if total > 20 or current != 1 or total < 1:
                    raise ValueError("Unsupported or excessive provider pagination")
                if total > 1:
                    records = payload.get("response")
                    if not isinstance(records, list):
                        raise ValueError("Incomplete provider response")
                    records = list(records)
                    for page in range(2, total + 1):
                        try:
                            self.store.increment(name, limit)
                        except RuntimeError as exc:
                            raise QuotaExhausted(str(exc)) from None
                        self._pace(name)
                        separator = "&" if "?" in item["url"] else "?"
                        page_url = item["url"] + separator + urllib.parse.urlencode({"page": page})
                        more = json.loads(providers.fetch(page_url, item["headers"],
                                                           max_bytes=item["max_bytes"]))
                        if (not isinstance(more, dict) or more.get("errors")
                                or not isinstance(more.get("response"), list)
                                or int((more.get("paging") or {}).get("current") or 0) != page
                                or int((more.get("paging") or {}).get("total") or 0) != total):
                            raise ValueError("Incomplete or conflicting provider page")
                        records.extend(more["response"])
                    payload["response"] = records
                    payload["paging"] = {"current": total, "total": total}
                    raw = json.dumps(payload).encode()
        return item["decode"](raw)

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
            return False
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
            return False
        cutoff = datetime.now(timezone.utc) - timedelta(days=2)
        # A 200 OK with a partial free-plan response does NOT prove all other
        # fixtures in that competition/day have disappeared. Keep unexpired
        # old IDs, then allow new records for the same IDs to supersede them.
        # This avoids deleting events when a source omits a competition/page.
        by_id = {}
        for event in (previous["data"]["events"] if previous else []):
            try:
                if datetime.fromisoformat(event["start_utc"]) < cutoff:
                    continue
                by_id[event["id"]] = event
            except (KeyError, ValueError, TypeError):
                continue
        for scope in succeeded:
            for event in scopes[scope]:
                by_id[event["id"]] = event
        events = list(by_id.values())
        # A successful zero-result response might be valid offseason or the
        # limits of free coverage. Never declare zero sport everywhere.
        self.store.save_snapshot("sports:" + name, {"events": events, "source_id": name, "complete": "unknown",
                                                    "observed_at": utcnow(), "scopes_ok": sorted(succeeded),
                                                    "scopes_failed": sorted(failed)})
        state = "partial" if failed else ("ok" if events else "no_events_reported")
        self.store.job(name, state, "%d event records; %d/%d request scopes refreshed (provider coverage not guaranteed)" % (
            len(events), len(succeeded), len(succeeded) + len(failed)))
        return True

    def _collect_epg(self, name):
        _, url = providers.EPG[name]
        max_bytes, max_programmes = providers.EPG_LIMITS.get(name, providers.DEFAULT_EPG_LIMIT)
        try:
            self.store.increment("epg:" + name, 4)
            raw = providers.fetch(url, max_bytes=max_bytes)
            parsed = providers.decode_xmltv(raw, name, max_programmes=max_programmes)
            if not parsed["programmes"]:
                self.store.job(name, "empty", "Guide contains no valid programme rows; retaining old data")
                return False
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
                return False
            # HTTP 200 does not imply a complete guide. Protect against a
            # partial/truncated-but-parseable upstream rebuild.
            previous = self.store.snapshot("epg:" + name)
            if previous:
                until = now + timedelta(days=1)
                def forward_count(rows):
                    count = 0
                    for programme in rows:
                        try:
                            if (datetime.fromisoformat(programme["end_utc"]) > now
                                    and datetime.fromisoformat(programme["start_utc"]) < until):
                                count += 1
                        except (KeyError, ValueError, TypeError, OverflowError):
                            # Ignore corrupt/legacy old entries; never crash
                            # the entire guide refresh during an upgrade.
                            continue
                    return count
                before = forward_count(previous["data"].get("programmes", []))
                after = forward_count(parsed["programmes"])
                if before >= 30 and after * 4 < before:
                    self.store.job(name, "coverage_collapse",
                                   "New guide lost over 75% of forward programme records; keeping last-good")
                    return False
            self.store.save_snapshot("epg:" + name, parsed)
            self.store.save_snapshot("epg-quality:" + name, quality)
            self.store.job(name, "ok", "%d channels; %d programmes; %d invalid; %d with 24h guide; %d recognised services" % (
                len(parsed["channels"]), len(parsed["programmes"]), parsed["invalid_programmes"],
                quality["full_coverage_channels"]["24h"], len(quality["matched_canonical_channels"])))
            return True
        except (ValueError, RuntimeError, TimeoutError, OSError, EOFError, json.JSONDecodeError, ET.ParseError) as exc:
            reason = _guide_failure(exc)
            self.store.job(name, "failed", reason)
            LOGGER.warning("EPG source %s failed: %s", name, reason)
            return False

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
            try:
                self.store.increment("epg:" + name, 4)
                guide = providers.decode_xmltv(providers.fetch(url, max_bytes=max_bytes), name, max_programmes=max_programmes)
                if not guide["programmes"]:
                    raise ValueError("Empty EPG programme list")
                self.store.job(name, "test_ok", "EPG parsed, %d programme records (no stored changes)" % len(guide["programmes"]))
                return "%s EPG connection successful (%d programmes)" % (name, len(guide["programmes"]))
            except (ValueError, RuntimeError, TimeoutError, OSError, EOFError, ET.ParseError) as exc:
                self.store.job(name, "test_failed", _guide_failure(exc))
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
            if local.strftime("%H:%M") in conf.get("schedule", []):
                if self.store.claim_scheduler_slot(key):
                    if not self.start_collection():
                        # Worker already running: allow a retry within this minute.
                        self.store.release_scheduler_slot(key)

    def preview_feed(self, out_dir=None):
        """Build the full sli/1 feed locally (no upload) for inspection and B1G testing."""
        state = self.store._get("feed_state") or {}
        manifest, files = feed.build_feed(self.store, previous_revision=state.get("last_revision"))
        out = Path(out_dir or os.environ.get("SLI_DATA_DIR", "/data")) / "feed-preview"
        staging = out.with_name("feed-preview.tmp")
        shutil.rmtree(staging, ignore_errors=True)
        for path, data in list(files.items()) + [("v1/manifest.json", feed._json(manifest))]:
            target = staging / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        shutil.rmtree(out, ignore_errors=True)
        staging.rename(out)
        summary = {"revision": manifest["revision"], "generated_at": manifest["generated_at"],
                   "assets": len(manifest["assets"]), "bytes": sum(a["bytes"] for a in manifest["assets"]),
                   "coverage": manifest["coverage"], "notices": manifest["notices"]}
        self.store._put("feed_preview", summary)
        self.store.job("publisher", "preview", "Feed %s built locally: %d assets" % (manifest["revision"], len(manifest["assets"])))
        return manifest

    def test_github_destination(self):
        """Read-only check that the saved fine-grained token reaches its target.

        A GET does not prove Contents:write. This intentionally never commits,
        modifies repository settings, or attempts to publish unlicensed data.
        """
        target = self.store.config()["github"]
        owner, repository, branch, token = (target.get(k, "") for k in
                                            ("owner", "repository", "branch", "token"))
        if not token:
            raise ValueError("Save your GitHub token first, then run Test Connection")
        if not all(isinstance(s, str) and s and len(s) <= 80
                   and all(ch.isalnum() or ch in "._-" for ch in s)
                   for s in (owner, repository, branch)):
            raise ValueError("Save a valid GitHub owner, repository and branch first")
        url = "https://api.github.com/repos/%s/%s" % (owner, repository)
        headers = {"Authorization": "Bearer " + token,
                   "Accept": "application/vnd.github+json",
                   "User-Agent": "SportsLiveInfo/0.3"}
        try:
            req = urllib.request.Request(url, headers=headers)
            with _github_open(req, timeout=12) as response:
                info = json.loads(response.read(64_000))
            if info.get("full_name", "").casefold() != (owner + "/" + repository).casefold():
                raise ValueError("GitHub returned a different repository")
            if info.get("private") is not False:
                raise ValueError("The feed destination must be a public repository")
            perms = info.get("permissions")
            if isinstance(perms, dict) and perms.get("push") is False:
                raise ValueError("Token appears to lack repository write permission; select Contents: Read and write")
            ref = urllib.request.Request(
                url + "/git/ref/heads/" + urllib.parse.quote(branch, safe=""),
                headers=headers)
            with _github_open(ref, timeout=12) as response:
                branch_info = json.loads(response.read(64_000))
            if branch_info.get("ref") != "refs/heads/" + branch:
                raise ValueError("GitHub did not confirm the requested feed branch")
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise ValueError("GitHub rejected the saved token (401); check or regenerate it") from None
            if exc.code == 403:
                raise ValueError("GitHub denied access (403); check token repository selection, permissions or expiry") from None
            if exc.code == 404:
                raise ValueError("Feed repository or branch was not found (404); check owner, repository and branch") from None
            raise ValueError("GitHub connection returned HTTP %d" % exc.code) from None
        except (TimeoutError, urllib.error.URLError, OSError):
            raise ValueError("Could not reach GitHub; check internet access and try again") from None
        except (TypeError, KeyError, AttributeError, json.JSONDecodeError):
            raise ValueError("GitHub returned an unexpected response") from None
        return ("GitHub token authenticated and public feed branch readable. "
                "Read-only check passed; Contents:write is proven only by an authorised publication.")

    def publish(self):
        """Publish the sli/1 feed in ONE atomic commit; EPG programme text is never copied.

        Disabled by default. Events appear only for sources whose public
        redistribution licence has been explicitly approved.
        """
        conf = self.store.config()
        target = conf["github"]
        if not conf["setup_complete"] or not target.get("enabled"):
            raise ValueError("Public publishing is disabled")
        # No approval is supplied by default; the app cannot invent redistribution rights.
        if not conf.get("publication_approvals"):
            raise ValueError("No sport source has an approved public redistribution licence")
        if not self.store.snapshot("sports"):
            raise ValueError("No valid sports snapshot yet")
        owner, repository, branch, token = (target.get(n, "") for n in ("owner", "repository", "branch", "token"))
        if not owner or not repository or not branch or not token:
            raise ValueError("GitHub destination/token incomplete")
        if not all(v.replace("-", "").replace("_", "").replace(".", "").isalnum() for v in [owner, repository, branch]):
            raise ValueError("Invalid GitHub repository address")
        state = self.store._get("feed_state") or {"revisions": []}
        manifest, files = feed.build_feed(self.store, previous_revision=state.get("last_revision"))
        revision = manifest["revision"]
        if revision == state.get("last_revision"):
            self.store.job("publisher", "unchanged", "Feed revision %s already published" % revision)
            return revision
        live_before = {p for h in state["revisions"] for p in h["assets"]}
        uploads = {p: d for p, d in files.items() if p not in live_before}
        manifest_bytes = feed._json(manifest)
        uploads["%s/manifests/%s.json" % (feed.ROOT, revision)] = manifest_bytes
        uploads["%s/manifest.json" % feed.ROOT] = manifest_bytes
        history = state["revisions"] + [{"revision": revision, "assets": sorted(files)}]
        keep, drop = history[-FEED_RETAIN:], history[:-FEED_RETAIN]
        live_after = {p for h in keep for p in h["assets"]}
        deletions = sorted({p for h in drop for p in h["assets"]} - live_after)
        deletions += ["%s/manifests/%s.json" % (feed.ROOT, h["revision"]) for h in drop]
        self._github_commit(owner, repository, branch, token, uploads, deletions,
                            "SportsLiveInfo feed %s (%d events)" % (revision, manifest["coverage"]["events"]))
        self.store._put("feed_state", {"last_revision": revision, "revisions": keep, "published_at": utcnow()})
        self.store.job("publisher", "submitted", "Feed %s committed atomically (%d new files, %d removed); verify the static endpoint" % (
            revision, len(uploads), len(deletions)))
        return revision

    @staticmethod
    def _github_commit(owner, repository, branch, token, uploads, deletions, message):
        """Single commit via the Git Data API: readers never see a manifest without its assets."""
        base = "https://api.github.com/repos/%s/%s" % (owner, repository)

        def api(method, path, body=None):
            req = urllib.request.Request(base + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                         headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                                                  "User-Agent": "SportsLiveInfo/0.3", "Content-Type": "application/json"})
            try:
                with _github_open(req, timeout=30) as res:
                    return json.loads(res.read(2_000_000))
            except urllib.error.HTTPError as exc:
                raise RuntimeError("GitHub API rejected %s request (%d)" % (method, exc.code)) from None

        ref = "/git/refs/heads/" + urllib.parse.quote(branch)
        head = api("GET", ref)["object"]["sha"]
        base_tree = api("GET", "/git/commits/" + head)["tree"]["sha"]
        tree = [{"path": path, "mode": "100644", "type": "blob",
                 "sha": api("POST", "/git/blobs", {"content": base64.b64encode(data).decode(), "encoding": "base64"})["sha"]}
                for path, data in sorted(uploads.items())]
        tree += [{"path": path, "mode": "100644", "type": "blob", "sha": None} for path in deletions]
        new_tree = api("POST", "/git/trees", {"base_tree": base_tree, "tree": tree})["sha"]
        commit = api("POST", "/git/commits", {"message": message, "tree": new_tree, "parents": [head]})["sha"]
        api("PATCH", ref, {"sha": commit, "force": False})
        return commit
