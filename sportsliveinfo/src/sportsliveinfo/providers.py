"""Small audited provider adapters. No arbitrary-user URL fetch or credential logging."""
import gzip
import hashlib
import io
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone

# Sources whose terms have not been verified for public republication are LOCAL ONLY.
# Every EPG source is disabled by default; URLs marked "verify" must pass the
# Ingress "Test EPG" button before being enabled.
# Retired 13 Nov 2026: fr_programmetv, fr_telerama, iptvorg_sky_uk, iptvorg_foxtel_au. iptv-org no longer
# hosts pre-built guides (HTTP 404 from the collector); iptv-epg.org and EPGShare cover the same markets.
EPG = {
    "farleyflex": ("UK sports · farleyflex", "https://raw.githubusercontent.com/farleyflex/epg-guide/main/epg.xml"),
    "uk_freeview": ("UK free-to-air · Freeview-EPG (dp247)", "https://raw.githubusercontent.com/dp247/Freeview-EPG/master/epg.xml"),
    "epgshare_uk": ("UK broad · EPG Share UK1 (verify)", "https://epgshare01.online/epgshare01/epg_ripper_UK1.xml.gz"),
    "epgshare_ie": ("Ireland · EPG Share IE1 (verify)", "https://epgshare01.online/epgshare01/epg_ripper_IE1.xml.gz"),
    "epgshare_fr": ("France broad · EPG Share FR1 (verify)", "https://epgshare01.online/epgshare01/epg_ripper_FR1.xml.gz"),
    "fr_xmltv": ("France · XMLTV France (racacax/XML-TV-Fr)", "https://xmltvfr.fr/xmltv/xmltv_fr.xml.gz"),
    # Feeds already offered by the B1G Android backup-guide list (SkyGuideScene.backupFeeds).
    "epgtalk_uk": ("UK national · EPGTalk (B1G suggested feed)", "https://raw.githubusercontent.com/acidjesuz/EPGTalk/master/UK_guide.xml.gz"),
    "epgtalk_sports": ("Sports · EPGTalk (B1G suggested feed)", "https://raw.githubusercontent.com/acidjesuz/EPGTalk/master/Sports_guide.xml.gz"),
    "iptv_epg_fr": ("France · IPTV-EPG.org (B1G; terms not explicit)", "https://iptv-epg.org/files/epg-fr.xml.gz"),
    "epgshare_us": ("United States · EPG Share US2", "https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz"),
    "epgshare_us_sports": ("United States sports · EPG Share US SPORTS1", "https://epgshare01.online/epgshare01/epg_ripper_US_SPORTS1.xml.gz"),
    "iptv_epg_gb": ("UK broad · IPTV-EPG.org", "https://iptv-epg.org/files/epg-gb.xml.gz"),
    "iptv_epg_au": ("Australia · IPTV-EPG.org", "https://iptv-epg.org/files/epg-au.xml.gz"),
    "iptv_epg_de": ("Germany · IPTV-EPG.org", "https://iptv-epg.org/files/epg-de.xml.gz"),
    "iptv_epg_it": ("Italy · IPTV-EPG.org", "https://iptv-epg.org/files/epg-it.xml.gz"),
    "iptv_epg_es": ("Spain · IPTV-EPG.org", "https://iptv-epg.org/files/epg-es.xml.gz"),
    "iptv_epg_nl": ("Netherlands · IPTV-EPG.org", "https://iptv-epg.org/files/epg-nl.xml.gz"),
    "iptv_epg_ca": ("Canada · IPTV-EPG.org", "https://iptv-epg.org/files/epg-ca.xml.gz"),
    # International sports lineups named in the B1G 10 Nov sports-coverage register entry.
    "epgshare_hk": ("Hong Kong · EPG Share HK1 — Now Sports/beIN (verify)", "https://epgshare01.online/epgshare01/epg_ripper_HK1.xml.gz"),
    "iptv_epg_hk": ("Hong Kong · IPTV-EPG.org (verify)", "https://iptv-epg.org/files/epg-hk.xml.gz"),
    "iptv_epg_ge": ("Georgia · IPTV-EPG.org — Setanta (verify)", "https://iptv-epg.org/files/epg-ge.xml.gz"),
    "epgshare_my": ("Malaysia · EPG Share MY1 — Astro (verify)", "https://epgshare01.online/epgshare01/epg_ripper_MY1.xml.gz"),
    # Matt Huisman regional guides (path pattern reported in community forums).
    "mjh_nz": ("New Zealand free-to-air · Matt Huisman", "https://raw.githubusercontent.com/matthuisman/i.mjh.nz/master/nz/epg.xml.gz"),
    "mjh_au_sydney": ("Australia free-to-air (Sydney) · Matt Huisman", "https://raw.githubusercontent.com/matthuisman/i.mjh.nz/master/au/Sydney/epg.xml.gz"),
    # Sport-only guides from the same repository (checked 14 Nov 2026: Sky Sport NZ 1-9, Sky Sport Premier
    # League, Sky Sport Select, ESPN/ESPN2, 7 days ahead, about 0.1 MB; Kayo: Fox Sports 503-506, Fox
    # Cricket/League/Footy, ESPN, Racing.com). The repository's Foxtel guide was stale (October) and is not offered.
    "mjh_skysportnow_nz": ("New Zealand sport · Sky Sport Now (Matt Huisman)",
                           "https://raw.githubusercontent.com/matthuisman/i.mjh.nz/master/SkySportNow/epg.xml.gz"),
    "mjh_kayo_au": ("Australia sport · Kayo (Matt Huisman)",
                    "https://raw.githubusercontent.com/matthuisman/i.mjh.nz/master/Kayo/epg.xml.gz"),
    # UK free streaming (FAST) channels: Stingray, Qwest TV, Vevo, Rakuten TV, DAZN Ringside, Sky Sports
    # Stories/Classics. Checked 14 Nov 2026: Plex 371 channels (3.4 days), Samsung TV Plus 278 (about
    # 17 hours), Pluto TV 183 (about 1 day). Platform ids, not iptv-org ids: matched by name.
    "mjh_plex_gb": ("UK free streaming · Plex (Matt Huisman)",
                    "https://raw.githubusercontent.com/matthuisman/i.mjh.nz/master/Plex/gb.xml.gz"),
    "mjh_samsung_gb": ("UK free streaming · Samsung TV Plus (Matt Huisman)",
                       "https://raw.githubusercontent.com/matthuisman/i.mjh.nz/master/SamsungTVPlus/gb.xml.gz"),
    "mjh_pluto_gb": ("UK free streaming · Pluto TV (Matt Huisman)",
                     "https://raw.githubusercontent.com/matthuisman/i.mjh.nz/master/PlutoTV/gb.xml.gz"),
    # Community guides on GitHub, checked 14 Nov 2026. No licence for the programme data: private use only.
    "es_doblem": ("Spain incl. Movistar Plus+ (M+ LaLiga, Liga de Campeones, Vamos) and DAZN · EPG dobleM",
                  "https://raw.githubusercontent.com/davidmuma/EPG_dobleM/master/guiatv.xml.gz"),
    "fr_mena_grab": ("France + beIN Sports (MENA/FR/EN), OSN, MBC · Fazzani/grab (130 MB, 9 days)",
                     "https://raw.githubusercontent.com/Fazzani/grab/master/merge.xml.gz"),
    "pt_m3upt": ("Portugal (Sport TV 1-7, DAZN 1-5 PT, Eleven) · M3UPT",
                 "https://raw.githubusercontent.com/LITUATUI/M3UPT/main/EPG/epg-m3upt.xml.gz"),
}
# Further iptv-epg.org country files named on its guides page (not reachable from the development
# sandbox: "verify" with Test EPG before enabling).
for _cc in ("se", "no", "dk", "tr", "pt", "pl", "ru", "al", "bg", "cz", "hu", "ro"):
    EPG["iptv_epg_" + _cc] = ("%s · IPTV-EPG.org (verify)" % _cc.upper(), "https://iptv-epg.org/files/epg-%s.xml.gz" % _cc)
# Further markets present in the owner's provider categories (CA, AU, NZ, PT,
# PL, GR, SG, IN). Canada uses the publisher's CA2 feed.
EPGSHARE_MARKETS = {
    "CA": "Canada (TSN/Sportsnet)", "AU": "Australia (Fox/Kayo)", "NZ": "New Zealand (Sky Sport NZ)",
    "PT": "Portugal (Sport TV)", "PL": "Poland (Polsat/Canal+ Sport)", "GR": "Greece (Nova/Cosmote)",
    "SG": "Singapore (Hub Sports)", "IN": "India (Star/Sony Sports)",
    # Added 14 Nov 2026 from the publisher's file list (iptv-org/epg sites/epgshare01.online channel counts).
    "DE": "Germany", "ES": "Spain", "IT": "Italy", "NL": "Netherlands", "CH": "Switzerland",
    "SE": "Sweden", "NO": "Norway", "DK": "Denmark", "FI": "Finland", "TR": "Turkey", "RO": "Romania",
    "BG": "Bulgaria", "HU": "Hungary", "CZ": "Czech Republic", "SK": "Slovakia", "HR": "Croatia",
    "BA": "Bosnia and Herzegovina", "AL": "Albania", "SA": "Saudi Arabia (SSC/Thmanyah)", "EG": "Egypt and pan-Arab (MBC)",
}
for _cc, _label in EPGSHARE_MARKETS.items():
    _tag = "CA2" if _cc == "CA" else _cc + "1"
    EPG["epgshare_" + _cc.lower()] = ("%s · EPG Share %s (verify)" % (_label, _tag),
                                      "https://epgshare01.online/epgshare01/epg_ripper_%s.xml.gz" % _tag)
# Upstream families: two guides from one family are not independent evidence.
EPG_FAMILY = {
    "farleyflex": "farleyflex", "uk_freeview": "freeview_epg",
    "epgshare_uk": "epgshare", "epgshare_ie": "epgshare", "epgshare_fr": "epgshare",
    "epgshare_us": "epgshare", "epgshare_us_sports": "epgshare", "epgshare_hk": "epgshare", "epgshare_my": "epgshare",
    "fr_programmetv": "iptv_org", "fr_telerama": "iptv_org", "iptvorg_sky_uk": "iptv_org", "iptvorg_foxtel_au": "iptv_org",
    "fr_xmltv": "xmltvfr", "mjh_sky_uk": "mjh", "mjh_nz": "mjh", "mjh_au_sydney": "mjh",
    "mjh_skysportnow_nz": "mjh", "mjh_kayo_au": "mjh", "epgtalk_uk": "epgtalk", "epgtalk_sports": "epgtalk",
    **{f"iptv_epg_{market}": "iptv_epg_org" for market in ("gb", "au", "de", "it", "es", "nl", "ca")},
    "iptv_epg_fr": "iptv_epg_org", "iptv_epg_hk": "iptv_epg_org", "iptv_epg_ge": "iptv_epg_org",
}
EPG["epgshare_bein"] = ("beIN Sports MENA (Arabic/English) · EPG Share BEIN1 (verify)",
                        "https://epgshare01.online/epgshare01/epg_ripper_BEIN1.xml.gz")
EPG_FAMILY.update({"epgshare_" + cc.lower(): "epgshare" for cc in EPGSHARE_MARKETS})
EPG_FAMILY.update({"epgshare_bein": "epgshare", "es_doblem": "doblem", "fr_mena_grab": "fazzani_grab",
                   "pt_m3upt": "m3upt", "mjh_plex_gb": "mjh", "mjh_samsung_gb": "mjh", "mjh_pluto_gb": "mjh",
                   **{"iptv_epg_" + cc: "iptv_epg_org" for cc in ("se", "no", "dk", "tr", "pt", "pl", "ru", "al",
                                                                 "bg", "cz", "hu", "ro")}})
# (max download bytes, max programmes) per guide; broad national guides are large.
EPG_LIMITS = {
    # The publisher serves an uncompressed file of about 21 MB.
    "uk_freeview": (30_000_000, 100_000),
    "iptv_epg_gb": (30_000_000, 180_000), "iptv_epg_au": (14_000_000, 100_000),
    "epgshare_us_sports": (5_000_000, 150_000),
    "iptv_epg_ca": (16_000_000, 175_000), "iptv_epg_nl": (20_000_000, 100_000),
    "epgshare_uk": (60_000_000, 300_000), "epgshare_fr": (40_000_000, 250_000),
    "epgshare_ie": (30_000_000, 200_000), "epgshare_us": (60_000_000, 300_000),
    "epgshare_hk": (30_000_000, 200_000), "epgshare_my": (30_000_000, 200_000),
    "fr_xmltv": (30_000_000, 250_000),
    # Current public guide samples are 1.24 MB / 9.8k rows (NZ) and
    # 0.73 MB / 13.8k rows (Sydney); these caps allow growth without using
    # the much larger broad-feed defaults.
    "mjh_nz": (5_000_000, 50_000), "mjh_au_sydney": (5_000_000, 50_000),
    "mjh_skysportnow_nz": (2_000_000, 20_000), "mjh_kayo_au": (2_000_000, 20_000),
}
EPG_LIMITS.update({"epgshare_" + cc.lower(): (40_000_000, 250_000) for cc in EPGSHARE_MARKETS})
EPG_LIMITS.update({"es_doblem": (15_000_000, 150_000), "fr_mena_grab": (25_000_000, 260_000),
                   "pt_m3upt": (8_000_000, 100_000), "mjh_plex_gb": (3_000_000, 40_000),
                   "mjh_samsung_gb": (2_000_000, 20_000), "mjh_pluto_gb": (2_000_000, 20_000)})
EPG_DAILY_REQUEST_LIMIT = 4
DEFAULT_EPG_LIMIT = (14_000_000, 100_000)
# XML TV Fr lists an expanded France-only file of about 70 MiB.
EPG_EXPANDED_LIMITS = {
    "fr_xmltv": 85_000_000, "epgshare_ca": 85_000_000, "epgshare_us": 95_000_000,
    "iptv_epg_gb": 95_000_000, "iptv_epg_ca": 95_000_000, "epgtalk_uk": 115_000_000,
    "mjh_nz": 25_000_000, "mjh_au_sydney": 15_000_000, "mjh_skysportnow_nz": 10_000_000, "mjh_kayo_au": 5_000_000,
    # Measured 14 Nov 2026 (uncompressed): dobleM 95 MB, Fazzani/grab 130 MB, M3UPT 38 MB, Plex GB 5 MB.
    "es_doblem": 130_000_000, "fr_mena_grab": 170_000_000, "pt_m3upt": 60_000_000,
    "mjh_plex_gb": 15_000_000, "mjh_samsung_gb": 8_000_000, "mjh_pluto_gb": 10_000_000,
}
# The standard XMLTV prologue names an *external* DTD that the parser never fetches.
# Remove only that exact marker at the start of the file, for every source; an
# internal subset ("[...]"), entities or a second DOCTYPE are still refused.
XMLTV_DTD_SOURCES = frozenset({"fr_xmltv", "epgtalk_uk", "epgtalk_sports"})  # historical; now applied to all
_XMLTV_DTD_PROLOGUE = re.compile(
    rb'\A((?:\xef\xbb\xbf)?(?:<\?xml [^<>]*\?>)?[ \t\r\n]*)'
    rb'<!DOCTYPE tv SYSTEM "[A-Za-z0-9:/._-]{0,120}xmltv\.dtd">'
)

# name -> (label, base URL, shared key name or None, conservative daily call budget)
TENNIS_API_HOST = "tennis-api-atp-wta-itf.p.rapidapi.com"
SPORTS = {
    "bha_racing": ("Horse racing · British Horseracing Authority", "https://crate.horseracing.software/ics/fixtures", None, 4),
    "openboxing": ("Boxing · Open Boxing world title bouts", "https://openboxing.org/api/bouts/scheduled/index.json", None, 4),
    "pandascore": ("Esports · PandaScore", "https://api.pandascore.co/matches/upcoming", "pandascore", 24),
    "tennis_api": ("Tennis · Tennis API (RapidAPI)", f"https://{TENNIS_API_HOST}/tennis/v2/extend/api/events", "tennis_api", 40),
    "jolpica": ("Formula 1 · Jolpica (Ergast)", "https://api.jolpi.ca/ergast/f1/current.json", None, 6),
    "openf1": ("Formula 1 sessions · OpenF1", "https://api.openf1.org/v1/sessions", None, 6),
    "openligadb": ("Football · OpenLigaDB", "https://api.openligadb.de/getmatchdata", None, 24),
    "football_data": ("Football · football-data.org (PL, CL, Championship, top European leagues)", "https://api.football-data.org/v4/matches", "football_data", 45),
    "api_sports": ("Football · API-Sports (worldwide incl. FA Cup, EFL Cup, UEL, UECL, internationals)", "https://v3.football.api-sports.io/fixtures", "api_sports", 80),
    "api_sports_rugby": ("Rugby union & league · API-Sports", "https://v1.rugby.api-sports.io/games", "api_sports", 80),
    "api_sports_basketball": ("Basketball · API-Sports", "https://v1.basketball.api-sports.io/games", "api_sports", 80),
    "api_sports_hockey": ("Ice hockey · API-Sports", "https://v1.hockey.api-sports.io/games", "api_sports", 80),
    "api_sports_nfl": ("American football · API-Sports", "https://v1.american-football.api-sports.io/games", "api_sports", 80),
    "api_sports_baseball": ("Baseball · API-Sports", "https://v1.baseball.api-sports.io/games", "api_sports", 80),
    "api_sports_handball": ("Handball · API-Sports", "https://v1.handball.api-sports.io/games", "api_sports", 80),
    "api_sports_volleyball": ("Volleyball · API-Sports", "https://v1.volleyball.api-sports.io/games", "api_sports", 80),
    "api_sports_afl": ("Australian rules (AFL) · API-Sports", "https://v1.afl.api-sports.io/games", "api_sports", 80),
    "api_sports_mma": ("MMA · API-Sports", "https://v1.mma.api-sports.io/fights", "api_sports", 80),
    "thesportsdb": ("Multi-sport · TheSportsDB (free public key)", "https://www.thesportsdb.com/api/v1/json/123/eventsday.php", None, 120),
    "cricketdata": ("Cricket · CricketData.org (CricAPI)", "https://api.cricapi.com/v1/matches", "cricketdata", 60),
}
SPORT_FAMILY = {name: ("api_sports" if name.startswith("api_sports") else name) for name in SPORTS}
API_SPORTS_SPORT = {
    "api_sports": "football", "api_sports_rugby": "rugby", "api_sports_basketball": "basketball",
    "api_sports_hockey": "ice_hockey", "api_sports_nfl": "american_football", "api_sports_baseball": "baseball",
    "api_sports_handball": "handball", "api_sports_volleyball": "volleyball", "api_sports_mma": "mma",
    "api_sports_afl": "aussie_rules",
}
SOURCE_NOTES = {
    "bha_racing": "Official British meeting dates and session labels. First-race times and TV availability require separate evidence. Private collection.",
    "openboxing": "Scheduled world title bouts with dates. Card times, ring walks and UK broadcaster or PPV access need a separate source.",
    "pandascore": "Optional PandaScore token. Upcoming fixtures only. The first 100 matches are collected; coverage may be partial. Private collection.",
    "tennis_api": "Optional RapidAPI key. Live singles and the first 50 upcoming matches per tour, when supplied. Check the RapidAPI plan for endpoint access and quota. Private collection.",
    "jolpica": "Ergast-compatible F1 calendar incl. practice/qualifying/sprint. CC BY-NC-SA attribution.",
    "openf1": "Historical F1 sessions with end times (2023+). Free historical access; live telemetry requires provider access.",
    "openligadb": "Community fixtures for selected German and European competitions. ODbL attribution/share-alike.",
    "football_data": "Free plan: 12 competitions incl. Premier League, Champions League, Championship, World Cup, Euros. 10 calls/min; delayed scores.",
    "api_sports": "One key works across these products. Provider quotas and season access depend on the product and plan.",
    "thesportsdb": "Free public key 123: soccer, rugby, cricket, motorsport, fighting, golf, darts, snooker and more. Free day results may be capped. Select sports with coverage gaps.",
    "cricketdata": "Free lifetime plan 100 hits/day. Key travels in the query string (provider requirement); never logged.",
}
THESPORTSDB_DEFAULT_SPORTS = ["Soccer", "Rugby", "Cricket", "Motorsport", "Fighting", "Golf", "Darts", "Snooker",
                      "Tennis", "Ice Hockey", "Basketball", "American Football", "Cycling", "Horse Racing"]
THESPORTSDB_SPORTS = THESPORTSDB_DEFAULT_SPORTS + ["Athletics", "Bowling", "eSports", "Boxing"]
OPENLIGADB_DEFAULT_LEAGUES = ("bl1", "bl2", "bl3")
OPENLIGADB_LEAGUES = {
    "bl1": ("Bundesliga", "Germany"),
    "bl2": ("2. Bundesliga", "Germany"),
    "bl3": ("3. Liga", "Germany"),
    "dfb": ("DFB-Pokal", "Germany"),
    "ffb1": ("Frauen-Bundesliga", "Germany"),
    "ucl": ("UEFA Champions League", "World"),
    "la1": ("La Liga", "Spain"),
}

ALLOW_HOSTS = {urllib.parse.urlparse(item[1]).hostname for item in list(EPG.values()) + list(SPORTS.values())}


class RedirectGuard(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        verify_url(newurl)
        # Never forward provider credentials to a *different* allowed hostname.
        # A host allowlist alone cannot prevent this cross-origin credential leak.
        src = urllib.parse.urlsplit(req.full_url)
        dst = urllib.parse.urlsplit(newurl)
        if (src.hostname, src.port or 443) != (dst.hostname, dst.port or 443):
            raise ValueError("Cross-origin provider redirect blocked")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def verify_url(url):
    u = urllib.parse.urlsplit(url)
    if u.scheme != "https" or u.hostname not in ALLOW_HOSTS or u.username or u.password or u.port not in (None, 443):
        raise ValueError("Source URL is not on the approved HTTPS provider list")


class UpstreamHTTPError(RuntimeError):
    def __init__(self, status, retry_after=None):
        super().__init__(f"HTTP {status} from upstream")
        self.status = status
        self.retry_after = retry_after


class ProviderRejected(ValueError):
    """Safe classification of a provider error envelope."""


def api_sports_error(payload):
    errors = payload.get("errors") if isinstance(payload, dict) else None
    if not errors:
        return None
    keys = {str(key).casefold() for key in errors} if isinstance(errors, dict) else set()
    if keys & {"requests", "quota", "ratelimit", "rate_limit"}:
        return "Provider quota or rate limit"
    if keys & {"token", "key", "auth", "authentication"}:
        return "Provider rejected the API key"
    if keys & {"plan", "subscription", "season"}:
        return "Provider plan or season restriction"
    return "Provider rejected the requested scope"


def fetch(url, headers=None, max_bytes=14_000_000, *, response_headers=None):
    verify_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": "SportsLiveInfo/0.3 (self-hosted EPG and sports collector)", **(headers or {})})
    opener = urllib.request.build_opener(RedirectGuard())
    try:
        with opener.open(request, timeout=30) as response:
            # +1 permits explicit rejection without unbounded memory consumption.
            data = response.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise ValueError("Provider response exceeded configured size limit")
            if response_headers is not None:
                for field in ("ETag", "Last-Modified", "Retry-After", "x-ratelimit-requests-remaining"):
                    value = response.headers.get(field)
                    if value and len(value) <= 256 and "\r" not in value and "\n" not in value:
                        response_headers[field] = value
            return data
    except urllib.error.HTTPError as exc:
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        exc.close()
        if exc.code == 304 and headers and ("If-None-Match" in headers or "If-Modified-Since" in headers):
            return None
        raise UpstreamHTTPError(exc.code, retry_after) from None
    except urllib.error.URLError:
        raise RuntimeError("Upstream network request failed") from None


def _utc(value):
    when = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if when.tzinfo is None:
        raise ValueError("Timestamp lacks an explicit offset")
    return when.astimezone(timezone.utc).isoformat(timespec="seconds")


def _epoch(value):
    return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat(timespec="seconds")


_LIVE = {"1h", "2h", "ht", "et", "bt", "p", "pt", "live", "in_play", "paused", "int", "q1", "q2", "q3", "q4", "ot",
         "in progress", "1st half", "2nd half", "half time", "halftime", "extra time", "break time", "penalty in progress"}
_FINISHED = {"ft", "aet", "pen", "finished", "match finished", "after over time", "after penalties", "awarded", "awd", "wo", "aw",
             "ended", "aot", "ap", "complete", "completed", "result"}
_POSTPONED = {"pst", "post", "postponed", "match postponed", "susp", "suspended", "delayed"}
_CANCELLED = {"canc", "cancelled", "canceled", "abd", "abandoned", "intr", "interrupted"}
_SCHEDULED = {"ns", "tbd", "scheduled", "timed", "not started", "time to be defined", ""}


def status_of(raw):
    value = str(raw or "").strip().casefold()
    for state, values in (("live", _LIVE), ("finished", _FINISHED), ("postponed", _POSTPONED),
                          ("cancelled", _CANCELLED), ("scheduled", _SCHEDULED)):
        if value in values:
            return state
    return "unknown"


def xmltv_time(value):
    value = (value or "").strip()
    if value.endswith("Z"):
        value = value[:-1].rstrip() + " +0000"
    for fmt in ("%Y%m%d%H%M%S %z", "%Y%m%d%H%M %z"):
        try:
            return datetime.strptime(value, fmt).astimezone(timezone.utc).isoformat(timespec="seconds")
        except ValueError:
            pass
    raise ValueError("XMLTV time missing explicit UTC offset or invalid")


def _display_name(node, fallback):
    names = node.findall("display-name")
    for preferred in names:
        if (preferred.get("lang") or "").lower().startswith("en") and preferred.text:
            return preferred.text
    for name in names:
        if name.text:
            return name.text
    return fallback


class _LimitedXmlInput:
    """Provide bounded bytes to ElementTree without expanding the entire gzip.

    The rolling tail also detects DTD/ENTITY declarations split across chunk
    boundaries. Peak decompression memory is bounded independently of the
    compressed HTTP response size.
    """

    def __init__(self, stream, byte_limit, strip_xmltv_dtd=False):
        self.stream = stream
        self.byte_limit = byte_limit
        self.total = 0
        self.tail = b""
        self.strip_xmltv_dtd = strip_xmltv_dtd

    def read(self, size=-1):
        size = 65536 if size is None or size < 0 else min(size, 65536)
        payload = self.stream.read(min(size, self.byte_limit - self.total + 1))
        self.total += len(payload)
        if self.total > self.byte_limit:
            raise ValueError("XMLTV decompressed past safety limit")
        if self.strip_xmltv_dtd:
            # ElementTree's first read covers these prologues. A truncated
            # or altered declaration still goes through the guard.
            self.strip_xmltv_dtd = False
            payload = _XMLTV_DTD_PROLOGUE.sub(rb"\1", payload, count=1)
        marker = (self.tail + payload).upper()
        if b"<!DOCTYPE" in marker or b"<!ENTITY" in marker or b"\x00" in payload:
            raise ValueError("XMLTV declarations and entities are not allowed")
        self.tail = marker[-16:]
        return payload


def decode_xmltv(raw, source, max_expanded=None, max_programmes=100_000,
                 max_channels=40_000):
    """Stream bounded XMLTV/gzip with source-aware programme detail.

    This is private source collection, never licence approval for redistribution.
    """
    if not isinstance(raw, bytes) or not raw:
        raise ValueError("Empty XMLTV input")
    if raw[:2] == b"\x1f\x8b":
        stream = gzip.GzipFile(fileobj=io.BytesIO(raw))
    else:
        stream = io.BytesIO(raw)
    if max_expanded is None:
        max_expanded = EPG_EXPANDED_LIMITS.get(source, 65_000_000)
    channels, icons, programmes, bad = {}, {}, [], 0
    root = None
    with stream:
        for event, node in ET.iterparse(
                _LimitedXmlInput(stream, max_expanded, True),
                events=("start", "end")):
            if root is None:
                root = node
                if root.tag != "tv":
                    raise ValueError("Not an XMLTV programme guide")
            if event != "end":
                continue
            if node.tag == "channel":
                if len(channels) >= max_channels:
                    raise ValueError("XMLTV channel count exceeded safety limit")
                channel_id = node.get("id", "")[:180]
                name = _display_name(node, channel_id)
                if channel_id:
                    channels[channel_id] = name[:180]
                    icon = node.find("icon")
                    if icon is not None and (icon.get("src") or "").startswith("https://"):
                        icons[channel_id] = icon.get("src")[:300]
                node.clear()
            elif node.tag == "programme":
                if len(programmes) >= max_programmes:
                    raise ValueError("XMLTV programme count exceeded safety limit")
                try:
                    start, end = xmltv_time(node.get("start")), xmltv_time(node.get("stop"))
                    title_node = node.find("title")
                    title = (title_node.text or "").strip() if title_node is not None else ""
                    if not title or end <= start:
                        raise ValueError("Incomplete programme")
                    programmes.append({
                        "channel_id": node.get("channel", "")[:180],
                        "start_utc": start, "end_utc": end,
                        "title": title[:240],
                        "subtitle": (node.findtext("sub-title") or "").strip()[:240],
                        "description": (node.findtext("desc") or "")[:1000],
                        "categories": [cat.text.strip()[:60] for cat in node.findall("category")
                                       if cat.text and cat.text.strip()][:5],
                        "is_live": node.find("live") is not None,
                        "is_repeat": node.find("previously-shown") is not None,
                        "is_premiere": node.find("premiere") is not None,
                        "episode_num": (node.findtext("episode-num") or "").strip()[:40],
                        "language": title_node.get("lang", "")[:12] if title_node is not None else "",
                        "source_id": source,
                    })
                except ValueError:
                    bad += 1
                node.clear()
                # ElementTree retains sibling references; release them in
                # bounded batches AFTER their complete end event.
                if root is not None and len(root) > 512:
                    root.clear()
    orphans = sum(1 for p in programmes if p["channel_id"] not in channels)
    return {"source_id": source, "channels": channels, "channel_icons": icons,
            "programmes": programmes, "invalid_programmes": bad,
            "orphaned_programmes": orphans, "source_redistribution_approved": False}


_F1_SESSIONS = {"race": "race", "FirstPractice": "practice1", "SecondPractice": "practice2", "ThirdPractice": "practice3",
                "Qualifying": "qualifying", "Sprint": "sprint", "SprintQualifying": "sprint_qualifying",
                "SprintShootout": "sprint_qualifying"}


def f1_events(data):
    obj = json.loads(data)
    table = obj.get("MRData", {}).get("RaceTable", {})
    if not isinstance(table.get("Races"), list):
        raise ValueError("Jolpica F1 races payload missing or invalid")
    rows = table["Races"]
    events = []
    for race in rows:
        try:
            circuit = race.get("Circuit", {})
            location = circuit.get("Location", {})
            season, round_ = str(race["season"]), str(race["round"])
            sessions = [("race", race)]
            sessions.extend((key, race[key]) for key in ("FirstPractice", "SecondPractice", "ThirdPractice", "Qualifying", "Sprint", "SprintQualifying", "SprintShootout") if key in race)
            for kind, entry in sessions:
                if not entry.get("date"):
                    continue
                if entry.get("time"):
                    utc = datetime.fromisoformat(entry["date"] + "T" + entry["time"].replace("Z", "+00:00")).astimezone(timezone.utc)
                    precision = "scheduled"
                elif kind == "race":
                    # A confirmed race date without a time is still a real fixture.
                    utc = datetime.fromisoformat(entry["date"] + "T12:00:00+00:00")
                    precision = "date_only"
                else:
                    continue
                events.append({"id": f"f1:{season}:{round_}:{kind}", "sport": "motorsport", "competition": "Formula 1", "event_type": kind,
                               "session": _F1_SESSIONS[kind],
                               "title": race.get("raceName", "Formula 1"), "start_utc": utc.isoformat(timespec="seconds"), "start_precision": precision,
                               "venue": circuit.get("circuitName", ""), "circuit_id": circuit.get("circuitId", ""), "country": location.get("country", ""),
                               "source_id": "jolpica", "broadcasts": [], "broadcast_verified": False})
        except (KeyError, ValueError, TypeError):
            continue
    return events


_OPENF1_SESSIONS = {"practice 1": "practice1", "practice 2": "practice2", "practice 3": "practice3", "qualifying": "qualifying",
                    "sprint": "sprint", "sprint qualifying": "sprint_qualifying", "sprint shootout": "sprint_qualifying", "race": "race"}


def openf1_events(data):
    rows = json.loads(data)
    if not isinstance(rows, list):
        raise ValueError("OpenF1 sessions payload missing or invalid")
    events = []
    for row in rows:
        try:
            name = str(row["session_name"])
            session = _OPENF1_SESSIONS.get(name.casefold())
            if not session:
                continue
            place = row.get("country_name") or row.get("location") or ""
            event = {"id": "openf1:%s" % row["session_key"], "sport": "motorsport", "competition": "Formula 1",
                     "event_type": name, "session": session, "title": ("Formula 1 %s — %s" % (place, name)) if place else "Formula 1 — %s" % name,
                     "start_utc": _utc(row["date_start"]), "start_precision": "scheduled",
                     "venue": row.get("circuit_short_name") or row.get("location") or "", "country": row.get("country_name") or "",
                     "source_id": "openf1", "broadcasts": [], "broadcast_verified": False}
            if row.get("date_end"):
                event["end_utc"] = _utc(row["date_end"])
            events.append(event)
        except (KeyError, ValueError, TypeError):
            continue
    return events


def football_data_events(data):
    payload = json.loads(data)
    if not isinstance(payload.get("matches"), list):
        raise ValueError("football-data.org matches payload missing or invalid")
    matches = payload["matches"]
    events = []
    for m in matches:
        try:
            when = m.get("utcDate")
            if not when:
                continue
            utc = datetime.fromisoformat(when.replace("Z", "+00:00")).astimezone(timezone.utc)
            home_team, away_team = m.get("homeTeam") or {}, m.get("awayTeam") or {}
            home = home_team.get("name") or "TBC"
            away = away_team.get("name") or "TBC"
            competition = m.get("competition") or {}
            raw_status = m.get("status", "SCHEDULED")
            events.append({"id": "football-data:%s" % m["id"], "sport": "football", "competition": competition.get("name", ""),
                           "competition_code": "fd:%s" % competition["code"] if competition.get("code") else None,
                           "competition_country": (m.get("area") or competition.get("area") or {}).get("name", ""),
                           "event_type": "match", "title": f"{home} v {away}", "participants": [home, away],
                           "participants_short": [home_team.get("shortName") or home, away_team.get("shortName") or away],
                           "start_utc": utc.isoformat(timespec="seconds"),
                           # SCHEDULED = date known, kick-off not yet fixed; TIMED = kick-off set.
                           "start_precision": "provisional" if raw_status == "SCHEDULED" else "scheduled",
                           "status": raw_status, "status_normalized": status_of(raw_status),
                           "stage": m.get("stage") or "", "round": str(m.get("matchday") or ""), "venue": m.get("venue") or "",
                           "source_id": "football_data", "broadcasts": [], "broadcast_verified": False})
        except (ValueError, KeyError, TypeError):
            continue
    return events


def api_sports_events(data):
    payload = json.loads(data)
    if payload.get("errors"):
        raise ValueError("API-Sports reported an upstream data error")
    paging = payload.get("paging") or {}
    if int(paging.get("total", 1)) > int(paging.get("current", 1)):
        raise ValueError("API-Sports fixture page incomplete; keep previous last-good")
    rows = payload.get("response")
    if not isinstance(rows, list):
        raise ValueError("API-Sports fixtures payload missing or invalid")
    events = []
    for row in rows:
        try:
            fixture = row["fixture"]
            when = datetime.fromisoformat(fixture["date"].replace("Z", "+00:00")).astimezone(timezone.utc)
            teams = row.get("teams") or {}
            home = (teams.get("home") or {}).get("name") or "TBC"
            away = (teams.get("away") or {}).get("name") or "TBC"
            league = row.get("league") or {}
            short = (fixture.get("status") or {}).get("short", "NS")
            events.append({"id": f"api-sports:{fixture['id']}", "sport": "football", "competition": league.get("name", ""),
                           "competition_code": "as:%s" % league["id"] if league.get("id") else None,
                           "competition_country": league.get("country") or "",
                           "event_type": "match", "title": f"{home} v {away}", "participants": [home, away],
                           "start_utc": when.isoformat(timespec="seconds"),
                           "start_precision": "time_tbc" if short == "TBD" else "scheduled",
                           "status": short, "status_normalized": status_of(short), "round": league.get("round") or "",
                           "venue": (fixture.get("venue") or {}).get("name") or "",
                           "source_id": "api_sports", "broadcasts": [], "broadcast_verified": False})
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
    return events


def api_sports_games_events(data, source_id, sport):
    """Shared decoder for API-Sports v1 'games' APIs (rugby, basketball, hockey, NFL, baseball, handball, volleyball).

    The epoch timestamp is preferred because it is unambiguous; the NFL API
    nests date/status inside a 'game' object.
    """
    payload = json.loads(data)
    if payload.get("errors"):
        raise ValueError("API-Sports reported an upstream data error")
    rows = payload.get("response")
    if not isinstance(rows, list):
        raise ValueError("API-Sports games payload missing or invalid")
    events = []
    for row in rows:
        try:
            game = row.get("game") if isinstance(row.get("game"), dict) else row
            raw_date = game.get("date")
            timestamp = game.get("timestamp") or (raw_date.get("timestamp") if isinstance(raw_date, dict) else None)
            if timestamp:
                start = _epoch(timestamp)
            elif isinstance(raw_date, str):
                start = _utc(raw_date)
            else:
                continue
            teams = row.get("teams") or {}
            home = (teams.get("home") or {}).get("name") or "TBC"
            away = (teams.get("away") or {}).get("name") or "TBC"
            league = row.get("league") or {}
            country = row.get("country") or league.get("country") or {}
            short = (game.get("status") or {}).get("short", "NS")
            events.append({"id": "%s:%s" % (source_id.replace("_", "-"), game["id"]), "sport": sport,
                           "competition": league.get("name", ""),
                           "competition_code": "as-%s:%s" % (sport, league["id"]) if league.get("id") else None,
                           "competition_country": country.get("name", "") if isinstance(country, dict) else str(country),
                           "event_type": "match", "title": f"{home} v {away}", "participants": [home, away],
                           "start_utc": start, "start_precision": "time_tbc" if short in ("TBD", "NS-TBD") else "scheduled",
                           "status": short, "status_normalized": status_of(short),
                           "round": str(row.get("week") or game.get("week") or game.get("stage") or ""),
                           "venue": (game.get("venue") or {}).get("name", "") if isinstance(game.get("venue"), dict) else "",
                           "source_id": source_id, "broadcasts": [], "broadcast_verified": False})
        except (ValueError, KeyError, TypeError, OverflowError):
            continue
    return events


def api_sports_mma_events(data, source_id="api_sports_mma"):
    payload = json.loads(data)
    if payload.get("errors"):
        raise ValueError("API-Sports reported an upstream data error")
    rows = payload.get("response")
    if not isinstance(rows, list):
        raise ValueError("API-Sports fights payload missing or invalid")
    events = []
    for row in rows:
        try:
            start = _epoch(row["timestamp"]) if row.get("timestamp") else _utc(row["date"])
            fighters = row.get("fighters") or {}
            first = (fighters.get("first") or {}).get("name") or "TBC"
            second = (fighters.get("second") or {}).get("name") or "TBC"
            short = (row.get("status") or {}).get("short", "NS")
            events.append({"id": "api-sports-mma:%s" % row["id"], "sport": "mma",
                           "competition": row.get("slug") or row.get("category") or "MMA",
                           "event_type": "main_event" if row.get("is_main") else "bout",
                           "title": f"{first} v {second}", "participants": [first, second],
                           "weight_class": row.get("category") or "", "start_utc": start,
                           # Individual bout times on a card are estimates.
                           "start_precision": "estimated", "status": short, "status_normalized": status_of(short),
                           "source_id": source_id, "broadcasts": [], "broadcast_verified": False})
        except (ValueError, KeyError, TypeError, OverflowError):
            continue
    return events


def bha_racing_events(data, *, year):
    """Decode the BHA year download, which lists one all-day entry per date."""
    text = data.decode("utf-8-sig").replace("\r\n", "\n")
    text = re.sub(r"\n[ \t]", "", text)
    lines = text.strip().splitlines()
    if (not lines or lines[0] != "BEGIN:VCALENDAR" or lines[-1] != "END:VCALENDAR"
            or f"X-WR-CALNAME:British Horseracing Authority Fixture List {year}" not in lines):
        raise ValueError("Unexpected BHA calendar or season")
    events = {}
    for entry in re.findall(r"(?m)^BEGIN:VEVENT$\n(.*?)^END:VEVENT$", text, re.DOTALL):
        if re.search(r"(?m)^STATUS:CANCELLED$", entry):
            continue
        start = re.search(r"(?m)^DTSTART;VALUE=DATE:(\d{8})$", entry)
        title = re.search(r"(?m)^SUMMARY:(.+)$", entry)
        if not start or not title:
            continue
        try:
            day = date.fromisoformat(start[1])
        except ValueError:
            continue
        if day.year != year:
            continue
        for meeting in title[1].split(" / "):
            course, separator, session = meeting.strip().rpartition(" (")
            if not separator or not session.endswith(")"):
                continue
            course = re.sub(r"\\([,;\\])", r"\1", course).strip()
            session = session[:-1].strip()
            if not course or not session:
                continue
            identity = hashlib.sha256(f"{course.casefold()}|{session.casefold()}".encode()).hexdigest()[:16]
            event_id = f"bha:{day.isoformat()}:{identity}"
            events[event_id] = {
                "id": event_id, "source_id": "bha_racing", "sport": "horse_racing", "event_type": "meeting",
                "competition": "British horse racing", "title": f"{course} ({session})", "session": session,
                "venue": course, "country": "United Kingdom", "start_utc": f"{day.isoformat()}T12:00:00+00:00",
                "start_precision": "date_only", "status_normalized": "scheduled",
                "broadcasts": [], "broadcast_verified": False,
            }
    # A full-year download must resemble a full-year calendar before its
    # successful scope can replace the previous season.
    if len({event["start_utc"] for event in events.values()}) < 300:
        raise ValueError("BHA calendar has incomplete annual coverage")
    return list(events.values())


def openboxing_events(data):
    rows = json.loads(data)
    if not isinstance(rows, list):
        raise ValueError("Open Boxing bouts payload missing or invalid")
    events = []
    for row in rows:
        try:
            if row["status"] != "SCHEDULED" or type(row["boutId"]) is not int:
                continue
            day = date.fromisoformat(row["date"])
            participants = []
            for side in ("boxerA", "boxerB"):
                name = row["boxers"][side]["name"]
                if isinstance(name, dict):
                    name = " ".join(part for part in (name.get("first"), name.get("last")) if part)
                if not isinstance(name, str) or not name.strip():
                    raise ValueError("Boxer name missing")
                participants.append(name.strip())
            weight = (row.get("weight") or {}).get("class") or ""
            location = row.get("location") or {}
            events.append({
                "id": f'openboxing:{row["boutId"]}', "source_id": "openboxing", "sport": "boxing",
                "event_type": "bout", "competition": "World title boxing", "weight_class": weight,
                "title": " v ".join(participants), "participants": participants,
                "start_utc": f"{day.isoformat()}T12:00:00+00:00", "start_precision": "date_only",
                "status_normalized": "scheduled", "country": location.get("country") or "",
                "venue": location.get("venue") or "", "broadcasts": [], "broadcast_verified": False,
            })
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    if rows and not events:
        raise ValueError("Open Boxing response contained no valid scheduled bouts")
    return events


def pandascore_events(data):
    rows = json.loads(data)
    if not isinstance(rows, list):
        raise ValueError("PandaScore fixtures payload missing or invalid")
    events = []
    for row in rows:
        try:
            if not row.get("id") or not row.get("name") or not row.get("begin_at"):
                continue
            start = _utc(row["begin_at"])
            league = (row.get("league") or {}).get("name") or ""
            series = (row.get("serie") or {}).get("full_name") or ""
            game = (row.get("videogame") or {}).get("name") or ""
            participants = [item["opponent"]["name"] for item in row.get("opponents", [])
                            if isinstance(item.get("opponent"), dict) and item["opponent"].get("name")]
            events.append({
                "id": f'pandascore:{row["id"]}', "sport": "esports",
                "competition": league or series or game, "event_type": "match",
                "title": str(row["name"]), "participants": participants,
                "start_utc": start, "start_precision": "scheduled",
                "status_normalized": "cancelled" if row.get("status") == "canceled" else "scheduled",
                "source_id": "pandascore", "broadcasts": [], "broadcast_verified": False,
            })
        except (AttributeError, TypeError, ValueError, KeyError):
            continue
    return events


def thesportsdb_events(data):
    """TheSportsDB v1 eventsday. strTimestamp/strTime are UTC by provider convention."""
    payload = json.loads(data)
    if not isinstance(payload, dict) or "events" not in payload:
        raise ValueError("TheSportsDB events payload missing or invalid")
    rows = payload["events"] or []
    if not isinstance(rows, list):
        raise ValueError("TheSportsDB events payload invalid")
    events = []
    for row in rows:
        try:
            if not row.get("idEvent"):
                continue
            stamp = row.get("strTimestamp")
            precision = "scheduled"
            if stamp:
                when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            elif row.get("dateEvent") and re.fullmatch(r"\d{2}:\d{2}(?::\d{2})?.*", str(row.get("strTime") or "")):
                when = datetime.fromisoformat("%sT%s" % (row["dateEvent"], row["strTime"][:8]))
            elif row.get("dateEvent"):
                when = datetime.fromisoformat(row["dateEvent"] + "T12:00:00")
                precision = "date_only"
            else:
                continue
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            home, away = row.get("strHomeTeam"), row.get("strAwayTeam")
            participants = [p for p in (home, away) if p]
            raw_status = "postponed" if str(row.get("strPostponed", "")).lower() == "yes" else row.get("strStatus") or ""
            sport = row.get("strSport") or "other"
            league = row.get("strLeague") or ""
            title = row.get("strEvent") or " v ".join(participants)
            if sport.casefold() == "fighting" and re.search(r"\bboxing\b", f"{league} {title}", re.I):
                sport = "boxing"
            events.append({"id": "thesportsdb:%s" % row["idEvent"], "sport": sport,
                           "competition": league, "competition_country": row.get("strCountry") or "",
                           "event_type": "match" if len(participants) == 2 else "event",
                           "title": title, "participants": participants,
                           "start_utc": when.astimezone(timezone.utc).isoformat(timespec="seconds"), "start_precision": precision,
                           "time_basis": "provider_declared_utc",
                           "status": raw_status, "status_normalized": status_of(raw_status),
                           "round": str(row.get("intRound") or ""), "venue": row.get("strVenue") or "",
                           "source_id": "thesportsdb", "broadcasts": [], "broadcast_verified": False})
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
    return events


def cricketdata_events(data, horizon_days=8):
    """CricAPI /v1/matches. dateTimeGMT is GMT by field definition. Test matches expand to one record per playing day."""
    payload = json.loads(data)
    if not isinstance(payload, dict) or payload.get("status") != "success" or not isinstance(payload.get("data"), list):
        raise ValueError("CricketData.org returned an unsuccessful or invalid response")
    events = []
    for row in payload["data"]:
        try:
            gmt = row.get("dateTimeGMT")
            if not gmt or not row.get("id"):
                continue
            start = datetime.fromisoformat(gmt.replace("Z", "+00:00"))
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            start = start.astimezone(timezone.utc)
            teams = [t for t in (row.get("teams") or []) if t][:2]
            parts = str(row.get("name") or "").split(", ")
            competition = ", ".join(parts[2:]) if len(parts) > 2 else (row.get("series") or "")
            match_type = str(row.get("matchType") or "").lower()
            if row.get("matchEnded"):
                state = "finished"
            elif row.get("matchStarted"):
                state = "live"
            else:
                state = "scheduled"
            base = {"sport": "cricket", "competition": competition, "match_type": match_type,
                    "event_type": match_type or "match", "participants": teams,
                    "status": str(row.get("status") or "")[:120], "status_normalized": state,
                    "venue": row.get("venue") or "", "source_id": "cricketdata", "broadcasts": [], "broadcast_verified": False}
            title = " v ".join(teams) if len(teams) == 2 else (parts[0] if parts else "Cricket")
            days = 5 if match_type == "test" else 1
            ended = bool(row.get("matchEnded"))
            for day in range(min(days, horizon_days)):
                day_start = start + timedelta(days=day)
                if ended and day and day_start > datetime.now(timezone.utc):
                    break  # a finished Test has no future playing days
                event = dict(base, id="cricketdata:%s" % row["id"] + (":d%d" % (day + 1) if days > 1 else ""),
                             title=title + (" — Day %d" % (day + 1) if days > 1 else ""),
                             start_utc=day_start.isoformat(timespec="seconds"),
                             start_precision="scheduled" if day == 0 else "not_before")
                if days > 1:
                    event["day_number"] = day + 1
                events.append(event)
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
    return events


def openligadb_events(data, league=None):
    """Parse community-maintained football match records (no supplied secret).

    Prefer the unambiguous UTC timestamp. Never infer dates from a naïve
    local-time string or fabricate teams or television carriage.
    """
    rows = json.loads(data)
    if not isinstance(rows, list):
        raise ValueError("OpenLigaDB returned an unexpected response shape")
    events = []
    for m in rows:
        if not isinstance(m, dict):
            continue
        try:
            raw_time = m.get("matchDateTimeUTC")
            if not raw_time or not m.get("matchID"):
                continue
            when = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
            if when.tzinfo is None:
                continue
            when = when.astimezone(timezone.utc)
            home = m["team1"]["teamName"]
            away = m["team2"]["teamName"]
            if not home or not away:
                continue
            shortcut = league or m.get("leagueShortcut") or "bl1"
            if league and m.get("leagueShortcut") not in (None, league):
                continue
            label, country = OPENLIGADB_LEAGUES.get(shortcut, ("OpenLigaDB football", ""))
            events.append({
                "id": "openligadb:%s" % m["matchID"],
                "sport": "football", "competition": label if shortcut in OPENLIGADB_LEAGUES else m.get("leagueName") or label,
                "competition_code": "old:%s" % shortcut, "competition_country": country,
                "event_type": "match", "title": f"{home} v {away}",
                "participants": [home, away],
                "participants_short": [m["team1"].get("shortName") or home, m["team2"].get("shortName") or away],
                "start_utc": when.isoformat(timespec="seconds"), "start_precision": "scheduled",
                "status": "finished" if m.get("matchIsFinished") else "scheduled",
                "status_normalized": "finished" if m.get("matchIsFinished") else "scheduled",
                "round": (m.get("group") or {}).get("groupName") or "",
                "venue": (m.get("location") or {}).get("locationStadium") or "",
                "source_id": "openligadb", "broadcasts": [], "broadcast_verified": False,
            })
        except (TypeError, KeyError, ValueError):
            continue
    return events


def tennis_api_events(data, *, live=False):
    """Normalise the documented Tennis API live-board records."""
    payload = json.loads(data)
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ValueError("Tennis API reported an upstream error")
    rows = payload.get("results")
    if not isinstance(rows, list):
        raise ValueError("Tennis API results missing or invalid")
    events = []
    for row in rows:
        try:
            match_key = row["matchKey"]
            if not isinstance(match_key, str) or not re.fullmatch(r"\d+-\d+-\d+-\d+", match_key):
                continue
            tour = row["tourType"].lower()
            if tour not in ("atp", "wta"):
                continue
            players = [row.get(f"participant{i}") or (row.get(f"player{i}") or {}).get("name") for i in (1, 2)]
            if not all(isinstance(p, str) and p.strip() for p in players):
                continue
            timestamp = row["startTimestamp"]
            if type(timestamp) is not int or timestamp <= 0:
                continue
            status = row.get("status", "").casefold().replace(" ", "")
            if live and status != "inplay":
                continue
            if not live and status not in ("notstarted", "upcoming"):
                continue
            tournament = (row.get("tournament") or {}).get("name") or row.get("league")
            if not isinstance(tournament, str) or not tournament.strip():
                continue
            events.append({
                "id": f"tennis-api:{tour}:{match_key}", "source_id": "tennis_api",
                "sport": "tennis", "competition": tournament, "event_type": "match",
                "title": " v ".join(players), "participants": players,
                "start_utc": _epoch(timestamp), "start_precision": "scheduled",
                "status_normalized": "live" if live else "scheduled",
                "broadcasts": [], "broadcast_verified": False,
            })
        except (AttributeError, KeyError, TypeError, ValueError, OverflowError, OSError):
            continue
    if rows and not events and live:
        # Non-live rows on the live board can be ignored. Invalid live rows
        # should not invalidate otherwise useful upcoming scopes.
        if any(isinstance(row, dict) and str(row.get("status", "")).casefold() == "inplay" for row in rows):
            raise ValueError("Tennis API live records could not be decoded")
    return events
