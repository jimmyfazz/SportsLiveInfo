"""Private, source-aware EPG coverage and channel identity diagnostics.

Never equate an inferred EPG service with a playable B1G subscription stream.
All programme text remains in the private HAOS database until rights are cleared.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import re
import unicodedata

COUNTRY_BY_SOURCE = {
    "farleyflex": "GB",
    "fr_programmetv": "FR", "fr_telerama": "FR", "fr_xmltv": "FR",
}

# An intentionally small *verified-name* registry. Exact catalogue IDs always
# need a source namespace; this is a reporting aid, not a stream router.
# Never strip service qualifiers: Sports+, region, +1, Canal+ Sport 360, etc.
KNOWN_SERVICES = {
    "bbc one": "gb.bbc.one",
    "bbc two": "gb.bbc.two",
    "itv 1": "gb.itv.one",
    "sky sports main event": "gb.sky.sports.main_event",
    "sky sports premier league": "gb.sky.sports.premier_league",
    "sky sports f1": "gb.sky.sports.f1",
    "sky sports football": "gb.sky.sports.football",
    "sky sports cricket": "gb.sky.sports.cricket",
    "sky sports tennis": "gb.sky.sports.tennis",
    "sky sports golf": "gb.sky.sports.golf",
    "sky sports racing": "gb.sky.sports.racing",
    "sky sports news": "gb.sky.sports.news",
    "tnt sports 1": "gb.tnt.sports.1",
    "tnt sports 2": "gb.tnt.sports.2",
    "tnt sports 3": "gb.tnt.sports.3",
    "tnt sports 4": "gb.tnt.sports.4",
    "premier sports 1": "gb.premier.sports.1",
    "premier sports 2": "gb.premier.sports.2",
    "france 2": "fr.francetv.france2",
    "france 3": "fr.francetv.france3",
    "france 4": "fr.francetv.france4",
    "france 5": "fr.francetv.france5",
    "tf1": "fr.tf1.tf1",
    "canal+": "fr.canal.main",
    "canal+ sport": "fr.canal.sport",
    "canal+ sport 360": "fr.canal.sport360",
    "bein sports 1": "fr.bein.sports.1",
    "bein sports 2": "fr.bein.sports.2",
    "bein sports 3": "fr.bein.sports.3",
    "rmc sport 1": "fr.rmc.sport.1",
    "rmc sport 2": "fr.rmc.sport.2",
}

QUALITY_SUFFIX = re.compile(r"\s+(?:hd|fhd|sd|uhd|4k|hevc|h265|h264|2160p|1080p|720p)$", re.I)
COUNTRY_PREFIX = re.compile(r"^(?:uk|gb|fr|france)\s*(?:[|:\-])\s*", re.I)
SPACES = re.compile(r"\s+")
GENERIC_PROGRAMME = re.compile(r"^(?:live (?:football|sport|sports|rugby|cricket|tennis|boxing)|to be announced|tba|programme information|no information|sporting event|live event)$", re.I)


def normalized_name(name):
    """Remove safe decorations while retaining identity-bearing service variants."""
    value = unicodedata.normalize("NFKD", str(name))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold().replace("&", " and ").strip()
    value = COUNTRY_PREFIX.sub("", value)
    value = SPACES.sub(" ", value)
    while True:
        new = QUALITY_SUFFIX.sub("", value).strip()
        if new == value:
            break
        value = new
    value = re.sub(r"\bbbc\s*1\b", "bbc one", value)
    value = re.sub(r"\bbbc\s*2\b", "bbc two", value)
    value = re.sub(r"\bitv\s*one\b", "itv 1", value)
    value = value.replace("be in sports", "bein sports")
    return SPACES.sub(" ", value).strip()


def canonical_channel(source_id, epg_id, display_name):
    """Conservative identity hint: never infer unknown regional or suffix variants."""
    name = normalized_name(display_name)
    market = COUNTRY_BY_SOURCE.get(source_id)
    cid = KNOWN_SERVICES.get(name)
    if not cid or not market or not cid.startswith(market.lower() + "."):
        return None
    return cid


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
            generic += bool(GENERIC_PROGRAMME.fullmatch(title.strip()))
            grouped[channel_id].append((a, b))
        except (KeyError, ValueError, TypeError, OverflowError):
            bad += 1
    breakdown = []
    counts = {"24h": 0, "72h": 0, "168h": 0}
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
        breakdown.append({
            "channel_id": channel_id[:180], "name": name[:180],
            "canonical_id": canonical_channel(source_id, channel_id, name),
            "programmes": len(ranges), "coverage_hours": coverage,
        })
    # Worst 24h gaps first, then stable name order; this is an actionable
    # diagnostic, not a blanket overwrite/guessed B1 stream identity.
    breakdown.sort(key=lambda row: (row["coverage_hours"]["24h"], row["name"].casefold()))
    return {
        "source_id": source_id, "country": COUNTRY_BY_SOURCE.get(source_id, "unknown"),
        "channels": len(breakdown), "valid_programmes": sum(map(len, grouped.values())),
        "invalid_programmes": bad + int(guide.get("invalid_programmes", 0)),
        "generic_programmes": generic, "full_coverage_channels": counts,
        "channels_needing_attention": breakdown[:detail_limit],
        "unmatched_canonical_channels": sum(not x["canonical_id"] for x in breakdown),
        "analysed_at": now.isoformat(timespec="seconds"),
        "note": "Private source diagnostics only; matches are identity hints, not IPTV stream mappings",
    }
