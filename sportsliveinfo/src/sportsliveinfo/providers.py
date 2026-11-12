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
EPG = {
    "farleyflex": ("UK sports · farleyflex", "https://raw.githubusercontent.com/farleyflex/epg-guide/main/epg.xml"),
    "fr_programmetv": ("France · programme-tv.net", "https://iptv-org.github.io/epg/guides/fr/programme-tv.net.epg.xml.gz"),
    "fr_telerama": ("France · Télérama", "https://iptv-org.github.io/epg/guides/fr/telerama.fr.epg.xml.gz"),
    "fr_xmltv": ("France · XMLTV France", "https://xmltvfr.fr/xmltv/xmltv_fr.xml.gz"),
}
SPORTS = {
    "jolpica": ("Formula 1 · Jolpica", "https://api.jolpi.ca/ergast/f1/current.json", None, 6),
    "football_data": ("Football · football-data.org", "https://api.football-data.org/v4/matches", "football_data", 45),
    "api_sports": ("Football · API-Sports", "https://v3.football.api-sports.io/fixtures", "api_sports", 80),
}
ALLOW_HOSTS = {urllib.parse.urlparse(item[1]).hostname for item in list(EPG.values()) + list(SPORTS.values())}


class RedirectGuard(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        verify_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def verify_url(url):
    u = urllib.parse.urlsplit(url)
    if u.scheme != "https" or u.hostname not in ALLOW_HOSTS or u.username or u.password or u.port not in (None, 443):
        raise ValueError("Source URL is not on the approved HTTPS provider list")


def fetch(url, headers=None, max_bytes=14_000_000):
    verify_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": "SportsLiveInfo/0.1 (self-hosted EPG and sports collector)", **(headers or {})})
    opener = urllib.request.build_opener(RedirectGuard())
    try:
        with opener.open(request, timeout=20) as response:
            # +1 permits explicit rejection without unbounded memory consumption.
            data = response.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise ValueError("Provider response exceeded configured size limit")
            return data
    except urllib.error.HTTPError as exc:
        raise RuntimeError("HTTP %d from upstream" % exc.code) from None
    except urllib.error.URLError:
        raise RuntimeError("Upstream network request failed") from None


def xmltv_time(value):
    value = (value or "").strip()
    for fmt in ("%Y%m%d%H%M%S %z", "%Y%m%d%H%M %z"):
        try:
            return datetime.strptime(value, fmt).astimezone(timezone.utc).isoformat(timespec="seconds")
        except ValueError:
            pass
    raise ValueError("XMLTV time missing explicit UTC offset or invalid")


def decode_xmltv(raw, source, max_expanded=65_000_000, max_programmes=100_000):
    """Reject unbounded downloads, XML entities and invalid intervals."""
    if raw[:2] == b"\x1f\x8b":
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as f:
            payload = f.read(max_expanded + 1)
    else:
        payload = raw
    if len(payload) > max_expanded:
        raise ValueError("XMLTV decompressed past safety limit")
    if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise ValueError("XMLTV declarations and entities are not allowed")
    channels, programmes, bad = {}, [], 0
    root = None
    for event, node in ET.iterparse(io.BytesIO(payload), events=("start", "end")):
        if root is None:
            root = node
            if root.tag != "tv":
                raise ValueError("Not an XMLTV programme guide")
        if event != "end":
            continue
        if node.tag == "channel":
            channel_id = node.get("id", "")[:180]
            name = node.findtext("display-name") or channel_id
            if channel_id:
                channels[channel_id] = name[:180]
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
                    "description": (node.findtext("desc") or "")[:1000],
                    "language": title_node.get("lang", "")[:12] if title_node is not None else "",
                    "source_id": source,
                })
            except ValueError:
                bad += 1
            node.clear()
            if root is not None:
                root.clear()
    return {"source_id": source, "channels": channels, "programmes": programmes,
            "invalid_programmes": bad, "source_redistribution_approved": False}


def f1_events(data):
    obj = json.loads(data)
    rows = obj.get("MRData", {}).get("RaceTable", {}).get("Races", [])
    events = []
    for race in rows:
        try:
            circuit = race.get("Circuit", {})
            location = circuit.get("Location", {})
            season, round_ = str(race["season"]), str(race["round"])
            sessions = [("race", race)]
            sessions.extend((key, race[key]) for key in ("FirstPractice", "SecondPractice", "ThirdPractice", "Qualifying", "Sprint", "SprintQualifying") if key in race)
            for kind, entry in sessions:
                if not entry.get("date") or not entry.get("time"):
                    continue
                utc = datetime.fromisoformat(entry["date"] + "T" + entry["time"].replace("Z", "+00:00")).astimezone(timezone.utc)
                events.append({"id": f"f1:{season}:{round_}:{kind}", "sport": "motorsport", "competition": "Formula 1", "event_type": kind,
                               "title": race.get("raceName", "Formula 1"), "start_utc": utc.isoformat(timespec="seconds"), "start_precision": "scheduled",
                               "venue": circuit.get("circuitName", ""), "country": location.get("country", ""),
                               "source_id": "jolpica", "broadcasts": [], "broadcast_verified": False})
        except (KeyError, ValueError, TypeError):
            continue
    return events


def football_data_events(data):
    matches = json.loads(data).get("matches", [])
    events = []
    for m in matches:
        try:
            when = m.get("utcDate")
            if not when:
                continue
            utc = datetime.fromisoformat(when.replace("Z", "+00:00")).astimezone(timezone.utc)
            home = m.get("homeTeam", {}).get("name") or "TBC"
            away = m.get("awayTeam", {}).get("name") or "TBC"
            events.append({"id": "football-data:%s" % m["id"], "sport": "football", "competition": m.get("competition", {}).get("name", ""),
                           "event_type": "match", "title": f"{home} v {away}", "participants": [home, away], "start_utc": utc.isoformat(timespec="seconds"),
                           "start_precision": "scheduled", "status": m.get("status", "SCHEDULED"), "venue": m.get("venue") or "",
                           "source_id": "football_data", "broadcasts": [], "broadcast_verified": False})
        except (ValueError, KeyError, TypeError):
            continue
    return events


def api_sports_events(data):
    rows = json.loads(data).get("response", [])
    events = []
    for row in rows:
        try:
            fixture = row["fixture"]
            when = datetime.fromisoformat(fixture["date"].replace("Z", "+00:00")).astimezone(timezone.utc)
            home = row.get("teams", {}).get("home", {}).get("name") or "TBC"
            away = row.get("teams", {}).get("away", {}).get("name") or "TBC"
            events.append({"id": f"api-sports:{fixture['id']}", "sport": "football", "competition": row.get("league", {}).get("name", ""),
                           "event_type": "match", "title": f"{home} v {away}", "participants": [home, away],
                           "start_utc": when.isoformat(timespec="seconds"), "start_precision": "scheduled",
                           "status": fixture.get("status", {}).get("short", "NS"), "venue": (fixture.get("venue") or {}).get("name") or "",
                           "source_id": "api_sports", "broadcasts": [], "broadcast_verified": False})
        except (ValueError, KeyError, TypeError):
            continue
    return events
