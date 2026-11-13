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
  start/end and taxonomy typical durations, so an old feed stays correct.
* Events use a field WHITELIST; EPG programme text and EPG-derived candidates
  are never published.
"""
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import __version__, providers, taxonomy
from .guide import CHANNEL_FAMILIES, COUNTRY_BY_SOURCE, SERVICES, SOURCE_ID_CROSSWALK

FORMAT_MAJOR, FORMAT_MINOR = 1, 2  # 1.1: optional `identity` asset; 1.2: optional `dictionary` asset
ROOT = "v1"
LONDON = ZoneInfo("Europe/London")

EVENT_FIELDS = (
    "id", "sport", "sport_label", "category_id", "category_label", "category_priority", "competition", "competition_id",
    "competition_country", "event_type", "session", "match_type", "day_number", "weight_class", "title", "participants",
    "participants_short", "start_utc", "end_utc", "start_precision", "status_normalized", "round", "stage", "venue",
    "country", "tags", "sources", "fixture_confidence", "corroboration", "start_conflict", "broadcast_verified",
)

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
        "live_state_rule": "status_normalized wins for live/finished/postponed/cancelled; otherwise live_probable when "
                           "start_utc <= now < (end_utc or start_utc + sport.typical_minutes); date_only -> time_tbc",
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


def dictionary_document(store, conf):
    """Published UK/Europe channel dictionary (public-domain iptv-org database), when the owner enabled it."""
    if not conf.get("dictionary", {}).get("iptvorg"):
        return None
    snapshot = store.snapshot("channel-dictionary")
    document = (snapshot or {}).get("data", {}).get("document") if snapshot else None
    return document if isinstance(document, dict) and document.get("channels") else None


def _event_public(event):
    row = {k: event[k] for k in EVENT_FIELDS if k in event and event[k] not in (None, "", [])}
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
    row["b1g_priority_group"] = _priority_group(event.get("sport"), event.get("competition_id"))
    return row


def build_feed(store, now=None, previous_revision=None):
    """Return (manifest_dict, {path: bytes}) without any network IO."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    conf = store.config()
    approved = set(conf.get("publication_approvals", []))
    enabled_sports = [name for name in providers.SPORTS if conf["sports"].get(name)]
    enabled_guides = [name for name in providers.EPG if conf["epg"].get(name)]
    snapshots = store.read_snapshots(
        products=("sports", *("epg-quality:" + name for name in enabled_guides)),
        timestamps_only=(*("sports:" + name for name in enabled_sports),
                         *("epg:" + name for name in enabled_guides)),
    )
    snap = snapshots.get("sports")
    all_events = snap["data"]["events"] if snap else []
    # In a fused fixture, the primary source may be approved while another
    # source supplied a participant/time/status. Until field-level lineage is
    # implemented, fail closed unless *every* contributor is approved.
    def licensed(event):
        origin = event.get("source_id")
        contributors = event.get("sources") or [origin]
        return (isinstance(origin, str) and origin in approved
                and isinstance(contributors, list) and bool(contributors)
                and all(isinstance(src, str) and src in approved for src in contributors))
    # Legacy/unclassified snapshot rows still need category fields the schema requires.
    events = [_event_public(e if "category_id" in e else taxonomy.classify(e)) for e in all_events if licensed(e)]
    omitted = sorted({src for e in all_events if not licensed(e)
                      for src in (e.get("sources") or [e.get("source_id")])
                      if isinstance(src, str) and src not in approved})
    by_day = {}
    for event in events:
        day = datetime.fromisoformat(event["start_utc"]).astimezone(LONDON).date().isoformat()
        by_day.setdefault(day, []).append(event)
    today = now.astimezone(LONDON).date()
    window = [(today + timedelta(days=i)).isoformat() for i in range(8)]

    assets, files = [], {}

    def add(kind, obj, schema, required, **extra):
        data = _json(obj)
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
    for day in window:
        rows = sorted(by_day.get(day, []), key=lambda e: (e["start_utc"], e["id"]))
        add("events:" + day, {"schema": "sli.events-day/1", "date": day, "timezone": "Europe/London", "events": rows},
            "sli.events-day/1", day == window[0], date=day, records=len(rows))
    todays = by_day.get(window[0], [])
    groups = {}
    for event in todays:
        groups.setdefault(event["sport"], {}).setdefault(event["category_id"], []).append(event)
    featured_tags = sorted({"team:england", "team:england_women", "team:scotland", "team:wales", "team:northern_ireland",
                            "team:ireland", "team:lions", "team:great_britain", "ppv"})
    today_doc = {
        "schema": "sli.today/1", "date": window[0],
        "featured_event_ids": [e["id"] for e in sorted(todays, key=lambda e: e["start_utc"]) if set(e.get("tags", [])) & set(featured_tags)],
        "groups": [{"sport": sport, "categories": [
            {"id": cid, "event_ids": [e["id"] for e in sorted(rows, key=lambda e: e["start_utc"])]}
            for cid, rows in sorted(cats.items(), key=lambda kv: (kv[1][0].get("category_priority", 90), kv[0]))]}
            for sport, cats in sorted(groups.items(), key=lambda kv: taxonomy.sport_order(kv[0]))],
    }
    add("today", today_doc, "sli.today/1", True, date=window[0], records=len(todays))
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
    manifest = {
        "feed": "sportsliveinfo", "format": "sli/%d.%d" % (FORMAT_MAJOR, FORMAT_MINOR),
        "format_major": FORMAT_MAJOR, "format_minor": FORMAT_MINOR,
        "compatibility": {"reader_major": FORMAT_MAJOR, "min_reader_minor": 0, "unknown_fields": "ignore",
                          "unknown_assets": "ignore", "unknown_enum_fallback": FALLBACKS,
                          "on_major_mismatch": "keep last good feed; show 'update B1G to read the newer SportsLiveInfo feed'"},
        "revision": revision, "previous_revision": previous_revision,
        "generated_at": now.isoformat(timespec="seconds"),
        "publisher": {"app": "SportsLiveInfo", "version": __version__},
        "timezone_reference": "Europe/London", "window": {"from": window[0], "to": window[-1]},
        "refresh": {"schedule_europe_london": schedule, "expected_interval_minutes": interval,
                    "reader_poll_minutes": 30, "stale_after_hours": 30,
                    "expires_at": (now + timedelta(hours=48)).isoformat(timespec="seconds")},
        "capabilities": ["taxonomy", "channel_registry", "channel_families", "guide_catalogue", "events_by_day",
                         "today", "source_health", "fixture_corroboration"]
                        + (["channel_identity"] if identity_doc else [])
                        + (["channel_dictionary"] if dictionary_doc else [])
                        + (["verified_broadcasts"] if any(e["broadcast_verified"] for e in events) else []),
        "assets": assets,
        "coverage": {"events": len(events), "today": len(todays), "by_sport": dict(sorted(by_sport.items())),
                     "corroborated": sum(e.get("fixture_confidence") == "corroborated" for e in events),
                     "verified_broadcasts": sum(e["broadcast_verified"] for e in events),
                     "sports_known": len(taxonomy.SPORTS), "competitions_known": sum(len(t) for t in taxonomy.COMPETITIONS.values()),
                     "services_known": len({cid for t in SERVICES.values() for cid in t.values()}),
                     "families_known": len(CHANNEL_FAMILIES)},
        "rights": {"events": {"approved_sources": sorted(approved), "omitted_unapproved_sources": omitted},
                   "epg_programmes": "not_published", "broadcast_candidates": "not_published",
                   "attribution": [{"source": s, "text": ATTRIBUTION[s][0], "licence": ATTRIBUTION[s][1]}
                                   for s in sorted({providers.SPORT_FAMILY.get(a, a) for a in approved}) if s in ATTRIBUTION]
                                  + ([{"source": "iptv_org_database", "text": "Channel dictionary from the iptv-org database",
                                       "licence": "Unlicense (public domain)"}] if dictionary_doc else [])},
        "display_policy": {"sports_today_body_cards": 10, "ppv_pinned_extra_card": True, "featured_tags": featured_tags,
                           "user_settings_override": True},
        "notices": [] if events else ["No rights-approved sporting events in this revision; registry assets remain valid."],
    }
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
