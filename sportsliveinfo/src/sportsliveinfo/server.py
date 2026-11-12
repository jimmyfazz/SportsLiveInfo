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

from . import __version__, providers, taxonomy

LOGGER = logging.getLogger(__name__)
LIVE_LABELS = {"live": "LIVE", "live_probable": "Probably live", "upcoming": "Upcoming", "finished": "Finished",
               "probably_finished": "Probably finished", "postponed": "Postponed", "cancelled": "Cancelled",
               "time_tbc": "Time TBC", "unknown": "Unknown"}

CSS = """
:root{color-scheme:dark;font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
  --bg:#071220;--surface:#102438;--surface2:#142d43;--border:#2a4659;
  --text:#eff7fc;--muted:#acc2d3;--accent:#67dfcb;--lime:#b9f185;--amber:#ffcf80;--red:#ffada4;
  background:var(--bg);color:var(--text)}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;min-width:320px;background:radial-gradient(ellipse at 85% -10%,#16495b 0,transparent 46%),var(--bg);line-height:1.5}
main{max-width:1340px;margin:auto;padding:24px clamp(14px,3vw,40px) 48px}
a{color:var(--accent);text-underline-offset:3px}
a:hover{text-decoration-thickness:2px}
a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible{
  outline:3px solid var(--lime);outline-offset:3px}
.skip{position:absolute;left:12px;top:-80px;z-index:100;background:var(--lime);color:#06111c;padding:12px}
.skip:focus{top:8px}
header{display:flex;align-items:center;justify-content:space-between;gap:20px;margin:0 0 22px;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:16px;min-width:0}
header img{width:60px;height:60px;object-fit:contain;filter:drop-shadow(0 5px 16px #31bda344)}
h1{font-size:clamp(24px,2.5vw,33px);letter-spacing:-.8px;line-height:1.12;margin:0}
h2{font-size:clamp(19px,2vw,23px);letter-spacing:-.25px;margin:0 0 12px}
h3{font-size:16px;margin:0 0 8px}
p{color:var(--muted);line-height:1.6;margin:8px 0 16px}
strong{color:var(--text)}
.sub,.help,small{font-size:12px;color:var(--muted)}
.sub{font-size:13px}
.mast-status{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
nav{position:sticky;top:0;z-index:10;display:flex;gap:5px;overflow-x:auto;white-space:nowrap;
  margin:0 0 26px;padding:9px;background:#0c2032f2;backdrop-filter:blur(14px);
  border:1px solid var(--border);border-radius:15px;scrollbar-width:thin}
nav a{flex:0 0 auto;color:var(--muted);border-radius:9px;padding:9px 13px;text-decoration:none;font-size:13px;font-weight:650}
nav a:hover{background:var(--surface2);color:var(--text)}
nav a.active{background:#214c54;color:#e3fff4;box-shadow:inset 0 -2px 0 var(--accent)}
.page-heading{display:flex;justify-content:space-between;gap:12px;align-items:flex-end;flex-wrap:wrap;margin-bottom:18px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,265px),1fr));gap:14px}
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,190px),1fr));gap:13px}
.card{min-width:0;padding:21px;border-radius:16px;border:1px solid var(--border);
  background:linear-gradient(160deg,#132b40,#0e2032);box-shadow:0 8px 24px #0002;overflow-x:auto}
.card-soft{background:var(--surface);border-color:#264255}
.metric-card{border-top:3px solid var(--accent)}
.metric{font-size:clamp(25px,2.7vw,36px);font-variant-numeric:tabular-nums;font-weight:750;letter-spacing:-.9px;color:var(--lime);line-height:1.3}
.pill,.state{display:inline-flex;align-items:center;padding:4px 10px;border:1px solid #326477;border-radius:100px;
  background:#163846;color:#9dece8;font-size:12px;font-weight:650;white-space:normal;gap:4px}
.state.ok{background:#183d32;border-color:#356c4d;color:#b8f9cb}
.state.warn{background:#473821;border-color:#866632;color:#ffe0a6}
.state.critical{background:#482a32;border-color:#875161;color:#ffc1bd}
.state.neutral{background:#21384b;border-color:#395267;color:#d4e0eb}
.warn{color:var(--amber)}.ok{color:var(--lime)}.critical{color:var(--red)}
label{display:block;margin:12px 0 6px;font-size:13px;font-weight:600;color:#e2f0f8}
input[type=text],input[type=password],input[type=search],select{
  width:100%;min-width:0;background:#071727;border:1px solid #426276;color:var(--text);
  padding:11px 13px;border-radius:9px;font:inherit}
input[type=checkbox]{accent-color:var(--lime);width:18px;height:18px;vertical-align:middle}
button,.button-link{display:inline-block;border:0;background:linear-gradient(110deg,#63dacc,#b6e987);color:#071b25;
  border-radius:9px;padding:10px 16px;font-size:14px;font-weight:750;cursor:pointer;margin-top:9px;
  text-decoration:none;min-height:40px}
button:hover,.button-link:hover{filter:brightness(1.08);text-decoration:none}
button.secondary,.button-link.secondary{background:#284b5d;color:#eff8fd;border:1px solid #406679}
button:disabled{opacity:.5;cursor:not-allowed}
form{margin:0 0 12px}
.formrow{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.formrow>select,.formrow>input[type=text]{flex:1 1 170px}
.divider{height:1px;background:var(--border);margin:18px 0}
.alert{padding:13px 16px;border-radius:10px;border-left:4px solid var(--accent);background:#123746;margin-bottom:17px}
.alert.error{border-color:var(--red);background:#3b2b34}
table{border-collapse:collapse;width:100%;min-width:520px;font-size:13px}
td,th{padding:11px 10px;text-align:left;border-bottom:1px solid #2b4658;overflow-wrap:anywhere;vertical-align:top}
th{color:#d2e5ed;font-size:12px;letter-spacing:.02em}
tbody tr:hover{background:#ffffff09}
table tr:last-child td{border-bottom:0}
.action-row{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.action-row .button-link{margin-top:0}
.step-list{display:grid;gap:12px;list-style:none;margin:16px 0;padding:0}
.step-list li{padding:14px 16px;background:#0b2030;border:1px solid #2a4856;border-radius:12px}
.progress-track{height:9px;border-radius:20px;overflow:hidden;background:#304557;margin:9px 0}
.progress-fill{height:100%;border-radius:inherit;background:linear-gradient(90deg,#2fc7cb,#b8f185)}
.provider-group{border:1px solid var(--border);background:#0c2132;border-radius:14px;margin:12px 0}
.provider-group>summary{cursor:pointer;padding:15px 19px;font-weight:750;list-style-position:inside}
.provider-group[open]>summary{border-bottom:1px solid var(--border)}
.provider-group>.grid{padding:14px}
.provider-group .card{box-shadow:none;padding:16px;background:#112b40}
.source-toolbar{display:flex;flex-wrap:wrap;gap:9px;margin:14px 0 18px}
.source-toolbar a{border:1px solid #3e6071;border-radius:100px;padding:8px 14px;text-decoration:none}
.source-toolbar a.active{background:#245766;border-color:#75e0ce;color:white}
.section-space{margin-top:22px}
.empty{padding:20px;border:1px dashed #466477;border-radius:12px}
.footer{margin-top:32px;padding:18px 0;border-top:1px solid var(--border);color:#a1b9c9;font-size:12px}
@media(max-width:720px){
 main{padding:14px 12px 36px}
 header{gap:12px}header img{width:45px;height:45px}
 nav{margin:0 0 18px;padding:7px;border-radius:11px}
 nav a{padding:9px 10px}
 .card{padding:15px}
 .metric{font-size:28px}
 .provider-group>.grid{padding:9px}
 .provider-group .card{padding:14px}
 .mast-status{width:100%}
}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}*{transition:none!important}}
"""


def e(value):
    """Escape user/provider data for HTML, including numeric zero values."""
    return html.escape(str(value if value is not None else ""), quote=True)


def freshness(snapshot, now=None):
    """Readable, conservative age indicator for a persisted last-good snapshot."""
    if not snapshot:
        return "Not collected", "warn"
    try:
        stamp = datetime.fromisoformat(snapshot["updated_at"])
        age = (now or datetime.now(ZoneInfo("UTC"))) - stamp
        if age.total_seconds() < -300:
            return "Clock mismatch", "warn"
        hours = max(0, int(age.total_seconds() // 3600))
        if hours < 1:
            return "Updated within 1 hour", "ok"
        if hours < 24:
            return "Updated %d hours ago" % hours, "ok"
        days = hours // 24
        return "Last updated %d days ago" % days, "warn"
    except (KeyError, ValueError, TypeError, OverflowError):
        return "Timestamp unavailable", "warn"


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
                self.store.configure({"sports": {name: value("enabled") == "on"}})
                # Keys are stored by provider account, so one API-Sports key serves every API-Sports sport.
                key_name = providers.SPORTS[name][2]
                secret = value("key")
                if secret and key_name:
                    if len(secret) > 512:
                        raise ValueError("API key exceeds safe length")
                    self.store.configure({"keys": {key_name: secret}})
                if value("remove") == "on" and key_name:
                    self.store.configure({"keys": {key_name: ""}})
                page = "sources"
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
                started = self.engine.start_collection()
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
        tabs = [("dashboard", "Overview"), ("today", "Live today"), ("events", "Sports events"),
                ("guide", "EPG coverage"), ("sources", "Sources & API keys"), ("scheduler", "Scheduler"),
                ("publishing", "Publishing"), ("health", "Diagnostics")]
        sports_enabled = sum(bool(v) for v in config["sports"].values())
        epg_enabled = sum(bool(v) for v in config["epg"].values())
        collection_active = self.engine._busy.locked()
        head = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                '<meta name="theme-color" content="#071220"><title>SportsLiveInfo</title>'
                '<style>%s</style></head><body><a class="skip" href="#content">Skip to main content</a><main>') % CSS
        head += ('<header><div class="brand"><img src="icon.png" alt="">'
                 '<div><h1>SportsLiveInfo</h1>'
                 '<div class="sub">Independent sports schedules &amp; private television guide intelligence</div>'
                 '</div></div><div class="mast-status"><span class="state %s">%s</span>'
                 '<span class="state neutral">%d sports · %d EPG sources enabled</span></div></header>') % (
                     "warn" if collection_active else ("ok" if config["setup_complete"] else "warn"),
                     "Refreshing sources" if collection_active else ("Configured" if config["setup_complete"] else "Setup required"),
                     sports_enabled, epg_enabled)
        if not config["setup_complete"]:
            head += ('<div class="alert" role="status">First-run setup: select sources, save optional API keys, '
                     'test each provider and review the schedule. Publishing remains disabled unless '
                     'you explicitly enable it and approve redistribution rights.</div>')
        if notice:
            head += '<div class="alert" role="status" aria-live="polite">%s</div>' % e(notice)
        head += ('<nav aria-label="Main navigation">' +
                 ''.join('<a %s href="?page=%s">%s</a>' % (
                     'class="active" aria-current="page"' if page == key else '',
                     e(key), e(label)) for key, label in tabs) +
                 '</nav><div id="content"></div>')
        if page == "sources":
            body = self.sources(config, query)
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
            body = self.health()
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
        events = sport["data"].get("events", []) if sport else []
        sources = epg["data"].get("sources", []) if epg else []
        day = today["data"] if today else {}
        enabled_sports = [n for n, active in config["sports"].items() if active and n in providers.SPORTS]
        enabled_epg = [n for n, active in config["epg"].items() if active and n in providers.EPG]
        missing_keys = sorted({providers.SPORTS[n][2] for n in enabled_sports
                               if providers.SPORTS[n][2] and not config["keys"].get(providers.SPORTS[n][2])})
        sport_age, sport_severity = freshness(sport)
        epg_age, epg_severity = freshness(epg)
        active = self.engine._busy.locked()
        result = '<div class="page-heading"><div><h2>Operations overview</h2><p>At-a-glance readiness, latest successful snapshots and the actions needed next.</p></div>'
        result += '<span class="state %s">%s</span></div>' % ("warn" if active else "neutral", "Collection running" if active else "Local-first · private collection")
        metrics = [
            ("Events today", day.get("count", 0), "UK calendar day · source-reported or estimated status"),
            ("Sports events", len(events), "Future event records in the current local snapshot"),
            ("EPG feeds", len(sources), "Private source feeds represented in the overview"),
            ("API calls today", sum(self.store.usage().values()), "Requests reserved in the local UTC quota ledger"),
        ]
        result += '<div class="kpi-grid">'
        for title, value, description in metrics:
            result += ('<article class="card metric-card"><div class="sub">%s</div>'
                       '<div class="metric">%s</div><div class="help">%s</div></article>') % (
                           e(title), e(value), e(description))
        result += '</div>'
        result += '<div class="grid section-space"><section class="card"><h2>System readiness</h2><ul class="step-list">'
        checks = [
            ("Initial setup", bool(config["setup_complete"]), "Complete the first-run setup", "dashboard"),
            ("Sports source selection", bool(enabled_sports), "Enable at least one sport provider", "sources"),
            ("EPG source selection", bool(enabled_epg), "Enable an authorised private EPG source", "sources"),
            ("Provider credentials", not missing_keys, "Enter keys for selected key-required providers", "sources"),
            ("Sports snapshot", bool(sport), "Run a refresh to collect sports events", "dashboard"),
            ("EPG snapshot", bool(epg), "Run a refresh to analyse programme coverage", "dashboard"),
        ]
        for label, good, action, destination in checks:
            result += ('<li><span class="state %s">%s</span> <strong>%s</strong>'
                       '<div class="help">%s</div></li>') % (
                           "ok" if good else "warn", "Ready" if good else "Needs attention",
                           e(label), "Completed" if good else (
                               '<a href="?page=%s">%s</a>' % (e(destination), e(action))))
        result += '</ul><p class="help">GitHub publishing is optional and excluded from collection readiness. '
        result += 'Only rights-approved data may be exported.</p></section>'
        result += '<section class="card"><h2>Latest snapshots</h2>'
        for title, snapshot, age, severity, destination in [
            ("Sports intelligence", sport, sport_age, sport_severity, "events"),
            ("Private EPG analysis", epg, epg_age, epg_severity, "guide"),
        ]:
            result += ('<div class="divider"></div><h3>%s</h3>'
                       '<p><span class="state %s">%s</span></p>'
                       '<p class="help">Snapshot time (UTC): %s</p>'
                       '<a href="?page=%s">Explore %s</a>') % (
                           e(title), severity, e(age), e(snapshot["updated_at"] if snapshot else "No successful refresh"),
                           e(destination), e(title))
        result += '<div class="divider"></div><h3>Refresh collection</h3>'
        result += '<p>A failed or partial provider refresh keeps the previous successful snapshot. '
        result += 'An EPG source with no current programmes cannot silently replace your guide.</p>'
        result += self._form("collect", '<button type="submit" %s>%s</button>' % (
            "disabled" if active else "", "Refresh in progress" if active else "Refresh selected sources now"))
        result += '<div class="action-row"><a class="button-link secondary" href="?page=sources">Configure sources</a>'
        result += '<a class="button-link secondary" href="?page=health">View diagnostics</a></div></section></div>'
        result += '<div class="grid section-space"><section class="card"><h2>Sports source coverage</h2>'
        result += '<p>%s</p></section><section class="card"><h2>EPG source coverage</h2><p>%s</p></section></div>' % (
            e(", ".join(str(s["id"]) + " (%s events)" % s.get("events", 0) for s in sport["data"].get("sources", []))
              if sport else "No collected sports source yet"),
            e(", ".join(str(s["id"]) + " (%s programmes)" % s.get("programmes", 0) for s in sources)
              if sources else "No collected EPG source yet"))
        result += '<p class="warn section-space">A sporting event is not a confirmed TV broadcast. '
        result += 'Event-to-channel matches remain explicitly unverified until independent broadcast evidence exists.</p>'
        return result

    def sources(self, config, query=None):
        """Operator-friendly provider catalogue; all controls remain independent HTML forms."""
        query = query or {}
        section = query.get("kind", "all")
        if section not in ("all", "sports", "epg"):
            section = "all"
        latest = {}
        for operation in self.store.recent_jobs(300):
            if operation["provider"] not in latest:
                latest[operation["provider"]] = operation

        def status(name):
            operation = latest.get(name)
            if not operation:
                return '<span class="state neutral">Not tested</span>'
            value = operation["state"]
            colour = ("ok" if value in ("ok", "test_ok", "no_events_reported") else
                      "warn" if value in ("partial", "empty", "stale", "needs_key", "test_failed",
                                          "coverage_collapse", "quota") else "critical")
            return '<span class="state %s" title="%s">%s</span>' % (
                colour, e(operation["time"]), e(value.replace("_", " ").title()))

        sports_on = sum(bool(config["sports"].get(name)) for name in providers.SPORTS)
        epg_on = sum(bool(config["epg"].get(name)) for name in providers.EPG)
        body = ('<div class="page-heading"><div><h2>Source management</h2>'
                '<p>Select only the services you need. Expand a provider family or region to configure '
                'it; independent Save and Test controls never overwrite other providers.</p></div>'
                '<span class="state neutral">%s sports · %s EPG enabled</span></div>') % (sports_on, epg_on)
        body += '<div class="source-toolbar" aria-label="Source type filters">'
        for key, label in (("all", "All sources"), ("sports", "Sports APIs"), ("epg", "Television EPG")):
            body += '<a href="?page=sources&amp;kind=%s" class="%s" %s>%s</a>' % (
                key, "active" if key == section else "", 'aria-current="page"' if key == section else "", e(label))
        body += '</div>'
        if section in ("all", "sports"):
            body += ('<h2>Sporting event APIs</h2><p>Choose free no-key sources first, then add optional '
                     'provider keys. A shared API-Sports key serves all of its sport-specific adapters; '
                     'free plans may have restricted competitions and quotas.</p>')
            families = {}
            for name in providers.SPORTS:
                families.setdefault(providers.SPORT_FAMILY.get(name, name), []).append(name)
            for family, names in families.items():
                heading = ("API-Sports · multiple sports, one saved key" if family == "api_sports" else
                           providers.SPORTS[names[0]][0])
                enabled_count = sum(bool(config["sports"].get(n)) for n in names)
                open_state = enabled_count > 0 or (not config["setup_complete"] and family == "jolpica")
                body += ('<details class="provider-group" %s><summary>%s '
                         '<span class="pill">%d / %d enabled</span></summary><div class="grid">') % (
                             "open" if open_state else "", e(heading), enabled_count, len(names))
                for name in names:
                    label, url, keyname, limit = providers.SPORTS[name]
                    enabled = bool(config["sports"].get(name))
                    saved = bool(config["keys"].get(keyname)) if keyname else True
                    note = providers.SOURCE_NOTES.get(providers.SPORT_FAMILY.get(name, name), "")
                    inner = ('<input type="hidden" name="provider" value="%s">'
                             '<label><input type="checkbox" name="enabled" value="on" %s> '
                             'Enable source</label>') % (e(name), "checked" if enabled else "")
                    if note:
                        inner += '<p class="help">%s</p>' % e(note)
                    if keyname:
                        inner += ('<span class="state %s">%s · %s</span>'
                                  '<p class="help">Conservative budget: %d requests/day</p>'
                                  '<label for="key-%s">Provider API key (optional until enabled)</label>'
                                  '<input id="key-%s" type="password" name="key" autocomplete="new-password" '
                                  'placeholder="%s"><label><input type="checkbox" name="remove" value="on"> '
                                  'Remove saved key</label>') % (
                                      "ok" if saved else "warn",
                                      "Key stored privately" if saved else "Key required", e(keyname), limit,
                                      e(name), e(name), "Saved — enter a replacement" if saved else "Enter provider key")
                    else:
                        inner += '<p class="ok help">No API key required · safe daily budget %d calls</p>' % limit
                    inner += '<button type="submit">Save provider</button>'
                    test = self._form("test_source", '<button class="secondary" type="submit">Test connection (uses quota)</button>',
                                      '<input type="hidden" name="kind" value="sports">'
                                      '<input type="hidden" name="provider" value="%s">' % e(name))
                    body += ('<article class="card card-soft"><h3>%s</h3>%s'
                             '<p class="help">Provider host: %s</p>%s%s</article>') % (
                                 e(label), status(name), e(urllib.parse.urlsplit(url).hostname),
                                 self._form("sports", inner), test)
                body += '</div></details>'
            options = config.get("options", {})
            chosen_sports = set(options.get("thesportsdb_sports", []))
            chosen_leagues = set(options.get("openligadb_leagues", []))
            option_form = '<h3>TheSportsDB sports</h3><p class="help">Each selected sport may use a daily call.</p><div class="formrow">'
            option_form += ''.join('<label><input type="checkbox" name="tsdb" value="%s" %s> %s</label>' % (
                e(item), "checked" if item in chosen_sports else "", e(item)) for item in providers.THESPORTSDB_SPORTS)
            option_form += '</div><h3>OpenLigaDB leagues</h3><div class="formrow">'
            option_form += ''.join('<label><input type="checkbox" name="old" value="%s" %s> %s</label>' % (
                e(item), "checked" if item in chosen_leagues else "", e(item)) for item in providers.OPENLIGADB_LEAGUES)
            option_form += '</div><button type="submit">Save source options</button>'
            body += '<details class="provider-group"><summary>Competition and sport selections</summary><div class="card">' + (
                self._form("options", option_form)) + '</div></details>'
        if section in ("all", "epg"):
            body += ('<div class="section-space"><h2>International television EPG sources</h2>'
                     '<p>EPG imports stay private on Home Assistant. Sources marked verify must pass '
                     'a connection test before their reliability is assumed. Public redistribution of '
                     'programme text is disabled unless rights are separately established.</p></div>')
            regions = {}
            for name, (label, _) in providers.EPG.items():
                if (label.startswith("UK ") or label.startswith("Sports ")):
                    region = "United Kingdom · sports and national guide"
                elif label.startswith("France "):
                    region = "France"
                elif label.startswith("Ireland "):
                    region = "Ireland"
                else:
                    region = label.split(" · ")[0]
                regions.setdefault(region, []).append(name)
            for region, names in regions.items():
                enabled_count = sum(bool(config["epg"].get(n)) for n in names)
                body += ('<details class="provider-group" %s><summary>%s '
                         '<span class="pill">%d / %d enabled</span></summary><div class="grid">') % (
                             "open" if enabled_count else "", e(region), enabled_count, len(names))
                for name in names:
                    label, url = providers.EPG[name]
                    inner = ('<input type="hidden" name="provider" value="%s">'
                             '<label><input type="checkbox" name="enabled" value="on" %s> '
                             'Enable private collection</label>'
                             '<p class="warn help">No public redistribution rights established</p>'
                             '<button type="submit">Save EPG source</button>') % (
                                 e(name), "checked" if config["epg"].get(name) else "")
                    check = self._form("test_source", '<button class="secondary" type="submit">Test EPG (downloads guide)</button>',
                                       '<input type="hidden" name="kind" value="epg">'
                                       '<input type="hidden" name="provider" value="%s">' % e(name))
                    quality = self.store.snapshot("epg-quality:" + name)
                    coverage = ""
                    if quality:
                        q = quality["data"]
                        coverage = '<p class="help">Most recent 24h full-guide coverage: %s / %s channels</p>' % (
                            e(q.get("full_coverage_channels", {}).get("24h", 0)), e(q.get("channels", 0)))
                    body += ('<article class="card card-soft"><h3>%s</h3>%s'
                             '<p class="help">Guide host: %s</p>%s%s%s</article>') % (
                                 e(label), status(name), e(urllib.parse.urlsplit(url).hostname),
                                 coverage, self._form("epg", inner), check)
                body += '</div></details>'
        return body

    @staticmethod
    def _uk_time(event, fmt="%d %b %H:%M %Z"):
        try:
            if event.get("start_precision") == "date_only":
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
            return "EPG match (unverified): " + ", ".join(c.get("channel_name", "") for c in candidates[:3])
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

    def today(self):
        snapshot = self.store.snapshot("today")
        day = snapshot["data"] if snapshot else {}
        body = '<h2>Live action today</h2><p>Today\'s fixtures, races and sessions (UK day), grouped by sport and competition. "Probably live" is estimated from start time and typical duration unless the provider reports live status. Channel names shown are unverified EPG matches.</p>'
        if not day.get("count"):
            return body + '<section class="card"><p>No events collected for today yet. Enable sources and run a refresh.</p></section>'
        body += '<p class="sub">%s · %s events · %s probably live · generated %s</p>' % (
            e(day.get("date")), e(day.get("count")), e(day.get("live_now", 0)), e(day.get("generated_at")))
        table_head = '<table><tr><th>UK time</th><th>Category</th><th>Event</th><th>Channel</th></tr>'
        if day.get("featured"):
            body += '<section class="card" style="margin-bottom:14px"><h3>Featured: England, home nations &amp; PPV</h3>' + table_head
            body += ''.join(self._event_row(ev, "%H:%M") for ev in day["featured"]) + '</table></section>'
        for group in day.get("sports", []):
            body += '<section class="card" style="margin-bottom:14px"><h3>%s <span class="pill">%s</span></h3>' % (e(group["label"]), e(group["count"]))
            for category in group["categories"]:
                body += '<p><strong>%s</strong> <small>(%s)</small></p>%s' % (e(category["label"]), e(category["count"]), table_head)
                body += ''.join(self._event_row(ev, "%H:%M") for ev in category["events"][:60]) + '</table>'
            body += '</section>'
        return body

    def events(self, query=None):
        query = query or {}
        snapshot = self.store.snapshot("sports")
        data = snapshot["data"] if snapshot else {}
        events = data.get("events", [])
        sport, category, text = query.get("sport", ""), query.get("category", ""), query.get("q", "").casefold()
        sports_present = sorted({ev.get("sport", "") for ev in events}, key=taxonomy.sport_order)
        categories_present = sorted({(ev.get("category_id", ""), ev.get("category_label", "")) for ev in events
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
        body += '<table><tr><th>UK start time</th><th>Category and competition</th><th>Event and sources</th><th>UK channel</th></tr>'
        body += ''.join(self._event_row(ev) for ev in shown[:200]) + '</table>'
        if len(shown) > 200:
            body += '<p class="help">Showing first 200 matching events; narrow the filter to see more.</p>'
        if not events:
            body += '<p>No events have been collected yet. Configure sources and run a refresh.</p>'
        return body + '</section>'

    def guide(self):
        body = '<h2>International EPG coverage</h2><p>Private UK and French source analysis: distinguish a real 24-hour programme schedule from a feed that merely responds successfully. Canonical IDs are conservative hints; actual IPTV stream mapping remains local to B1G.</p>'
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
            body += '</div><div class="divider"></div><h3>Channels needing attention (worst 24h gaps)</h3>'
            body += '<table><tr><th>Channel</th><th>Recognised service</th><th>24h programme coverage</th></tr>'
            for row in q.get("channels_needing_attention", []):
                body += '<tr><td>%s</td><td>%s</td><td>%s h</td></tr>' % (
                    e(row.get("name", "")), e(row.get("canonical_id") or "Needs matching"),
                    e(row.get("coverage_hours", {}).get("24h", 0)))
            body += '</table><p class="help">Programme text and channel identifiers remain private. Guide source redistribution is disabled until independently licensed.</p></section>'
        if not any_source:
            body += '<section class="card"><p>No successful EPG import yet. Enable an approved UK or French guide in Sources and run a refresh.</p></section>'
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
