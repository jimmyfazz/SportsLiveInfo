"""Private Home Assistant Ingress UI; no directly published Home Assistant port."""
import html
import json
import logging
import os
import re
import secrets
import threading
import urllib.parse
from collections import OrderedDict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

from . import __version__, linking, providers, taxonomy
from .storage import utcnow

LOGGER = logging.getLogger(__name__)
LONDON = ZoneInfo("Europe/London")
LIVE_LABELS = {"live": "LIVE", "live_probable": "Probably live", "upcoming": "Upcoming", "finished": "Finished",
               "probably_finished": "Probably finished", "postponed": "Postponed", "cancelled": "Cancelled",
               "time_tbc": "Time TBC", "unknown": "Unknown"}
STATE_CLASS = {"ok": "ok", "finished": "ok", "test_ok": "ok", "submitted": "ok", "preview": "ok", "unchanged": "ok",
               "partial": "warn", "degraded": "warn", "stale": "warn", "empty": "warn", "needs_key": "warn",
               "no_events_reported": "warn", "coverage_collapse": "warn", "failed": "critical", "test_failed": "critical",
               "lane_error": "critical", "error": "critical"}
ICON_PATHS = (Path(__file__).parent / "icon.png", Path(__file__).resolve().parents[2] / "icon.png")

CSS = """
:root{color-scheme:dark;font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;background:#081224;color:#e8f3ff}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 90% -30%,#103b54,transparent 55%),#081224}
main{max-width:1140px;margin:auto;padding:24px 24px 50px}header{display:flex;align-items:center;gap:17px;margin-bottom:23px}header img{width:64px;height:64px;object-fit:contain;border-radius:14px}
h1{font-size:27px;letter-spacing:-.7px;margin:0}h2{font-size:18px;margin:0 0 16px}h3{font-size:16px;margin:0 0 8px}
p{line-height:1.55;margin:8px 0 15px;color:#b2c3d6}.sub{font-size:13px;color:#a5b8cc}
nav{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:24px}nav a{color:#d1e6f5;border:1px solid #29465b;border-radius:11px;padding:10px 14px;text-decoration:none}nav a:hover,nav a.active{background:#123c52;border-color:#3fb8ba}
a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible{outline:2px solid #a2ef59;outline-offset:2px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}.card{padding:20px;border-radius:16px;border:1px solid #254157;background:#0d2034;box-shadow:0 8px 20px #0002}
.metric{font-size:32px;font-weight:700;color:#bbf977}.pill{display:inline-block;padding:3px 9px;border-radius:20px;background:#14364a;color:#85e1eb;font-size:12px}
.pill.live{background:#3a1d22;color:#ff9c8f}.pill.warn{background:#3a3020;color:#ffd68b}
.warn{color:#ffd68b}.ok{color:#b1ec91}.critical{color:#ffb1a2}label{display:block;margin:12px 0 6px;font-size:13px;color:#d8e8f7}
input[type=text],input[type=password],select{width:100%;background:#071627;border:1px solid #376078;color:#f4f9ff;padding:12px 13px;border-radius:8px;font:inherit}
input[type=checkbox]{accent-color:#88df88;width:18px;height:18px;vertical-align:middle}button{border:0;background:linear-gradient(110deg,#05c6cc,#a2ef59);color:#071524;border-radius:9px;padding:10px 16px;font-size:14px;font-weight:750;cursor:pointer;margin-top:10px}button:hover{filter:brightness(1.08)}button.secondary{background:#234659;color:white}
button:disabled{background:#2a3a48;color:#8ea3b5;cursor:not-allowed;filter:none}
form{margin:0 0 15px}.help{font-size:12px;color:#94adbf}.formrow{display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap}.formrow>*{flex:1 1 180px}.formrow button{flex:0 0 auto}.formrow label.inline{flex:0 0 auto}
.divider{height:1px;background:#294258;margin:18px 0}
table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:9px;text-align:left;border-bottom:1px solid #244054;word-break:break-word;vertical-align:top}th{color:#b8d4e4}
table.fixed{table-layout:fixed}table.fixed col.time{width:110px}table.fixed col.chan{width:28%}
tr.group td{background:#10283f;color:#cfe4f3;font-weight:650;border-bottom:1px solid #2c4b63}
.alert{padding:13px 16px;border-radius:11px;border-left:4px solid #80dfe3;background:#133043;margin-bottom:20px}.error{border-color:#ffb181;background:#38252b}
details.group{margin:14px 0;border:1px solid #254157;border-radius:14px;background:#0b1c2e}details.group>summary{cursor:pointer;padding:14px 18px;font-weight:650;list-style-position:inside}
details.group[open]>summary{border-bottom:1px solid #254157}details.group>.grid{padding:14px}
a{color:#7be1eb}small{color:#a0b8cb}.footer{margin-top:30px;color:#829db1;font-size:12px}
@media(max-width:600px){main{padding:14px}header img{width:48px;height:48px}h1{font-size:22px}.card{padding:14px}table.fixed col.time{width:70px}}
"""


def e(value):
    """HTML-escape for text and attributes. Zero and False must still render."""
    return html.escape("" if value is None else str(value), quote=True)


def when(value, now=None):
    """'13 Nov 09:29 GMT (2 h ago)' from an ISO timestamp; raw text if unparsable."""
    if not value:
        return "never"
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
    except ValueError:
        return str(value)
    now = now or datetime.now(timezone.utc)
    seconds = (now - moment).total_seconds()
    if abs(seconds) < 90:
        rel = "just now"
    elif abs(seconds) < 5400:
        rel = "%d min %s" % (round(abs(seconds) / 60), "ago" if seconds > 0 else "from now")
    elif abs(seconds) < 172800:
        rel = "%d h %s" % (round(abs(seconds) / 3600), "ago" if seconds > 0 else "from now")
    else:
        rel = "%d days %s" % (round(abs(seconds) / 86400), "ago" if seconds > 0 else "from now")
    return "%s (%s)" % (moment.astimezone(LONDON).strftime("%d %b %H:%M %Z"), rel)


class _Flash:
    """Short-lived server-side notices so a crafted ?message= URL cannot spoof app alerts."""

    def __init__(self, limit=64):
        self._items, self._lock, self._limit = OrderedDict(), threading.Lock(), limit

    def put(self, text):
        token = secrets.token_urlsafe(6)
        with self._lock:
            self._items[token] = str(text)[:200]
            while len(self._items) > self._limit:
                self._items.popitem(last=False)
        return token

    def get(self, token):
        with self._lock:
            return self._items.get(token or "", "")


def _flash(server):
    flash = getattr(server, "flash", None)
    if flash is None:
        flash = server.flash = _Flash()
    return flash


class UI(BaseHTTPRequestHandler):
    server_version = "SportsLiveInfo/" + __version__
    timeout = 20  # a client that announces more body than it sends cannot pin a thread

    def setup(self):
        if not hasattr(self.request, "settimeout"):
            self.timeout = None
        super().setup()

    def log_message(self, format, *args):
        # Never emit paths or form fields; some future auth connectors may use URLs.
        LOGGER.info("Ingress %s %s", self.command, self.client_address[0])

    def _allowed(self):
        # Home Assistant Ingress is the sole production entry point; use an
        # explicit admin-configured proxy IP set, never a spoofable HTTP header.
        peers = os.environ.get("SLI_INGRESS_TRUSTED_IPS", "172.30.32.2,127.0.0.1,::1")
        trusted = {address.strip() for address in peers.split(",") if address.strip()}
        return (os.environ.get("SLI_DEV") == "1"
                or self.client_address[0] in trusted)

    def _headers(self, code=200, content_type="text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'self'")
        self.end_headers()

    @property
    def store(self):
        return self.server.store

    @property
    def engine(self):
        return self.server.engine

    def do_GET(self):
        try:
            self._get()
        except Exception as exc:  # always answer; the Ingress proxy otherwise shows a blank 502
            LOGGER.exception("Ingress page failed")
            try:
                self.store.job("ui", "error", "Page failed: %s" % type(exc).__name__)
                self._headers(500)
                self.wfile.write(b"<p>SportsLiveInfo could not render this page. See Diagnostics.</p>")
            except Exception:
                pass

    def _get(self):
        if not self._allowed():
            self._headers(403)
            self.wfile.write(b"Not available outside authenticated Home Assistant Ingress")
            return
        route = urllib.parse.urlsplit(self.path)
        if route.path == "/icon.png":
            data = next((p.read_bytes() for p in ICON_PATHS if p.is_file()), None)
            if data is None:
                self._headers(404)
                return
            self._headers(200, "image/png")
            self.wfile.write(data)
            return
        if route.path == "/healthz":
            beat = self.store._get("scheduler_heartbeat")
            self._headers(200, "application/json")
            self.wfile.write(json.dumps({"ok": True, "version": __version__, "scheduler_heartbeat": beat}).encode())
            return
        if route.path not in ("/", ""):
            self._headers(404)
            return
        query = urllib.parse.parse_qs(route.query)
        page = query.get("page", ["dashboard"])[0]
        notice = _flash(self.server).get(query.get("m", [""])[0])
        config = self.store.config()
        if not config["setup_complete"] and page == "dashboard":
            page = "sources"
        body = self.render(page, config, notice, {k: v[0][:80] for k, v in query.items()})
        self._headers()
        self.wfile.write(body.encode("utf-8"))

    def do_POST(self):
        if not self._allowed():
            self._headers(403)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except (TypeError, ValueError):
            self._headers(400)
            return
        if size < 0 or size > 12_000:
            self._headers(413)
            return
        form = urllib.parse.parse_qs(self.rfile.read(size).decode("utf-8", errors="replace"), keep_blank_values=True)
        value = lambda key: form.get(key, [""])[0].strip()
        # Compare bytes: str compare_digest raises TypeError on non-ASCII input.
        if not secrets.compare_digest(value("csrf").encode("utf-8"), self.server.csrf.encode("utf-8")):
            self._headers(403)
            return
        action = value("action")
        page = "dashboard" if self.store.config()["setup_complete"] else "sources"
        message = "Settings saved"
        try:
            page, message = self._action(action, form, value, page, message)
        except (ValueError, RuntimeError) as exc:
            # Render only own controlled errors, not upstream URLs or secret-bearing exceptions.
            message = str(exc)[:140]
        except Exception as exc:
            LOGGER.exception("Ingress action %s failed", action[:20])
            self.store.job("ui", "error", "Action %s failed: %s" % (action[:20], type(exc).__name__))
            message = "Unexpected error (%s); nothing else was changed. See Diagnostics." % type(exc).__name__
        url = "?page=%s&m=%s" % (urllib.parse.quote(page), urllib.parse.quote(_flash(self.server).put(message)))
        self.send_response(303)
        self.send_header("Location", url)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _action(self, action, form, value, page, message):
        if action == "sports":
            name = value("provider")
            if name not in providers.SPORTS:
                raise ValueError("Unknown sports provider")
            key_name = providers.SPORTS[name][2]
            secret = value("key")
            if secret and value("remove") == "on":
                raise ValueError("Enter a new key or tick Remove saved key, not both")
            self.store.configure({"sports": {name: value("enabled") == "on"}})
            # Keys are stored by provider account, so one API-Sports key serves every API-Sports sport.
            if secret and key_name:
                if len(secret) > 512:
                    raise ValueError("API key exceeds safe length")
                self.store.configure({"keys": {key_name: secret}})
            if value("remove") == "on" and key_name:
                self.store.configure({"keys": {key_name: ""}})
            return "sources", message
        if action == "options":
            sports = [s for s in form.get("tsdb", []) if s in providers.THESPORTSDB_SPORTS]
            leagues = [l for l in form.get("old", []) if l in providers.OPENLIGADB_LEAGUES]
            if not sports or not leagues:
                raise ValueError("Choose at least one TheSportsDB sport and one OpenLigaDB league")
            self.store.configure({"options": {"thesportsdb_sports": sports, "openligadb_leagues": leagues}})
            return "sources", message
        if action == "epg":
            name = value("provider")
            if name not in providers.EPG:
                raise ValueError("Unknown EPG source")
            self.store.configure({"epg": {name: value("enabled") == "on"}})
            return "sources", message
        if action == "test_source":
            kind, name = value("kind"), value("provider")
            if kind not in ("sports", "epg") or name not in (providers.SPORTS if kind == "sports" else providers.EPG):
                raise ValueError("Unknown test source")
            # One source only. No credentials or untrusted URLs enter logs.
            return "sources", self.engine.test_source(kind, name)
        if action == "github":
            from .engine import validate_github_target
            owner, repository, branch = validate_github_target(value("owner"), value("repository"), value("branch"))
            updates = {"owner": owner, "repository": repository, "branch": branch, "enabled": value("enabled") == "on",
                       "auto_publish": value("auto_publish") == "on"}
            if value("token") and value("remove") == "on":
                raise ValueError("Enter a new token or tick Remove saved token, not both")
            if value("token"):
                if len(value("token")) > 400:
                    raise ValueError("GitHub token exceeds safe length")
                updates["token"] = value("token")
            if value("remove") == "on":
                updates["token"] = ""
            self.store.configure({"github": updates})
            return "publishing", message
        if action == "approvals":
            chosen = sorted({s for s in form.get("approve", []) if s in providers.SPORTS})
            if chosen and value("attest") != "on":
                raise ValueError("Confirm you have reviewed each selected source's redistribution terms")
            self.store.configure({"publication_approvals": chosen})
            log = (self.store._get("approval_log") or [])[-49:]
            log.append({"at": utcnow(), "approved": chosen})
            self.store._put("approval_log", log)
            return "publishing", ("Publication approvals saved: %s" % ", ".join(chosen)) if chosen else "All publication approvals withdrawn"
        if action == "test_github":
            # Authenticate and inspect the SAVED destination; never commit.
            return "publishing", self.engine.test_github_destination()
        if action == "schedule":
            times = []
            for t in value("times").split(","):
                t = t.strip()
                if t and re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", t):
                    times.append(t)
                elif t:
                    raise ValueError("Enter times as HH:MM, separated by commas")
            if not times or len(times) > 6:
                raise ValueError("Choose 1 to 6 daily refresh times")
            self.store.configure({"schedule": list(dict.fromkeys(times))})
            return "scheduler", message
        if action == "finish":
            self.store.configure({"setup_complete": True})
            return "dashboard", "First-run setup complete; collector is ready"
        if action == "collect":
            if not self.store.config()["setup_complete"]:
                raise ValueError("Finish initial setup first")
            started = self.engine.start_collection()
            return "dashboard", "Refresh started. Check source history shortly" if started else "A refresh is already running"
        if action == "publish":
            revision = self.engine.publish()
            return "publishing", "Feed %s committed atomically; public endpoint verification remains necessary" % revision
        if action == "preview_feed":
            manifest = self.engine.preview_feed()
            return "publishing", "Feed preview %s built locally (%d assets); nothing uploaded" % (manifest["revision"], len(manifest["assets"]))
        raise ValueError("Unsupported action")

    def _form(self, action, inner, extra=""):
        return '<form method="post"><input type="hidden" name="csrf" value="%s"><input type="hidden" name="action" value="%s">%s%s</form>' % (e(self.server.csrf), e(action), extra, inner)

    def render(self, page, config, notice, query=None):
        query = query or {}
        tabs = [("dashboard", "Overview"), ("today", "Live today"), ("sources", "Sources & API keys"), ("events", "Sports events"), ("guide", "EPG coverage"), ("scheduler", "Scheduler"), ("publishing", "Publishing"), ("health", "Diagnostics")]
        if page not in {key for key, _ in tabs}:
            page = "dashboard" if config["setup_complete"] else "sources"
        head = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SportsLiveInfo</title><style>%s</style></head><body><main>' % CSS
        head += '<header><img src="icon.png" alt="" width="64" height="64"><div><h1>SportsLiveInfo</h1><div class="sub">International EPG intelligence · Live sporting fixtures</div></div></header>'
        if not config["setup_complete"]:
            head += '<div class="alert">First-run setup: configure providers, review refresh times and optionally set a publishing destination. Credentials are stored privately in the Home Assistant App data volume.</div>'
        if notice:
            head += '<div class="alert" role="status">%s</div>' % e(notice)
        head += '<nav aria-label="Sections">' + ''.join('<a class="%s" href="?page=%s"%s>%s</a>' % ("active" if page == key else "", e(key), ' aria-current="page"' if page == key else "", e(label)) for key, label in tabs) + '</nav>'
        if page == "sources":
            body = self.sources(config)
        elif page == "today":
            body = self.today()
        elif page == "events":
            body = self.events(query)
        elif page == "guide":
            body = self.guide()
        elif page == "scheduler":
            body = self.schedule(config)
        elif page == "publishing":
            body = self.publishing(config)
        elif page == "health":
            body = self.health(config)
        else:
            body = self.dashboard(config)
        if not config["setup_complete"]:
            body += '<section class="card" style="margin-top:18px"><h2>Complete first-run setup</h2><p>You can return later to change individual suppliers and the schedule. The wizard will not show again automatically after finishing.</p>'
            body += self._form("finish", '<button type="submit">Finish setup</button>') + '</section>'
        return head + body + '<div class="footer">%s · Local-first operation · No public access to Home Assistant · No TV write access to GitHub</div></main></body></html>' % e(__version__)

    def dashboard(self, config):
        sport = self.store.snapshot("sports")
        epg = self.store.snapshot("epg")
        today = self.store.snapshot("today")
        events = sport["data"]["events"] if sport else []
        sources = epg["data"]["sources"] if epg else []
        day = today["data"] if today else {}
        now = datetime.now(timezone.utc)
        todays = self._today_events(day, now)
        live_now = sum(ev["live_state"] in ("live", "live_probable") for ev in todays)
        featured = len(day.get("featured", [])) if day.get("date") == now.astimezone(LONDON).date().isoformat() else 0
        candidates = sum(ev.get("broadcast_status", "none") != "none" for ev in events)
        result = '<div class="grid">'
        for title, value, desc in [("Events today", len(todays), "%d probably live now · %d featured (England, home nations, PPV)" % (live_now, featured)),
                                    ("Sporting events (8 days)", len(events), "De-duplicated across enabled sources"),
                                    ("EPG source feeds", len(sources), "Private guide sources with last-good snapshots"),
                                    ("EPG channel candidates", candidates, "Unverified guide matches; no channel is fabricated from league rights"),
                                    ("API calls today", sum(self.store.usage().values()), "Local call-budget ledger; UTC day")]:
            result += '<div class="card"><div class="sub">%s</div><div class="metric">%s</div><div class="help">%s</div></div>' % (e(title), e(value), e(desc))
        result += '</div><section class="card" style="margin-top:16px"><h2>Collection status</h2>'
        result += '<p>Sports snapshot: <strong>%s</strong><br>EPG snapshot: <strong>%s</strong></p>' % (
            e(when(sport["updated_at"], now)) if sport else "No successful collection yet",
            e(when(epg["updated_at"], now)) if epg else "No successful collection yet")
        result += '<p class="warn">Channel names shown for events are unverified EPG matches. No event is marked playable or published with a broadcaster until a reviewed verification rule confirms it.</p>'
        result += self._form("collect", '<button type="submit">Refresh both engines now</button>')
        labels = {name: providers.SPORTS[name][0] for name in providers.SPORTS}
        result += '</section><div class="grid" style="margin-top:16px"><section class="card"><h2>Sports coverage</h2><p>%s</p></section><section class="card"><h2>EPG coverage</h2><p>%s</p></section></div>' % (
            "<br>".join(e("%s — %d" % (labels.get(s["id"], s["id"]), s["events"])) for s in sport["data"].get("sources", [])) if sport else "No sporting source collected yet",
            "<br>".join(e("%s — %d programmes" % (providers.EPG.get(s["id"], (s["id"],))[0], s["programmes"])) for s in sources) or "No EPG source collected yet")
        return result

    def _source_status(self):
        latest = {}
        for job in self.store.recent_jobs(300):
            latest.setdefault(job["provider"], job)
        return latest

    def sources(self, config):
        latest = self._source_status()
        usage = self.store.usage()
        rows = []
        for name, (label, url, keyname, limit) in providers.SPORTS.items():
            if config["sports"].get(name):
                job = latest.get(name, {})
                key = "n/a" if not keyname else ("saved" if config["keys"].get(keyname) else "missing")
                rows.append((label, "Sports", key, job.get("state", "not run yet"), "%d/%d" % (usage.get(name, 0), limit)))
        for name, (label, url) in providers.EPG.items():
            if config["epg"].get(name):
                job = latest.get(name, {})
                rows.append((label, "EPG", "n/a", job.get("state", "not run yet"), "%d/4" % usage.get("epg:" + name, 0)))
        body = '<h2>Enabled sources at a glance</h2><section class="card">'
        if rows:
            body += '<table><tr><th>Source</th><th>Type</th><th>Key</th><th>Last result</th><th>Calls today</th></tr>'
            for label, kind, key, state, calls in rows:
                body += '<tr><td>%s</td><td>%s</td><td class="%s">%s</td><td class="%s">%s</td><td>%s</td></tr>' % (
                    e(label), e(kind), "warn" if key == "missing" else "", e(key), STATE_CLASS.get(state, ""), e(state), e(calls))
            body += '</table>'
        else:
            body += '<p>No source is enabled yet. Open a group below, tick <strong>Enabled</strong> and save.</p>'
        body += '</section><p>Keys are entered once on Home Assistant, never on the ten televisions. Each Save preserves keys for other providers. One API-Sports key serves every API-Sports sport (each sport has its own free daily allowance).</p>'
        groups = [("Sports — no API key needed", [n for n, v in providers.SPORTS.items() if not v[2]]),
                  ("Sports — API key required", [n for n, v in providers.SPORTS.items() if v[2]])]
        for title, names in groups:
            open_attr = " open" if any(config["sports"].get(n) for n in names) or not rows else ""
            body += '<details class="group"%s><summary>%s <span class="pill">%d</span></summary><div class="grid">' % (open_attr, e(title), len(names))
            for name in names:
                body += self._sport_card(name, config)
            body += '</div></details>'
        options = config.get("options", {})
        chosen_sports, chosen_leagues = set(options.get("thesportsdb_sports", [])), set(options.get("openligadb_leagues", []))
        option_form = '<h3>TheSportsDB sports (one call per sport per day)</h3><div class="formrow">'
        option_form += ''.join('<label class="inline"><input type="checkbox" name="tsdb" value="%s" %s> %s</label>' % (e(s), "checked" if s in chosen_sports else "", e(s)) for s in providers.THESPORTSDB_SPORTS)
        option_form += '</div><h3>OpenLigaDB leagues</h3><div class="formrow">'
        option_form += ''.join('<label class="inline"><input type="checkbox" name="old" value="%s" %s> %s</label>' % (e(l), "checked" if l in chosen_leagues else "", e(l)) for l in providers.OPENLIGADB_LEAGUES)
        option_form += '</div><button type="submit">Save source options</button>'
        body += '<details class="group"><summary>Sports source options</summary><div class="card" style="margin:14px">%s</div></details>' % self._form("options", option_form)
        body += '<h2 style="margin-top:28px">International television EPG sources</h2><p>Sources marked "verify" use a URL pattern that must pass Test EPG first. Optional, private guide collection only. Public re-publication of third-party programme text is DISABLED until verified rights are available.</p>'
        from .guide import COUNTRY_BY_SOURCE
        markets = OrderedDict()
        for name in providers.EPG:
            markets.setdefault(COUNTRY_BY_SOURCE.get(name) or "Multi-country", []).append(name)
        for market, names in sorted(markets.items(), key=lambda kv: ({"GB": 0, "FR": 1, "IE": 2}.get(kv[0], 9), kv[0])):
            enabled = sum(bool(config["epg"].get(n)) for n in names)
            body += '<details class="group"%s><summary>%s guides <span class="pill">%d</span>%s</summary><div class="grid">' % (
                " open" if enabled else "", e(market), len(names), (' <span class="pill">%d enabled</span>' % enabled) if enabled else "")
            for name in names:
                label, url = providers.EPG[name]
                cid = "epg-" + name
                content = '<input type="hidden" name="provider" value="%s"><label for="%s"><input id="%s" type="checkbox" name="enabled" value="on" %s> Enable private guide collection</label><p class="warn help">Rights for public redistribution not established</p><button type="submit">Save this source</button>' % (e(name), e(cid), e(cid), "checked" if config["epg"].get(name) else "")
                test_button = self._form("test_source", '<button class="secondary" type="submit">Test EPG (downloads guide)</button>',
                    '<input type="hidden" name="kind" value="epg"><input type="hidden" name="provider" value="%s">' % e(name))
                body += '<section class="card"><h3>%s</h3><p class="help">Source: %s</p>%s%s</section>' % (
                    e(label), e(urllib.parse.urlsplit(url).hostname), self._form("epg", content), test_button)
            body += '</div></details>'
        return body

    def _sport_card(self, name, config):
        label, url, keyname, limit = providers.SPORTS[name]
        enabled = bool(config["sports"].get(name))
        saved = bool(config["keys"].get(keyname)) if keyname else True
        note = providers.SOURCE_NOTES.get(providers.SPORT_FAMILY[name], "")
        cid, kid = "sport-" + name, "key-" + name
        content = '<input type="hidden" name="provider" value="%s"><label for="%s"><input id="%s" type="checkbox" name="enabled" value="on" %s> Enabled</label>' % (e(name), e(cid), e(cid), "checked" if enabled else "")
        if note:
            content += '<p class="help">%s</p>' % e(note)
        if keyname:
            content += '<p class="help">%s (%s) · configured safe daily budget: %d calls</p><label for="%s">API key (leave blank to keep saved key)</label><input id="%s" type="password" name="key" autocomplete="new-password" placeholder="%s"><label><input type="checkbox" name="remove" value="on"> Remove saved key</label>' % ("Key saved" if saved else "No key configured", e(keyname), limit, e(kid), e(kid), "Saved — enter a replacement" if saved else "Enter provider key")
        else:
            content += '<p class="ok">No API key required · conservative daily budget: %d calls</p>' % limit
        content += '<button type="submit">Save this provider</button>'
        test_button = self._form("test_source", '<button class="secondary" type="submit">Test connection (uses 1 quota call)</button>',
            '<input type="hidden" name="kind" value="sports"><input type="hidden" name="provider" value="%s">' % e(name))
        return '<section class="card"><h3>%s</h3><p class="help">Endpoint: %s</p>%s%s</section>' % (
            e(label), e(urllib.parse.urlsplit(url).hostname), self._form("sports", content), test_button)

    @staticmethod
    def _uk_time(event, fmt="%d %b %H:%M %Z"):
        try:
            if event.get("start_precision") == "date_only":
                return datetime.fromisoformat(event["start_utc"]).astimezone(LONDON).strftime("%d %b") + " (time TBC)"
            return datetime.fromisoformat(event["start_utc"]).astimezone(LONDON).strftime(fmt)
        except (ValueError, KeyError, TypeError):
            return "Unconfirmed"

    @staticmethod
    def _channel_text(event):
        if event.get("broadcast_verified"):
            return ", ".join(str(c.get("name", "")) for c in event.get("broadcasts", []) if isinstance(c, dict)) or "Verified"
        candidates = event.get("broadcast_candidates") or []
        if candidates:
            return "EPG match (unverified): " + ", ".join(c.get("channel_name", "") for c in candidates[:3])
        return "—"

    def _event_row(self, event, fmt="%d %b %H:%M %Z", show_sport=False):
        sources = event.get("sources") or [event.get("source_id", "")]
        confidence = "%s · %s" % (event.get("fixture_confidence", "reported"), ", ".join(sources))
        if event.get("start_conflict"):
            confidence += " · start time disagreement"
        state = event.get("live_state", "")
        pill = ""
        if state in LIVE_LABELS and state not in ("unknown",):
            css = "live" if state in ("live", "live_probable") else ("warn" if state in ("postponed", "cancelled", "time_tbc") else "")
            pill = '<br><span class="pill %s">%s</span>' % (css, e(LIVE_LABELS[state]))
        category = event.get("category_label") or event.get("sport", "")
        if show_sport:
            category = "%s · %s" % (event.get("sport_label") or taxonomy.SPORTS.get(event.get("sport"), ("Other",))[0], category)
        competition = event.get("competition", "")
        sub = "" if not competition or competition == event.get("category_label") else competition
        return '<tr><td>%s%s</td><td>%s<br><small>%s</small></td><td>%s%s</td><td>%s</td></tr>' % (
            e(self._uk_time(event, fmt)), pill, e(event.get("title", "")), e(confidence),
            e(category), ('<br><small>%s</small>' % e(sub)) if sub else "", e(self._channel_text(event)))

    @staticmethod
    def _today_events(day, now):
        """Today's events with live state recomputed now, not frozen at collection time."""
        if not day or day.get("date") != now.astimezone(LONDON).date().isoformat():
            return []
        out = []
        for group in day.get("sports", []):
            for category in group.get("categories", []):
                for event in category.get("events", []):
                    out.append(dict(event, live_state=linking.live_state(event, now)))
        return out

    def today(self):
        snapshot = self.store.snapshot("today")
        day = snapshot["data"] if snapshot else {}
        now = datetime.now(timezone.utc)
        body = '<h2>Live action today</h2><p>Today\'s fixtures, races and sessions (UK day), grouped by sport and competition. "Probably live" is estimated from start time and typical duration unless the provider reports live status. Channel names shown are unverified EPG matches.</p>'
        today_iso = now.astimezone(LONDON).date().isoformat()
        if day and day.get("date") != today_iso:
            return body + '<section class="card"><p class="warn">The latest collection covered %s, not today (%s). The next scheduled refresh will rebuild today\'s list, or use <strong>Refresh both engines now</strong> on the Overview page.</p></section>' % (e(day.get("date")), e(today_iso))
        if not day.get("count"):
            return body + '<section class="card"><p>No events collected for today yet. Enable sources and run a refresh.</p></section>'
        live_now = sum(linking.live_state(ev, now) in ("live", "live_probable")
                       for g in day.get("sports", []) for c in g["categories"] for ev in c["events"])
        body += '<p class="sub">%s · %d events · %d probably live now · collected %s</p>' % (
            e(day.get("date")), day.get("count", 0), live_now, e(when(day.get("generated_at"), now)))
        colgroup = '<colgroup><col class="time"><col><col><col class="chan"></colgroup>'
        head = '<table class="fixed">%s<tr><th>UK time</th><th>Event</th><th>Competition</th><th>Channel</th></tr>' % colgroup
        if day.get("featured"):
            body += '<section class="card" style="margin-bottom:14px"><h3>Featured: England, home nations &amp; PPV</h3>' + head
            body += ''.join(self._event_row(dict(ev, live_state=linking.live_state(ev, now)), "%H:%M", show_sport=True) for ev in day["featured"]) + '</table></section>'
        for group in day.get("sports", []):
            body += '<section class="card" style="margin-bottom:14px"><h3>%s <span class="pill">%d</span></h3>%s' % (e(group["label"]), group.get("count", 0), head)
            for category in group["categories"]:
                rows = category["events"]
                body += '<tr class="group"><td colspan="4">%s <small>(%d)</small></td></tr>' % (e(category["label"]), len(rows))
                body += ''.join(self._event_row(dict(ev, live_state=linking.live_state(ev, now)), "%H:%M") for ev in rows[:60])
                if len(rows) > 60:
                    body += '<tr><td colspan="4" class="help">%d more in this competition — see Sports events.</td></tr>' % (len(rows) - 60)
            body += '</table></section>'
        return body

    def events(self, query=None):
        query = query or {}
        snapshot = self.store.snapshot("sports")
        data = snapshot["data"] if snapshot else {}
        events = data.get("events", [])
        sport, category, text = query.get("sport", ""), query.get("category", ""), query.get("q", "").casefold()
        sports_present = sorted({ev.get("sport", "") for ev in events}, key=taxonomy.sport_order)
        categories_present = sorted({(ev.get("category_id", ""), "%s · %s" % (ev.get("sport_label", ""), ev.get("category_label", "")))
                                     for ev in events if not sport or ev.get("sport") == sport}, key=lambda c: c[1])
        shown = [ev for ev in events if (not sport or ev.get("sport") == sport)
                 and (not category or ev.get("category_id") == category)
                 and (not text or text in ("%s %s %s" % (ev.get("title", ""), ev.get("competition", ""), " ".join(ev.get("participants") or []))).casefold())]
        body = '<h2>Sporting events</h2><p>Independent sports fixtures, races and sessions for the next eight UK days, de-duplicated across sources. This view does not claim a broadcaster unless a separately verified source has supplied one.</p>'
        filters = '<form method="get"><input type="hidden" name="page" value="events"><div class="formrow"><div><label for="f-sport">Sport</label><select id="f-sport" name="sport"><option value="">All sports</option>%s</select></div><div><label for="f-cat">Competition</label><select id="f-cat" name="category"><option value="">All competitions</option>%s</select></div><div><label for="f-q">Team or competition</label><input id="f-q" type="text" name="q" value="%s" placeholder="e.g. England, Arsenal, Six Nations"></div><button type="submit">Filter</button></div></form>' % (
            "".join('<option value="%s" %s>%s</option>' % (e(s), "selected" if s == sport else "", e(taxonomy.SPORTS.get(s, ("Other",))[0])) for s in sports_present),
            "".join('<option value="%s" %s>%s</option>' % (e(c), "selected" if c == category else "", e(label)) for c, label in categories_present),
            e(query.get("q", "")))
        body += '<section class="card">%s<h3>%d of %d events</h3><p class="help">Updated %s · Data is private on this Home Assistant instance.</p>' % (
            filters, len(shown), len(events), e(when(snapshot["updated_at"])) if snapshot else "never")
        now = datetime.now(timezone.utc)
        body += '<table class="fixed"><colgroup><col class="time"><col><col><col class="chan"></colgroup><tr><th>UK time</th><th>Event and sources</th><th>Sport · competition</th><th>UK channel</th></tr>'
        last_day = None
        for ev in shown[:200]:
            day = self._uk_time(ev, "%A %d %B")
            if day != last_day:
                body += '<tr class="group"><td colspan="4">%s</td></tr>' % e(day)
                last_day = day
            body += self._event_row(dict(ev, live_state=linking.live_state(ev, now)), "%H:%M", show_sport=True)
        body += '</table>'
        if len(shown) > 200:
            body += '<p class="help">Showing the first 200 matching events; narrow the filter to see more.</p>'
        if not events:
            body += '<p>No events have been collected yet. Configure sources and run a refresh.</p>'
        elif not shown:
            body += '<p>No events match this filter.</p>'
        return body + '</section>'

    def guide(self):
        body = '<h2>International EPG coverage</h2><p>Private source analysis: distinguish a real 24-hour programme schedule from a feed that merely responds successfully. Canonical IDs are conservative hints; actual IPTV stream mapping remains local to B1G.</p>'
        any_source = False
        for name, (label, _) in providers.EPG.items():
            snapshot = self.store.snapshot("epg-quality:" + name)
            if not snapshot:
                continue
            any_source = True
            q = snapshot["data"]
            total = int(q.get("channels", 0))
            full = q.get("full_coverage_channels", {})
            body += '<section class="card" style="margin-bottom:14px"><h3>%s (%s)</h3>' % (e(label), e(q.get("country", "unknown")))
            horizon = q.get("horizon_hours")
            body += '<p class="sub">Analysed %s · %d channels · %d valid programmes · %d generic titles · %d invalid programmes%s</p>' % (
                e(when(q.get("analysed_at"))), total, int(q.get("valid_programmes", 0)),
                int(q.get("generic_programmes", 0)), int(q.get("invalid_programmes", 0)),
                (" · guide reaches %.0f h ahead" % horizon) if isinstance(horizon, (int, float)) else "")
            body += '<div class="grid">'
            for span in ("24h", "72h", "168h"):
                body += '<div><div class="metric">%d / %d</div><div class="help">Channels with a full %s guide</div></div>' % (
                    int(full.get(span, 0)), total, e(span))
            body += '</div>'
            families = q.get("families", {})
            if families:
                body += '<div class="divider"></div><h3>Lineup families in this guide</h3><table><tr><th>Family</th><th>Channels</th><th>Full 24h guide</th></tr>'
                for row in sorted(families.values(), key=lambda r: -r["channels"]):
                    body += '<tr><td>%s</td><td>%d</td><td>%d</td></tr>' % (e(row["label"]), int(row["channels"]), int(row["full_24h"]))
                body += '</table>'
            body += '<div class="divider"></div><h3>Channels needing attention (worst 24h gaps)</h3>'
            body += '<table><tr><th>Channel</th><th>Recognised service</th><th>24h programme coverage</th></tr>'
            for row in q.get("channels_needing_attention", []):
                body += '<tr><td>%s</td><td>%s</td><td>%s h</td></tr>' % (
                    e(row.get("name", "")), e(row.get("canonical_id") or "Needs matching"),
                    e(row.get("coverage_hours", {}).get("24h", 0)))
            body += '</table><p class="help">Programme text and channel identifiers remain private. Guide source redistribution is disabled until independently licensed.</p></section>'
        if not any_source:
            body += '<section class="card"><p>No successful EPG import yet. Enable a guide in Sources and run a refresh.</p></section>'
        return body

    def schedule(self, config):
        times = ", ".join(config["schedule"])
        text = '<h2>Scheduled provider refresh</h2><p>Times are in Europe/London and automatically follow GMT/BST. Heavy EPG import remains separate from the television interface. An unavailable source retains its previous successful snapshot.</p>'
        text += '<section class="card">' + self._form("schedule", '<label for="times">Daily refresh times (HH:MM, commas between entries)</label><input id="times" type="text" name="times" value="%s" required><p class="help">Default: 04:00, 12:00, 17:00. Limit 1–6 refresh slots per local day. Quota budgets can block individual calls. Multi-day fixture discovery runs once per day; other slots refresh today.</p><button type="submit">Save schedule</button>' % e(times)) + '</section>'
        local = datetime.now(LONDON)
        beat = self.store._get("scheduler_heartbeat")
        text += '<p class="sub">Current London time: %s · Scheduler last active: %s</p>' % (e(local.strftime("%d %b %Y, %H:%M %Z")), e(when(beat)))
        return text

    def publishing(self, config):
        github = config["github"]
        owner, repository, branch = github.get("owner") or "", github.get("repository") or "", github.get("branch") or ""
        state = self.store._get("feed_state") or {}
        preview = self.store._get("feed_preview") or {}
        approvals = list(config.get("publication_approvals", []))
        form = ('<label for="gh-owner">GitHub owner</label><input id="gh-owner" name="owner" type="text" value="%s" required>'
                '<label for="gh-repo">Separate public feed repository name</label><input id="gh-repo" name="repository" type="text" value="%s" placeholder="LiveSports-EPG" required>'
                '<label for="gh-branch">Branch</label><input id="gh-branch" name="branch" type="text" value="%s" required>'
                '<label for="gh-token">Fine-grained GitHub publishing token</label><input id="gh-token" name="token" type="password" autocomplete="new-password" placeholder="%s">'
                '<label><input type="checkbox" name="remove" value="on"> Remove saved token</label>') % (
            e(owner), e(repository), e(branch), "Saved — enter replacement only" if github.get("token") else "Token (only rights-cleared feed repository)")
        form += '<label><input type="checkbox" name="enabled" value="on" %s> Enable publishing</label>' % ("checked" if github.get("enabled") else "")
        form += '<label><input type="checkbox" name="auto_publish" value="on" %s> Publish automatically after every scheduled refresh</label><button type="submit">Save GitHub settings</button>' % ("checked" if github.get("auto_publish") else "")
        destination = "%s/%s" % (owner, repository) if owner and repository else "not set"
        published = ("Last published revision <code>%s</code> %s." % (e(state["last_revision"]), e(when(state.get("published_at"))))
                     if state.get("last_revision") else "No feed has been published from this installation yet.")
        body = '<h2>Outbound GitHub distribution</h2><p>Only SportsLiveInfo on Home Assistant will write to GitHub. B1G TVs remain read-only; no incoming connections to Home Assistant are needed.</p>'
        if owner and repository:
            body += '<p>Public data repository: <a href="https://github.com/%s/%s" rel="noopener noreferrer" target="_blank">%s</a> (branch <code>%s</code>). This is the JSON output destination, not the Home Assistant App installation repository. %s</p>' % (
                e(urllib.parse.quote(owner)), e(urllib.parse.quote(repository)), e(destination), e(branch), published)
        else:
            body += '<p>No public data repository is configured yet. %s</p>' % published
        body += '<div class="alert error">Public publishing requires documented permission to redistribute every selected source. No programme guide source has been cleared for public export; EPG copying is disabled. No sporting source has been approved by default.</div>'
        body += (
            '<section class="card" style="margin-top:16px"><h2>Set up your GitHub publishing token</h2>'
            '<p>You only need one fine-grained personal access token on this Home Assistant installation. '
            'Do not put it in GitHub files or on any of the B1G televisions.</p>'
            '<ol>'
            '<li>Open <a href="https://github.com/settings/personal-access-tokens/new" '
            'target="_blank" rel="noopener noreferrer">GitHub: Generate a fine-grained token</a> '
            '(sign in to your <strong>jimmyfazz</strong> account).</li>'
            '<li>Give it a descriptive name such as <strong>SportsLiveInfo Publisher</strong>. '
            'Set an expiry (for example 90 days); make a note to renew it before it expires.</li>'
            '<li>Choose <strong>Resource owner: jimmyfazz</strong>. Under Repository access choose '
            '<strong>Only select repositories</strong> and select <strong>LiveSports-EPG</strong> only. '
            'Do not choose All repositories or the private SportsLiveInfo source repository.</li>'
            '<li>Under Repository permissions, set <strong>Contents: Read and write</strong>. '
            'Leave other permissions at their defaults, then click <strong>Generate token</strong>.</li>'
            '<li>Copy the token from GitHub into the masked field below. '
            'Keep owner <strong>jimmyfazz</strong>, repository <strong>LiveSports-EPG</strong> '
            'and branch <strong>main</strong>. Click <strong>Save GitHub settings</strong>.</li>'
            '<li>Click <strong>Test saved GitHub connection</strong>. This checks authentication, '
            'public repository access and branch existence without creating or publishing any files. '
            'A read-only test cannot fully establish write access; this is confirmed only by a '
            'rights-approved actual publication.</li>'
            '<li>Keep <strong>Enable publishing</strong> and <strong>Publish automatically</strong> '
            'unticked until programme/event redistribution permissions have been reviewed. '
            'Later, preview the feed before enabling publishing. '
            'Only authorised source-derived data may be published.</li>'
            '</ol>'
            '<p class="help">If the token expires or is revoked, create a replacement token in GitHub '
            'and paste it here; Save changes only the provided token. The existing one is not shown '
            'after saving. Any Home Assistant backup containing tokens is sensitive.</p></section>'
        )
        body += '<section class="card" style="margin-top:16px">' + self._form("github", form) + '<div class="divider"></div><p class="help">Saved token: %s.</p>' % ("yes" if github.get("token") else "no") + '</section>'
        body += '<section class="card" style="margin-top:16px"><h3>Connection check (no upload)</h3><p>Save the token and destination first. Testing never enables publication or changes GitHub contents.</p>' + self._form("test_github", '<button class="secondary" type="submit">Test saved GitHub connection</button>') + '</section>'
        # Rights register: the only place event publication can be authorised.
        rights = '<p>Tick only sources whose terms you have reviewed and that permit public redistribution of fixture facts (teams, times, competition). A fused event is published only when <em>every</em> contributing source is approved. EPG programme text is never published.</p><div class="grid">'
        for name, (label, _, _, _) in providers.SPORTS.items():
            note = providers.SOURCE_NOTES.get(providers.SPORT_FAMILY[name], "")
            rights += '<label class="card" style="margin:0"><input type="checkbox" name="approve" value="%s" %s> <strong>%s</strong><br><small>%s</small></label>' % (
                e(name), "checked" if name in approvals else "", e(label), e(note))
        rights += '</div><label><input type="checkbox" name="attest" value="on"> I have reviewed the redistribution terms of every source ticked above.</label><button type="submit">Save publication approvals</button>'
        log = self.store._get("approval_log") or []
        last = ("Last changed %s." % e(when(log[-1]["at"]))) if log else "Never changed."
        body += '<section class="card" style="margin-top:16px"><h2>Publication rights register</h2><p class="sub">Approved now: %s. %s</p>%s</section>' % (
            e(", ".join(approvals) or "none"), last, self._form("approvals", rights))
        blockers = []
        if not github.get("enabled"):
            blockers.append("publishing is not enabled")
        if not github.get("token"):
            blockers.append("no token is saved")
        if not approvals:
            blockers.append("no source is approved in the rights register")
        if not self.store.snapshot("sports"):
            blockers.append("no sports snapshot has been collected")
        body += '<section class="card" style="margin-top:16px"><h2>B1G feed (format sli/1)</h2><p>One atomic GitHub commit per revision: taxonomy, channel registry, guide catalogue, eight daily event files, today grouping and source health, all referenced by <code>v1/manifest.json</code>. Assets are content-addressed, so TVs download only what changed. EPG programme text and unverified channel candidates are never included.</p>'
        body += '<p class="sub">Last preview: %s · Last published: %s</p>' % (
            e("%s (%s assets, %s bytes, %s events)" % (preview["revision"], preview["assets"], preview["bytes"], preview["coverage"]["events"])) if preview else "none",
            e("%s %s" % (state["last_revision"], when(state.get("published_at")))) if state.get("last_revision") else "never")
        for note in preview.get("notices", []):
            body += '<p class="warn help">%s</p>' % e(note)
        body += self._form("preview_feed", '<button class="secondary" type="submit">Build feed preview (no upload)</button>')
        if blockers:
            body += '<p class="warn help">Publishing is unavailable because %s.</p>' % e("; ".join(blockers))
        body += self._form("publish", '<button type="submit"%s>Publish feed now</button>' % (" disabled" if blockers else "")) + '</section>'
        return body

    def health(self, config=None):
        config = config or self.store.config()
        rows = self.store.recent_jobs(300)
        usage = self.store.usage()
        now = datetime.now(timezone.utc)
        body = '<h2>Provider health &amp; diagnostics</h2><p>Errors are recorded locally without API keys, programme titles or private account URLs. Home Assistant persistent notifications require a separately reviewed, least-privilege integration.</p>'
        beat = self.store._get("scheduler_heartbeat")
        stale = True
        try:
            stale = (now - datetime.fromisoformat(beat)).total_seconds() > 120
        except (TypeError, ValueError):
            pass
        body += '<section class="card"><h3>Scheduler</h3><p class="%s">Last heartbeat: %s%s</p></section>' % (
            "warn" if stale else "ok", e(when(beat, now)), " — not running or stalled" if stale else "")
        by_source = OrderedDict()
        for row in rows:
            by_source.setdefault(row["provider"], []).append(row)
        body += '<section class="card" style="margin-top:16px"><h3>Enabled sources</h3>'
        enabled = [(n, providers.SPORTS[n][0], providers.SPORTS[n][3], n) for n in providers.SPORTS if config["sports"].get(n)]
        enabled += [(n, providers.EPG[n][0], 4, "epg:" + n) for n in providers.EPG if config["epg"].get(n)]
        if enabled:
            body += '<table><tr><th>Source</th><th>Last result</th><th>Last success</th><th>Consecutive failures</th><th>Calls today</th></tr>'
            for name, label, limit, ledger in enabled:
                history = by_source.get(name, [])
                last = history[0] if history else {}
                fails = 0
                for row in history:
                    if row["state"] in ("failed", "test_failed"):
                        fails += 1
                    elif row["state"] not in ("test_ok",):
                        break
                snap = self.store.snapshot(("sports:" if name in providers.SPORTS else "epg:") + name)
                body += '<tr><td>%s</td><td class="%s">%s</td><td>%s</td><td class="%s">%d</td><td>%d / %d</td></tr>' % (
                    e(label), STATE_CLASS.get(last.get("state"), ""), e(last.get("state", "not run yet")),
                    e(when(snap["updated_at"], now)) if snap else "never", "critical" if fails >= 3 else "", fails,
                    usage.get(ledger, 0), limit)
            body += '</table>'
        else:
            body += '<p>No source is enabled.</p>'
        body += '</section><section class="card" style="margin-top:16px"><h3>Requests reserved today (UTC)</h3>'
        if usage:
            body += '<table><tr><th>Provider</th><th>Count</th></tr>' + ''.join('<tr><td>%s</td><td>%d</td></tr>' % (e(k), v) for k, v in sorted(usage.items())) + '</table>'
        else:
            body += '<p>No provider requests have been made today.</p>'
        body += '</section><section class="card" style="margin-top:16px"><h3>Last 35 operations</h3><table><tr><th>When</th><th>Source</th><th>Status</th><th>Details</th></tr>'
        for row in rows[:35]:
            body += '<tr><td>%s</td><td>%s</td><td class="%s">%s</td><td>%s</td></tr>' % (
                e(when(row["time"], now)), e(row["provider"]), STATE_CLASS.get(row["state"], ""), e(row["state"]), e(row["details"]))
        body += '</table></section>'
        return body


def serve(store, engine):
    bind = os.environ.get("SLI_BIND", "0.0.0.0")
    port = int(os.environ.get("SLI_PORT", "8099"))
    instance = ThreadingHTTPServer((bind, port), UI)
    instance.store, instance.engine, instance.flash = store, engine, _Flash()
    csrf = store._get("csrf")
    if not csrf:
        csrf = secrets.token_urlsafe(32)
        store._put("csrf", csrf)
    instance.csrf = csrf
    LOGGER.info("SportsLiveInfo Ingress HTTP ready on internal port %d", port)
    instance.serve_forever(poll_interval=0.5)
