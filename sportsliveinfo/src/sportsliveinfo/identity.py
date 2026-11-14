"""Channel identity across guides by schedule fingerprints (EPG identity graph).

Two guide channels that show the same programmes at the same times are the
same service, whatever they are called. This module links channels across the
guides the collector already downloads, so B1G can translate a provider tvg-id
from one guide family into another guide's id (an "identity graph").

Rights and privacy: fingerprints are built and compared privately on the Home
Assistant host. Only channel identifiers, display names and timeshift
relations are published, never programme titles, times or descriptions.

Safety: names must not contradict each other. Identity-bearing differences
(+1/+2, "Sports+"/plus, numbers, UK regions) block a merge regardless of how
similar the schedules are, because regional and sister channels share most
of their schedule.
"""
import hashlib
import html
import re
import unicodedata
from collections import Counter, defaultdict
from functools import lru_cache
from datetime import datetime, timedelta, timezone

from .guide import COUNTRY_BY_SOURCE, GENERIC_PROGRAMME, SOURCE_ID_CROSSWALK, canonical_channel, normalized_name

METHOD = "schedule_fingerprint/1"
BUCKET_MINUTES = 5
WINDOW_HOURS = 36
SHIFTS = (0, 60, 120)
MAX_SLOTS_PER_CHANNEL = 160
MAX_POSTING = 40            # a (time, token) key shared by more channels is generic (simulcast news, filler)
MIN_SHARED_KEYS = 4
MIN_MATCHED_SLOTS = 6
MIN_OVERLAP_MINUTES = 6 * 60

STOP_WORDS = frozenset("""the and with from for live new season series episode part premiere repeat
    les des une sur avec dans der die das und mit the""".split())
FILLER_TITLES = re.compile(
    r"^(?:close|closedown|teleshopping|shopping|off air|programmes? (?:start|resume).*|paid programming|"
    r"this is bbc .*|bbc news(?: at .*)?|news|weather|film|movie|tba|to be announced|no information|"
    r"programme information|coming up|join .*|sign zone|.*infomercial.*)$", re.I)
REGIONS = frozenset("""scotland wales cymru ireland northern ni london yorkshire midlands granada meridian anglia
    ulster tyne tees border westcountry west east north south channel islands lancashire roi ci""".split())
# Language and territory feeds of one brand are different services (Al Jazeera vs Al Jazeera Arabic).
LANGUAGES = frozenset("""arabic english french francais german deutsch spanish espanol italian hindi urdu turkish
    polish portuguese russian chinese mandarin cantonese persian farsi kurdish dutch greek""".split())
NUMBER_WORDS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
                "eight": "8", "nine": "9", "ten": "10"}
# Decoration that never changes which service a name denotes.
NAME_NOISE = frozenset({"tv", "channel", "the", "hd", "network", "uk", "gb", "uktv", "television"})


def _fold(text):
    value = unicodedata.normalize("NFKD", str(text))
    return "".join(ch for ch in value if not unicodedata.combining(ch)).casefold()


def title_tokens(title):
    """Comparable title tokens, or None for generic/filler programmes."""
    text = _fold(title).strip()
    text = re.sub(r"^(?:live|new|premiere|nouveau|direct)\s*[:\-]\s*", "", text)
    text = re.sub(r"\(.*?\)|\[.*?\]", " ", text)
    if not text or GENERIC_PROGRAMME.match(text) or FILLER_TITLES.match(text):
        return None
    tokens = [t for t in re.split(r"[^a-z0-9]+", text) if len(t) >= 3 and t not in STOP_WORDS]
    return frozenset(tokens[:6]) or None


def name_signature(display_name):
    """(identity tokens, comparable name tokens, normalised name) for a display name."""
    return _name_signature(str(display_name))


@lru_cache(maxsize=100_000)
def _name_signature(display_name):
    norm = normalized_name(html.unescape(display_name))
    text = re.sub(r"\+\s*([12])\b", r" ts\1 ", norm)
    text = re.sub(r"\bplus\s*([12])\b", r" ts\1 ", text)
    text = text.replace("+", " plus ")
    words = [NUMBER_WORDS.get(w, w) for w in re.split(r"[^a-z0-9]+", text) if w]
    identity = set()
    for word in words:
        if word in ("ts1", "ts2", "plus"):
            identity.add(word)
        elif word.isdigit() and len(word) <= 3:
            identity.add("n" + word)
        elif word in REGIONS:
            identity.add("r" + word)
        elif word in LANGUAGES:
            identity.add("l" + word)
    tokens = frozenset(w for w in words if w not in NAME_NOISE and w not in ("ts1", "ts2"))
    return frozenset(identity), tokens, norm


def _jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def fingerprint_guide(source_id, guide, start, end):
    """Compact private fingerprints: {channel_id: {"name", "slots": [(bucket, tokens)]}}."""
    names = guide.get("channels") or {}
    lo = int(start.timestamp() // 60 // BUCKET_MINUTES)
    hi = int(end.timestamp() // 60 // BUCKET_MINUTES)
    slots = defaultdict(list)
    for row in guide.get("programmes") or []:
        try:
            begin = datetime.fromisoformat(row["start_utc"])
            if begin.tzinfo is None:
                begin = begin.replace(tzinfo=timezone.utc)
        except (KeyError, TypeError, ValueError):
            continue
        bucket = int(begin.timestamp() // 60 // BUCKET_MINUTES)
        if not lo <= bucket < hi:
            continue
        tokens = title_tokens(row.get("title", ""))
        channel = str(row.get("channel_id") or "")
        if tokens and channel:
            slots[channel].append((bucket, tokens))
    out = {}
    for channel, rows in slots.items():
        rows.sort(key=lambda r: r[0])
        deduped = []
        for bucket, tokens in rows:
            if not deduped or deduped[-1][0] != bucket:
                deduped.append((bucket, tokens))
        if len(deduped) >= MIN_MATCHED_SLOTS:
            out[channel] = {"name": html.unescape(str(names.get(channel, channel))),
                            "slots": deduped[:MAX_SLOTS_PER_CHANNEL]}
    return out


def _slot_score(a_slots, b_slots, shift_buckets):
    """Fraction of comparable slots whose titles agree, with B shifted earlier by shift_buckets."""
    b_shifted = [(bucket - shift_buckets, tokens) for bucket, tokens in b_slots]
    lo = max(a_slots[0][0], b_shifted[0][0])
    hi = min(a_slots[-1][0], b_shifted[-1][0])
    if (hi - lo) * BUCKET_MINUTES < MIN_OVERLAP_MINUTES:
        return 0.0, 0
    a_in = [s for s in a_slots if lo <= s[0] <= hi]
    b_in = [s for s in b_shifted if lo <= s[0] <= hi]
    if not a_in or not b_in:
        return 0.0, 0
    by_bucket = defaultdict(list)
    for bucket, tokens in b_in:
        by_bucket[bucket].append(tokens)
    matched = 0
    for bucket, tokens in a_in:
        for near in (bucket - 1, bucket, bucket + 1):
            if any(_titles_agree(tokens, other) for other in by_bucket.get(near, ())):
                matched += 1
                break
    return matched / min(len(a_in), len(b_in)), matched


def _titles_agree(a, b):
    if _jaccard(a, b) >= 0.5:
        return True
    small, large = (a, b) if len(a) <= len(b) else (b, a)
    return len(small) >= 2 and small <= large


def _candidate_pairs(prints):
    """Channel pairs (different sources) sharing enough (time, title-token) keys, per shift."""
    index = defaultdict(list)
    for node, fp in prints.items():
        for bucket, tokens in fp["slots"]:
            for token in tokens:
                if len(token) >= 4:
                    index[(bucket, token)].append(node)
    pairs = Counter()
    shift_steps = [s // BUCKET_MINUTES for s in SHIFTS]
    for (bucket, token), nodes in index.items():
        if len(nodes) > MAX_POSTING:
            continue
        for step in shift_steps:
            # node B airing the same title `step` later than A: B key = bucket + step.
            later = index.get((bucket + step, token)) if step else nodes
            if not later or len(later) > MAX_POSTING:
                continue
            for a in nodes:
                for b in later:
                    if (a[0] != b[0] and (step or a < b)) or (not step and a[0] == b[0] and a < b):
                        pairs[(a, b, step)] += 1
    return [key for key, shared in pairs.items() if shared >= MIN_SHARED_KEYS]


def _curated_id(node, name):
    source_id, channel_id = node
    return (SOURCE_ID_CROSSWALK.get(source_id, {}).get(channel_id)
            or canonical_channel(source_id, channel_id, name))


def _market(source_ids):
    markets = Counter(COUNTRY_BY_SOURCE.get(s) for s in source_ids if COUNTRY_BY_SOURCE.get(s))
    if not markets:
        return "ZZ"
    top = max(markets.values())
    return "GB" if markets.get("GB") == top else sorted(m for m, n in markets.items() if n == top)[0]


def resolve(prints_by_source):
    """Link channels across guides. Returns (document, private_report).

    prints_by_source: {source_id: fingerprint_guide(...)}.
    """
    prints = {(source, channel): fp for source, chans in prints_by_source.items() for channel, fp in chans.items()}
    sigs = {node: name_signature(fp["name"]) for node, fp in prints.items()}
    edges, suggestions, timeshifts, duplicates = [], [], [], []
    for a, b, step in _candidate_pairs(prints):
        score, matched = _slot_score(prints[a]["slots"], prints[b]["slots"], step)
        if matched < MIN_MATCHED_SLOTS or score < 0.5:
            continue
        (ida, toka, norma), (idb, tokb, normb) = sigs[a], sigs[b]
        if a[0] == b[0]:
            # Same guide: only HD/SD duplicates of one service (identical names, near-identical schedules).
            if ida == idb and toka == tokb and score >= 0.9:
                duplicates.append((a, b))
            continue
        if step:
            # B airs A's schedule `step` buckets later: B must be the +1/+2 of A.
            tag = {60: "ts1", 120: "ts2"}.get(step * BUCKET_MINUTES)
            if (tag in idb and tag not in ida and (idb - {tag}) == ida
                    and _jaccard(toka, tokb) >= 0.5 and score >= 0.75):
                timeshifts.append((b, a, step * BUCKET_MINUTES, round(score, 3)))
            continue
        if ida != idb:
            continue                       # regional, language, numbered, +1 or Sports+ difference: never merged
        if toka == tokb and score >= 0.5:
            # Same name once decoration (HD, TV, prefixes) is removed.
            edges.append((score + (0.5 if norma == normb else 0.25), a, b))
        elif score >= 0.85 and matched >= 10:
            suggestions.append({"a": list(a), "a_name": prints[a]["name"], "b": list(b), "b_name": prints[b]["name"],
                                "schedule_agreement": round(score, 3), "matched_slots": matched,
                                "reason": "schedules agree but names differ; owner review required"})

    # Constrained union-find: a cluster never holds two channels of one guide
    # or two different curated identities.
    parent = {node: node for node in prints}
    members = {node: {node} for node in prints}
    curated = {node: ({c} if (c := _curated_id(node, prints[node]["name"])) else set()) for node in prints}

    def find(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def guides_conflict(ra, rb):
        """Two clusters may share a guide only through same-name duplicates (HD/SD/UHD copies)."""
        shared = {n[0] for n in members[ra]} & {n[0] for n in members[rb]}
        for source in shared:
            names = {sigs[n][:2] for n in members[ra] | members[rb] if n[0] == source}
            if len(names) > 1:
                return True
        return False

    def merge(ra, rb):
        parent[rb] = ra
        members[ra] |= members.pop(rb)
        curated[ra] |= curated.pop(rb)

    for a, b in sorted(duplicates):
        ra, rb = find(a), find(b)
        if ra != rb and len(curated[ra] | curated[rb]) <= 1:
            merge(ra, rb)

    for _, a, b in sorted(edges, key=lambda e: (-e[0], e[1], e[2])):
        ra, rb = find(a), find(b)
        if ra == rb:
            continue
        if guides_conflict(ra, rb) or len(curated[ra] | curated[rb]) > 1:
            continue
        merge(ra, rb)

    # A curated identity is authoritative: every cluster carrying it is one service,
    # even where the schedules did not overlap enough to link them.
    by_curated = {}
    for root in [r for r in members if find(r) == r]:
        if len(curated[root]) == 1:
            cid = next(iter(curated[root]))
            if cid in by_curated:
                merge(by_curated[cid], root)
            else:
                by_curated[cid] = root

    clusters, used_ids = [], set()
    for root, nodes in members.items():
        if find(root) != root:
            continue
        cid = next(iter(curated[root]), None)
        if len(nodes) < 2 and not cid:
            continue
        if not cid:
            names = Counter(sigs[n][2] for n in nodes)
            slug = re.sub(r"[^a-z0-9]+", "_", _fold(names.most_common(1)[0][0])).strip("_") or "channel"
            cid = "%s.auto.%s" % (_market({n[0] for n in nodes}).lower(), slug)
            if cid in used_ids:
                digest = hashlib.sha256("|".join(sorted("%s:%s" % n for n in nodes)).encode()).hexdigest()[:6]
                cid = "%s_%s" % (cid, digest)
        used_ids.add(cid)
        clusters.append({
            "id": cid,
            "market": _market({n[0] for n in nodes}),
            "curated": bool(curated[root]),
            "names": sorted({prints[n]["name"] for n in nodes})[:6],
            "members": [{"source_id": s, "channel_id": c} for s, c in sorted(nodes)],
        })
    clusters.sort(key=lambda c: c["id"])
    by_node = {(m["source_id"], m["channel_id"]): c["id"] for c in clusters for m in c["members"]}

    shift_rows = []
    for shifted, base, minutes, score in sorted(set(timeshifts)):
        base_id = by_node.get(base) or _curated_id(base, prints[base]["name"])
        shift_rows.append({"source_id": shifted[0], "channel_id": shifted[1], "offset_minutes": minutes,
                           "base": {"source_id": base[0], "channel_id": base[1]},
                           **({"base_id": base_id} if base_id else {})})

    document = {
        "schema": "sli.identity/1",
        "method": METHOD,
        "rules": {
            "published": "channel ids, display names and timeshift relations only; no programme data",
            "merge_requires": "matching identity tokens (+1/+2, plus/Sports+, numbers, regions, languages) AND "
                              "the same name once decoration is removed AND >=50% schedule agreement",
            "never_merged": "two differently named channels of the same guide; two different curated identities; "
                            "names differing by anything other than decoration (those go to owner review)",
            "reader_use": "a provider tvg-id equal to any member channel_id of a guide may use any other member's "
                          "guide rows; user manual mapping and provider exact ids still take precedence",
        },
        "channels": clusters,
        "timeshifts": shift_rows,
    }
    stats = {
        "guides": len(prints_by_source),
        "channels_fingerprinted": len(prints),
        "candidate_edges": len(edges),
        "clusters": len(clusters),
        "linked_channels": sum(len(c["members"]) for c in clusters),
        "timeshifts": len(shift_rows),
        "suggestions": len(suggestions),
    }
    suggestions.sort(key=lambda s: -s["schedule_agreement"])
    return document, {"stats": stats, "suggestions": suggestions[:200]}


def build_from_store(store, guide_names, now=None):
    """Fingerprint stored guides one at a time (bounded memory) and resolve identity."""
    now = now or datetime.now(timezone.utc)
    start, end = now - timedelta(hours=1), now + timedelta(hours=WINDOW_HOURS)
    prints = {}
    for name in guide_names:
        snapshot = store.read_snapshots(products=("epg:" + name,)).get("epg:" + name)
        if snapshot and snapshot.get("data"):
            prints[name] = fingerprint_guide(name, snapshot["data"], start, end)
    document, report = resolve(prints)
    report["generated_at"] = now.isoformat(timespec="seconds")
    report["window"] = {"from": start.isoformat(timespec="seconds"), "to": end.isoformat(timespec="seconds")}
    return document, report
