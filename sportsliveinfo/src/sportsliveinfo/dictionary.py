"""Channel identity dictionary for UK and Europe from the iptv-org database.

The iptv-org database (https://github.com/iptv-org/database) is released into
the public domain under the Unlicense. It describes about 32,000 channels with
alternative names, owners, categories, closures and rebrands, plus 45,000
"feeds": regional, HD and timeshift variants, each with a broadcast area.

Why it matters: many guides (e.g. iptv-epg.org) and many provider tvg-ids use
these channel ids. Resolving a provider channel name to an id, restricted to the
channel's market, is the strongest name-based route to the right guide. It also
says *what* a channel is when no guide carries it at all (network, genre,
website, rebrand or closure).

Measured on a real 7,701-channel UK/Europe lineup (private, not committed):
37.9 % of channels resolved by name before this work, 54.3 % with the market
prefix rules plus broadcast-area feeds, with every one of 70 manually checked
matches correct.

Opt-in: the source is disabled by default (an upgrade never starts outbound
calls the owner has not chosen). It is fetched at most once a day with
conditional requests.
"""
import csv
import io
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from . import providers
from .guide import BARE_MARKET_CODES, market_key, normalized_name
from .identity import name_signature

SOURCE = {
    "name": "iptv-org/database",
    "licence": "Unlicense (public domain)",
    "url": "https://github.com/iptv-org/database",
}
CHANNELS_URL = "https://raw.githubusercontent.com/iptv-org/database/master/data/channels.csv"
FEEDS_URL = "https://raw.githubusercontent.com/iptv-org/database/master/data/feeds.csv"
REGIONS_URL = "https://raw.githubusercontent.com/iptv-org/database/master/data/regions.csv"
MAX_CSV_BYTES = 10_000_000
REFRESH_EVERY = timedelta(hours=24)

# UK and Europe (iptv-org uses "UK" for the United Kingdom).
EUROPE = frozenset("""UK IE FR BE CH LU MC DE AT LI ES AD IT SM VA MT PT NL PL SE NO DK FI IS TR CY GR RO MD BG HU CZ SK
    SI HR BA RS ME MK AL XK RU UA BY LT LV EE GG JE IM GI""".split())
# Feed market (as used by B1G and the published guide catalogue) -> iptv-org countries to search.
MARKET_COUNTRIES = {
    "GB": ["UK", "GG", "JE", "IM", "IE"], "IE": ["IE", "UK"], "FR": ["FR", "BE", "CH", "LU", "MC"], "DE": ["DE", "AT", "CH", "LI"],
    "AT": ["AT", "DE"], "CH": ["CH", "DE", "FR", "IT"], "BE": ["BE", "FR", "NL"], "ES": ["ES", "AD"],
    "IT": ["IT", "SM", "VA", "CH"], "PT": ["PT"], "NL": ["NL", "BE"], "PL": ["PL"], "SE": ["SE", "NO", "DK", "FI"], "NO": ["NO", "SE", "DK", "FI"],
    "DK": ["DK", "SE", "NO", "FI"], "FI": ["FI", "SE", "NO", "DK"], "IS": ["IS"], "TR": ["TR", "CY"], "GR": ["GR", "CY"], "CY": ["CY", "GR"],
    "RO": ["RO", "MD"], "BG": ["BG"], "HU": ["HU"], "CZ": ["CZ", "SK"], "SK": ["SK", "CZ"], "SI": ["SI"],
    "HR": ["HR"], "RS": ["RS"], "BA": ["BA"], "ME": ["ME"], "MK": ["MK"], "AL": ["AL", "XK", "MK"], "RU": ["RU", "BY"],
    "UA": ["UA"], "LT": ["LT"], "LV": ["LV"], "EE": ["EE"], "MT": ["MT"],
    # Optional world regions (owner opt-in, see REGIONS); multi-country provider sections use a group market.
    "US": ["US"], "CA": ["CA", "US"], "AU": ["AU"], "NZ": ["NZ"], "IN": ["IN"], "PK": ["PK"], "BD": ["BD"],
    "NP": ["NP"], "IR": ["IR"], "KU": ["IQ", "TR", "IR", "SY"], "VN": ["VN"], "PH": ["PH"],
    "MENA": "QA SA AE EG KW BH OM LB JO IQ SY MA DZ TN LY PS YE SD MR".split(),
    "AFRICA": "NG ZA KE GH ET TZ UG CM CI SN CD AO MZ ZM ZW RW SO ML BF GA CG BJ TG MG GN NE".split(),
    "CARIB": "JM TT BB DO PR HT BS GY SR LC GD VC AG DM KN CW AW".split(),
    "LATAM": "MX AR CO CL PE VE BR EC UY PY BO CR GT HN SV NI PA US".split(),
}
# Multi-country provider sections ("AR | Food Music & West Asia", "AFRICA") tag each channel with its
# country or platform: "|NIGERIA| AIT", "IRQ: Al Iraqia", "DSTV | M-Net". In those markets the tag
# narrows the lookup to that country only, so "AIT" is Nigeria's AIT, never Ghana's AIT TV.
GROUP_MARKETS = {"MENA", "AFRICA", "CARIB", "LATAM", "KU"}
COUNTRY_TAGS = {
    "IRQ": "IQ", "ALG": "DZ", "MOR": "MA", "SAU": "SA", "KSA": "SA", "SUD": "SD", "PAL": "PS", "YEMEN": "YE",
    "LIBYA": "LY", "EM": "AE", "UAE": "AE", "DSTV": "ZA", "JAWWY": "SA", "SHAHID": "SA", "NIGERIA": "NG",
    "GHANA": "GH", "SENEGAL": "SN", "SOMALIA": "SO", "CAMAROON": "CM", "CAMEROON": "CM", "GUINEE": "GN",
    "GUINEA": "GN", "BENIN": "BJ", "MALI": "ML", "BURKINAFASO": "BF", "KENYA": "KE", "UGANDA": "UG",
    "TANZANIA": "TZ", "ETHIOPIA": "ET", "ZAMBIA": "ZM", "ZIMBABWE": "ZW", "RWANDA": "RW", "CONGO": "CD",
    "ANGOLA": "AO", "GABON": "GA", "TOGO": "TG", "NIGER": "NE", "JAMAICA": "JM", "TRINIDAD": "TT",
}
_COUNTRY_TAG = re.compile(r"^\s*(?:\|\s*([A-Za-z ]{2,20}?)\s*\||([A-Za-z]{2,6})\s*[|:])")


def country_tag(name, market):
    """ISO country named by a group-market section tag ("|NIGERIA| ...", "IQ: ...", "DSTV | ..."), else None."""
    if str(market or "").upper() not in GROUP_MARKETS:
        return None
    match = _COUNTRY_TAG.match(str(name))
    if not match:
        return None
    token = (match.group(1) or match.group(2)).replace(" ", "").upper()
    if token in COUNTRY_TAGS:
        return COUNTRY_TAGS[token]
    return token if len(token) == 2 and token in MARKET_COUNTRIES.get(str(market).upper(), ()) else None


# Owner opt-in regions beyond UK/Europe (all off by default: each adds megabytes to the
# published dictionary that every TV downloads). Keys are config switches under "dictionary".
REGIONS = {
    "north_america": ("North America", "US CA MX PR"),
    "latin_america_caribbean": ("Latin America and the Caribbean",
                                "AR CO CL PE VE BR EC UY PY BO CR GT HN SV NI PA DO HT JM TT BB BS GY SR LC GD VC AG DM KN CW AW"),
    "middle_east_north_africa": ("Middle East and North Africa", "QA SA AE EG KW BH OM LB JO IQ SY MA DZ TN LY PS YE SD IR IL"),
    "south_asia": ("South Asia", "IN PK BD LK NP AF MV BT"),
    "africa": ("Sub-Saharan Africa", "NG ZA KE GH ET TZ UG CM CI SN CD AO MZ ZM ZW RW SO ML BF GA CG BJ TG MG NA BW MW"),
    "asia_pacific": ("Asia-Pacific", "AU NZ SG MY HK PH VN ID TH JP KR CN TW FJ PG"),
}


# Fallback spellings, tried only when a name does not resolve as written. Each rule is a
# regex on the market key and its replacement; "*" applies in every market. Exact and
# conservative: a rule names one brand's own alternative spelling, never a different service.
ALIASES = {
    "*": [
        (r"^nat geo\b", "national geographic"), (r"^national geo channel$", "national geographic"),
        (r"^nick (?:jr|junior)$", "nickelodeon junior"), (r"^rmc sports\b", "rmc sport"),
        (r"^discovery inves$", "discovery investigation"), (r"^euro sport\b", "eurosport"),
    ],
    "FR": [
        (r"^hd1$", "tf1 series films"), (r"^automoto(?: tv)?$", "automoto la chaine"),
        (r"^tv8 mont[ +-]blanc$", "tv8 mont blanc"), (r"^djazz tv$", "stingray djazz"),
        (r"^lci - la chaine info$", "lci"), (r"^lcp public senat$", "lcp"),
        (r"^planete\+ aventure experience$", "planete+ aventure"), (r"^discovery$", "discovery channel"),
        (r"^canal\+ cinema$", "canal+ cinemas"),
    ],
    "DE": [(r"^pro ?7\b", "prosieben"), (r"^kabel ?1\b", "kabel eins")],
    # Rebrands the database lists only under the new name (viju: 1 Mar 2023).
    "RU": [(r"^viasat (explore|history|nature)$", r"viju \1"), (r"^viasat sport$", "viju+ sport")],
}
_ALIASES = {market: [(re.compile(pattern), target) for pattern, target in rules] for market, rules in ALIASES.items()}
# Language/territory variants: "i24NEWS" in a French list is the database's "i24NEWS French".
LANGUAGE_VARIANTS = {
    "FR": ["french", "francais", "france"], "DE": ["deutsch", "german", "germany", "deutschland"],
    "ES": ["espanol", "spanish", "espana"], "IT": ["italia", "italiano", "italian"],
    "PT": ["portugal", "portugues", "portuguese"], "NL": ["nederland", "dutch"], "PL": ["polska", "polish"],
    "TR": ["turkiye", "turk", "turkish"], "GR": ["greece", "hellas", "greek"], "RU": ["russia", "russian"],
}


def _split(value):
    return [part.strip() for part in str(value or "").split(";") if part.strip()]


def _areas(value, regions):
    """Countries covered by a broadcast_area: c/XX, r/REGION (expanded), s/XX-YY and ct/XX... (their country)."""
    out = set()
    for area in _split(value):
        kind, _, code = area.partition("/")
        if kind == "c":
            out.add(code)
        elif kind == "r" and code != "WW":            # worldwide would match every market; never used
            out.update(regions.get(code, ()))
        elif kind in ("s", "ct") and len(code) >= 2:
            out.add(code[:2])
    return out


def scope_countries(regions=()):
    """UK/Europe plus the owner's opted-in REGIONS."""
    countries = set(EUROPE)
    for key in regions or ():
        countries.update(REGIONS[key][1].split())
    return frozenset(countries)


def build_document(channels_csv, feeds_csv, regions_csv="", extra_regions=()):
    """Filter the database to UK/Europe (plus opted-in REGIONS) and to feeds broadcasting there."""
    scope = scope_countries(extra_regions)
    csv.field_size_limit(10_000_000)
    regions = {row["code"]: _split(row.get("countries")) for row in csv.DictReader(io.StringIO(regions_csv or ""))
               if row.get("code")}
    feeds_by_channel = defaultdict(list)
    for row in csv.DictReader(io.StringIO(feeds_csv)):
        areas = sorted(_areas(row.get("broadcast_area"), regions))
        feed = {"id": row.get("id", ""), "name": row.get("name", "")}
        if _split(row.get("alt_names")):
            feed["alt_names"] = _split(row.get("alt_names"))
        if areas:
            feed["areas"] = areas
        if _split(row.get("languages")):
            feed["languages"] = _split(row.get("languages"))
        if row.get("format"):
            feed["format"] = row["format"]
        if row.get("is_main") == "TRUE":
            feed["main"] = True
        feeds_by_channel[row.get("channel", "")].append(feed)
    channels = []
    for row in csv.DictReader(io.StringIO(channels_csv)):
        if row.get("is_nsfw") == "TRUE" or not row.get("id"):
            continue
        feeds = feeds_by_channel.get(row["id"], [])
        home = row.get("country", "")
        if home not in scope:
            # Pan-regional channel (e.g. beIN, DAZN): keep only feeds broadcasting into the scope.
            feeds = [f for f in feeds if scope.intersection(f.get("areas", ()))]
            if not feeds:
                continue
        entry = {"id": row["id"], "name": row.get("name", ""), "country": home}
        for field, value in (("alt_names", _split(row.get("alt_names"))), ("network", row.get("network")),
                             ("owners", _split(row.get("owners"))), ("categories", _split(row.get("categories"))),
                             ("website", row.get("website")), ("launched", row.get("launched")),
                             ("closed", row.get("closed")), ("replaced_by", row.get("replaced_by"))):
            if value:
                entry[field] = value
        if feeds:
            entry["feeds"] = feeds
        channels.append(entry)
    channels.sort(key=lambda c: c["id"])
    return {
        "schema": "sli.dictionary/1",
        "source": SOURCE,
        "scope": ("UK and Europe" + "".join(" + " + REGIONS[k][0] for k in sorted(extra_regions or ()))
                  + " channels, plus feeds of other channels that broadcast there"),
        "regions": sorted(extra_regions or ()),
        "market_countries": MARKET_COUNTRIES,
        "bare_market_codes": {k: sorted(v) for k, v in BARE_MARKET_CODES.items()},
        "group_markets": sorted(GROUP_MARKETS),
        "country_tags": COUNTRY_TAGS,
        "aliases": {market: [{"pattern": pattern, "replacement": target} for pattern, target in rules]
                    for market, rules in ALIASES.items()},
        "language_variants": LANGUAGE_VARIANTS,
        "rules": {
            "lookup": "market_key(name, market) == normalised name, alt name, or base name + feed name of a channel "
                      "in one of market_countries[market] (exact or ignoring spaces/punctuation); then decoration-only "
                      "equality; then channels whose feed broadcasts into those countries",
            "fallbacks": "only when the lookup finds nothing, in order: (1) aliases[market] then aliases['*']: "
                         "replace the first matching pattern and repeat the lookup; (2) singular/plural of the last "
                         "word (>= 4 letters); (3) language_variants[market]: '<name> <variant>' in any country, only when "
                         "the name ends in a market code (dropped first, e.g. 'CGTN FR'), or the plain name has at least 6 "
                         "letters/digits and is not itself a channel; a result counts only when it is one channel; "
                         "(4) a trailing code of the channel's own market (bare_market_codes[market]) is dropped, with a "
                         "quality word before it ('ZDF HD DE' -> 'zdf'), and the lookup repeated",
            "country_tag": "group_markets only: a leading section tag naming a country ('|NIGERIA| ', 'IQ: ', "
                           "'DSTV | ') replaces market_countries[market] with that one country for every step; the tag "
                           "is country_tags[TAG] or a two-letter code listed in market_countries[market]. Without a tag, "
                           "each lookup method pools all market_countries (not first country wins), so a name found in "
                           "two countries is ambiguous",
            "callsign": "US/CA/Caribbean only, when the lookup finds nothing: a station callsign in brackets "
                        "('NBC 5 (KFYR) Minot') matches feeds named after that callsign ('KFYR', 'KFYR-TV'); when "
                        "several channels share it, the one whose name or network appears in the provider name wins",
            "transliteration": "Cyrillic and Greek names and alternative names are also indexed in Latin script "
                               "(transliterate()), so 'Rossiya 1' and 'EPT 1' match",
            "explain_closed": "a name matching only a closed channel is reported as closed (with replaced_by), "
                              "never as a guide match",
            "confidence": "one channel id = high; several ids = ambiguous (owner review, never applied automatically)",
            "closed": "a closed channel never supplies its own guide. Fallback (5): when every closed channel a name "
                      "matches names a live successor (replaced_by, followed up to 3 times) and that is one channel, "
                      "the name resolves to the successor with method 'replaced_by' (the stream now carries it: "
                      "'FOX' in a Turkish list -> NOW). Otherwise explain_closed only explains the name",
            "precedence": "below user manual mappings, provider tvg-id exact and published crosswalks",
        },
        "channels": channels,
    }


class Resolver:
    """Reference lookup that B1G must reproduce (same normalisation and order)."""

    def __init__(self, document):
        self.exact = defaultdict(set)
        self.compact = defaultdict(set)
        self.signature = defaultdict(set)
        self.area = defaultdict(set)
        self.anywhere = defaultdict(set)      # compact key -> ids in any country (language variants)
        self.closed = defaultdict(set)        # (country, compact key) -> closed channel ids
        self.callsign = defaultdict(set)      # US/CA station callsign -> (channel id, feed id)
        self.channels = {c["id"]: c for c in document.get("channels", [])}
        self.main_feed = {c["id"]: next((f.get("id") for f in c.get("feeds", []) if f.get("main")), None)
                          for c in self.channels.values()}
        for channel in self.channels.values():
            bases = [channel.get("name", "")] + list(channel.get("alt_names", []))
            home = channel.get("country", "")
            if channel.get("closed"):
                for base in bases:
                    self.closed[(home, _compact(normalized_name(base)))].add(channel["id"])
                continue
            bases = bases + [t for base in bases for t in transliterate(base)]
            for base in bases:
                self.anywhere[_compact(normalized_name(base))].add((channel["id"], None))
            for base in bases:
                self._add(home, normalized_name(base), (channel["id"], None))
            for feed in channel.get("feeds", []):
                names = [feed.get("name", "")] + list(feed.get("alt_names", []))
                for name in names:
                    call = _CALLSIGN_FEED.match(name.strip())
                    if call:
                        self.callsign[call.group(1)].add((channel["id"], feed.get("id")))
                for base in bases:
                    for name in names:
                        if feed.get("main") and name in ("SD", "HD"):
                            continue
                        self._add(home, normalized_name(base + " " + name), (channel["id"], feed.get("id")))
                    for country in set(feed.get("areas", [])) - {home}:
                        self.area[(country, normalized_name(base))].add((channel["id"], feed.get("id")))
                        self.area[(country, _compact(normalized_name(base)))].add((channel["id"], feed.get("id")))

    def _add(self, country, key, value):
        if not key:
            return
        self.exact[(country, key)].add(value)
        self.compact[(country, _compact(key))].add(value)
        self.signature[(country,) + _sig(key)].add(value)

    def resolve(self, name, market):
        """Returns {"ids": [(channel_id, feed_id), ...], "method": ..., "confidence": "high"|"ambiguous"} or None."""
        market = str(market or "").upper()
        countries = MARKET_COUNTRIES.get(market, [])
        key = market_key(name, market)
        if not key or not countries:
            return None
        tagged = country_tag(name, market)
        if tagged:
            countries = [tagged]
        pooled = market in GROUP_MARKETS and not tagged      # untagged in a multi-country section
        found = self._lookup(key, countries, pooled)
        if found:
            return found
        if market in _CALLSIGN_MARKETS:
            found = self._callsign(name, key)
            if found:
                return found
        for rule_market in (market, "*"):                     # (1) known alternative spellings
            for pattern, target in _ALIASES.get(rule_market, []):
                if pattern.search(key):
                    found = self._lookup(pattern.sub(target, key, count=1), countries)
                    if found:
                        return dict(found, method="alias:" + found["method"])
        words = key.split()                                   # (2) singular/plural of the last word
        if words and len(words[-1]) >= 4 and words[-1].isalpha():
            last = words[-1][:-1] if words[-1].endswith("s") else words[-1] + "s"
            found = self._lookup(" ".join(words[:-1] + [last]), countries)
            if found:
                return dict(found, method="plural:" + found["method"])
        # (3) language/territory variant in any country. Only when the name says so ("CGTN FR") or the
        # plain name is distinctive and not itself a channel ("i24NEWS"): "CNN" stays unmatched, never
        # CNN Portugal, because a short global brand in a local list is often the international feed.
        coded = re.match(r"^(.+?)\s+(%s)$" % "|".join(code.lower() for code in MARKET_COUNTRIES), key)
        base = coded.group(1) if coded else key
        if coded or (len(_compact(base)) >= 6 and not self.anywhere.get(_compact(base))):
            for variant in LANGUAGE_VARIANTS.get(market, []):
                ids = self.anywhere.get(_compact(base + " " + variant))
                if ids and len({i[0] for i in ids}) == 1:
                    return {"ids": sorted(ids), "method": "language_variant", "confidence": "high"}
        found = self._successor(key, countries)                # (5) rebrand: closed name -> its successor
        if found:
            return found
        if coded and coded.group(2).upper() in BARE_MARKET_CODES.get(market, ()):
            # (4) a trailing code of the channel's own market ("ZDF HD DE" in a German list): drop it.
            stripped = re.sub(r"\s+(?:hd|fhd|uhd|4k)$", "", base)
            found = self._lookup(stripped, countries)
            if found:
                return dict(found, method="market_suffix:" + found["method"])
        return None

    def _lookup(self, key, countries, pooled=False):
        """First method that finds anything; within it the first country in order, or (pooled: an untagged
        name in a multi-country section) every country together, so a name found in two countries is ambiguous."""
        for method, lookup in (("exact", lambda c: self.exact.get((c, key)) or self.compact.get((c, _compact(key)))),
                               ("decoration", lambda c: self.signature.get((c,) + _sig(key))),
                               ("broadcast_area", lambda c: self.area.get((c, key)) or self.area.get((c, _compact(key))))):
            hits = [lookup(country) or set() for country in countries]
            if pooled:
                hits = [set().union(*hits)]
            for hit in hits:
                if hit:
                    ids = sorted(hit, key=lambda x: (x[0], x[1] not in (None, self.main_feed.get(x[0])), x[1] or ""))
                    return {"ids": ids, "method": method,
                            "confidence": "high" if len({i[0] for i in ids}) == 1 else "ambiguous"}
        return None

    def _successor(self, key, countries):
        """A closed channel that names its replacement ("FOX" -> NOW, "C More Hits" -> TV4 Hits): the provider
        stream now carries the successor, so its guide is the successor's. Closures without a successor never
        resolve (explain_closed says why)."""
        closed = {cid for country in countries for cid in self.closed.get((country, _compact(key)), ())}
        targets = set()
        def live(cid):
            return cid in self.channels and not self.channels[cid].get("closed")
        for cid in closed:
            target, hops = self.channels[cid].get("replaced_by"), 0
            while target and target in self.channels and not live(target) and hops < 3:   # rebranded again later
                target, hops = self.channels[target].get("replaced_by"), hops + 1
            if not target or not live(target):
                return None                       # one of the matches has no live successor: do not guess
            targets.add(target)
        if len(targets) != 1:
            return None
        return {"ids": [(next(iter(targets)), None)], "method": "replaced_by", "confidence": "high"}

    def _callsign(self, name, key):
        call = _CALLSIGN_NAME.search(str(name))
        ids = self.callsign.get(call.group(1)) if call else None
        if not ids:
            return None
        channels = {i[0] for i in ids}
        if len(channels) > 1:                 # PBS and PBS Kids on WNIT: the provider name decides
            named = {cid for cid in channels if any(
                _compact(normalized_name(n)) and _compact(normalized_name(n)) in _compact(key)
                for n in [self.channels[cid].get("name", ""), self.channels[cid].get("network", "")]
                + list(self.channels[cid].get("alt_names", [])))}
            channels = named or channels
        hits = sorted(i for i in ids if i[0] in channels)
        return {"ids": hits, "method": "callsign", "confidence": "high" if len(channels) == 1 else "ambiguous"}

    def explain_closed(self, name, market):
        """Closed channels a name matches (e.g. "C8", closed 2025): why no guide carries it. None otherwise."""
        market = str(market or "").upper()
        key = _compact(market_key(name, market))
        ids = sorted({cid for country in MARKET_COUNTRIES.get(market, []) for cid in self.closed.get((country, key), ())})
        if not ids:
            return None
        return [{k: self.channels[cid][k] for k in ("id", "name", "closed", "replaced_by") if self.channels[cid].get(k)}
                for cid in ids]

    def describe(self, channel_id):
        """What a channel is, for channels without guide data."""
        channel = self.channels.get(channel_id)
        if not channel:
            return None
        return {k: channel[k] for k in ("id", "name", "country", "network", "categories", "website", "launched",
                                         "closed", "replaced_by") if channel.get(k)}


_CALLSIGN_MARKETS = {"US", "CA", "CARIB"}
_CALLSIGN_FEED = re.compile(r"^([KWC][A-Z]{2,3})(?:-?(?:TV|DT|CD|LD|CA|HD))?$")
_CALLSIGN_NAME = re.compile(r"\(([KWC][A-Z]{2,3})(?:[- ]?(?:TV|DT|CD|LD|CA))?\)")
_CYRILLIC = dict(zip("абвгдезийклмнопрстуфцъыьэ", ["a", "b", "v", "g", "d", "e", "z", "i", "y", "k", "l", "m", "n",
                                                   "o", "p", "r", "s", "t", "u", "f", "ts", "", "y", "", "e"]))
_CYRILLIC.update({"ё": "e", "ж": "zh", "х": "kh", "ч": "ch", "ш": "sh", "щ": "shch", "ю": "yu", "я": "ya",
                  "і": "i", "ї": "yi", "є": "ye", "ґ": "g"})
# Greek: providers either spell the letters that look Latin ("EPT" for ΕΡΤ) or transliterate ("ERT").
_GREEK_LOOK = dict(zip("ΑΒΕΖΗΙΚΜΝΟΡΤΥΧ", "ABEZHIKMNOPTYX"))
_GREEK_SOUND = dict(zip("ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ", ["A", "V", "G", "D", "E", "Z", "I", "TH", "I", "K", "L", "M", "N",
                                                    "X", "O", "P", "R", "S", "T", "Y", "F", "CH", "PS", "O"]))


def transliterate(name):
    """Latin spellings of a Cyrillic or Greek name (empty for Latin names)."""
    text = str(name)
    out = set()
    if re.search("[\u0400-\u04ff]", text):
        latin = "".join(_CYRILLIC.get(ch, ch) for ch in text.lower())
        out |= {latin, latin.replace("kh", "h").replace("ya", "ia").replace("yu", "iu")}
    if re.search("[\u0370-\u03ff]", text):
        upper = text.upper()
        for table in (_GREEK_LOOK, _GREEK_SOUND):
            out.add("".join(table.get(ch, ch) for ch in upper))
    return sorted(out)


def _compact(key):
    return re.sub(r"[^a-z0-9+]", "", key)


def _sig(key):
    identity, tokens, _ = name_signature(key)
    return identity, tokens


def refresh(store, *, now=None, fetch=None, regions=()):
    """Fetch (conditionally, at most daily) and rebuild the dictionary snapshot. Returns a status string."""
    regions = sorted(regions or ())
    fetch = fetch or providers.fetch
    now = now or datetime.now(timezone.utc)
    previous = store.snapshot("channel-dictionary")
    meta = (previous or {}).get("data", {}).get("meta", {}) if previous else {}
    kept = previous                           # last good document, kept whenever a rebuild fails
    if previous and meta.get("regions", []) != regions:
        previous, meta = None, {}             # scope changed: rebuild from full downloads now
    if previous and meta.get("checked_at"):
        try:
            if now - datetime.fromisoformat(meta["checked_at"]) < REFRESH_EVERY:
                return "fresh"
        except ValueError:
            pass
    validators = meta.get("validators", {})
    bodies, new_validators, unchanged = {}, {}, True
    for name, url in (("channels", CHANNELS_URL), ("feeds", FEEDS_URL), ("regions", REGIONS_URL)):
        headers = {"If-None-Match": validators[name]} if previous and validators.get(name) else {}
        response_headers = {}
        raw = fetch(url, headers, max_bytes=MAX_CSV_BYTES, response_headers=response_headers)
        new_validators[name] = response_headers.get("ETag", "")
        if raw is None:
            new_validators[name] = validators.get(name, "")
            continue
        unchanged = False
        bodies[name] = raw.decode("utf-8")
    stamp = now.isoformat(timespec="seconds")
    if unchanged and previous:
        store.save_snapshot("channel-dictionary", dict(previous["data"], meta=dict(meta, checked_at=stamp)))
        return "unchanged"
    if len(bodies) < 3:
        # Some files changed and others were 304: fetch all unconditionally next time.
        store.save_snapshot("channel-dictionary", dict((kept or {}).get("data", {}),
                                                       meta=dict(meta, checked_at=stamp, validators={},
                                                                 regions=((kept or {}).get("data", {}).get("meta", {})
                                                                          .get("regions", [])))))
        return "partial"
    document = build_document(bodies["channels"], bodies["feeds"], bodies["regions"], regions)
    if len(document["channels"]) < 1000:
        raise ValueError("Channel dictionary unexpectedly small; previous version kept")
    store.save_snapshot("channel-dictionary", {
        "document": document,
        "meta": {"checked_at": stamp, "updated_at": stamp, "validators": new_validators, "regions": regions,
                 "channels": len(document["channels"]),
                 "feeds": sum(len(c.get("feeds", [])) for c in document["channels"])},
    })
    return "updated"
