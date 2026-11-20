"""Versioned, data-driven public feed (format sli/1) for read-only B1G clients.

Design rules that let SportsLiveInfo improvements reach the TVs without a B1G
release:
* Everything a reader needs to classify, order, label and match is DATA
  (taxonomy, channel registry, families, guide catalogue, display policy).
* Assets are content-addressed (path contains the SHA-256 prefix); unchanged
  assets keep their path so readers download only what changed.
* Minor versions only ADD optional fields/assets/enum values. Readers ignore
  unknown fields and map unknown enum values to documented fallbacks.
* Time-relative state (live now) is never baked in; readers compute it from
  start/expected end and the time each status was observed (live_state_rule),
  so an old feed never shows a stale "LIVE".
* Events use a field WHITELIST; EPG programme text and EPG-derived candidates
  are never published.
"""
import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import __version__, linking, providers, taxonomy
from .guide import CHANNEL_FAMILIES, COUNTRY_BY_SOURCE, REGIONAL_PARENTS, REGIONAL_RULES, SERVICES, SOURCE_ID_CROSSWALK

FORMAT_MAJOR, FORMAT_MINOR = 1, 6  # 1.1: optional `identity` asset; 1.2: optional `dictionary` asset;
# 1.3: optional event `broadcast_links` (owner decision D8); 1.4: dictionary `regions`, `group_markets`,
# `country_tags` and the 0.3.18 lookup rules (country tag, callsign, transliteration, successor, own-market suffix);
# 1.5: optional `guide_map` asset (what each guide channel is);
# 1.6: event `status_observed_at`, `expected_end_utc` and `tier`; optional `live` and `events_extra:<date>` assets;
# broadcast link status `guide_corroborated` (contract agreed 15 Nov 2026)
ROOT = "v1"
# B1G refuses any asset above this size (SliFeedContract.MAX_ASSET_BYTES, sized for 32-bit Fire TV sticks).
# An optional asset over it is not published; a required one fails the build loudly.
MAX_READER_ASSET_BYTES = 8 * 1024 * 1024
LONDON = ZoneInfo("Europe/London")

EVENT_FIELDS = (
    "id", "sport", "sport_label", "category_id", "category_label", "category_priority", "competition", "competition_id",
    "competition_country", "event_type", "session", "match_type", "day_number", "weight_class", "title", "participants",
    "participants_short", "start_utc", "end_utc", "start_precision", "status_normalized", "round", "stage", "venue",
    "country", "tags", "sources", "fixture_confidence", "corroboration", "start_conflict", "broadcast_verified",
    "status_observed_at", "expected_end_utc", "tier",
)
LIVE_STATE_RULE = ("status_normalized == 'live' is trusted only when status_observed_at is at most 45 minutes old AND "
                   "start_utc <= now <= expected_end_utc + 30 minutes. Otherwise treat it as unknown and fall back to the "
                   "clock (start..expected_end) shown as 'should be on now', never 'LIVE'.")
FEATURED_TAGS = sorted(linking.FEATURED_TAGS)

# Tiered public "today" (contract sli/1.6 §3). Core: named competitions, internationals, featured nations, PPV, the
# main non-football sports, and football leagues and cups of the UK, Ireland and France. Everything else (mostly
# low-tier football elsewhere) is "extra" and published in the optional events_extra:<date> assets.
CORE_SPORTS = frozenset({"motorsport", "rugby_union", "rugby_league", "rugby", "cricket", "tennis", "golf", "darts",
                         "snooker", "boxing", "mma", "horse_racing"})
CORE_FOOTBALL_COUNTRIES = frozenset({"england", "scotland", "wales", "northern ireland", "ireland", "republic of ireland",
                                     "united kingdom", "great britain", "uk", "france"})
_YOUTH = re.compile(r"\b(?:u ?1[5-9]|u ?2[0-3]|under ?(?:1[5-9]|2[0-3])|youth|reserves?|academy|development|"
                    r"premier league 2|professional development)\b")


def event_tier(event):
    """'core' or 'extra' (contract sli/1.6 §3)."""
    if event.get("origin") == "guide_listing":
        return "core"              # private feed: live sport the owner's guides list on a recognised channel
    category = event.get("category_id") or ""
    # A named taxonomy category (anything but "<sport>.other") covers named competitions, including the NFL, NBA, NHL
    # and MLB top leagues, the national-team categories and boxing PPV.
    if (event.get("competition_id") or (category and not category.endswith(".other"))
            or set(event.get("tags") or ()) & linking.FEATURED_TAGS or event.get("sport") in CORE_SPORTS):
        return "core"
    if (event.get("sport") == "football" and taxonomy.norm(event.get("competition_country")) in CORE_FOOTBALL_COUNTRIES
            and not _YOUTH.search(taxonomy.norm(event.get("competition")))):
        return "core"              # UK, Irish and French leagues and cups not named in the taxonomy (youth excepted)
    return "extra"


LIVE_MAX_AGE = timedelta(minutes=45)
LIVE_END_GRACE = timedelta(minutes=30)


def live_until(status, observed_at, start_utc, expected_end_utc):
    """``live_until_utc`` (contract sli/1.6, 0.3.24): the moment after which a reader stops showing this event as LIVE,
    computed here so readers compare one clock time instead of applying the rule themselves. None unless the status
    is live and was observed: min(observed + 45 min, expected end + 30 min), never before the start."""
    if status != "live":
        return None
    observed, start, end = _z(observed_at), _z(start_utc), _z(expected_end_utc)
    if not observed or not start or not end:
        return None
    parse = lambda value: datetime.fromisoformat(value.replace("Z", "+00:00"))
    until = min(parse(observed) + LIVE_MAX_AGE, parse(end) + LIVE_END_GRACE)
    if until <= parse(start):
        return None
    return until.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _z(value):
    """ISO-8601 UTC with a trailing Z, or None."""
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        return None
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# B1G SportsPriorityStore groups. New taxonomy sports map to a group here; a
# group B1G has never seen is appended to the user's order by the reader.
B1G_PRIORITY_GROUP = {
    "football": "Football", "tennis": "Tennis", "rugby": "Rugby", "rugby_union": "Rugby", "rugby_league": "Rugby",
    "cricket": "Cricket", "golf": "Golf", "boxing": "Boxing", "basketball": "Basketball", "mma": "MMA",
    "snooker": "Snooker", "darts": "Darts", "american_football": "American football", "ice_hockey": "Ice hockey",
    "baseball": "Baseball", "cycling": "Cycling", "athletics": "Athletics", "motorsport": "Other motorsport",
    "bowling": "Bowling", "esports": "Esports",
    "horse_racing": "Horse racing", "handball": "Handball", "volleyball": "Volleyball",
    "aussie_rules": "Australian rules football", "netball": "Netball", "other": "Other sport",
}
COMPETITION_PRIORITY_GROUP = {"motorsport.f1": "Formula 1", "motorsport.motogp": "Motorbike racing",
                              "motorsport.moto2_moto3": "Motorbike racing", "motorsport.superbikes": "Motorbike racing"}

ATTRIBUTION = {
    "jolpica": ("Formula 1 data from the Jolpica (Ergast-compatible) API", "CC BY-NC-SA 4.0"),
    "openf1": ("Formula 1 session data from OpenF1", "OpenF1 terms"),
    "openligadb": ("Football data © OpenLigaDB contributors", "ODbL 1.0"),
    "football_data": ("Football data provided by the Football-Data.org API", "football-data.org terms"),
    "api_sports": ("Sports data from API-Sports", "API-Sports terms"),
    "thesportsdb": ("Sports data from TheSportsDB", "TheSportsDB terms"),
    "cricketdata": ("Cricket data from CricketData.org", "CricketData.org terms"),
}

LIVE_STATES = [("live", "Live", True), ("live_probable", "Probably live", True), ("upcoming", "Upcoming", False),
               ("probably_finished", "Probably finished", False), ("finished", "Finished", False),
               ("postponed", "Postponed", False), ("cancelled", "Cancelled", False), ("time_tbc", "Time TBC", False),
               ("unknown", "Unknown", False)]
PRECISIONS = [("scheduled", "Confirmed time"), ("provisional", "Provisional time"), ("not_before", "Not before"),
              ("estimated", "Estimated"), ("time_tbc", "Time to be confirmed"), ("date_only", "Date only")]
FALLBACKS = {"sport": "other", "category_id": "<sport>.other", "status_normalized": "unknown",
             "start_precision": "time_tbc", "live_state": "unknown", "family": "ignore"}


def _json(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _priority_group(sport, competition_id=None):
    return COMPETITION_PRIORITY_GROUP.get(competition_id or "") or B1G_PRIORITY_GROUP.get(sport, "Other sport")


def taxonomy_document():
    sports = [{"id": sid, "label": label, "order": order, "typical_minutes": minutes,
               "b1g_priority_group": _priority_group(sid)} for sid, (label, minutes, order) in taxonomy.SPORTS.items()]
    competitions = []
    for sport, table in taxonomy.COMPETITIONS.items():
        for entry in table:
            competitions.append({"id": entry["id"], "sport": sport, "label": entry["label"], "priority": entry["priority"],
                                 "countries": [c for c in (entry["countries"] or ()) if c] or None,
                                 "b1g_priority_group": _priority_group(sport, entry["id"])})
    national = []
    for sport, table in taxonomy.NATIONAL_CATEGORIES.items():
        seen = set()
        for nation, (cid, label, priority) in table.items():
            if cid not in seen:
                seen.add(cid)
                national.append({"id": cid, "sport": sport, "label": label, "priority": priority,
                                 "b1g_priority_group": _priority_group(sport)})
            next(n for n in national if n["id"] == cid).setdefault("nations", []).append(nation)
    nations = sorted({(slug, label) for slug, label in taxonomy.NATIONS.values()})
    return {
        "schema": "sli.taxonomy/1",
        "sports": sorted(sports, key=lambda s: s["order"]),
        "competitions": competitions,
        "national_categories": national,
        "other_category": {"id_pattern": "<sport>.other", "priority": 90, "label_from": "competition"},
        "tags": {**{"team:" + slug: label for slug, label in nations}, "ppv": "Pay-per-view"},
        "live_states": [{"id": i, "label": l, "is_live": live} for i, l, live in LIVE_STATES],
        "start_precisions": [{"id": i, "label": l} for i, l in PRECISIONS],
        "live_state_rule": LIVE_STATE_RULE + " finished/postponed/cancelled win; otherwise live_probable when "
                           "start_utc <= now < expected_end_utc (older feeds: end_utc or start_utc + "
                           "sport.typical_minutes); date_only -> time_tbc",
    }


def channels_document():
    services = {}
    for market, table in SERVICES.items():
        for name, cid in table.items():
            row = services.setdefault(cid, {"id": cid, "market": market, "names": []})
            row["names"].append(name)
    crosswalk = []
    for source_id, ids in SOURCE_ID_CROSSWALK.items():
        for channel_id, service_id in ids.items():
            services.setdefault(service_id, {"id": service_id, "market": COUNTRY_BY_SOURCE[source_id],
                                             "names": [channel_id]})
        crosswalk.append({"source_id": source_id, "source_url": providers.EPG[source_id][1], "ids": ids})
    for service_id, (parent, region) in REGIONAL_PARENTS.items():
        row = services.setdefault(service_id, {"id": service_id, "market": "GB", "names": []})
        row.update(parent=parent, region=region)
    guides = []
    for gid, (label, url) in providers.EPG.items():
        guides.append({"id": gid, "label": label, "url": url, "market": COUNTRY_BY_SOURCE.get(gid),
                       "upstream_family": providers.EPG_FAMILY.get(gid, gid),
                       "url_verified": "verify" not in label.lower(), "automatic_fallback": False,
                       "programme_rights": "not_cleared"})
    return {
        "schema": "sli.channels/1",
        "normalisation": {
            "steps": ["NFKD; drop combining marks; casefold", "replace '&' with ' and '",
                      "strip one leading country/category prefix followed by | : or -", "collapse whitespace",
                      "repeatedly strip trailing quality tokens", "apply synonyms"],
            "country_prefixes": ["uk", "gb", "fr", "france", "ie", "irl", "us", "usa", "ca", "can", "au", "aus", "nz", "hk",
                                 "hkg", "my", "mys", "sg", "ge", "geo", "pt", "pl", "gr", "in", "pk", "ar", "ara", "arabic",
                                 "mena", "int", "sports"],
            "quality_suffixes": ["hd", "fhd", "sd", "uhd", "4k", "hevc", "h265", "h264", "2160p", "1080p", "720p"],
            "synonyms": [["\\bbbc\\s*1\\b", "bbc one"], ["\\bbbc\\s*2\\b", "bbc two"], ["\\bitv\\s*one\\b", "itv 1"],
                         ["\\bitv\\s*([1-4])\\b", "itv $1"], ["\\brte\\s*2\\b", "rte 2"], ["be in sports", "bein sports"]],
            "identity_bearing_never_stripped": ["+1", "+", "sports+", "region names", "numbers", "plus",
                                                "(ie)/(roi) kept as 'roi'", "bracketed markets and cities, e.g. (XX), (CITY)",
                                                "beIN feed letters (G)/(N)/(F)"],
            "provider_annotations_ignored_for_matching": ["trailing *", "(UK)", "(GB)", "(From hh:mm UK)", "(Live Event Only)",
                                                         "(Events Only)", "(X)", "(D)", "(M)", "' - HEVC' / ' - 4K'",
                                                         "50fps/60fps/HDR/VIP/RAW/backup in the trailing run"],
        },
        "display_variants": {
            "rule": "never merge or hide a provider channel for display; show base name plus variant tags in this order; "
                    "identical labels within one category are numbered in provider order (' · 2')",
            "tag_order": ["4K", "FHD", "HD", "SD", "HDR", "50fps/60fps", "HEVC", "Ireland", "from hh:mm", "Events only",
                          "VIP", "RAW", "Backup", "Alt", "Alt feed (*)", "Source X/D/M"],
            "separator": " · ",
            "matching_vs_display": "normalised names decide which guide a channel uses (quality copies share one guide); "
                                   "display labels keep every copy distinct",
        },
        "services": sorted(services.values(), key=lambda s: s["id"]),
        "regional_services": {
            "rules": [{"pattern": pattern, "service": target} for pattern, target in REGIONAL_RULES],
            "rule_syntax": "java/ecmascript regex, full match on the normalised name; {0} is capture group 1; "
                           "applies to UK-market names only, after the services name table",
            "irish_names_in_uk_guides": ["rte one", "rte 2", "tg4", "virgin media one"],
            "english_regions": "carry network sport and resolve to the network id",
            "nations": "Scotland, Wales and Northern Ireland versions are separate services with parent and region; "
                       "a provider channel is never merged with another region",
            "event_allocation": "a broadcast candidate names the parent (coverage 'network') only when the guides show "
                                "every observed nation carrying the event, or a same-slot shortened title (simulcast); "
                                "nations that showed something else are listed in not_on. Otherwise each carrying "
                                "nation is its own candidate (coverage 'regional', parent_channel_id)",
        },
        "source_crosswalk": crosswalk,
        "families": [{"id": fid, "label": label, "pattern": pattern, "pattern_syntax": "java/ecmascript regex, find() on normalised name"}
                     for fid, label, pattern in CHANNEL_FAMILIES],
        "matching_rules": {
            "precedence": ["user manual mapping (always wins)", "provider tvg-id exact", "source_crosswalk exact id",
                           "service name in the guide's own market", "generic name index"],
            "market_gate": "a service name match requires the guide market to equal the service market and any explicit country prefix to agree",
            "never_auto_match": ["regional variants", "+1 timeshift", "Sky Sports+", "numbered channels with a different number"],
            "families_are_diagnostic_only": True,
        },
        "guide_catalogue": guides,
    }


def identity_document(store):
    """Published channel identity graph: ids, names and timeshift relations only (never programme data)."""
    snapshot = store.snapshot("channel-identity")
    document = (snapshot or {}).get("data", {}).get("document") if snapshot else None
    if not isinstance(document, dict) or not document.get("channels"):
        return None
    used = sorted({m["source_id"] for c in document["channels"] for m in c["members"]}
                  | {t["source_id"] for t in document.get("timeshifts", [])})
    return dict(document, sources=[{"source_id": s, "source_url": providers.EPG[s][1]}
                                   for s in used if s in providers.EPG])


def guide_map_document(store):
    """Published guide channel map: for every enabled guide, each channel's id, name, the service it is
    (SLI service id or dictionary id, with the method) and its programme count for the next 7 days.
    Ids, names and counts only: never programme text."""
    snapshot = store.snapshot("guide-map")
    data = (snapshot or {}).get("data") or {}
    guides = data.get("guides") or {}
    if not guides:
        return None
    return {"schema": "sli.guide-map/1", "generated_at": data.get("generated_at"),
            "guides": [{"source_id": source_id, "source_url": providers.EPG[source_id][1],
                        "market": COUNTRY_BY_SOURCE.get(source_id), "channels": channels}
                       for source_id, channels in sorted(guides.items()) if source_id in providers.EPG],
            "service_aliases": {str(k): str(v) for k, v in sorted((data.get("service_aliases") or {}).items())},
            "rules": {"service": "SLI service id (registry/identity methods) or iptv-org dictionary id "
                                 "(dictionary methods); absent when the guide channel is not identified",
                      "use": "after B1G identifies a provider channel (user mapping > provider tvg-id > service id > "
                             "dictionary id), take the guide channel with that id or service, preferring the one with "
                             "the most programmes_7d; never a guide channel of another service, region or +1",
                      "service_aliases": "dictionary id -> SLI service id where SportsLiveInfo reports that "
                                         "dictionary channel under a curated service; look up both"}}


def dictionary_document(store, conf):
    """Published UK/Europe channel dictionary (public-domain iptv-org database), when the owner enabled it."""
    if not conf.get("dictionary", {}).get("iptvorg"):
        return None
    snapshot = store.snapshot("channel-dictionary")
    document = (snapshot or {}).get("data", {}).get("document") if snapshot else None
    return document if isinstance(document, dict) and document.get("channels") else None


def _event_public(event, private=False, observed_fallback=None):
    row = {k: event[k] for k in EVENT_FIELDS if k in event and event[k] not in (None, "", [])}
    row.setdefault("status_normalized", "scheduled")
    # Contract sli/1.6 §1: when the status was last observed (always present) and the typical end.
    row["status_observed_at"] = _z(event.get("status_observed_at")) or _z(observed_fallback) or "1970-01-01T00:00:00Z"
    row.pop("expected_end_utc", None)
    if event.get("start_utc") and event.get("start_precision") != "date_only":
        try:
            row["expected_end_utc"] = linking.expected_end(event).isoformat(timespec="seconds")
        except (TypeError, ValueError):
            pass
    until = live_until(row.get("status_normalized"), row["status_observed_at"], row.get("start_utc"),
                       row.get("expected_end_utc"))
    if until:
        row["live_until_utc"] = until
    row["tier"] = event_tier(event)
    # A cached event must not become a "verified broadcaster" merely
    # because an untrusted source sets a boolean. A reviewed, versioned
    # evidence rule must be attached before publishing clickable TV claims.
    row["broadcast_verified"] = (
        bool(event.get("broadcast_verified"))
        and event.get("broadcast_verification_rule") == "approved_v1"
        and bool(event.get("broadcast_evidence"))
    )
    if row["broadcast_verified"]:
        row["broadcasts"] = [{k: b[k] for k in ("canonical_channel_id", "name", "coverage_start_utc", "transmission") if k in b}
                             for b in event.get("broadcasts", []) if isinstance(b, dict)]
    links = _broadcast_links(event, private)
    if links:
        row["broadcast_links"] = links
    if private and event.get("origin") == "guide_listing":
        row["origin"] = "guide_listing"     # live sport listed in the guides, no event-source fixture
    row["b1g_priority_group"] = _priority_group(event.get("sport"), event.get("competition_id"))
    return row


def _broadcast_links(event, private=False):
    """Owner decision D8: publish guide-listed event->channel links as canonical ids and confidence only.

    No guide channel names, programme titles or programme times are published,
    and a link never makes an event "verified": the guide shows a channel
    listing the event, not that a provider stream carries it.
    """
    # Audit 15 Nov (P1): links found only by the looser guide-listing matcher (team words stripped, ±3 h) can name the
    # wrong match ("Man City v Liverpool" 14:30 → "Manchester United v Liverpool" 17:30). Until that matcher is as
    # strict as the main one they stay in the owner's private feed and are never published publicly.
    if not private and event.get("broadcast_status") == "guide_listing_match":
        return []
    links = []
    # Published best first (linking.candidate_rank); readers keep this order and use `binds`, so ranking and binding
    # are decided here and improve without a reader update.
    for candidate in linking.rank_candidates(event.get("broadcast_candidates") or [], event):
        if not candidate.get("canonical_channel_id"):
            continue
        link = {"canonical_channel_id": str(candidate["canonical_channel_id"]),
                "status": "guide_listed_unverified",
                "coverage": candidate.get("coverage") or "network",
                "confidence": "high" if candidate.get("match_confidence") == "high" else "medium",
                "guides": len(candidate.get("epg_sources") or [])}
        if linking.guide_corroborated(event, candidate):
            # Contract sli/1.6 §4: strict match, same slot, curated channel, two independent guide families.
            # Still not "verified": broadcast_verified is reserved for provider or official evidence.
            link["status"] = "guide_corroborated"
            link["verification"] = linking.CORROBORATION_RULE
        if candidate.get("parent_channel_id"):
            link["parent_channel_id"] = str(candidate["parent_channel_id"])
        if candidate.get("not_on"):
            link["not_on"] = [str(x) for x in candidate["not_on"]]
        if private:   # the owner's private feed may carry the guide's channel name and programme times
            for field in ("channel_name", "programme_start_utc", "programme_end_utc"):
                if candidate.get(field):
                    link[field] = str(candidate[field])[:120]
        # May this link name the channel that shows the event ("on now", Sports Today)? Weaker links are "may be on".
        link["binds"] = link["status"] == "guide_corroborated" or link["confidence"] == "high"
        link["rank"] = len(links) + 1
        links.append(link)
    return links


def live_document(store, events):
    """The optional ``live`` asset (contract sli/1.6 §2), or None.

    Built from the live-status lane's observations (``live_observations``, keyed by source event id). An event is
    listed when an observation newer than its published status either changes the status or confirms play in
    progress (so a reader keeps trusting "live" for 45 minutes). Ids, statuses and times only: no scores."""
    observations = ((store._get("live_observations") or {}).get("events") or {})
    if not observations:
        return None
    rows = []
    for event in events:
        seen = [observations[sid] for sid in event.get("source_events") or [event.get("id")]
                if isinstance(observations.get(sid), dict)]
        if not seen:
            continue
        latest = max(seen, key=lambda o: str(o.get("status_observed_at") or ""))
        observed, published = _z(latest.get("status_observed_at")), _z(event.get("status_observed_at"))
        status = latest.get("status_normalized")
        if not observed or status not in linking.STATUS_PROGRESS or (published and observed <= published):
            continue
        if status != event.get("status_normalized") or status == "live":
            row = {"id": event["id"], "status_normalized": status, "status_observed_at": observed}
            try:
                end = linking.expected_end(event).isoformat(timespec="seconds") \
                    if event.get("start_utc") and event.get("start_precision") != "date_only" else None
            except (TypeError, ValueError):
                end = None
            until = live_until(status, observed, event.get("start_utc"), end)
            if until:
                row["live_until_utc"] = until
            rows.append(row)
    if not rows:
        return None
    rows.sort(key=lambda r: r["id"])
    # generated_at is the newest observation, not the build time, so an unchanged lane keeps the same bytes.
    return {"schema": "sli.live/1", "generated_at": max(r["status_observed_at"] for r in rows), "events": rows}


def build_feed(store, now=None, previous_revision=None, private=False):
    """Return (manifest_dict, {path: bytes}) without any network IO.

    ``private=True`` builds the owner's personal-use feed for a private repository:
    every collected event (no publication approval needed) and guide-listed live sport.
    """
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    conf = store.config()
    approved = set(conf.get("publication_approvals", []))
    enabled_sports = [name for name in providers.SPORTS if conf["sports"].get(name)]
    enabled_guides = [name for name in providers.EPG if conf["epg"].get(name)]
    snapshots = store.read_snapshots(
        products=("sports", *(() if private else ("sports-public",)), *("epg-quality:" + name for name in enabled_guides)),
        timestamps_only=(*("sports:" + name for name in enabled_sports),
                         *("epg:" + name for name in enabled_guides)),
    )
    snap = snapshots.get("sports")
    all_events = snap["data"]["events"] if snap else []
    observed_fallback = ((snap or {}).get("data") or {}).get("generated_at") or (snap or {}).get("updated_at")

    # Audit 15 Nov (C1): the public feed is built from a merge of approved-source events only (engine
    # materialisation, snapshot "sports-public"), so an unapproved source corroborating an approved fixture can no
    # longer remove it. Every published record must still come from approved sources only: a fused fixture whose
    # contributors are not all approved is never published (field-level lineage is not tracked).
    def licensed(event):
        if private:
            return True                   # personal use in the owner's private repository
        if event.get("origin") == "guide_listing":
            return False                  # derived from guide programme text: never published
        origin = event.get("source_id")
        contributors = event.get("sources") or [origin]
        return (isinstance(origin, str) and origin in approved
                and isinstance(contributors, list) and bool(contributors)
                and all(isinstance(src, str) and src in approved for src in contributors))
    public = snapshots.get("sports-public")
    public_data = (public or {}).get("data") or {}
    if not private and public and sorted(public_data.get("approved") or []) == sorted(approved):
        selected = public_data.get("events") or []
    else:
        # Private feed, or approvals changed since the last collection: the full merge, fail-closed.
        selected = all_events
    selected = [e if "category_id" in e else taxonomy.classify(e) for e in selected if licensed(e)]
    # Legacy/unclassified snapshot rows still need category fields the schema requires.
    events = [_event_public(e, private, observed_fallback) for e in selected]
    if private:
        approved = {src for e in all_events for src in (e.get("sources") or [e.get("source_id")])
                    if isinstance(src, str) and src != "guide_listing"}
    omitted = sorted({src for e in all_events if e.get("origin") != "guide_listing"
                      for src in (e.get("sources") or [e.get("source_id")])
                      if isinstance(src, str) and src not in approved})
    by_day, extra_by_day = {}, {}
    for event in events:
        day = datetime.fromisoformat(event["start_utc"]).astimezone(LONDON).date().isoformat()
        (by_day if event["tier"] == "core" else extra_by_day).setdefault(day, []).append(event)
    today = now.astimezone(LONDON).date()
    window = [(today + timedelta(days=i)).isoformat() for i in range(8)]

    assets, files, skipped = [], {}, []

    def add(kind, obj, schema, required, **extra):
        data = _json(obj)
        if len(data) > MAX_READER_ASSET_BYTES:
            if required:
                raise ValueError("required feed asset %s exceeds the reader limit" % kind.split(":")[0])
            skipped.append(kind)
            return                     # e.g. a dictionary with every world region switched on
        digest = hashlib.sha256(data).hexdigest()
        path = "%s/assets/%s/%s.json" % (ROOT, kind.split(":")[0], digest[:24])
        files[path] = data
        assets.append(dict({"kind": kind, "path": path, "sha256": digest, "bytes": len(data), "schema": schema,
                            "content_type": "application/json", "required": required}, **extra))

    add("taxonomy", taxonomy_document(), "sli.taxonomy/1", True)
    add("channels", channels_document(), "sli.channels/1", True)
    identity_doc = identity_document(store)
    if identity_doc:
        add("identity", identity_doc, "sli.identity/1", False)
    dictionary_doc = dictionary_document(store, conf)
    if dictionary_doc:
        add("dictionary", dictionary_doc, "sli.dictionary/1", False)
    guide_map_doc = guide_map_document(store)
    if guide_map_doc:
        add("guide_map", guide_map_doc, "sli.guide-map/1", False)
    for day in window:
        rows = sorted(by_day.get(day, []), key=lambda e: (e["start_utc"], e["id"]))
        add("events:" + day, {"schema": "sli.events-day/1", "date": day, "timezone": "Europe/London", "events": rows},
            "sli.events-day/1", day == window[0], date=day, records=len(rows))
    for day in window:
        rows = sorted(extra_by_day.get(day, []), key=lambda e: (e["start_utc"], e["id"]))
        if rows:      # contract sli/1.6 §3: the long tail, same schema as events:<date>
            add("events_extra:" + day, {"schema": "sli.events-day/1", "date": day, "timezone": "Europe/London",
                                        "events": rows}, "sli.events-day/1", False, date=day, records=len(rows))
    todays = by_day.get(window[0], [])
    groups = {}
    for event in todays:
        groups.setdefault(event["sport"], {}).setdefault(event["category_id"], []).append(event)
    featured_tags = FEATURED_TAGS
    today_doc = {
        "schema": "sli.today/1", "date": window[0],
        "featured_event_ids": [e["id"] for e in sorted(todays, key=lambda e: e["start_utc"]) if set(e.get("tags", [])) & set(featured_tags)],
        "groups": [{"sport": sport, "categories": [
            {"id": cid, "event_ids": [e["id"] for e in sorted(rows, key=lambda e: e["start_utc"])]}
            for cid, rows in sorted(cats.items(), key=lambda kv: (kv[1][0].get("category_priority", 90), kv[0]))]}
            for sport, cats in sorted(groups.items(), key=lambda kv: taxonomy.sport_order(kv[0]))],
    }
    add("today", today_doc, "sli.today/1", True, date=window[0], records=len(todays))
    published_ids = {e["id"] for e in events}
    live_doc = live_document(store, [dict(e, status_observed_at=e.get("status_observed_at") or observed_fallback)
                                     for e in selected if e.get("id") in published_ids])
    if live_doc:
        add("live", live_doc, "sli.live/1", False, records=len(live_doc["events"]))
    add("health", health_document(store, conf, snapshots), "sli.health/1", False)

    schedule = sorted(conf.get("schedule", []))
    # Revision = data assets + meaningful manifest settings. The health asset is
    # excluded because its timestamps change on every collection and would force
    # a new GitHub commit each refresh with no data change.
    stable = {"assets": [a["sha256"] for a in assets if a["kind"] != "health"], "approved": sorted(approved),
              "schedule": schedule, "version": __version__, "format": [FORMAT_MAJOR, FORMAT_MINOR]}
    revision = hashlib.sha256(_json(stable)).hexdigest()[:20]
    interval = _interval_minutes(schedule)
    by_sport = {}
    for event in events:
        by_sport[event["sport"]] = by_sport.get(event["sport"], 0) + 1
    corroborated_links = sum(link.get("status") == "guide_corroborated"
                             for e in events for link in e.get("broadcast_links") or [])
    core = sum(e["tier"] == "core" for e in events)
    notices = [] if events else ["No rights-approved sporting events in this revision; registry assets remain valid."]
    notices += ["Optional asset %s exceeded the %d MiB reader limit and was not published." % (kind, MAX_READER_ASSET_BYTES >> 20)
                for kind in skipped]
    manifest = {
        "feed": "sportsliveinfo", "format": "sli/%d.%d" % (FORMAT_MAJOR, FORMAT_MINOR),
        "format_major": FORMAT_MAJOR, "format_minor": FORMAT_MINOR,
        "compatibility": {"reader_major": FORMAT_MAJOR, "min_reader_minor": 0, "unknown_fields": "ignore",
                          "unknown_assets": "ignore", "unknown_enum_fallback": FALLBACKS,
                          "on_major_mismatch": "keep last good feed; show 'update B1G to read the newer SportsLiveInfo feed'",
                          "live_state_rule": LIVE_STATE_RULE,
                          "live_overlay_rule": "overlay the optional 'live' asset on the day assets by event id when its "
                                               "status_observed_at is newer; a feed older than 45 minutes never makes "
                                               "anything 'LIVE'",
                          "tier_rule": "events:<date> and today carry tier 'core'; the optional events_extra:<date> "
                                       "assets (same schema) carry tier 'extra'",
                          # 0.3.24: decisions made here, so readers follow them without an update.
                          "link_order": "best_first",
                          "link_rule": "broadcast_links are published best first (rank 1 = best); keep that order. A "
                                       "link with binds=true may name the channel showing the event; binds=false is "
                                       "'may be on' only",
                          "live_until_rule": "when an event (or its live-asset row) has live_until_utc, show LIVE only "
                                             "while start_utc <= now < live_until_utc; without it apply live_state_rule",
                          "live_max_age_minutes": int(LIVE_MAX_AGE.total_seconds() // 60),
                          "live_end_grace_minutes": int(LIVE_END_GRACE.total_seconds() // 60)},
        "revision": revision, "previous_revision": previous_revision,
        "generated_at": now.isoformat(timespec="seconds"),
        "publisher": {"app": "SportsLiveInfo", "version": __version__},
        "timezone_reference": "Europe/London", "window": {"from": window[0], "to": window[-1]},
        "refresh": {"schedule_europe_london": schedule, "expected_interval_minutes": interval,
                    "reader_poll_minutes": 30, "stale_after_hours": 30,
                    "expires_at": (now + timedelta(hours=48)).isoformat(timespec="seconds")},
        "capabilities": ["taxonomy", "channel_registry", "channel_families", "guide_catalogue", "events_by_day",
                         "today", "source_health", "fixture_corroboration", "status_observed_at", "event_tiers"]
                        + (["channel_identity"] if identity_doc else [])
                        + (["channel_dictionary"] if dictionary_doc else [])
                        + (["guide_map"] if guide_map_doc else [])
                        + (["live_status"] if live_doc else [])
                        + (["verified_broadcasts"] if any(e["broadcast_verified"] for e in events) else [])
                        + (["broadcast_links"] if any(e.get("broadcast_links") for e in events) else [])
                        + (["guide_corroborated_broadcasts"] if corroborated_links else []),
        "assets": assets,
        "coverage": {"events": len(events), "today": len(todays), "by_sport": dict(sorted(by_sport.items())),
                     "tiers": {"core": core, "extra": len(events) - core},
                     "today_extra": len(extra_by_day.get(window[0], [])),
                     "corroborated": sum(e.get("fixture_confidence") == "corroborated" for e in events),
                     "verified_broadcasts": sum(e["broadcast_verified"] for e in events),
                     "guide_corroborated_broadcasts": corroborated_links,
                     "sports_known": len(taxonomy.SPORTS), "competitions_known": sum(len(t) for t in taxonomy.COMPETITIONS.values()),
                     "services_known": len({cid for t in SERVICES.values() for cid in t.values()}),
                     "families_known": len(CHANNEL_FAMILIES)},
        "rights": {"events": {"approved_sources": sorted(approved), "omitted_unapproved_sources": omitted},
                   "epg_programmes": "not_published",
                   "broadcast_candidates": "channel_links_published_unverified",
                   "attribution": [{"source": s, "text": ATTRIBUTION[s][0], "licence": ATTRIBUTION[s][1]}
                                   for s in sorted({providers.SPORT_FAMILY.get(a, a) for a in approved}) if s in ATTRIBUTION]
                                  + ([{"source": "iptv_org_database", "text": "Channel dictionary from the iptv-org database",
                                       "licence": "Unlicense (public domain)"}] if dictionary_doc else [])},
        "display_policy": {"sports_today_body_cards": 10, "ppv_pinned_extra_card": True, "featured_tags": featured_tags,
                           "user_settings_override": True},
        "notices": notices,
    }
    if private:
        manifest["visibility"] = "private"
        manifest["rights"]["events"]["scope"] = "personal_use_private_repository"
        manifest["rights"]["guide_listed_events"] = "included_private"
        manifest["rights"]["broadcast_candidates"] = "channel_links_with_guide_names_and_times_private"
        if any(e.get("origin") == "guide_listing" for e in events):
            manifest["capabilities"].append("guide_listed_events")
        manifest["notices"] = ["Private personal-use feed: never copy it to a public location."] + manifest["notices"]
    return manifest, files


def _interval_minutes(schedule):
    minutes = sorted(int(t[:2]) * 60 + int(t[3:]) for t in schedule if len(t) == 5)
    if len(minutes) < 2:
        return 1440
    gaps = [b - a for a, b in zip(minutes, minutes[1:])] + [minutes[0] + 1440 - minutes[-1]]
    return max(gaps)


def health_document(store, conf, snapshots):
    jobs = store.recent_jobs(300)
    latest = {}
    for job in jobs:
        if not job["state"].startswith("test_"):
            latest.setdefault(job["provider"], job)
    rows = []
    for kind, registry, enabled in (("sports", providers.SPORTS, conf["sports"]), ("epg", providers.EPG, conf["epg"])):
        for name in registry:
            if not enabled.get(name):
                continue
            snap = snapshots.get(kind + ":" + name)
            job = latest.get(name, {})
            rows.append({"id": name, "kind": kind, "label": registry[name][0], "state": job.get("state", "unknown"),
                         "last_attempt": job.get("time"), "last_success": snap["updated_at"] if snap else None,
                         "upstream_family": providers.SPORT_FAMILY.get(name) if kind == "sports" else providers.EPG_FAMILY.get(name)})
    guides = []
    for name, on in conf["epg"].items():
        quality = snapshots.get("epg-quality:" + name) if on else None
        if quality:
            q = quality["data"]
            guides.append({"id": name, "market": q.get("country"), "channels": q.get("channels", 0),
                           "full_24h": q.get("full_coverage_channels", {}).get("24h", 0),
                           "recognised_services": q.get("matched_canonical_channels", []),
                           "families": {k: {"channels": v["channels"], "full_24h": v["full_24h"]} for k, v in q.get("families", {}).items()},
                           "analysed_at": q.get("analysed_at")})
    return {"schema": "sli.health/1", "sources": rows, "guides": guides,
            "note": "Measured on the SportsLiveInfo host; no programme text, URLs with credentials or error payloads."}
