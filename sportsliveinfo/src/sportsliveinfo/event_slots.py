"""Event-slot channels: provider channels whose *name* is the programme.

Many lineups carry numbered event channels whose name announces the match and its
start time, e.g. ``EPL 05 | Home vs Away (Sat 17:30 UK)`` or ``DAZN 52: Premier
League| Home vs. Away| Sat 18 Oct 12:30 PM``. No guide lists them (the channel only
exists for the event), so the name itself is the guide entry. This module is the
reference parser B1G reproduces on the TV (the channel names are the owner's local
lineup and are never uploaded): it extracts the slot label, competition,
participants and start time, and links the slot to a SportsLiveInfo event when the
fixture and time agree.

Conservative by design: a slot links only to exactly one event with both sides
matching and the start within ``MATCH_WINDOW``; without a parsed time, only an event
starting within the next ``UNTIMED_WINDOW``.
"""
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import linking
from .guide import repair_text

MATCH_WINDOW = timedelta(hours=3)
UNTIMED_WINDOW = timedelta(hours=36)
ZONES = {"uk": "Europe/London", "gmt": "UTC", "bst": "Europe/London", "utc": "UTC", "cet": "Europe/Paris",
         "cest": "Europe/Paris", "et": "America/New_York", "est": "America/New_York", "edt": "America/New_York",
         "pt": "America/Los_Angeles", "pst": "America/Los_Angeles", "pdt": "America/Los_Angeles",
         "ct": "America/Chicago", "aest": "Australia/Sydney", "nzt": "Pacific/Auckland"}
_MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
_DAYS = {d: i for i, d in enumerate(("mon", "tue", "wed", "thu", "fri", "sat", "sun"))}
_ZONE = r"(?P<zone>uk|gmt|bst|utc|cet|cest|et|est|edt|pt|pst|pdt|ct|aest|nzt)"
_CLOCK = r"(?P<h>\d{1,2})(?:[:.h](?P<m>\d{2}))?\s*(?P<ampm>am|pm)?"

# Time expressions, most specific first. Each match is removed from the name before the fixture is read.
_TIME_PATTERNS = [
    ("iso", re.compile(r"(?:start:\s*)?\(?(?P<y>20\d\d)-(?P<mo>\d\d)-(?P<d>\d\d)[ t](?P<h>\d\d):(?P<m>\d\d)(?::\d\d)?\)?"
                       r"(?:\s*stop:\s*20\d\d-\d\d-\d\d[ t]\d\d:\d\d(?::\d\d)?)?", re.I)),
    ("dow_day_month", re.compile(r"(?P<dow>mon|tue|wed|thu|fri|sat|sun)[a-z]*,?\s*(?P<d>\d{1,2})\s+(?P<mon>[a-z]{3})[a-z]*"
                                 r"\s+" + _CLOCK + r"(?:\s*" + _ZONE + r")?\b", re.I)),
    ("month_day", re.compile(r"(?P<mon>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(?P<d>\d{1,2})\s+"
                             + _CLOCK + r"(?:\s*" + _ZONE + r")?\b", re.I)),
    ("numeric_day", re.compile(r"(?P<mo>\d{1,2})[.\-/](?P<d>\d{1,2})\s+" + _CLOCK + r"(?:\s*" + _ZONE + r")?\b", re.I)),
    ("dow_time", re.compile(r"(?P<dow>mon|tue|wed|thu|fri|sat|sun)[a-z]*\s+" + _CLOCK + r"(?:\s*" + _ZONE + r")?\b", re.I)),
    ("time", re.compile(r"(?<![\w:])(?P<h>\d{1,2})(?:[:.h](?P<m>\d{2}))?\s*(?P<ampm>am|pm)(?:\s*" + _ZONE + r")?\b"
                        r"|(?<![\w:.])(?P<h2>[01]?\d|2[0-3]):(?P<m2>\d{2})(?:\s*" + _ZONE.replace("zone", "zone2") + r")?\b",
                        re.I)),
]
# Leading slot label: "22. EPL 05 | ", "PL+ 017| ", "CA-DAZN 52: ", "L1 Pass 06 | ", "GaaTv02: ", "NFL 01: ".
_SLOT = re.compile(r"^\s*(?:\d{1,3}\.\s*)?(?P<slot>(?:[A-Za-z][A-Za-z0-9+&'\-]*\s?){1,4}?\s?\d{1,3}"
                   r"(?:\s+(?:hd|sd|fhd|uhd)(?:\s*\([a-z]\))?)?)\s*(?:[|:]|\s-\s)\s*", re.I)
# Slot label at the end ("… @ Nov 9 9:00 PM :NBA 07", "… :TSN+  06").
_TRAILING_SLOT = re.compile(r"\s:\s*(?P<slot>[A-Za-z][A-Za-z+ ]{0,20}?\s*\d{1,3})\s*$")
_SIDES = re.compile(r"\s+(?:[vV][sS]?\.?|versus|x|@)\s+")    # lower-case "x" only: "X Premium" is a channel
_QUALIFIER = re.compile(r"\s*(?:\((?:[^()]{1,25})\)|-\s*(?:player cam|host corner.*|tactical cam.*|multi.*)|\b(?:hd|fhd|sd|uhd|4k)\b)\s*$",
                        re.I)
_NOISE = re.compile(r"//|\bstart\b|\bstop\b|\b(?:and|or)\s*$|\s+-\s*$|\s*[|:,]\s*$", re.I)


def _tz(token, default_tz):
    return ZoneInfo(ZONES.get((token or "").lower(), default_tz))


def _hour(match):
    groups = match.groupdict()
    hour = int(groups.get("h") or groups.get("h2"))
    minute = int(groups.get("m") or groups.get("m2") or 0)
    ampm = (groups.get("ampm") or "").lower()
    if ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        raise ValueError("not a clock time")
    return hour, minute


def _nearest(candidates, now):
    return min(candidates, key=lambda dt: abs(dt - now)) if candidates else None


def parse_time(text, *, now, default_tz="Europe/London"):
    """(start datetime in UTC or None, precision, remaining text). Precision: "datetime" or "time"."""
    for kind, pattern in _TIME_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        try:
            groups = match.groupdict()
            zone = _tz(groups.get("zone") or groups.get("zone2"), default_tz if kind != "iso" or "start:" not in
                       match.group(0).lower() else "UTC")
            local_now = now.astimezone(zone)
            if kind == "iso":
                start = datetime(int(groups["y"]), int(groups["mo"]), int(groups["d"]), int(groups["h"]),
                                 int(groups["m"]), tzinfo=zone)
            else:
                hour, minute = _hour(match)
                if kind in ("dow_day_month", "month_day", "numeric_day"):
                    month = _MONTHS[groups["mon"][:3].lower()] if groups.get("mon") else int(groups["mo"])
                    day = int(groups["d"])
                    if month > 12 and day <= 12:                  # "21/07": day/month (UK style)
                        month, day = day, month
                    start = _nearest([datetime(year, month, day, hour, minute, tzinfo=zone)
                                      for year in (local_now.year - 1, local_now.year, local_now.year + 1)], now)
                elif kind == "dow_time":
                    wanted = _DAYS[groups["dow"][:3].lower()]
                    base = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    start = _nearest([base + timedelta(days=offset) for offset in range(-3, 5)
                                      if (base + timedelta(days=offset)).weekday() == wanted], now)
                else:
                    base = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    start = _nearest([base + timedelta(days=offset) for offset in (-1, 0, 1)], now)
        except (ValueError, KeyError):
            continue
        rest = (text[:match.start()] + " " + text[match.end():]).strip()
        return start.astimezone(timezone.utc), ("time" if kind == "time" else "datetime"), rest
    return None, None, text


def parse_slot(name, *, now, default_tz="Europe/London"):
    """Parse an event-slot channel name; None when it does not announce a fixture.

    Returns {"slot", "competition", "participants": [first, second], "start_utc" (ISO or None),
    "precision": "datetime"|"time"|None, "away_at_home": bool}.
    """
    text = repair_text(str(name)).replace("\u00a0", " ")
    trailing = _TRAILING_SLOT.search(text)
    if trailing:
        text = text[:trailing.start()]
    slot_match = _SLOT.match(text)
    slot = slot_match.group("slot").strip() if slot_match else (trailing.group("slot").strip() if trailing else "")
    body = text[slot_match.end():] if slot_match else text
    body = re.sub(r"\[[^\]]{1,12}\]", " ", body)                   # "[4K]", "[EN]"
    zoned = re.search(r"(?://|^|\|)\s*(UK|ET|GMT|CET)\s+(?=(?:mon|tue|wed|thu|fri|sat|sun))", body, re.I)
    if zoned:                                                        # "// UK Sun 21/07 11:50pm // ET …"
        default_tz = ZONES[zoned.group(1).lower()]
        later = re.search(r"//\s*(?:UK|ET|GMT|CET)\s+[^/]*$", body[zoned.end():], re.I)
        if later:                                                    # drop the second time zone's copy
            body = body[:zoned.end() + later.start()]
        body = body[:zoned.start(1)] + body[zoned.end(1):]
    body = re.sub(r"(?<![\d:])(\d{1,2})(\d{2})\s*(am|pm)\b", r"\1:\2\3", body, flags=re.I)   # "530PM"
    start, precision, body = parse_time(body, now=now, default_tz=default_tz)
    body = re.sub(r"\(\s*\)|\[\s*\]", " ", body)
    body = re.sub(r"\s+@\s*(?=$|\s+-\s|\s*\|)", " ", body)   # "@" left behind by "@ Nov 9 9:00 PM"
    suffix = ""
    if re.search(r"\s-\s", body) and _SIDES.search(" " + body.split(" - ")[0] + " "):
        body, suffix = body.split(" - ", 1)                   # "A vs B - WTA Finals": competition after
    elif re.search(r"\s-\s", body) and _SIDES.search(" " + body.rsplit(" - ", 1)[-1] + " ") \
            and not _SIDES.search(" " + body.rsplit(" - ", 1)[0] + " "):
        suffix, body = body.rsplit(" - ", 1)                  # "WTA Finals - A vs B"
    segments = [s.strip() for s in re.split(r"\s*\|\s*|\s+//\s+|:\s+(?=[^:]*\b(?:vs?\.?|x|@)\s)", body) if s.strip()]
    fixture_index = next((i for i, s in enumerate(segments) if _SIDES.search(" " + s + " ")), None)
    if fixture_index is None:
        return None
    fixture = segments[fixture_index]
    competition = " | ".join(s for s in segments[:fixture_index] if not re.fullmatch(r"[\d\s:./]+", s))
    if ":" in fixture:
        head, tail = fixture.rsplit(":", 1)
        if _SIDES.search(" " + tail + " ") and not _SIDES.search(" " + head + " "):
            fixture = tail                               # "TrillerTV-UAE Pro League 2025/26: A vs B"
            competition = (competition + " | " + head.strip()).strip(" |")
        elif _SIDES.search(" " + head + " "):
            fixture = head                               # "A vs. B: Prelims"
    competition = (competition + (" | " + suffix.strip() if suffix.strip() else "")).strip(" |")
    separator = _SIDES.search(" " + fixture.strip() + " ")
    sides = _SIDES.split(" " + fixture.strip() + " ")
    if len(sides) != 2:
        return None
    lead = re.match(r"^\s*([A-Z][A-Za-z+]{1,9}\s?\d{1,3})\s+(?=\S)", sides[0])
    if lead and not slot:                               # "WNBA 1 Connecticut Sun @ Indiana Fever"
        slot, sides[0] = lead.group(1), sides[0][lead.end():]
    away_at_home = bool(re.search(r"\s@\s", fixture))
    cleaned = []
    for side in sides:
        side = re.sub(r"\s*\b\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm)\b", " ", side, flags=re.I)
        for _ in range(3):
            side = _QUALIFIER.sub("", _NOISE.sub("", side.strip()))
        side = re.sub(r",\s*\d+(?:st|nd|rd|th)\b.*$", "", side)       # "India, 3rd ODI"
        side = re.sub(r"^\W+|\W+$", "", side.replace("_", " ")).strip()
        cleaned.append(side)
    if not all(cleaned) or any(len(s) > 60 for s in cleaned):
        return None
    single_letter = separator and separator.group(0).strip() in ("V", "x")
    if min(len(s) for s in cleaned) < 2 or re.fullmatch(r"[A-Z]{2}", cleaned[0]) or (
            single_letter and re.fullmatch(r"[A-Z]{2,3}", cleaned[0])):
        return None                                      # "CA V Montreal": a channel name, not a fixture
    return {"slot": slot, "competition": competition.strip(" -|:"), "participants": cleaned,
            "start_utc": start.isoformat().replace("+00:00", "Z") if start else None,
            "precision": precision, "away_at_home": away_at_home}


def _keys(name):
    key = frozenset(linking.team_key(re.sub(r"\s*\([^)]*\)", " ", str(name))) - linking._VARIANT)
    return key if key and set(key) - linking._GENERIC - linking._LOW_SIGNAL_TEAM_TOKENS else None


def match_slot(parsed, events, *, now):
    """The one SportsLiveInfo event a parsed slot shows, or None (never a guess between several).

    Both sides must match (either order: "Away @ Home" is common). A full date and time must be within
    MATCH_WINDOW of the event; a clock time alone ("8:15PM") matches that time of day on any day from
    four hours ago to UNTIMED_WINDOW ahead, so two meetings of the same teams on consecutive days stay
    unresolved; no time at all needs the event within that same window.
    """
    if not parsed:
        return None
    first, second = (_keys(p) for p in parsed["participants"])
    if not first or not second:
        return None
    start = datetime.fromisoformat(parsed["start_utc"].replace("Z", "+00:00")) if parsed["start_utc"] else None
    found = []
    for event in events:
        participants = event.get("participants") or []
        if len(participants) < 2:
            continue
        short = (event.get("participants_short") or []) + [None, None]
        home = [k for k in (_keys(participants[0]), _keys(short[0]) if short[0] else None) if k]
        away = [k for k in (_keys(participants[1]), _keys(short[1]) if short[1] else None) if k]
        same = any(linking.same_team(first, h) for h in home) and any(linking.same_team(second, a) for a in away)
        swapped = any(linking.same_team(first, a) for a in away) and any(linking.same_team(second, h) for h in home)
        if not (same or swapped):
            continue
        try:
            event_start = linking._dt(event.get("start_utc") or event.get("start"))
        except (TypeError, ValueError):
            continue
        in_window = now - timedelta(hours=4) <= event_start <= now + UNTIMED_WINDOW
        if start is not None and parsed.get("precision") == "datetime":
            if abs(event_start - start) > MATCH_WINDOW:
                continue
        elif start is not None:                                     # clock time only
            offset = (event_start - start) % timedelta(days=1)
            if not in_window or min(offset, timedelta(days=1) - offset) > timedelta(minutes=30):
                continue
        elif not in_window:
            continue
        found.append(event)
    return found[0] if len(found) == 1 else None
