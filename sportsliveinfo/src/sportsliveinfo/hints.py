"""Channel hints (optional ``channel_hints`` asset, ``sli.channel-hints/1``) and the rights-holder prior.

Design rule: SportsLiveInfo decides, B1G follows the feed. B1G used to hard-code which channels look like sport and
how to order duplicates (``SportsChannelPriorityPolicy.kt``: keyword tiers, ``broadcasterRank``). This module publishes
those decisions as data, derived from the curated registry (``guide.SERVICES``) and the UK broadcast notes
(``docs/UK_BROADCAST_MATCHING.md``), so a correction reaches every TV without an app update. Everything is additive:
readers that do not know the asset keep their own tiers.

Nothing here is programme data or evidence that an event is on a channel. ``competition_rights`` is a *prior*: who
usually holds the rights, used only to suggest ``rights_holder_prior`` links that never bind.
"""
from zoneinfo import ZoneInfo

from . import linking
from .guide import REGIONAL_PARENTS, SERVICES

LONDON = ZoneInfo("Europe/London")
AS_OF = "2026-11-20"
SCHEMA = "sli.channel-hints/1"

# Broadcaster id, label, market and channel-id prefixes. Order matters: first match wins.
BROADCASTERS = [
    ("sky_sports", "Sky Sports", "GB", ("gb.sky.sports.",)),
    ("sky", "Sky (entertainment)", "GB", ("gb.sky.",)),
    ("tnt_sports", "TNT Sports", "GB", ("gb.tnt.sports.",)),
    ("premier_sports", "Premier Sports", "GB", ("gb.premier.sports.",)),
    ("eurosport", "Eurosport", "GB", ("gb.eurosport.",)),
    ("bbc", "BBC", "GB", ("gb.bbc.",)),
    ("itv", "ITV / STV / UTV", "GB", ("gb.itv.", "gb.stv", "gb.utv")),
    ("channel_4", "Channel 4", "GB", ("gb.c4.",)),
    ("channel_5", "Channel 5", "GB", ("gb.c5.",)),
    ("s4c", "S4C", "GB", ("gb.s4c",)),
    ("laliga_tv", "LaLiga TV", "GB", ("gb.laliga.",)),
    ("racing_tv", "Racing TV", "GB", ("gb.racing.",)),
    ("club_tv", "Club channels", "GB", ("gb.club.",)),
    ("rte", "RTE", "IE", ("ie.rte.",)),
    ("virgin_media", "Virgin Media", "IE", ("ie.virgin.",)),
    ("tg4", "TG4", "IE", ("ie.tg4",)),
    ("canal_plus", "Canal+", "FR", ("fr.canal.",)),
    ("bein", "beIN Sports", "FR", ("fr.bein.", "hk.bein.")),
    ("rmc_sport", "RMC Sport", "FR", ("fr.rmc.",)),
    ("eurosport_fr", "Eurosport (FR)", "FR", ("fr.eurosport.",)),
    ("lequipe", "L'Equipe", "FR", ("fr.lequipe",)),
    ("french_fta", "French free-to-air", "FR", ("fr.francetv.", "fr.tf1.", "fr.m6.")),
    ("espn", "ESPN", "US", ("us.espn",)),
    ("fox_sports", "Fox Sports", "US", ("us.fox.",)),
    ("us_league_tv", "League channels (US)", "US", ("us.nfl.", "us.nba.")),
    ("us_specialist", "Golf / Tennis Channel", "US", ("us.golf.", "us.tennis.")),
    ("tsn_sportsnet", "TSN / Sportsnet", "CA", ("ca.",)),
    ("fox_sports_au", "Fox Sports (AU)", "AU", ("au.fox.",)),
    ("sky_sport_nz", "Sky Sport (NZ)", "NZ", ("nz.sky.",)),
    ("now_sports", "Now Sports (HK)", "HK", ("hk.now.",)),
    ("astro", "Astro (MY)", "MY", ("my.astro.",)),
    ("setanta", "Setanta (GE)", "GE", ("ge.setanta.",)),
]

# Specialist channels: the sports a channel is the natural home of (reader sorts these first for that sport).
SPORT_AFFINITY = {
    "gb.sky.sports.f1": ["motorsport"], "gb.sky.sports.cricket": ["cricket"], "gb.sky.sports.tennis": ["tennis"],
    "gb.sky.sports.golf": ["golf"], "gb.sky.sports.racing": ["horse_racing"], "gb.racing.tv": ["horse_racing"],
    "gb.sky.sports.premier_league": ["football"], "gb.sky.sports.football": ["football"],
    "gb.premier.sports.rugby": ["rugby", "rugby_union", "rugby_league"], "gb.laliga.tv": ["football"],
    "gb.club.mutv": ["football"], "gb.club.lfctv": ["football"], "fr.canal.foot": ["football"],
    "us.nfl.network": ["american_football"], "us.nba.tv": ["basketball"], "us.golf.channel": ["golf"],
    "us.tennis.channel": ["tennis"], "au.fox.footy": ["aussie_rules"], "au.fox.cricket": ["cricket"],
    "au.fox.league": ["rugby_league"], "hk.now.sports.premier_league": ["football"],
    "my.astro.premier_league": ["football"], "nz.sky.sport.premier_league": ["football"],
}

# Registry ids of general-entertainment or news channels (not sport specialists). The main channels of a public or
# commercial broadcaster that carry live sport are tier 2, their secondary channels tier 3.
_GENERAL_MAIN = {"gb.bbc.one", "gb.bbc.two", "gb.itv.one", "gb.c4.channel4", "gb.c5.channel5", "gb.s4c", "ie.rte.one",
                 "ie.rte.two", "ie.virgin.one", "ie.tg4", "fr.francetv.france2", "fr.francetv.france3", "fr.tf1.tf1",
                 "fr.m6.m6", "fr.canal.main", "gb.stv", "gb.utv", "gb.bbc.scotland", "gb.bbc.alba"}
_NEWS = {"gb.bbc.news", "gb.sky.sports.news", "us.espnews"}
_GENERAL_SECONDARY_PREFIX = ("gb.bbc.", "gb.itv.", "gb.c4.", "gb.c5.", "gb.sky.mix", "fr.francetv.", "fr.tf1.", "fr.m6.")

# Per-sport order of broadcasters for the owner's home market (GB), best first. Seeded from the owner's own tiers in
# B1G (Sky/TNT/Premier before free-to-air for football; Sky F1; Sky cricket and rugby specialists) and the UK notes
# (docs/UK_BROADCAST_MATCHING.md hard cases: F1, boxing PPV, tennis, cricket, rugby). The reader sorts equally-bound
# links by (sport affinity, rank here, link rank); links of broadcasters not listed come after, by tier.
_DEFAULT_RANK = ["sky_sports", "tnt_sports", "bbc", "itv", "channel_4", "channel_5", "premier_sports", "eurosport"]
BROADCASTER_RANK = {
    "football": ["sky_sports", "tnt_sports", "bbc", "itv", "premier_sports", "channel_4", "channel_5", "s4c",
                 "eurosport", "laliga_tv", "club_tv"],
    "motorsport": ["sky_sports", "channel_4", "bbc", "itv", "eurosport", "premier_sports"],
    "cricket": ["sky_sports", "bbc", "channel_4", "itv", "channel_5"],
    "rugby": ["sky_sports", "premier_sports", "tnt_sports", "bbc", "itv", "s4c", "channel_4"],
    "rugby_union": ["sky_sports", "premier_sports", "tnt_sports", "bbc", "itv", "s4c", "channel_4"],
    "rugby_league": ["sky_sports", "premier_sports", "bbc", "channel_4", "itv"],
    "tennis": ["sky_sports", "bbc", "eurosport", "tnt_sports", "channel_4"],
    "golf": ["sky_sports", "bbc", "eurosport", "tnt_sports"],
    "boxing": ["sky_sports", "tnt_sports", "premier_sports", "channel_5", "itv"],
    "mma": ["tnt_sports", "sky_sports", "premier_sports"],
    "darts": ["sky_sports", "itv", "bbc", "channel_4", "premier_sports"],
    "snooker": ["bbc", "eurosport", "itv", "sky_sports", "channel_4"],
    "horse_racing": ["racing_tv", "itv", "sky_sports", "channel_4", "channel_5"],
    "american_football": ["sky_sports", "bbc", "itv", "channel_4"],
    "basketball": ["sky_sports", "tnt_sports", "premier_sports"],
}

# Competition -> usual UK rights holders (a PRIOR, not evidence): channel ids, most likely first. Owner-maintained; kept
# to competitions with long, public rights deals. Used only to suggest ``rights_holder_prior`` links.
COMPETITION_RIGHTS = {
    "football.premier_league": ["gb.sky.sports.premier_league", "gb.sky.sports.main_event", "gb.tnt.sports.1"],
    "football.champions_league": ["gb.tnt.sports.1"],
    "football.europa_league": ["gb.tnt.sports.1"],
    "football.conference_league": ["gb.tnt.sports.1"],
    "motorsport.f1": ["gb.sky.sports.f1"],
}
# Competitions whose Saturday 3 pm UK kick-offs are not shown live in the UK (blackout): no prior then
# (docs/UK_BROADCAST_MATCHING.md: "Premier League Saturday blackout").
BLACKOUT_COMPETITIONS = frozenset({"football.premier_league"})
BLACKOUT_FROM, BLACKOUT_TO = (14, 30), (15, 30)

TIER_LEGEND = {
    "1": "sport specialist: carries live sport (Sky Sports, TNT Sports, beIN, ESPN...)",
    "2": "main channel of a general broadcaster that carries live sport (BBC One/Two, ITV1, Channel 4/5, RTE...)",
    "3": "secondary general channel (BBC Three/Four, ITV2-4, E4, More4, Sky Mix, TMC, W9...)",
    "4": "news channel (never the home of a live event)",
    "5": "other",
}


def broadcaster_of(channel_id):
    cid = str(channel_id or "")
    for bid, _, _, prefixes in BROADCASTERS:
        if cid.startswith(prefixes):
            return bid
    return None


def _classify(cid):
    """(sports_class, tier) of a curated registry channel id."""
    if cid in _NEWS:
        return "news", 4
    if cid in _GENERAL_MAIN:
        return "general", 2
    bid = broadcaster_of(cid)
    if cid.startswith(_GENERAL_SECONDARY_PREFIX) or bid in ("french_fta",) or cid in ("gb.c4.e4", "gb.c4.more4"):
        return "general", 3
    if bid in (None, "sky"):
        return "other", 5
    return "sports", 1


def channel_entries():
    """{channel id: hint} for every curated registry service and regional service."""
    ids = {cid for table in SERVICES.values() for cid in table.values()}
    entries = {}
    for cid in sorted(ids):
        sports_class, tier = _classify(cid)
        row = {"sports_class": sports_class, "tier": tier}
        bid = broadcaster_of(cid)
        if bid:
            row["broadcaster"] = bid
        if cid in SPORT_AFFINITY:
            row["sports"] = SPORT_AFFINITY[cid]
        entries[cid] = row
    for cid, (parent, _region) in sorted(REGIONAL_PARENTS.items()):
        base = entries.get(parent) or {"sports_class": "general", "tier": 2}
        row = {"sports_class": base["sports_class"], "tier": base["tier"], "parent": parent}
        bid = broadcaster_of(cid) or base.get("broadcaster")
        if bid:
            row["broadcaster"] = bid
        entries[cid] = row
    return entries


def channel_hints_document():
    """The optional ``channel_hints`` asset: compact, deterministic, registry-derived."""
    used = {row["broadcaster"] for row in channel_entries().values() if row.get("broadcaster")}
    return {
        "schema": SCHEMA, "as_of": AS_OF,
        "market": "GB",
        "tiers": TIER_LEGEND,
        "broadcasters": [{"id": bid, "label": label, "market": market}
                         for bid, label, market, _ in BROADCASTERS if bid in used],
        "channels": channel_entries(),
        "broadcaster_rank": dict(BROADCASTER_RANK, default=_DEFAULT_RANK),
        "competition_rights": COMPETITION_RIGHTS,
        "rules": {
            "scope": "curated registry channel ids only (gb.sky.sports.f1); a dictionary-only id has no entry: fall back "
                     "to your own keyword tiers or treat it as sports_class 'other'",
            "sports_class": "sports | general | news | other: whether the channel is a sport specialist, a general "
                            "broadcaster, a news channel or none; a 'news' or 'other' channel is not the home of a live "
                            "event",
            "tier": "1 = best home for live sport; see tiers. Replaces keyword tiers",
            "order_equal_links": "among links that bind, sort by: channel.sports contains the event's sport first, then "
                                 "the index of channel.broadcaster in broadcaster_rank[sport] (else 'default'; an "
                                 "unlisted broadcaster last), then published rank. Never reorder a corroborated link "
                                 "below an uncorroborated one",
            "broadcaster_rank": "owner's home market (GB); other markets' channels use tier only",
            "competition_rights": "PRIOR only (who usually holds the rights). Not evidence that this event is on that "
                                  "channel; never bind from it. SportsLiveInfo publishes it as links with status "
                                  "'rights_holder_prior' (binds false) when the owner enables it",
            "regional": "regional services inherit class and tier of their parent",
        },
    }


# ---- per-event slot hint -----------------------------------------------------------------------------------
def slot_hint(event):
    """Where B1G should look in the provider guide for this event, or None when it cannot be said.

    Same window the corroboration rule uses (linking.CORROBORATION_BEFORE/AFTER): a programme that *starts* between
    kick-off - 60 min and kick-off + 20 min and overlaps the event. Derived from the event's own start only (no guide
    data). ``match``: "teams" (fixture named in the title), "session" (F1 session) or "tournament" (one side or none:
    the competition's coverage, never a particular match)."""
    if event.get("start_precision") in linking.UNCONFIRMED_START_PRECISIONS or not event.get("start_utc"):
        return None
    if event.get("status_normalized") in ("postponed", "cancelled"):
        return None
    try:
        start = linking._dt(event["start_utc"])
    except (TypeError, ValueError):
        return None
    if event.get("sport") == "motorsport":
        match = "session"
    elif len(event.get("participants") or []) >= 2:
        match = "teams"
    else:
        match = "tournament"
    zulu = "%Y-%m-%dT%H:%M:%SZ"
    return {"starts_from_utc": (start - linking.CORROBORATION_BEFORE).strftime(zulu),
            "starts_to_utc": (start + linking.CORROBORATION_AFTER).strftime(zulu), "match": match}


# ---- rights-holder prior ----------------------------------------------------------------------------------------
def _blackout(event):
    try:
        local = linking._dt(event["start_utc"]).astimezone(LONDON)
    except (KeyError, TypeError, ValueError):
        return True            # unknown time: never suggest
    return local.weekday() == 5 and BLACKOUT_FROM <= (local.hour, local.minute) <= BLACKOUT_TO


def rights_holder_prior(event):
    """Candidate channel ids that usually hold the rights for ``event``'s competition in the owner's market.

    Empty unless the competition is in ``COMPETITION_RIGHTS``, the start is confirmed and the event is not a
    blackout slot. The caller publishes them as ``rights_holder_prior`` links that never bind."""
    competition = event.get("competition_id") or event.get("category_id") or ""
    channels = COMPETITION_RIGHTS.get(competition)
    if not channels or event.get("start_precision") in linking.UNCONFIRMED_START_PRECISIONS:
        return []
    if event.get("status_normalized") in ("postponed", "cancelled", "finished"):
        return []
    if competition in BLACKOUT_COMPETITIONS and _blackout(event):
        return []
    return list(channels)
