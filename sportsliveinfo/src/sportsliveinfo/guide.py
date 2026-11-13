"""Private, source-aware EPG coverage and channel identity diagnostics.

Never equate an inferred EPG service with a playable B1G subscription stream.
All programme text remains in the private HAOS database until rights are cleared.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import html
import re
import unicodedata

COUNTRY_BY_SOURCE = {
    **{f"iptv_epg_{market.lower()}": market for market in ("DE", "IT", "ES", "NL", "CA")},
    "farleyflex": "GB", "uk_freeview": "GB", "epgshare_uk": "GB", "mjh_sky_uk": "GB",
    "iptvorg_sky_uk": "GB", "epgtalk_uk": "GB", "iptv_epg_gb": "GB",
    "epgshare_ie": "IE",
    "fr_programmetv": "FR", "fr_telerama": "FR", "fr_xmltv": "FR", "epgshare_fr": "FR", "iptv_epg_fr": "FR",
    "epgshare_us": "US", "epgshare_us_sports": "US", "iptvorg_foxtel_au": "AU", "iptv_epg_au": "AU",
    "epgshare_hk": "HK", "iptv_epg_hk": "HK", "iptv_epg_ge": "GE", "epgshare_my": "MY",
    "mjh_nz": "NZ", "mjh_au_sydney": "AU",
    "epgshare_ca": "CA", "epgshare_au": "AU", "epgshare_nz": "NZ", "epgshare_pt": "PT",
    "epgshare_pl": "PL", "epgshare_gr": "GR", "epgshare_sg": "SG", "epgshare_in": "IN",
}

# An intentionally small *verified-name* registry, per market. Exact catalogue
# IDs always need a source namespace; this is a reporting aid, not a stream
# router. Never strip service qualifiers: Sports+, region, +1, Canal+ Sport 360.
SERVICES = {
    "GB": {
        "bbc one": "gb.bbc.one", "bbc two": "gb.bbc.two", "bbc three": "gb.bbc.three", "bbc four": "gb.bbc.four",
        "bbc news": "gb.bbc.news",
        "itv 1": "gb.itv.one", "itv 2": "gb.itv.two", "itv 3": "gb.itv.three", "itv 4": "gb.itv.four",
        "channel 4": "gb.c4.channel4", "channel 5": "gb.c5.channel5", "e4": "gb.c4.e4", "more4": "gb.c4.more4", "s4c": "gb.s4c",
        "sky sports main event": "gb.sky.sports.main_event",
        "sky sports premier league": "gb.sky.sports.premier_league",
        "sky sports f1": "gb.sky.sports.f1",
        "sky sports football": "gb.sky.sports.football",
        "sky sports cricket": "gb.sky.sports.cricket",
        "sky sports tennis": "gb.sky.sports.tennis",
        "sky sports golf": "gb.sky.sports.golf",
        "sky sports racing": "gb.sky.sports.racing",
        "sky sports mix": "gb.sky.sports.mix",
        "sky sports action": "gb.sky.sports.action",
        "sky sports news": "gb.sky.sports.news",
        "sky sports box office": "gb.sky.sports.box_office",
        "sky sports +": "gb.sky.sports.plus",
        "tnt sports box office": "gb.tnt.sports.box_office",
        "tnt sports box office 2": "gb.tnt.sports.box_office.2",
        "premier sports rugby": "gb.premier.sports.rugby",
        "tnt sports 1": "gb.tnt.sports.1", "tnt sports 2": "gb.tnt.sports.2",
        "tnt sports 3": "gb.tnt.sports.3", "tnt sports 4": "gb.tnt.sports.4",
        "tnt sports ultimate": "gb.tnt.sports.ultimate",
        "premier sports 1": "gb.premier.sports.1", "premier sports 2": "gb.premier.sports.2",
        "eurosport 1": "gb.eurosport.1", "eurosport 2": "gb.eurosport.2",
        "laliga tv": "gb.laliga.tv", "racing tv": "gb.racing.tv", "mutv": "gb.club.mutv", "lfc tv": "gb.club.lfctv",
    },
    "IE": {
        "rte one": "ie.rte.one", "rte 2": "ie.rte.two", "virgin media one": "ie.virgin.one", "tg4": "ie.tg4",
    },
    "FR": {
        "france 2": "fr.francetv.france2", "france 3": "fr.francetv.france3",
        "france 4": "fr.francetv.france4", "france 5": "fr.francetv.france5",
        "tf1": "fr.tf1.tf1", "tmc": "fr.tf1.tmc", "m6": "fr.m6.m6", "w9": "fr.m6.w9",
        "canal+": "fr.canal.main", "canal+ sport": "fr.canal.sport", "canal+ sport 360": "fr.canal.sport360",
        "canal+ foot": "fr.canal.foot",
        "bein sports 1": "fr.bein.sports.1", "bein sports 2": "fr.bein.sports.2", "bein sports 3": "fr.bein.sports.3",
        "rmc sport 1": "fr.rmc.sport.1", "rmc sport 2": "fr.rmc.sport.2",
        "eurosport 1": "fr.eurosport.1", "eurosport 2": "fr.eurosport.2",
        "l'equipe": "fr.lequipe", "l equipe": "fr.lequipe", "lequipe": "fr.lequipe",
    },
    "US": {
        "espn": "us.espn", "espn2": "us.espn2", "fs1": "us.fox.fs1", "nfl network": "us.nfl.network",
        "nba tv": "us.nba.tv", "golf channel": "us.golf.channel",
        "fs2": "us.fox.fs2", "tennis channel": "us.tennis.channel",
        "espnu": "us.espnu", "espnews": "us.espnews", "espn deportes": "us.espn.deportes",
    },
    "CA": {
        **{f"tsn {number}": f"ca.tsn.{number}" for number in range(1, 6)},
        **{f"sportsnet {region.lower()}": f"ca.sportsnet.{region.lower()}"
           for region in ("East", "Ontario", "West", "One", "360", "World", "Pacific")},
    },
    "AU": {"fox footy": "au.fox.footy", "fox cricket": "au.fox.cricket", "fox league": "au.fox.league"},
    "HK": {
        # Hong Kong Communications Authority, Now TV lineup as of December 2025.
        "now sports premier league": "hk.now.sports.premier_league",
        "now sports premier league tv": "hk.now.sports.premier_league",
        "now sports prime": "hk.now.sports.prime",
        "now sports plus": "hk.now.sports.plus",
        **{f"now sports {number}": f"hk.now.sports.{number}" for number in range(1, 8)},
        **{f"now sports premier league {number}": f"hk.now.sports.premier_league.{number}" for number in range(1, 8)},
        **{f"now sports 4k{number}": f"hk.now.sports.4k{number}" for number in range(1, 4)},
        **{f"bein sports {number}": f"hk.bein.sports.{number}" for number in range(1, 7)},
    },
    "MY": {"astro premier league": "my.astro.premier_league"},
    "GE": {"setanta sports 1": "ge.setanta.sports.1", "setanta sports 2": "ge.setanta.sports.2"},
}
KNOWN_SERVICES = {name: cid for table in SERVICES.values() for name, cid in table.items()}

# Exact source-scoped EPG ids (strongest evidence). farleyflex ids are those the
# B1G apps already remap to (BroadcasterEpgAliases.kt / sports-epg-aliases.ts),
# including the source's own "premiereleague" spelling.
SOURCE_ID_CROSSWALK = {
    "iptv_epg_gb": {
        "SkySportsPlus.uk": "gb.sky.sports.plus",
        "PremierSportsRugby.uk": "gb.premier.sports.rugby",
        "TNTSportsBoxOffice.uk": "gb.tnt.sports.box_office",
        "TNTSportsBoxOffice2.uk": "gb.tnt.sports.box_office.2",
        **{f"TNTSports{number}.uk": f"gb.tnt.sports.{number}" for number in range(5, 11)},
    },
    "epgshare_us": {
        "FS1.Fox.Sports.1.HD.us2": "us.fox.fs1",
        "FS2.Fox.Sports.2.HD.us2": "us.fox.fs2",
        "FS2.HD.us2": "us.fox.fs2",
        "Tennis.Channel.HD.us2": "us.tennis.channel",
        "ESPNU.HD.us2": "us.espnu",
        "ESPNEWS.HD.us2": "us.espnews",
        "ESPN.Deportes.HD.us2": "us.espn.deportes",
    },
    "epgshare_ca": {
        **{f"TSN.{number}{quality}.ca2": f"ca.tsn.{number}"
           for number in range(1, 6) for quality in ("", ".HD")},
        **{f"Sportsnet.{region}.HD.ca2": f"ca.sportsnet.{region.lower()}"
           for region in ("East", "Ontario", "West", "One", "360", "World")},
        "Sportsnet.(Pacific).HD.ca2": "ca.sportsnet.pacific",
    },
    "farleyflex": {
        "skysportsmainevent.uk": "gb.sky.sports.main_event",
        "skysportspremiereleague.uk": "gb.sky.sports.premier_league",
        "skysportsfootball.uk": "gb.sky.sports.football",
        "skysportscricket.uk": "gb.sky.sports.cricket",
        "skysportsf1.uk": "gb.sky.sports.f1",
        "skysportsgolf.uk": "gb.sky.sports.golf",
        "skysportstennis.uk": "gb.sky.sports.tennis",
        "skysportsracing.uk": "gb.sky.sports.racing",
        "skysportsmix.uk": "gb.sky.sports.mix",
        "skysportsaction.uk": "gb.sky.sports.action",
        "skysportsnews.uk": "gb.sky.sports.news",
        "tntsports1.uk": "gb.tnt.sports.1", "tntsports2.uk": "gb.tnt.sports.2",
        "tntsports3.uk": "gb.tnt.sports.3", "tntsports4.uk": "gb.tnt.sports.4",
        "premiersports1.uk": "gb.premier.sports.1", "premiersports2.uk": "gb.premier.sports.2",
    },
}

# Lineup families (as in the B1G sports category-family review). Families are
# coverage diagnostics only and never assign an exact service identity.
CHANNEL_FAMILIES = [
    ("sky_sports", "Sky Sports (UK)", r"^sky sports\b"),
    ("tnt_sports", "TNT Sports / BT Sport (UK)", r"^(?:tnt|bt) sports?\b"),
    ("premier_sports", "Premier Sports (UK/IE)", r"^premier sports\b"),
    ("uk_ie_fta", "UK & Ireland free-to-air", r"^(?:bbc|itv|channel [45]|e4|more4|s4c|rte|virgin media|tg4)\b"),
    ("eurosport", "Eurosport", r"^eurosport\b"),
    ("dazn", "DAZN", r"^dazn\b"),
    ("bein", "beIN Sports", r"^bein\b"),
    ("canal_plus", "Canal+ (FR)", r"^canal\+"),
    ("rmc_sport", "RMC Sport (FR)", r"^rmc sport\b"),
    ("setanta", "Setanta Sports", r"^setanta\b"),
    ("now_sports_hk", "Now Sports (Hong Kong)", r"^now (?:sports|premier league|golf)\b"),
    ("astro", "Astro (Malaysia)", r"^astro\b"),
    ("supersport", "SuperSport (Africa)", r"^supersport\b"),
    ("espn", "ESPN", r"^espn"),
    ("fox_sports", "Fox Sports", r"^(?:fox sports|fs1|fs2|fox footy|fox cricket|fox league)\b"),
    ("tsn_sportsnet", "TSN / Sportsnet (CA)", r"^(?:tsn|sportsnet)\b"),
    ("viaplay", "Viaplay", r"^viaplay\b"),
    ("flosports", "FloSports / SuperLeague+", r"^(?:flo ?(?:sports|rugby|racing|wrestling|hockey|football)|super ?league\+)"),
    ("club_league_tv", "League & club channels", r"^(?:laliga tv|mutv|lfc tv|chelsea tv|nfl network|nba tv|mlb network|nhl network|nfl game ?pass)\b"),
    ("racing", "Horse racing channels", r"^(?:racing tv|sky sports racing|at the races)\b"),
    ("ppv", "PPV / Box Office", r"\b(?:ppv|box office|pay per view)\b"),
    # Streaming event services seen in the owner's provider categories. These
    # usually carry event slots with no XMLTV guide; fixture binding must come
    # from the event name, never from league-rights assumptions.
    ("sky_sports_plus", "Sky Sports+ (UK)", r"^sky sports ?\+"),
    ("amazon_prime", "Amazon Prime Video sport", r"^(?:amazon|prime video)\b"),
    ("hbo_max", "HBO Max / TNT sport events", r"^(?:hbo ?max|max sport)\b"),
    ("peacock", "Peacock", r"^peacock\b"),
    ("paramount_plus", "Paramount+", r"^paramount ?\+"),
    ("fubo", "Fubo Sports", r"^fubo\b"),
    ("us_networks", "US networks (ABC/CBS/NBC/Fox/USA)", r"^(?:abc|cbs|nbc|fox|usa network|tnt|tbs|nbcsn)\b(?! (?:sports?\b|footy|cricket|league))"),
    ("us_team_channels", "US league/team channels (MLB/NBA/WNBA/NFL/NHL)", r"^(?:mlb|nba|wnba|nfl|nhl)\b"),
    ("kayo_stan", "Kayo / Stan Sport (AU)", r"^(?:kayo|stan sports?)\b"),
    ("sky_sport_nz", "Sky Sport (NZ)", r"(?:^|\| )(?:nz\b.*\bsky sports?\b|sky sports? (?:\d+ )?nz\b|sky sport (?:now|select)\b)"),
    ("tennis_channel", "Tennis Channel", r"^tennis channel\b"),
    ("onefootball", "OneFootball", r"^onefootball\b"),
    ("coupang_play", "Coupang Play (KR)", r"^coupang\b"),
    ("vidio_mola", "Vidio / Mola (ID)", r"^(?:vidio|mola)\b"),
    ("hub_sports", "Hub Sports / StarHub (SG)", r"^(?:hub sports?|starhub)\b"),
    ("shahid_ssc", "SSC / Shahid (Saudi)", r"^(?:ssc|shahid)\b"),
    ("in_pk_sports", "India/Pakistan sport (Star, Sony, PTV, Willow, Ten)", r"^(?:star sports|sony (?:sports|ten|six)|ptv sports|willow|ten sports|a sports)\b"),
    ("fite", "Fite TV (combat PPV)", r"^fite\b"),
    ("europe_sport_nets", "European sport networks (Sport TV, Eleven, Polsat, Canal+ Sport PL, Nova, Cosmote, V Sport, TV2 Sport)",
     r"^(?:sport ?tv|eleven|polsat sport|canal\+ sport \d\b|nova sports?|cosmote sport|v sport|tv ?2 sport|c more|ziggo sport|dazn \d)"),
    ("latin_sport_nets", "Latin American sport networks (ESPN LatAm, TyC, Fox Sports AR, TUDN)", r"^(?:tyc|tudn|tnt sports (?:ar|cl|br)|fox sports (?:ar|mx|premium))\b"),
]
_FAMILY_PATTERNS = [(fid, label, re.compile(pattern)) for fid, label, pattern in CHANNEL_FAMILIES]

DECORATION = re.compile(r"\s*[\[(](?:vip|sd|hd|fhd|uhd|4k|hdr|hevc|backup|back up|alt|b|raw|multi|50 ?fps|60 ?fps|1080p|720p)[\])]\s*", re.I)
# Provider annotations that never change the service. Exact forms only: "(MX)", "(DET)" or a
# city in brackets are market/location identity and must survive.
ANNOTATION = re.compile(r"\s*\((?:uk|gb|x|d|m|from [^)]*|(?:live )?events? only|live event only)\)\s*", re.I)
IRISH_FEED = re.compile(r"\s*\((?:ie|roi)\)\s*", re.I)
TRAILING_JUNK = re.compile(r"\s+(?:vip|backup|raw|50 ?fps|60 ?fps)$", re.I)
QUALITY_SUFFIX = re.compile(r"\s+(?:hd|fhd|sd|uhd|4k|hdr|hevc|h265|h264|2160p|1080p|720p|vip|backup|raw|50 ?fps|60 ?fps)$", re.I)
COUNTRY_PREFIX = re.compile(r"^(uk|gb|fr|france|ie|irl|us|usa|ca|can|au|aus|nz|hk|hkg|my|mys|sg|ge|geo|pt|pl|gr|in|pk|ar|ara|arabic|mena|int|sports)\s*(?:[|:\-])\s*", re.I)
BRACKET_COUNTRY = re.compile(r"^\((uk|gb|fr|ie|us|ca|au|nz|hk|my|sg|ge|pt|pl|gr|in|pk)\)\s*", re.I)
COUNTRY_PREFIX_ALIASES = {
    "uk": "gb", "france": "fr", "irl": "ie", "usa": "us", "can": "ca",
    "aus": "au", "hkg": "hk", "mys": "my", "geo": "ge",
}
SPACES = re.compile(r"\s+")
GENERIC_PROGRAMME = re.compile(r"^(?:live (?:football|sport|sports|rugby|cricket|tennis|boxing)|to be announced|tba|programme information|no information|sporting event|live event)$", re.I)


def normalized_name(name):
    """Remove safe decorations while retaining identity-bearing service variants."""
    value = unicodedata.normalize("NFKD", html.unescape(str(name)))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.replace("*", " ")
    irish = bool(IRISH_FEED.search(value))     # Irish feed of a UK service: identity-bearing, kept as "roi"
    value = IRISH_FEED.sub(" ", value)
    value = ANNOTATION.sub(" ", value)
    value = DECORATION.sub(" ", value.replace("\u00ae", "").replace("\u2122", ""))
    value = value.casefold().replace("&", " and ").strip()
    value = BRACKET_COUNTRY.sub("", value)
    value = COUNTRY_PREFIX.sub("", value)
    value = SPACES.sub(" ", value)
    while True:
        new = re.sub(r"\s*[-|:]$", "", TRAILING_JUNK.sub("", QUALITY_SUFFIX.sub("", value))).strip()
        if new == value:
            break
        value = new
    value = re.sub(r"\bbbc\s*1\b", "bbc one", value)
    value = re.sub(r"\bbbc\s*2\b", "bbc two", value)
    value = re.sub(r"\bitv\s*one\b", "itv 1", value)
    value = re.sub(r"\bitv\s*([1-4])\b", r"itv \1", value)
    value = re.sub(r"\brte\s*2\b", "rte 2", value)
    value = value.replace("be in sports", "bein sports")
    value = SPACES.sub(" ", value).strip()
    return value + " roi" if irish and value else value


# ---- Display variants: keep every provider channel, label the difference sensibly ----
# Matching (normalized_name) deliberately ignores quality copies so they share one
# guide. Display must do the opposite: every channel stays selectable, shown as a
# tidy base name plus short variant tags. Identity parts (+1, numbers, regions,
# beIN (G)/(N)/(F), cities) stay in the base name.
VARIANT_TAGS = (
    (r"\b(?:uhd|4k|2160p)\b", "4K"), (r"\bfhd\b|\b1080p\b", "FHD"), (r"(?<![fu])\bhd\b|\b720p\b|\u1d34\u1d30", "HD"),
    (r"\bsd\b", "SD"), (r"\bhdr\b", "HDR"), (r"\b(50|60)\s?fps\b", "{0}fps"), (r"\b(?:hevc|h\.?265)\b", "HEVC"),
    (r"\((?:ie|roi)\)", "Ireland"), (r"\(from ([^)]*?)(?:\s+uk)?\)", "from {0}"),
    (r"\((?:live )?events? only\)|\(live event only\)", "Events only"),
    (r"\bvip\b", "VIP"), (r"\braw\b", "RAW"), (r"\b(?:backup|back up)\b", "Backup"), (r"\balt\b", "Alt"),
    (r"\*", "Alt feed"), (r"\(x\)", "Source X"), (r"\(d\)", "Source D"), (r"\(m\)", "Source M"),
)
_VARIANT_STRIP = re.compile(r"\s*(?:\((?:uk|gb|ie|roi|x|d|m|from [^)]*|(?:live )?events? only|live event only)\)"
                            r"|[\[(](?:vip|hd|fhd|sd|uhd|4k|hevc)[\])])\s*", re.I)
_VARIANT_WORDS = re.compile(r"(?<=\S)\s+-?\s*(?:uhd/?|4k|2160p|fhd|1080p|hd|720p|sd|hdr|hevc|h\.?265|50\s?fps|60\s?fps|vip|raw|"
                            r"backup|alt)(?=\s|$)", re.I)
_DISPLAY_PREFIX = re.compile(r"^\s*(?:(?:uk|gb|us|ca|fr|de|ie|au)\s*[-|:]|4k\s*\|)\s*", re.I)


def channel_variant(name):
    """{"base", "tags", "label"} for display. Never used to merge or hide channels."""
    original = html.unescape(str(name))
    tags = []
    for pattern, label in VARIANT_TAGS:
        match = re.search(pattern, original, re.I)
        if match:
            text = label.format(*(g.strip() for g in match.groups())) if match.groups() else label
            if text not in tags:
                tags.append(text)
    base = _VARIANT_STRIP.sub(" ", original.replace("*", " "))
    base = _DISPLAY_PREFIX.sub("", base)
    stripped = _VARIANT_WORDS.sub(" ", base)
    base = stripped if stripped.strip(" -|:/") else base       # never strip a name down to nothing
    base = SPACES.sub(" ", base).strip(" -|:/")
    return {"base": base, "tags": tags, "label": " · ".join([base] + tags)}


def display_labels(names):
    """Labels for one category in provider order; identical labels are numbered (· 2, · 3)."""
    seen = defaultdict(int)
    out = []
    for name in names:
        label = channel_variant(name)["label"]
        seen[label] += 1
        out.append(label if seen[label] == 1 else "%s · %d" % (label, seen[label]))
    return out


def canonical_channel(source_id, epg_id, display_name):
    """Conservative identity hint: never infer unknown regional or suffix variants.

    An exact source-scoped EPG id wins; otherwise the normalised name must be
    in the source market's own service table.
    """
    exact = SOURCE_ID_CROSSWALK.get(source_id, {}).get(str(epg_id or ""))
    if exact:
        return exact
    market = COUNTRY_BY_SOURCE.get(source_id)
    if not market:
        return None
    prefix = COUNTRY_PREFIX.match(str(display_name).strip())
    if prefix:
        region = prefix[1].casefold()
        if region != "sports" and COUNTRY_PREFIX_ALIASES.get(region, region) != market.casefold():
            return None
    return SERVICES.get(market, {}).get(normalized_name(display_name))


_RAW_FAMILIES = {"sky_sport_nz"}  # need the market prefix that normalized_name() strips


def channel_families(display_name):
    name = normalized_name(display_name)
    raw = unicodedata.normalize("NFKD", str(display_name))
    raw = SPACES.sub(" ", "".join(ch for ch in raw if not unicodedata.combining(ch)).casefold()).strip()
    return [fid for fid, _, pattern in _FAMILY_PATTERNS
            if pattern.search(name) or (fid in _RAW_FAMILIES and pattern.search(raw))]


def _dt(value):
    if not isinstance(value, str):
        raise ValueError("Date must be ISO8601")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Time must specify UTC offset")
    return parsed.astimezone(timezone.utc)


def _union_hours(ranges, start, end):
    intervals = sorted((max(a, start), min(b, end)) for a, b in ranges if a < end and b > start)
    if not intervals:
        return 0.0
    total = timedelta()
    lo, hi = intervals[0]
    for a, b in intervals[1:]:
        if a > hi:
            total += hi - lo
            lo, hi = a, b
        else:
            hi = max(hi, b)
    total += hi - lo
    return round(total.total_seconds() / 3600.0, 2)


def analyze_guide(guide, now=None, detail_limit=30):
    """Compute independent EPG quality/coverage from the full private source guide.

    No programme titles/descriptions go into the public GitHub output. Lists
    are bounded to keep the Ingress dashboard responsive on very large guides.
    """
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    source_id = guide.get("source_id", "")
    channels = guide.get("channels", {})
    programmes = guide.get("programmes", [])
    grouped = defaultdict(list)
    detailed = defaultdict(list)
    bad = 0
    generic = 0
    for row in programmes:
        try:
            a, b = _dt(row["start_utc"]), _dt(row["end_utc"])
            if a >= b or (b - a) > timedelta(days=10):
                bad += 1
                continue
            channel_id = str(row["channel_id"])
            title = row.get("title", "")
            if not title:
                bad += 1
                continue
            if GENERIC_PROGRAMME.fullmatch(title.strip()):
                generic += 1
            else:
                detailed[channel_id].append((a, b))
            grouped[channel_id].append((a, b))
        except (KeyError, ValueError, TypeError, OverflowError):
            bad += 1
    breakdown = []
    counts = {"24h": 0, "72h": 0, "168h": 0}
    full_detail = 0
    families = {fid: {"label": label, "channels": 0, "full_24h": 0} for fid, label, _ in CHANNEL_FAMILIES}
    for channel_id in sorted(set(channels) | set(grouped)):
        name = str(channels.get(channel_id) or channel_id)
        ranges = grouped.get(channel_id, [])
        coverage = {}
        for hours in (24, 72, 168):
            horizon_end = now + timedelta(hours=hours)
            value = _union_hours(ranges, now, horizon_end)
            coverage[f"{hours}h"] = value
            if value >= hours - 0.1:
                counts[f"{hours}h"] += 1
        detail_hours = _union_hours(detailed.get(channel_id, ()), now, now + timedelta(hours=24))
        full_detail += detail_hours >= 23.9
        found = channel_families(name)
        for fid in found:
            families[fid]["channels"] += 1
            families[fid]["full_24h"] += coverage["24h"] >= 23.9
        breakdown.append({
            "channel_id": channel_id[:180], "name": name[:180],
            "canonical_id": canonical_channel(source_id, channel_id, name),
            "families": found, "programmes": len(ranges), "coverage_hours": coverage,
            "specific_title_hours_24h": detail_hours,
        })
    # Worst 24h gaps first, then stable name order; this is an actionable
    # diagnostic, not a blanket overwrite/guessed B1 stream identity.
    breakdown.sort(key=lambda row: (row["coverage_hours"]["24h"], row["name"].casefold()))
    detail_gaps = sorted((row for row in breakdown if row["coverage_hours"]["24h"] >= 23.9
                          and row["specific_title_hours_24h"] < 23.9),
                         key=lambda row: (row["specific_title_hours_24h"], row["name"].casefold()))
    return {
        "source_id": source_id, "country": COUNTRY_BY_SOURCE.get(source_id, "unknown"),
        "channels": len(breakdown), "valid_programmes": sum(map(len, grouped.values())),
        "invalid_programmes": bad + int(guide.get("invalid_programmes", 0)),
        "generic_programmes": generic, "full_coverage_channels": counts,
        "channels_with_full_specific_titles_24h": full_detail,
        "generic_title_gaps": detail_gaps[:detail_limit],
        "channels_needing_attention": breakdown[:detail_limit],
        "unmatched_canonical_channels": sum(not x["canonical_id"] for x in breakdown),
        # How far ahead the guide really reaches; thin files (e.g. ~3 days) show up here.
        "horizon_hours": round(max(((b - now).total_seconds() / 3600 for spans in grouped.values() for _, b in spans), default=0), 1),
        "matched_canonical_channels": sorted({x["canonical_id"] for x in breakdown if x["canonical_id"]}),
        "families": {fid: row for fid, row in families.items() if row["channels"]},
        "analysed_at": now.isoformat(timespec="seconds"),
        "note": "Private source diagnostics only; matches are identity hints, not IPTV stream mappings",
    }
