"""Event and taxonomy metadata published in the feed (additive, sli/1.6 compatible; contract section 4.3 "Metadata").

Design rule: SportsLiveInfo decides, B1G follows the feed. Everything here is computed centrally and deterministically
from fields the feed already carries, so a correction reaches every TV with the next feed and needs no B1G update:

* sport and competition icon keys and the default sport order (taxonomy asset);
* ``participants_short`` for every event, and ``participant_ids``;
* ``competition_logo`` references (same gating as team crests; see ``feed._event_public``);
* ``feature_rank`` (0-100) and the ordering built from it, ``ppv`` / ``ppv_label``;
* F1 ``session_label`` and ``weekend_id``.

All of it is optional on the wire: a reader that knows none of these fields keeps working.
"""
import re

from . import linking, taxonomy

# ---------------------------------------------------------------- taxonomy: icons and order

SPORT_ICON_KEYS = {sid: sid for sid in taxonomy.SPORTS}
SPORT_ICON_KEYS["other"] = "other"

COMPETITION_ICON_KEYS = {
    "football.premier_league": "premier_league", "football.champions_league": "uefa_champions_league",
    "football.europa_league": "uefa_europa_league", "football.conference_league": "uefa_conference_league",
    "football.fa_cup": "fa_cup", "football.efl_cup": "efl_cup", "football.championship": "efl_championship",
    "football.league_one": "efl_league_one", "football.league_two": "efl_league_two", "football.wsl": "wsl",
    "football.scottish_premiership": "scottish_premiership", "football.world_cup": "fifa_world_cup",
    "football.womens_world_cup": "fifa_womens_world_cup", "football.euro": "uefa_euro",
    "football.womens_euro": "uefa_womens_euro", "football.nations_league": "uefa_nations_league",
    "football.la_liga": "la_liga", "football.serie_a": "serie_a", "football.bundesliga": "bundesliga",
    "football.ligue_1": "ligue_1", "football.eredivisie": "eredivisie", "football.primeira_liga": "primeira_liga",
    "football.mls": "mls", "football.libertadores": "copa_libertadores",
    "rugby_union.six_nations": "six_nations", "rugby_union.womens_six_nations": "six_nations",
    "rugby_union.world_cup": "rugby_world_cup", "rugby_union.premiership": "premiership_rugby",
    "rugby_union.urc": "urc", "rugby_union.champions_cup": "european_champions_cup", "rugby_union.top_14": "top_14",
    "rugby_union.rugby_championship": "rugby_championship", "rugby_league.super_league": "super_league",
    "rugby_league.nrl": "nrl", "cricket.ashes": "the_ashes", "cricket.ipl": "ipl", "cricket.the_hundred": "the_hundred",
    "cricket.t20_world_cup": "icc_t20_world_cup", "cricket.world_cup": "icc_world_cup",
    "tennis.australian_open": "australian_open", "tennis.roland_garros": "roland_garros",
    "tennis.wimbledon": "wimbledon", "tennis.us_open": "us_open", "tennis.davis_cup": "davis_cup",
    "motorsport.f1": "formula_1", "motorsport.motogp": "motogp", "motorsport.formula_e": "formula_e",
    "motorsport.wec": "wec", "motorsport.indycar": "indycar", "motorsport.wrc": "wrc", "motorsport.nascar": "nascar",
    "mma.ufc": "ufc", "mma.pfl": "pfl", "golf.majors": "golf_majors", "golf.ryder_cup": "ryder_cup",
    "golf.liv": "liv_golf", "golf.pga_tour": "pga_tour", "darts.world_championship": "pdc_world_championship",
    "snooker.world_championship": "world_snooker_championship", "basketball.nba": "nba", "basketball.wnba": "wnba",
    "basketball.euroleague": "euroleague", "american_football.nfl": "nfl", "ice_hockey.nhl": "nhl",
    "baseball.mlb": "mlb", "aussie_rules.afl": "afl", "cycling.grand_tours": "grand_tours",
}

# Competitions SportsLiveInfo asks a reader to feature (display_policy.featured_competition_ids). Curated, not computed.
FEATURED_COMPETITION_IDS = (
    "football.premier_league", "football.champions_league", "football.europa_league", "football.fa_cup",
    "football.efl_cup", "football.world_cup", "football.euro", "football.nations_league", "football.wsl",
    "football.womens_euro", "football.womens_world_cup", "rugby_union.six_nations", "rugby_union.autumn_nations",
    "rugby_union.world_cup", "rugby_union.premiership", "rugby_union.urc", "rugby_union.champions_cup",
    "rugby_league.super_league", "cricket.ashes", "cricket.the_hundred", "cricket.t20_world_cup",
    "cricket.world_cup", "tennis.australian_open", "tennis.roland_garros", "tennis.wimbledon", "tennis.us_open",
    "motorsport.f1", "motorsport.motogp", "golf.majors", "golf.ryder_cup", "darts.world_championship",
    "snooker.world_championship", "american_football.nfl", "basketball.nba", "boxing.ppv", "mma.ufc",
)


def default_sport_order(group_of):
    """B1G priority groups in the default display order, derived from taxonomy.SPORTS order so it never drifts from
    ``b1g_priority_group``. ``group_of(sport_id, competition_id=None)`` is ``feed._priority_group``. Competition-level
    groups (Formula 1, Motorbike racing) come immediately before their sport's own group. Every group a sport or
    competition can publish is present, including the eight B1G has no built-in entry for (Horse racing, Handball,
    Volleyball, Esports, Bowling, Netball, Australian rules football, Other sport)."""
    order = []

    def add(group):
        if group and group not in order:
            order.append(group)

    by_sport = {}
    for entry in (e for table in taxonomy.COMPETITIONS.values() for e in table):
        sport = entry["id"].split(".", 1)[0]
        group = group_of(sport, entry["id"])
        if group != group_of(sport):
            by_sport.setdefault(sport, [])
            if group not in by_sport[sport]:
                by_sport[sport].append(group)
    for sport, (_label, _minutes, _order) in sorted(taxonomy.SPORTS.items(), key=lambda kv: kv[1][2]):
        for group in by_sport.get(sport, ()):
            add(group)
        add(group_of(sport))
    return order


# ---------------------------------------------------------------- short names and participant ids

_CLUB_AFFIX = frozenset({"fc", "afc", "cf", "ssc", "fk", "bk", "rcd", "rfc", "rufc", "rlfc", "cfc"})
_SHORT_OVERRIDES = {
    "manchester city": "Man City", "manchester united": "Man Utd", "tottenham hotspur": "Spurs", "tottenham": "Spurs",
    "wolverhampton wanderers": "Wolves", "wolverhampton": "Wolves", "nottingham forest": "Nott'm Forest",
    "newcastle united": "Newcastle", "west ham united": "West Ham", "brighton and hove albion": "Brighton",
    "leicester city": "Leicester", "leeds united": "Leeds", "west bromwich albion": "West Brom",
    "queens park rangers": "QPR", "sheffield united": "Sheff Utd", "sheffield wednesday": "Sheff Wed",
    "paris saint germain": "PSG", "borussia dortmund": "Dortmund", "borussia monchengladbach": "Gladbach",
    "bayern munich": "Bayern", "bayern munchen": "Bayern", "inter milan": "Inter", "internazionale": "Inter",
    "atletico madrid": "Atletico", "club atletico de madrid": "Atletico",
}
_INDIVIDUAL_SPORTS = frozenset({"tennis", "boxing", "mma", "darts", "snooker", "golf"})
_PARTICLES = frozenset({"de", "del", "della", "da", "di", "dos", "van", "von", "der", "den", "le", "la", "bin", "al",
                        "el"})
_PLACEHOLDER = frozenset({"tbc", "tbd", "bye", "winner", "loser"})


def short_name(name, sport=None):
    """A deterministic short display name: club affixes (FC, AFC...) and a leading "The" dropped, a small published
    table for well-known clubs ("Manchester City" -> "Man City"), the surname for individual sports (tennis, boxing,
    MMA, darts, snooker, golf; doubles "A / B" per player), otherwise the name unchanged. Never empty."""
    text = re.sub(r"\s+", " ", str(name or "")).strip()
    if not text or taxonomy.norm(text) in _PLACEHOLDER:
        return text or "TBC"
    if sport in _INDIVIDUAL_SPORTS:
        parts = [p.strip() for p in re.split(r"\s+/\s+|\s*&\s*", text) if p.strip()]
        return " / ".join(_surname(p) for p in parts) or text
    words = text.split(" ")
    while len(words) > 1 and taxonomy.norm(words[0]) in ({"the"} | _CLUB_AFFIX):
        words = words[1:]
    while len(words) > 1 and taxonomy.norm(words[-1]) in _CLUB_AFFIX:
        words = words[:-1]
    trimmed = " ".join(words)
    return _SHORT_OVERRIDES.get(taxonomy.norm(trimmed), trimmed)


def _surname(person):
    words = person.split(" ")
    if len(words) < 2:
        return person
    index = len(words) - 1
    while index > 0 and taxonomy.norm(words[index - 1]) in _PARTICLES:
        index -= 1
    return " ".join(words[index:])


def participants_short(event):
    """``participants_short`` index-aligned with ``participants`` for every event that has participants. A source's own
    short name is kept where it gave one for that side (football-data.org, OpenLigaDB); every other side is derived."""
    names = [str(n or "") for n in event.get("participants") or []]
    if not names:
        return None
    given = event.get("participants_short")
    given = given if isinstance(given, list) and len(given) == len(names) else [None] * len(names)
    sport = event.get("sport")
    return [str(g).strip() if isinstance(g, str) and g.strip() else short_name(n, sport) for g, n in zip(given, names)]


_API_SPORTS_REF = re.compile(r"^([a-z][a-z-]{1,30})/teams/([1-9][0-9]{0,11})$")


def participant_key(name):
    """Normalised key for a side with no provider id: the identity tokens the merge logic already uses ("Arsenal FC"
    and "Arsenal" agree), in order, joined with "-". None for a placeholder such as TBC."""
    if taxonomy.norm(name) in _PLACEHOLDER or not taxonomy.norm(name):
        return None
    seen, out = set(), []
    for token in linking.tokens(name):
        if token not in linking._STOP and token not in seen:
            seen.add(token)
            out.append(token)
    slug = "-".join(out) or taxonomy.norm(name).replace(" ", "-")
    return slug or None


def participant_ids(event):
    """``participant_ids``: index-aligned with ``participants``. ``apisports:<product>:<team id>`` when a provider team
    id is known (``apisports:football:42``), otherwise ``key:<normalised name>``; null for an unknown (TBC) side.
    Treat as opaque strings: a side's id moves from ``key:`` to the provider id when a provider id becomes known."""
    names = event.get("participants")
    if not isinstance(names, list) or not names:
        return None
    refs = event.get("participant_crests")
    refs = refs if isinstance(refs, list) and len(refs) == len(names) else [None] * len(names)
    out = []
    for ref, name in zip(refs, names):
        match = _API_SPORTS_REF.match(ref["ref"]) if isinstance(ref, dict) and isinstance(ref.get("ref"), str) else None
        if match:
            out.append("apisports:%s:%s" % (match.group(1), match.group(2)))
        else:
            key = participant_key(str(name or ""))
            out.append("key:" + key if key else None)
    return out if any(out) else None


# ---------------------------------------------------------------- competition logo reference

LEAGUE_REF = re.compile(r"^[a-z][a-z-]{1,30}/leagues/[1-9][0-9]{0,11}$")


def competition_logo_public(event):
    """A valid ``{src, ref}`` competition logo reference, or None. Same style as crests; the caller applies the crest
    kill switch. SportsLiveInfo never fetches or stores the image (the payload's logo URL is ignored)."""
    logo = event.get("competition_logo")
    if (isinstance(logo, dict) and logo.get("src") == "apisports" and isinstance(logo.get("ref"), str)
            and LEAGUE_REF.match(logo["ref"])):
        return {"src": "apisports", "ref": logo["ref"]}
    return None


# ---------------------------------------------------------------- PPV

_PPV_SPORTS = frozenset({"boxing", "mma"})
_PPV_WORDS = re.compile(r"\b(?:ppv|box office|pay per view)\b")


def ppv_fields(event):
    """``ppv`` (true only; absent means false) and ``ppv_label`` for boxing and MMA pay-per-view cards."""
    if event.get("sport") not in _PPV_SPORTS or "ppv" not in (event.get("tags") or ()):
        return {}
    competition = str(event.get("competition") or "").strip()
    base = competition if competition and not _PPV_WORDS.search(taxonomy.norm(competition)) else \
        str(event.get("sport_label") or ("Boxing" if event.get("sport") == "boxing" else "MMA"))
    return {"ppv": True, "ppv_label": ("%s PPV" % base)[:40]}


# ---------------------------------------------------------------- F1

F1_SESSION_LABELS = {"race": "Race", "practice1": "Practice 1", "practice2": "Practice 2", "practice3": "Practice 3",
                     "qualifying": "Qualifying", "sprint": "Sprint", "sprint_qualifying": "Sprint Qualifying"}
_JOLPICA_ID = re.compile(r"^f1:(\d{4}):(\d{1,2}):")


def is_f1(event):
    return event.get("competition_id") == "motorsport.f1"


def f1_fields(event):
    """``session_label`` (Practice 1, Qualifying, Sprint, Race...) and ``weekend_id`` for Formula 1 sessions.

    ``weekend_id`` is shared by every session of one race weekend and does not change when sessions pass or when the
    sources that report the weekend change: ``f1:<season>:<round>`` from the Jolpica calendar (also when OpenF1 is the
    primary record, through ``source_events``), else ``f1:openf1:<meeting_key>``."""
    if not is_f1(event):
        return {}
    out = {}
    label = F1_SESSION_LABELS.get(str(event.get("session") or ""))
    if label:
        out["session_label"] = label
    weekend = None
    for source_id in [event.get("id")] + list(event.get("source_events") or []):
        match = _JOLPICA_ID.match(str(source_id or ""))
        if match:
            weekend = "f1:%s:%d" % (match.group(1), int(match.group(2)))
            break
    if not weekend and event.get("weekend_key"):
        weekend = "f1:openf1:%s" % event["weekend_key"]
    if weekend:
        out["weekend_id"] = weekend
    return out


# ---------------------------------------------------------------- ranking

# Per-sport interest weight (0-20). Competition points are within-sport, so this makes sports comparable.
SPORT_WEIGHT = {
    "football": 20, "rugby_union": 16, "motorsport": 16, "rugby": 14, "cricket": 14, "tennis": 14, "boxing": 14,
    "rugby_league": 12, "golf": 12, "mma": 12, "darts": 12, "snooker": 10, "basketball": 8, "american_football": 8,
    "horse_racing": 8, "athletics": 7, "ice_hockey": 6, "cycling": 6, "baseball": 5,
}
DEFAULT_SPORT_WEIGHT = 3
TEAM_TAG_POINTS = {"team:england": 20, "team:england_women": 20, "team:great_britain": 20, "team:lions": 20,
                   "team:scotland": 15, "team:scotland_women": 15, "team:wales": 15, "team:wales_women": 15,
                   "team:northern_ireland": 15, "team:ireland": 15}
OTHER_TEAM_TAG_POINTS = 5
PPV_POINTS = 25
FEATURED_COMPETITION_POINTS = 5
RANK_SESSION_POINTS = {"race": 10, "qualifying": 5, "sprint": 5, "sprint_qualifying": 3, "practice1": -10,
                       "practice2": -10, "practice3": -10}
FEATURED_COUNT = 10

RANK_RULE = (
    "feature_rank = clamp(0..100, sport_weight + competition_points + featured_competition + team_points + ppv + "
    "corroboration + link + session - penalties). sport_weight 0-20 per sport (football 20, rugby union and motorsport "
    "16, cricket/tennis/boxing 14, ... other sports 3). competition_points = max(0, 40 - category_priority) for a named "
    "category (id not ending '.other'), else 0; +5 when competition_id is in display_policy.featured_competition_ids. "
    "team_points: team:england, england_women, great_britain, lions 20; scotland, wales, northern_ireland, ireland "
    "(and their women's sides) 15; any other team:* tag 5; ppv +25. +5 when corroboration >= 2. +5 when a "
    "broadcast link has binds=true, else +2 when there is any link. F1 sessions: race +10, qualifying/sprint +5, "
    "sprint qualifying +3, practice -10. Penalties: -10 when start_precision is date_only or time_tbc, -15 when "
    "tier is extra. Ties are broken by start_utc, then id.")


def feature_rank(row):
    """Integer 0-100 importance of a published event row (contract 4.3). Reads only published fields, so a reader can
    check it, but it is meant to be used as published."""
    sport = row.get("sport")
    points = SPORT_WEIGHT.get(sport, DEFAULT_SPORT_WEIGHT)
    category = str(row.get("category_id") or "")
    priority = row.get("category_priority")
    priority = priority if isinstance(priority, int) and not isinstance(priority, bool) else 90
    if category and not category.endswith(".other"):
        points += max(0, 40 - priority)
    if row.get("competition_id") in FEATURED_COMPETITION_IDS:
        points += FEATURED_COMPETITION_POINTS
    tags = set(row.get("tags") or ())
    team = [TEAM_TAG_POINTS.get(t, OTHER_TEAM_TAG_POINTS) for t in tags if t.startswith("team:")]
    points += max(team) if team else 0
    points += PPV_POINTS if "ppv" in tags else 0
    corroboration = row.get("corroboration")
    points += 5 if isinstance(corroboration, int) and corroboration >= 2 else 0
    links = row.get("broadcast_links") or []
    if any(isinstance(link, dict) and link.get("binds") for link in links):
        points += 5
    elif links:
        points += 2
    if sport == "motorsport":
        points += RANK_SESSION_POINTS.get(str(row.get("session") or ""), 0)
    if row.get("start_precision") in ("date_only", "time_tbc"):
        points -= 10
    if row.get("tier") == "extra":
        points -= 15
    return max(0, min(100, points))


def rank_order(rows):
    """Rows best first: feature_rank descending, then start_utc, then id (deterministic)."""
    return sorted(rows, key=lambda r: (-int(r.get("feature_rank") or 0), str(r.get("start_utc") or ""), str(r["id"])))


# ---------------------------------------------------------------- wire

# Fields computed here and published by feed._event_public (never copied from the internal record).
EVENT_FIELDS = ("participant_ids", "competition_logo", "feature_rank", "ppv", "ppv_label", "session_label", "weekend_id")


def event_metadata(event, row, crests=False):
    """Metadata fields for a published row: ``event`` is the internal record, ``row`` the public row built so far
    (it already has tags, tier, links, corroboration). ``crests`` is the crest kill switch for ``competition_logo``."""
    out = {}
    short = participants_short(event)
    if short:
        out["participants_short"] = short
    ids = participant_ids(event)
    if ids:
        out["participant_ids"] = ids
    logo = competition_logo_public(event) if crests else None
    if logo:
        out["competition_logo"] = logo
    out.update(ppv_fields(row))
    out.update(f1_fields(event))
    return out
