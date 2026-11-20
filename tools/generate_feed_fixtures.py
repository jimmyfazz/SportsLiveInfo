"""Generate the golden sli/1 feed used as the B1G reader contract fixture.

Run from the repository root:
    PYTHONPATH=sportsliveinfo/src python tools/generate_feed_fixtures.py
Output: schemas/fixtures/sli-v1/ (byte-identical to what the publisher uploads,
so asset SHA-256 values in the manifest verify). tests/test_feed.py fails if
these files drift from the code; regenerate and copy them to the B1 repo's
reader test resources whenever the feed changes.
"""
import json
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

NOW = datetime(2026, 11, 14, 14, 0, tzinfo=timezone.utc)
STAMP = NOW.isoformat(timespec="seconds")
OUT = Path(__file__).resolve().parents[1] / "schemas" / "fixtures" / "sli-v1"


def _e(**kw):
    row = {"start_precision": "scheduled", "broadcasts": [], "broadcast_verified": False, "participants": []}
    row.update(kw)
    return row


SNAPSHOTS = {
    "football_data": [
        _e(id="football-data:5001", source_id="football_data", sport="football", competition="Premier League", competition_code="fd:PL",
           competition_country="England", title="Arsenal FC v Manchester City FC", participants=["Arsenal FC", "Manchester City FC"],
           participants_short=["Arsenal", "Man City"], start_utc="2026-11-14T15:00:00+00:00", status_normalized="scheduled", round="12",
           venue="Emirates Stadium"),
        _e(id="football-data:5002", source_id="football_data", sport="football", competition="UEFA Champions League", competition_code="fd:CL",
           title="Liverpool FC v FC Barcelona", participants=["Liverpool FC", "FC Barcelona"], start_utc="2026-11-17T20:00:00+00:00",
           status_normalized="scheduled", stage="LEAGUE_STAGE"),
    ],
    "api_sports": [
        _e(id="api-sports:9001", source_id="api_sports", sport="football", competition="Premier League", competition_code="as:39",
           competition_country="England", title="Arsenal v Manchester City", participants=["Arsenal", "Manchester City"],
           start_utc="2026-11-14T15:00:00+00:00", status_normalized="scheduled"),
        _e(id="api-sports:9002", source_id="api_sports", sport="football", competition="Friendlies", competition_country="World",
           title="England v Japan", participants=["England", "Japan"], start_utc="2026-11-14T19:45:00+00:00", status_normalized="scheduled",
           venue="Wembley Stadium"),
        _e(id="api-sports:9003", source_id="api_sports", sport="football", competition="FA Cup", competition_country="England",
           title="Leeds United v Hull City", participants=["Leeds United", "Hull City"], start_utc="2026-11-15T12:30:00+00:00",
           status_normalized="scheduled", round="1st Round"),
        _e(id="api-sports:9004", source_id="api_sports", sport="football", competition="UEFA Europa League", competition_country="World",
           title="Aston Villa v AS Roma", participants=["Aston Villa", "AS Roma"], start_utc="2026-11-18T20:00:00+00:00", status_normalized="scheduled"),
        _e(id="api-sports:9005", source_id="api_sports", sport="football", competition="Friendlies", competition_country="World",
           title="England W v Spain W", participants=["England W", "Spain W"], start_utc="2026-11-15T17:00:00+00:00", status_normalized="scheduled"),
        # 1.6 tiers: an English league outside the named competitions is core; low-tier football elsewhere is extra.
        _e(id="api-sports:9006", source_id="api_sports", sport="football", competition="National League",
           competition_country="England", title="York City v Solihull Moors", participants=["York City", "Solihull Moors"],
           start_utc="2026-11-14T15:00:00+00:00", status_normalized="scheduled"),
        _e(id="api-sports:9007", source_id="api_sports", sport="football", competition="Liga Nacional",
           competition_country="Honduras", title="Olimpia v Motagua", participants=["Olimpia", "Motagua"],
           start_utc="2026-11-14T20:00:00+00:00", status_normalized="scheduled"),
        # Contract 1.6 history (§4.5): yesterday's match, last known status finished (read at the 04:00 discovery).
        _e(id="api-sports:9010", source_id="api_sports", sport="football", competition="Premier League", competition_code="as:39",
           competition_country="England", title="Everton v Fulham", participants=["Everton", "Fulham"],
           start_utc="2026-11-13T15:00:00+00:00", status="FT", status_normalized="finished",
           status_observed_at="2026-11-14T04:00:00+00:00"),
    ],
    "api_sports_rugby": [
        _e(id="api-sports-rugby:301", source_id="api_sports_rugby", sport="rugby", competition="Autumn Nations Series",
           competition_country="World", title="Scotland v Fiji", participants=["Scotland", "Fiji"], start_utc="2026-11-14T13:10:00+00:00",
           status_normalized="scheduled", venue="Murrayfield", status_observed_at="2026-11-14T12:00:00+00:00"),
    ],
    "api_sports_mma": [
        _e(id="api-sports-mma:77", source_id="api_sports_mma", sport="mma", competition="UFC 330", event_type="main_event",
           title="UFC 330 PPV: Champion v Challenger", participants=["Champion", "Challenger"], start_utc="2026-11-15T04:00:00+00:00",
           start_precision="estimated", status_normalized="scheduled", weight_class="Heavyweight"),
    ],
    "api_sports_basketball": [
        _e(id="api-sports-basketball:88", source_id="api_sports_basketball", sport="basketball", competition="NBA", competition_country="USA",
           title="Boston Celtics v Los Angeles Lakers", participants=["Boston Celtics", "Los Angeles Lakers"],
           start_utc="2026-11-15T00:30:00+00:00", status_normalized="scheduled"),
    ],
    # Metadata fixture (contract 4.3): an F1 weekend gets session_label and a stable weekend_id.
    "jolpica": [
        _e(id="f1:2026:22:practice1", source_id="jolpica", sport="motorsport", competition="Formula 1", event_type="FirstPractice",
           session="practice1", title="Las Vegas Grand Prix \u2014 Practice 1", start_utc="2026-11-20T00:30:00+00:00",
           status_normalized="scheduled", venue="Las Vegas Strip Circuit", country="USA"),
        _e(id="f1:2026:22:qualifying", source_id="jolpica", sport="motorsport", competition="Formula 1", event_type="Qualifying",
           session="qualifying", title="Las Vegas Grand Prix \u2014 Qualifying", start_utc="2026-11-21T04:00:00+00:00",
           status_normalized="scheduled", venue="Las Vegas Strip Circuit", country="USA"),
    ],
    "thesportsdb": [
        _e(id="thesportsdb:6001", source_id="thesportsdb", sport="Darts", competition="Grand Slam of Darts", title="Luke Littler vs Luke Humphries",
           participants=["Luke Littler", "Luke Humphries"], start_utc="2026-11-14T19:00:00+00:00", status_normalized="scheduled"),
        # §4.5 time precision: the provider gave only a date (stored at noon UTC); the feed publishes 00:00 Europe/London.
        _e(id="thesportsdb:6002", source_id="thesportsdb", sport="Darts", competition="Players Championship Finals",
           title="Players Championship Finals", start_utc="2026-11-16T12:00:00+00:00", start_precision="date_only",
           status_normalized="scheduled"),
    ],
    "jolpica": [
        _e(id="f1:2026:22:race", source_id="jolpica", sport="motorsport", competition="Formula 1", event_type="race", session="race",
           title="Las Vegas Grand Prix", start_utc="2026-11-21T06:00:00+00:00", venue="Las Vegas Strip Circuit", country="USA"),
    ],
    "openf1": [
        _e(id="openf1:9999", source_id="openf1", sport="motorsport", competition="Formula 1", event_type="Race", session="race",
           title="Formula 1 United States — Race", start_utc="2026-11-21T06:00:00+00:00", end_utc="2026-11-21T08:00:00+00:00"),
    ],
    "cricketdata": [
        _e(id="cricketdata:ash1:d%d" % d, source_id="cricketdata", sport="cricket", competition="The Ashes 2026-27", match_type="test",
           event_type="test", day_number=d, title="Australia v England — Day %d" % d, participants=["Australia", "England"],
           start_utc="2026-11-%02dT23:30:00+00:00" % (19 + d), start_precision="scheduled" if d == 1 else "not_before",
           status_normalized="scheduled", venue="Perth Stadium")
        for d in (1, 2)
    ],
}

GUIDE = {"source_id": "farleyflex", "channels": {"skysportsmainevent.uk": "Sky Sports Main Event"},
         "programmes": [{"channel_id": "skysportsmainevent.uk", "start_utc": "2026-11-14T14:30:00+00:00",
                         "end_utc": "2026-11-14T17:15:00+00:00", "title": "Live Premier League",
                         "subtitle": "Arsenal v Manchester City", "is_live": True, "is_repeat": False}]}

# A second guide naming the same service differently, plus its +1, so the
# identity graph (sli.identity/1) is exercised. Programme titles never leave
# the collector; only the resulting channel ids appear in the fixture.
_IDENTITY_TITLES = ["Soccer Saturday Preview", "Fantasy Football Club", "Monday Night Football Replay",
                    "Premier League Review", "Saturday Night Football", "Goals Reloaded Special",
                    "Rugby Union Weekly", "Cricket Masterclass Session", "Golf Highlights Tonight", "Boxing Countdown Show"]


def _schedule(channel_id, first_start, offset_minutes=0):
    rows = []
    for i, title in enumerate(_IDENTITY_TITLES):
        start = first_start.replace(hour=0) + __import__("datetime").timedelta(hours=18 + i, minutes=offset_minutes)
        rows.append({"channel_id": channel_id, "start_utc": start.isoformat(),
                     "end_utc": (start + __import__("datetime").timedelta(minutes=55)).isoformat(), "title": title})
    return rows


GUIDE["programmes"].append({"channel_id": "skysportsmainevent.uk", "start_utc": "2026-11-13T14:30:00+00:00",
                            "end_utc": "2026-11-13T17:15:00+00:00", "title": "Live Premier League",
                            "subtitle": "Everton v Fulham", "is_live": True, "is_repeat": False})
GUIDE["programmes"] += _schedule("skysportsmainevent.uk", NOW)
GUIDE_B = {"source_id": "epgtalk_uk",
           "channels": {"SkySpMainEvHD.uk": "UK - Sky Sports Main Event HD", "SkySpMainEv1.uk": "Sky Sports Main Event +1"},
           "programmes": _schedule("SkySpMainEvHD.uk", NOW) + _schedule("SkySpMainEv1.uk", NOW, offset_minutes=60)}
# 1.6: the same fixture in a second, independent guide family (EPGTalk / Schedules Direct vs farleyflex / mytelly) at the
# same slot makes the strict link "guide_corroborated" (still never broadcast_verified).
GUIDE_B["programmes"].append({"channel_id": "SkySpMainEvHD.uk", "start_utc": "2026-11-14T14:30:00+00:00",
                              "end_utc": "2026-11-14T17:15:00+00:00", "title": "Premier League Football",
                              "subtitle": "Arsenal v Manchester City", "is_live": True, "is_repeat": False})
# 1.6 live lane: the rugby was "scheduled" at the 12:00 refresh; the API-Sports live board saw it in play at 13:55.
LIVE_OBSERVATIONS = {"events": {"api-sports-rugby:301": {"status": "2H", "status_normalized": "live",
                                                         "status_observed_at": "2026-11-14T13:55:00+00:00"}}}


# sli/1.7 scores variant (schemas/fixtures/sli-v1-scores): the same feed with score_approvals set. The football fixture
# is reported by two sources that name the sides in opposite order (football-data first), so the golden file proves the
# score stays attached to participants[0]/[1] of the merged event; the rugby is live with a live score.
SCORE_APPROVALS = ["api_sports", "api_sports_rugby", "football_data"]
SCORE_SNAPSHOTS = {
    "football_data": [
        _e(id="football-data:5008", source_id="football_data", sport="football", competition="Premier League",
           competition_code="fd:PL", competition_country="England", title="Tottenham Hotspur FC v Chelsea FC",
           participants=["Tottenham Hotspur FC", "Chelsea FC"], start_utc="2026-11-14T11:30:00+00:00",
           status="FINISHED", status_normalized="finished", round="12", score={"home": 1, "away": 2, "period": "FT"}),
    ],
    "api_sports": [
        _e(id="api-sports:9008", source_id="api_sports", sport="football", competition="Premier League",
           competition_code="as:39", competition_country="England", title="Chelsea v Tottenham Hotspur",
           participants=["Chelsea", "Tottenham Hotspur"], start_utc="2026-11-14T11:30:00+00:00", status="FT",
           status_normalized="finished", score={"home": 2, "away": 1, "period": "FT"}),
    ],
}
SCORE_LIVE_OBSERVATIONS = {"events": {"api-sports-rugby:301": {
    "status": "2H", "status_normalized": "live", "status_observed_at": "2026-11-14T13:55:00+00:00",
    "score": {"home": 17, "away": 10, "period": "2H"}}}}


# Tiny public-domain dictionary sample (same shape as the iptv-org database files).
DICT_CHANNELS = """id,name,alt_names,network,owners,country,categories,is_nsfw,launched,closed,replaced_by,website
SkySportsMainEvent.uk,Sky Sports Main Event,,,Sky,UK,sports,FALSE,,,,
CanalPlusSport.fr,Canal+ Sport,,,Canal+,FR,sports,FALSE,1998-08-31,,,
beINSports1.qa,beIN Sports 1,,,beIN Media Group,QA,sports,FALSE,,,,
"""
DICT_FEEDS = """channel,id,name,alt_names,is_main,broadcast_area,timezones,languages,format
beINSports1.qa,France,France,,FALSE,c/FR,Europe/Paris,fra,1080i
"""


def build(scores=False):
    """Return (manifest, files) for the fixed fixture day; ``scores=True`` builds the sli/1.7 scores variant."""
    from sportsliveinfo import dictionary, feed, identity
    from sportsliveinfo.engine import Engine
    from sportsliveinfo.guide import analyze_guide
    from sportsliveinfo.storage import Store
    with tempfile.TemporaryDirectory() as tmp, patch("sportsliveinfo.storage.utcnow", return_value=STAMP):
        store = Store(Path(tmp) / "fixture.sqlite3")
        snapshots = {name: list(events) + (SCORE_SNAPSHOTS.get(name, []) if scores else [])
                     for name, events in SNAPSHOTS.items()}
        store.configure({"setup_complete": True, "schedule": ["04:00", "12:00", "17:00"],
                         "sports": {name: True for name in SNAPSHOTS} | {"jolpica": True},
                         "epg": {"farleyflex": True, "epgtalk_uk": True}, "publication_approvals": sorted(SNAPSHOTS),
                         "dictionary": {"iptvorg": True}, **({"score_approvals": SCORE_APPROVALS} if scores else {})})
        for name, events in snapshots.items():
            store.save_snapshot("sports:" + name, {"events": events, "source_id": name})
        store.save_snapshot("epg:farleyflex", GUIDE)
        store.save_snapshot("epg-quality:farleyflex", analyze_guide(GUIDE, now=NOW))
        store.save_snapshot("epg:epgtalk_uk", GUIDE_B)
        store.save_snapshot("epg-quality:epgtalk_uk", analyze_guide(GUIDE_B, now=NOW))
        document, report = identity.build_from_store(store, ["farleyflex", "epgtalk_uk"], now=NOW)
        store.save_snapshot("channel-identity", {"document": document, "report": report})
        store.save_snapshot("channel-dictionary", {"document": dictionary.build_document(DICT_CHANNELS, DICT_FEEDS),
                                                   "meta": {"channels": 3}})
        Engine(store)._materialize(now=NOW)
        store._put("live_observations", SCORE_LIVE_OBSERVATIONS if scores else LIVE_OBSERVATIONS)
        return feed.build_feed(store, now=NOW)


MATCH_CASES = [
    ("farleyflex", "skysportsmainevent.uk", "Sky Sports Main Event"), ("farleyflex", "", "UK | SKY SPORTS MAIN EVENT FHD"),
    ("farleyflex", "", "Sky Sports Premier League UHD +1"), ("farleyflex", "", "Sky Sports+"), ("farleyflex", "", "Sky News"),
    ("farleyflex", "", "BBC 1"), ("farleyflex", "", "BBC One Scotland"), ("farleyflex", "", "BBC One +1"),
    ("mjh_sky_uk", "", "ITV1 HD"), ("mjh_sky_uk", "", "TNT Sports 2"), ("mjh_sky_uk", "", "TNT Sports 8"), ("epgshare_us", "", "TNT Sports 8"),
    ("epgshare_uk", "", "Premier Sports 1"), ("epgshare_uk", "", "Setanta Sports 1"), ("epgshare_uk", "", "Sky Sports Box Office"),
    ("fr_programmetv", "", "FR: Canal+ Sport HD"), ("fr_programmetv", "", "Canal+ Sport 360 +1"), ("fr_xmltv", "", "beIN Sports 4"),
    ("fr_xmltv", "", "L'Équipe"), ("epgshare_ie", "", "RTE2"), ("epgshare_us", "", "ESPN2"), ("iptvorg_foxtel_au", "", "Fox Footy"),
    ("epgshare_hk", "", "HK: Now Sports Premier League"), ("epgshare_my", "", "MYS | Astro Premier League FHD"),
    ("iptv_epg_ge", "", "Setanta Sports 2 HD"), ("epgtalk_sports", "", "Sky Sports Main Event"), ("unknown_source", "", "BBC One"),
    # 0.3.18: a mixed guide's foreign id is never this market's service; NZ/AU sport guides.
    ("fr_mena_grab", "beINSports1.qa@MENA", "beIN SPORTS 1"), ("fr_mena_grab", "beINSPORTS1.fr", "FR - beIN SPORTS 1"),
    ("iptv_epg_gb", "RTEOne.ie", "RTE One"), ("mjh_skysportnow_nz", "341", "Sky Sport 1"),
    ("iptv_epg_de", "", "Sky Sport 1"), ("mjh_kayo_au", "53211", "Fox Sports 503"),
]

# Dictionary resolution cases (synthetic database, every 0.3.18 rule). B1G's resolver must give the same answers.
WORLD_CHANNELS = """id,name,alt_names,network,owners,country,categories,is_nsfw,launched,closed,replaced_by,website
ExampleNet.us,Example Net,,,,US,general,FALSE,,,,
ExampleKids.us,Example Kids,,,,US,kids,FALSE,,,,
SunExample.in,Sun Example,,,,IN,general,FALSE,,,,
AzteExample.mx,Azte Example,,,,MX,general,FALSE,,,,
CaribNews.tt,Carib News,,,,TT,news,FALSE,,,,
PeakNational.ng,Peak National,PNT,,,NG,news,FALSE,,,,
PeakTV.gh,PNT TV,,,,GH,news,FALSE,,,,
DesertOne.iq,Desert One,,,,IQ,general,FALSE,,,,
DesertOne.sa,Desert One,,,,SA,general,FALSE,,,,
Rodina1.ru,Rodina 1,Родина 1,,,RU,general,FALSE,,,,
Ellas1.gr,ELT1,ΕΛΤ1,,,GR,general,FALSE,,,,
OldBrand.tr,Old Brand,,,,TR,general,FALSE,,2024-02-12,NewBrand.tr,
NewBrand.tr,New Brand,,,,TR,general,FALSE,,,,
Gone.tr,Gone,,,,TR,general,FALSE,,2025-01-01,,
ExampleTV.de,Example TV,,,,DE,general,FALSE,,,,
"""
WORLD_FEEDS = """channel,id,name,alt_names,is_main,broadcast_area,timezones,languages,format
ExampleNet.us,KXMP,KXMP,,FALSE,ct/USXYZ,America/Chicago,eng,1080i
ExampleKids.us,KXMP,KXMP,,FALSE,ct/USXYZ,America/Chicago,eng,480i
ExampleNet.us,WXMQ,WXMQ-TV,,FALSE,ct/USABC,America/New_York,eng,1080i
"""
DICTIONARY_CASES = [
    ("US Example Net HD", "US"), ("US USA Example Net", "US"), ("IN-TM | Sun Example FHD", "IN"),
    ("(MX) (IZ) Azte Example", "LATAM"), ("Claro Azte Example", "LATAM"), ("Carib (FLOW) Carib News", "CARIB"),
    ("US Example Net 5 (KXMP) Springfield", "US"), ("US Example Kids (KXMP)", "US"), ("US Other 7 (KXMP) Town", "US"),
    ("US Example 9 (WXMQ-TV) Town", "US"), ("|NIGERIA| PNT", "AFRICA"), ("IRQ: Desert One HD", "MENA"),
    ("Desert One", "MENA"), ("RU | RODINA 1 HD", "RU"), ("GR | ELT 1", "GR"), ("TR | Old Brand HD", "TR"),
    ("TR | Gone", "TR"), ("DE ||VIP| Example TV HD DE", "DE"), ("Al Example", "AL"),
    ("(MX) (IZ) Azte Example HD", "US"),
]


SLOT_NOW = "2026-11-14T16:00:00+00:00"
SLOT_EVENTS = [
    {"id": "a", "participants": ["Northtown United", "Southport Rovers"], "start_utc": "2026-11-14T17:30:00+00:00"},
    {"id": "b", "participants": ["Lake City", "River Wanderers"], "start_utc": "2026-11-15T00:15:00+00:00"},
    {"id": "c1", "participants": ["Hill Hawks", "Bay Bears"], "start_utc": "2026-11-14T22:00:00+00:00"},
    {"id": "c2", "participants": ["Hill Hawks", "Bay Bears"], "start_utc": "2026-11-15T22:00:00+00:00"},
]
SLOT_CASES = [
    ("22. EPL 05 | Northtown United vs Southport Rovers (Sat 17:30 UK)", "Europe/London"),
    ("CA-DAZN 52: Premier League| Northtown United vs. Southport Rovers| Sat 14 Nov 12:30 PM", "America/New_York"),
    ("PL+ 017|  Northtown United v Southport Rovers - Player Cam (2026-11-14 17:30:00)", "Europe/London"),
    ("National League 8 | Northtown United vs Southport Rovers // UK Sat 14 Nov 5:30pm // ET Sat 14 Nov 12:30pm",
     "America/New_York"),
    ("NFL 01: 7:15PM River Wanderers @ Lake City", "America/New_York"),
    ("MLB 01 |  Lake City x River Wanderers start:2026-11-15 00:15:00 stop:2026-11-15 03:00:00", "America/New_York"),
    ("Fite TV 3 HD: TrillerTV-Example League 2025/26: Lake City vs River Wanderers - Sat,14 Nov 19:15 ET",
     "Europe/London"),
    ("Lake City vs River Wanderers (Lake) @ Nov 14 7:15 PM :NBA  04", "America/New_York"),
    ("PPV EVENT 09: Lake City vs. River Wanderers (11.14 7:15 PM ET)", "Europe/London"),
    ("NCAAF 02 Lake City vs River Wanderers 715PM", "America/New_York"),
    ("NHL 01: 5:00PM Bay Bears @ Hill Hawks", "America/New_York"),
    ("NHL 01 | Bay Bears @ Hill Hawks (Sat 22:00 UK)", "Europe/London"),
    ("EPL 05 | Northtown United vs Lake City (Sat 17:30 UK)", "Europe/London"),
    ("NO: V SPORT 1 HD", "Europe/London"),
    ("AL: X Premium 2 HD", "Europe/London"),
    ("L1 Pass 03 | PSG vs Troyes (Sat 20:05 UK)", "Europe/London"),
]


def slot_cases():
    from datetime import datetime
    from sportsliveinfo import event_slots
    now = datetime.fromisoformat(SLOT_NOW)
    cases = []
    for name, tz in SLOT_CASES:
        parsed = event_slots.parse_slot(name, now=now, default_tz=tz)
        found = event_slots.match_slot(parsed, SLOT_EVENTS, now=now) if parsed else None
        cases.append({"name": name, "default_tz": tz, "parsed": parsed, "event_id": found["id"] if found else None})
    return {"schema": "sli.slot-cases/1",
            "note": "B1G's event-slot parser must give these results for now=" + SLOT_NOW + " and the events listed",
            "now": SLOT_NOW, "events": SLOT_EVENTS, "cases": cases}


SLOT_TEAMS = ["Northtown United", "Southport Rovers", "Lake City", "River Wanderers", "Hill Hawks", "Bay Bears",
              "Eastfield Athletic", "Kingsbridge Town", "Saint Marys", "Harbour Albion", "Redwood FC", "Glenmoor",
              "Ashford County", "Northtown United Women", "Southport Rovers Women", "Ironvale", "Marsh Harriers",
              "Cobalt Kings", "Valley Vipers", "Summit Stags"]
SLOT_ZONES = [("UK", "Europe/London"), ("ET", "America/New_York"), ("CET", "Europe/Paris"), ("PT", "America/Los_Angeles"),
              ("GMT", "UTC"), ("", None)]


def slot_conformance_cases():
    """Thousands of generated event-slot channel names (fictional teams) with Python's parse and match.
    Several clocks ("now") and event sets, every time format the parser knows, swapped sides, wrong
    times, repeat fixtures on consecutive days and non-fixture channel names."""
    import random
    from datetime import datetime, timedelta, timezone
    from zoneinfo import ZoneInfo
    from sportsliveinfo import event_slots
    rng = random.Random(15112026)
    groups = []
    for now_text in ("2026-11-14T16:00:00+00:00", "2026-03-29T00:30:00+00:00", "2026-07-01T21:45:00+00:00",
                     "2026-12-31T23:10:00+00:00", "2026-10-25T00:50:00+00:00"):
        now = datetime.fromisoformat(now_text)
        events = []
        for index in range(14):
            a, b = rng.sample(SLOT_TEAMS, 2)
            start = now + timedelta(minutes=15 * rng.randint(-20, 150))
            events.append({"id": "e%d" % index, "participants": [a, b],
                           "start_utc": start.isoformat()})
            if rng.random() < 0.2:                       # same fixture tomorrow: clock-time-only stays unresolved
                events.append({"id": "e%dr" % index, "participants": [a, b],
                               "start_utc": (start + timedelta(days=1)).isoformat()})
        cases = []
        for _ in range(500):
            event = rng.choice(events)
            a, b = event["participants"]
            if rng.random() < 0.15:
                a, b = rng.sample(SLOT_TEAMS, 2)
            start = datetime.fromisoformat(event["start_utc"]) + timedelta(minutes=rng.choice([0, 0, 0, 0, 30, -90, 300]))
            label, zone_name = rng.choice(SLOT_ZONES)
            default_tz = rng.choice(["Europe/London", "America/New_York", "Europe/Paris"])
            local = start.astimezone(ZoneInfo(zone_name or default_tz))
            zone = (" " + label) if label else ""
            h12 = "%d:%02d %s" % ((local.hour % 12) or 12, local.minute, "AM" if local.hour < 12 else "PM")
            h12c = h12.replace(" ", "")
            h24 = "%02d:%02d" % (local.hour, local.minute)
            dow, mon = local.strftime("%a"), local.strftime("%b")
            when = rng.choice([
                "(%s %s%s)" % (dow, h24, zone), "%s %d %s %s" % (dow, local.day, mon, h12), "(%s)" % local.strftime("%Y-%m-%d %H:%M:%S"),
                "@ %s %d %s" % (mon, local.day, h12), "(%d.%d %s%s)" % (local.month, local.day, h12, zone), h12c,
                "%s,%d %s %s%s" % (dow, local.day, mon, h24, zone), "start:%s stop:%s" % (
                    start.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                    (start + timedelta(hours=2)).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")),
                "", "%d%02d%s" % ((local.hour % 12) or 12, local.minute, "PM" if local.hour >= 12 else "AM")])
            slot = rng.choice(["EPL %02d" % rng.randint(1, 20), "NFL %02d" % rng.randint(1, 16), "CA-DAZN %d" % rng.randint(1, 80),
                               "PL+ %03d" % rng.randint(1, 120), "L1 Pass %02d" % rng.randint(1, 9), "NBA  %02d" % rng.randint(1, 15),
                               "PPV EVENT %02d" % rng.randint(1, 20), "Fite TV %d HD" % rng.randint(1, 9), "GaaTv%02d" % rng.randint(1, 9)])
            sep = rng.choice([" vs ", " v ", " vs. ", " @ ", " x ", " V ", " versus "])
            comp = rng.choice(["", "Premier League", "Example Cup 2025/26", "Player Cam", "WTA Finals"])
            fixture = a + sep + b + rng.choice(["", "", " (Lake)", " [4K]", " HD", " - Player Cam"])
            shape = rng.randrange(8)
            if shape == 0:
                name = "%d. %s | %s %s" % (rng.randint(1, 99), slot, fixture, when)
            elif shape == 1:
                name = "%s: %s| %s| %s" % (slot, comp or "Example League", fixture, when)
            elif shape == 2:
                name = "%s: %s %s" % (slot, when, fixture)
            elif shape == 3:
                name = "%s %s :%s" % (fixture, when, slot)
            elif shape == 4:
                name = "%s: %s: %s - %s" % (slot, comp or "Example League", fixture, when)
            elif shape == 5:
                name = "%s | %s // UK %s" % (slot, fixture, when) if when else "%s %s" % (slot, fixture)
            elif shape == 6:
                name = "%s | %s - %s %s" % (slot, comp or "Example Cup", fixture, when)
            else:
                name = rng.choice(["NO: V SPORT 1 HD", "AL: X Premium 2 HD", "UK: Sky Sports Main Event", "CA V Montreal",
                                   "%s | Coming soon" % slot, "%s" % slot, "%s: %s" % (slot, when)])
            name = name.replace("  |", " |").strip()
            if rng.random() < 0.05:
                name = name.replace(" ", "\u00a0", 1)
            parsed = event_slots.parse_slot(name, now=now, default_tz=default_tz)
            found = event_slots.match_slot(parsed, events, now=now) if parsed else None
            cases.append({"name": name, "default_tz": default_tz, "parsed": parsed,
                          "event_id": found["id"] if found else None})
        groups.append({"now": now_text, "events": events, "cases": cases})
    return {"schema": "sli.slot-conformance/1",
            "note": "Generated event-slot names (fictional teams). B1G's port must give exactly these parses and links.",
            "groups": groups}


GUIDE_CHOICE_MAP = {
    "schema": "sli.guide-map/1",
    "service_aliases": {"BBCOne.uk": "gb.bbc.one", "BBCOne.uk@Wales": "gb.bbc.one.wales", "ITV1.uk": "gb.itv.one",
                        "SkySportsMainEvent.uk": "gb.sky.sports.main_event"},
    "guides": [
        {"source_id": "farleyflex", "market": "GB", "channels": [
            {"id": "bbcone.uk", "name": "BBC One", "service": "gb.bbc.one", "method": "registry", "programmes_7d": 120},
            {"id": "BBCOne.uk@Wales", "name": "BBC One Wales", "service": "gb.bbc.one.wales", "method": "registry",
             "programmes_7d": 118},
            {"id": "ITV1.uk", "name": "ITV1", "service": "gb.itv.one", "method": "registry", "programmes_7d": 95},
            {"id": "ITV1.uk@Granada", "name": "ITV1 Granada", "service": "ITV1.uk@Granada", "method": "dictionary",
             "programmes_7d": 90},
            {"id": "ITV1.uk@Plus1", "name": "ITV1 +1", "programmes_7d": 95},
            {"id": "SkySportsMainEvent.uk@HD", "name": "Sky Sports Main Event HD", "service": "gb.sky.sports.main_event",
             "method": "registry", "programmes_7d": 40},
            {"id": "DAZN1.uk@GermanyHD", "name": "DAZN 1", "programmes_7d": 50},
            {"id": "Empty.uk", "name": "Empty", "service": "Empty.uk", "method": "dictionary", "programmes_7d": 0}]},
        {"source_id": "epgtalk_uk", "market": "GB", "channels": [
            {"id": "BBCOne.uk@HD", "name": "BBC One HD", "programmes_7d": 150},
            {"id": "BBCOne.uk@WalesHD", "name": "BBC One Wales HD", "programmes_7d": 100},
            {"id": "BBCOne.uk@LondonEast", "name": "BBC One London East", "programmes_7d": 80},
            {"id": "BBCOne.uk@London", "name": "BBC One London", "programmes_7d": 60},
            {"id": "SkySpMainEvHD.uk", "name": "Sky Sports Main Event", "service": "gb.sky.sports.main_event",
             "method": "registry", "programmes_7d": 40},
            {"id": "DAZN1.uk", "name": "DAZN 1", "service": "DAZN1.uk", "method": "dictionary", "programmes_7d": 20}]},
        {"source_id": "fr_xmltv", "market": "FR", "channels": [
            {"id": "France3.fr@Alsace", "name": "France 3 Alsace", "service": "France3.fr@Alsace",
             "method": "dictionary", "programmes_7d": 70},
            {"id": "France3.fr", "name": "France 3", "service": "France3.fr", "method": "dictionary", "programmes_7d": 70},
            {"id": "beINSports1.qa@France", "name": "beIN Sports 1", "programmes_7d": 60},
            {"id": "beINSports1.qa@MENA", "name": "beIN Sports 1 MENA", "programmes_7d": 60}]},
        {"source_id": "iptv_epg_de", "market": "DE", "channels": [
            {"id": "DAZN1.de", "name": "DAZN 1", "service": "DAZN1.de", "method": "dictionary", "programmes_7d": 30},
            {"id": "SkySportsMainEvent.uk@GermanyHD", "name": "Sky Sports Main Event", "programmes_7d": 30}]},
    ],
}


def guide_choice_cases():
    """Every combination of identity, provider tvg-id, market and enabled guides over a guide map built to
    hold the hard cases (regions, +1, foreign feeds, aliases, empty guides), with Python's choice."""
    from sportsliveinfo import coverage
    identities = [None, "gb.bbc.one", "BBCOne.uk", "BBCOne.uk@Wales", "BBCOne.uk@London", "gb.bbc.one.wales",
                  "ITV1.uk", "ITV1.uk@Granada", "gb.itv.one", "SkySportsMainEvent.uk", "gb.sky.sports.main_event",
                  "France3.fr", "France3.fr@Alsace", "beINSports1.qa", "beINSports1.qa@France", "DAZN1.uk",
                  "DAZN1.de", "Empty.uk", "Unknown.uk", "ITV1.uk@Plus1"]
    cases = []
    for identity in identities:
        for tvg_id in (None, "bbcone.uk", "ITV1.uk@Plus1", "Empty.uk", "nothere"):
            for market in (None, "GB", "FR", "DE"):
                for enabled in (None, ["farleyflex"], ["epgtalk_uk", "fr_xmltv"]):
                    how, hits = coverage.choose_guide_channels(GUIDE_CHOICE_MAP, identity, tvg_id=tvg_id,
                                                               market=market, enabled=enabled)
                    cases.append({"identity": identity, "tvg_id": tvg_id, "market": market, "enabled": enabled,
                                  "how": how, "hits": [list(hit) for hit in hits]})
    return {"schema": "sli.guide-choice-cases/1",
            "note": "B1G's guide chooser must give exactly these results for guide_map (coverage.choose_guide_channels)",
            "guide_map": GUIDE_CHOICE_MAP, "cases": cases}


RECONCILE_CATEGORIES = {
    "GB": ["UK | ENTERTAINMENT", "UK| SPORTS", "UK | KIDS", "UK: MOVIES", "|UK| NEWS", "United Kingdom"],
    "IE": ["IE | IRELAND", "Irish TV"], "FR": ["FR| GENERAL", "FRANCE SPORT", "|FR| CINEMA", "SK: France"],
    "DE": ["DE | Deutschland", "GERMANY SPORT"], "ES": ["ES | ESPAÑA", "Spain"], "IT": ["IT | ITALIA", "Italy Sport"],
    "NL": ["NL | Nederland"], "PT": ["PT | PORTUGAL"], "PL": ["PL | POLSKA"], "SE": ["Nordic | Sweden", "SE | SVERIGE"],
    "TR": ["TR | TÜRKIYE", "Turkish"], "US": ["USA | ENTERTAINMENT", "US: SPORTS"], "CA": ["CA | Canada"],
    "MENA": ["AR | Gulf", "Arabic | MBC"], "RU": ["RU | Russia"], "GR": ["GR | Greece"], "IN": ["IN | Hindi"],
}
RECONCILE_OTHER = [("VOD Movies", "Some Film (2024)"), ("Radio UK", "Radio: Heart"), ("24/7 Cartoons", "24/7 Classic"),
                   ("XXX ADULT", "Adult One"), ("Series VOD", "Some Series S01"), ("LIVE | DAZN CA", "DAZN CA 05"),
                   ("PPV EVENTS", "PPV EVENT 09: Lake City vs. River Wanderers (11.14 7:15 PM ET)"),
                   ("PPV EVENTS", "EPL 05 | Northtown United vs Southport Rovers (Sat 17:30 UK)"),
                   ("PPV EVENTS", "NFL 01: 7:15PM River Wanderers @ Lake City"), ("PPV EVENTS", "Event 12"),
                   ("SPORTS EVENTS", "NHL 01 | Bay Bears @ Hill Hawks (Sat 22:00 UK)"), ("", "Unknown Channel"),
                   ("MISC", "Channel 5 HD"), ("ENTERTAINMENT", "Some Network")]


CLASSIFIER_CATEGORIES = [
    "UK | ENTERTAINMENT", "UK| SPORTS", "|UK| KIDS", "UK: DOCUMENTARIES", "UK MUSIC", "England", "Scotland HD",
    "Wales", "British Classics", "IE | IRELAND", "FR| GENERAL", "|FR| CINEMA", "SK: France", "Français", "DE | Deutschland",
    "Deutsch HD", "AT | Austria", "Swiss TV", "ES | ESPAÑA", "España Deportes", "IT | ITALIA", "NL | Nederland", "Dutch",
    "Belgium", "PT | PORTUGAL", "PL | POLSKA", "GR | Greece", "Nordic | Sweden", "NO | Norway", "Danish", "Suomi",
    "RU | Russia", "Ukraine", "TR | TÜRKIYE", "Türk Sinema", "AL | Albania", "Kosova", "RO | Romania", "Bulgaria",
    "HU | Hungary", "CZ/SK", "Croatia", "Serbia", "Slovenia", "Bosnia", "Macedonia", "CA | Canada", "Mexico",
    "Latino", "Argentina", "Caribbean", "AR | Gulf", "Arabic | MBC", "Middle East", "Egypt", "Kurdistan", "Iran",
    "Persian", "IN | Hindi", "Tamil", "Punjabi", "Pakistan", "Nepal", "Vietnam", "Pinoy TV", "Africa", "DSTV",
    "Australia", "Kayo Sports", "New Zealand", "USA | ENTERTAINMENT", "US: LOCAL", "American Sports", "SW | Sport",
    "UKR | TV", "TRK | Ulusal", "INR | Movies", "NPL | News", "AF | Movies", "CARIB | Local", "MX | Deportes",
    "VOD Movies", "Movies VOD", "Series", "TV Series", "Radio UK", "XXX ADULT", "+18 Night", "24/7 Cartoons",
    "PPV EVENTS", "LIVE | NFL", "Fite TV", "FloSports", "ESPN+ Events", "Peacock Events", "Paramount+", "TSN+",
    "DAZN CA", "Tennis Channel", "beIN MAX", "PL+ UK", "Ligue 1 Pass", "TrillerTV", "Now HK", "Kayo",
    "SuperLeague+", "Stan Sport", "OneFootball", "Events", "", "MISC", "GENERAL", "Channels VOD"]
CLASSIFIER_NAMES = [
    "Sky Sports Main Event", "BBC One HD", "CNN International", "Euronews", "BFM TV", "France 24", "DW", "Al Jazeera",
    "Nick Jr", "Disney Junior", "Cartoon Network", "Baby TV", "CBeebies", "Gulli", "Boomerang", "Cine+ Premier",
    "HBO Max", "Sky Cinema Action", "Film4", "Kino Polska", "AMC", "TCM", "MTV Hits", "VH1", "Stingray Djazz",
    "Trace Urban", "Kiss FM", "Discovery Channel", "Nat Geo Wild", "History", "Animal Planet", "Viasat Explore",
    "Planete+", "Crime + Investigation", "Daystar", "TBN", "EWTN", "Peace TV", "Food Network", "HGTV", "TLC",
    "QVC", "Travel Channel", "Eurosport 1", "DAZN 2", "beIN Sports 3", "Arena Sport 1", "Setanta Sports",
    "SuperSport Football", "ESPN 2", "TSN 4", "NBA TV", "NFL Network", "Premier League TV", "Golf Channel",
    "Racing TV", "UFC Fight Pass", "Some Network", "TV 24", "Info Kanal", "Haber Turk", "+18 Night Show",
    "Radio: Heart", "24/7 The Simpsons", "Event 12", "PPV Event 3", "Live Event Only", "Events Only Feed",
    "UK: ITV 1", "DE | ZDF", "FR: TF1", "|AR| MBC 1", "IN-TM | Sun TV", "USA: FOX 5 New York"]


def reconcile_cases():
    """The TV's per-channel result (coverage.reconcile_channel) for thousands of provider-style channels over the
    public conformance dictionary and a synthetic guide map built from it. No owner channel list is used."""
    import random
    from datetime import datetime
    from sportsliveinfo import coverage, dictionary
    rng = random.Random(16112026)
    document = json.loads((CONFORMANCE_DIR / "dictionary.json").read_text(encoding="utf-8"))
    resolver = dictionary.Resolver(document)
    channels = sorted(resolver.channels)
    guides = {"guide_a": ("GB", []), "guide_b": ("FR", []), "guide_c": ("DE", []), "guide_d": (None, [])}
    aliases = {}
    for channel_id in channels:
        if rng.random() < 0.45:
            continue
        channel = resolver.channels[channel_id]
        source = rng.choice(sorted(guides))
        feeds = [f.get("id") for f in channel.get("feeds", []) if f.get("id")]
        variants = [channel_id, channel_id + "@HD"] + [channel_id + "@" + f for f in feeds[:3]]
        if rng.random() < 0.1:
            variants.append(channel_id + "@Plus1")
        if rng.random() < 0.05:
            variants.append(channel_id + "@GermanyHD")
        for gid in rng.sample(variants, min(len(variants), rng.randint(1, 3))):
            row = {"id": gid, "name": channel.get("name", ""), "programmes_7d": rng.choice([0, 3, 40, 120, 160])}
            if rng.random() < 0.6 and "@Plus1" not in gid:
                service = coverage.identity_from_id(gid, resolver)
                if service:
                    row.update(service=service, method="dictionary")
            guides[source][1].append(row)
        if rng.random() < 0.03:
            sli_id = "zz.service." + channel_id.lower().replace(".", "_")
            aliases[channel_id] = sli_id
            guides["guide_a"][1].append({"id": "reg-" + channel_id.lower(), "name": channel.get("name", ""),
                                         "service": sli_id, "method": "registry", "programmes_7d": 90})
    guide_map = {"schema": "sli.guide-map/1", "service_aliases": dict(sorted(aliases.items())),
                 "guides": [{"source_id": source, "market": market, "channels": rows}
                            for source, (market, rows) in sorted(guides.items())]}
    guide_ids = [c["id"] for g in guide_map["guides"] for c in g["channels"]]
    conformance = dictionary_conformance_cases()["cases"]
    entries = []
    for case in rng.sample(conformance, 5000):
        categories = RECONCILE_CATEGORIES.get(case["market"])
        if not categories:
            continue
        entry = {"category": rng.choice(categories), "name": case["name"], "tvg_id": ""}
        roll = rng.random()
        if roll < 0.15:
            entry["tvg_id"] = rng.choice(guide_ids)
        elif roll < 0.25:
            entry["tvg_id"] = rng.choice(channels) + rng.choice(["", "@HD", "@SD", "@Plus1", "@WalesHD"])
        elif roll < 0.28:
            entry["tvg_id"] = "provider-%d" % rng.randint(1, 999)
        entries.append(entry)
    entries += [{"category": c, "name": n, "tvg_id": ""} for c, n in RECONCILE_OTHER]
    grid = [(c, n) for c in CLASSIFIER_CATEGORIES for n in CLASSIFIER_NAMES]
    entries += [{"category": c, "name": n, "tvg_id": ""} for c, n in rng.sample(grid, 2500)]
    now = datetime.fromisoformat(SLOT_NOW)
    cases = []
    for entry in entries:
        for enabled in ([None, ["guide_a", "guide_b"]] if rng.random() < 0.2 else [None]):
            row = coverage.reconcile_channel(entry, resolver=resolver, guide_map=guide_map, enabled=enabled,
                                             now=now, events=SLOT_EVENTS)
            cases.append({"entry": entry, "enabled": enabled, "row": row})
    return {"schema": "sli.reconcile-cases/1",
            "note": "coverage.reconcile_channel over dictionary-conformance/dictionary.json, guide_map, now and events; "
                    "B1G's reconciler must give exactly these rows",
            "now": SLOT_NOW, "events": SLOT_EVENTS, "guide_map": guide_map, "cases": cases}


STANDALONE_DIR = OUT / "standalone"


def dictionary_rules():
    """The dictionary's rule tables without channels, plus the scope definitions: what B1G bundles to build the
    dictionary itself from the iptv-org database when the SportsLiveInfo feed is unavailable."""
    from sportsliveinfo import dictionary
    document = dictionary.build_document("id,name,country\n", "channel,id,name\n")
    document.pop("channels")
    document.update(schema="sli.dictionary-rules/1", europe=sorted(dictionary.EUROPE),
                    region_definitions={key: {"label": label, "countries": sorted(countries.split())}
                                        for key, (label, countries) in sorted(dictionary.REGIONS.items())},
                    sources={"channels": dictionary.CHANNELS_URL, "feeds": dictionary.FEEDS_URL,
                             "regions": dictionary.REGIONS_URL})
    return document


def standalone_cases():
    """build_document over a fixed public slice of the iptv-org database (standalone/*.csv), for B1G's own build."""
    from sportsliveinfo import dictionary
    read = lambda name: (STANDALONE_DIR / name).read_text(encoding="utf-8")
    cases = []
    for regions in ([], sorted(dictionary.REGIONS)[:2], sorted(dictionary.REGIONS)):
        document = dictionary.build_document(read("channels.csv"), read("feeds.csv"), read("regions.csv"), regions)
        cases.append({"regions": regions, "channels": document["channels"]})
    return {"schema": "sli.standalone-cases/1",
            "note": "dictionary.build_document over standalone/channels.csv, feeds.csv and regions.csv",
            "cases": cases}


CONFORMANCE_DIR = OUT / "dictionary-conformance"


def dictionary_conformance_cases():
    """Thousands of provider-style names built from a fixed public subset of the dictionary
    (`dictionary-conformance/dictionary.json`, iptv-org data, public domain) with Python's answers.
    B1G's port of the resolver must give exactly these results. No owner channel list is used."""
    import random
    from sportsliveinfo import dictionary
    document = json.loads((CONFORMANCE_DIR / "dictionary.json").read_text(encoding="utf-8"))
    resolver = dictionary.Resolver(document)
    home_market = {}
    for market, countries in document["market_countries"].items():
        for country in countries[:1]:
            home_market.setdefault(country, market)
    code_of = {market: sorted(codes)[0] for market, codes in document["bare_market_codes"].items()}
    rng = random.Random(14112026)
    names = []
    for channel in sorted(document["channels"], key=lambda c: c["id"]):
        market = home_market.get(channel["country"])
        if not market:
            continue
        code = code_of.get(market, market)
        name = channel["name"]
        variants = [name, "%s | %s HD" % (code, name), "|%s| %s FHD" % (code, name), "%s: %s" % (code, name),
                    name.upper() + " 4K", name + " +1", name + " (UHD/4K)", name + " HEVC"]
        variants += [alt for alt in channel.get("alt_names", [])[:2]]
        variants += ["%s %s" % (name, feed["name"]) for feed in channel.get("feeds", [])[:2] if feed.get("name")]
        if re.search(r"\bsports?\b", name, re.I):
            variants.append(re.sub(r"(?i)\bsports\b", "Sport", name) if re.search(r"(?i)\bsports\b", name)
                            else re.sub(r"(?i)\bsport\b", "Sports", name))
        if re.search(r"\s2$", name):
            variants.append(name[:-1] + "1")
        if any(ord(ch) > 127 for ch in name):
            try:
                variants.append(name.encode("utf-8").decode("latin-1"))       # mis-encoded export
            except UnicodeDecodeError:
                pass
        if "&" in name:
            variants.append(name.replace("&", "&amp;"))
        if market == "DE":
            variants.append("DE ||VIP| %s HD DE" % name)
        if market in ("US", "LATAM") and channel["country"] == "MX":
            variants.append("(MX) (IZ) " + name)
        for feed in channel.get("feeds", []):
            if re.fullmatch(r"[KW][A-Z]{2,3}(?:-?(?:TV|DT|CD|LD))?", feed.get("name", "")):
                variants.append("US %s 5 (%s) City" % (name, feed["name"]))
                break
        rng.shuffle(variants)
        for variant in variants[:6]:
            names.append((variant, market))
    names += [("|NIGERIA| AIT", "AFRICA"), ("IRQ: Al Iraqia HD", "MENA"), ("Desert One", "MENA"),
              ("Carib (FLOW) CNC3", "CARIB"), ("Claro HBO Plus", "LATAM"), ("Al Jazeera", "AL"),
              ("TRK | beINSport 1 HD", "TR"), ("PL | Eleven Sports 1 FHD", "PL"), ("BG | Diema Sport 1", "BG"),
              ("IT| Sky Sports UNO", "IT"), ("GR | NOVA SPORT 1", "GR"), ("SW | VIASAT SPORT PREMIUM HD", "SE")]
    cases, seen = [], set()
    for name, market in names:
        if (name, market) in seen:
            continue
        seen.add((name, market))
        hit = resolver.resolve(name, market)
        cases.append({"name": name, "market": market,
                      "ids": [list(i) for i in hit["ids"]] if hit else [], "method": hit["method"] if hit else None,
                      "confidence": hit["confidence"] if hit else None,
                      "identity": dictionary.service_identity(hit)})
    return {"schema": "sli.dictionary-conformance/1",
            "note": "B1G's dictionary resolver must return exactly these results for dictionary.json in this folder",
            "cases": cases}


def dictionary_cases():
    from sportsliveinfo import dictionary
    from sportsliveinfo.guide import market_key
    document = dictionary.build_document(WORLD_CHANNELS, WORLD_FEEDS, "", list(dictionary.REGIONS))
    resolver = dictionary.Resolver(document)
    cases = []
    for name, market in DICTIONARY_CASES:
        hit = resolver.resolve(name, market)
        cases.append({"name": name, "market": market, "market_key": market_key(name, market),
                      "ids": [list(i) for i in hit["ids"]] if hit else [], "method": hit["method"] if hit else None,
                      "confidence": hit["confidence"] if hit else None, "identity": dictionary.service_identity(hit)})
    return {"schema": "sli.dictionary-cases/1",
            "note": "B1G's dictionary resolver must return exactly these results for `document` (built from the "
                    "synthetic channels/feeds CSV in tools/generate_feed_fixtures.py, all optional regions on)",
            "document": document, "cases": cases}


def matching_cases():
    from sportsliveinfo.guide import canonical_channel, channel_families, normalized_name
    return {"schema": "sli.matching-cases/1",
            "note": "B1G SliChannelRegistry must return exactly these results for the same source market/url",
            "cases": [{"source_id": s, "epg_id": i, "name": n, "normalised": normalized_name(n),
                       "canonical_id": canonical_channel(s, i, n), "families": channel_families(n)} for s, i, n in MATCH_CASES]}


def write(out=OUT):
    from sportsliveinfo import feed
    manifest, files = build()
    fixed = {}                                   # fixed inputs, not generated: kept across the rebuild
    for path in [out / "dictionary-conformance" / "dictionary.json"] + [out / "standalone" / n for n in
                                                                          ("channels.csv", "feeds.csv", "regions.csv")]:
        if path.is_file():
            fixed[path] = path.read_bytes()
    shutil.rmtree(out, ignore_errors=True)
    for path, data in fixed.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    for path, data in list(files.items()) + [("v1/manifest.json", feed._json(manifest))]:
        target = out / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (out / "matching-cases.json").write_text(json.dumps(matching_cases(), ensure_ascii=False, indent=1) + "\n")
    (out / "dictionary-cases.json").write_text(json.dumps(dictionary_cases(), ensure_ascii=False, indent=1) + "\n")
    (out / "slot-cases.json").write_text(json.dumps(slot_cases(), ensure_ascii=False, indent=1) + "\n")
    (out / "guide-choice-cases.json").write_text(json.dumps(guide_choice_cases(), ensure_ascii=False, indent=1) + "\n")
    (out / "standalone" / "expected.json").write_text(
        json.dumps(standalone_cases(), ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    (out / "standalone" / "dictionary-rules.json").write_text(
        json.dumps(dictionary_rules(), ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (out / "slot-conformance.json").write_text(
        json.dumps(slot_conformance_cases(), ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    (out / "dictionary-conformance").mkdir(exist_ok=True)
    (out / "dictionary-conformance" / "reconcile-cases.json").write_text(
        json.dumps(reconcile_cases(), ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    (out / "dictionary-conformance" / "cases.json").write_text(
        json.dumps(dictionary_conformance_cases(), ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return manifest


SCORES_OUT = OUT.parent / "sli-v1-scores"


def write_scores(out=SCORES_OUT):
    """The sli/1.7 scores variant: feed files only (manifest and assets), no conformance side files."""
    from sportsliveinfo import feed
    manifest, files = build(scores=True)
    shutil.rmtree(out, ignore_errors=True)
    for path, data in list(files.items()) + [("v1/manifest.json", feed._json(manifest))]:
        target = out / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return manifest


if __name__ == "__main__":
    write_scores()
    m = write()
    json.dump({"revision": m["revision"], "assets": len(m["assets"]), "coverage": m["coverage"]}, sys.stdout, indent=1)
    print()
