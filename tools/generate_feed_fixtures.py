"""Generate the golden sli/1 feed used as the B1G reader contract fixture.

Run from the repository root:
    PYTHONPATH=sportsliveinfo/src python tools/generate_feed_fixtures.py
Output: schemas/fixtures/sli-v1/ (byte-identical to what the publisher uploads,
so asset SHA-256 values in the manifest verify). tests/test_feed.py fails if
these files drift from the code; regenerate and copy them to the B1 repo's
reader test resources whenever the feed changes.
"""
import json
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
    ],
    "api_sports_rugby": [
        _e(id="api-sports-rugby:301", source_id="api_sports_rugby", sport="rugby", competition="Autumn Nations Series",
           competition_country="World", title="Scotland v Fiji", participants=["Scotland", "Fiji"], start_utc="2026-11-14T13:10:00+00:00",
           status_normalized="scheduled", venue="Murrayfield"),
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
    "thesportsdb": [
        _e(id="thesportsdb:6001", source_id="thesportsdb", sport="Darts", competition="Grand Slam of Darts", title="Luke Littler vs Luke Humphries",
           participants=["Luke Littler", "Luke Humphries"], start_utc="2026-11-14T19:00:00+00:00", status_normalized="scheduled"),
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


GUIDE["programmes"] += _schedule("skysportsmainevent.uk", NOW)
GUIDE_B = {"source_id": "epgtalk_uk",
           "channels": {"SkySpMainEvHD.uk": "UK - Sky Sports Main Event HD", "SkySpMainEv1.uk": "Sky Sports Main Event +1"},
           "programmes": _schedule("SkySpMainEvHD.uk", NOW) + _schedule("SkySpMainEv1.uk", NOW, offset_minutes=60)}


# Tiny public-domain dictionary sample (same shape as the iptv-org database files).
DICT_CHANNELS = """id,name,alt_names,network,owners,country,categories,is_nsfw,launched,closed,replaced_by,website
SkySportsMainEvent.uk,Sky Sports Main Event,,,Sky,UK,sports,FALSE,,,,
CanalPlusSport.fr,Canal+ Sport,,,Canal+,FR,sports,FALSE,1998-08-31,,,
beINSports1.qa,beIN Sports 1,,,beIN Media Group,QA,sports,FALSE,,,,
"""
DICT_FEEDS = """channel,id,name,alt_names,is_main,broadcast_area,timezones,languages,format
beINSports1.qa,France,France,,FALSE,c/FR,Europe/Paris,fra,1080i
"""


def build():
    """Return (manifest, files) for the fixed fixture day."""
    from sportsliveinfo import dictionary, feed, identity
    from sportsliveinfo.engine import Engine
    from sportsliveinfo.guide import analyze_guide
    from sportsliveinfo.storage import Store
    with tempfile.TemporaryDirectory() as tmp, patch("sportsliveinfo.storage.utcnow", return_value=STAMP):
        store = Store(Path(tmp) / "fixture.sqlite3")
        store.configure({"setup_complete": True, "schedule": ["04:00", "12:00", "17:00"],
                         "sports": {name: True for name in SNAPSHOTS} | {"jolpica": True},
                         "epg": {"farleyflex": True, "epgtalk_uk": True}, "publication_approvals": sorted(SNAPSHOTS),
                         "dictionary": {"iptvorg": True}})
        for name, events in SNAPSHOTS.items():
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
        return feed.build_feed(store, now=NOW)


MATCH_CASES = [
    ("farleyflex", "skysportsmainevent.uk", "Sky Sports Main Event"), ("farleyflex", "", "UK | SKY SPORTS MAIN EVENT FHD"),
    ("farleyflex", "", "Sky Sports Premier League UHD +1"), ("farleyflex", "", "Sky Sports+"), ("farleyflex", "", "Sky News"),
    ("farleyflex", "", "BBC 1"), ("farleyflex", "", "BBC One Scotland"), ("farleyflex", "", "BBC One +1"),
    ("mjh_sky_uk", "", "ITV1 HD"), ("mjh_sky_uk", "", "TNT Sports 2"), ("mjh_sky_uk", "", "TNT Sports 8"),
    ("epgshare_uk", "", "Premier Sports 1"), ("epgshare_uk", "", "Setanta Sports 1"), ("epgshare_uk", "", "Sky Sports Box Office"),
    ("fr_programmetv", "", "FR: Canal+ Sport HD"), ("fr_programmetv", "", "Canal+ Sport 360 +1"), ("fr_xmltv", "", "beIN Sports 4"),
    ("fr_xmltv", "", "L'Équipe"), ("epgshare_ie", "", "RTE2"), ("epgshare_us", "", "ESPN2"), ("iptvorg_foxtel_au", "", "Fox Footy"),
    ("epgshare_hk", "", "HK: Now Sports Premier League"), ("epgshare_my", "", "MYS | Astro Premier League FHD"),
    ("iptv_epg_ge", "", "Setanta Sports 2 HD"), ("epgtalk_sports", "", "Sky Sports Main Event"), ("unknown_source", "", "BBC One"),
]


def matching_cases():
    from sportsliveinfo.guide import canonical_channel, channel_families, normalized_name
    return {"schema": "sli.matching-cases/1",
            "note": "B1G SliChannelRegistry must return exactly these results for the same source market/url",
            "cases": [{"source_id": s, "epg_id": i, "name": n, "normalised": normalized_name(n),
                       "canonical_id": canonical_channel(s, i, n), "families": channel_families(n)} for s, i, n in MATCH_CASES]}


def write(out=OUT):
    from sportsliveinfo import feed
    manifest, files = build()
    shutil.rmtree(out, ignore_errors=True)
    for path, data in list(files.items()) + [("v1/manifest.json", feed._json(manifest))]:
        target = out / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (out / "matching-cases.json").write_text(json.dumps(matching_cases(), ensure_ascii=False, indent=1) + "\n")
    return manifest


if __name__ == "__main__":
    m = write()
    json.dump({"revision": m["revision"], "assets": len(m["assets"]), "coverage": m["coverage"]}, sys.stdout, indent=1)
    print()
