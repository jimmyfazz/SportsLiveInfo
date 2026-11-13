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
    "GB": ["UK", "GG", "JE", "IM"], "IE": ["IE", "UK"], "FR": ["FR", "BE", "CH", "LU", "MC"], "DE": ["DE", "AT", "CH", "LI"],
    "AT": ["AT", "DE"], "CH": ["CH", "DE", "FR", "IT"], "BE": ["BE", "FR", "NL"], "ES": ["ES", "AD"],
    "IT": ["IT", "SM", "VA", "CH"], "PT": ["PT"], "NL": ["NL", "BE"], "PL": ["PL"], "SE": ["SE", "NO", "DK", "FI"], "NO": ["NO", "SE", "DK", "FI"],
    "DK": ["DK", "SE", "NO", "FI"], "FI": ["FI", "SE", "NO", "DK"], "IS": ["IS"], "TR": ["TR", "CY"], "GR": ["GR", "CY"], "CY": ["CY", "GR"],
    "RO": ["RO", "MD"], "BG": ["BG"], "HU": ["HU"], "CZ": ["CZ", "SK"], "SK": ["SK", "CZ"], "SI": ["SI"],
    "HR": ["HR"], "RS": ["RS"], "BA": ["BA"], "ME": ["ME"], "MK": ["MK"], "AL": ["AL", "XK", "MK"], "RU": ["RU", "BY"],
    "UA": ["UA"], "LT": ["LT"], "LV": ["LV"], "EE": ["EE"], "MT": ["MT"],
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


def build_document(channels_csv, feeds_csv, regions_csv=""):
    """Filter the database to UK/Europe channels and to feeds broadcasting there."""
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
        if home not in EUROPE:
            # Pan-regional channel (e.g. beIN, DAZN): keep only feeds broadcasting into Europe.
            feeds = [f for f in feeds if EUROPE.intersection(f.get("areas", ()))]
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
        "scope": "UK and Europe channels, plus feeds of other channels that broadcast into Europe",
        "market_countries": MARKET_COUNTRIES,
        "bare_market_codes": {k: sorted(v) for k, v in BARE_MARKET_CODES.items()},
        "rules": {
            "lookup": "market_key(name, market) == normalised name, alt name, or base name + feed name of a channel "
                      "in one of market_countries[market]; then decoration-only equality; then channels whose feed "
                      "broadcasts into those countries",
            "confidence": "one channel id = high; several ids = ambiguous (owner review, never applied automatically)",
            "closed": "a closed channel only explains a name (e.g. a rebrand via replaced_by); it never supplies a guide",
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
        self.channels = {c["id"]: c for c in document.get("channels", [])}
        self.main_feed = {c["id"]: next((f.get("id") for f in c.get("feeds", []) if f.get("main")), None)
                          for c in self.channels.values()}
        for channel in self.channels.values():
            if channel.get("closed"):
                continue
            bases = [channel.get("name", "")] + list(channel.get("alt_names", []))
            home = channel.get("country", "")
            for base in bases:
                self._add(home, normalized_name(base), (channel["id"], None))
            for feed in channel.get("feeds", []):
                names = [feed.get("name", "")] + list(feed.get("alt_names", []))
                for base in bases:
                    for name in names:
                        if feed.get("main") and name in ("SD", "HD"):
                            continue
                        self._add(home, normalized_name(base + " " + name), (channel["id"], feed.get("id")))
                    for country in set(feed.get("areas", [])) - {home}:
                        self.area[(country, normalized_name(base))].add((channel["id"], feed.get("id")))

    def _add(self, country, key, value):
        if not key:
            return
        self.exact[(country, key)].add(value)
        self.compact[(country, _compact(key))].add(value)
        self.signature[(country,) + _sig(key)].add(value)

    def resolve(self, name, market):
        """Returns {"ids": [(channel_id, feed_id), ...], "method": ..., "confidence": "high"|"ambiguous"} or None."""
        countries = MARKET_COUNTRIES.get(str(market or "").upper(), [])
        key = market_key(name, market)
        if not key or not countries:
            return None
        for method, lookup in (("exact", lambda c: self.exact.get((c, key)) or self.compact.get((c, _compact(key)))),
                               ("decoration", lambda c: self.signature.get((c,) + _sig(key))),
                               ("broadcast_area", lambda c: self.area.get((c, key)))):
            for country in countries:
                hit = lookup(country)
                if hit:
                    ids = sorted(hit, key=lambda x: (x[0], x[1] not in (None, self.main_feed.get(x[0])), x[1] or ""))
                    return {"ids": ids, "method": method,
                            "confidence": "high" if len({i[0] for i in ids}) == 1 else "ambiguous"}
        return None

    def describe(self, channel_id):
        """What a channel is, for channels without guide data."""
        channel = self.channels.get(channel_id)
        if not channel:
            return None
        return {k: channel[k] for k in ("id", "name", "country", "network", "categories", "website", "launched",
                                         "closed", "replaced_by") if channel.get(k)}


def _compact(key):
    return re.sub(r"[^a-z0-9+]", "", key)


def _sig(key):
    identity, tokens, _ = name_signature(key)
    return identity, tokens


def refresh(store, *, now=None, fetch=None):
    """Fetch (conditionally, at most daily) and rebuild the dictionary snapshot. Returns a status string."""
    fetch = fetch or providers.fetch
    now = now or datetime.now(timezone.utc)
    previous = store.snapshot("channel-dictionary")
    meta = (previous or {}).get("data", {}).get("meta", {}) if previous else {}
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
        store.save_snapshot("channel-dictionary", dict((previous or {}).get("data", {}),
                                                       meta=dict(meta, checked_at=stamp, validators={})))
        return "partial"
    document = build_document(bodies["channels"], bodies["feeds"], bodies["regions"])
    if len(document["channels"]) < 1000:
        raise ValueError("Channel dictionary unexpectedly small; previous version kept")
    store.save_snapshot("channel-dictionary", {
        "document": document,
        "meta": {"checked_at": stamp, "updated_at": stamp, "validators": new_validators,
                 "channels": len(document["channels"]),
                 "feeds": sum(len(c.get("feeds", [])) for c in document["channels"])},
    })
    return "updated"
