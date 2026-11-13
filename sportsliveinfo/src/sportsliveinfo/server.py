"""Private Home Assistant Ingress UI; no directly published Home Assistant port."""
import base64
import hashlib
import html
import json
import logging
import os
import re
import secrets
import threading
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

from . import __version__, linking, providers, taxonomy

LOGGER = logging.getLogger(__name__)
LIVE_LABELS = {"live": "Live at refresh", "live_probable": "Probably live at refresh", "upcoming": "Upcoming", "finished": "Finished",
               "probably_finished": "Probably finished", "postponed": "Postponed", "cancelled": "Cancelled",
               "time_tbc": "Time TBC", "unknown": "Unknown"}

BULK_SELECTION_SCRIPT = """document.querySelectorAll("[data-select-all]").forEach(button => {
    button.hidden = false;
    button.addEventListener("click", () => {
        button.form.querySelectorAll('input[name="selected"]').forEach(box => { box.checked = true; });
    });
});"""
BULK_SELECTION_HASH = base64.b64encode(hashlib.sha256(BULK_SELECTION_SCRIPT.encode()).digest()).decode()


def bulk_providers(group):
    if group == "keyless_sports":
        return "sports", {name: item[0] for name, item in providers.SPORTS.items() if item[2] is None}
    if group == "epg":
        return "epg", {name: item[0] for name, item in providers.EPG.items()}
    raise ValueError("Unknown source group")


CSS = """
:root{color-scheme:dark;font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;background:#081224;color:#e8f3ff}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 90% -30%,#103b54,transparent 55%),#081224}
main{max-width:1140px;margin:auto;padding:24px 24px 50px}header{display:flex;align-items:center;gap:17px;margin-bottom:23px}header img{width:68px;height:68px;object-fit:contain}
h1{font-size:27px;letter-spacing:-.7px;margin:0}h2{font-size:18px;margin:0 0 16px}h3{font-size:16px;margin:0 0 8px}
p{line-height:1.55;margin:8px 0 15px;color:#b2c3d6}.sub{font-size:13px;color:#a5b8cc}
nav{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:24px}nav a{color:#d1e6f5;border:1px solid #29465b;border-radius:11px;padding:10px 14px;text-decoration:none}nav a:hover,nav a.active{background:#123c52;border-color:#3fb8ba}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}.card{padding:20px;border-radius:16px;border:1px solid #254157;background:#0d2034;box-shadow:0 8px 20px #0002}
.metric{font-size:32px;font-weight:700;color:#bbf977}.pill{display:inline-block;padding:4px 9px;border-radius:20px;background:#14364a;color:#85e1eb;font-size:12px}
.warn{color:#ffd68b}.ok{color:#b1ec91}.critical{color:#ffb1a2}label{display:block;margin:12px 0 6px;font-size:13px;color:#d8e8f7}
input[type=text],input[type=password],select{width:100%;background:#071627;border:1px solid #376078;color:#f4f9ff;padding:12px 13px;border-radius:8px;font:inherit}
input[type=checkbox]{accent-color:#88df88;width:18px;height:18px;vertical-align:middle}button{border:0;background:linear-gradient(110deg,#05c6cc,#a2ef59);color:#071524;border-radius:9px;padding:10px 16px;font-size:14px;font-weight:750;cursor:pointer;margin-top:10px}button:hover{filter:brightness(1.08)}button.secondary{background:#234659;color:white}
form{margin:0 0 15px}.help{font-size:12px;color:#94adbf}.formrow{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.divider{height:1px;background:#294258;margin:18px 0}
table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:9px;text-align:left;border-bottom:1px solid #244054;word-break:break-word}th{color:#b8d4e4}
.alert{padding:13px 16px;border-radius:11px;border-left:4px solid #80dfe3;background:#133043;margin-bottom:20px}.error{border-color:#ffb181;background:#38252b}
a{color:#7be1eb}small{color:#a0b8cb}.footer{margin-top:30px;color:#829db1;font-size:12px}
@media(max-width:600px){main{padding:14px}header img{width:48px;height:48px}h1{font-size:22px}.card{padding:14px}}
"""


def e(value):
    return html.escape(str("" if value is None else value), quote=True)


class UI(BaseHTTPRequestHandler):
    server_version = "SportsLiveInfo/" + __version__

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
        self.send_header("Content-Security-Policy", f"default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; script-src 'sha256-{BULK_SELECTION_HASH}'; form-action 'self'; base-uri 'none'; frame-ancestors 'self'")
        self.end_headers()

    @property
    def store(self):
        return self.server.store

    @property
    def engine(self):
        return self.server.engine

    def do_GET(self):
        if not self._allowed():
            self._headers(403)
            self.wfile.write(b"Not available outside authenticated Home Assistant Ingress")
            return
        route = urllib.parse.urlsplit(self.path)
        if route.path == "/icon.png":
            self._headers(200, "image/png")
            self.wfile.write((Path(__file__).parent / "icon.png").read_bytes())
            return
        if route.path not in ("/", ""):
            self._headers(404)
            return
        query = urllib.parse.parse_qs(route.query)
        page = query.get("page", ["dashboard"])[0]
        notice = query.get("message", [""])[0][:140]
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
        if not secrets.compare_digest(value("csrf"), self.server.csrf):
            self._headers(403)
            return
        action = value("action")
        page = "dashboard" if self.store.config()["setup_complete"] else "sources"
        message = "Settings saved"
        try:
            if action == "sports":
                name = value("provider")
                if name not in providers.SPORTS:
                    raise ValueError("Unknown sports provider")
                page = "sources"
                update = {"sports": {name: value("enabled") == "on"}}
                # One API-Sports key serves every API-Sports sport.
                key_name = providers.SPORTS[name][2]
                secret = value("key")
                if key_name:
                    if len(secret) > 512:
                        raise ValueError("API key exceeds safe length")
                    if value("remove") == "on":
                        update["keys"] = {key_name: ""}
                    elif secret:
                        update["keys"] = {key_name: secret}
                self.store.configure(update)
            elif action == "bulk_sources":
                page = "sources"
                section, allowed = bulk_providers(value("group"))
                selected = set(form.get("selected", []))
                if selected - allowed.keys():
                    raise ValueError("Selection contains a provider outside this source group")
                self.store.configure({section: {name: name in selected for name in allowed}})
                message = "Source selections saved (%d enabled)" % len(selected)
            elif action == "options":
                sports = [s for s in form.get("tsdb", []) if s in providers.THESPORTSDB_SPORTS]
                leagues = [l for l in form.get("old", []) if l in providers.OPENLIGADB_LEAGUES]
                if not sports or not leagues:
                    raise ValueError("Choose at least one TheSportsDB sport and one OpenLigaDB league")
                self.store.configure({"options": {"thesportsdb_sports": sports, "openligadb_leagues": leagues}})
                page = "sources"
            elif action == "epg":
                name = value("provider")
                if name not in providers.EPG:
                    raise ValueError("Unknown EPG source")
                self.store.configure({"epg": {name: value("enabled") == "on"}})
                page = "sources"
            elif action == "test_source":
                kind, name = value("kind"), value("provider")
                if kind not in ("sports", "epg") or name not in (providers.SPORTS if kind == "sports" else providers.EPG):
                    raise ValueError("Unknown test source")
                # One source only. No credentials or untrusted URLs enter logs.
                status = self.engine.test_source(kind, name)
                page = "sources"
                message = status
            elif action == "github":
                owner, repository, branch = value("owner"), value("repository"), value("branch")
                if not all(re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", k) for k in (owner, repository, branch)):
                    raise ValueError("Invalid GitHub owner, repository or branch")
                updates = {"owner": owner, "repository": repository, "branch": branch, "enabled": value("enabled") == "on",
                           "auto_publish": value("auto_publish") == "on"}
                if value("token"):
                    if len(value("token")) > 400:
                        raise ValueError("GitHub token exceeds safe length")
                    updates["token"] = value("token")
                if value("remove") == "on":
                    updates["token"] = ""
                self.store.configure({"github": updates})
                page = "publishing"
            elif action == "test_github":
                # Authenticate and inspect the SAVED destination; never commit.
                # Saving a token and testing its connection are separate actions.
                message = self.engine.test_github_destination()
                page = "publishing"
            elif action == "schedule":
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
                page = "scheduler"
            elif action == "finish":
                self.store.configure({"setup_complete": True})
                page = "dashboard"
                message = "First-run setup complete; collector is ready"
            elif action == "collect":
                if not self.store.config()["setup_complete"]:
                    raise ValueError("Finish initial setup first")
                started = self.engine.start_collection(value("scope") or "both")
                page = "dashboard"
                message = "Refresh started. Check source history shortly" if started else "A refresh is already running"
            elif action == "publish":
                revision = self.engine.publish()
                page = "publishing"
                message = "Feed %s committed atomically; public endpoint verification remains necessary" % revision
            elif action == "preview_feed":
                manifest = self.engine.preview_feed()
                page = "publishing"
                message = "Feed preview %s built locally (%d assets); nothing uploaded" % (manifest["revision"], len(manifest["assets"]))
            else:
                raise ValueError("Unsupported action")
        except (ValueError, RuntimeError) as exc:
            # Render only own controlled errors, not upstream URLs or secret-bearing exceptions.
            message = str(exc)[:140]
        url = "?page=%s&message=%s" % (urllib.parse.quote(page), urllib.parse.quote(message))
        self.send_response(303)
        self.send_header("Location", url)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _form(self, action, inner, extra=""):
        return '<form method="post"><input type="hidden" name="csrf" value="%s"><input type="hidden" name="action" value="%s">%s%s</form>' % (e(self.server.csrf), e(action), extra, inner)

    def render(self, page, config, notice, query=None):
        query = query or {}
        tabs = [("dashboard", "Overview"), ("today", "Live today"), ("sources", "Sources & API keys"), ("events", "Sports events"), ("guide", "EPG coverage"), ("scheduler", "Scheduler"), ("publishing", "Publishing"), ("health", "Diagnostics")]
        head = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SportsLiveInfo</title><style>%s</style></head><body><main>' % CSS
        head += '<header><img src="icon.png" alt="SportsLiveInfo"><div><h1>SportsLiveInfo</h1><div class="sub">International EPG intelligence · Live sporting fixtures</div></div></header>'
        if not config["setup_complete"]:
            head += '<div class="alert">First-run setup: configure providers, review refresh times and optionally set a publishing destination. Credentials are stored privately in the Home Assistant App data volume.</div>'
        if notice:
            head += '<div class="alert">%s</div>' % e(notice)
        head += '<nav>' + ''.join('<a class="%s" href="?page=%s">%s</a>' % ("active" if page == key else "", e(key), e(label)) for key, label in tabs) + '</nav>'
        if page == "sources":
            body = self.sources(config)
        elif page == "today":
            body = self.today(query)
        elif page == "events":
            body = self.events(query)
        elif page == "guide":
            body = self.guide()
        elif page == "scheduler":
            body = self.schedule(config)
        elif page == "publishing":
            body = self.publishing(config)
        elif page == "health":
            body = self.health()
        else:
            body = self.dashboard(config)
        if not config["setup_complete"]:
            body += '<section class="card" style="margin-top:18px"><h2>Complete first-run setup</h2><p>You can return later to change individual suppliers and the schedule. The wizard will not show again automatically after finishing.</p>'
            body += self._form("finish", '<button type="submit">Finish setup</button>') + '</section>'
        return head + body + '<div class="footer">%s · Local-first operation · No public access to Home Assistant · No TV write access to GitHub</div></main></body></html>' % e(__version__)

    def dashboard(self, config):
        snapshots = self.store.read_snapshots(products=("sports", "epg", "today"))
        sport, epg, today = (snapshots.get(name) for name in ("sports", "epg", "today"))
        events = sport["data"]["events"] if sport else []
        sources = epg["data"]["sources"] if epg else []
        day = today["data"] if today else {}
        candidates = sum(e.get("broadcast_status", "none") != "none" for e in events)
        result = '<div class="grid">'
        for title, value, desc in [("Events today", day.get("count", 0), "%s live or probably live at refresh · %s featured (England, home nations, PPV)" % (day.get("live_now", 0), len(day.get("featured", [])))),
                                    ("Sporting events (8 days)", len(events), "De-duplicated across enabled sources"),
                                    ("EPG source feeds", len(sources), "Private guide sources with last-good snapshots"),
                                    ("EPG channel candidates", candidates, "Unverified guide matches; no channel is fabricated from league rights"),
                                    ("API calls today", sum(self.store.usage().values()), "Local call-budget ledger; UTC day")]:
            result += '<div class="card"><div class="sub">%s</div><div class="metric">%s</div><div class="help">%s</div></div>' % (e(title), e(value), e(desc))
        result += '</div><section class="card" style="margin-top:16px"><h2>Collection status</h2>'
        result += '<p>Sports snapshot: <strong>%s</strong><br>EPG snapshot: <strong>%s</strong></p>' % (e(sport["updated_at"] if sport else "No successful collection yet"), e(epg["updated_at"] if epg else "No successful collection yet"))
        jobs = self.store.recent_jobs(1, provider="collector")
        if jobs:
            job = jobs[0]
            result += '<p>Latest collection activity: <strong>%s</strong> · %s%s</p>' % (
                e(job["state"].replace("_", " ").capitalize()), e(job["time"]),
                " · " + e(job["details"]) if job["details"] else "")
        result += '<p class="warn">TV broadcaster confirmation is not yet implemented in the live adapters. All unverified sporting events are deliberately non-playable in the planned B1G feed.</p>'
        result += self._form("collect", '<div class="formrow">'
                             '<button type="submit" name="scope" value="both">Refresh both engines now</button>'
                             '<button type="submit" class="secondary" name="scope" value="sports">Refresh sports</button>'
                             '<button type="submit" class="secondary" name="scope" value="epg">Refresh EPG</button>'
                             '</div>')
        result += '</section><div class="grid" style="margin-top:16px"><section class="card"><h2>Sports coverage</h2><p>%s</p></section><section class="card"><h2>EPG coverage</h2><p>%s</p></section></div>' % (
            e(", ".join(s["id"] + " (%s)" % s["events"] for s in sport["data"].get("sources", [])) if sport else "No sporting source collected yet"),
            e(", ".join(s["id"] + " (%s programmes)" % s["programmes"] for s in sources) or "No EPG source collected yet"))
        return result

    def _bulk_sources(self, config, group, title, help_text):
        section, options = bulk_providers(group)
        content = '<p>%s</p>' % e(help_text)
        content += "".join(
            '<label><input type="checkbox" name="selected" value="%s"%s> %s</label>' % (
                e(name), " checked" if config[section].get(name) else "", e(label))
            for name, label in options.items()
        )
        content += ('<button type="button" class="secondary" data-select-all hidden>Tick all</button> '
                    '<button type="submit">Save selected sources</button>')
        form = self._form("bulk_sources", content, '<input type="hidden" name="group" value="%s">' % e(group))
        return '<section class="card"><h3>%s</h3>%s</section>' % (e(title), form)

    @staticmethod
    def _source_status(snapshot, job, remaining):
        result = '<p class="help">Last successful refresh: %s · %s requests remaining today (UTC)</p>' % (
            e(snapshot["updated_at"] if snapshot else "None"), e(remaining))
        if job:
            result += '<p class="help">Latest activity: %s · %s%s</p>' % (
                e(job["state"].replace("_", " ")), e(job["time"]),
                " · " + e(job["details"]) if job["details"] else "")
        return result

    def sources(self, config):
        snapshots = self.store.read_snapshots(timestamps_only=(
            *("sports:" + name for name in providers.SPORTS), *("epg:" + name for name in providers.EPG),
        ))
        usage = self.store.usage()
        latest = {}
        for job in self.store.recent_jobs(300):
            latest.setdefault(job["provider"], job)
        body = '<h2>Sporting event APIs</h2><p>Keys are entered once on Home Assistant, never on the ten televisions. Each Save preserves keys for other providers; no-key services are clearly labelled. One API-Sports key serves every API-Sports sport (each sport has its own free daily allowance).</p><div class="grid">'
        body += self._bulk_sources(config, "keyless_sports", "Sports providers without API keys",
                                   "Choose sources individually or tick all, then save the group once.")
        for name, (label, url, keyname, limit) in providers.SPORTS.items():
            note = providers.SOURCE_NOTES.get(providers.SPORT_FAMILY[name], "")
            content = '<p class="help">%s</p>' % e(note) if note else ""
            if keyname:
                enabled = bool(config["sports"].get(name))
                saved = bool(config["keys"].get(keyname))
                content += '<input type="hidden" name="provider" value="%s"><label><input type="checkbox" name="enabled" value="on" %s> Enabled</label>' % (e(name), "checked" if enabled else "")
                content += '<p class="help">%s (%s) · configured safe daily budget: %d calls</p><label>API key (leave blank to keep saved key)</label><input type="password" name="key" autocomplete="new-password" placeholder="%s"><label><input type="checkbox" name="remove" value="on"> Remove saved key</label>' % ("Key saved" if saved else "No key configured", e(keyname), limit, "Saved — enter a replacement" if saved else "Enter provider key")
                content += '<button type="submit">Save this provider</button>'
                content = self._form("sports", content)
            else:
                content += '<p class="ok">No API key required · conservative daily budget: %d calls</p>' % limit
            test_button = self._form("test_source", '<button class="secondary" type="submit">Test connection (uses 1 quota call)</button>',
                '<input type="hidden" name="kind" value="sports"><input type="hidden" name="provider" value="%s">' % e(name))
            body += '<section class="card"><h3>%s</h3><p class="help">Endpoint: %s</p>%s%s</section>' % (
                e(label), e(urllib.parse.urlsplit(url).hostname), self._source_status(
                    snapshots.get("sports:" + name), latest.get(name), max(0, limit - usage.get(name, 0))
                ) + content, test_button)
        options = config.get("options", {})
        chosen_sports, chosen_leagues = set(options.get("thesportsdb_sports", [])), set(options.get("openligadb_leagues", []))
        option_form = '<h3>TheSportsDB sports (one call per sport per day)</h3><div class="formrow">'
        option_form += ''.join('<label><input type="checkbox" name="tsdb" value="%s" %s> %s</label>' % (e(s), "checked" if s in chosen_sports else "", e(s)) for s in providers.THESPORTSDB_SPORTS)
        option_form += '</div><h3>OpenLigaDB leagues</h3><div class="formrow">'
        option_form += ''.join('<label><input type="checkbox" name="old" value="%s" %s> %s</label>' % (e(l), "checked" if l in chosen_leagues else "", e(l)) for l in providers.OPENLIGADB_LEAGUES)
        option_form += '</div><button type="submit">Save source options</button>'
        body += '</div><section class="card" style="margin-top:16px"><h2>Source options</h2>%s</section>' % self._form("options", option_form)
        body += '<h2 style="margin-top:28px">International television EPG sources</h2><p>Sources marked "verify" use a URL pattern that must pass Test EPG first. Optional, private guide collection only. Public re-publication of third-party programme text is DISABLED until verified rights are available. Source quality, geography and licence restrictions vary.</p><div class="grid">'
        body += self._bulk_sources(config, "epg", "Private EPG guides",
                                   "Test unfamiliar guides before enabling them. Saving makes no provider requests.")
        for name, (label, url) in providers.EPG.items():
            test_button = self._form("test_source", '<button class="secondary" type="submit">Test EPG (downloads guide)</button>',
                '<input type="hidden" name="kind" value="epg"><input type="hidden" name="provider" value="%s">' % e(name))
            body += '<section class="card"><h3>%s</h3><p class="help">Source: %s</p>%s%s</section>' % (
                e(label), e(urllib.parse.urlsplit(url).hostname), self._source_status(
                    snapshots.get("epg:" + name), latest.get(name),
                    max(0, providers.EPG_DAILY_REQUEST_LIMIT - usage.get("epg:" + name, 0)),
                ), test_button)
        return body + '</div><script>' + BULK_SELECTION_SCRIPT + '</script>'

    @staticmethod
    def _uk_time(event, fmt="%d %b %H:%M %Z"):
        try:
            if event.get("start_precision") in linking.UNCONFIRMED_START_PRECISIONS:
                return datetime.fromisoformat(event["start_utc"]).astimezone(ZoneInfo("Europe/London")).strftime("%d %b") + " (time TBC)"
            return datetime.fromisoformat(event["start_utc"]).astimezone(ZoneInfo("Europe/London")).strftime(fmt)
        except (ValueError, KeyError, TypeError):
            return "Unconfirmed"

    @staticmethod
    def _channel_text(event):
        if event.get("broadcast_verified"):
            return ", ".join(str(c.get("name", "")) for c in event.get("broadcasts", []) if isinstance(c, dict)) or "Verified"
        candidates = event.get("broadcast_candidates") or []
        if candidates:
            names = []
            for candidate in candidates[:3]:
                name = candidate.get("channel_name", "")
                market = candidate.get("canonical_channel_id", "").partition(".")[0].upper()
                names.append(f"{name} ({market})" if market and market != "GB" else name)
            return "EPG match (unverified): " + ", ".join(names)
        return "Not verified"

    def _event_row(self, event, fmt="%d %b %H:%M %Z"):
        sources = event.get("sources") or [event.get("source_id", "")]
        confidence = "%s · %s" % (event.get("fixture_confidence", "reported"), ", ".join(sources))
        if event.get("start_conflict"):
            confidence += " · start time disagreement"
        state = LIVE_LABELS.get(event.get("live_state", ""), "")
        return '<tr><td>%s%s</td><td>%s<br><small>%s</small></td><td>%s<br><small>%s</small></td><td>%s</td></tr>' % (
            e(self._uk_time(event, fmt)), ('<br><span class="pill">%s</span>' % e(state)) if state else "",
            e(event.get("category_label") or event.get("sport", "")), e(event.get("competition", "")),
            e(event.get("title", "")), e(confidence), e(self._channel_text(event)))

    def today(self, query=None):
        snapshot = self.store.snapshot("today")
        day = snapshot["data"] if snapshot else {}
        body = '<h2>Live action today</h2><p>Fixtures, races and sessions for the UK day. Statuses reflect the refresh time below. Channel suggestions are unverified.</p>'
        if not day.get("count"):
            return body + '<section class="card"><p>No events collected for today yet. Enable sources and run a refresh.</p></section>'
        body += '<p class="sub">%s · %s events · %s live or probably live at refresh · generated %s</p>' % (
            e(day.get("date")), e(day.get("count")), e(day.get("live_now", 0)), e(day.get("generated_at")))
        today = datetime.now(ZoneInfo("Europe/London")).date().isoformat()
        if day.get("date") and day["date"] != today:
            body += '<p class="warn">Showing the saved schedule for %s. Refresh sports to update today’s list.</p>' % e(day["date"])
        groups = day.get("sports", [])
        sport = (query or {}).get("sport", "")
        if sport not in {group["sport"] for group in groups}:
            sport = ""
        options = "".join('<option value="%s"%s>%s</option>' % (
            e(group["sport"]), " selected" if group["sport"] == sport else "", e(group["label"]))
            for group in groups)
        body += ('<form method="get"><input type="hidden" name="page" value="today">'
                 '<label for="today-sport">Sport</label><select id="today-sport" name="sport">'
                 '<option value="">All sports</option>%s</select><button type="submit">Filter</button></form>') % options

        featured = [event for event in day.get("featured", []) if not sport or event.get("sport") == sport]
        if featured:
            body += '<section class="card" style="margin-bottom:14px"><h3>Featured: England, home nations &amp; PPV</h3>'
            body += self._today_rows(featured) + '</section>'
        for group in groups:
            if sport and group["sport"] != sport:
                continue
            body += '<section class="card" style="margin-bottom:14px"><h3>%s <span class="pill">%s</span></h3>' % (
                e(group["label"]), e(group["count"]))
            for category in group["categories"]:
                label = "Other competitions" if category["id"] == group["sport"] + ".other" else category["label"]
                body += '<p><strong>%s</strong> <small>(%s)</small></p>%s' % (
                    e(label), e(category["count"]), self._today_rows(category["events"]))
            body += '</section>'
        return body

    def _today_rows(self, events):
        table_head = '<table><tr><th>UK time</th><th>Category</th><th>Event</th><th>Channel</th></tr>'
        closed = {"finished", "probably_finished", "postponed", "cancelled"}
        live = {"live", "live_probable"}
        active = sorted((event for event in events if event.get("live_state") not in closed),
                        key=lambda event: event.get("live_state") not in live)
        ended = [event for event in events if event.get("live_state") in closed]
        body = ""
        for rows, collapsed in ((active, False), (ended, True)):
            if not rows:
                continue
            if collapsed:
                body += '<details><summary>Finished, postponed or cancelled (%s)</summary>' % e(len(rows))
            body += table_head + ''.join(self._event_row(event, "%H:%M") for event in rows[:60]) + '</table>'
            if len(rows) > 60:
                body += '<p class="help">Showing 60 of %s events. See Sports events for more.</p>' % e(len(rows))
            if collapsed:
                body += '</details>'
        return body

    def events(self, query=None):
        query = query or {}
        snapshot = self.store.snapshot("sports")
        data = snapshot["data"] if snapshot else {}
        events = data.get("events", [])
        sport, category, text = query.get("sport", ""), query.get("category", ""), query.get("q", "").casefold()
        sports_present = sorted({ev.get("sport", "") for ev in events}, key=taxonomy.sport_order)
        categories_present = sorted({(ev.get("category_id", ""),
                                      "Other competitions" if ev.get("category_id") == ev.get("sport", "") + ".other"
                                      else ev.get("category_label", "")) for ev in events
                                     if not sport or ev.get("sport") == sport}, key=lambda c: c[1])
        shown = [ev for ev in events if (not sport or ev.get("sport") == sport)
                 and (not category or ev.get("category_id") == category)
                 and (not text or text in ("%s %s" % (ev.get("title", ""), ev.get("competition", ""))).casefold())]
        body = '<h2>Sporting events</h2><p>Independent sports fixtures, races and sessions for the next eight UK days, de-duplicated across sources. This view does not claim a broadcaster unless a separately verified source has supplied one.</p>'
        filters = '<form method="get"><input type="hidden" name="page" value="events"><div class="formrow"><select name="sport"><option value="">All sports</option>%s</select><select name="category"><option value="">All competitions</option>%s</select><input type="text" name="q" value="%s" placeholder="Team or competition"><button type="submit">Filter</button></div></form>' % (
            "".join('<option value="%s" %s>%s</option>' % (e(s), "selected" if s == sport else "", e(taxonomy.SPORTS.get(s, ("Other",))[0])) for s in sports_present),
            "".join('<option value="%s" %s>%s</option>' % (e(c), "selected" if c == category else "", e(label)) for c, label in categories_present),
            e(query.get("q", "")))
        body += '<section class="card">%s<h3>%s of %s events</h3><p class="help">%s · Data is private on this Home Assistant instance.</p>' % (
            filters, e(len(shown)), e(len(events)), e(snapshot["updated_at"] if snapshot else "No sporting snapshot yet"))
        body += '<table><tr><th>UK start time</th><th>Category and competition</th><th>Event and sources</th><th>Channel</th></tr>'
        body += ''.join(self._event_row(ev) for ev in shown[:200]) + '</table>'
        if len(shown) > 200:
            body += '<p class="help">Showing first 200 matching events; narrow the filter to see more.</p>'
        if not events:
            body += '<p>No events have been collected yet. Configure sources and run a refresh.</p>'
        return body + '</section>'

    def guide(self):
        body = '<h2>International EPG coverage</h2><p>Private guide analysis: distinguish a real 24-hour programme schedule from a feed that merely responds successfully. Canonical IDs are conservative hints; actual IPTV stream mapping remains local to B1G.</p>'
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
            body += '<p class="sub">Last analysis: %s · %s channels · %s valid programmes · %s generic titles · %s invalid programmes</p>' % (
                e(q.get("analysed_at")), e(total), e(q.get("valid_programmes", 0)),
                e(q.get("generic_programmes", 0)), e(q.get("invalid_programmes", 0)))
            body += '<div class="grid">'
            for horizon in ("24h", "72h", "168h"):
                body += '<div><div class="metric">%s / %s</div><div class="help">Channels with a full %s guide</div></div>' % (
                    e(full.get(horizon, 0)), e(total), e(horizon))
            families = q.get("families", {})
            if families:
                body += '</div><div class="divider"></div><h3>Lineup families in this guide</h3><table><tr><th>Family</th><th>Channels</th><th>Full 24h guide</th></tr>'
                for row in sorted(families.values(), key=lambda r: -r["channels"]):
                    body += '<tr><td>%s</td><td>%s</td><td>%s</td></tr>' % (e(row["label"]), e(row["channels"]), e(row["full_24h"]))
                body += '</table><div>'
            body += '</div><div class="divider"></div><h3>24-hour schedule gaps</h3>'
            # Match the full-coverage threshold used in the guide analysis.
            gaps = [row for row in q.get("channels_needing_attention", [])
                    if row.get("coverage_hours", {}).get("24h", 0) < 23.9]
            if gaps:
                body += '<table><tr><th>Channel</th><th>Recognised service</th><th>24h programme coverage</th></tr>'
                for row in gaps:
                    body += '<tr><td>%s</td><td>%s</td><td>%s h</td></tr>' % (
                        e(row.get("name", "")), e(row.get("canonical_id") or "Needs matching"),
                        e(row.get("coverage_hours", {}).get("24h", 0)))
                body += '</table>'
            elif full.get("24h") == total:
                body += '<p>All channels meet the 24-hour coverage threshold.</p>'
            unmatched = q.get("unmatched_canonical_channels")
            if unmatched is not None:
                body += '<p>Channels without a recognised service ID: %s / %s.</p>' % (e(unmatched), e(total))
            body += '<p class="help">Programme text and channel identifiers remain private. Guide source redistribution is disabled until independently licensed.</p></section>'
        if not any_source:
            body += '<section class="card"><p>No successful EPG import yet. Enable an approved guide in Sources and run a refresh.</p></section>'
        return body

    def schedule(self, config):
        times = ", ".join(config["schedule"])
        text = '<h2>Scheduled provider refresh</h2><p>Times are in Europe/London and automatically follow GMT/BST. Heavy EPG import remains separate from the television interface. An unavailable source retains its previous successful snapshot.</p>'
        text += '<section class="card">' + self._form("schedule", '<label>Daily refresh times (HH:MM, commas between entries)</label><input type="text" name="times" value="%s" required><p class="help">Default: 04:00, 12:00, 17:00. Limit 1–6 refresh slots per local day. Quota budgets can block individual calls.</p><button type="submit">Save schedule</button>' % e(times)) + '</section>'
        local = datetime.now(ZoneInfo("Europe/London"))
        text += '<p class="sub">Current London time: %s · Timezone: Europe/London</p>' % e(local.strftime("%d %b %Y, %H:%M %Z"))
        return text

    def publishing(self, config):
        github = config["github"]
        form = '<label>GitHub owner</label><input name="owner" type="text" value="%s" required><label>Separate public feed repository name</label><input name="repository" type="text" value="%s" placeholder="LiveSports-EPG" required><label>Branch</label><input name="branch" type="text" value="%s" required><label>Fine-grained GitHub publishing token</label><input name="token" type="password" autocomplete="new-password" placeholder="%s"><label><input type="checkbox" name="remove" value="on"> Remove saved token</label>' % (e(github.get("owner")), e(github.get("repository")), e(github.get("branch")), "Saved — enter replacement only" if github.get("token") else "Token (only rights-cleared feed repository)")
        form += '<label><input type="checkbox" name="enabled" value="on" %s> Enable publishing</label>' % ("checked" if github.get("enabled") else "")
        form += '<label><input type="checkbox" name="auto_publish" value="on" %s> Publish automatically after every scheduled refresh</label><button type="submit">Save GitHub settings</button>' % ("checked" if github.get("auto_publish") else "")
        body = '<h2>Outbound GitHub distribution</h2><p>Only SportsLiveInfo on Home Assistant will write to GitHub. B1G TVs remain read-only; no incoming connections to Home Assistant are needed.</p><p>Confirmed public data repository: <a href="https://github.com/jimmyfazz/LiveSports-EPG" rel="noopener noreferrer" target="_blank">jimmyfazz/LiveSports-EPG</a>. This is the JSON output destination, not the Home Assistant App installation repository. No feed has been published yet.</p>'
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
        body += '<section class="card">' + self._form("github", form) + '<div class="divider"></div><p class="help">Even after enabling publishing, a permission gate will reject an export until a source is explicitly approved in the backend rights register. Saved token: %s.</p>' % ("yes" if github.get("token") else "no") + '</section>'
        body += '<section class="card" style="margin-top:16px"><h3>Connection check (no upload)</h3><p>Save the token and destination first. Testing never enables publication or changes GitHub contents.</p>' + self._form("test_github", '<button class="secondary" type="submit">Test saved GitHub connection</button>') + '</section>'
        preview = self.store._get("feed_preview") or {}
        state = self.store._get("feed_state") or {}
        body += '<section class="card" style="margin-top:16px"><h2>B1G feed (format sli/1)</h2><p>One atomic GitHub commit per revision: taxonomy, channel registry, guide catalogue, eight daily event files, today grouping and source health, all referenced by <code>v1/manifest.json</code>. Assets are content-addressed, so TVs download only what changed. EPG programme text and unverified channel candidates are never included.</p>'
        body += '<p class="sub">Last preview: %s · Last published: %s</p>' % (
            e("%s (%s assets, %s bytes, %s events)" % (preview["revision"], preview["assets"], preview["bytes"], preview["coverage"]["events"])) if preview else "none",
            e("%s at %s" % (state["last_revision"], state.get("published_at"))) if state.get("last_revision") else "never")
        for note in preview.get("notices", []):
            body += '<p class="warn help">%s</p>' % e(note)
        body += self._form("preview_feed", '<button class="secondary" type="submit">Build feed preview (no upload)</button>')
        body += self._form("publish", '<button type="submit">Publish feed now</button>') + '</section>'
        return body

    def health(self):
        rows = self.store.recent_jobs(35)
        usage = self.store.usage()
        body = '<h2>Provider health & diagnostics</h2><p>Errors are recorded locally without API keys, programme titles or private account URLs. Repeat failures remain in the history; Home Assistant persistent notifications require a separately reviewed, least-privilege integration.</p>'
        body += '<section class="card"><h3>Requests reserved today (UTC)</h3><table><tr><th>Provider</th><th>Count</th></tr>'
        for k, v in sorted(usage.items()):
            body += '<tr><td>%s</td><td>%s</td></tr>' % (e(k), e(v))
        body += '</table></section><section class="card" style="margin-top:16px"><h3>Last 35 operations</h3><table><tr><th>Time (UTC)</th><th>Source</th><th>Status</th><th>Details</th></tr>'
        for row in rows:
            body += '<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % tuple(e(row[k]) for k in ("time", "provider", "state", "details"))
        body += '</table></section>'
        return body


def serve(store, engine):
    bind = os.environ.get("SLI_BIND", "0.0.0.0")
    port = int(os.environ.get("SLI_PORT", "8099"))
    instance = ThreadingHTTPServer((bind, port), UI)
    instance.store, instance.engine = store, engine
    csrf = store._get("csrf")
    if not csrf:
        csrf = secrets.token_urlsafe(32)
        store._put("csrf", csrf)
    instance.csrf = csrf
    LOGGER.info("SportsLiveInfo Ingress HTTP ready on internal port %d", port)
    instance.serve_forever(poll_interval=0.5)
