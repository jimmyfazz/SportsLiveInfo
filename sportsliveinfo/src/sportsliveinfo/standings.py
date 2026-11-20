"""League standings (optional feed asset ``standings:<competition_id>``, schema ``sli.standings/1``).

One small document per competition so a reader can drop its own standings clients (contract §4.5). Sources:

* football-data.org free competitions (primary): ``/v4/competitions/<code>/standings``, one call per competition, at
  most ``FD_DAILY_BUDGET`` calls a day in an own counter, never into the last ``FD_RESERVE`` of the source's daily
  quota (those stay for the fixture lane).
* API-Sports ``standings`` (optional, off unless config ``standings_api_sports`` is true): only for a competition
  whose table is missing or incomplete after the football-data pass, at most ``AS_DAILY_BUDGET`` calls a day in an
  own counter, never into the live-lane reserve.

Kill switch: config ``publish_standings`` (default true). Nothing is collected or published while it is false.
Network IO lives only in ``collect``; the decoders and ``documents`` are pure. No scores, fixtures or programme data.
"""
import json
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import providers

SCHEMA = "sli.standings/1"
LONDON = ZoneInfo("Europe/London")
FD_DAILY_BUDGET = 12        # football-data.org standings calls per UTC day (own counter "standings:football_data")
FD_RESERVE = 10             # of football_data's daily calls, kept for the fixture lane
AS_DAILY_BUDGET = 4         # API-Sports standings calls per UTC day (own counter "standings:api_sports")
RETRY_AFTER = timedelta(hours=2)    # a competition that failed is not asked again sooner than this
SKIP_DAYS = 3               # a competition the plan refuses (403/404) is not asked again for this long
MAX_AGE_DAYS = 7            # an unrefreshed table older than this is no longer published (rights.standings.max_age_days)
MAX_BYTES = 1_500_000
MAX_ROWS_PER_GROUP = 64

# competition_id -> football-data code, API-Sports league id, label, expected_teams (the six B1G leagues first, in the
# owner's tab order, then the other free football-data leagues). expected_teams counts every row of every group.
COMPETITIONS = {
    "football.champions_league": {"fd": "CL", "as": 2, "label": "UEFA Champions League", "expected": 36},
    "football.premier_league": {"fd": "PL", "as": 39, "label": "Premier League", "expected": 20},
    "football.la_liga": {"fd": "PD", "as": 140, "label": "La Liga", "expected": 20},
    "football.serie_a": {"fd": "SA", "as": 135, "label": "Serie A", "expected": 20},
    "football.bundesliga": {"fd": "BL1", "as": 78, "label": "Bundesliga", "expected": 18},
    "football.ligue_1": {"fd": "FL1", "as": 61, "label": "Ligue 1", "expected": 18},
    "football.championship": {"fd": "ELC", "as": 40, "label": "EFL Championship", "expected": 24},
    "football.eredivisie": {"fd": "DED", "as": 88, "label": "Eredivisie", "expected": 18},
    "football.primeira_liga": {"fd": "PPL", "as": 94, "label": "Primeira Liga", "expected": 18},
}
STANDINGS_SOURCES = ("football_data", "api_sports")

_STAMP = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_GROUP = re.compile(r"^GROUP[_ ]([A-Z0-9])$")


def enabled(conf):
    """The kill switch: ``publish_standings`` (default true)."""
    return conf.get("publish_standings", True) is True


def _z(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return None


def _int(value, low=0):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= low else None


def _name(value, limit=80):
    text = " ".join(str(value or "").split())[:limit]
    return text or None


def _form(value):
    """``"W,W,D,L"`` or ``"WWDL"`` -> ``"WWDL"``; None when absent or not made of W, D and L."""
    letters = re.sub(r"[\s,]", "", str(value or "")).upper()
    return letters[-10:] if letters and re.fullmatch(r"[WDL]{1,20}", letters) else None


def _group_name(value):
    text = _name(value, 40)
    if not text:
        return None
    match = _GROUP.match(text.upper())
    return "Group " + match.group(1) if match else text


def season_start_year(now):
    """Football seasons start in August (Europe/London)."""
    local = now.astimezone(LONDON)
    return local.year - (1 if local.month < 8 else 0)


def season_label(start_year, end_year=None):
    end = end_year if isinstance(end_year, int) and end_year > start_year else start_year + 1
    return "%d-%02d" % (start_year, end % 100)


def _row(position, name, short, participant_id, played, won, drawn, lost, goals_for, goals_against, goal_diff, points,
         form):
    """One table row, or None when a required value is missing or invalid (the row is dropped and the table is then
    never complete)."""
    values = (_int(position, 1), _name(name), _int(played), _int(won), _int(drawn), _int(lost), _int(goals_for),
              _int(goals_against), _int(points))
    if any(v is None for v in values):
        return None
    position, name, played, won, drawn, lost, goals_for, goals_against, points = values
    diff = goal_diff if isinstance(goal_diff, int) and not isinstance(goal_diff, bool) else goals_for - goals_against
    row = {"position": position, "participant": name, "played": played, "won": won, "drawn": drawn, "lost": lost,
           "goals_for": goals_for, "goals_against": goals_against, "goal_diff": diff, "points": points}
    if participant_id:
        row["participant_id"] = participant_id
    if _name(short, 40) and _name(short, 40) != name:
        row["participant_short"] = _name(short, 40)
    if _form(form):
        row["form"] = _form(form)
    return row


def _finish(competition_id, source, season, season_start, season_end, matchday, groups, observed_at, dropped):
    """Assemble the published document from decoded groups ``[(name, stage, [rows])]``."""
    spec = COMPETITIONS[competition_id]
    out_groups, total, contiguous = [], 0, True
    for name, stage, rows in groups:
        rows = sorted(rows, key=lambda r: (r["position"], r["participant"]))[:MAX_ROWS_PER_GROUP]
        if not rows:
            continue
        contiguous = contiguous and [r["position"] for r in rows] == list(range(1, len(rows) + 1))
        group = {"name": name, "rows": rows}
        if stage:
            group["stage"] = stage
        out_groups.append(group)
        total += len(rows)
    if not out_groups:
        raise ValueError("standings payload has no table rows")
    document = {"schema": SCHEMA, "competition_id": competition_id, "competition": spec["label"], "season": season[0],
                "season_start_year": season[1], "groups": out_groups, "teams": total,
                "expected_teams": spec["expected"],
                "table_complete": bool(total == spec["expected"] and contiguous and not dropped),
                "observed_at": observed_at, "source": source}
    if season_start:
        document["season_start"] = season_start
    if season_end:
        document["season_end"] = season_end
    if matchday is not None:
        document["matchday"] = matchday
    return document


def football_data_standings(data, competition_id, observed_at):
    """Decode a football-data.org ``/competitions/<code>/standings`` payload into a ``sli.standings/1`` document.

    Only the ``TOTAL`` tables are read (HOME and AWAY tables are ignored). Raises ValueError for anything that is not a
    standings payload for ``competition_id``."""
    spec = COMPETITIONS[competition_id]
    payload = json.loads(data)
    if not isinstance(payload, dict) or not isinstance(payload.get("standings"), list):
        raise ValueError("football-data.org standings payload missing or invalid")
    code = (payload.get("competition") or {}).get("code") if isinstance(payload.get("competition"), dict) else None
    if code and code != spec["fd"]:
        raise ValueError("football-data.org standings payload is for another competition")
    season = payload.get("season") if isinstance(payload.get("season"), dict) else {}
    start, end = str(season.get("startDate") or ""), str(season.get("endDate") or "")
    try:
        start_year = int(start[:4])
        end_year = int(end[:4]) if end else None
    except ValueError:
        start_year, end_year = None, None
    if start_year is None:
        filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else {}
        try:
            start_year, end_year = int(filters.get("season")), None
        except (TypeError, ValueError):
            raise ValueError("football-data.org standings payload has no season") from None
    groups, dropped = [], 0
    for block in payload["standings"]:
        if not isinstance(block, dict) or block.get("type") not in (None, "TOTAL") or not isinstance(block.get("table"), list):
            continue
        rows = []
        for item in block["table"]:
            team = item.get("team") if isinstance(item, dict) and isinstance(item.get("team"), dict) else {}
            team_id = _int(team.get("id"), 1)
            row = _row(item.get("position") if isinstance(item, dict) else None, team.get("name"), team.get("shortName"),
                       "fd:%d" % team_id if team_id else None, item.get("playedGames"), item.get("won"),
                       item.get("draw"), item.get("lost"), item.get("goalsFor"), item.get("goalsAgainst"),
                       item.get("goalDifference"), item.get("points"), item.get("form")) if isinstance(item, dict) else None
            if row:
                rows.append(row)
            else:
                dropped += 1
        stage = _name(block.get("stage"), 40)
        groups.append((_group_name(block.get("group")), stage, rows))
    return _finish(competition_id, "football_data", (season_label(start_year, end_year), start_year),
                   start[:10] if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", start) else None,
                   end[:10] if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", end) else None,
                   _int(season.get("currentMatchday"), 1), groups, observed_at, dropped)


def api_sports_standings(data, competition_id, observed_at, start_year):
    """Decode an API-Sports ``/standings?league=<id>&season=<year>`` payload (football product)."""
    spec = COMPETITIONS[competition_id]
    payload = json.loads(data)
    if not isinstance(payload, dict) or not isinstance(payload.get("response"), list) or not payload["response"]:
        raise ValueError("API-Sports standings payload missing or empty")
    league = payload["response"][0].get("league") if isinstance(payload["response"][0], dict) else None
    if not isinstance(league, dict) or not isinstance(league.get("standings"), list):
        raise ValueError("API-Sports standings payload missing or invalid")
    if league.get("id") not in (None, spec["as"]):
        raise ValueError("API-Sports standings payload is for another competition")
    tables = [t for t in league["standings"] if isinstance(t, list)]
    groups, dropped = [], 0
    for table in tables:
        rows, name = [], None
        for item in table:
            if not isinstance(item, dict):
                dropped += 1
                continue
            team = item.get("team") if isinstance(item.get("team"), dict) else {}
            totals = item.get("all") if isinstance(item.get("all"), dict) else {}
            goals = totals.get("goals") if isinstance(totals.get("goals"), dict) else {}
            team_id = _int(team.get("id"), 1)
            row = _row(item.get("rank"), team.get("name"), None, "as:%d" % team_id if team_id else None,
                       totals.get("played"), totals.get("win"), totals.get("draw"), totals.get("lose"),
                       goals.get("for"), goals.get("against"), item.get("goalsDiff"), item.get("points"),
                       item.get("form"))
            if row:
                rows.append(row)
                if len(tables) > 1 and name is None:
                    name = _group_name(item.get("group"))
            else:
                dropped += 1
        groups.append((name, None, rows))
    return _finish(competition_id, "api_sports", (season_label(start_year), start_year), None, None, None, groups,
                   observed_at, dropped)


def football_data_url(code):
    base = providers.SPORTS["football_data"][1].rsplit("/", 1)[0]
    return "%s/competitions/%s/standings" % (base, urllib.parse.quote(code, safe=""))


def api_sports_url(league_id, start_year):
    base = providers.SPORTS["api_sports"][1].rsplit("/", 1)[0]
    return "%s/standings?%s" % (base, urllib.parse.urlencode({"league": league_id, "season": start_year}))


def _stored(store):
    snap = store.snapshot("standings")
    data = (snap or {}).get("data") or {}
    comps = data.get("competitions") if isinstance(data.get("competitions"), dict) else {}
    tried = data.get("tried") if isinstance(data.get("tried"), dict) else {}
    return {k: v for k, v in comps.items() if k in COMPETITIONS and isinstance(v, dict)}, dict(tried)


def _london_day(stamp):
    try:
        return datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).astimezone(LONDON).date()
    except (ValueError, TypeError):
        return None


def _rank(document):
    return (bool(document.get("table_complete")), int(document.get("teams") or 0))


def collect(engine, conf, now=None):
    """Refresh due competitions; returns a short summary (also written as job ``standings``) or None when nothing ran.

    Due = not observed since the start of the current London day and not tried in the last ``RETRY_AFTER``. Never
    raises for provider trouble: a failure keeps the last good table (published until ``MAX_AGE_DAYS``)."""
    from .engine import LIVE_RESERVE, SAFE_ERRORS, QuotaExhausted, _sports_failure
    if not enabled(conf):
        return None
    store = engine.store
    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    today = now.astimezone(LONDON).date()
    comps, tried = _stored(store)
    due = []
    for cid in COMPETITIONS:
        doc = comps.get(cid)
        fresh = bool(doc) and _london_day(doc.get("observed_at")) == today and doc.get("table_complete")
        try:
            recent = now - datetime.fromisoformat(tried[cid]) < RETRY_AFTER
        except (KeyError, TypeError, ValueError):
            recent = False
        if not fresh and not recent:
            due.append(cid)
    fd_on = bool(conf.get("sports", {}).get("football_data") and conf.get("keys", {}).get("football_data"))
    as_on = bool(conf.get("standings_api_sports") is True and conf.get("keys", {}).get("api_sports"))
    if not due or not (fd_on or as_on):
        return None
    notes, calls, changed = [], 0, False

    def call(name, url, headers, budget, daily_limit, reserve):
        """One counted, paced provider call; raises QuotaExhausted before any network IO when a limit would break."""
        engine._check_sport_backoff(name)
        if store.usage().get(name, 0) >= daily_limit - reserve:
            raise QuotaExhausted("%s: remaining calls kept for scheduled refreshes" % name)
        try:
            store.increment("standings:" + name, budget)
        except RuntimeError:
            raise QuotaExhausted("%s: daily standings budget (%d) used" % (name, budget)) from None
        try:
            store.increment(name, daily_limit)
        except RuntimeError:
            raise QuotaExhausted("%s: daily call budget used" % name) from None
        engine._pace(name)
        return providers.fetch(url, headers, max_bytes=MAX_BYTES)

    def adopt(cid, document):
        """Keep the better table; an incomplete answer never replaces a complete one of the same season."""
        nonlocal changed
        old = comps.get(cid)
        if (old and old.get("season_start_year") == document["season_start_year"]
                and _rank(document) < _rank(old)):
            return False
        if document != old:
            comps[cid] = document
            changed = True
        return True

    def stop_on(exc, name, cid):
        """True when the whole source pass must stop."""
        reason = _sports_failure(exc)
        status = getattr(exc, "status", None)
        if status == 429 or reason == "Provider quota or rate limit":
            engine._defer_sport(name, exc)
            notes.append("%s: %s" % (name, reason))
            return True
        if status == 401 or reason == "Provider rejected the API key":
            notes.append("%s: %s" % (name, reason))
            return True
        if status in (403, 404) or reason in ("Provider plan or season restriction", "Provider rejected the requested scope"):
            store._put("standings_skip:%s:%s" % (name, cid), (now + timedelta(days=SKIP_DAYS)).isoformat(timespec="seconds"))
        notes.append("%s %s: %s" % (name, COMPETITIONS[cid]["fd"], reason))
        return False

    def skipped(name, cid):
        return (store._get("standings_skip:%s:%s" % (name, cid)) or "") > now.isoformat(timespec="seconds")

    fd_stopped = not fd_on
    for cid in due:
        if fd_stopped:
            break
        if skipped("football_data", cid):
            continue
        tried[cid] = now.isoformat(timespec="seconds")
        spec = COMPETITIONS[cid]
        try:
            raw = call("football_data", football_data_url(spec["fd"]), {"X-Auth-Token": conf["keys"]["football_data"]},
                       FD_DAILY_BUDGET, providers.SPORTS["football_data"][3], FD_RESERVE)
            calls += 1
            adopt(cid, football_data_standings(raw, cid, stamp))
        except QuotaExhausted as exc:
            notes.append(str(exc)[:80])
            fd_stopped = True
        except SAFE_ERRORS as exc:
            fd_stopped = stop_on(exc, "football_data", cid)
    if as_on:
        for cid in due:
            old = comps.get(cid)
            if (old and _london_day(old.get("observed_at")) == today and old.get("table_complete")) or skipped("api_sports", cid):
                continue
            spec = COMPETITIONS[cid]
            year = season_start_year(now)
            tried[cid] = now.isoformat(timespec="seconds")
            try:
                raw = call("api_sports", api_sports_url(spec["as"], year), {"x-apisports-key": conf["keys"]["api_sports"]},
                           AS_DAILY_BUDGET, providers.SPORTS["api_sports"][3], LIVE_RESERVE)
                calls += 1
                payload = json.loads(raw)
                error = providers.api_sports_error(payload) if isinstance(payload, dict) else None
                if error:
                    raise providers.ProviderRejected(error)
                adopt(cid, api_sports_standings(raw, cid, stamp, year))
            except QuotaExhausted as exc:
                notes.append(str(exc)[:80])
                break
            except SAFE_ERRORS as exc:
                if stop_on(exc, "api_sports", cid):
                    break
    store.save_snapshot("standings", {"competitions": comps, "tried": tried})
    complete = sum(bool(d.get("table_complete")) for d in comps.values())
    summary = "%d calls; %d of %d competitions held, %d complete" % (calls, len(comps), len(COMPETITIONS), complete)
    if notes:
        summary += "; " + "; ".join(notes[:3])
    store.job("standings", "ok" if not notes else "partial", summary)
    return summary


def documents(store, conf, now=None):
    """Documents to publish, in COMPETITIONS order: valid, enabled, and observed within ``MAX_AGE_DAYS``."""
    if not enabled(conf):
        return []
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    comps, _ = _stored(store)
    out = []
    for cid in COMPETITIONS:
        doc = comps.get(cid)
        if not isinstance(doc, dict) or doc.get("schema") != SCHEMA or doc.get("source") not in STANDINGS_SOURCES:
            continue
        observed = _z(doc.get("observed_at"))
        if not observed or not _STAMP.match(observed):
            continue
        if now - datetime.fromisoformat(observed.replace("Z", "+00:00")) > timedelta(days=MAX_AGE_DAYS):
            continue
        out.append(dict(doc, observed_at=observed))
    return out
