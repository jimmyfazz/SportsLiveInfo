"""Private Home Assistant Ingress UI; no directly published Home Assistant port."""
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

from . import providers

LOGGER = logging.getLogger(__name__)

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
    return html.escape(str(value or ""), quote=True)


class UI(BaseHTTPRequestHandler):
    server_version = "SportsLiveInfo/0.1"

    def log_message(self, format, *args):
        # Never emit paths or form fields; some future auth connectors may use URLs.
        LOGGER.info("Ingress %s %s", self.command, self.client_address[0])

    def _allowed(self):
        return os.environ.get("SLI_DEV") == "1" or self.client_address[0] in ("172.30.32.2", "127.0.0.1", "::1")

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
        body = self.render(page, config, notice)
        self._headers()
        self.wfile.write(body.encode("utf-8"))

    def do_POST(self):
        if not self._allowed():
            self._headers(403)
            return
        size = int(self.headers.get("Content-Length", "0"))
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
                self.store.configure({"sports": {name: value("enabled") == "on"}})
                secret = value("key")
                if secret:
                    if len(secret) > 512:
                        raise ValueError("API key exceeds safe length")
                    self.store.configure({"keys": {name: secret}})
                if value("remove") == "on":
                    self.store.configure({"keys": {name: ""}})
                page = "sources"
            elif action == "epg":
                name = value("provider")
                if name not in providers.EPG:
                    raise ValueError("Unknown EPG source")
                self.store.configure({"epg": {name: value("enabled") == "on"}})
                page = "sources"
            elif action == "github":
                owner, repository, branch = value("owner"), value("repository"), value("branch")
                if not all(re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", k) for k in (owner, repository, branch)):
                    raise ValueError("Invalid GitHub owner, repository or branch")
                updates = {"owner": owner, "repository": repository, "branch": branch, "enabled": value("enabled") == "on"}
                if value("token"):
                    if len(value("token")) > 400:
                        raise ValueError("GitHub token exceeds safe length")
                    updates["token"] = value("token")
                if value("remove") == "on":
                    updates["token"] = ""
                self.store.configure({"github": updates})
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
                self.engine.start_collection()
                page = "dashboard"
                message = "Refresh started. Check status and source history shortly"
            elif action == "publish":
                self.engine.publish()
                page = "publishing"
                message = "GitHub commit submitted; public endpoint verification remains necessary"
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

    def render(self, page, config, notice):
        tabs = [("dashboard", "Overview"), ("sources", "Sources & API keys"), ("scheduler", "Scheduler"), ("publishing", "Publishing"), ("health", "Diagnostics")]
        head = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SportsLiveInfo</title><style>%s</style></head><body><main>' % CSS
        head += '<header><img src="icon.png" alt="SportsLiveInfo"><div><h1>SportsLiveInfo</h1><div class="sub">International EPG intelligence · Live sporting fixtures</div></div></header>'
        if not config["setup_complete"]:
            head += '<div class="alert">First-run setup: configure providers, review refresh times and optionally set a publishing destination. Credentials are stored privately in the Home Assistant App data volume.</div>'
        if notice:
            head += '<div class="alert">%s</div>' % e(notice)
        head += '<nav>' + ''.join('<a class="%s" href="?page=%s">%s</a>' % ("active" if page == key else "", e(key), e(label)) for key, label in tabs) + '</nav>'
        if page == "sources":
            body = self.sources(config)
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
        return head + body + '<div class="footer">0.1.0 · Local-first operation · No public access to Home Assistant · No TV write access to GitHub</div></main></body></html>'

    def dashboard(self, config):
        sport = self.store.snapshot("sports")
        epg = self.store.snapshot("epg")
        events = sport["data"]["events"] if sport else []
        sources = epg["data"]["sources"] if epg else []
        verified = sum(bool(evt.get("broadcast_verified")) for evt in events)
        result = '<div class="grid">'
        for title, value, desc in [("Sporting events", len(events), "Collected across enabled sources"),
                                    ("EPG source feeds", len(sources), "Private guide sources with last-good snapshots"),
                                    ("Verified TV broadcasts", verified, "No channel is fabricated from league rights"),
                                    ("API calls today", sum(self.store.usage().values()), "Local call-budget ledger; UTC day")]:
            result += '<div class="card"><div class="sub">%s</div><div class="metric">%s</div><div class="help">%s</div></div>' % (e(title), e(value), e(desc))
        result += '</div><section class="card" style="margin-top:16px"><h2>Collection status</h2>'
        result += '<p>Sports snapshot: <strong>%s</strong><br>EPG snapshot: <strong>%s</strong></p>' % (e(sport["updated_at"] if sport else "No successful collection yet"), e(epg["updated_at"] if epg else "No successful collection yet"))
        result += '<p class="warn">TV broadcaster confirmation is not yet implemented in the live adapters. All unverified sporting events are deliberately non-playable in the planned B1G feed.</p>'
        result += self._form("collect", '<button type="submit">Refresh both engines now</button>')
        result += '</section><div class="grid" style="margin-top:16px"><section class="card"><h2>Sports coverage</h2><p>%s</p></section><section class="card"><h2>EPG coverage</h2><p>%s</p></section></div>' % (
            e(", ".join(s["id"] + " (%s)" % s["events"] for s in sport["data"].get("sources", [])) if sport else "No sporting source collected yet"),
            e(", ".join(s["id"] + " (%s programmes)" % s["programmes"] for s in sources) or "No EPG source collected yet"))
        return result

    def sources(self, config):
        body = '<h2>Sporting event APIs</h2><p>Keys are entered once on Home Assistant, never on the ten televisions. Each Save preserves keys for other providers; no-key services are clearly labelled.</p><div class="grid">'
        for name, (label, url, keyname, limit) in providers.SPORTS.items():
            enabled = bool(config["sports"].get(name))
            saved = bool(config["keys"].get(keyname)) if keyname else True
            content = '<input type="hidden" name="provider" value="%s"><label><input type="checkbox" name="enabled" value="on" %s> Enabled</label>' % (e(name), "checked" if enabled else "")
            if keyname:
                content += '<p class="help">%s · configured safe daily budget: %d calls</p><label>API key (leave blank to keep saved key)</label><input type="password" name="key" autocomplete="new-password" placeholder="%s"><label><input type="checkbox" name="remove" value="on"> Remove saved key</label>' % ("Key saved" if saved else "No key configured", limit, "Saved — enter a replacement" if saved else "Enter provider key")
            else:
                content += '<p class="ok">No API key required · conservative daily budget: %d calls</p>' % limit
            content += '<button type="submit">Save this provider</button>'
            body += '<section class="card"><h3>%s</h3><p class="help">Endpoint: %s</p>%s</section>' % (e(label), e(urllib.parse.urlsplit(url).hostname), self._form("sports", content))
        body += '</div><h2 style="margin-top:28px">International television EPG sources</h2><p>Optional, private guide collection only. Public re-publication of third-party programme text is DISABLED until verified rights are available. Source quality, geography and licence restrictions vary.</p><div class="grid">'
        for name, (label, url) in providers.EPG.items():
            content = '<input type="hidden" name="provider" value="%s"><label><input type="checkbox" name="enabled" value="on" %s> Enable private guide collection</label><p class="warn help">Rights for public redistribution not established</p><button type="submit">Save this source</button>' % (e(name), "checked" if config["epg"].get(name) else "")
            body += '<section class="card"><h3>%s</h3><p class="help">Source: %s</p>%s</section>' % (e(label), e(urllib.parse.urlsplit(url).hostname), self._form("epg", content))
        return body + '</div>'

    def schedule(self, config):
        times = ", ".join(config["schedule"])
        text = '<h2>Scheduled provider refresh</h2><p>Times are in Europe/London and automatically follow GMT/BST. Heavy EPG import remains separate from the television interface. An unavailable source retains its previous successful snapshot.</p>'
        text += '<section class="card">' + self._form("schedule", '<label>Daily refresh times (HH:MM, commas between entries)</label><input type="text" name="times" value="%s" required><p class="help">Default: 04:00, 12:00, 17:00. Limit 1–6 refresh slots per local day. Quota budgets can block individual calls.</p><button type="submit">Save schedule</button>' % e(times)) + '</section>'
        local = datetime.now(ZoneInfo("Europe/London"))
        text += '<p class="sub">Current London time: %s · Timezone: Europe/London</p>' % e(local.strftime("%d %b %Y, %H:%M %Z"))
        return text

    def publishing(self, config):
        github = config["github"]
        form = '<label>GitHub owner</label><input name="owner" type="text" value="%s" required><label>Separate public feed repository name</label><input name="repository" type="text" value="%s" placeholder="SportsLiveInfoFeed" required><label>Branch</label><input name="branch" type="text" value="%s" required><label>Fine-grained GitHub publishing token</label><input name="token" type="password" autocomplete="new-password" placeholder="%s"><label><input type="checkbox" name="remove" value="on"> Remove saved token</label>' % (e(github.get("owner")), e(github.get("repository")), e(github.get("branch")), "Saved — enter replacement only" if github.get("token") else "Token (only rights-cleared feed repository)")
        form += '<label><input type="checkbox" name="enabled" value="on" %s> Enable publishing</label><button type="submit">Save GitHub settings</button>' % ("checked" if github.get("enabled") else "")
        body = '<h2>Outbound GitHub distribution</h2><p>Only SportsLiveInfo on Home Assistant will write to GitHub. B1G TVs remain read-only; no incoming connections to Home Assistant are needed.</p>'
        body += '<div class="alert error">Public publishing requires documented permission to redistribute every selected source. No programme guide source has been cleared for public export; EPG copying is disabled. No sporting source has been approved by default.</div>'
        body += '<section class="card">' + self._form("github", form) + '<div class="divider"></div><p class="help">Even after enabling publishing, a permission gate will reject an export until a source is explicitly approved in the backend rights register. Saved token: %s.</p>' % ("yes" if github.get("token") else "no") + '</section>'
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
