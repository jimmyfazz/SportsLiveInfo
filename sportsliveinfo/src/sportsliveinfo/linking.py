"""Cross-source event fusion, the grouped "today" view and EPG broadcast candidates.

A fixture reported by two independent provider families is "corroborated";
one family is "reported". EPG programme matches are *candidates*: they name a
recognised channel whose guide shows a programme covering kick-off whose
title/sub-title identifies the fixture or a named tournament session. They never set broadcast_verified,
because guide upstream lineage is not yet proven independent.
"""
import hashlib
import re
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

from . import dictionary as channel_dictionary, taxonomy
from .guide import (COUNTRY_BY_SOURCE, REGIONAL_PARENTS, canonical_channel, channel_families, foreign_guide_channel,
                    normalized_name)
from .identity import name_signature
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
         "nottm": "nottingham", "munchen": "munich", "w": "women", "womens": "women", "ladies": "women", "st": "saint",
         "cymru": "wales", "lloegr": "england", "rep": "republic", "ny": "new york"}
# Alias expansion is deliberately exact and small. Feed-provided short names are
# also considered below; arbitrary fuzzy/substring team matching is not safe.
_TEAM_ALIASES = {
    "man city": "manchester city", "man utd": "manchester united", "man united": "manchester united",
    "nottm forest": "nottingham forest", "notts forest": "nottingham forest",
    "west brom": "west bromwich albion", "wba": "west bromwich albion",
    "qpr": "queens park rangers", "nz": "new zealand", "all blacks": "new zealand",
    "springboks": "south africa", "wallabies": "australia",
    "yr alban": "scotland", "gogledd iwerddon": "northern ireland", "iwerddon": "ireland",
}
_VARIANT = {"women", "u17", "u18", "u19", "u20", "u21", "u23", "ii", "b", "reserves", "xi", "a", "jong"}
# Suffix words that may be dropped without changing a club's identity
# ("Leeds" == "Leeds United"). Anything else that differs (Miami, Northern,
# Queens Park, Saint Germain) makes it a different team.
_GENERIC = {"city", "united", "town", "county", "rovers", "athletic", "albion", "wanderers", "hotspur", "hove",
            "fc", "afc", "club", "calcio", "football"}
# These words can occur in place names but are too weak to identify a team by
# themselves. Keep them when comparing names; never use them as the required
# evidence for a side (e.g. "West v North").
_LOW_SIGNAL_TEAM_TOKENS = {"new", "north", "south", "east", "west"}
# Words a programme title may wrap around a fixture without naming a team.
_PROGRAMME_WORDS = {"live", "ppv", "premier", "league", "football", "rugby", "cricket", "cup", "final", "semi", "quarter",
                    "round", "match", "coverage", "uefa", "champions", "europa", "conference", "fa", "efl", "carabao",
                    "championship", "super", "sunday", "monday", "friday", "saturday", "night", "nations", "series",
                    "international", "internationals", "friendly", "qualifier", "qualifiers", "world", "euro", "the",
                    "and", "on", "in", "at", "of", "game", "day", "matchday", "sports", "sport", "tv"}
_SIDES = re.compile(r"\b(?:v|vs|versus)\b|\s+@\s+")
_NEGATIVE = re.compile(r"\b(highlights|review|reaction|preview|classic|replay|rewind|magazine|best of|goals show|"
                       r"build up|countdown|extra|debate|analysis|recap|delayed|"
                       # Audio-only coverage on a TV channel (e.g. a club channel's "Radio Commentary"):
                       # the match is not shown, so it is never a viewing candidate.
                       r"radio commentary|audio commentary|commentary only|radio coverage|audio only)\b")
_MAX_PROGRAMME = timedelta(hours=9)
_SESSION_WORDS = {"race": ("race", "grand prix"), "qualifying": ("qualifying",), "sprint": ("sprint",),
                  "sprint_qualifying": ("sprint qualifying", "sprint shootout"),
                  "practice1": ("practice",), "practice2": ("practice",), "practice3": ("practice",)}


# Named events only. Broad tours and ambiguous labels such as "The Masters"
# require sport context in the programme or an unambiguous alternative name.
_TOURNAMENT_NAMES = {
    "golf": (
        ("masters tournament", "us masters", "augusta masters", "the masters"),
        ("pga championship", "us pga championship"),
        ("us open golf", "u s open golf", "us open", "u s open"),
        ("the open championship", "the open"),
        ("ryder cup",), ("solheim cup",),
    ),
    "snooker": (
        ("world snooker championship", "world championship snooker"),
        ("uk snooker championship", "snooker uk championship", "uk championship"),
        ("masters snooker", "snooker masters", "the masters"),
        ("champion of champions snooker", "snooker champion of champions", "champion of champions"),
    ),
    "cycling": (
        ("tour de france",), ("giro d italia",), ("vuelta a espana", "la vuelta"),
    ),
    "darts": (
        ("pdc world championship", "pdc world darts championship", "world darts championship"),
        ("premier league darts", "darts premier league"),
        ("world matchplay darts", "darts world matchplay", "world matchplay"),
        ("grand slam of darts",),
    ),
    "athletics": (("world athletics championships",),),
    "horse_racing": (
        ("cheltenham festival", "cheltenham"), ("royal ascot",),
        ("grand national", "aintree grand national"), ("glorious goodwood",),
    ),
}
_AMBIGUOUS_TITLES = frozenset({
    "the masters", "us open", "u s open", "the open", "the open championship",
    "uk championship", "champion of champions", "world matchplay", "cheltenham",
})
_TOURNAMENT_QUALIFIER = re.compile(
    r"\b(stage|round|day|night|session) (\d{1,2})\b|"
    r"\b(quarter finals?|semi finals?|quarterfinals?|semifinals?|finals?|"
    r"morning|afternoon|evening|qualifying|qualification)\b"
)
_UNMAPPED_TITLE = re.compile(
    r"\b(?:" + "|".join(re.escape(name) for groups in _TOURNAMENT_NAMES.values()
                         for aliases in groups for name in aliases)
    + r"|f1|formula 1|formula one|v|vs|versus)\b"
)

_WOMENS_VARIANTS = frozenset({"women", "womens", "ladies", "femmes", "femenina", "femminile"})
_TOURNAMENT_VARIANT = re.compile(r"\b(women|womens|ladies|femmes|femenina|femminile|w|junior|juniors|u\s*[-]?\s*(?:23|21|20|19|18|17)|seniors|senior|indoor|indoors|para|paralympic|virtual)\b")
_RADIO_OR_SHOPPING = re.compile(r"\b(radio|shopping|shop|retail|qvc|ideal world|bid tv)\b")
_CHANNEL_SPORT_HINTS = {
    "football": {"football", "soccer"}, "rugby": {"rugby"}, "cricket": {"cricket"},
    "tennis": {"tennis"}, "motorsport": {"f1", "formula", "motogp", "moto gp", "motorsport"},
    "horse_racing": {"horse racing", "racing tv", "at the races"}, "golf": {"golf"},
    "basketball": {"basketball", "nba"}, "american_football": {"nfl", "american football"},
    "ice_hockey": {"ice hockey", "nhl", "hockey"}, "baseball": {"baseball", "mlb"},
    "boxing": {"boxing", "box office", "ppv"}, "mma": {"mma", "ufc"},
    "darts": {"darts"}, "snooker": {"snooker"}, "cycling": {"cycling"},
    "athletics": {"athletics"}, "handball": {"handball"}, "volleyball": {"volleyball"},
    "aussie_rules": {"aussie rules", "afl"}, "netball": {"netball"},
}


def _dt(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def tokens(text):
    normal = taxonomy.norm(text)
    normal = _TEAM_ALIASES.get(normal, normal)
    out = []
    for token in normal.split():
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


def _registry_channel_id(source_id, channel_id, display_name):
    return canonical_channel(source_id, channel_id, display_name)


def _identity_members(identity_document):
    members, clusters = {}, {}
    if not isinstance(identity_document, dict):
        return members, clusters
    for cluster in identity_document.get("channels", []):
        if not isinstance(cluster, dict) or not cluster.get("id"):
            continue
        cluster_id = str(cluster["id"])
        clusters[cluster_id] = cluster
        for member in cluster.get("members", []):
            if isinstance(member, dict) and member.get("source_id") and member.get("channel_id"):
                members[(str(member["source_id"]), str(member["channel_id"]))] = cluster_id
    return members, clusters


_TIMESHIFT_FEED = re.compile(r"(?:plus\s*[12]|\+\s*[12]|timeshift|1hr|2hr)", re.I)


def _dictionary_hit(resolver, source_id, display_name, channel_id=None):
    market = COUNTRY_BY_SOURCE.get(source_id)
    if resolver is None or not market or foreign_guide_channel(market, channel_id):
        return None
    hit = resolver.resolve(display_name, market)
    if not hit or hit.get("confidence") != "high":
        return None
    if {"ts1", "ts2"} & name_signature(display_name)[0] or any(
            entry and entry[1] and _TIMESHIFT_FEED.search(str(entry[1])) for entry in hit.get("ids", [])):
        return None                       # a timeshift feed must never resolve to its base channel id
    ids = {entry[0] for entry in hit.get("ids", []) if entry and entry[0]}
    if len(ids) != 1:
        return None
    channel_id = next(iter(ids))
    channel = resolver.channels.get(channel_id, {})
    if channel.get("closed"):
        return None
    return channel_id, tuple(channel.get("categories", []))


def _channel_identity_index(epg_guides, dictionary_document=None, identity_document=None):
    """Resolve guide channels through the curated registry, identity graph and dictionary.

    Identity auto-ids are revision-scoped, so only curated identity ids or a
    unique stable dictionary id are returned as candidate keys.
    """
    try:
        resolver = channel_dictionary.Resolver(dictionary_document) if isinstance(dictionary_document, dict) else None
    except (KeyError, TypeError, ValueError):
        resolver = None
    member_cluster, clusters = _identity_members(identity_document)
    guides = list(epg_guides.items()) if isinstance(epg_guides, dict) else list(epg_guides)
    names = {(source_id, str(channel_id)): str(name)
             for source_id, guide in guides
             for channel_id, name in (guide.get("channels") or {}).items()}
    dictionary_by_cluster = defaultdict(set)
    category_by_dictionary_id = {}
    if resolver:
        for member, cluster_id in member_cluster.items():
            name = names.get(member)
            if not name:
                continue
            hit = _dictionary_hit(resolver, member[0], name, member[1])
            if hit:
                dictionary_by_cluster[cluster_id].add(hit[0])
                category_by_dictionary_id[hit[0]] = hit[1]
    # One identity per service: when a guide channel has both a registry id and a
    # unique dictionary id, every other channel resolving to that dictionary id is
    # reported under the registry id (e.g. ITV1.uk -> gb.itv.one).
    registry_for_dictionary = defaultdict(set)
    if resolver:
        for source_id, guide in guides:
            for channel_id, name in (guide.get("channels") or {}).items():
                registry_id = _registry_channel_id(source_id, channel_id, name)
                hit = registry_id and _dictionary_hit(resolver, source_id, name, channel_id)
                if hit:
                    registry_for_dictionary[hit[0]].add(registry_id)
    alias = {dict_id: next(iter(ids)) for dict_id, ids in registry_for_dictionary.items() if len(ids) == 1}
    index = {}
    for source_id, guide in guides:
        for channel_id, name in (guide.get("channels") or {}).items():
            key = (source_id, str(channel_id))
            cluster_id = member_cluster.get(key)
            cluster = clusters.get(cluster_id, {}) if cluster_id else {}
            canonical = _registry_channel_id(source_id, channel_id, name)
            if canonical:
                index[key] = (canonical, "registry", "high", ())
                continue
            if cluster.get("curated") and cluster.get("id"):
                index[key] = (str(cluster["id"]), "identity_registry", "high", ())
                continue
            hit = _dictionary_hit(resolver, source_id, name, channel_id)
            if hit:
                index[key] = (alias.get(hit[0], hit[0]), "dictionary", "high", hit[1])
                continue
            if cluster_id and len(dictionary_by_cluster.get(cluster_id, ())) == 1:
                stable_id = next(iter(dictionary_by_cluster[cluster_id]))
                index[key] = (alias.get(stable_id, stable_id), "identity_dictionary", "high",
                              category_by_dictionary_id.get(stable_id, ()))
    return index, guides


def _programme_index(epg_guides, window_start, window_end, *, include_non_matches=False, coverage=None,
                     channel_identities=None):
    """Index programmes in the window and optionally measure guide dates and unmapped titles."""
    rows = []
    guides = epg_guides.items() if isinstance(epg_guides, dict) else epg_guides
    for source_id, guide in guides:
        if coverage is not None:
            coverage.setdefault(source_id, (None, None))
        channels = guide.get("channels", {})
        identity = {}
        for programme in guide.get("programmes", []):
            channel_id = programme.get("channel_id", "")
            if channel_id not in identity:
                key = (source_id, str(channel_id))
                identity[channel_id] = (channel_identities or {}).get(key) or (
                    _registry_channel_id(source_id, channel_id, channels.get(channel_id, channel_id)),
                    "registry", "high", ())
            canonical, mapping_method, mapping_confidence, dictionary_categories = identity[channel_id]
            if coverage is None and not canonical:
                continue
            try:
                start, end = _dt(programme["start_utc"]), _dt(programme["end_utc"])
            except (KeyError, ValueError, TypeError):
                continue
            if end <= start:
                continue
            if coverage is not None:
                first, last = coverage[source_id]
                coverage[source_id] = (min(first, start) if first else start, max(last, end) if last else end)
            if end <= window_start or start >= window_end or programme.get("is_repeat") or end - start > _MAX_PROGRAMME:
                continue
            if canonical and ".news" in canonical:
                continue
            text = taxonomy.norm("%s %s" % (programme.get("title", ""), programme.get("subtitle", "")))
            excluded = bool(_NEGATIVE.search(text))
            if not canonical and (excluded or not _UNMAPPED_TITLE.search(text)):
                continue
            if excluded and not include_non_matches:
                continue
            parts = [] if excluded else _listing_parts(programme)
            channel_name = channels.get(channel_id, channel_id)
            rows.append((start, end, [p for p in parts if p], text, bool(programme.get("is_live")), canonical,
                         channel_name, source_id, mapping_method, mapping_confidence, dictionary_categories,
                         (str(programme.get("title") or ""), str(programme.get("subtitle") or ""))))
    return rows


_LISTING_DATE = re.compile(r"\s+\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?\s*$")
_LISTING_TAG = re.compile(r"\s*[\[(](?:new|live|hd|s|r|repeat|premiere)[\])]\s*", re.I)
# Some guides prefix team names with a pictogram and league tag ("\u26bd [EPL] Chelsea").
_LISTING_BADGE = re.compile(r"[\u2600-\u27bf\U0001f300-\U0001faff]\ufe0f?\s*(?:\[[A-Za-z0-9]{2,6}\]\s*)?")
# Competitions whose name already means the women's game ("Live WSL: Spurs v Everton").
_WOMENS_COMPETITION = re.compile(r"\b(wsl|wsl 2|barclays wsl|women s super league|womens super league|"
                                 r"women s championship|womens championship|lionesses|nwsl|swpl|wbbl|aflw)\b")


def _listing_parts(programme):
    """Title and subtitle, plus each side of a colon ("Northern Series: Wales v New Zealand")."""
    parts = []
    for field in ("title", "subtitle"):
        value = _clean_listing(programme.get(field, ""))
        pieces = value.split(":")
        candidates = [value] + [":".join(pieces[i:]) for i in range(1, len(pieces))] + \
                     [":".join(pieces[:i]) for i in range(1, len(pieces))]
        for candidate in candidates:
            normal = taxonomy.norm(candidate)
            if normal and normal not in parts:
                parts.append(normal)
    return parts


def _clean_listing(value):
    """Drop guide decorations that are not part of the fixture: a trailing "14.11" date, "[NEW]" or a league badge."""
    text = _LISTING_BADGE.sub(" ", _LISTING_TAG.sub(" ", str(value or "")))
    return _LISTING_DATE.sub("", text).strip()


def _side_matches(segment, team, allowed):
    words = set(tokens(segment)) - _STOP
    distinctive = set(team) - _GENERIC - _LOW_SIGNAL_TEAM_TOKENS
    extra = words - set(team) - _LOW_SIGNAL_TEAM_TOKENS
    # A guide may add a club suffix the feed omits ("Cheltenham" -> "Cheltenham Town",
    # "Brighton" -> "Brighton & Hove Albion"), as same_team allows. Only when the
    # feed's own suffix words are present too, so "Manchester City" never matches
    # "Manchester United".
    if set(team) & _GENERIC <= words:
        extra -= _GENERIC
    return (bool(distinctive) and "tbc" not in team and distinctive <= words and extra <= allowed)


def _fixture_in(text, home, away, allowed):
    """True when text names the fixture as '<home> v <away>' (either order) with nothing but programme words around it."""
    sides = _SIDES.split(text)
    if len(sides) != 2:
        return False
    left, right = sides
    return ((_side_matches(left, home, allowed) and _side_matches(right, away, allowed)) or
            (_side_matches(left, away, allowed) and _side_matches(right, home, allowed)))


def _team_options(event):
    """Return conservative full/short name alternatives for the two fixture sides."""
    return [list(side) for side in _team_options_cached(tuple(str(p) for p in event.get("participants") or []),
                                                         tuple(str(p or "") for p in event.get("participants_short") or []))]


@lru_cache(maxsize=50_000)      # per fixture names; the same event is checked against every programme
def _team_options_cached(participants, short):
    if len(participants) < 2:
        return ()
    options = []
    for index in range(2):
        names = [participants[index]]
        if len(short) > index and short[index]:
            names.append(short[index])
        keys = []
        for name in names:
            # Age/gender markers ("W", "U21") are checked by _event_identity_variants,
            # not required inside the team name ("Tottenham Hotspur W" == "Tottenham Hotspur").
            key = frozenset(team_key(name) - _VARIANT)
            if key and "tbc" not in key and set(key) - _GENERIC - _LOW_SIGNAL_TEAM_TOKENS:
                if key not in keys:
                    keys.append(key)
        options.append(tuple(keys))
    return tuple(options) if all(options) else ()


def _event_identity_variants(event):
    text = " ".join(str(event.get(field) or "") for field in
                    ("title", "competition", "round", "stage", "session"))
    text += " " + " ".join(str(name) for field in ("participants", "participants_short")
                            for name in (event.get(field) or []))
    return set(_identity_variants_of(text))


@lru_cache(maxsize=50_000)
def _identity_variants_of(text):
    variants = _tournament_variants(taxonomy.norm(text))
    return frozenset("women" if item == "w" else re.sub(r"\s*[- ]\s*", "", item) for item in variants
                     if item == "w" or item.startswith("u") or item in _WOMENS_VARIANTS or item == "women")


def _programme_identity_variants(text):
    variants = _tournament_variants(text)
    if _WOMENS_COMPETITION.search(text):
        variants.add("women")
    return {"women" if item == "w" else re.sub(r"\s*[- ]\s*", "", item) for item in variants
            if item == "w" or item.startswith("u") or item in _WOMENS_VARIANTS or item == "women"}


_IRISH_FEED_NAME = re.compile(r"\b(?:roi|ireland)\b|\(ie\)", re.I)


def _display_name_for(canonical, current, candidate):
    """The guide name shown for a UK service: a UK feed's name over an Irish feed's ("Sky Mix HD" over
    "Sky Mix HD ROI"), otherwise the first name seen (deterministic: rows are in guide order)."""
    if (str(canonical).startswith("gb.") and _IRISH_FEED_NAME.search(current or "")
            and not _IRISH_FEED_NAME.search(candidate or "")):
        return str(candidate)[:120]
    return current


def _eligibility_name(row):
    """The guide's display name plus the recognised service ("SkySp ActionHD" + gb.sky.sports.nfl): abbreviated
    names in id-based guides would otherwise look like non-sport channels."""
    canonical = row[5] or ""
    if not canonical:
        return row[6]
    return "%s %s" % (row[6], canonical.split(".", 1)[-1].replace(".", " ").replace("_", " "))


def _channel_sport_eligible(sport, channel_name, dictionary_categories=()):
    """Reject non-viewing/sport-incompatible channels before a guide link is emitted."""
    return _sport_eligible(str(sport or ""), str(channel_name or ""), tuple(str(c) for c in dictionary_categories or ()))


@lru_cache(maxsize=100_000)     # one answer per (sport, channel): called for every programme row
def _sport_eligible(sport, channel_name, dictionary_categories):
    name = taxonomy.norm(channel_name)
    if not name or _RADIO_OR_SHOPPING.search(name):
        return False
    if {"ts1", "ts2"} & name_signature(channel_name)[0]:
        return False                      # +1/+2 channels air the event later; never a live candidate
    families = set()
    # The existing source registry recognises the named UK/European sports
    # families and free-to-air broadcasters. A generic sports label is also
    # useful for regional feeds whose service names are not in that registry.
    families.update(channel_families(channel_name))
    recognized = bool(families) or "sport" in name or any("sport" in taxonomy.norm(str(c)) for c in dictionary_categories)
    if not recognized:
        return False
    event_sport = _sport_family(sport)
    hints = set()
    for family, terms in _CHANNEL_SPORT_HINTS.items():
        if any(_has_phrase(name, term) for term in terms):
            hints.add(_sport_family(family))
    # A non-specific sports network or general broadcaster can carry any sport;
    # an explicitly sport-branded service must agree with the fixture sport.
    return not hints or event_sport in hints


def _has_phrase(text, phrase):
    return f" {phrase} " in f" {text} "


def _tournament_qualifiers(text):
    qualifiers = set()
    for kind, number, word in _TOURNAMENT_QUALIFIER.findall(text):
        if kind:
            qualifiers.add(f"{kind} {int(number)}")
        else:
            word = word.replace(" ", "").removesuffix("s")
            qualifiers.add("qualifying" if word == "qualification" else word)
    return qualifiers


def _tournament_variants(text):
    variants = set(_TOURNAMENT_VARIANT.findall(text))
    if variants & _WOMENS_VARIANTS:
        variants.difference_update(_WOMENS_VARIANTS)
        variants.add("women")
    if "indoors" in variants:
        variants.remove("indoors")
        variants.add("indoor")
    return variants


def _matches_tournament(event, row):
    sport = event.get("sport")
    series = _TOURNAMENT_NAMES.get(sport)
    if not series:
        return False
    title = taxonomy.norm(event.get("title"))
    competition = taxonomy.norm(event.get("competition"))
    fixture = " ".join((title, competition))
    # Round, stage or session information must agree, including when one
    # source gives a generic tournament listing and the other names a round.
    details = []
    for field in ("session", "round", "stage"):
        value = taxonomy.norm(event.get(field))
        details.append(f"{field} {value}" if value.isdecimal() else value)
    detail = " ".join(details)
    text = row[3]
    if _tournament_qualifiers(f"{fixture} {detail}") != _tournament_qualifiers(text):
        return False
    if _tournament_variants(fixture) != _tournament_variants(text):
        return False
    context = "racing" if sport == "horse_racing" else sport
    # A long-form generic EPG row needs either a live flag or an explicit
    # live title before it can support a tournament or meeting candidate.
    if not row[4] and not _has_phrase(text, "live"):
        return False
    return any(
        any(_has_phrase(fixture, name) for name in aliases)
        and any(_has_phrase(text, name) and (name not in _AMBIGUOUS_TITLES or _has_phrase(text, context))
                for name in aliases)
        for aliases in series
    )


def _matches(event, row):
    parts, text = row[2], row[3]
    if not parts:
        return False
    event_variants = _event_identity_variants(event)
    if event_variants != _programme_identity_variants(text) and (event_variants or _programme_identity_variants(text)):
        return False
    if event.get("sport") == "motorsport":
        if taxonomy.norm(event.get("competition", "")) not in {"f1", "formula 1", "formula one"}:
            return False
        if not re.search(r"\b(f1|formula 1|formula one)\b", text) and row[5] != "gb.sky.sports.f1":
            return False
        session = event.get("session")
        if session in ("practice1", "practice2", "practice3"):
            number = session[-1]
            return bool(re.search(rf"\b(?:practice {number}|fp\s*{number})\b", text))
        if any(w in text for other, words in _SESSION_WORDS.items() if other != session and other[:8] != (session or "")[:8]
               for w in words if w not in _SESSION_WORDS.get(session, ())):
            return False
        return any(w in text for w in _SESSION_WORDS.get(session, ()))
    teams = _team_options(event)
    if not teams:
        return _matches_tournament(event, row)
    allowed = _PROGRAMME_WORDS | set(tokens(event.get("competition", ""))) | event_variants
    return any(_fixture_in(part, home, away, allowed)
               for part in parts for home in teams[0] for away in teams[1])


_REGIONAL_FAMILIES = {parent for parent, _ in REGIONAL_PARENTS.values()}
_SIMULCAST_TOLERANCE = timedelta(minutes=5)


def _regional_family(canonical):
    if canonical in _REGIONAL_FAMILIES:
        return canonical
    return REGIONAL_PARENTS.get(canonical, (None, None))[0]


def _allocate_regions(found, matched, observed):
    """Allocate network channels to the network id only when the nations carry the event.

    ``matched``/``observed`` map a service id to (start, text, name) rows at kickoff:
    fixture listings, and every listing of a regional-family channel. A nation whose
    listing at the same slot is a shortened title of the fixture listing (e.g. STV's
    "Nations Championship" for ITV1's "Wales v New Zealand: Nations Championship")
    is a simulcast. Any other listing is evidence that the nation opts out.
    """
    families = defaultdict(set)
    for canonical in found:
        family = _regional_family(canonical)
        if family:
            families[family].add(canonical)
    for parent, carriers in families.items():
        listings = [row for canonical in carriers for row in matched.get(canonical, [])]

        def simulcast(canonical):
            for start, text, _ in observed.get(canonical, []):
                words = set(text.split())
                if len(words) >= 2 and any(abs(start - other) <= _SIMULCAST_TOLERANCE and words <= set(full.split())
                                           for other, full, _ in listings):
                    return True
            return False

        nations = {canonical for canonical in observed if REGIONAL_PARENTS.get(canonical, (None,))[0] == parent}
        opted_out = sorted(canonical for canonical in nations - carriers if not simulcast(canonical))
        if parent not in carriers and simulcast(parent):
            template = found[sorted(carriers)[0]]
            name = observed[parent][0][2]
            found[parent] = dict(template, canonical_channel_id=parent, channel_name=name[:120],
                                 epg_sources=list(template["epg_sources"]))
            carriers = carriers | {parent}
        if parent in carriers:
            entry = found[parent]
            names = [name for _, _, name in matched.get(parent, [])]
            if names:                     # "BBC One" rather than an English region's name
                entry["channel_name"] = min(names, key=lambda n: (len(normalized_name(n)), n))[:120]
            for canonical in sorted(carriers - {parent}):
                child = found.pop(canonical)
                entry["epg_live_flag"] = entry["epg_live_flag"] or child["epg_live_flag"]
                entry["epg_sources"].extend(s for s in child["epg_sources"] if s not in entry["epg_sources"])
            entry["coverage"] = "network"
            if opted_out:
                entry["not_on"] = opted_out
        else:
            for canonical in carriers:
                found[canonical]["coverage"] = "regional"
                found[canonical]["parent_channel_id"] = parent
    for entry in found.values():
        entry.setdefault("coverage", "network")


def broadcast_candidates(events, epg_guides, now, *, gaps=None, dictionary_document=None, identity_document=None,
                         guide_events=None, guide_days=8):
    """Return {event_id: (status, [candidate...])} for the given events.

    When ``guide_events`` is a list, live sport listed on recognised channels that
    no event matched is appended to it as private guide-listed events
    (see ``_guide_live_events``); they are never published.
    """
    timed = []
    for event in events:
        if event.get("start_precision") in UNCONFIRMED_START_PRECISIONS:
            if gaps is not None:
                gaps[event["id"]] = "time_unconfirmed"
            continue
        if event.get("status_normalized") in ("postponed", "cancelled"):
            if gaps is not None:
                gaps[event["id"]] = "fixture_inactive"
            continue
        try:
            timed.append((event, _dt(event["start_utc"])))
        except (KeyError, TypeError, ValueError):
            continue
    if not timed and guide_events is None:
        return {}
    starts = [start for _, start in timed]
    window_start = min(starts) if starts else now
    window_end = max(starts) + timedelta(minutes=21) if starts else now
    if guide_events is not None:
        window_start, window_end = min(window_start, now), max(window_end, now + timedelta(days=guide_days))
    # Bound each lookup by the longest accepted programme and the kickoff tolerance.
    coverage = {} if gaps is not None else None
    channel_identities, guides = _channel_identity_index(epg_guides or {}, dictionary_document, identity_document)
    rows = _programme_index(guides, window_start, window_end,
                            include_non_matches=gaps is not None, coverage=coverage,
                            channel_identities=channel_identities)
    guide_periods = [(first, last) for first, last in (coverage or {}).values() if first is not None]
    by_start = sorted(enumerate(rows), key=lambda item: item[1][0])
    programme_starts = [row[0] for _, row in by_start]
    result = {}
    matched_rows = set()
    for event, start in timed:
        found = {}
        matched, observed = defaultdict(list), defaultdict(list)
        unmapped_match = False
        earliest_end = start + timedelta(minutes=30)
        latest_start = start + timedelta(minutes=20)
        first = bisect_left(programme_starts, earliest_end - _MAX_PROGRAMME)
        last = bisect_right(programme_starts, latest_start)
        overlapping = [item for item in by_start[first:last] if item[1][1] >= earliest_end]
        if event.get("sport") == "motorsport":
            basis = "epg_f1_session"
        elif len(event.get("participants") or []) < 2:
            basis = "epg_tournament_session"
        else:
            basis = "epg_title_teams"
        # Keep source order when choosing the representative channel name
        # and programme times for a service reported by multiple guides.
        for row_index, row in sorted(overlapping):
            if row[5] and _regional_family(row[5]):
                observed[row[5]].append((row[0], row[3], row[6]))
            if not _channel_sport_eligible(event.get("sport", ""), _eligibility_name(row), row[10]):
                continue
            if not _matches(event, row):
                continue
            canonical = row[5]
            if not canonical:
                unmapped_match = True
                continue
            entry = found.setdefault(canonical, {"canonical_channel_id": canonical, "channel_name": row[6][:120],
                                                 "programme_start_utc": row[0].isoformat(timespec="seconds"),
                                                 "programme_end_utc": row[1].isoformat(timespec="seconds"),
                                                 "epg_live_flag": False, "epg_sources": [], "match_basis": basis,
                                                 "channel_identity_method": row[8],
                                                 "channel_identity_confidence": row[9],
                                                 "match_confidence": "high" if row[9] == "high" else "medium"})
            entry["channel_name"] = _display_name_for(canonical, entry["channel_name"], row[6])
            entry["epg_live_flag"] = entry["epg_live_flag"] or row[4]
            if row[7] not in entry["epg_sources"]:
                entry["epg_sources"].append(row[7])
            matched[canonical].append((row[0], row[3], row[6]))
            matched_rows.add(row_index)
        _allocate_regions(found, matched, observed)
        candidates = sorted(found.values(), key=lambda c: c["canonical_channel_id"])
        if not candidates:
            if gaps is not None:
                if unmapped_match:
                    gap = "matching_channel_unmapped"
                elif any(row[5] for _, row in overlapping):
                    gap = "fixture_title_unmatched"
                elif not guide_periods:
                    gap = "no_guide_data"
                elif not any(first <= latest_start and last >= earliest_end for first, last in guide_periods):
                    gap = "outside_guide_dates"
                else:
                    gap = "no_recognised_guide_slot"
                gaps[event["id"]] = gap
            continue
        multi = any(len({EPG_FAMILY.get(s, s) for s in c["epg_sources"]}) > 1 for c in candidates)
        result[event["id"]] = ("multi_guide_match" if multi else "single_guide_match", candidates)
    if guide_events is not None:
        for event in _guide_live_events(by_start, programme_starts, matched_rows, now, timed):
            target = event.pop("_feed_event_id", None)
            if target and target not in result:
                # The guide confirms a feed fixture the strict title match missed (e.g. "NY Rangers at Vancouver").
                result[target] = ("guide_listing_match", event["broadcast_candidates"])
                if gaps is not None:
                    gaps.pop(target, None)
            elif not target:
                guide_events.append(event)
    return result


# ---- guide-listed live sport ------------------------------------------------
# Free sports APIs cover a day or two ahead; the guides list a week of live sport
# with the channel. Live listings on recognised channels that no event matched
# become private events, so live action is allocated to a channel even when no
# event source has the fixture. Never published: programme text is not cleared.
_LIVE_TEXT = re.compile(r"^(?:live|en direct|direct|en vivo|in diretta|live ?:)\b")
_SPORT_WORDS = [
    ("other", r"\b(skiing|alpine|alpin|ski|biathlon|ski jumping|snowboard|powerlifting|weightlifting|triathlon|gaa|"
              r"hurling|camogie|gaelic|badminton|swimming|natation|diving|gymnastics|gymnastique|bowls|equestrian|"
              r"equitation|sailing|voile|rowing|petanque|escrime|judo|wintersport|skating|patinage)\b"),
    ("darts", r"\bdarts\b"), ("snooker", r"\bsnooker\b"), ("golf", r"\b(golf|pga|lpga|dp world tour|wtgl)\b"),
    ("tennis", r"\b(tennis|atp|wta|davis cup|coupe davis|billie jean king|roland garros)\b"),
    ("cricket", r"\b(cricket|big bash|wbbl|odi|t20|t10|test match)\b"),
    ("rugby_league", r"\brugby league\b|\bsuper league\b"),
    ("rugby_union", r"\b(rugby|nations championship|six nations|prem rugby|urc|champions cup|top 14|pro d2|"
                    r"tournoi des six nations)\b"),
    ("american_football", r"\b(nfl|redzone|college football|ncaa football|american football)\b"),
    ("basketball", r"\b(nba|basketball|basket|baloncesto|pallacanestro|euroleague|eurobasket|betclic elite)\b"),
    ("ice_hockey", r"\b(nhl|ice hockey|hockey sur glace|eishockey)\b"),
    ("baseball", r"\b(mlb|baseball)\b"), ("motorsport", r"\b(f1|formula 1|formula one|formule 1|formel 1|formula uno|motogp|moto gp|indycar|nascar|wec|"
                   r"grand prix|gran premio|rallye)\b"),
    ("boxing", r"\b(boxing|boxe|boxen|boxeo|pugilato)\b"), ("mma", r"\b(ufc|mma|pfl)\b"),
    ("horse_racing", r"\b(racing|raceday|race day|horse|hippisme|quinte|courses hippiques|turf|pferderennen)\b"),
    ("cycling", r"\b(cycling|cyclocross|cyclisme|radsport|ciclismo|tour de|giro|vuelta)\b"),
    ("athletics", r"\b(athletics|athletisme|leichtathletik|atletismo|atletica|marathon|diamond league)\b"),
    ("aussie_rules", r"\b(afl|aflw|aussie rules)\b"),
    ("netball", r"\bnetball\b"), ("handball", r"\b(handball|balonmano|pallamano)\b"),
    ("volleyball", r"\b(volleyball|volley|voleibol|pallavolo)\b"),
    ("football", r"\b(football|soccer|fussball|futbol|calcio|ligue 1|ligue 2|ligue des champions|ligue europa|"
                 r"coupe de france|wsl|swpl|nwsl|mls|premier league|nations league|fa cup|efl|league one|"
                 r"league two|championship|a league|laliga|la liga|serie a|bundesliga|ligue 1|eredivisie|spfl|"
                 r"champions league|europa league|conference league|world cup|euro 20\d\d|copa)\b"),
]
_SPORT_WORDS = [(sport, re.compile(pattern)) for sport, pattern in _SPORT_WORDS]
_CHANNEL_SPORT = [("golf", "golf"), ("cricket", "cricket"), ("tennis", "tennis"), ("motorsport", "f1"),
                  ("horse_racing", "racing"), ("darts", "darts"), ("football", "football")]
_GENERIC_CORE = {"live", "new", "sport", "sports", "football", "tennis", "golf", "cricket", "rugby", "racing", "darts",
                 "snooker", "boxing", "basketball", "baseball", "nfl", "nba", "nhl", "ufc", "the", "and", "of", "on",
                 "day", "session", "game", "match", "coverage", "beo"}
_FIXTURE_SPLIT = re.compile(r"\s+(?:v|vs|versus)\.?\s+|\s+@\s+", re.I)
# North American listings write "Away at Home"; only trusted for those sports.
_US_SPLIT = re.compile(r"\s+(?:v|vs|versus)\.?\s+|\s+@\s+|\s+at\s+", re.I)
_US_SPORTS = {"american_football", "ice_hockey", "basketball", "baseball"}
_DATE_ONLY = re.compile(r"^\s*\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?\s*$")
_LEADING_TAG = re.compile(r"^\s*\[[^\]]{1,20}\]\s*")


def _guide_sport(text, channel_name):
    for sport, pattern in _SPORT_WORDS:
        if pattern.search(text):
            return sport
    name = taxonomy.norm(channel_name)
    for sport, word in _CHANNEL_SPORT:
        if _has_phrase(name, word):
            return sport
    return None


def _strip_live(value):
    value = _clean_listing(value)
    value = re.sub(r"^\s*\[?\s*(?:live|en direct|direct)\s*\]?\s*:?\s*", "", value, flags=re.I).strip(" :|-")
    value = _LEADING_TAG.sub("", value)
    value = re.sub(r"\s+", " ", value).strip(" :|-")
    return "" if _DATE_ONLY.match(value) else value


def _guide_listing(raw_title, raw_subtitle, sport=None):
    """(title, competition, participants) for display, from a live listing."""
    title, subtitle = _strip_live(raw_title), _strip_live(raw_subtitle)
    if title and subtitle and taxonomy.norm(subtitle).startswith(taxonomy.norm(title)):
        title, subtitle = subtitle, ""               # "Darts" + "Darts D1 S1" -> one title
    splitter = _US_SPLIT if sport in _US_SPORTS else _FIXTURE_SPLIT
    for field, other in ((subtitle, title), (title, subtitle)):
        pieces = [piece.strip() for piece in field.split(":")]
        for index, piece in enumerate(pieces):
            sides = splitter.split(piece)
            if len(sides) == 2 and all(side.strip() for side in sides):
                prefix = ": ".join(pieces[:index]).strip(" ,")
                parts = [x for x in (other if field is subtitle else "", prefix) if x]
                competition = ", ".join(dict.fromkeys(parts))
                home, away = (side.strip(" -,") for side in sides)
                away = re.split(r"\s+-\s*|-(?=\d)", away)[0].strip()      # "England-2nd ODI"
                return "%s v %s" % (home, away), competition[:120], [home[:80], away[:80]]
    core = set(taxonomy.norm(title).split()) - _GENERIC_CORE
    if subtitle and not core:                         # "Live Tennis" + "ATP Finals Day 1"
        return subtitle[:120], title[:120], []
    return (title + (": " + subtitle if subtitle else ""))[:120], title[:120], []


def _listing_key(sport, participants, title, variants=frozenset()):
    """Sport (plus women's/age-group variant) and the fixture sides or title words."""
    sport_key = sport + ("|" + "|".join(sorted(variants)) if variants else "")
    if participants:
        return (sport_key, frozenset(frozenset(team_key(name) - _VARIANT) for name in participants))
    return (sport_key, frozenset(set(taxonomy.norm(title).split()) - _GENERIC_CORE))


def _is_fixture_key(key):
    return isinstance(next(iter(key[1]), None), frozenset)


def _token_in(token, tokens_):
    # A guide may truncate the last word ("London City Lionesse").
    return token in tokens_ or (len(token) >= 5 and any(len(t) >= 5 and (t.startswith(token) or token.startswith(t))
                                                         for t in tokens_))


def _same_side(a, b):
    a, b = a - _GENERIC, b - _GENERIC
    return bool(a) and bool(b) and (all(_token_in(t, b) for t in a) or all(_token_in(t, a) for t in b))


def _feed_event_for(cluster_key, start, timed):
    """The one feed event with the same sport and fixture (names contained) within 3 hours, if any."""
    if not _is_fixture_key(cluster_key):
        return None
    sides = (tuple(cluster_key[1]) * 2)[:2]
    found = []
    for event, event_start in timed:
        if (abs(event_start - start) > timedelta(hours=3)
                or _sport_family(event.get("sport")) != _sport_family(cluster_key[0].split("|")[0])
                or set(_event_identity_variants(event)) != set(cluster_key[0].split("|")[1:])):
            continue
        teams = [frozenset(team_key(name) - _VARIANT) for name in (event.get("participants") or [])[:2]]
        if len(teams) == 2 and ((_same_side(sides[0], teams[0]) and _same_side(sides[1], teams[1]))
                                or (_same_side(sides[0], teams[1]) and _same_side(sides[1], teams[0]))):
            found.append(event)
    return found[0] if len(found) == 1 else None


def _same_listing(a, b):
    """Same sport and the same fixture (sides equal or one name contained in the other) or similar title."""
    if a[0] != b[0]:
        return False
    if _is_fixture_key(a) and _is_fixture_key(b):
        (a1, a2), (b1, b2) = (tuple(a[1]) * 2)[:2], (tuple(b[1]) * 2)[:2]
        return (_same_side(a1, b1) and _same_side(a2, b2)) or (_same_side(a1, b2) and _same_side(a2, b1))
    if _is_fixture_key(a) or _is_fixture_key(b):
        return False
    union = a[1] | b[1]
    return bool(union) and len(a[1] & b[1]) / len(union) >= 0.5


def _guide_live_events(by_start, programme_starts, matched_rows, now, timed=()):
    clusters = []        # [key, start, [(row_index, row, title, competition, participants)]]
    for row_index, row in by_start:
        canonical, text = row[5], row[3]
        if not canonical or row[1] <= now or not (row[4] or _LIVE_TEXT.match(text)):
            continue
        raw_title, raw_subtitle = row[11]
        sport = _guide_sport(text, row[6])
        if not sport or not _channel_sport_eligible(sport, _eligibility_name(row), row[10]):
            continue
        title, competition, participants = _guide_listing(raw_title, raw_subtitle, sport)
        if not title.strip():
            continue
        key = _listing_key(sport, participants, title, frozenset(_programme_identity_variants(text)))
        member = (row_index, row, title, competition, participants)
        home = None
        horizon = timedelta(hours=6) if participants else timedelta(minutes=45)
        for cluster in reversed(clusters):
            if row[0] - cluster[1] > timedelta(hours=6):
                break
            same_slot = any(other[1][5] == row[5] and abs(other[1][0] - row[0]) <= timedelta(minutes=20)
                            for other in cluster[2])
            if (cluster[0][0] == key[0] and same_slot) or (
                    row[0] - cluster[1] <= horizon and _same_listing(cluster[0], key)):
                home = cluster
                break
        if home:
            home[2].append(member)
        else:
            clusters.append([key, row[0], [member]])
    events = []
    for key, start, members in clusters:
        if any(index in matched_rows for index, *_ in members):
            continue                      # the same broadcast already belongs to a fixture
        found, matched, observed = {}, defaultdict(list), defaultdict(list)
        for _, row, *_ in members:
            entry = found.setdefault(row[5], {"canonical_channel_id": row[5], "channel_name": row[6][:120],
                                              "programme_start_utc": row[0].isoformat(timespec="seconds"),
                                              "programme_end_utc": row[1].isoformat(timespec="seconds"),
                                              "epg_live_flag": False, "epg_sources": [], "match_basis": "epg_live_listing",
                                              "channel_identity_method": row[8], "channel_identity_confidence": row[9],
                                              "match_confidence": "guide_listed"})
            entry["channel_name"] = _display_name_for(row[5], entry["channel_name"], row[6])
            entry["epg_live_flag"] = entry["epg_live_flag"] or row[4]
            if row[7] not in entry["epg_sources"]:
                entry["epg_sources"].append(row[7])
            matched[row[5]].append((row[0], row[3], row[6]))
        first = bisect_left(programme_starts, start + timedelta(minutes=30) - _MAX_PROGRAMME)
        last = bisect_right(programme_starts, start + timedelta(minutes=20))
        for _, row in by_start[first:last]:
            if row[1] >= start + timedelta(minutes=30) and row[5] and _regional_family(row[5]):
                observed[row[5]].append((row[0], row[3], row[6]))
        _allocate_regions(found, matched, observed)
        candidates = sorted(found.values(), key=lambda c: c["canonical_channel_id"])
        # Fixtures: the fullest team names; sessions: the plainest title.
        pick = max if key and _is_fixture_key(key) else min
        _, row, title, competition, participants = pick(members, key=lambda m: (len(m[2]), -m[1][0].timestamp()))
        end = max(member[1][1] for member in members)
        digest = hashlib.sha1(("%s|%s|%s" % (key[0], taxonomy.norm(title), start.isoformat())).encode()).hexdigest()[:16]
        guides = sorted({source for c in candidates for source in c["epg_sources"]})
        feed_event = _feed_event_for(key, start, timed)
        events.append({
            "_feed_event_id": feed_event["id"] if feed_event else None,
            "id": "guide:" + digest, "title": title, "sport": key[0].split("|")[0], "competition": competition or title,
            "participants": participants, "start_utc": start.isoformat(timespec="seconds"),
            "end_utc": end.isoformat(timespec="seconds"), "start_precision": "scheduled",
            "start_basis": "broadcast_start", "event_type": "match" if participants else "session",
            "origin": "guide_listing", "source_id": "guide_listing", "sources": ["guide_listing"],
            "epg_sources": guides, "fixture_confidence": "guide_listed", "corroboration": len(guides),
            "broadcast_verified": False, "broadcast_status": "guide_listed", "broadcast_candidates": candidates,
        })
    return events


def build_today(events, now, epg_guides=None, *, use_saved_candidates=False):
    today = now.astimezone(LONDON).date()
    todays = []
    for event in events:
        try:
            if _dt(event["start_utc"]).astimezone(LONDON).date() == today:
                todays.append(dict(event, live_state=live_state(event, now)))
        except (KeyError, ValueError, TypeError):
            continue
    if not use_saved_candidates:
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
