"""Cross-source event fusion, the grouped "today" view and EPG broadcast candidates.

A fixture reported by two independent provider families is "corroborated";
one family is "reported". EPG programme matches are *candidates*: they name a
recognised channel whose guide shows a programme covering kick-off whose
title/sub-title contains both teams. They never set broadcast_verified,
because guide upstream lineage is not yet proven independent.
"""
import re
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import taxonomy
from .guide import canonical_channel
from .providers import EPG_FAMILY, SPORT_FAMILY

LONDON = ZoneInfo("Europe/London")
UNCONFIRMED_START_PRECISIONS = frozenset({"date_only", "time_tbc"})
PRECISION_RANK = {"scheduled": 0, "provisional": 1, "not_before": 2, "estimated": 3, "time_tbc": 4, "date_only": 5}
SOURCE_PREFERENCE = ["football_data", "openligadb", "jolpica", "openf1", "cricketdata", "api_sports"]
FEATURED_TAGS = {"team:england", "team:england_women", "team:scotland", "team:wales", "team:northern_ireland",
                 "team:ireland", "team:lions", "team:great_britain", "ppv"}

_STOP = {"fc", "afc", "cf", "sc", "ac", "club", "the", "de", "cd", "ud", "sv", "fk", "sk", "bk", "if", "and",
         "v", "vs", "calcio", "1", "football", "rfc", "rlfc", "cc", "ccc"}
_ABBR = {"man": "manchester", "utd": "united", "spurs": "tottenham", "wolves": "wolverhampton",
         "nottm": "nottingham", "munchen": "munich", "w": "women", "womens": "women", "ladies": "women", "st": "saint"}
_VARIANT = {"women", "u17", "u18", "u19", "u20", "u21", "u23", "ii", "b", "reserves", "xi", "a", "jong"}
# Suffix words that may be dropped without changing a club's identity
# ("Leeds" == "Leeds United"). Anything else that differs (Miami, Northern,
# Queens Park, Saint Germain) makes it a different team.
_GENERIC = {"city", "united", "town", "county", "rovers", "athletic", "albion", "wanderers", "hotspur", "hove",
            "fc", "afc", "club", "calcio", "football"}
# Words a programme title may wrap around a fixture without naming a team.
_PROGRAMME_WORDS = {"live", "ppv", "premier", "league", "football", "rugby", "cricket", "cup", "final", "semi", "quarter",
                    "round", "match", "coverage", "uefa", "champions", "europa", "conference", "fa", "efl", "carabao",
                    "championship", "super", "sunday", "monday", "friday", "saturday", "night", "nations", "series",
                    "international", "internationals", "friendly", "qualifier", "qualifiers", "world", "euro", "the",
                    "and", "on", "in", "at", "of", "game", "day", "matchday", "sports", "sport", "tv"}
_SIDES = re.compile(r"\b(?:v|vs|versus)\b")
_NEGATIVE = re.compile(r"\b(highlights|review|reaction|preview|classic|replay|rewind|magazine|best of|goals show|"
                       r"build up|countdown|extra|debate|analysis|recap|delayed)\b")
_MAX_PROGRAMME = timedelta(hours=9)
_SESSION_WORDS = {"race": ("race", "grand prix"), "qualifying": ("qualifying",), "sprint": ("sprint",),
                  "sprint_qualifying": ("sprint qualifying", "sprint shootout"),
                  "practice1": ("practice",), "practice2": ("practice",), "practice3": ("practice",)}


def _dt(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def tokens(text):
    out = []
    for token in taxonomy.norm(text).split():
        out.extend(_ABBR.get(token, token).split())
    return out


def team_key(name):
    return frozenset(t for t in tokens(name) if t not in _STOP)


def same_team(a, b):
    if not a or not b or "tbc" in a or "tbc" in b:
        return False
    if (a & _VARIANT) != (b & _VARIANT):
        return False
    if a == b:
        return True
    small, large = (a, b) if len(a) < len(b) else (b, a)
    return small < large and bool(small - _GENERIC) and (large - small) <= _GENERIC


def _source_rank(source_id):
    try:
        return SOURCE_PREFERENCE.index(source_id)
    except ValueError:
        return len(SOURCE_PREFERENCE) + (0 if source_id.startswith("api_sports") else 1)


def _quality(event):
    return (PRECISION_RANK.get(event.get("start_precision"), 6), _source_rank(event.get("source_id", "")))


def _sport_family(sport):
    return "rugby" if sport in ("rugby", "rugby_union", "rugby_league") else sport


def _same_event(a, b):
    if _sport_family(a["sport"]) != _sport_family(b["sport"]):
        return False
    gap = abs((a["_start"] - b["_start"]).total_seconds())
    if a["sport"] == "motorsport":
        return (a.get("competition_id") and a.get("competition_id") == b.get("competition_id")
                and a.get("session") and a.get("session") == b.get("session") and gap <= 5400)
    if gap > 3 * 3600:
        return False
    ca, cb = a.get("competition_id"), b.get("competition_id")
    if ca and cb and ca != cb:
        return False
    ta, tb = a["_teams"], b["_teams"]
    if len(ta) == 2 and len(tb) == 2:
        return ((same_team(ta[0], tb[0]) and same_team(ta[1], tb[1])) or
                (same_team(ta[0], tb[1]) and same_team(ta[1], tb[0])))
    return gap <= 1800 and taxonomy.norm(a.get("title")) == taxonomy.norm(b.get("title"))


def merge_events(events):
    """Fuse duplicate fixtures across providers; keep the most precise record as primary."""
    latest = {}
    for event in events:  # a later copy of the same provider id is the fresher one
        if isinstance(event, dict) and event.get("id"):
            latest[event["id"]] = event
    prepared = []
    for event in latest.values():
        try:
            row = dict(event)
            row["_start"] = _dt(event["start_utc"])
            row["_teams"] = [team_key(p) for p in event.get("participants") or []][:2]
            prepared.append(row)
        except (KeyError, ValueError, TypeError):
            continue
    buckets = defaultdict(list)
    for index, row in enumerate(prepared):
        buckets[(_sport_family(row["sport"]), int(row["_start"].timestamp() // 10800))].append(index)
    parent = list(range(len(prepared)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for (sport, bucket), members in buckets.items():
        neighbours = members + buckets.get((sport, bucket + 1), [])
        for i in members:
            for j in neighbours:
                if j <= i or find(i) == find(j):
                    continue
                if prepared[i]["source_id"] != prepared[j]["source_id"] and _same_event(prepared[i], prepared[j]):
                    parent[find(j)] = find(i)
    groups = defaultdict(list)
    for index in range(len(prepared)):
        groups[find(index)].append(prepared[index])
    merged = []
    for rows in groups.values():
        rows.sort(key=_quality)
        primary = dict(rows[0])
        sources = sorted({r["source_id"] for r in rows})
        families = sorted({SPORT_FAMILY.get(s, s) for s in sources})
        starts = {r["source_id"]: r["start_utc"] for r in rows}
        spread = max(r["_start"] for r in rows) - min(r["_start"] for r in rows)
        if not primary.get("end_utc"):
            ends = [r["end_utc"] for r in rows if r.get("end_utc")]
            if ends:
                primary["end_utc"] = ends[0]
        primary.update({
            "sources": sources, "source_events": sorted(r["id"] for r in rows),
            "corroboration": len(families),
            "fixture_confidence": "corroborated" if len(families) > 1 else "reported",
            "start_conflict": spread > timedelta(minutes=15),
        })
        if primary["start_conflict"]:
            primary["start_alternatives"] = starts
        primary.pop("_start", None)
        primary.pop("_teams", None)
        merged.append(primary)
    merged.sort(key=lambda e: e.get("start_utc", ""))
    return merged


def live_state(event, now):
    if event.get("live_status_unconfirmed"):
        return "unknown"
    status = event.get("status_normalized") or "unknown"
    if status == "live" and event.get("live_observed_at"):
        try:
            if now - _dt(event["live_observed_at"]) > timedelta(minutes=45):
                return "unknown"
        except (TypeError, ValueError):
            return "unknown"
    if status in ("finished", "postponed", "cancelled"):
        return status
    try:
        start = _dt(event["start_utc"])
    except (KeyError, ValueError, TypeError):
        return "unknown"
    typical = timedelta(minutes=taxonomy.typical_minutes(event.get("sport")))
    # A provider "live" flag is trusted only near the event; a stale snapshot or
    # an expanded future cricket day must not stay LIVE indefinitely.
    if status == "live" and start - timedelta(minutes=30) <= now < start + typical * 1.5:
        return "live"
    if event.get("start_precision") in UNCONFIRMED_START_PRECISIONS:
        return "time_tbc"
    end = _dt(event["end_utc"]) if event.get("end_utc") else start + typical
    if start <= now < end:
        return "live_probable"
    if now >= end:
        return "probably_finished"
    return "upcoming"


def _programme_index(epg_guides, window_start, window_end):
    """Recognised-channel programmes overlapping the window: (start, end, tokens, text, live, channel...)."""
    rows = []
    guides = epg_guides.items() if isinstance(epg_guides, dict) else epg_guides
    for source_id, guide in guides:
        channels = guide.get("channels", {})
        identity = {}
        for programme in guide.get("programmes", []):
            try:
                start, end = _dt(programme["start_utc"]), _dt(programme["end_utc"])
            except (KeyError, ValueError, TypeError):
                continue
            if end <= window_start or start >= window_end or programme.get("is_repeat") or end - start > _MAX_PROGRAMME:
                continue
            channel_id = programme.get("channel_id", "")
            if channel_id not in identity:
                identity[channel_id] = canonical_channel(source_id, channel_id, channels.get(channel_id, channel_id))
            canonical = identity[channel_id]
            if not canonical or ".news" in canonical:
                continue
            text = taxonomy.norm("%s %s" % (programme.get("title", ""), programme.get("subtitle", "")))
            if _NEGATIVE.search(text):
                continue
            parts = [taxonomy.norm(programme.get("title", "")), taxonomy.norm(programme.get("subtitle", ""))]
            rows.append((start, end, [p for p in parts if p], text, bool(programme.get("is_live")), canonical,
                         channels.get(channel_id, channel_id), source_id))
    return rows


def _side_matches(segment, team, allowed):
    words = set(tokens(segment)) - _STOP
    return bool(team) and "tbc" not in team and team <= words and (words - team) <= allowed


def _fixture_in(text, home, away, allowed):
    """True when text names the fixture as '<home> v <away>' (either order) with nothing but programme words around it."""
    sides = _SIDES.split(text)
    if len(sides) != 2:
        return False
    left, right = sides
    return ((_side_matches(left, home, allowed) and _side_matches(right, away, allowed)) or
            (_side_matches(left, away, allowed) and _side_matches(right, home, allowed)))


def _matches(event, row):
    parts, text = row[2], row[3]
    if event.get("sport") == "motorsport":
        if not re.search(r"\b(f1|formula 1|formula one|grand prix)\b", text):
            return False
        session = event.get("session")
        if any(w in text for other, words in _SESSION_WORDS.items() if other != session and other[:8] != (session or "")[:8]
               for w in words if w not in _SESSION_WORDS.get(session, ())):
            return False
        return any(w in text for w in _SESSION_WORDS.get(session, ()))
    teams = [team_key(p) for p in event.get("participants") or []][:2]
    if len(teams) != 2:
        return False
    allowed = _PROGRAMME_WORDS | set(tokens(event.get("competition", "")))
    return any(_fixture_in(part, teams[0], teams[1], allowed) for part in parts)


def broadcast_candidates(events, epg_guides, now):
    """Return {event_id: (status, [candidate...])} for the given events."""
    timed = []
    for event in events:
        if event.get("start_precision") in UNCONFIRMED_START_PRECISIONS:
            continue
        try:
            timed.append((event, _dt(event["start_utc"])))
        except (KeyError, TypeError, ValueError):
            continue
    if not timed or not epg_guides:
        return {}
    starts = [start for _, start in timed]
    # A programme starting earlier can still cover kickoff. Index by its end
    # so long programmes remain eligible without rescanning expired rows.
    rows = _programme_index(epg_guides, min(starts), max(starts) + timedelta(minutes=21))
    by_end = sorted(enumerate(rows), key=lambda item: item[1][1])
    ends = [row[1] for _, row in by_end]
    result = {}
    for event, start in timed:
        found = {}
        earliest_end = start + timedelta(minutes=30)
        latest_start = start + timedelta(minutes=20)
        first = bisect_left(ends, earliest_end)
        # Keep source order when choosing the representative channel name
        # and programme times for a service reported by multiple guides.
        for _, row in sorted(item for item in by_end[first:] if item[1][0] <= latest_start):
            if not _matches(event, row):
                continue
            canonical = row[5]
            entry = found.setdefault(canonical, {"canonical_channel_id": canonical, "channel_name": row[6][:120],
                                                 "programme_start_utc": row[0].isoformat(timespec="seconds"),
                                                 "programme_end_utc": row[1].isoformat(timespec="seconds"),
                                                 "epg_live_flag": False, "epg_sources": [], "match_basis": "epg_title_teams"})
            entry["epg_live_flag"] = entry["epg_live_flag"] or row[4]
            if row[7] not in entry["epg_sources"]:
                entry["epg_sources"].append(row[7])
        candidates = sorted(found.values(), key=lambda c: c["canonical_channel_id"])
        if not candidates:
            continue
        multi = any(len({EPG_FAMILY.get(s, s) for s in c["epg_sources"]}) > 1 for c in candidates)
        result[event["id"]] = ("multi_guide_match" if multi else "single_guide_match", candidates)
    return result


def build_today(events, now, epg_guides=None):
    today = now.astimezone(LONDON).date()
    todays = []
    for event in events:
        try:
            if _dt(event["start_utc"]).astimezone(LONDON).date() == today:
                todays.append(dict(event, live_state=live_state(event, now)))
        except (KeyError, ValueError, TypeError):
            continue
    links = broadcast_candidates(todays, epg_guides or {}, now)
    for event in todays:
        status, candidates = links.get(event["id"], ("none", []))
        event["broadcast_status"] = status
        event["broadcast_candidates"] = candidates
    sports = defaultdict(lambda: defaultdict(list))
    labels = {}
    for event in todays:
        sports[event["sport"]][event["category_id"]].append(event)
        labels[event["category_id"]] = (event["category_label"], event["category_priority"])
    grouped = []
    for sport in sorted(sports, key=taxonomy.sport_order):
        categories = []
        for cid in sorted(sports[sport], key=lambda c: (labels[c][1], labels[c][0])):
            rows = sorted(sports[sport][cid], key=lambda e: e["start_utc"])
            categories.append({"id": cid, "label": labels[cid][0], "count": len(rows), "events": rows})
        grouped.append({"sport": sport, "label": taxonomy.SPORTS[sport][0],
                        "count": sum(c["count"] for c in categories), "categories": categories})
    featured = [e for e in sorted(todays, key=lambda e: e["start_utc"]) if FEATURED_TAGS & set(e.get("tags", []))]
    return {"date": today.isoformat(), "generated_at": now.isoformat(timespec="seconds"),
            "count": len(todays), "live_now": sum(e["live_state"] in ("live", "live_probable") for e in todays),
            "featured": featured, "sports": grouped,
            "note": "Fixtures are provider-reported; EPG channel matches are unverified candidates."}
