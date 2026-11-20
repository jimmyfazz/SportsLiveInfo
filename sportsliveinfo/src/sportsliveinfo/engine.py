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
from datetime import date, datetime, timedelta, timezone
from functools import partial
from pathlib import Path
from zoneinfo import ZoneInfo

from . import coverage, dictionary, feed, identity, linking, providers, taxonomy
from .storage import utcnow
from .guide import analyze_guide

LOGGER = logging.getLogger(__name__)
COLLECTION_SCOPES = {"both": "Sports and EPG", "sports": "Sports", "epg": "EPG"}
LONDON = ZoneInfo("Europe/London")
# Minimum seconds between calls to one provider (published per-minute limits).
PACING = {"thesportsdb": 2.1, "football_data": 6.5, **{n: 6.1 for n in providers.SPORTS if n.startswith("api_sports")}}
# TheSportsDB: whole-sport day requests cover today only (the free key returns 3 events per request, so later days
# added little); the week ahead comes from per-competition requests (providers.THESPORTSDB_LEAGUES).
DAY_HORIZON = {**{n: 7 for n in providers.SPORTS if n.startswith("api_sports")}, "thesportsdb": 1}
SAFE_ERRORS = (ValueError, RuntimeError, TimeoutError, OSError, EOFError,
               json.JSONDecodeError, TypeError, KeyError, OverflowError, ET.ParseError)
FEED_RETAIN = 10  # published manifests (and the assets they reference) kept for slow/offline TVs
# Light live-status lane (contract sli/1.6 §2). API-Sports "live=all" boards, only while the collected feed has an
# event between its start and expected end, at most every 15 minutes, within a daily budget per product that also
# counts against the product's own daily quota (and always leaves calls for the scheduled refreshes).
LIVE_INTERVAL = timedelta(minutes=15)
LIVE_DAILY_BUDGET = 40          # live calls per product per UTC day
LIVE_RESERVE = 20               # product calls kept back for the scheduled refreshes
LIVE_REFRESH = timedelta(minutes=30)   # re-confirm an unchanged "live" this often, so readers keep trusting it
LIVE_RETAIN = timedelta(hours=36)
LIVE_SLOT_GUARD = 3             # minutes either side of a scheduled refresh when the lane stays quiet
LIVE_UNSUPPORTED_DAYS = 3       # a product that refuses live=all is not asked again for this long
# Football uses fixtures?live=all; the v1 "games" products games?live=all. The MMA API has no live board.
# Pre-publish regression gate: automatic publication is refused when the new feed has more than this share fewer
# events, or fewer guide-corroborated bindings, than the one last published (manual publish overrides). Baselines
# below the minimum are ignored so a tiny feed cannot trip it.
PUBLISH_REGRESSION_THRESHOLD = 0.20
PUBLISH_REGRESSION_MIN_BASELINE = 5


class PublishRegression(RuntimeError):
    """Automatic publication refused: the new feed lost too much against the published one."""


def publish_regression(previous, manifest):
    """Reason string when ``manifest`` regresses against ``previous`` (stored stats), else None."""
    if not isinstance(previous, dict):
        return None
    cover = manifest.get("coverage") or {}
    now = {"events": cover.get("events", 0), "corroborated_bindings": cover.get("guide_corroborated_broadcasts", 0)}
    labels = {"events": "events", "corroborated_bindings": "guide-corroborated bindings"}
    for key, label in labels.items():
        before = previous.get(key)
        if (isinstance(before, int) and before >= PUBLISH_REGRESSION_MIN_BASELINE
                and now[key] < before * (1 - PUBLISH_REGRESSION_THRESHOLD)):
            return "%s fell from %d to %d (more than %d%%)" % (label, before, now[key],
                                                                round(PUBLISH_REGRESSION_THRESHOLD * 100))
    return None


LIVE_PRODUCTS = tuple(name for name in providers.SPORTS if name.startswith("api_sports") and name != "api_sports_mma")
# Settle pass: an event that has left the live board is never "finished" by that alone. Once it is past its expected
# end plus the live grace (and at most SETTLE_WINDOW after), one date=<London start day> call per product per hour reads
# the provider's explicit final status (FT/AET/PEN, PST, CANC ...) while unsettled events exist. Its own daily counter
# "settle:<product>" is also counted in the product's quota and obeys the same reserve as the live lane.
SETTLE_DAILY_BUDGET = 4         # settle calls per product per UTC day
SETTLE_INTERVAL = timedelta(hours=1)
SETTLE_WINDOW = timedelta(hours=12)    # how long after the live grace an unsettled event is still looked up
SETTLE_FINAL = ("finished", "postponed", "cancelled")


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


def parse_github_repository(owner, repository):
    """Accept a repository as a name, "owner/name" or a GitHub link; returns (owner, name).

    Owners naturally paste "https://github.com/owner/name" into the repository field.
    """
    owner, value = str(owner or "").strip(), str(repository or "").strip()
    match = re.match(r"^(?:https?://)?(?:www\.)?github\.com/([^/\s]+)/([^/\s?#]+)", value, re.I)
    if match:
        owner, value = match.group(1), match.group(2)
    elif value.count("/") == 1:
        owner, value = value.split("/")
    value = value.rstrip("/")
    if value.endswith(".git"):
        value = value[:-4]
    return owner.strip(), value.strip()


def validate_github_target(owner, repository, branch):
    """One validator for save, test and publish (GitHub owner/repo/ref naming rules)."""
    ok = (isinstance(owner, str) and _GH_OWNER.fullmatch(owner) and not owner.endswith("-")
          and isinstance(repository, str) and _GH_REPO.fullmatch(repository) and repository not in (".", "..")
          and isinstance(branch, str) and _GH_BRANCH.fullmatch(branch) and ".." not in branch
          and not branch.startswith(("-", "/", ".")) and not branch.endswith(("/", ".", ".lock")) and "//" not in branch)
    if not ok:
        owner_ok = isinstance(owner, str) and bool(_GH_OWNER.fullmatch(owner)) and not owner.endswith("-")
        repo_ok = isinstance(repository, str) and bool(_GH_REPO.fullmatch(repository)) and repository not in (".", "..")
        field = "owner" if not owner_ok else "repository name" if not repo_ok else "branch"
        raise ValueError("Invalid GitHub %s: use e.g. owner jimmyfazz, repository LiveSports-EPG-private, "
                         "branch main (a github.com link in the repository field also works)" % field)
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
        self._test_threads = {}
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
    @staticmethod
    def _full_discovery_recent(previous, today):
        """Whether a full multi-day discovery already ran this London day (and within 20 h). Timed from the last FULL
        discovery, not from the last snapshot write, which every today-only run also updates."""
        try:
            last = datetime.fromisoformat(previous["data"]["full_discovery_at"])
            return (datetime.now(timezone.utc) - last < timedelta(hours=20)
                    and last.astimezone(LONDON).date() == today)
        except (ValueError, TypeError, KeyError):
            return False

    def _days(self, name, previous, today):
        # Full multi-day discovery once per London day (and at most every 20 h); other runs refresh today only.
        recent = self._full_discovery_recent(previous, today)
        days = [today] if recent else [today + timedelta(days=i) for i in range(DAY_HORIZON.get(name, 1))]
        window = self._plan_window(name)
        if window:
            first, last = window
            days = [day for day in days if first <= (day - today).days <= last] or [today]
        return days

    PLAN_WINDOW_RELEARN = timedelta(days=3)

    def _plan_window(self, name):
        """Day offsets (from today) the source's plan allows, as learned from its own refusal, or None.

        Forgotten after PLAN_WINDOW_RELEARN so an upgraded plan is noticed by the next full discovery."""
        stored = self.store._get("plan_window:" + name)
        try:
            learned = datetime.fromisoformat(stored["learned_at"])
            if datetime.now(timezone.utc) - learned > self.PLAN_WINDOW_RELEARN:
                return None
            return int(stored["first"]), int(stored["last"])
        except (TypeError, KeyError, ValueError):
            return None

    def _learn_plan_window(self, name, exc, today):
        first, last = (exc.first - today).days, (exc.last - today).days
        self.store._put("plan_window:" + name, {"first": first, "last": last,
                                                 "learned_at": datetime.now(timezone.utc).isoformat()})
        return first, last

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
            leagues = [l for l in options.get("thesportsdb_leagues", providers.THESPORTSDB_DEFAULT_LEAGUES)
                       if l in providers.THESPORTSDB_LEAGUES]
            for day in self._days(name, previous, today):
                for sport in chosen:
                    query = urllib.parse.urlencode({"d": day.isoformat(), "s": sport})
                    plan.append(dict(url=base + "?" + query, scope="%s|%s" % (day.isoformat(), sport),
                                     decode=providers.thesportsdb_events, max_bytes=3_000_000))
            # The week ahead per competition, once per full discovery (other runs: today only, like the sports).
            recent = self._full_discovery_recent(previous, today)
            league_days = [today] if recent else [today + timedelta(days=i) for i in range(providers.THESPORTSDB_LEAGUE_DAYS)]
            for day in league_days:
                for league in leagues:
                    query = urllib.parse.urlencode({"d": day.isoformat(), "l": league})
                    plan.append(dict(url=base + "?" + query, scope="%s|league:%s" % (day.isoformat(), league),
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
                window = providers.api_sports_plan_window(payload)
                if window:
                    raise providers.PlanWindow(error, *window)
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
        outside = set()     # dates the provider plan does not cover: not failures, not requested again
        window = None
        deferred = False
        for item in plan:
            scope = item["scope"]
            if scope in failed or scope in cached:
                continue
            if window and not window[0] <= (date.fromisoformat(scope.split("|")[0]) - today).days <= window[1]:
                outside.add(scope)
                continue
            try:
                rows = self._request(name, item, daily_limit)
                observed = utcnow()      # contract sli/1.6 §1: when this status was read from the source
                scopes.setdefault(scope, []).extend(dict(r, fetch_scope=scope, status_observed_at=observed)
                                                    for r in rows)
            except QuotaExhausted as exc:
                errors[scope] = (str(exc) if str(exc).startswith("Provider quota")
                                 else "Local daily request budget exhausted")
                scopes.pop(scope, None)
                deferred = True
                break
            except providers.PlanWindow as exc:
                window = self._learn_plan_window(name, exc, today)
                outside.add(scope)
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
        missing = planned - succeeded - cached - outside
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
        if outside:
            summary += f"; {len(outside)} outside the provider plan's dates (not requested again for 3 days)"
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
            switches = self.store.config().get("dictionary", {})
            regions = [key for key in dictionary.REGIONS if switches.get(key)]
            status = dictionary.refresh(self.store, regions=regions)
            if status != "fresh":
                meta = (self.store.snapshot("channel-dictionary") or {}).get("data", {}).get("meta", {})
                scope = " + ".join(["UK and Europe"] + [dictionary.REGIONS[k][0] for k in meta.get("regions", [])])
                self.store.job("dictionary", "ok", "Channel dictionary %s (%s channels, %s feeds for %s)" % (
                    status, meta.get("channels", "?"), meta.get("feeds", "?"), scope))
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
    # Fields that decide which guide programmes match an event: a public (approved-only) merged event equal on all of
    # these to the full-merge event holding its primary record reuses that event's broadcast candidates.
    _MATCH_FIELDS = ("sport", "start_utc", "start_precision", "status_normalized", "participants", "participants_short",
                     "competition", "competition_id", "session", "title", "event_type", "category_id", "end_utc")

    def _apply_live_observations(self, raw):
        """Fold the live-status lane's observations into source records whose own status is older."""
        observations = (self.store._get("live_observations") or {}).get("events") or {}
        if not observations:
            return raw
        out = []
        for event in raw:
            seen = observations.get(event.get("id"))
            if (isinstance(seen, dict) and str(seen.get("status_observed_at") or "")
                    > str(event.get("status_observed_at") or "")):
                event = dict(event, status=seen.get("status", event.get("status")),
                             status_normalized=seen.get("status_normalized"),
                             status_observed_at=seen["status_observed_at"])
                event.pop("live_status_unconfirmed", None)
                # A newer observation replaces the record's score (sli/1.7); one without a score clears it, so a
                # score never outlives the status it was read with. Both stay internal unless scores are enabled.
                if isinstance(seen.get("score"), dict):
                    event["score"] = seen["score"]
                else:
                    event.pop("score", None)
            out.append(event)
        return out

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
                # Records saved before 0.3.23 carry no observation time: the snapshot's own time is the latest it can be.
                fallback = entry["data"].get("observed_at") or entry["updated_at"]
                raw.extend(e if e.get("status_observed_at") else dict(e, status_observed_at=fallback)
                           for e in entry["data"]["events"])
        raw = self._apply_live_observations(raw)
        classified = [taxonomy.classify(e) for e in raw]
        merged = linking.merge_events(classified)
        # Audit 15 Nov (C1): the public feed is a merge of approved-source records only, so an unapproved source that
        # corroborates an approved fixture can no longer remove it. The private feed keeps the full merge.
        approved = sorted(set(conf.get("publication_approvals") or []))
        merged_public = linking.merge_events([e for e in classified if e.get("source_id") in approved]) if approved else []
        # A rolling window prevents stale earlier-season races appearing on a TV's 'today' rail.
        london_today = now.astimezone(LONDON).date()

        def in_window(rows):
            kept = []
            for event in rows:
                try:
                    local_day = datetime.fromisoformat(event["start_utc"]).astimezone(LONDON).date()
                    if london_today <= local_day <= london_today + timedelta(days=7):
                        kept.append(event)
                except (ValueError, KeyError, TypeError):
                    continue
            return kept
        eligible, eligible_public = in_window(merged), in_window(merged_public)
        holder = {sid: event for event in eligible for sid in event.get("source_events") or [event["id"]]}
        reuse, copies = {}, []
        for event in eligible_public:
            full = holder.get(event["id"])
            if full is not None and all(full.get(f) == event.get(f) for f in self._MATCH_FIELDS):
                reuse[event["id"]] = full["id"]
            else:
                copies.append(dict(event, id="public:" + event["id"], _public_copy=True))
        guides = []
        # Guides are always read: besides matching events, live sport they list is kept (see below).
        guide_sources = self._guide_sources(conf, guides, True)
        gaps = {}
        dictionary_snapshot = self.store.snapshot("channel-dictionary") or {}
        identity_snapshot = self.store.snapshot("channel-identity") or {}
        dictionary_document = (dictionary_snapshot.get("data") or {}).get("document")
        identity_document = (identity_snapshot.get("data") or {}).get("document")
        guide_listed, guide_map, service_aliases = [], {}, {}
        # One pass over the guides serves both merges; public copies only when their matching fields differ.
        links = linking.broadcast_candidates(eligible + copies, guide_sources, now, gaps=gaps,
                                             dictionary_document=dictionary_document,
                                             identity_document=identity_document,
                                             guide_events=guide_listed, guide_map=guide_map,
                                             service_aliases=service_aliases)
        for event in eligible:
            status, candidates = links.get(event["id"], ("none", []))
            event["broadcast_status"] = status
            event["broadcast_candidates"] = candidates
            if event["id"] in gaps:
                event["broadcast_gap"] = gaps[event["id"]]
        for event in eligible_public:
            key = reuse.get(event["id"]) or "public:" + event["id"]
            status, candidates = links.get(key, ("none", []))
            event["broadcast_status"] = status
            event["broadcast_candidates"] = [dict(c, epg_sources=list(c.get("epg_sources") or [])) for c in candidates]
            if key in gaps:
                event["broadcast_gap"] = gaps[key]
        # Live sport listed in the guides that no event source has: private, never published.
        for event in guide_listed:
            try:
                local_day = datetime.fromisoformat(event["start_utc"]).astimezone(LONDON).date()
            except (ValueError, KeyError, TypeError):
                continue
            if london_today <= local_day <= london_today + timedelta(days=7):
                eligible.append(taxonomy.classify(event))
        self._measure_source_contribution(eligible, sources, guides)
        today = linking.build_today(eligible, now, use_saved_candidates=True)
        generated_at = now.isoformat(timespec="seconds")
        self.store.save_snapshots({
            "sports": {"schema_version": "0.3", "events": eligible, "sources": sources,
                       "generated_at": generated_at, "broadcast_status": "not_verified"},
            "sports-public": {"schema_version": "0.3", "events": eligible_public, "approved": approved,
                              "generated_at": generated_at},
            "today": today,
            "epg": {"schema_version": "0.3", "generated_at": generated_at, "sources": guides,
                    "note": "Private source-specific schedules; publication rights not cleared"},
            "guide-map": {"generated_at": generated_at, "guides": guide_map,
                          "service_aliases": dict(sorted(service_aliases.items()))},
        })
        # Observations folded into this snapshot are no longer "since the last full feed"; keep only newer ones.
        self._prune_live_observations(now)

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
        self._live_tick(conf, local)

    # ---- live-status lane -------------------------------------------------
    @staticmethod
    def live_lane_enabled(conf):
        """Switchable (config ``live_status``, default on) and only with an API-Sports key and product enabled."""
        return bool(conf.get("live_status", True) and conf["keys"].get("api_sports")
                    and any(conf["sports"].get(name) for name in LIVE_PRODUCTS))

    def _live_tick(self, conf, local):
        if not self.live_lane_enabled(conf):
            return
        state = self.store._get("live_lane") or {}
        try:
            if datetime.now(timezone.utc) - datetime.fromisoformat(state["last_run"]) < LIVE_INTERVAL:
                return
        except (KeyError, TypeError, ValueError):
            pass
        minute = local.hour * 60 + local.minute
        for slot in conf.get("schedule", []):
            gap = abs(minute - (int(slot[:2]) * 60 + int(slot[3:])))
            if min(gap, 1440 - gap) <= LIVE_SLOT_GUARD:
                return                     # leave the scheduled refresh its slot
        if not self._busy.acquire(blocking=False):
            return

        def worker():
            try:
                changed = self.live_lane()
            except Exception:
                LOGGER.exception("Live status lane failed")
                self.store.job("live_status", "failed", "Unexpected error; previous statuses kept")
                changed = 0
            try:
                changed += self.settle_pass()
            except Exception:
                LOGGER.exception("Settle pass failed")
            finally:
                self._busy.release()
            if changed:
                self._publish_live()
        try:
            threading.Thread(target=worker, name="sportsliveinfo-live", daemon=True).start()
        except RuntimeError:
            self._busy.release()

    def _publish_live(self):
        """Publish after a status change, under the same conditions as automatic publication after a collection.
        Content addressing means only the small live asset and the manifests are new files."""
        conf = self.store.config()
        github = conf["github"]
        if github.get("enabled") and github.get("auto_publish") and conf.get("publication_approvals"):
            self._publish_job("live")

    def _live_candidates(self, conf, now, observations):
        """{product: [(event, [source event ids])]} for collected events between start and expected end."""
        snapshot = self.store.snapshot("sports")
        events = ((snapshot or {}).get("data") or {}).get("events") or []
        found = {}
        products = [name for name in LIVE_PRODUCTS if conf["sports"].get(name)]
        for event in events:
            if (event.get("origin") == "guide_listing"
                    or event.get("start_precision") in linking.UNCONFIRMED_START_PRECISIONS):
                continue
            try:
                start, end = datetime.fromisoformat(event["start_utc"]), linking.expected_end(event)
            except (KeyError, TypeError, ValueError):
                continue
            if not start <= now <= end + linking.LIVE_END_GRACE:
                continue
            ids = event.get("source_events") or [event.get("id")]
            seen = [observations[sid] for sid in ids if isinstance(observations.get(sid), dict)] + [event]
            latest = max(seen, key=lambda o: str(o.get("status_observed_at") or ""))
            if latest.get("status_normalized") in ("finished", "postponed", "cancelled"):
                continue
            for name in products:
                prefix = name.replace("_", "-") + ":"
                mine = [sid for sid in ids if isinstance(sid, str) and sid.startswith(prefix)]
                if mine:
                    found.setdefault(name, []).append((event, mine))
        return found

    def live_lane(self, now=None):
        """One pass of the live-status lane; returns the number of status observations that changed.

        Never touches the day assets: observations go to ``live_observations`` (keyed by source event id), which
        the feed publishes as the small ``live`` asset and the next materialisation folds into the events."""
        now = now or datetime.now(timezone.utc)
        conf = self.store.config()
        stamp = now.isoformat(timespec="seconds")
        if not conf["setup_complete"] or not self.live_lane_enabled(conf):
            return 0
        stored = self.store._get("live_observations") or {}
        observations = dict(stored.get("events") or {})
        candidates = self._live_candidates(conf, now, observations)
        calls, changed, notes = 0, 0, []
        score_sources = feed.score_approvals(conf)      # empty (the default): scores are neither read nor stored
        for name, rows in sorted(candidates.items()):
            _, base, key_name, daily_limit = providers.SPORTS[name]
            unsupported = self.store._get("live_unsupported:" + name) or ""
            if unsupported > stamp:
                notes.append("%s: live board refused earlier; retry after %s" % (name, unsupported[:16]))
                continue
            window = self._plan_window(name)
            if window and not window[0] <= 0 <= window[1]:
                notes.append("%s: today is outside the provider plan's dates" % name)
                continue
            if self.store.usage().get(name, 0) >= daily_limit - LIVE_RESERVE:
                notes.append("%s: remaining calls kept for scheduled refreshes" % name)
                continue
            if name == "api_sports":
                decode = providers.api_sports_events
            else:
                decode = partial(providers.api_sports_games_events, source_id=name, sport=providers.API_SPORTS_SPORT[name])
            item = dict(url=base + "?" + urllib.parse.urlencode({"live": "all"}),
                        headers={"x-apisports-key": conf["keys"].get(key_name, "")}, scope="live", decode=decode,
                        max_bytes=7_000_000)
            try:
                self._check_sport_backoff(name)
                try:
                    self.store.increment("live:" + name, LIVE_DAILY_BUDGET)
                except RuntimeError:
                    notes.append("%s: daily live budget (%d) used" % (name, LIVE_DAILY_BUDGET))
                    continue
                board = {row["id"]: row for row in self._request(name, item, daily_limit)}
                calls += 1
            except QuotaExhausted as exc:
                notes.append("%s: %s" % (name, str(exc)[:80]))
                continue
            except providers.PlanWindow as exc:
                self._learn_plan_window(name, exc, now.astimezone(LONDON).date())
                notes.append("%s: today is outside the provider plan's dates" % name)
                continue
            except SAFE_ERRORS as exc:
                reason = _sports_failure(exc)
                if getattr(exc, "status", None) == 429 or reason == "Provider quota or rate limit":
                    self._defer_sport(name, exc)
                elif reason in ("Provider plan or season restriction", "Provider rejected the requested scope"):
                    self.store._put("live_unsupported:" + name,
                                    (now + timedelta(days=LIVE_UNSUPPORTED_DAYS)).isoformat(timespec="seconds"))
                notes.append("%s: %s" % (name, reason))
                continue
            for event, ids in rows:
                for sid in ids:
                    previous = observations.get(sid)
                    score = None
                    if sid in board:
                        status, raw = board[sid]["status_normalized"], str(board[sid].get("status") or "")[:20]
                        if name in score_sources:
                            score = board[sid].get("score")
                    else:
                        before = (previous or event).get("status_normalized")
                        if before != "live":
                            continue           # not on the board and not known live: nothing new to say
                        status, raw = "unknown", "left the live board"   # finished? abandoned? not claimed
                    if previous and previous.get("status_normalized") == status:
                        try:
                            # A changed score is news at once (it republishes the live asset); otherwise an unchanged
                            # status is only re-confirmed every LIVE_REFRESH.
                            if (previous.get("score") == score
                                    and now - datetime.fromisoformat(previous["status_observed_at"]) < LIVE_REFRESH):
                                continue       # unchanged and recently confirmed: no new asset
                        except (KeyError, TypeError, ValueError):
                            pass
                    elif not previous and status == event.get("status_normalized") and status != "live":
                        continue
                    observations[sid] = {"status": raw, "status_normalized": status, "status_observed_at": stamp}
                    if score:
                        observations[sid]["score"] = score
                    changed += 1
        # A stored "live" nobody re-confirmed within LIVE_MAX_AGE becomes "unknown" (no API call), so the lane
        # republishes and a published "live" cannot outlive its evidence (readers already ignore it after 45 min).
        for sid, obs in observations.items():
            try:
                stale = (obs.get("status_normalized") == "live"
                         and now - datetime.fromisoformat(obs["status_observed_at"]) > feed.LIVE_MAX_AGE)
            except (KeyError, TypeError, ValueError, AttributeError):
                stale = False
            if stale:
                observations[sid] = {"status": "stale live expired", "status_normalized": "unknown",
                                     "status_observed_at": stamp}
                changed += 1
        cutoff = (now - LIVE_RETAIN).isoformat()
        observations = {k: v for k, v in observations.items() if str(v.get("status_observed_at", "")) >= cutoff}
        if changed or observations != (stored.get("events") or {}):
            self.store._put("live_observations", {"events": observations, "updated_at": stamp})
        in_play = sum(len(rows) for rows in candidates.values())
        summary = "%d events in play; %d live calls; %d status changes" % (in_play, calls, changed)
        if notes:
            summary += "; " + "; ".join(notes[:3])
        self.store._put("live_lane", {"last_run": stamp, "in_play": in_play, "calls": calls, "changed": changed,
                                      "summary": summary[:300]})
        if candidates or notes:
            self.store.job("live_status", "ok" if not notes else "partial", summary)
        return changed

    def _settle_candidates(self, conf, now, observations):
        """{product: {london_day: [(event, [source event ids])]}} for events past expected end + grace (and within
        SETTLE_WINDOW of that) whose latest known status is not final."""
        snapshot = self.store.snapshot("sports")
        events = ((snapshot or {}).get("data") or {}).get("events") or []
        found = {}
        products = [name for name in LIVE_PRODUCTS if conf["sports"].get(name)]
        for event in events:
            if (event.get("origin") == "guide_listing"
                    or event.get("start_precision") in linking.UNCONFIRMED_START_PRECISIONS):
                continue
            try:
                start = datetime.fromisoformat(event["start_utc"])
                due = linking.expected_end(event) + linking.LIVE_END_GRACE
            except (KeyError, TypeError, ValueError):
                continue
            if not due < now <= due + SETTLE_WINDOW:
                continue
            ids = event.get("source_events") or [event.get("id")]
            seen = [observations[sid] for sid in ids if isinstance(observations.get(sid), dict)] + [event]
            latest = max(seen, key=lambda o: str(o.get("status_observed_at") or ""))
            if latest.get("status_normalized") in SETTLE_FINAL:
                continue
            day = start.astimezone(LONDON).date()
            for name in products:
                prefix = name.replace("_", "-") + ":"
                mine = [sid for sid in ids if isinstance(sid, str) and sid.startswith(prefix)]
                if mine:
                    found.setdefault(name, {}).setdefault(day, []).append((event, mine))
        return found

    def settle_pass(self, now=None):
        """Read the provider's explicit final status for events that ended and are still not final; returns the number
        of observations written.

        At most one ``date=`` call per product per SETTLE_INTERVAL (oldest unsettled London day first), at most
        SETTLE_DAILY_BUDGET a day (counter ``settle:<product>``), never into the product's reserve. Only an explicit
        finished/postponed/cancelled status is stored: absence from the response, or any other status, says nothing."""
        now = now or datetime.now(timezone.utc)
        conf = self.store.config()
        stamp = now.isoformat(timespec="seconds")
        if not conf["setup_complete"] or not self.live_lane_enabled(conf):
            return 0
        stored = self.store._get("live_observations") or {}
        observations = dict(stored.get("events") or {})
        candidates = self._settle_candidates(conf, now, observations)
        if not candidates:
            return 0
        today = now.astimezone(LONDON).date()
        calls, changed, notes = 0, 0, []
        score_sources = feed.score_approvals(conf)
        for name, days in sorted(candidates.items()):
            _, base, key_name, daily_limit = providers.SPORTS[name]
            last = self.store._get("settle_last:" + name) or ""
            try:
                if now - datetime.fromisoformat(last) < SETTLE_INTERVAL:
                    continue
            except (TypeError, ValueError):
                pass
            day = min(days)
            window = self._plan_window(name)
            if window and not window[0] <= (day - today).days <= window[1]:
                notes.append("%s: %s is outside the provider plan's dates" % (name, day))
                continue
            if self.store.usage().get(name, 0) >= daily_limit - LIVE_RESERVE:
                notes.append("%s: remaining calls kept for scheduled refreshes" % name)
                continue
            if name == "api_sports":
                decode = providers.api_sports_events
            else:
                decode = partial(providers.api_sports_games_events, source_id=name, sport=providers.API_SPORTS_SPORT[name])
            query = urllib.parse.urlencode({"date": day.isoformat(), "timezone": "Europe/London"})
            item = dict(url=base + "?" + query, headers={"x-apisports-key": conf["keys"].get(key_name, "")},
                        scope="settle:" + day.isoformat(), decode=decode, max_bytes=7_000_000)
            try:
                self._check_sport_backoff(name)
                try:
                    self.store.increment("settle:" + name, SETTLE_DAILY_BUDGET)
                except RuntimeError:
                    notes.append("%s: daily settle budget (%d) used" % (name, SETTLE_DAILY_BUDGET))
                    continue
                self.store._put("settle_last:" + name, stamp)
                board = {row["id"]: row for row in self._request(name, item, daily_limit)}
                calls += 1
            except QuotaExhausted as exc:
                notes.append("%s: %s" % (name, str(exc)[:80]))
                continue
            except providers.PlanWindow as exc:
                self._learn_plan_window(name, exc, today)
                notes.append("%s: %s is outside the provider plan's dates" % (name, day))
                continue
            except SAFE_ERRORS as exc:
                reason = _sports_failure(exc)
                if getattr(exc, "status", None) == 429 or reason == "Provider quota or rate limit":
                    self._defer_sport(name, exc)
                notes.append("%s: %s" % (name, reason))
                continue
            for _, ids in days[day]:
                for sid in ids:
                    row = board.get(sid)
                    status = (row or {}).get("status_normalized")
                    if status not in SETTLE_FINAL:
                        continue               # still in progress, or not listed: never claimed finished
                    previous = observations.get(sid)
                    score = row.get("score") if name in score_sources and status == "finished" else None
                    if previous and previous.get("status_normalized") == status and (
                            score is None or previous.get("score") == score):
                        continue
                    observations[sid] = {"status": str(row.get("status") or "")[:20], "status_normalized": status,
                                         "status_observed_at": stamp}
                    if score:
                        observations[sid]["score"] = score     # the final score, read with the final status
                    changed += 1
        if changed:
            self.store._put("live_observations", {"events": observations, "updated_at": stamp})
        unsettled = sum(len(rows) for days in candidates.values() for rows in days.values())
        summary = "%d unsettled events; %d settle calls; %d settled" % (unsettled, calls, changed)
        if notes:
            summary += "; " + "; ".join(notes[:3])
        self.store._put("settle_lane", {"last_run": stamp, "unsettled": unsettled, "calls": calls, "changed": changed,
                                        "summary": summary[:300]})
        return changed

    def _prune_live_observations(self, now):
        stored = self.store._get("live_observations")
        if not stored:
            return
        cutoff = (now - LIVE_RETAIN).isoformat()
        kept = {k: v for k, v in (stored.get("events") or {}).items() if str(v.get("status_observed_at", "")) >= cutoff}
        if kept != stored.get("events"):
            self.store._put("live_observations", dict(stored, events=kept))

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

    def _private_target(self, conf=None):
        """(owner, repository, branch, token) of the private feed; the token is the saved GitHub token."""
        conf = conf or self.store.config()
        target, public = conf.get("private_feed") or {}, conf["github"]
        owner, repository, branch = (target.get(k, "") for k in ("owner", "repository", "branch"))
        if (owner.casefold(), repository.casefold()) == (public.get("owner", "").casefold(),
                                                         public.get("repository", "").casefold()):
            raise ValueError("The private feed needs its own repository, not the public feed repository")
        return owner, repository, branch, public.get("token", "")

    def test_github_destination(self, private=False):
        """Read-only check that the saved fine-grained token reaches its target.

        A GET does not prove Contents:write. This intentionally never commits,
        modifies repository settings, or attempts to publish unlicensed data.
        The private feed target must be a private repository; the public one public.
        """
        if private:
            owner, repository, branch, token = self._private_target()
        else:
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
            if private and info.get("private") is not True:
                raise ValueError("The private feed destination must be a PRIVATE repository; make it private on GitHub first")
            if not private and info.get("private") is not False:
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
        if private:
            return ("GitHub token authenticated, private feed repository confirmed private, branch readable and "
                    "write access confirmed (no commit or file was created).")
        return ("GitHub token authenticated, public feed branch readable and write access confirmed "
                "(no commit or file was created). Publishing still requires approved sources.")

    # ---- Owner channel-list coverage (local only; nothing here is ever published) ----------
    def import_lineup(self, text):
        """Store the owner's channel list (M3U or text) locally; stream URLs are discarded while reading."""
        entries = coverage.parse_lineup(text)
        if not entries:
            raise ValueError("No channels found in that file (expected an M3U playlist or one channel per line)")
        self.store.save_snapshot(coverage.LINEUP_PRODUCT, {"entries": entries, "imported_at": utcnow()})
        LOGGER.info("Channel list imported locally (%d entries)", len(entries))
        self.start_coverage(survey=False)
        return len(entries)

    def delete_lineup(self):
        self.store.save_snapshots({coverage.LINEUP_PRODUCT: {"entries": []}, coverage.REPORT_PRODUCT: {},
                                   coverage.TV_EXPORT_PRODUCT: {"rows": []}, coverage.COMPARISON_PRODUCT: {}})

    def import_tv_export(self, text):
        """Store B1G's per-channel export (local CSV from the TV) and compare it with SportsLiveInfo's result."""
        rows = coverage.parse_tv_export(text)
        if not rows:
            raise ValueError("That B1G export has no channels")
        self.store.save_snapshot(coverage.TV_EXPORT_PRODUCT, {"rows": rows, "imported_at": utcnow()})
        LOGGER.info("B1G channel export imported locally (%d rows)", len(rows))
        self.start_coverage(survey=False)
        return len(rows)

    def delete_tv_export(self):
        self.store.save_snapshots({coverage.TV_EXPORT_PRODUCT: {"rows": []}, coverage.COMPARISON_PRODUCT: {}})

    def start_coverage(self, survey=False):
        """Rebuild the coverage report (and first survey every guide when asked) in the background."""
        with self._publish_start:
            thread = self._test_threads.get("coverage")
            if thread is not None and thread.is_alive():
                return False
            self.store._put("coverage:status", {"state": "running", "at": utcnow(),
                                                "message": "Surveying guides" if survey else "Building report"})
            thread = threading.Thread(target=self._coverage_job, args=(survey,), name="sportsliveinfo-coverage",
                                      daemon=True)
            self._test_threads["coverage"] = thread
            thread.start()
        return True

    def _coverage_job(self, survey):
        try:
            surveyed = self._survey_guides() if survey else None
            self._build_coverage()
            message = "Report ready" + ("; %d guides surveyed" % surveyed if surveyed is not None else "")
            self.store._put("coverage:status", {"state": "done", "at": utcnow(), "message": message})
        except Exception as exc:
            LOGGER.exception("Coverage job failed")
            self.store._put("coverage:status", {"state": "failed", "at": utcnow(),
                                                "message": "Failed (%s); see the App log" % type(exc).__name__})

    def _survey_guides(self):
        """Download every catalogue guide not enabled (at most once a day each) and keep a compact
        channel index: ids, names, programme counts. Programmes themselves are not kept."""
        enabled = {n for n, on in self.store.config()["epg"].items() if on}
        done = 0
        for name, (_label, url) in providers.EPG.items():
            if name in enabled:
                continue
            previous = self.store.snapshot(coverage.SURVEY_PREFIX + name)
            if previous and previous.get("updated_at", "") > (datetime.now(timezone.utc) - timedelta(hours=20)).isoformat():
                continue
            self.store._put("coverage:status", {"state": "running", "at": utcnow(),
                                                "message": "Surveying guides: %s (%d done)" % (name, done)})
            max_bytes, max_programmes = providers.EPG_LIMITS.get(name, providers.DEFAULT_EPG_LIMIT)
            try:
                self._reserve_epg(name)
                guide = providers.decode_xmltv(providers.fetch(url, max_bytes=max_bytes), name,
                                               max_programmes=max_programmes)
                index = coverage.guide_index(name, guide)
                index["status"] = "ok"
                del guide
            except QuotaExhausted as exc:
                index = {"source_id": name, "status": "deferred", "reason": str(exc)[:200], "channels": {},
                         "programmes": {}}
            except Exception as exc:   # one unreachable guide never stops the survey
                reason = (_guide_failure(exc) if isinstance(exc, (ValueError, RuntimeError, TimeoutError))
                          else type(exc).__name__)
                index = {"source_id": name, "status": "failed", "reason": reason[:200], "channels": {},
                         "programmes": {}}
            self.store.save_snapshot(coverage.SURVEY_PREFIX + name, index)
            done += 1
        return done

    def _build_coverage(self):
        lineup = (self.store.snapshot(coverage.LINEUP_PRODUCT) or {}).get("data") or {}
        if not lineup.get("entries"):
            self.store.save_snapshot(coverage.REPORT_PRODUCT, {})
            return
        config = self.store.config()
        enabled_indexes, surveyed_indexes = [], []
        for name in providers.EPG:
            if config["epg"].get(name):
                snapshot = self.store.snapshot("epg:" + name)
                if snapshot and snapshot.get("data"):
                    enabled_indexes.append(coverage.guide_index(name, snapshot["data"]))
            else:
                snapshot = self.store.snapshot(coverage.SURVEY_PREFIX + name)
                if snapshot and (snapshot.get("data") or {}).get("status") == "ok":
                    surveyed_indexes.append(snapshot["data"])
        dictionary_snapshot = self.store.snapshot("channel-dictionary")
        document = ((dictionary_snapshot or {}).get("data") or {}).get("document")
        report = coverage.build_report(lineup["entries"], dictionary_document=document,
                                       enabled_indexes=enabled_indexes, surveyed_indexes=surveyed_indexes,
                                       now=datetime.now(timezone.utc))
        report["built_at"] = utcnow()
        report["dictionary"] = bool(document)
        self.store.save_snapshot(coverage.REPORT_PRODUCT, report)
        tv_export = (self.store.snapshot(coverage.TV_EXPORT_PRODUCT) or {}).get("data") or {}
        if tv_export.get("rows"):
            # The TV sees the published dictionary and guide map, so compare against exactly those.
            published = feed.dictionary_document(self.store, config)
            resolver = dictionary.Resolver(published) if published else None
            comparison = coverage.compare_tv_export(lineup["entries"], tv_export["rows"], resolver=resolver,
                                                    guide_map=feed.guide_map_document(self.store),
                                                    now=datetime.now(timezone.utc))
            comparison["built_at"] = utcnow()
            self.store.save_snapshot(coverage.COMPARISON_PRODUCT, comparison)

    def start_connection_test(self, private=False):
        """Run the GitHub connection test in the background; False if one for this target is running.

        The test makes up to three GitHub requests. Inside the Ingress request, a slow
        network or Home Assistant remote access could drop the connection before the
        answer arrived, so the result was never seen. The page and App log show it instead.
        """
        target = "private" if private else "public"
        with self._publish_start:
            thread = self._test_threads.get(target)
            if thread is not None and thread.is_alive():
                return False
            self._set_test_status(target, "running", "Connection test in progress")
            thread = threading.Thread(target=self._connection_test_job, args=(private,),
                                      name="sportsliveinfo-test-" + target, daemon=True)
            self._test_threads[target] = thread
            thread.start()
        return True

    def _set_test_status(self, target, state, message):
        self.store._put("connection_test:" + target, {"state": state, "message": str(message)[:300], "at": utcnow()})

    def _connection_test_job(self, private):
        target = "private" if private else "public"
        try:
            message = self.test_github_destination(private=private)
            state = "succeeded"
            LOGGER.info("GitHub connection test (%s feed) succeeded: %s", target, message)
        except (ValueError, RuntimeError, OSError) as exc:
            message, state = str(exc)[:300], "failed"
            LOGGER.warning("GitHub connection test (%s feed) failed: %s", target, message)
        except Exception as exc:
            LOGGER.exception("GitHub connection test (%s feed) failed", target)
            message, state = "Unexpected %s; see the App log" % type(exc).__name__, "failed"
        self._set_test_status(target, state, message)

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
        conf = self.store.config()
        private_note = ""
        if (conf.get("private_feed") or {}).get("enabled"):
            # The private feed never blocks or changes the public one, and vice versa.
            try:
                private_revision = self.publish_private()
                private_note = "; private feed %s %s" % (
                    private_revision, "unchanged" if self._private_outcome == "unchanged" else "committed")
                LOGGER.info("Private feed publication finished (%s): %s", trigger, private_revision)
            except (ValueError, RuntimeError, OSError) as exc:
                private_note = "; private feed failed: %s" % str(exc)[:200]
                LOGGER.warning("Private feed publication failed (%s): %s", trigger, str(exc)[:300])
                self.store.job("private_publisher", "failed", str(exc)[:300])
            if not conf["github"].get("enabled"):
                state = "failed" if "failed" in private_note else "succeeded"
                self._set_publish_status(state, private_note.lstrip("; ").capitalize(), trigger)
                return None
        try:
            revision = self.publish() if trigger == "manual" else self.publish(allow_regression=False)
        except PublishRegression as exc:
            message = "Automatic publish refused: %s; the previous feed stays live. Publish manually to override" % exc
            LOGGER.warning("Feed publication refused (%s): %s", trigger, message)
            self.store.job("publisher", "blocked", message)
            self.store._put("publish_gate", {"blocked_at": utcnow(), "reason": str(exc)[:200], "trigger": trigger})
            self._set_publish_status("failed", message + private_note, trigger)
            return None
        except (ValueError, RuntimeError, OSError) as exc:
            message = str(exc)[:300]
            LOGGER.warning("Feed publication failed (%s): %s", trigger, message)
            self.store.job("publisher", "failed", message)
            self._set_publish_status("failed", message + private_note, trigger)
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
        self._set_publish_status("failed" if "failed" in private_note else "succeeded", message + private_note, trigger)
        return revision

    def publish(self, allow_regression=True):
        """Publish the sli/1 feed in ONE atomic commit; EPG programme text is never copied.

        ``allow_regression=False`` (automatic publication) refuses a feed that lost more than
        ``PUBLISH_REGRESSION_THRESHOLD`` of its events or corroborated bindings against the published one.

        Disabled by default. Events appear only for sources whose public
        redistribution licence has been explicitly approved.
        """
        if not self._publish_lock.acquire(timeout=120):
            raise RuntimeError("Another feed publication is already running")
        try:
            return self._publish() if allow_regression else self._publish(False)
        finally:
            self._publish_lock.release()

    def publish_private(self):
        """Publish the owner's private personal-use feed (all events + guide-listed live sport)."""
        if not self._publish_lock.acquire(timeout=120):
            raise RuntimeError("Another feed publication is already running")
        try:
            return self._publish_private()
        finally:
            self._publish_lock.release()

    def _publish_private(self):
        conf = self.store.config()
        self._private_outcome = None
        if not conf["setup_complete"]:
            raise ValueError("Finish first-run setup (Sources page) before publishing")
        if not (conf.get("private_feed") or {}).get("enabled"):
            raise ValueError("Tick Enable private feed and save its settings first")
        if not self.store.snapshot("sports"):
            raise ValueError("No valid sports snapshot yet")
        owner, repository, branch, token = self._private_target(conf)
        if not owner or not repository or not branch or not token:
            raise ValueError("Private feed repository or GitHub token incomplete")
        validate_github_target(owner, repository, branch)
        state = self.store._get("private_feed_state") or {"revisions": []}
        manifest, files = feed.build_feed(self.store, previous_revision=state.get("last_revision"), private=True)
        outcome, revision = self._commit_feed(owner, repository, branch, token, manifest, files, state,
                                              "private_feed_state", "private_publisher", "SportsLiveInfo private feed", private=True)
        self._private_outcome = outcome
        return revision

    def _publish(self, allow_regression=True):
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
        if not allow_regression and manifest["revision"] != state.get("last_revision"):
            reason = publish_regression(state.get("stats"), manifest)
            if reason:
                raise PublishRegression(reason)
        outcome, revision = self._commit_feed(owner, repository, branch, token, manifest, files, state,
                                              "feed_state", "publisher", "SportsLiveInfo feed", private=False)
        self._publish_outcome = outcome
        return revision

    def _commit_feed(self, owner, repository, branch, token, manifest, files, state, state_key, job, label, private):
        """One atomic commit with revision retention; returns (outcome, revision)."""
        revision = manifest["revision"]
        try:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(state.get("published_at") or "")
        except (TypeError, ValueError):
            age = timedelta(days=999)
        # Republish an unchanged revision only to renew the manifest's expiry
        # (48 h) before TVs would wrongly treat a static-but-healthy feed as stale.
        if revision == state.get("last_revision") and age < timedelta(hours=24):
            self.store.job(job, "unchanged", "Feed revision %s already published" % revision)
            return "unchanged", revision
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
                            "%s %s (%d events)" % (label, revision, manifest["coverage"]["events"]),
                            required=files, private=private)
        cover = manifest["coverage"]
        self.store._put(state_key, {"last_revision": revision, "revisions": keep, "published_at": utcnow(),
                                    "stats": {"events": cover["events"],
                                              "corroborated_bindings": cover["guide_corroborated_broadcasts"]}})
        self.store.job(job, "submitted", "Feed %s committed atomically (%d new files, %d removed); verify the static endpoint" % (
            revision, len(uploads), len(deletions)))
        return "committed", revision

    @staticmethod
    def _github_commit(owner, repository, branch, token, uploads, deletions, message, required=None, private=None):
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

        # Re-check the destination on every publish, not only in the connection test: a private feed (every collected
        # event and guide-derived listings) must never land in a repository that was made public or mistyped since.
        if private is not None:
            info = api("GET", "", step="checking the repository")
            if not isinstance(info, dict) or str(info.get("full_name", "")).casefold() != (owner + "/" + repository).casefold():
                raise RuntimeError("GitHub returned a different repository; nothing was published")
            if private and info.get("private") is not True:
                raise RuntimeError("The private feed repository is not private on GitHub; nothing was published")
            if not private and info.get("private") is not False:
                raise RuntimeError("The public feed repository is not public on GitHub; nothing was published")
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
