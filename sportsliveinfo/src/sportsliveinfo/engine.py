"""Independent collector lanes with last-good snapshots, quotas and private defaults."""
import base64
import json
import logging
import os
import re
import shutil
import threading
import time
import zlib
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path
from zoneinfo import ZoneInfo

from . import dictionary, feed, identity, linking, providers, taxonomy
from .storage import utcnow
from .guide import analyze_guide

LOGGER = logging.getLogger(__name__)
COLLECTION_SCOPES = {"both": "Sports and EPG", "sports": "Sports", "epg": "EPG"}
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


def _github_failure(step, exc):
    """Actionable, credential-free description of a GitHub API rejection."""
    detail = ""
    try:
        payload = json.loads(exc.read(4000) or b"{}")
        detail = re.sub(r"[^\w .,:;'()/-]", "", str(payload.get("message", "")))[:120].strip()
    except Exception:
        pass
    hint = {
        401: "the token was rejected; check or regenerate it",
        403: "the token cannot write here; edit it to grant Contents: Read and write on the feed repository",
        404: "the token cannot see or write the feed repository; check its repository selection and Contents: Read and write",
        422: "GitHub refused the change",
    }.get(exc.code, "unexpected GitHub response")
    return "GitHub HTTP %d while %s: %s%s" % (exc.code, step, hint, (" (GitHub: %s)" % detail) if detail else "")


class QuotaExhausted(RuntimeError):
    pass


def _sports_failure(exc):
    if isinstance(exc, providers.ProviderRejected):
        return str(exc)
    if isinstance(exc, providers.UpstreamHTTPError):
        return {401: "HTTP 401: check the saved key", 403: "HTTP 403: check key access or plan",
                429: "HTTP 429: provider rate limit"}.get(exc.status, f"Upstream HTTP {exc.status}")
    match = re.fullmatch(r"HTTP ([1-5][0-9]{2}) from upstream", str(exc))
    if match:
        return f"Upstream HTTP {match[1]}"
    if str(exc) == "Upstream network request failed" or isinstance(exc, TimeoutError):
        return "Upstream connection failed or timed out"
    return "Invalid or unsupported provider response"


def _retry_time(exc, now):
    value = getattr(exc, "retry_after", None)
    if value:
        try:
            return now + timedelta(seconds=max(10, int(value)))
        except (ValueError, OverflowError):
            try:
                return max(now + timedelta(seconds=10), parsedate_to_datetime(value).astimezone(timezone.utc))
            except (ValueError, TypeError, OverflowError):
                pass
    return now + timedelta(minutes=30)


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
    specific = {
        "Cross-origin provider redirect blocked": "Cross-origin provider redirect blocked",
        "Source URL is not on the approved HTTPS provider list":
            "Source URL is not on the approved HTTPS provider list",
        "XMLTV declarations and entities are not allowed":
            "Guide contains a DTD declaration or entity that the importer blocks for safety",
        "Not an XMLTV programme guide": "Download is not an XMLTV guide (wrong root element)",
        "Empty XMLTV input": "Guide download was empty",
    }
    if detail in specific:
        return specific[detail]
    if isinstance(exc, ET.ParseError):
        return "Guide is not well-formed XML (parse error)"
    if isinstance(exc, EOFError):
        return "Guide download was truncated (incomplete gzip)"
    if isinstance(exc, ValueError):
        return "Guide was empty, invalid or blocked by source safety checks"
    return "Guide request or import failed"


_GH_OWNER = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")
_GH_REPO = re.compile(r"[A-Za-z0-9._-]{1,100}")
_GH_BRANCH = re.compile(r"[A-Za-z0-9._/-]{1,100}")


def validate_github_target(owner, repository, branch):
    """One validator for save, test and publish (GitHub owner/repo/ref naming rules)."""
    ok = (isinstance(owner, str) and _GH_OWNER.fullmatch(owner) and not owner.endswith("-")
          and isinstance(repository, str) and _GH_REPO.fullmatch(repository) and repository not in (".", "..")
          and isinstance(branch, str) and _GH_BRANCH.fullmatch(branch) and ".." not in branch
          and not branch.startswith(("-", "/", ".")) and not branch.endswith(("/", ".", ".lock")) and "//" not in branch)
    if not ok:
        raise ValueError("Invalid GitHub owner, repository or branch")
    return owner, repository, branch


class Engine:
    def __init__(self, store):
        self.store = store
        self._busy = threading.Lock()
        self._scheduler_stop = threading.Event()
        self._last_call = {}
        self._pace_lock = threading.Lock()
        self._publish_lock = threading.Lock()
        self._publish_start = threading.Lock()
        self._publish_thread = None
        self._publish_outcome = None
        # A publication cannot survive an app restart; never leave "running" shown forever.
        status = store._get("publish_status")
        if isinstance(status, dict) and status.get("state") == "running":
            store._put("publish_status", dict(status, state="failed", message="Interrupted by an app restart; publish again"))

    def collect(self):
        if not self._busy.acquire(blocking=False):
            return False
        try:
            return self._collect_locked()
        finally:
            self._busy.release()

    def _collect_locked(self, scope="both", *, scheduled=False):
        try:
            return self._collect_run(scope, scheduled=scheduled)
        except Exception as exc:  # never leave the last collector job reading "started"
            LOGGER.exception("Collection failed")
            self.store.job("collector", "failed", "Unexpected %s; last-good retained" % type(exc).__name__)
            return False

    def _collect_run(self, scope, *, scheduled=False):
        conf = self.store.config()
        if not conf["setup_complete"]:
            self.store.job("collector", "skipped", "Setup not completed")
            return False
        label = COLLECTION_SCOPES[scope]
        self.store.job("collector", "started", label)
        sports = [n for n, on in conf["sports"].items() if on and n in providers.SPORTS]
        guides = [n for n, on in conf["epg"].items() if on and n in providers.EPG]
        if scope == "sports":
            guides = []
        elif scope == "epg":
            sports = []
        # Each sports provider is its own lane; EPG guides share one sequential
        # lane so several large XMLTV parses never run at once on the mini PC.
        successes = 0
        deferrals = 0
        with ThreadPoolExecutor(max_workers=max(1, min(6, len(sports) + 1)), thread_name_prefix="sli-lane") as pool:
            futures = [pool.submit(self._collect_sport, name, conf) for name in sports]
            epg_future = None
            if guides:
                collect_epg = partial(self._collect_epg, scheduled=True) if scheduled else self._collect_epg
                epg_future = pool.submit(lambda: [collect_epg(name) for name in guides])
                futures.append(epg_future)
            guides_refreshed = 0
            for future in futures:
                try:
                    result = future.result()
                    if future is epg_future:
                        guides_refreshed = sum(item is True for item in result)
                    results = result if isinstance(result, list) else [result]
                    successes += sum(bool(item) for item in results)
                    deferrals += sum(item is None for item in results)
                except Exception as exc:  # A crashed lane must not mask missing data.
                    LOGGER.error("Collector lane failed (%s)", type(exc).__name__)
                    self.store.job("collector", "lane_error", type(exc).__name__)
        if scope in ("both", "epg") and conf.get("dictionary", {}).get("iptvorg"):
            self._refresh_dictionary()
        if guides_refreshed:
            # Only when at least one guide changed; an all-failed run keeps the previous identity graph.
            self._refresh_identity([n for n, on in conf["epg"].items() if on and n in providers.EPG])
        attempted = len(sports) + len(guides)
        if attempted and deferrals == attempted:
            self.store.job("collector", "deferred", f"{label}: all {attempted} sources deferred; last-good retained")
            return False
        if not successes:
            state = "failed" if attempted else "no_sources"
            self.store.job("collector", state, "%s: %d of %d enabled sources refreshed; last-good retained" %
                           (label, successes, attempted))
            return False
        try:
            self._materialize()
        except Exception as exc:
            LOGGER.error("Combined snapshot update failed (%s)", type(exc).__name__)
            self.store.job("collector", "failed", "Combined snapshot update failed; previous dashboard retained")
            return False
        state = "finished" if successes == attempted else "degraded"
        self.store.job("collector", state, "%s: %d of %d sources refreshed; older last-good retained as needed" %
                       (label, successes, attempted))
        github = conf["github"]
        if (scope == "both" and github.get("enabled") and github.get("auto_publish")
                and conf.get("publication_approvals")):
            self._publish_job("automatic")
        return bool(successes)

    # ---- request planning -------------------------------------------------
    def _days(self, name, previous, today):
        # Full multi-day discovery once per London day (and at most every 20 h);
        # other runs refresh today only. Timed from the last FULL discovery, not
        # from the last snapshot write, which every today-only run also updates.
        try:
            last = datetime.fromisoformat(previous["data"]["full_discovery_at"])
            recent = (datetime.now(timezone.utc) - last < timedelta(hours=20)
                      and last.astimezone(LONDON).date() == today)
        except (ValueError, TypeError, KeyError):
            recent = False
        return [today] if recent else [today + timedelta(days=i) for i in range(DAY_HORIZON.get(name, 1))]

    def _plan(self, name, conf, today, previous=None):
        """Return request dicts: url, headers, max_bytes, decode, scope."""
        _, base, key_name, _ = providers.SPORTS[name]
        key = conf["keys"].get(key_name, "") if key_name else ""
        options = conf.get("options", {})
        plan = []
        if name == "jolpica":
            plan.append(dict(url=base, scope=f"season:{today.year}", decode=providers.f1_events, max_bytes=3_000_000))
            if today.month >= 10:
                root = base.rsplit("/", 1)[0]
                plan.append(dict(url="%s/%d.json" % (root, today.year + 1), scope=f"season:{today.year + 1}",
                                 decode=providers.f1_events, max_bytes=3_000_000))
        elif name == "openf1":
            plan.append(dict(url=base + "?" + urllib.parse.urlencode({"year": today.year}), scope="year:%d" % today.year,
                             decode=providers.openf1_events, max_bytes=3_000_000))
        elif name == "openligadb":
            season = today.year if today.month >= 7 else today.year - 1
            leagues = [l for l in options.get("openligadb_leagues", providers.OPENLIGADB_DEFAULT_LEAGUES) if l in providers.OPENLIGADB_LEAGUES]
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
            chosen = [s for s in options.get("thesportsdb_sports", providers.THESPORTSDB_DEFAULT_SPORTS) if s in providers.THESPORTSDB_SPORTS]
            for day in self._days(name, previous, today):
                for sport in chosen:
                    query = urllib.parse.urlencode({"d": day.isoformat(), "s": sport})
                    plan.append(dict(url=base + "?" + query, scope="%s|%s" % (day.isoformat(), sport),
                                     decode=providers.thesportsdb_events, max_bytes=3_000_000))
        elif name == "bha_racing":
            for year in sorted({today.year, (today + timedelta(days=7)).year}):
                plan.append(dict(url=f"{base}?year={year}", scope=f"season:{year}",
                                 decode=partial(providers.bha_racing_events, year=year), max_bytes=500_000))
        elif name == "openboxing":
            plan.append(dict(url=base, scope="scheduled_bouts", decode=providers.openboxing_events,
                             max_bytes=1_000_000))
        elif name == "pandascore":
            query = urllib.parse.urlencode({"per_page": 100, "sort": "begin_at"})
            plan.append(dict(url=base + "?" + query, scope="upcoming",
                             headers={"Authorization": "Bearer " + key},
                             decode=providers.pandascore_events, max_bytes=3_000_000))
        elif name == "tennis_api":
            headers = {"X-RapidAPI-Key": key, "X-RapidAPI-Host": providers.TENNIS_API_HOST}
            for scope in ("upcoming/atp", "upcoming/wta", "live"):
                plan.append(dict(url=f"{base}/{scope}", headers=headers, scope=scope,
                                 decode=partial(providers.tennis_api_events, live=scope == "live"),
                                 max_bytes=3_000_000))
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
        gap = PACING.get(name) or 0
        with self._pace_lock:  # reserve a slot, then sleep without blocking other lanes
            now = time.monotonic()
            slot = max(now, self._last_call.get(family, 0) + gap)
            self._last_call[family] = slot
        if slot > now:
            time.sleep(slot - now)

    def _request(self, name, item, limit):
        self._check_sport_backoff(name)
        try:
            self.store.increment(name, limit)
        except RuntimeError as exc:
            raise QuotaExhausted(str(exc)) from None
        self._pace(name)
        raw = self._fetch_sport(name, item, item["url"])
        # API-Sports responses can advertise multiple pages. Collect them
        # completely (within quota), or reject the scope and retain last-good;
        # never pass an incomplete free-plan page off as a full schedule.
        if name.startswith("api_sports"):
            payload = json.loads(raw)
            error = providers.api_sports_error(payload)
            if error:
                raise providers.ProviderRejected(error)
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
                        self._check_sport_backoff(name)
                        try:
                            self.store.increment(name, limit)
                        except RuntimeError as exc:
                            raise QuotaExhausted(str(exc)) from None
                        self._pace(name)
                        separator = "&" if "?" in item["url"] else "?"
                        page_url = item["url"] + separator + urllib.parse.urlencode({"page": page})
                        more = json.loads(self._fetch_sport(name, item, page_url))
                        error = providers.api_sports_error(more)
                        if error:
                            raise providers.ProviderRejected(error)
                        if (not isinstance(more, dict)
                                or not isinstance(more.get("response"), list)
                                or int((more.get("paging") or {}).get("current") or 0) != page
                                or int((more.get("paging") or {}).get("total") or 0) != total):
                            raise ValueError("Incomplete or conflicting provider page")
                        records.extend(more["response"])
                    payload["response"] = records
                    payload["paging"] = {"current": total, "total": total}
                    raw = json.dumps(payload).encode()
        return item["decode"](raw)

    def _check_sport_backoff(self, name):
        retry = self.store._get("sports_backoff:" + name) or ""
        if retry > datetime.now(timezone.utc).isoformat():
            raise QuotaExhausted(f"Provider quota or throttling; retry after {retry}")

    def _defer_sport(self, name, exc):
        retry = _retry_time(exc, datetime.now(timezone.utc))
        self.store._put("sports_backoff:" + name, retry.isoformat())

    def _fetch_sport(self, name, item, url):
        if not name.startswith("api_sports"):
            return providers.fetch(url, item["headers"], max_bytes=item["max_bytes"])
        headers = {}
        raw = providers.fetch(url, item["headers"], max_bytes=item["max_bytes"], response_headers=headers)
        if headers.get("x-ratelimit-requests-remaining") == "0":
            self._defer_sport(name, providers.UpstreamHTTPError(429, headers.get("Retry-After")))
        return raw

    def _collect_sport(self, name, conf):
        _, _, key_name, daily_limit = providers.SPORTS[name]
        if key_name and not conf["keys"].get(key_name):
            self.store.job(name, "needs_key", "Add a provider API key in Sources")
            return False
        today = datetime.now(LONDON).date()
        previous = self.store.snapshot("sports:" + name)
        plan = self._plan(name, conf, today, previous)
        now = datetime.now(timezone.utc)
        previous_data = (previous or {}).get("data", {})
        last_ok = previous_data.get("scope_success_at", {})
        provider_key = "sports_backoff:" + name
        backoff = self.store._get(provider_key) or ""
        if backoff > now.isoformat():
            self.store.job(name, "deferred", f"Provider quota or throttling; retry after {backoff}")
            return None

        planned = {item["scope"] for item in plan}
        cached = set()
        for scope in planned:
            stamp = last_ok.get(scope, "")
            if name in ("openboxing", "bha_racing"):
                interval = timedelta(hours=12)
            elif name == "jolpica":
                interval = timedelta(days=3) if scope == f"season:{today.year + 1}" else timedelta(hours=12)
            elif name.startswith(("api_sports", "thesportsdb")) and scope.split("|")[0] > today.isoformat():
                interval = timedelta(hours=20)
            else:
                continue
            if stamp >= (now - interval).isoformat():
                cached.add(scope)
        scopes, failed, errors = {}, set(), {}
        deferred = False
        for item in plan:
            scope = item["scope"]
            if scope in failed or scope in cached:
                continue
            try:
                rows = self._request(name, item, daily_limit)
                scopes.setdefault(scope, []).extend(dict(r, fetch_scope=scope) for r in rows)
            except QuotaExhausted as exc:
                errors[scope] = (str(exc) if str(exc).startswith("Provider quota")
                                 else "Local daily request budget exhausted")
                scopes.pop(scope, None)
                deferred = True
                break
            except SAFE_ERRORS as exc:
                errors[scope] = _sports_failure(exc)
                failed.add(scope)
                scopes.pop(scope, None)
                if (getattr(exc, "status", None) == 429 or errors[scope] == "Provider quota or rate limit"):
                    self._defer_sport(name, exc)
                    deferred = True
                    break
                if getattr(exc, "status", None) == 401 or errors[scope] == "Provider rejected the API key":
                    break
        succeeded = set(scopes)
        missing = planned - succeeded - cached
        for scope in missing:
            errors.setdefault(scope, "Deferred by request budget" if deferred else "Skipped after provider rejection")
        detail = "; ".join(f"{scope}: {errors[scope]}" for scope in sorted(errors)[:3])
        if len(errors) > 3:
            detail += f"; +{len(errors) - 3} more"
        if not succeeded:
            if not missing and cached:
                self.store.job(name, "unchanged", "Using recently collected schedule")
                return True
            state = "deferred" if deferred and not failed else "failed"
            self.store.job(name, state, detail or "No request scopes configured")
            return None if state == "deferred" else False
        cutoff = datetime.now(timezone.utc) - timedelta(days=2)
        # A 200 OK with a partial free-plan response does NOT prove all other
        # fixtures in that competition/day have disappeared. Keep unexpired
        # old IDs, then allow new records for the same IDs to supersede them.
        # This avoids deleting events when a source omits a competition/page.
        by_id = {}
        for event in (previous["data"]["events"] if previous else []):
            if name == "bha_racing" and event.get("fetch_scope") in succeeded:
                continue
            try:
                if datetime.fromisoformat(event["start_utc"]) < cutoff:
                    continue
                by_id[event["id"]] = event
            except (KeyError, ValueError, TypeError):
                continue
        # Apply the live board after upcoming scopes so reported play wins.
        if name == "tennis_api":
            for event_id, event in list(by_id.items()):
                if event.get("status_normalized") == "live" and "live" in succeeded:
                    # A match leaving the board is no longer confirmed live.
                    by_id[event_id] = dict(event, status_normalized="unknown", live_status_unconfirmed=True)
        for scope in sorted(succeeded, key=lambda scope: scope == "live"):
            for event in scopes[scope]:
                if name == "tennis_api" and event["status_normalized"] == "live":
                    event["live_observed_at"] = utcnow()
                by_id[event["id"]] = event
        events = list(by_id.values())
        full_horizon = len({i["scope"].split("|")[0] for i in plan}) > 1 or not name.startswith(("api_sports", "thesportsdb"))
        previous_full = previous_data.get("full_discovery_at")
        stamp = now.isoformat()
        scope_success = {scope: last_ok[scope] for scope in planned if scope in last_ok}
        scope_success.update({scope: stamp for scope in succeeded})
        result_cap = {"thesportsdb": 3, "pandascore": 100}.get(name)
        possible_truncation = result_cap and any(len(rows) >= result_cap for rows in scopes.values())
        self.store.save_snapshot("sports:" + name, {"events": events, "source_id": name, "complete": "unknown",
                                                    "observed_at": utcnow(), "scopes_ok": sorted(succeeded),
                                                    "scopes_failed": sorted(missing), "scope_errors": errors,
                                                    "scope_success_at": scope_success,
                                                    "full_discovery_at": utcnow() if full_horizon and not missing else previous_full})
        state = "partial" if missing or possible_truncation else ("ok" if events else "no_events_reported")
        summary = f"{len(events)} event records; {len(succeeded)}/{len(planned)} request scopes refreshed"
        if cached:
            summary += f"; {len(cached)} reused"
        if possible_truncation:
            summary += f"; results reached the {result_cap}-row limit and may be incomplete"
        if detail:
            summary += "; " + detail
        self.store.job(name, state, summary)
        return True

    def _reserve_epg(self, name, *, scheduled=False):
        now = datetime.now(timezone.utc)
        midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        daily_limit = providers.EPG_DAILY_REQUEST_LIMIT
        limit = daily_limit
        if not scheduled:
            slots = set(self.store.config()["schedule"])
            local_day = now.astimezone(LONDON).date()
            for day in (local_day, local_day + timedelta(days=1)):
                for slot in slots:
                    instant = datetime.combine(day, datetime.strptime(slot, "%H:%M").time(), LONDON)
                    if now.replace(second=0, microsecond=0) <= instant < midnight:
                        limit -= 1
        provider = "epg:" + name
        if limit > 0:
            try:
                self.store.increment(provider, limit)
                return
            except RuntimeError as exc:
                if str(exc) != "Configured daily call budget exhausted":
                    raise
        if limit < daily_limit and self.store.usage().get(provider, 0) < daily_limit:
            raise QuotaExhausted("Remaining guide requests reserved for scheduled refreshes")
        raise QuotaExhausted("Local daily guide request budget exhausted; resets at 00:00 UTC")

    def _refresh_dictionary(self):
        """Public-domain channel dictionary: at most daily, conditional requests, last good kept on failure."""
        try:
            status = dictionary.refresh(self.store)
            if status != "fresh":
                meta = (self.store.snapshot("channel-dictionary") or {}).get("data", {}).get("meta", {})
                self.store.job("dictionary", "ok", "Channel dictionary %s (%s channels, %s feeds for UK and Europe)" % (
                    status, meta.get("channels", "?"), meta.get("feeds", "?")))
        except Exception as exc:
            LOGGER.warning("Channel dictionary refresh failed (%s)", type(exc).__name__)
            self.store.job("dictionary", "failed", "Channel dictionary not refreshed (%s); previous version kept"
                           % (_guide_failure(exc) if isinstance(exc, (ValueError, RuntimeError, TimeoutError)) else type(exc).__name__))

    def _refresh_identity(self, names):
        """Link channels across stored guides by schedule (private); never breaks a collection."""
        try:
            document, report = identity.build_from_store(self.store, names)
            self.store.save_snapshot("channel-identity", {"document": document, "report": report})
            stats = report["stats"]
            self.store.job("identity", "ok", "%d services linked across %d guides (%d guide channels); "
                           "%d timeshifts; %d pairs for owner review" % (
                               stats["clusters"], stats["guides"], stats["linked_channels"],
                               stats["timeshifts"], stats["suggestions"]))
        except Exception as exc:
            LOGGER.exception("Channel identity refresh failed")
            self.store.job("identity", "failed", "Channel identity not refreshed (%s); previous result kept"
                           % type(exc).__name__)

    def _collect_epg(self, name, *, scheduled=False):
        _, url = providers.EPG[name]
        max_bytes, max_programmes = providers.EPG_LIMITS.get(name, providers.DEFAULT_EPG_LIMIT)
        try:
            self._reserve_epg(name, scheduled=scheduled)
            cached = self.store.read_snapshots(products=("epg-quality:" + name,),
                                               timestamps_only=("epg:" + name,))
            guide_snapshot = cached.get("epg:" + name)
            quality_snapshot = cached.get("epg-quality:" + name)
            quality_data = quality_snapshot["data"] if quality_snapshot else {}
            validators = quality_data.get("http_validators", {})
            # Revalidate only when the saved guide still covers upcoming programmes.
            headers = {}
            if guide_snapshot and quality_snapshot and guide_snapshot["updated_at"] == quality_snapshot["updated_at"]:
                fresh_until = quality_data.get("http_revalidate_until", "")
                if fresh_until > utcnow() and validators.get("url") == url:
                    headers = {key: validators[field] for key, field in
                               (("If-None-Match", "ETag"), ("If-Modified-Since", "Last-Modified"))
                               if validators.get(field)}
            response_headers = {}
            raw = providers.fetch(url, headers, max_bytes=max_bytes, response_headers=response_headers)
            if raw is None:
                self.store.job(name, "unchanged", "Guide unchanged upstream; retained the saved programmes")
                return True
            parsed = providers.decode_xmltv(raw, name, max_programmes=max_programmes)
            if not parsed["programmes"]:
                self.store.job(name, "empty", "Guide contains no valid programme rows; retaining old data")
                return False
            # Enrichment/coverage report is local only and non-destructive;
            # no guessed EPG ID is ever exposed as an IPTV playable stream.
            now = datetime.now(timezone.utc)
            next_day = now + timedelta(days=1)
            upcoming_until = max(
                (datetime.fromisoformat(p["end_utc"]) for p in parsed["programmes"]
                 if datetime.fromisoformat(p["start_utc"]) < next_day), default=now)
            # A guide with no programme in the next 24h is not a successful forward update.
            if upcoming_until <= now:
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
            quality = analyze_guide(parsed, now)
            if response_headers:
                quality["http_validators"] = {"url": url, **response_headers}
                # Force a complete validation after 24 hours even if a publisher keeps stale validators.
                quality["http_revalidate_until"] = min(next_day, upcoming_until).isoformat(timespec="seconds")
            self.store.save_snapshots({"epg:" + name: parsed, "epg-quality:" + name: quality})
            self.store.job(name, "ok", "%d channels; %d programmes; %d invalid; %d with 24h guide; %d recognised services" % (
                len(parsed["channels"]), len(parsed["programmes"]), parsed["invalid_programmes"],
                quality["full_coverage_channels"]["24h"], len(quality["matched_canonical_channels"])))
            return True
        except QuotaExhausted as exc:
            self.store.job(name, "deferred", str(exc))
            return None
        except (ValueError, RuntimeError, TimeoutError, OSError, EOFError, json.JSONDecodeError, ET.ParseError, zlib.error) as exc:
            reason = _guide_failure(exc)
            self.store.job(name, "failed", reason)
            LOGGER.warning("EPG source %s failed: %s", name, reason)
            return False

    @staticmethod
    def _measure_source_contribution(events, sports, guides):
        sports_by_id = {row["id"]: row for row in sports}
        guides_by_id = {row["id"]: row for row in guides}
        for row in sports:
            row.update(window_fixtures=0, exclusive_fixtures=0)
        for row in guides:
            row.update(window_matches=0, exclusive_matches=0)
        for event in events:
            contributors = event["sources"]
            for name in contributors:
                if name in sports_by_id:
                    sports_by_id[name]["window_fixtures"] += 1
                    sports_by_id[name]["exclusive_fixtures"] += int(len(contributors) == 1)
            for candidate in event["broadcast_candidates"]:
                guide_ids = candidate["epg_sources"]
                for name in guide_ids:
                    guides_by_id[name]["window_matches"] += 1
                    guides_by_id[name]["exclusive_matches"] += int(len(guide_ids) == 1)

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
        guides = []
        match_guides = any(event.get("start_precision") not in linking.UNCONFIRMED_START_PRECISIONS
                           and event.get("status_normalized") not in ("postponed", "cancelled") for event in eligible)
        guide_sources = self._guide_sources(conf, guides, match_guides)
        if not match_guides:
            for _ in guide_sources:
                pass
        gaps = {}
        dictionary_snapshot = self.store.snapshot("channel-dictionary") or {}
        identity_snapshot = self.store.snapshot("channel-identity") or {}
        dictionary_document = (dictionary_snapshot.get("data") or {}).get("document")
        identity_document = (identity_snapshot.get("data") or {}).get("document")
        links = linking.broadcast_candidates(eligible, guide_sources, now, gaps=gaps,
                                             dictionary_document=dictionary_document,
                                             identity_document=identity_document)
        for event in eligible:
            status, candidates = links.get(event["id"], ("none", []))
            event["broadcast_status"] = status
            event["broadcast_candidates"] = candidates
            if event["id"] in gaps:
                event["broadcast_gap"] = gaps[event["id"]]
        self._measure_source_contribution(eligible, sources, guides)
        today = linking.build_today(eligible, now, use_saved_candidates=True)
        generated_at = now.isoformat(timespec="seconds")
        self.store.save_snapshots({
            "sports": {"schema_version": "0.3", "events": eligible, "sources": sources,
                       "generated_at": generated_at, "broadcast_status": "not_verified"},
            "today": today,
            "epg": {"schema_version": "0.3", "generated_at": generated_at, "sources": guides,
                    "note": "Private source-specific schedules; publication rights not cleared"},
        })

    def _guide_sources(self, conf, summaries, include_programmes):
        """Load one saved guide at a time and retain only coverage summaries."""
        for name, enabled in conf["epg"].items():
            if not enabled:
                continue
            snapshots = self.store.read_snapshots(
                products=("epg-quality:" + name,), timestamps_only=("epg:" + name,))
            entry = snapshots.get("epg:" + name)
            if not entry:
                continue
            quality = snapshots.get("epg-quality:" + name)
            summary = quality["data"] if quality else {}
            if (quality is None or quality["updated_at"] != entry["updated_at"]
                    or "channels" not in summary or "valid_programmes" not in summary):
                entry = self.store.snapshot("epg:" + name)
                payload = entry["data"]
                channels, programmes = len(payload["channels"]), len(payload["programmes"])
            else:
                payload = None
                channels, programmes = summary["channels"], summary["valid_programmes"]
            summaries.append({"id": name, "channels": channels, "programmes": programmes,
                "last_success": entry["updated_at"], "country": summary.get("country", "unknown"),
                "covered_24h": summary.get("full_coverage_channels", {}).get("24h", 0),
                "horizon_hours": summary.get("horizon_hours"),
                "unmatched": summary.get("unmatched_canonical_channels", 0),
                "recognised_services": len(summary.get("matched_canonical_channels", [])),
                "public_redistribution": False})
            if include_programmes:
                yield name, payload if payload is not None else self.store.snapshot("epg:" + name)["data"]

    def test_source(self, kind, name):
        """Probe the configured connection and reserve quota for each request.

        Never accept a user-supplied URL or echo credential-bearing errors.
        Test results do not replace last-good data or enable publication.
        """
        conf = self.store.config()
        if kind == "sports" and name in providers.SPORTS:
            _, _, key_name, limit = providers.SPORTS[name]
            if key_name and not conf["keys"].get(key_name):
                raise ValueError("Save this provider API key before testing")
            plan = self._plan(name, conf, datetime.now(LONDON).date())
            if not plan:
                raise ValueError("Select at least one provider option before testing")
            items = plan if name == "tennis_api" else plan[:1]
            outcomes = []
            successes = 0
            for item in items:
                try:
                    self._check_sport_backoff(name)
                    self.store.increment(name, limit)
                    self._pace(name)
                    raw = self._fetch_sport(name, item, item["url"])
                    if name.startswith("api_sports"):
                        error = providers.api_sports_error(json.loads(raw))
                        if error:
                            raise providers.ProviderRejected(error)
                    rows = item["decode"](raw)
                    successes += 1
                    result = f"successful ({len(rows)} events)"
                except QuotaExhausted as exc:
                    result = str(exc)
                except SAFE_ERRORS as exc:
                    result = ("local request budget exhausted" if str(exc) == "Configured daily call budget exhausted"
                              else _sports_failure(exc))
                    if getattr(exc, "status", None) == 429 or result == "Provider quota or rate limit":
                        self._defer_sport(name, exc)
                outcomes.append(f'{item["scope"]}: {result}')
            status = "test_ok" if successes == len(items) else "test_partial" if successes else "test_failed"
            detail = "; ".join(outcomes)
            self.store.job(name, status, detail)
            if len(items) == 1 and successes:
                return "%s connection successful (%d events returned; coverage not guaranteed)" % (name, len(rows))
            return f"{name} connection test: {detail}"
        if kind == "epg" and name in providers.EPG:
            _, url = providers.EPG[name]
            max_bytes, max_programmes = providers.EPG_LIMITS.get(name, providers.DEFAULT_EPG_LIMIT)
            try:
                self._reserve_epg(name)
                guide = providers.decode_xmltv(providers.fetch(url, max_bytes=max_bytes), name, max_programmes=max_programmes)
                if not guide["programmes"]:
                    raise ValueError("Empty EPG programme list")
                now = datetime.now(timezone.utc)
                until = now + timedelta(days=1)
                if not any(datetime.fromisoformat(row["end_utc"]) > now
                           and datetime.fromisoformat(row["start_utc"]) < until for row in guide["programmes"]):
                    self.store.job(name, "test_failed", "No guide programmes cover the next 24 hours")
                    return "%s EPG test unsuccessful; no programmes in the next 24 hours" % name
                self.store.job(name, "test_ok", "EPG parsed, %d programme records (no stored changes)" % len(guide["programmes"]))
                return "%s EPG connection successful (%d programmes)" % (name, len(guide["programmes"]))
            except QuotaExhausted as exc:
                self.store.job(name, "test_deferred", str(exc))
                return f"{name} EPG test deferred: {exc}"
            except (ValueError, RuntimeError, TimeoutError, OSError, EOFError, ET.ParseError, zlib.error) as exc:
                self.store.job(name, "test_failed", _guide_failure(exc))
                return "%s EPG test unsuccessful; see Diagnostics" % name
        raise ValueError("Unknown provider")

    def start_collection(self, scope="both", *, scheduled=False):
        if scope not in COLLECTION_SCOPES:
            raise ValueError("Unknown refresh scope")
        # Reserve the job slot before threading: multiple UI presses must not
        # incorrectly report that additional refreshes have been scheduled.
        if not self._busy.acquire(blocking=False):
            return False
        def worker():
            try:
                self._collect_locked(scope, scheduled=scheduled)
            finally:
                self._busy.release()
        thread = threading.Thread(target=worker, name="sportsliveinfo-collect", daemon=True)
        try:
            thread.start()
        except RuntimeError:
            self._busy.release()
            raise
        return True

    def run_scheduler(self):
        """Run from a daemon thread. DST-aware and no catch-up request storm."""
        failures = 0
        while not self._scheduler_stop.wait(10):
            try:
                self._scheduler_tick()
                failures = 0
            except Exception as exc:  # a locked/full database must not kill scheduling for good
                failures += 1
                LOGGER.exception("Scheduler tick failed")
                if failures in (1, 10, 100):
                    try:
                        self.store.job("scheduler", "error", "%s (repeat %d); scheduler still running" % (type(exc).__name__, failures))
                    except Exception:
                        pass

    def _scheduler_tick(self):
        self.store._put("scheduler_heartbeat", utcnow())
        conf = self.store.config()
        if not conf["setup_complete"]:
            return
        local = datetime.now(LONDON)
        key = local.strftime("%Y-%m-%d %H:%M")
        if local.strftime("%H:%M") in conf.get("schedule", []):
            if self.store.claim_scheduler_slot(key):
                if not self.start_collection(scheduled=True):
                    # Worker already running: allow a retry within this minute.
                    self.store.release_scheduler_slot(key)

    def preview_feed(self, out_dir=None):
        """Build the full sli/1 feed locally (no upload) for inspection and B1G testing."""
        if not self._publish_lock.acquire(timeout=60):
            raise RuntimeError("A feed preview or publication is already running")
        try:
            return self._preview_feed(out_dir)
        except OSError as exc:
            raise RuntimeError("Could not write the feed preview (%s)" % type(exc).__name__) from None
        finally:
            self._publish_lock.release()

    def _preview_feed(self, out_dir=None):
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
        try:
            validate_github_target(owner, repository, branch)
        except ValueError:
            raise ValueError("Save a valid GitHub owner, repository and branch first") from None
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
        # Write probe: an unreferenced blob proves Contents:write without adding
        # a commit or a file to any branch (GitHub garbage-collects it). Read-only
        # tokens previously passed this test and then failed only at publication.
        try:
            probe = urllib.request.Request(
                url + "/git/blobs", method="POST",
                data=json.dumps({"content": "SportsLiveInfo write-access check", "encoding": "utf-8"}).encode(),
                headers=dict(headers, **{"Content-Type": "application/json"}))
            with _github_open(probe, timeout=12) as response:
                if not json.loads(response.read(64_000)).get("sha"):
                    raise ValueError("GitHub returned an unexpected response to the write check")
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 404):
                raise ValueError("The token can read %s/%s but cannot write to it (HTTP %d). On GitHub edit the token: "
                                 "Repository access must include %s, and Repository permissions > Contents must be "
                                 "Read and write. Then save the new token here." % (owner, repository, exc.code, repository)) from None
            if exc.code == 401:
                raise ValueError("GitHub rejected the saved token (401); check or regenerate it") from None
            raise ValueError("GitHub write check returned HTTP %d" % exc.code) from None
        except (TimeoutError, urllib.error.URLError, OSError):
            raise ValueError("Could not reach GitHub for the write check; try again") from None
        except (TypeError, AttributeError, json.JSONDecodeError):
            raise ValueError("GitHub returned an unexpected response to the write check") from None
        return ("GitHub token authenticated, public feed branch readable and write access confirmed "
                "(no commit or file was created). Publishing still requires approved sources.")

    def start_publish(self):
        """Start a manual publication in the background; False if one is already running.

        Publishing takes tens of seconds (feed build plus a dozen GitHub API
        calls). Running it inside the Ingress request left the browser waiting
        with no feedback, invited repeated clicks, and lost the failure reason
        when the browser gave up before the redirect.
        """
        with self._publish_start:
            if self._publish_thread is not None and self._publish_thread.is_alive():
                return False
            self._set_publish_status("running", "Publication in progress", "manual")
            thread = threading.Thread(target=self._publish_job, args=("manual",),
                                      name="sportsliveinfo-publish", daemon=True)
            self._publish_thread = thread
            try:
                thread.start()
            except RuntimeError:
                self._publish_thread = None
                self._set_publish_status("failed", "Could not start the publisher thread", "manual")
                raise
        return True

    def publishing_active(self):
        thread = self._publish_thread
        return thread is not None and thread.is_alive()

    def _set_publish_status(self, state, message, trigger):
        self.store._put("publish_status", {"state": state, "message": str(message)[:300],
                                           "trigger": trigger, "at": utcnow()})

    def _publish_job(self, trigger):
        """Run one publication and always record its outcome (Diagnostics, Publishing page, App log)."""
        LOGGER.info("Feed publication started (%s)", trigger)
        self._set_publish_status("running", "Publication in progress", trigger)
        try:
            revision = self.publish()
        except (ValueError, RuntimeError, OSError) as exc:
            message = str(exc)[:300]
            LOGGER.warning("Feed publication failed (%s): %s", trigger, message)
            self.store.job("publisher", "failed", message)
            self._set_publish_status("failed", message, trigger)
            return None
        except Exception as exc:
            LOGGER.exception("Feed publication failed (%s)", trigger)
            message = "Unexpected %s; see the App log" % type(exc).__name__
            self.store.job("publisher", "failed", message)
            self._set_publish_status("failed", message, trigger)
            return None
        if self._publish_outcome == "unchanged":
            message = "Feed %s is already live and unchanged; nothing to commit" % revision
        else:
            message = "Feed %s committed to GitHub" % revision
        LOGGER.info("Feed publication finished (%s): %s", trigger, message)
        self._set_publish_status("succeeded", message, trigger)
        return revision

    def publish(self):
        """Publish the sli/1 feed in ONE atomic commit; EPG programme text is never copied.

        Disabled by default. Events appear only for sources whose public
        redistribution licence has been explicitly approved.
        """
        if not self._publish_lock.acquire(timeout=120):
            raise RuntimeError("Another feed publication is already running")
        try:
            return self._publish()
        finally:
            self._publish_lock.release()

    def _publish(self):
        conf = self.store.config()
        target = conf["github"]
        self._publish_outcome = None
        if not conf["setup_complete"]:
            raise ValueError("Finish first-run setup (Sources page) before publishing")
        if not target.get("enabled"):
            raise ValueError("Tick Enable publishing and save the GitHub settings first")
        # No approval is supplied by default; the app cannot invent redistribution rights.
        if not conf.get("publication_approvals"):
            raise ValueError("No sport source has an approved public redistribution licence")
        if not self.store.snapshot("sports"):
            raise ValueError("No valid sports snapshot yet")
        owner, repository, branch, token = (target.get(n, "") for n in ("owner", "repository", "branch", "token"))
        if not owner or not repository or not branch or not token:
            raise ValueError("GitHub destination/token incomplete")
        validate_github_target(owner, repository, branch)
        state = self.store._get("feed_state") or {"revisions": []}
        manifest, files = feed.build_feed(self.store, previous_revision=state.get("last_revision"))
        revision = manifest["revision"]
        try:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(state.get("published_at") or "")
        except (TypeError, ValueError):
            age = timedelta(days=999)
        # Republish an unchanged revision only to renew the manifest's expiry
        # (48 h) before TVs would wrongly treat a static-but-healthy feed as stale.
        if revision == state.get("last_revision") and age < timedelta(hours=24):
            self.store.job("publisher", "unchanged", "Feed revision %s already published" % revision)
            self._publish_outcome = "unchanged"
            return revision
        state["revisions"] = [h for h in state["revisions"] if h["revision"] != revision]
        live_before = {p for h in state["revisions"] for p in h["assets"]}
        uploads = {p: d for p, d in files.items() if p not in live_before}
        manifest_bytes = feed._json(manifest)
        uploads["%s/manifests/%s.json" % (feed.ROOT, revision)] = manifest_bytes
        uploads["%s/manifest.json" % feed.ROOT] = manifest_bytes
        history = state["revisions"] + [{"revision": revision, "assets": sorted(files)}]
        keep, drop = history[-FEED_RETAIN:], history[:-FEED_RETAIN]
        live_after = {p for h in keep for p in h["assets"]}
        deletions = sorted({p for h in drop for p in h["assets"]} - live_after)
        kept_ids = {h["revision"] for h in keep}
        deletions += ["%s/manifests/%s.json" % (feed.ROOT, h["revision"]) for h in drop if h["revision"] not in kept_ids]
        self._github_commit(owner, repository, branch, token, uploads, deletions,
                            "SportsLiveInfo feed %s (%d events)" % (revision, manifest["coverage"]["events"]),
                            required=files)
        self.store._put("feed_state", {"last_revision": revision, "revisions": keep, "published_at": utcnow()})
        self.store.job("publisher", "submitted", "Feed %s committed atomically (%d new files, %d removed); verify the static endpoint" % (
            revision, len(uploads), len(deletions)))
        self._publish_outcome = "committed"
        return revision

    @staticmethod
    def _github_commit(owner, repository, branch, token, uploads, deletions, message, required=None):
        """Single commit via the Git Data API: readers never see a manifest without its assets.

        The remote tree is the source of truth: any referenced asset missing
        remotely (reset repo, restored HA backup) is uploaded, and only paths that
        actually exist are deleted, so a stale local ledger cannot break publishing.
        """
        base = "https://api.github.com/repos/%s/%s" % (owner, repository)

        def api(method, path, body=None, step="request"):
            req = urllib.request.Request(base + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                         headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                                                  "User-Agent": "SportsLiveInfo/0.3", "Content-Type": "application/json"})
            try:
                with _github_open(req, timeout=30) as res:
                    return json.loads(res.read(20_000_000))
            except urllib.error.HTTPError as exc:
                if method == "PATCH" and exc.code in (409, 422):
                    raise RuntimeError("Feed branch changed during publication; publish again") from None
                raise RuntimeError(_github_failure(step, exc)) from None
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                raise RuntimeError("Could not reach GitHub while %s (%s); publish again" % (step, type(exc).__name__)) from None

        quoted = urllib.parse.quote(branch, safe="")
        try:
            head = api("GET", "/git/ref/heads/" + quoted, step="reading the feed branch")["object"]["sha"]
            base_tree = api("GET", "/git/commits/" + head, step="reading the latest commit")["tree"]["sha"]
            remote = api("GET", "/git/trees/%s?recursive=1" % base_tree, step="reading the repository files")
            existing = None if remote.get("truncated") else {e["path"] for e in remote.get("tree", []) if e.get("type") == "blob"}
        except (KeyError, TypeError) as exc:
            raise RuntimeError("GitHub returned an unexpected repository response") from None
        uploads = dict(uploads)
        if existing is not None:
            for path, data in (required or {}).items():
                if path not in existing:
                    uploads.setdefault(path, data)
            deletions = [path for path in deletions if path in existing and path not in uploads]
        tree = [{"path": path, "mode": "100644", "type": "blob",
                 "sha": api("POST", "/git/blobs", {"content": base64.b64encode(data).decode(), "encoding": "base64"},
                            step="uploading feed files")["sha"]}
                for path, data in sorted(uploads.items())]
        tree += [{"path": path, "mode": "100644", "type": "blob", "sha": None} for path in deletions]
        new_tree = api("POST", "/git/trees", {"base_tree": base_tree, "tree": tree}, step="building the commit tree")["sha"]
        commit = api("POST", "/git/commits", {"message": message, "tree": new_tree, "parents": [head]},
                     step="creating the commit")["sha"]
        api("PATCH", "/git/refs/heads/" + quoted, {"sha": commit, "force": False}, step="moving the feed branch")
        return commit
