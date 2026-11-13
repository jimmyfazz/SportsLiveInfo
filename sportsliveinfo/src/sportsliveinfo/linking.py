"""Cross-source event fusion, the grouped "today" view and EPG broadcast candidates.

A fixture reported by two independent provider families is "corroborated";
one family is "reported". EPG programme matches are *candidates*: they name a
recognised channel whose guide shows a programme covering kick-off whose
title/sub-title identifies the fixture or a named tournament session. They never set broadcast_verified,
because guide upstream lineage is not yet proven independent.
"""
import re
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import dictionary as channel_dictionary, taxonomy
from .guide import COUNTRY_BY_SOURCE, canonical_channel, channel_families, normalized_name
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
# Alias expansion is deliberately exact and small. Feed-provided short names are
# also considered below; arbitrary fuzzy/substring team matching is not safe.
_TEAM_ALIASES = {
    "man city": "manchester city", "man utd": "manchester united", "man united": "manchester united",
    "nottm forest": "nottingham forest", "notts forest": "nottingham forest",
    "west brom": "west bromwich albion", "wba": "west bromwich albion",
    "qpr": "queens park rangers", "nz": "new zealand", "all blacks": "new zealand",
    "springboks": "south africa", "wallabies": "australia",
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
                       r"build up|countdown|extra|debate|analysis|recap|delayed)\b")
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


_ITV1_REGIONS = frozenset({"anglia", "border", "central", "granada", "london", "meridian", "tyne tees",
                           "utv", "wales", "west country", "westcountry", "yorkshire"})


def _regional_service_id(source_id, display_name, *, market, base_name, regions, canonical_id):
    """Collapse only explicitly known regional names to their parent service."""
    if COUNTRY_BY_SOURCE.get(source_id) != market:
        return None
    name = normalized_name(display_name)
    if name == base_name or any(name == base_name + " " + region for region in regions):
        return canonical_id
    return None


def _registry_channel_id(source_id, channel_id, display_name):
    canonical = canonical_channel(source_id, channel_id, display_name)
    if canonical:
        return canonical
    return _regional_service_id(source_id, display_name, market="GB", base_name="itv 1",
                                regions=_ITV1_REGIONS, canonical_id="gb.itv.one")


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


def _dictionary_hit(resolver, source_id, display_name):
    market = COUNTRY_BY_SOURCE.get(source_id)
    if resolver is None or not market:
        return None
    hit = resolver.resolve(display_name, market)
    if not hit or hit.get("confidence") != "high":
        return None
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
            hit = _dictionary_hit(resolver, member[0], name)
            if hit:
                dictionary_by_cluster[cluster_id].add(hit[0])
                category_by_dictionary_id[hit[0]] = hit[1]
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
            hit = _dictionary_hit(resolver, source_id, name)
            if hit:
                index[key] = (hit[0], "dictionary", "high", hit[1])
                continue
            if cluster_id and len(dictionary_by_cluster.get(cluster_id, ())) == 1:
                stable_id = next(iter(dictionary_by_cluster[cluster_id]))
                index[key] = (stable_id, "identity_dictionary", "high", category_by_dictionary_id.get(stable_id, ()))
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
            parts = [] if excluded else [taxonomy.norm(programme.get(field, "")) for field in ("title", "subtitle")]
            channel_name = channels.get(channel_id, channel_id)
            rows.append((start, end, [p for p in parts if p], text, bool(programme.get("is_live")), canonical,
                         channel_name, source_id, mapping_method, mapping_confidence, dictionary_categories))
    return rows


def _side_matches(segment, team, allowed):
    words = set(tokens(segment)) - _STOP
    distinctive = set(team) - _GENERIC - _LOW_SIGNAL_TEAM_TOKENS
    return (bool(distinctive) and "tbc" not in team and distinctive <= words
            and (words - set(team) - _LOW_SIGNAL_TEAM_TOKENS) <= allowed)


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
    participants = event.get("participants") or []
    if len(participants) < 2:
        return []
    short = event.get("participants_short") or []
    options = []
    for index in range(2):
        names = [participants[index]]
        if len(short) > index and short[index]:
            names.append(short[index])
        keys = []
        for name in names:
            key = team_key(name)
            if key and "tbc" not in key and set(key) - _GENERIC - _LOW_SIGNAL_TEAM_TOKENS:
                if key not in keys:
                    keys.append(key)
        options.append(keys)
    return options if all(options) else []


def _event_identity_variants(event):
    text = " ".join(str(event.get(field) or "") for field in
                    ("title", "competition", "round", "stage", "session"))
    text += " " + " ".join(str(name) for field in ("participants", "participants_short")
                            for name in (event.get(field) or []))
    variants = _tournament_variants(taxonomy.norm(text))
    return {"women" if item == "w" else re.sub(r"\s*[- ]\s*", "", item) for item in variants
            if item == "w" or item.startswith("u") or item in _WOMENS_VARIANTS or item == "women"}


def _programme_identity_variants(text):
    variants = _tournament_variants(text)
    return {"women" if item == "w" else re.sub(r"\s*[- ]\s*", "", item) for item in variants
            if item == "w" or item.startswith("u") or item in _WOMENS_VARIANTS or item == "women"}


def _channel_sport_eligible(sport, channel_name, dictionary_categories=()):
    """Reject non-viewing/sport-incompatible channels before a guide link is emitted."""
    name = taxonomy.norm(channel_name)
    if not name or _RADIO_OR_SHOPPING.search(name):
        return False
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


def broadcast_candidates(events, epg_guides, now, *, gaps=None, dictionary_document=None, identity_document=None):
    """Return {event_id: (status, [candidate...])} for the given events."""
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
    if not timed:
        return {}
    starts = [start for _, start in timed]
    # Bound each lookup by the longest accepted programme and the kickoff tolerance.
    coverage = {} if gaps is not None else None
    channel_identities, guides = _channel_identity_index(epg_guides or {}, dictionary_document, identity_document)
    rows = _programme_index(guides, min(starts), max(starts) + timedelta(minutes=21),
                            include_non_matches=gaps is not None, coverage=coverage,
                            channel_identities=channel_identities)
    guide_periods = [(first, last) for first, last in (coverage or {}).values() if first is not None]
    by_start = sorted(enumerate(rows), key=lambda item: item[1][0])
    programme_starts = [row[0] for _, row in by_start]
    result = {}
    for event, start in timed:
        found = {}
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
        for _, row in sorted(overlapping):
            if not _channel_sport_eligible(event.get("sport", ""), row[6], row[10]):
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
            entry["epg_live_flag"] = entry["epg_live_flag"] or row[4]
            if row[7] not in entry["epg_sources"]:
                entry["epg_sources"].append(row[7])
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
    return result


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
