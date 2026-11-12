"""Small audited provider adapters. No arbitrary-user URL fetch or credential logging."""
import gzip
import io
import json
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone

# Sources whose terms have not been verified for public republication are LOCAL ONLY.
# Every EPG source is disabled by default; URLs marked "verify" must pass the
# Ingress "Test EPG" button before being enabled.
EPG = {
    "farleyflex": ("UK sports · farleyflex", "https://raw.githubusercontent.com/farleyflex/epg-guide/main/epg.xml"),
    "uk_freeview": ("UK free-to-air · Freeview-EPG (dp247)", "https://raw.githubusercontent.com/dp247/Freeview-EPG/master/epg.xml"),
    "epgshare_uk": ("UK broad · EPG Share UK1 (verify)", "https://epgshare01.online/epgshare01/epg_ripper_UK1.xml.gz"),
    "epgshare_ie": ("Ireland · EPG Share IE1 (verify)", "https://epgshare01.online/epgshare01/epg_ripper_IE1.xml.gz"),
    "epgshare_fr": ("France broad · EPG Share FR1 (verify)", "https://epgshare01.online/epgshare01/epg_ripper_FR1.xml.gz"),
    "fr_programmetv": ("France · programme-tv.net via iptv-org (verify)", "https://iptv-org.github.io/epg/guides/fr/programme-tv.net.epg.xml.gz"),
    "fr_telerama": ("France · Télérama via iptv-org (verify)", "https://iptv-org.github.io/epg/guides/fr/telerama.fr.epg.xml.gz"),
    "fr_xmltv": ("France · XMLTV France (racacax/XML-TV-Fr)", "https://xmltvfr.fr/xmltv/xmltv_fr.xml.gz"),
    # Feeds already offered by the B1G Android backup-guide list (SkyGuideScene.backupFeeds).
    "mjh_sky_uk": ("UK Sky · Matt Huisman (B1G backup feed)", "https://i.mjh.nz/SkyUK/epg.xml.gz"),
    "iptvorg_sky_uk": ("UK Sky · iptv-org sky.com (B1G backup feed; verify)", "https://iptv-org.github.io/epg/guides/uk/sky.com.epg.xml.gz"),
    "epgtalk_uk": ("UK national · EPGTalk (B1G suggested feed)", "https://raw.githubusercontent.com/acidjesuz/EPGTalk/master/UK_guide.xml.gz"),
    "epgtalk_sports": ("Sports · EPGTalk (B1G suggested feed)", "https://raw.githubusercontent.com/acidjesuz/EPGTalk/master/Sports_guide.xml.gz"),
    "iptv_epg_fr": ("France · IPTV-EPG.org (B1G; terms not explicit)", "https://iptv-epg.org/files/epg-fr.xml.gz"),
    "epgshare_us": ("United States · EPG Share US1 (B1G backup feed)", "https://epgshare01.online/epgshare01/epg_ripper_US1.xml.gz"),
    "iptvorg_foxtel_au": ("Australia · iptv-org Foxtel (B1G backup feed; verify)", "https://iptv-org.github.io/epg/guides/au/foxtel.com.au.epg.xml.gz"),
    # International sports lineups named in the B1G 10 Nov sports-coverage register entry.
    "epgshare_hk": ("Hong Kong · EPG Share HK1 — Now Sports/beIN (verify)", "https://epgshare01.online/epgshare01/epg_ripper_HK1.xml.gz"),
    "iptv_epg_hk": ("Hong Kong · IPTV-EPG.org (verify)", "https://iptv-epg.org/files/epg-hk.xml.gz"),
    "iptv_epg_ge": ("Georgia · IPTV-EPG.org — Setanta (verify)", "https://iptv-epg.org/files/epg-ge.xml.gz"),
    "epgshare_my": ("Malaysia · EPG Share MY1 — Astro (verify)", "https://epgshare01.online/epgshare01/epg_ripper_MY1.xml.gz"),
}
# Further markets present in the owner's provider categories (CA, AU, NZ, PT,
# PL, GR, SG, IN). File names follow the confirmed epg_ripper_<CC>1 pattern
# (UK1, US1, FR1, HK1); each must pass "Test EPG" before use.
EPGSHARE_MARKETS = {
    "CA": "Canada (TSN/Sportsnet)", "AU": "Australia (Fox/Kayo)", "NZ": "New Zealand (Sky Sport NZ)",
    "PT": "Portugal (Sport TV)", "PL": "Poland (Polsat/Canal+ Sport)", "GR": "Greece (Nova/Cosmote)",
    "SG": "Singapore (Hub Sports)", "IN": "India (Star/Sony Sports)",
}
for _cc, _label in EPGSHARE_MARKETS.items():
    EPG["epgshare_" + _cc.lower()] = ("%s · EPG Share %s1 (verify)" % (_label, _cc),
                                      "https://epgshare01.online/epgshare01/epg_ripper_%s1.xml.gz" % _cc)
# Upstream families: two guides from one family are not independent evidence.
EPG_FAMILY = {
    "farleyflex": "farleyflex", "uk_freeview": "freeview_epg",
    "epgshare_uk": "epgshare", "epgshare_ie": "epgshare", "epgshare_fr": "epgshare",
    "epgshare_us": "epgshare", "epgshare_hk": "epgshare", "epgshare_my": "epgshare",
    "fr_programmetv": "iptv_org", "fr_telerama": "iptv_org", "iptvorg_sky_uk": "iptv_org", "iptvorg_foxtel_au": "iptv_org",
    "fr_xmltv": "xmltvfr", "mjh_sky_uk": "mjh", "epgtalk_uk": "epgtalk", "epgtalk_sports": "epgtalk",
    "iptv_epg_fr": "iptv_epg_org", "iptv_epg_hk": "iptv_epg_org", "iptv_epg_ge": "iptv_epg_org",
}
EPG_FAMILY.update({"epgshare_" + cc.lower(): "epgshare" for cc in EPGSHARE_MARKETS})
# (max download bytes, max programmes) per guide; broad national guides are large.
EPG_LIMITS = {
    # The publisher serves an uncompressed file of about 21 MB.
    "uk_freeview": (30_000_000, 100_000),
    "epgshare_uk": (60_000_000, 300_000), "epgshare_fr": (40_000_000, 250_000),
    "epgshare_ie": (30_000_000, 200_000), "epgshare_us": (60_000_000, 300_000),
    "epgshare_hk": (30_000_000, 200_000), "epgshare_my": (30_000_000, 200_000),
    "fr_xmltv": (30_000_000, 250_000), "mjh_sky_uk": (40_000_000, 250_000),
    "iptvorg_sky_uk": (40_000_000, 250_000), "epgtalk_uk": (40_000_000, 250_000),
    "iptvorg_foxtel_au": (40_000_000, 250_000),
}
EPG_LIMITS.update({"epgshare_" + cc.lower(): (40_000_000, 250_000) for cc in EPGSHARE_MARKETS})
DEFAULT_EPG_LIMIT = (14_000_000, 100_000)
# XML TV Fr lists an expanded France-only file of about 70 MiB.
EPG_EXPANDED_LIMITS = {"fr_xmltv": 85_000_000}

# name -> (label, base URL, shared key name or None, conservative daily call budget)
SPORTS = {
    "jolpica": ("Formula 1 · Jolpica (Ergast)", "https://api.jolpi.ca/ergast/f1/current.json", None, 6),
    "openf1": ("Formula 1 sessions · OpenF1", "https://api.openf1.org/v1/sessions", None, 6),
    "openligadb": ("Football · OpenLigaDB (Bundesliga 1–3)", "https://api.openligadb.de/getmatchdata", None, 12),
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
    "jolpica": "Ergast-compatible F1 calendar incl. practice/qualifying/sprint. CC BY-NC-SA attribution.",
    "openf1": "Independent F1 session times with end times (2023+). Free, no key.",
    "openligadb": "Community Bundesliga, 2. Bundesliga, 3. Liga fixtures. ODbL attribution/share-alike.",
    "football_data": "Free plan: 12 competitions incl. Premier League, Champions League, Championship, World Cup, Euros. 10 calls/min; delayed scores.",
    "api_sports": "Free plan 100 calls/day per sport API; one key works for every API-Sports sport below.",
    "thesportsdb": "Free public key 123: soccer, rugby, cricket, motorsport, fighting, golf, darts, snooker and more. Free-tier coverage is partial.",
    "cricketdata": "Free lifetime plan 100 hits/day. Key travels in the query string (provider requirement); never logged.",
}
THESPORTSDB_SPORTS = ["Soccer", "Rugby", "Cricket", "Motorsport", "Fighting", "Golf", "Darts", "Snooker",
                      "Tennis", "Ice Hockey", "Basketball", "American Football", "Cycling", "Horse Racing"]
OPENLIGADB_LEAGUES = ["bl1", "bl2", "bl3"]

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


def fetch(url, headers=None, max_bytes=14_000_000):
    verify_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": "SportsLiveInfo/0.3 (self-hosted EPG and sports collector)", **(headers or {})})
    opener = urllib.request.build_opener(RedirectGuard())
    try:
        with opener.open(request, timeout=30) as response:
            # +1 permits explicit rejection without unbounded memory consumption.
            data = response.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise ValueError("Provider response exceeded configured size limit")
            return data
    except urllib.error.HTTPError as exc:
        raise RuntimeError("HTTP %d from upstream" % exc.code) from None
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
_POSTPONED = {"pst", "post", "postponed", "susp", "suspended", "delayed"}
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

    def __init__(self, stream, byte_limit):
        self.stream = stream
        self.byte_limit = byte_limit
        self.total = 0
        self.tail = b""

    def read(self, size=-1):
        size = 65536 if size is None or size < 0 else min(size, 65536)
        payload = self.stream.read(min(size, self.byte_limit - self.total + 1))
        self.total += len(payload)
        if self.total > self.byte_limit:
            raise ValueError("XMLTV decompressed past safety limit")
        marker = (self.tail + payload).upper()
        if b"<!DOCTYPE" in marker or b"<!ENTITY" in marker:
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
        for event, node in ET.iterparse(_LimitedXmlInput(stream, max_expanded), events=("start", "end")):
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
                     "event_type": name, "session": session, "title": "Formula 1 %s — %s" % (place, name),
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
            home = row.get("teams", {}).get("home", {}).get("name") or "TBC"
            away = row.get("teams", {}).get("away", {}).get("name") or "TBC"
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
        except (ValueError, KeyError, TypeError):
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
            elif row.get("dateEvent") and row.get("strTime"):
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
            events.append({"id": "thesportsdb:%s" % row["idEvent"], "sport": row.get("strSport") or "other",
                           "competition": row.get("strLeague") or "", "competition_country": row.get("strCountry") or "",
                           "event_type": "match" if len(participants) == 2 else "event",
                           "title": row.get("strEvent") or (" v ".join(participants)), "participants": participants,
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
            for day in range(min(days, horizon_days)):
                day_start = start + timedelta(days=day)
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
    """Parse community-maintained Bundesliga match records (no supplied secret).

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
            events.append({
                "id": "openligadb:%s" % m["matchID"],
                "sport": "football", "competition": m.get("leagueName") or "German Bundesliga",
                "competition_code": "old:%s" % shortcut, "competition_country": "Germany",
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
