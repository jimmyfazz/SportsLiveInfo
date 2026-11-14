"""Owner channel-list coverage: which channels are identified and which guide carries each one.

LOCAL ONLY. The owner imports their provider's channel list (M3U or plain text) on the
Home Assistant Ingress page. It is stored in the App's private SQLite database, never
published, never sent to GitHub and never logged. Stream URLs (which carry provider
credentials) are discarded while reading the file; only the category, the channel
name and the provider's own guide id (tvg-id) are kept.

The report covers every linear channel (entertainment, movies, kids, news, documentaries,
music, sport, regional, religious ...), not only sport. For each channel it records:
  * identity: the provider's tvg-id when a guide uses it, else the channel dictionary;
  * guide: the best guide (enabled, or surveyed but not enabled) that carries it, matched
    by the provider's tvg-id, by the dictionary id (regional feed aware) or by name within
    the channel's market;
  * recommendations: the not-yet-enabled guides that would cover the most channels still
    without a guide (greedy set cover).
"""
import re
from collections import Counter, defaultdict

from . import dictionary as channel_dictionary
from . import event_slots
from .guide import COUNTRY_BY_SOURCE, foreign_guide_channel, local_station_key, market_key, normalized_name

LINEUP_PRODUCT = "coverage:lineup"
REPORT_PRODUCT = "coverage:report"
TV_EXPORT_PRODUCT = "coverage:tv-export"
COMPARISON_PRODUCT = "coverage:comparison"
MAX_DIFFERENCES = 400
SURVEY_PREFIX = "survey:"
MAX_LINEUP_ENTRIES = 60_000

# ---- Reading the owner's list ------------------------------------------------------------------
_EXTINF = re.compile(r"^#EXTINF:[^,]*?,(?P<name>.*)$")
_ATTR = re.compile(r'([a-zA-Z0-9_-]+)="([^"]*)"')
_VOD_URL = re.compile(r"/(?:movie|series|vod)/", re.I)


def parse_lineup(text):
    """[{"category", "name", "tvg_id", "kind"}] from an M3U playlist or plain text.

    Plain text: one channel per line, optionally "category<TAB>name" or "category | name"
    is NOT split (provider names contain "|"), only a tab separates a category.
    URLs are read only to recognise video-on-demand entries and are never stored.
    """
    entries = []
    lines = str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if any(line.startswith("#EXTM3U") or line.startswith("#EXTINF") for line in lines[:50]):
        pending = None
        for line in lines:
            line = line.strip()
            if line.startswith("#EXTINF"):
                match = _EXTINF.match(line)
                attrs = dict(_ATTR.findall(line.split(",", 1)[0] if "," in line else line))
                pending = {"category": attrs.get("group-title", "")[:120],
                           "name": (match.group("name") if match else attrs.get("tvg-name", "")).strip()[:160],
                           "tvg_id": attrs.get("tvg-id", "").strip()[:160]}
            elif pending is not None and line and not line.startswith("#"):
                pending["kind"] = "vod" if _VOD_URL.search(line) else classify_kind(pending["category"], pending["name"])
                if pending["name"]:
                    entries.append(pending)
                pending = None
            if len(entries) >= MAX_LINEUP_ENTRIES:
                break
    else:
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            category, _, name = line.partition("\t") if "\t" in line else ("", "", line)
            entry = {"category": category.strip()[:120], "name": name.strip()[:160], "tvg_id": ""}
            entry["kind"] = classify_kind(entry["category"], entry["name"])
            entries.append(entry)
            if len(entries) >= MAX_LINEUP_ENTRIES:
                break
    return entries


def classify_kind(category, name):
    """linear | event_slot | radio | adult | loop | vod."""
    c, n = str(category or ""), str(name or "")
    if re.search(r"^(?:xxx|\+18|adult)|\bxxx\b", c, re.I) or re.match(r"^\+18", n):
        return "adult"
    if re.search(r"\bradio\b", c, re.I) or re.match(r"^radio\s*:", n, re.I):
        return "radio"
    if re.match(r"^24/7\b", c) or re.match(r"^24/7\b", n):
        return "loop"
    if re.search(r"\b(?:vod|movies? vod|series)\b", c, re.I) and not re.search(r"\b(?:tv|channels?)\b", c, re.I):
        return "vod"
    if re.search(r"\b(?:ppv|events?)\b", c, re.I) or re.search(r"events? only|live event|ppv event|\bevent \d+", n, re.I):
        return "event_slot"
    if _EVENT_SECTION.search(c):
        return "event_slot"
    return "linear"


# Sections that hold per-event feeds of streaming services, not linear channels with a schedule.
_EVENT_SECTION = re.compile(
    r"^(?:live\s*\||ppv\b|fite\b)|\b(?:flosports|espn\+|peacock|paramount\+|tsn\+|dazn (?:ca|gb|events?)|"
    r"tennis channel|beIN max|hub premier|pl\+|ligue 1 pass|monomax|trillertv|dirtvision|vidio|mola|"
    r"coupang|now hk|astro sports|superleague\+|florugby|kayo|stan sport|onefootball)\b", re.I)


# ---- Market and genre ------------------------------------------------------------------------
# Country names and codes as providers write them in categories ("INT | France", "UK |",
# "|FR|", "AR | Gulf") and name prefixes ("DE |", "FR:"). Order matters: first match wins.
_MARKET_WORDS = [
    (r"\bunited kingdom\b|\bengland\b|\bscotland\b|\bwales\b|\bbritish\b", "GB"), (r"\bireland\b|\birish\b", "IE"),
    (r"\bfrance\b|\bfrench\b|\bfrancais\b", "FR"), (r"\bgerman[y]?\b|\bdeutsch", "DE"), (r"\baustria\b", "AT"),
    (r"\bswitzerland\b|\bswiss\b", "CH"), (r"\bspain\b|\bspanish\b|\bespa[nñ]a\b", "ES"), (r"\bital[yi]\b", "IT"),
    (r"\bnetherland|\bdutch\b|\bholland\b", "NL"), (r"\bbelgi", "BE"), (r"\bportug", "PT"), (r"\bpoland\b|\bpolish\b|\bpolska\b", "PL"),
    (r"\bgreece\b|\bgreek\b", "GR"), (r"\bscandinavia|\bnordic\b|\bsweden\b|\bswedish\b", "SE"), (r"\bnorway\b|\bnorsk\b", "NO"),
    (r"\bdenmark\b|\bdanish\b|\bdansk\b", "DK"), (r"\bfinland\b|\bsuomi\b", "FI"), (r"\brussia", "RU"), (r"\bukrain", "UA"),
    (r"\bturkey\b|\bturkish\b|\bt[uü]rk", "TR"), (r"\balbania|\bkosov", "AL"), (r"\bromania", "RO"), (r"\bbulgaria", "BG"),
    (r"\bhungar", "HU"), (r"\bczech|\bslovak|\bslovok", "CZ"), (r"\bcroatia", "HR"), (r"\bserbia", "RS"),
    (r"\bslovenia", "SI"), (r"\bbosnia", "BA"), (r"\bmacedonia", "MK"), (r"\bcanad", "CA"), (r"\bmexic", "LATAM"),
    (r"\blatin|\bargentin|\bbrazil|\bcolombia|\bchile\b|\bperu\b", "LATAM"), (r"\bcaribbean|\bjamaica|\btrinidad", "CARIB"),
    (r"\barab|\bgulf\b|\bmena\b|\bmiddle east|\begypt|\bsaudi|\bemirat|\bqatar|\bmorocc|\balgeri|\btunis|\biraq|\blebanon", "MENA"),
    (r"\bkurd", "KU"), (r"\biran\b|\bpersian\b|\bfarsi\b", "IR"),
    (r"\bindia\b|\bhindi\b|\btamil\b|\btelugu\b|\bpunjabi\b|\bbangla|\bmalayalam\b|\bkannada\b|\bgujr?a?ti\b|"
     r"\bmarathi\b|\bodia\b|\b(?:inr)\b", "IN"),
    (r"\bpakistan", "PK"), (r"\bnepal", "NP"), (r"\bvietnam", "VN"), (r"\bphilippin|\bpinoy\b", "PH"),
    (r"\bafrica|\bnigeria|\bkenya|\bghana|\bdstv\b", "AFRICA"), (r"\baustralia|\bkayo\b|\bfoxtel\b", "AU"),
    (r"\bnew zealand\b|\bnz\b", "NZ"), (r"\busa\b|\bunited states\b|\bamerican?\b", "US"),
]
_MARKET_WORDS = [(re.compile(p, re.I), m) for p, m in _MARKET_WORDS]
_CODES = {"UK": "GB", "GB": "GB", "IE": "IE", "FR": "FR", "DE": "DE", "AT": "AT", "CH": "CH", "ES": "ES", "IT": "IT",
          "NL": "NL", "BE": "BE", "PT": "PT", "PL": "PL", "GR": "GR", "SE": "SE", "SW": "SE", "NO": "NO", "DK": "DK",
          "FI": "FI", "RU": "RU", "UA": "UA", "UKR": "UA", "TR": "TR", "TRK": "TR", "AL": "AL", "RO": "RO", "BG": "BG",
          "HU": "HU", "CZ": "CZ", "SK": "SK", "HR": "HR", "RS": "RS", "SI": "SI", "BA": "BA", "MK": "MK", "US": "US",
          "USA": "US", "CA": "CA", "MX": "LATAM", "AR": "MENA", "IN": "IN", "INR": "IN", "PK": "PK", "NP": "NP", "NPL": "NP",
          "VN": "VN", "PH": "PH", "AU": "AU", "NZ": "NZ", "IR": "IR", "KU": "KU", "AF": "AFRICA", "CARIB": "CARIB"}
_LEADING_CODE = re.compile(r"^\s*(?:\|\s*)?([A-Za-z]{2,5})\s*(?:\||:|-\s|\s\|)")


def market_of(category, name):
    """Market for a lineup channel: a country or language word in the category ("SK: France" -> FR), then
    a leading code in the category ("UK |"), then the same in the name ("DE | ..."); None when unknown."""
    for text in (str(category or ""), str(name or "")):
        for pattern, market in _MARKET_WORDS:
            if pattern.search(text):
                return market
        code = _LEADING_CODE.match(text)
        if code and code.group(1).upper() in _CODES:
            return _CODES[code.group(1).upper()]
    return None


_GENRES = [
    ("sport", r"sport|bein|dazn|eurosport|arena|football|futbol|soccer|tennis|golf|racing|motor|fight|boxing|ufc|"
              r"\bnba\b|\bnfl\b|\bnhl\b|\bmlb\b|cricket|rugby|\bespn|\btsn\b|supersport|setanta|premier league"),
    ("news", r"\bnews\b|haber|nachrichten|\binfo\b|\b24\b|\bcnn\b|bbc world|euronews|al jazeera|bloomberg|cnbc|"
             r"\bbfm|\blci\b|france ?24|\bdw\b|sky ?news|\bnhk\b|\bcgtn\b"),
    ("kids", r"\bkids?\b|junior|\bjr\b|cartoon|\bnick|disney|\bbaby|boomerang|cartoonito|\bduck\b|gulli|\bboing\b|"
             r"minimax|jim ?jam|\bpanda\b|cbeebies|cbbc|\bpbs kids|tiji|\bpogo\b|baraem|\bjeem\b|toon"),
    ("movies", r"\bcine|\bfilm|movie|\bkino\b|\bhbo\b|cinemax|filmbox|\bamc\b|\btcm\b|paramount|sky cinema|"
               r"\bm\+ cine|\bstar movies|\bmgm\b|\bocs\b|\bsony (?:max|pix|movies)|\baflam\b|\bflix\b"),
    ("music", r"music|\bmtv\b|\bvh1\b|stingray|vevo|\btrace\b|mezzo|djazz|\bhits?\b|\bclub\b|dance|\brock\b|\bpop\b|"
              r"muzik|xite|\bkiss\b|\bfm\b"),
    ("documentary", r"discovery|nat ?geo|national geographic|history|animal|viasat (?:explore|nature|history)|"
                    r"planete|travel|science|investigation|crime|\bdocu|\bviju\b|love nature|\bwild\b"),
    ("religious", r"\bgod\b|church|christ|gospel|\bquran\b|\bislam|\bdaystar|\btbn\b|\bewtn\b|\bpeace tv|sikh|sangat|"
                  r"\bfaith\b|catholic|\bbible"),
    ("lifestyle", r"food|cook|kitchen|fashion|\bhome\b|garden|\btlc\b|\bhgtv\b|lifestyle|shop|qvc|travel"),
]
_GENRES = [(g, re.compile(p, re.I)) for g, p in _GENRES]
_DICTIONARY_GENRES = {"sports": "sport", "news": "news", "kids": "kids", "animation": "kids", "family": "kids",
                      "movies": "movies", "music": "music", "documentary": "documentary", "science": "documentary",
                      "outdoor": "documentary", "religious": "religious", "cooking": "lifestyle",
                      "lifestyle": "lifestyle", "shop": "lifestyle", "travel": "lifestyle", "series": "entertainment",
                      "comedy": "entertainment", "entertainment": "entertainment", "general": "general",
                      "culture": "entertainment", "education": "documentary", "business": "news",
                      "weather": "news", "legislative": "news", "relax": "lifestyle", "auto": "sport"}


def genre_of(category, name, dictionary_categories=()):
    """sport | news | kids | movies | music | documentary | religious | lifestyle | entertainment | general."""
    for cat in dictionary_categories or ():
        genre = _DICTIONARY_GENRES.get(str(cat).lower())
        if genre and genre != "general":
            return genre
    text = "%s %s" % (name or "", category or "")
    for genre, pattern in _GENRES:
        if pattern.search(text):
            return genre
    return "general" if dictionary_categories else "entertainment"


# ---- Guide indexes (enabled guides and surveyed guides) -----------------------------------
def guide_index(source_id, guide):
    """Compact, programme-free index of one guide: channel ids, names and programme counts."""
    counts = Counter(str(p.get("channel_id", "")) for p in guide.get("programmes") or [])
    starts = [p.get("start_utc") for p in guide.get("programmes") or [] if p.get("start_utc")]
    return {"source_id": source_id,
            "channels": {str(cid): str(name)[:160] for cid, name in (guide.get("channels") or {}).items()},
            "programmes": {cid: n for cid, n in counts.items() if cid},
            "first": min(starts) if starts else None, "last": max(starts) if starts else None}


_IPTVORG_BASE = re.compile(r"^[A-Za-z0-9+&!'_-]+\.[a-z]{2}$")


def feed_agrees(region, guide_feed):
    """Whether a guide channel's iptv-org feed ("WalesHD", "HD", "Plus1") is the wanted region (None = national).
    Exact region only: "London" never takes "LondonEast", a national channel never takes a region or +1."""
    guide_feed = str(guide_feed or "")
    if channel_dictionary._TIMESHIFT_FEED.search(guide_feed):
        return False
    guide_region = "" if channel_dictionary._MAIN_FEED.fullmatch(guide_feed) else re.sub(r"(?:HD|SD)$", "", guide_feed)
    return guide_region.lower() == str(region or "").lower()


def choose_guide_channels(guide_map, identity=None, *, tvg_id=None, market=None, enabled=None):
    """Reference for B1G: the published guide channels for one provider channel, best first.

    ``guide_map`` is the published ``sli.guide-map/1`` document; ``identity`` the provider channel's service
    (SLI service id, or a dictionary identity from ``dictionary.service_identity``); ``tvg_id`` the provider's
    own guide id; ``market`` the channel's market; ``enabled`` the guide sources switched on (None = all).
    Returns ``(how, [(source_id, guide channel id, programmes_7d)])``; ``how`` is "provider_id", "service",
    "dictionary_id" or None. Guide channels without programmes in the next 7 days are never offered.
    Conformance: ``schemas/fixtures/sli-v1/guide-choice-cases.json``.
    """
    aliases = {str(k): str(v) for k, v in ((guide_map or {}).get("service_aliases") or {}).items()}
    rows = []
    for guide in (guide_map or {}).get("guides") or []:
        source = str(guide.get("source_id") or "")
        if enabled is not None and source not in enabled:
            continue
        for channel in guide.get("channels") or []:
            count = int(channel.get("programmes_7d") or 0)
            if count > 0 and channel.get("id"):
                rows.append((source, str(channel["id"]), count, channel.get("service")))

    def ranked(hits):
        return sorted({(source, cid, count) for source, cid, count, _ in hits}, key=lambda h: (-h[2], h[0], h[1]))

    if tvg_id:
        hits = [row for row in rows if row[1] == tvg_id]
        if hits:
            return "provider_id", ranked(hits)
    if not identity:
        return None, []
    wanted = {identity} | ({aliases[identity]} if identity in aliases else set()) | {
        dictionary_id for dictionary_id, service in aliases.items() if service == identity}
    service_hits = [row for row in rows if row[3] in wanted]
    # Also the same iptv-org channel in guides that did not identify it, for the dictionary id itself and for
    # each dictionary id SLI reports under this service (the region after "@" must agree exactly).
    id_hits = []
    for wanted_id in sorted(wanted):
        base, _, region = wanted_id.partition("@")
        if not _IPTVORG_BASE.match(base):
            continue
        for row in rows:
            guide_base, _, guide_feed = row[1].partition("@")
            if guide_base != base or (row[3] and row[3] not in wanted):
                continue                          # another channel, or the guide itself says another service
            if market and foreign_guide_channel(market, row[1]):
                continue
            if feed_agrees(region, guide_feed):
                id_hits.append(row)
    if service_hits or id_hits:
        return ("service" if service_hits else "dictionary_id"), ranked(service_hits + id_hits)
    return None, []


class _Matcher:
    def __init__(self, indexes):
        self.by_id = defaultdict(list)          # exact guide channel id -> [(source, id, n)]
        self.by_base = defaultdict(list)        # iptv-org base id ("TNTSports1.uk") -> [(source, id, n, feed)]
        self.by_name = defaultdict(list)        # (market, key) -> [(source, id, n)]
        self.local = defaultdict(set)           # (network, city) -> {(source, id, n)}
        for index in indexes:
            source = index["source_id"]
            market = COUNTRY_BY_SOURCE.get(source)
            for cid, name in index["channels"].items():
                n = index["programmes"].get(cid, 0)
                if not n:
                    continue
                entry = (source, cid, n)
                self.by_id[cid].append(entry)
                base, _, feed = cid.partition("@")
                if _IPTVORG_BASE.match(base):
                    self.by_base[base].append(entry + (feed,))
                markets = [market] if market else []
                for m in markets:
                    key = market_key(name, m)
                    if key:
                        self.by_name[(m, key)].append(entry)
                        self.by_name[(m, channel_dictionary._compact(key))].append(entry)
                station = local_station_key(name, guide=True)
                if station:
                    self.local[station].add(entry)

    def match(self, entry, market, identity):
        """(how, [(source, guide channel id, programmes)]) for one lineup channel."""
        tvg = entry.get("tvg_id") or ""
        if tvg and self.by_id.get(tvg):
            return "provider_id", self.by_id[tvg]
        if identity:
            channel_id, feed = identity
            hits = []
            for source, cid, n, guide_feed in self.by_base.get(channel_id, ()):
                if market and foreign_guide_channel(market, cid):
                    continue
                if feed_agrees(feed, guide_feed):
                    hits.append((source, cid, n))
            if hits:
                return "dictionary_id", hits
        if market:
            key = market_key(entry["name"], market)
            hits = self.by_name.get((market, key)) or self.by_name.get((market, channel_dictionary._compact(key)))
            if hits:
                return "name", list(hits)
            if market in ("US", "CA"):
                station = local_station_key(entry["name"])
                if station and len(self.local.get(station, ())) == 1:
                    return "local_station", list(self.local[station])
        return None, []


# ---- The TV's view: one provider channel through the B1G order of work ---------------------------------------
SKIPPED_KINDS = frozenset({"vod", "radio", "adult", "loop"})
TV_FIELDS = ["market", "category", "name", "genre", "kind", "state", "identity", "identity_method", "match",
             "guide_source", "guide_channel", "programmes", "slot", "slot_start_utc", "event_id"]


def identity_from_id(channel_id, resolver):
    """Identity for an iptv-org style id the provider already gives ("BBCOne.uk@WalesHD" -> "BBCOne.uk@Wales",
    "SkySportsMainEvent.uk@HD" -> "SkySportsMainEvent.uk"); None for an unknown channel or a timeshift feed."""
    base, _, feed = str(channel_id or "").partition("@")
    if not resolver or base not in resolver.channels or channel_dictionary._TIMESHIFT_FEED.search(feed):
        return None
    region = "" if channel_dictionary._MAIN_FEED.fullmatch(feed) else re.sub(r"(?:HD|SD)$", "", feed)
    return base + ("@" + region if region else "")


def reconcile_channel(entry, *, resolver=None, guide_map=None, enabled=None, now=None, events=()):
    """Reference for B1G: one provider channel through the reconciliation spec, using only what a TV has
    (the published dictionary, guide_map and events, and its own channel list). Columns: ``TV_FIELDS``.

    Order: skip VOD/radio/adult/24-7 loops; provider ``tvg-id`` (a guide channel id, whose service is the
    identity, else a dictionary id); dictionary name rules in the channel's market (``service_identity``:
    regions kept, +1 and ambiguous refused); event-slot name for event feeds and unidentified channels;
    then ``choose_guide_channels``. A user's manual mapping on the TV is applied before this and wins.
    Conformance: ``schemas/fixtures/sli-v1/reconcile-cases.json``.
    """
    category, name = str(entry.get("category") or ""), str(entry.get("name") or "")
    tvg = str(entry.get("tvg_id") or "").strip()
    kind = entry.get("kind") or classify_kind(category, name)
    market = market_of(category, name)
    row = dict.fromkeys(TV_FIELDS, "")
    row.update(category=category, name=name, market=market or "", kind=kind, programmes=0)
    if kind in SKIPPED_KINDS:
        row.update(genre=genre_of(category, name), state="skipped")
        return row
    identity, method, ambiguous = None, None, False
    if tvg:
        services = sorted({str(channel.get("service")) for guide in (guide_map or {}).get("guides") or []
                           for channel in guide.get("channels") or []
                           if channel.get("id") == tvg and channel.get("service")})
        if len(services) == 1:
            identity, method = services[0], "provider_id"
        elif not services:
            identity = identity_from_id(tvg, resolver)
            method = "provider_id" if identity else None
    if not identity and resolver and market:
        hit = resolver.resolve(name, _dictionary_market(market))
        service = channel_dictionary.service_identity(hit)
        if service:
            identity, method = service, hit["method"]
        elif hit:
            ambiguous = True
    if kind == "event_slot" or not identity:
        slot = event_slots.parse_slot(name, now=now, default_tz="America/New_York" if market in ("US", "CA")
                                      else "Europe/London") if now else None
        if slot:
            found = event_slots.match_slot(slot, list(events or ()), now=now) if events else None
            row.update(slot=slot["slot"], slot_start_utc=slot["start_utc"] or "",
                       event_id=str(found["id"]) if found else "")
    how, hits = choose_guide_channels(guide_map, identity, tvg_id=tvg or None, market=market,
                                      enabled=enabled) if guide_map else (None, [])
    base = (identity or "").partition("@")[0]
    categories = tuple((resolver.channels.get(base) or {}).get("categories", ())) if resolver and base else ()
    if hits:
        state = "guide"
    elif row["slot"]:
        state = "slot_linked" if row["event_id"] else "slot_from_name"
    elif kind == "event_slot":
        state = "event_feed"
    else:
        state = "identified_no_guide" if identity else "ambiguous" if ambiguous else "unknown"
    row.update(genre=genre_of(category, name, categories), state=state, identity=identity or "",
               identity_method=method or ("ambiguous" if ambiguous else ""), match=how or "")
    if hits:
        row.update(guide_source=hits[0][0], guide_channel=hits[0][1], programmes=hits[0][2])
    return row


def parse_tv_export(text):
    """Rows of B1G's local per-channel export (CSV in ``TV_FIELDS`` order). Only the compared columns are kept."""
    import csv
    import io
    reader = csv.DictReader(io.StringIO(str(text or "").lstrip("\ufeff")))
    if not reader.fieldnames or not {"category", "name", "identity"} <= set(reader.fieldnames):
        raise ValueError("That is not a B1G channel export (expected the columns category, name and identity)")
    keep = ("category", "name", "market", "genre", "kind", "identity", "guide_source", "guide_channel")
    rows = []
    for row in reader:
        rows.append({key: str(row.get(key) or "")[:200] for key in keep})
        if len(rows) >= MAX_LINEUP_ENTRIES:
            break
    return rows


def compare_tv_export(lineup, tv_rows, *, resolver=None, guide_map=None, now=None):
    """B1G's per-channel result against SportsLiveInfo's for the same channels and the same published inputs.

    Channels are matched on (category, name) with the imported channel list, whose provider ``tvg-id`` is used.
    Identity agreement is the acceptance figure (target 99 %); a *wrong region* is the same channel with another
    region or a timeshift feed, and must be zero. Guide: B1G's guide channel must be one SportsLiveInfo would
    also choose (from any guide, since the TV's own guide switches are not known here).
    """
    by_key = {}
    for entry in lineup or ():
        by_key.setdefault((entry.get("category", ""), entry.get("name", "")), entry)
    result = Counter()
    differences = []

    def differ(row, field, sli, tv, serious=False):
        result["differences"] += 1
        result["serious"] += serious
        if len(differences) < MAX_DIFFERENCES:
            differences.append({"category": row["category"], "name": row["name"], "field": field,
                                "sli": sli, "tv": tv, "serious": serious})

    for tv in tv_rows:
        entry = by_key.get((tv["category"], tv["name"]))
        if entry is None:
            result["not_in_list"] += 1
            continue
        result["compared"] += 1
        expected = reconcile_channel(entry, resolver=resolver, guide_map=guide_map, now=now)
        for field in ("kind", "market", "genre"):
            if tv.get(field, "") == expected[field]:
                result[field + "_agree"] += 1
            else:
                differ(tv, field, expected[field], tv.get(field, ""))
        sli_id, tv_id = expected["identity"], tv.get("identity", "")
        if sli_id and tv_id:
            result["identity_both"] += 1
            if sli_id == tv_id:
                result["identity_agree"] += 1
            else:
                same_channel = sli_id.partition("@")[0] == tv_id.partition("@")[0]
                result["wrong_region"] += same_channel
                differ(tv, "identity", sli_id, tv_id, serious=same_channel)
        elif sli_id or tv_id:
            result["identity_only_sli" if sli_id else "identity_only_tv"] += 1
            differ(tv, "identity", sli_id, tv_id, serious=bool(tv_id) and channel_dictionary._TIMESHIFT_FEED.search(
                tv_id.partition("@")[2]) is not None)
        if tv.get("guide_channel"):
            result["guide_checked"] += 1
            _how, hits = choose_guide_channels(guide_map, sli_id or None, tvg_id=entry.get("tvg_id") or None,
                                               market=expected["market"] or None) if guide_map else (None, [])
            if any(source == tv.get("guide_source") and cid == tv["guide_channel"] for source, cid, _n in hits):
                result["guide_ok"] += 1
            else:
                differ(tv, "guide_channel", ", ".join(cid for _s, cid, _n in hits[:3]), tv["guide_channel"],
                       serious=True)
    both = result["identity_both"]
    return {"counts": dict(result), "differences": differences,
            "identity_agreement": round(100.0 * result["identity_agree"] / both, 2) if both else None,
            "passes": bool(both) and result["identity_agree"] >= 0.99 * both and not result["serious"]}


def _dictionary_market(market):
    return {"AT": "AT", "SE": "SE", "CZ": "CZ"}.get(market, market)


def build_report(lineup, *, dictionary_document=None, enabled_indexes=(), surveyed_indexes=(), now=None):
    """Per-channel identity and guide coverage, totals by market and genre, and source recommendations."""
    resolver = channel_dictionary.Resolver(dictionary_document) if isinstance(dictionary_document, dict) else None
    enabled = _Matcher(enabled_indexes)
    everything = _Matcher(list(enabled_indexes) + list(surveyed_indexes))
    enabled_ids = {index["source_id"] for index in enabled_indexes}
    rows, totals = [], defaultdict(Counter)
    kinds = Counter(entry.get("kind", "linear") for entry in lineup)
    uncovered_by_source = defaultdict(set)
    for number, entry in enumerate(lineup):
        if entry.get("kind", "linear") not in ("linear", "event_slot"):
            continue
        market = market_of(entry["category"], entry["name"])
        identity, method, categories = None, None, ()
        if resolver and market:
            hit = resolver.resolve(entry["name"], _dictionary_market(market))
            service = channel_dictionary.service_identity(hit)
            if service:                                  # same rule as the guide side and B1G
                base, _, region = service.partition("@")
                identity = (base, region or None)
                method = hit["method"]
                categories = tuple(resolver.channels.get(base, {}).get("categories", ()))
            elif hit:
                method = "ambiguous"
        genre = genre_of(entry["category"], entry["name"], categories)
        slot = None
        if entry.get("kind") == "event_slot" or not identity:
            slot = event_slots.parse_slot(entry["name"], now=now, default_tz="America/New_York"
                                          if market in ("US", "CA") else "Europe/London") if now else None
        how, hits = enabled.match(entry, market, identity)
        state = "guide_enabled" if hits else None
        if not hits:
            how, hits = everything.match(entry, market, identity)
            state = "guide_available" if hits else None
            for source, _cid, _n in hits:
                uncovered_by_source[source].add(number)
        if not state:
            state = "slot_from_name" if slot else "event_feed" if entry.get("kind") == "event_slot" else (
                "identified_no_guide" if identity else "ambiguous" if method == "ambiguous" else "unknown")
        best = max(hits, key=lambda h: (h[0] in enabled_ids, h[2])) if hits else None
        rows.append({"category": entry["category"], "name": entry["name"], "market": market or "",
                     "genre": genre, "kind": entry.get("kind", "linear"),
                     "identity": (identity[0] + ("@" + identity[1] if identity[1] else "")) if identity else "",
                     "identity_method": method or "",
                     "state": state, "match": how or "", "guide_source": best[0] if best else "",
                     "guide_channel": best[1] if best else "", "programmes": best[2] if best else 0})
        for group in ("*all", "market:" + (market or "?"), "genre:" + genre):
            totals[group][state] += 1
            totals[group]["channels"] += 1
            totals[group]["identified"] += bool(identity)
    # Greedy set cover over the channels only surveyed (not enabled) guides carry.
    recommendations, covered = [], set()
    remaining = {source: set(numbers) for source, numbers in uncovered_by_source.items() if source not in enabled_ids}
    while remaining and len(recommendations) < 12:
        source, numbers = max(remaining.items(), key=lambda item: len(item[1] - covered))
        gain = len(numbers - covered)
        if gain < 3:
            break
        recommendations.append({"source_id": source, "adds_channels": gain})
        covered |= numbers
        remaining.pop(source)
    # Dictionary regions the list needs but the owner has not switched on.
    region_needed = Counter()
    switched_on = set((dictionary_document or {}).get("regions") or ()) if isinstance(dictionary_document, dict) else set()
    for row in rows:
        if row["identity"] or not row["market"]:
            continue
        for key, (_label, countries) in channel_dictionary.REGIONS.items():
            wanted = set(channel_dictionary.MARKET_COUNTRIES.get(row["market"], ()))
            if key not in switched_on and wanted & set(countries.split()) and not wanted & channel_dictionary.EUROPE:
                region_needed[key] += 1
    regions = [{"region": key, "label": channel_dictionary.REGIONS[key][0], "channels": n}
               for key, n in region_needed.most_common() if n >= 20]
    return {"rows": rows, "totals": {k: dict(v) for k, v in totals.items()}, "kinds": dict(kinds),
            "recommendations": recommendations, "region_recommendations": regions,
            "enabled_sources": sorted(enabled_ids),
            "surveyed_sources": sorted(index["source_id"] for index in surveyed_indexes)}
