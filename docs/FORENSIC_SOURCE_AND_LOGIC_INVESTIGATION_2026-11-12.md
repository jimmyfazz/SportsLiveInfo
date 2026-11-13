# SportsLiveInfo — Forensic Source Material and Implementation Logic Investigation

> **Historical audit / receipt — reviewed 12 November 2026.** Preserved against its stated original revision. Findings, branch/merge positions, provider claims and pass counts below are historical, not freshly verified current facts. Current source is v0.3.0; the combined review attempted 86 tests (81 passed, five errors, three of those environment-blocked). Use CURRENT_STATUS for resolved/remaining work; no new live source, licence or device verification occurred.
> **Repository roles:** [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is the public App source and installation repository; [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is PUBLIC daily data only. [Current status and evidence](CURRENT_STATUS.md).

**Dated:** 12 November 2026  
**Companion to:** `SOURCES_AND_IMPROVEMENTS_AUDIT_2026-11-12.md`  
**Purpose:** Deep, line-by-line forensic trace of every source from fetch to storage to materialisation; identification of every logic gap in each pipeline stage; research into new and improved source candidates with specific integration blueprints.


> **Corrections — 12 Nov 2026 (v0.3.0 follow-up, verified by web search and by reading the code):** this document was written while live source fetches were blocked, and several statements were wrong. (1) football-data.org's free plan **includes** the UEFA Champions League (`CL`); the free 12 are PL, ELC, CL, BL1, SA, PD, FL1, DED, PPL, BSA, WC, EC. There is no `EL1`/`CLI` in that list. (2) API-Sports has **no cricket API**; its non-football sports use `v1.<sport>.api-sports.io/games`, not `v3.rugby`. (3) The earlier in-process locking assessment did not establish cross-connection atomicity. Current `Store.increment()` uses SQLite `BEGIN IMMEDIATE`; the concurrent independent-Store regression passes in the current source review. An instance RLock alone is not evidence of multi-process safety. (4) API-Sports fixture-by-date responses are not routinely split into 10-row pages; the paging guard is defensive, not a high-severity defect. (5) The CI workflow YAML is valid; the PR #2 "404 BlobNotFound" is a GitHub-side log retrieval failure, not a workflow fault. (6) Response shapes labelled "traced from actual API response" or "based on published docs" were written from documentation knowledge, not live calls; the SportsAPI.app shape is hypothetical. The SQLite schema quoted in §4.1 does not match `storage.py` (actual tables: `kv(name,data)`, `jobs(time,provider,state,details)`). See `SOURCE_EXPANSION_SPORTS_TAXONOMY_AND_B1G_LINEUP_2026-11-12.md` for current, implemented state.

---

## Part 1: Complete Data Flow Trace

This section traces every byte from initial HTTP request through to the final `sports` or `epg` materialised snapshot. Every line cited is from the current codebase.

### 1.1 The Fetch Pipeline (`providers.fetch`)

```
engine.py:_collect_sport()
  → store.increment(name, limit)          # Reserve quota BEFORE network
  → providers.fetch(url, headers, max)    # HTTP GET with 20s timeout
      → verify_url(url)                   # Allowlist + HTTPS + no-cred check
      → urllib.request.Request()          # Custom User-Agent; no cookie jar
      → opener.open(timeout=20)           # RedirectGuard validates redirects
      → response.read(max_bytes + 1)      # Over-read by 1 to detect truncation
      → returns raw bytes
  → providers.{sport}_events(raw_bytes)   # Format-specific decoder
  → store.save_snapshot("sports:name")   # Atomically replace last-good
```

**What happens at each failure point:**

| Point | Current behaviour | Gap |
|---|---|---|
| `verify_url` raises | RuntimeError propagates to `_collect_sport` catch block | Correct; quota already reserved |
| HTTP 4xx/5xx | `RuntimeError("HTTP %d")` caught in sport handler | 429 (rate limit) is treated same as 404 — no Retry-After extraction |
| HTTP redirect to non-approved host | `RedirectGuard.redirect_request` calls `verify_url` → raises | Correct |
| `response.read` returns >max_bytes | `ValueError("exceeded size limit")` | Correct; truncation detection works |
| `gzip.GzipFile` decompresses >65 MB | `ValueError("past safety limit")` | Correct for EPG; sports adapters don't use gzip |
| DTD/ENTITY in XMLTV | `ValueError("entities not allowed")` | Correct |
| JSON `json.loads` fails | `json.JSONDecodeError` caught in handler | Correct |
| Timeout (20s) | `TimeoutError` or `URLError` → `RuntimeError` | 20s is arbitrary; some sources (iptv-org French guides) may legitimately be slower on first cold load |
| Network failure | `URLError` → `RuntimeError("Upstream failed")` | Error message is generic, correct for security (no URL leakage) |

**Missing: 429 / Retry-After handling.** When an API responds with HTTP 429 and a `Retry-After: N` header, the application raises `RuntimeError("HTTP 429")` and stores a `failed` job. The quota ledger still has this call deducted even though it did not return data. If collection runs three times per day at 06:00, 12:00, 20:00 and the 06:00 run hits a 429, the 12:00 run will retry without knowledge that the provider signalled not-before. The correct fix: catch 429 separately, read the `Retry-After` header, store a `retry_after_utc` field in the quota ledger, and skip the source until that time passes.

**Missing: ETag/Last-Modified round-trip.** Every call fetches the full payload. The correct flow:
```python
# On fetch: send If-None-Match + If-Modified-Since from last response
# On 304 Not Modified: skip parse, retain last-good snapshot
# On 200: update stored ETag and Last-Modified, proceed with parse
```
This is especially important for the XMLTV guides (10–50 MB gzipped) where iptv-org's CDN supports ETags.

**Missing: Content-Encoding `br` (Brotli).** `urllib.request` does not decompress Brotli. If any source sends `Content-Encoding: br`, the raw bytes will be binary gibberish. Currently no source uses Brotli, but this should be guarded with a check on the response `Content-Encoding` header.

---

### 1.2 XMLTV Decode Pipeline (`providers.decode_xmltv`)

The decode pipeline is the most security-critical component; it processes untrusted external XML.

```
decode_xmltv(raw_bytes, source_id)
  → check raw[:2] == b"\x1f\x8b"           # Gzip magic number detection
  → gzip.GzipFile.read(max_expanded + 1)   # Bounded decompression (65 MB)
  → check len(payload) > max_expanded      # Bomb detection
  → check b"<!DOCTYPE" in payload.upper()  # DTD rejection (case-insensitive)
  → check b"<!ENTITY" in payload.upper()   # Entity rejection
  → ET.iterparse(events=("start","end"))   # Streaming parse — no full DOM
  → root = first node; assert root.tag == "tv"
  → on "end" + tag == "channel":
       channel_id = node.get("id")[:180]
       name = node.findtext("display-name")[:180]
       channels[channel_id] = name
       node.clear()
  → on "end" + tag == "programme":
       start = xmltv_time(node.get("start"))  # Strict UTC offset required
       end   = xmltv_time(node.get("stop"))
       title = node.find("title").text[:240]
       desc  = node.findtext("desc")[:1000]
       lang  = title_node.get("lang")[:12]
       programmes.append({...})
       node.clear()
       root.clear()
→ return {channels, programmes, invalid_programmes, source_redistribution_approved: False}
```

**Critical defects in this pipeline:**

**D-01: `root.clear()` on every programme node is redundant and potentially harmful**  
`root.clear()` after each `programme` element clears the top-level `<tv>` node's children list. Because `iterparse` has already yielded `channel` end events, those channel nodes have already been processed and cleared. However, calling `root.clear()` on every programme also removes any partially-buffered `channel` nodes whose `end` event hasn't fired yet when two channels are defined adjacent to a programme. In practice, XMLTV defines all channels before all programmes, so this doesn't trigger — but it's a time bomb if any XMLTV source interleaves channel and programme definitions.

The correct approach is to clear the root only periodically (every 1000 programmes) or not at all, since `node.clear()` on the programme node itself is sufficient for memory bounds.

**D-02: `channel` `display-name` takes only the first occurrence**  
XMLTV allows multiple `<display-name>` elements per channel with different `lang` attributes:
```xml
<channel id="bbc1.gb">
    <display-name lang="en">BBC One</display-name>
    <display-name lang="fr">BBC Un</display-name>
</channel>
```
Current code: `name = node.findtext("display-name") or channel_id` — this takes the first `<display-name>` only. For UK channels in a French guide, the French name may appear first ("BBC Un") and be used as the canonical display name, breaking the `normalized_name()` matching in `guide.py`.

Fix: prefer `lang="en"` when present, fall back to first.

**D-03: No `icon` or `url` capture from channel elements**  
XMLTV `<channel>` elements often carry `<icon src="...">` with a logo URL. This is valuable for the B1G Android Guide overlay. Currently not captured. The `icon` URL should be stored as an optional field (but NOT fetched — only stored as a reference).

**D-04: Programme `subtitle`, `category`, `live` and `previously-shown` are silently discarded**  
The critical `<live />` flag and `<previously-shown />` element are ignored entirely. Without the live flag, all EPG programmes appear equivalent whether live or recorded. This distinction is fundamental to the Sports Today rail in B1G: a live match is prioritised, a highlights programme is secondary.

XMLTV element taxonomy:
- `<sub-title>` — episode title (e.g. "Matchday 12 Highlights")
- `<category>` — genre; repeatable with `lang` attribute ("Sport", "Football", "Film")
- `<live />` — empty element present when this is a live transmission
- `<previously-shown date="YYYYMMDD">` — when originally broadcast (indicates repeat)
- `<premiere />` — first broadcast
- `<episode-num system="xmltv_ns">0.0.0/1</episode-num>` — SxxExx notation
- `<star-rating>` — quality rating (rarely reliable in sports guides)
- `<rating system="BBFC">PG</rating>` — content rating

Required additions to `decode_xmltv` return dict:
```python
"subtitle": (node.findtext("sub-title") or "")[:240],
"categories": [n.text[:60] for n in node.findall("category") if n.text][:5],
"is_live": node.find("live") is not None,
"is_repeat": node.find("previously-shown") is not None,
"episode_num": (node.findtext("episode-num") or "")[:40],
```

**D-05: `xmltv_time` does not handle bare Z suffix or naive times**  
```python
# Current formats tried:
"%Y%m%d%H%M%S %z"   # e.g. 20261112133000 +0000
"%Y%m%d%H%M %z"     # e.g. 202611121330 +0000
```
Some XMLTV sources emit:
- `20261112133000Z` — 'Z' suffix without a space, not matched by either format
- `20261112133000` — naive with no offset (non-compliant but common)
- `20261112T133000+0000` — ISO 8601 variant with 'T'

The function should handle `Z` → `+0000` before format matching, and log a warning (not raise) for naive times from known-UTC sources.

**D-06: No validation that `channel_id` referenced in `<programme>` exists in `channels` dict**  
Programmes can reference channel IDs not defined in any `<channel>` element. Currently these are stored with an orphan `channel_id` and no display name. The orphan detection should increment a counter (`orphaned_programmes`) in the return dict.

**D-07: `max_programmes=100_000` does not scale with large guides**  
The iptv-org French guides contain 150,000–300,000 programme rows for a 7-day window. The 100k ceiling will cause the parse to raise `ValueError("count exceeded")` on these guides. This limit needs to be configurable per source or raised to 500,000 (the decompressed 65 MB limit provides the actual safety bound).

---

### 1.3 JSON Sports Parse Pipelines (per adapter)

#### 1.3.1 Jolpica F1 (`providers.f1_events`)

**Input structure (from provider documentation; not a live capture):**
```json
{
  "MRData": {
    "xmlns": "...", "series": "f1", "url": "...",
    "limit": "30", "offset": "0", "total": "24",
    "RaceTable": {
      "season": "2026",
      "Races": [
        {
          "season": "2026", "round": "1", "url": "...",
          "raceName": "Bahrain Grand Prix",
          "Circuit": {
            "circuitId": "bahrain",
            "url": "...",
            "circuitName": "Bahrain International Circuit",
            "Location": {"lat": "26.0325", "long": "50.5106", "locality": "Sakhir", "country": "Bahrain"}
          },
          "date": "2026-03-01", "time": "15:00:00Z",
          "FirstPractice": {"date": "2026-02-27", "time": "11:30:00Z"},
          "SecondPractice": {"date": "2026-02-27", "time": "15:00:00Z"},
          "ThirdPractice": {"date": "2026-02-28", "time": "12:00:00Z"},
          "Qualifying": {"date": "2026-02-28", "time": "15:00:00Z"}
        }
      ]
    }
  }
}
```

**Logic trace for one race:**
```python
sessions = [("race", race)]                          # Race entry first
sessions.extend(                                      # Then all session keys
    (key, race[key])
    for key in ("FirstPractice", "SecondPractice",
                "ThirdPractice", "Qualifying",
                "Sprint", "SprintQualifying", "SprintShootout")
    if key in race
)
# For standard weekend: [race, FP1, FP2, FP3, Quali]
# For sprint weekend:   [race, FP1, SprintShootout, Sprint, Quali]
```

**Gap L-01: Race entries where `time` is missing but `date` is known are silently dropped**
```python
if not entry.get("date") or not entry.get("time"):
    continue   # Race dropped entirely
```
Some early-season races have a confirmed date but no confirmed time (UTC). This is common at announcement time. The correct behaviour: if date is known but time is not, generate an event with `start_precision: "date_only"` and `start_utc` set to noon UTC on that date as a placeholder, plus a `time_unconfirmed: true` flag. Never silently drop a known fixture.

**Gap L-02: Season rollover not handled**  
`https://api.jolpi.ca/ergast/f1/current.json` returns the **current season's** races. After the last race of the year (typically December), the next season's pre-season races are not returned until the new season is published. This creates a December→February gap. To cover pre-season, the application should also fetch `f1/{year+1}.json` from October onwards.

**Gap L-03: Race Circuit coordinates not stored**  
`Location.lat/long` are available but not stored in the event record. These are useful for time-zone inference for the B1G Android display. Store as `venue_lat` and `venue_lon`.

**Gap L-04: `circuitId` not stored as an identifier field**  
The canonical circuit identifier (`bahrain`, `monza`, `silverstone`) enables deduplication and future cross-referencing. Store as `circuit_id`.

**Gap L-05: Pagination not checked (`limit`/`total`/`offset` ignored)**  
The `MRData.total` vs `MRData.limit` ratio is never checked. The Jolpica API returns up to 30 races per page by default. A 24-race season fits in one page, but future seasons or combined multi-year queries would need pagination. The check `int(paging.get("total",1)) > int(paging.get("current",1))` exists for api_sports but not jolpica.

---

#### 1.3.2 football-data.org (`providers.football_data_events`)

**Input structure (from provider documentation; not a live capture):**
```json
{
  "count": 42,
  "filters": {"dateFrom": "2026-11-12", "dateTo": "2026-11-19"},
  "matches": [
    {
      "id": 519048,
      "competition": {"id": 2021, "name": "Premier League", "code": "PL", "emblem": "...", "area": {"name": "England"}},
      "utcDate": "2026-11-15T15:00:00Z",
      "status": "SCHEDULED",
      "homeTeam": {"id": 57, "name": "Arsenal FC", "shortName": "Arsenal", "tla": "ARS", "crest": "..."},
      "awayTeam": {"id": 65, "name": "Manchester City FC", "shortName": "Man City", "tla": "MCI", "crest": "..."},
      "venue": "Emirates Stadium",
      "group": null,
      "stage": "REGULAR_SEASON",
      "lastUpdated": "2026-11-01T12:34:56Z"
    }
  ]
}
```

**Logic trace:**
```python
for m in matches:
    when = m.get("utcDate")     # "2026-11-15T15:00:00Z"
    utc = datetime.fromisoformat(when.replace("Z", "+00:00"))
    home = m.get("homeTeam", {}).get("name") or "TBC"
    away = m.get("awayTeam", {}).get("name") or "TBC"
    events.append({"id": "football-data:%s" % m["id"], ...})
```

**Gap L-06: `shortName` and `tla` are not stored**  
`shortName: "Arsenal"` and `tla: "ARS"` are more useful for the B1G Sports Today rail display than the full legal name. Store as `home_short`, `away_short`, `home_tla`, `away_tla`.

**Gap L-07: `competition.area.name` (country) not stored**  
The competition country ("England" for PL, "Europe" for UCL) enables the B1G Android country-filter feature. Store as `competition_country`.

**Gap L-08: `stage` and `group` not stored**  
"GROUP_STAGE" vs "KNOCKOUT_ROUND_OF_16" vs "FINAL" is essential for display priority. Store as `stage`.

**Gap L-09: `status: "POSTPONED"` / `"CANCELLED"` events are stored as normal events**  
Current code stores all matches regardless of `status`. A POSTPONED match will appear in the Sports Today rail with no indicator. It should be stored with `status: "postponed"` and filtered out of the "today's live matches" display while still being available for calendar view.

**Gap L-10: `lastUpdated` field not tracked**  
If `lastUpdated` is earlier than the application's last successful fetch time, the row hasn't changed and need not trigger a materialize update. Tracking `lastUpdated` per event enables incremental updates within the 7-day window without refetching unchanged fixtures.

**Gap L-11: Free tier returns only 12 specific competitions — not checked in code**  
Free tier competitions are: PL, BL1, PD, SA, FL1, DED, PPL, EL1, CLI, WC, EC, BSA, PL (`PL` = Premier League; `EL1` = Dutch Eerste Divisie, NOT Europa League; `EL` Europa League requires Tier 3+). The application silently fetches all competitions and silently receives only the free-tier subset. This creates a coverage gap without warning: users may configure the app expecting Europa League coverage that never arrives. The code should log a warning if `competition.code` falls outside the expected free-tier list.

---

#### 1.3.3 API-Sports Football (`providers.api_sports_events`)

**Input structure:**
```json
{
  "get": "fixtures",
  "parameters": {"date": "2026-11-15", "timezone": "Europe/London"},
  "errors": [],
  "results": 10,
  "paging": {"current": 1, "total": 1},
  "response": [
    {
      "fixture": {
        "id": 1234567,
        "referee": "Michael Oliver",
        "timezone": "Europe/London",
        "date": "2026-11-15T15:00:00+00:00",
        "timestamp": 1763215200,
        "venue": {"id": 556, "name": "Emirates Stadium", "city": "London"},
        "status": {"long": "Not Started", "short": "NS", "elapsed": null}
      },
      "league": {
        "id": 39, "name": "Premier League", "country": "England",
        "logo": "...", "flag": "...", "season": 2026, "round": "Regular Season - 12"
      },
      "teams": {
        "home": {"id": 42, "name": "Arsenal", "logo": "...", "winner": null},
        "away": {"id": 50, "name": "Manchester City", "logo": "...", "winner": null}
      },
      "goals": {"home": null, "away": null},
      "score": {"halftime": {"home": null, "away": null}, "fulltime": {"home": null, "away": null}}
    }
  ]
}
```

**Gap L-12: `league.round` not stored (e.g. "Regular Season - 12")**  
The round string is useful for display in the B1G Sports Today rail. Store as `round`.

**Gap L-13: `fixture.timestamp` (Unix epoch) not stored**  
UTC ISO string is derived from `fixture.date` already, but the Unix timestamp is a redundant cross-check. If `fixture.date` has an unexpected timezone offset, `timestamp` provides a fallback. Store as a sanity check.

**Gap L-14: `goals` and `score` fields not stored even as optional**  
For live and in-progress matches, the score is essential. Store `score_home`, `score_away` as nullable integers. When both are null, the match hasn't started. This enables B1G to show live scores.

**Gap L-15: `league.id` and `fixture.id` are both integers but stored as string in `id` field**  
`"id": f"api-sports:{fixture['id']}"` — `fixture['id']` is an integer. If the API returns a fixture ID as a string in some edge cases (e.g. very large IDs), `str(fixture['id'])` should be explicit.

**Gap L-16: Paging abort is catastrophic for multi-page responses**  
```python
if int(paging.get("total", 1)) > int(paging.get("current", 1)):
    raise ValueError("API-Sports fixture page incomplete; keep previous last-good")
```
The API-Sports free tier returns 10 results per page. On a typical Premier League matchday there are 5 matches, 10 at most — often exactly the page boundary. Any day with 11+ matches across all competitions triggers this error and the entire day's collection is abandoned in favour of stale data. The fix is to fetch subsequent pages:

```python
def api_sports_events_paged(base_url, headers, day, store, name, daily_limit):
    """Fetch all pages for a given day, consuming quota per page."""
    all_events = []
    page = 1
    while True:
        query = urllib.parse.urlencode({"date": day, "timezone": "Europe/London", "page": page})
        raw = providers.fetch(base_url + "?" + query, headers)
        payload = json.loads(raw)
        paging = payload.get("paging", {})
        all_events.extend(providers.api_sports_events_single_page(payload))
        if int(paging.get("current", 1)) >= int(paging.get("total", 1)):
            break
        page += 1
        store.increment(name, daily_limit)  # Reserve quota before next fetch
    return all_events
```

---

#### 1.3.4 OpenLigaDB (`providers.openligadb_events`)

**Input structure (from `getmatchdata/bl1/{season}`):**
```json
[
  {
    "matchID": 67890,
    "matchDateTime": "2026-11-15 15:30:00",   // CET local time (not UTC!)
    "matchDateTimeUTC": "2026-11-15T14:30:00Z",  // UTC preferred
    "leagueId": 35, "leagueName": "1. Fußball-Bundesliga",
    "leagueSeason": 2026, "leagueShortcut": "bl1",
    "group": {"groupName": "12. Spieltag", "groupOrderID": 12, "groupID": 123},
    "team1": {"teamId": 6, "teamName": "FC Bayern München", "shortName": "Bayern", "teamIconUrl": "..."},
    "team2": {"teamId": 9, "teamName": "FC Schalke 04", "shortName": "Schalke", "teamIconUrl": "..."},
    "matchIsFinished": false,
    "matchResults": [],
    "goals": [],
    "location": {"locationID": 1, "locationCity": "München", "locationStadium": "Allianz Arena"}
  }
]
```

**Gap L-17: `matchDateTime` (local CET time) is used as fallback, but current code doesn't do so**  
The current code:
```python
raw_time = m.get("matchDateTimeUTC")
if not raw_time or not m.get("matchID"):
    continue   # Row dropped if matchDateTimeUTC absent
```
If `matchDateTimeUTC` is absent but `matchDateTime` is present, the row is silently dropped. The fix is to fall back to `matchDateTime` with an assumed `Europe/Berlin` timezone (CET/CEST) when the UTC field is absent, with a warning.

**Gap L-18: `group.groupName` ("12. Spieltag" = Matchday 12) not stored**  
This is the equivalent of football-data.org's `round` field. Store as `round`.

**Gap L-19: `shortName` for team not stored**  
`"Bayern"` vs `"FC Bayern München"` — the short name is better for the B1G Sports Today rail narrow display.

**Gap L-20: `matchResults` and `goals` ignored**  
Live and completed match data is available. For finished matches, `matchResults` contains half-time and full-time scores. Store as `result_home` / `result_away` nullable integers.

**Gap L-21: `getlastchangedate` endpoint never called**  
OpenLigaDB provides `GET /getlastchangedate/bl1/{season}/{group}` which returns the last time any match in that group was updated. If the returned date is earlier than the last successful snapshot `updated_at`, the full `getmatchdata` call can be skipped. This saves 4 daily quota units per redundant collection and speeds up the collection loop.

**Gap L-22: Multiple leagues hardcoded to `bl1` only**  
The URL base is `https://api.openligadb.de/getmatchdata/bl1`. OpenLigaDB supports many leagues. The `SPORTS` dict entry should be parameterised as a list of leagues:
```python
"openligadb": {
    "label": "Football · OpenLigaDB",
    "base": "https://api.openligadb.de/getmatchdata",
    "leagues": ["bl1", "bl2", "oefb1"],   # configurable
    "daily_limit": 4 * len(leagues),
}
```

---

### 1.4 Collection Orchestration (`engine._collect_locked`)

```python
def _collect_locked(self):
    conf = self.store.config()
    if not conf["setup_complete"]:
        self.store.job("collector", "skipped", "Setup not completed")
        return False
    self.store.job("collector", "started")
    for name, enabled in conf["sports"].items():
        if enabled and name in providers.SPORTS:
            self._collect_sport(name, conf)   # Sequential
    for name, enabled in conf["epg"].items():
        if enabled and name in providers.EPG:
            self._collect_epg(name)            # Sequential, after all sports
    self._materialize()
    self.store.job("collector", "finished")
    return True
```

**Critical architectural issue: sequential single-threaded collection**

With 4 sports sources × 20s timeout = worst case 80s just for sports, then EPG sources another 80s = 160+ seconds for a full collection run. When the application expands to 10+ sports adapters (tennis, cricket, boxing, rugby, MotoGP) and 6+ EPG sources (UK general, France, additional countries), a worst-case collection could take 10 minutes if any sources time out.

The required architecture (from ADR-04) is independent parallel pipelines:

```python
def _collect_locked(self):
    conf = self.store.config()
    # Launch each source in its own daemon thread
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        sport_futures = {
            name: pool.submit(self._collect_sport, name, conf)
            for name, enabled in conf["sports"].items()
            if enabled and name in providers.SPORTS
        }
        epg_futures = {
            name: pool.submit(self._collect_epg, name)
            for name, enabled in conf["epg"].items()
            if enabled and name in providers.EPG
        }
        # Wait for all; each _collect_sport/_collect_epg handles its own errors
        for f in concurrent.futures.as_completed(list(sport_futures.values()) + list(epg_futures.values())):
            try:
                f.result()
            except Exception as exc:
                LOGGER.error("Collection thread raised: %s", exc)
    self._materialize()
```

Each `_collect_sport` and `_collect_epg` already has its own exception handler and writes directly to the store, so parallelism is safe. The single `_busy` lock prevents overlapping collection runs (unchanged). The `store.increment()` pre-reservation is thread-safe because SQLite WAL mode serialises writes.

---

### 1.5 Materialisation Pipeline (`engine._materialize`)

```python
def _materialize(self):
    conf = self.store.config()
    events = {}
    for name, enabled in conf["sports"].items():
        if not enabled: continue
        entry = self.store.snapshot("sports:" + name)
        if entry:
            for event in entry["data"]["events"]:
                events[event["id"]] = event   # Last-write-wins by ID
    # 7-day rolling window filter
    london_today = datetime.now(ZoneInfo("Europe/London")).date()
    eligible = [e for e in events.values()
                if london_today <= parse_date(e) <= london_today + timedelta(days=7)]
    self.store.save_snapshot("sports", {
        "events": sorted(eligible, key=start_utc),
        ...
    })
```

**Gap M-01: Last-write-wins deduplication is source-ordering dependent**  
If `jolpica` updates its F1 snapshot after `api_sports`, the dict merge `events[event["id"]] = event` overwrites the api_sports entry with the jolpica entry for any event with the same ID. But IDs are `"f1:2026:1:race"` vs `"api-sports:1234567"` — they never collide in the current set. However, if two providers cover the same competition (e.g. two football providers both cover Premier League), their events will have different IDs (`"football-data:519048"` vs `"api-sports:1234567"`) and **both will appear in the materialised feed as separate events for the same match**. This is a data quality failure.

The correct materialisation needs a canonical event merge:
```python
# Key: (sport, competition_normalised, start_utc_rounded_to_hour, home_team_normalised, away_team_normalised)
# If two events share this key, merge their sources[] lists and keep the one with better start_precision
```

**Gap M-02: 7-day window uses `london_today` not `utc_today`**  
Events at 23:30 BST (00:30 UTC next day) may fall outside the 7-day window depending on when materialisation runs. Using `ZoneInfo("Europe/London")` for the window boundary is correct for the owner's local experience but should be documented.

**Gap M-03: No EPG-to-event cross-reference in materialisation**  
The `_materialize` function builds `sports` and `epg` snapshots independently with no cross-reference. The event→broadcaster evidence layer should run here, after both snapshots are populated but before the final `save_snapshot("sports", ...)`.

---

### 1.6 Publication Pipeline (`engine.publish`)

```python
def publish(self):
    conf = self.store.config()
    allowed = set(conf.get("publication_approvals", []))
    if not allowed:
        raise ValueError("No sport source has an approved public redistribution licence")
    snap = self.store.snapshot("sports")
    events = [x for x in snap["data"]["events"] if x["source_id"] in allowed]
    # Content-addressed revision
    payload = json.dumps(events, separators=(",",":"), ensure_ascii=False).encode()
    revision = hashlib.sha256(payload).hexdigest()[:20]
    self._github_write(owner, repo, branch, token, f"data/revisions/{revision}/events.json", payload)
    self._github_write(owner, repo, branch, token, "data/manifest.json", manifest_json)
```

**Gap P-01: Manifest is overwritten but asset is content-addressed**  
Two collection runs with the same event data will produce the same `revision` hash and attempt to write to the same asset path. The first write creates it; the second attempt GETs the existing SHA and writes identical content. This is harmless but wasteful. The manifest should be compared with the previous manifest before writing, and skipped if unchanged.

**Gap P-02: `ensure_ascii=False` in JSON encoding can produce UTF-8 with high Unicode**  
Team names and venue names can contain non-ASCII characters (accented letters, Arabic, Japanese). `ensure_ascii=False` correctly allows these through. GitHub API accepts UTF-8 in base64-encoded content. This is correct.

**Gap P-03: No retry on GitHub API rate limit (secondary rate limit)**  
GitHub API has a secondary rate limit on write operations (content API limit: ~1 request per second). With two sequential writes (asset then manifest), there's a low risk of hitting this, but no retry logic exists. Add exponential backoff on `RuntimeError("GitHub API rejected request (429)")`.

**Gap P-04: `_github_write` is called synchronously from the UI thread when triggered from the Publishing page**  
GitHub API writes can take 1–10 seconds. The Publishing page's POST handler blocks the HTTP server thread for the duration. This prevents the CSRF check and other page loads from responding. The publish operation should be dispatched to a background thread and the UI should poll for completion status.

---

## Part 2: Source Material Forensic Investigation

### 2.1 Existing Source: farleyflex EPG Guide

**URL:** `https://raw.githubusercontent.com/farleyflex/epg-guide/main/epg.xml`  
**Format:** XMLTV uncompressed XML  
**Hosting:** GitHub raw file; no CDN; no ETag (GitHub raw files do have ETag headers)  
**Update frequency:** Unknown; repository commit history is the only indicator  
**Coverage observed:** Sports-heavy UK channels; Sky Sports 1–9, Sky Sports Main Event, Premier League, F1, Football, Cricket, TNT Sports 1–4, BT Sport 1–3, BBC Sport, ITV Sport, Premier Sports 1–2  
**Coverage NOT observed:** BBC One/Two general, ITV 1 general, Channel 4/5, regional UK channels, any French channels  

**Rights investigation:**
The repository `farleyflex/epg-guide` is a GitHub-hosted XMLTV file. It has no explicit licence file (`LICENSE.md` absent at time of review). The commit history suggests it is manually maintained or auto-generated by a personal script. It has historically appeared in IPTV community lists, suggesting it may be derived from or cross-reference with iptv-org/epg mirror aggregation.

**Key concern: upstream chain.** iptv-org/epg acts as a scraping aggregator; farleyflex may be one of its downstream mirrors or a manual curated subset. If programme data originated from commercial EPG data companies (ITV Hub, Sky Go internal EPG, BT Sport API), the redistribution chain is completely opaque. The current application handles this correctly by setting `source_redistribution_approved: False` and never publishing EPG programme text.

**Usage in application:**
1. Fetched as raw XML (no gzip)
2. All channels parsed into `channels` dict
3. All programmes parsed — but `subtitle`, `category`, `live` discarded
4. Coverage analysed by `analyze_guide()`
5. Stored as `epg:farleyflex` snapshot

**Identified improvements:**
- Use GitHub API `HEAD` request to get ETag; skip full fetch when ETag unchanged
- Extract `is_live: True` from `<live/>` elements to identify live sport in EPG
- Extract `category` to filter programmes by genre in coverage reporting
- Cross-reference channel IDs with `KNOWN_SERVICES` to get canonical IDs

---

### 2.2 Existing Sources: French XMLTV Sources

**fr_programmetv:** `https://iptv-org.github.io/epg/guides/fr/programme-tv.net.epg.xml.gz`  
**fr_telerama:** `https://iptv-org.github.io/epg/guides/fr/telerama.fr.epg.xml.gz`  
**fr_xmltv:** `https://xmltvfr.fr/xmltv/xmltv_fr.xml.gz`

**iptv-org hosted sources common characteristics:**
- Served via GitHub Pages CDN (Fastly); ETags supported; Last-Modified headers present
- Files are gzip-compressed XMLTV
- Updated by iptv-org's automated scrapers on varying schedules (some daily, some hourly)
- The iptv-org project licence is MIT for the **software** (`epg` repository code), but this says **nothing** about the EPG data content rights, which originate from the scraped source (programme-tv.net, telerama.fr)
- Télérama is a major French media company; its programme data is commercially licensed

**fr_xmltv (xmltvfr.fr) investigation:**
This is an independent French XMLTV project, separate from iptv-org. The site is community-maintained. It covers:
- Approximately 300 French TV channels including regional
- TF1 family, France Télévisions, Canal+, beIN Sports, RMC Sport
- Typical 7-day forward schedule
- Self-hosted on a private server; not mirrored through iptv-org
- Licence: not formally stated on the site. France's database rights (sui generis) under the 1996 EU Database Directive apply — programme schedules are factual data but their compilation may be a protected database

**Key distinction for rights:** Under EU law (and UK law post-Brexit via CDPA 1988 as amended), programme listings (time, channel, title) in simple tabular form are considered factual data with weaker copyright protection, but compiled collections of such data may qualify as a "database" protected by database rights. Personal/private use is generally permitted; public redistribution of a compiled database requires the maker's consent.

The application's current conservative position (never publish EPG programme text; store only locally) is the correct approach.

---

### 2.3 Candidate New Source: EPG Share UK1

**URL investigation:** `https://epgshare01.online`  
**Format:** XMLTV XML and XML.GZ  
**Coverage:** UK channels broadly; a mix of FTA (BBC/ITV/C4/C5) and subscription (Sky, Virgin, BT)  
**Update frequency:** Claims to update several times daily  
**Authentication:** None required for read access  
**Community status:** Widely referenced in IPTV communities; appears in multiple B1G-related discussions  

**Rights status:** No terms of service or licence visible at the domain. This is a community resource with no formal legal standing. Programme data is almost certainly scraped from commercial EPG providers (possibly tvguide.co.uk, Freesat, Sky EPG). The absence of attribution or stated rights means it is NOT safe for public redistribution. For private collection and display (the SportsLiveInfo local use case), the legal risk is lower but not zero.

**Integration blueprint:**
```python
# providers.py addition:
"epgshare_uk": (
    "UK · EPG Share UK1",
    "https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.xml.gz",
)
```

**Key technical considerations:**
- The main guide (`ALL_SOURCES1`) covers ~2000+ channels
- Channel IDs follow the pattern `[channel].uk` or `[channel].com`  
- The guide is very large (possibly >50 MB compressed) — `max_expanded` limit may need raising to 200 MB for this source, or a source-specific limit should be added
- `max_programmes=100_000` will definitely need raising to 500,000 for this source

---

### 2.4 Candidate New Source: Matt Huisman EPG

**URL investigation:** `https://i.mjh.nz`  
**Format:** Multiple guides in XMLTV and m3u8 format  
**Coverage:** UK (Sky, Virgin, BT), Australia, New Zealand, USA (Pluto TV, DirecTV Stream)  
**Channel IDs:** Matt Huisman uses his own channel ID scheme (e.g. `sky.go.sky.sports.main.event.uk`)  
**Authentication:** None; freely accessible  

**Rights status:** No explicit licence. Similar position to EPG Share. The maintainer is a known community contributor. Programme data sourced from broadcaster EPG APIs (Sky Go, BBC iPlayer, ITV Hub, etc.). Safe for private local use; not safe for public redistribution.

**Integration blueprint:**
```python
"mjh_uk": (
    "UK · Matt Huisman",
    "https://i.mjh.nz/Sky/epg.xml.gz",    # Sky UK guide
)
```

**Key channel ID mapping challenge:**
Matt Huisman uses his own channel ID namespace (`sky.go.sky.sports.main.event.uk`) which differs from both iptv-org's namespace and farleyflex's namespace. The `canonical_channel()` function must learn to handle this. `KNOWN_SERVICES` normalisation needs to map these IDs to `gb.sky.sports.main.event`.

---

### 2.5 Candidate New Source: IPTV-org Channel and Guide APIs

**Base URL:** `https://iptv-org.github.io/api/`  
**Available endpoints:**
- `/channels.json` — full channel registry with canonical IDs, names, country, website, logo URL
- `/guides.json` — registry of available EPG guides with their XMLTV URLs and channel coverage
- `/feeds.json` — registry of m3u8 playlist feeds

**Licence:** Data is MIT-licensed by iptv-org. However, the channel metadata (logos, names) may have third-party rights. The guide URLs in `guides.json` point to the original source EPG pages — iptv-org does not hold redistribution rights to those.

**Usage for SportsLiveInfo:**
This API is valuable NOT for programme data but for **channel identity crosswalk**. The `channels.json` file maps channel names (with their alternative spellings) to canonical IDs used in XMLTV guides. This is exactly what `guide.py`'s `KNOWN_SERVICES` dict is trying to do manually.

**Integration blueprint:**
```python
# guide.py enhancement: load iptv-org channels as a crosswalk index
def load_iptv_org_crosswalk(channels_json_path):
    """Build name→canonical_id map from iptv-org channels.json (local copy)."""
    channels = json.load(open(channels_json_path))
    crosswalk = {}
    for ch in channels:
        # ch["id"] = "BBC1.uk" etc.
        # ch["name"] = "BBC One"
        # ch["alt_names"] = ["BBC 1", "BBC One HD"]
        norm = normalized_name(ch["name"])
        crosswalk[norm] = ch["id"]
        for alt in ch.get("alt_names", []):
            crosswalk[normalized_name(alt)] = ch["id"]
    return crosswalk
```

The `channels.json` file (downloaded periodically as a source, not at runtime) would replace the manual 30-entry `KNOWN_SERVICES` dict with 10,000+ entries. It should be treated as a local reference fixture, not fetched at collection time.

---

### 2.6 Candidate New Source: SportsAPI.app

**URL investigation:** `https://sportsapi.app`  
**Pricing:** Documented as 100 requests/day free (beta docs suggest 1000/day — must use 100 conservatively)  
**Sports covered:** Football, basketball, baseball, ice hockey, American football, rugby, tennis, cricket, MMA, volleyball, handball  
**Authentication:** `x-api-key` header  
**Base URL:** `https://api.sportsapi.app/v1/`  

**API structure:**
```
GET /fixtures?sport=football&date=2026-11-15&timezone=Europe/London
GET /fixtures?sport=tennis&date=2026-11-15
GET /fixtures?sport=cricket&date=2026-11-15
GET /leagues?sport=football&country=England
```

**Response structure (HYPOTHETICAL — not verified against the live API):**
```json
{
  "status": "success",
  "meta": {"sport": "football", "date": "2026-11-15", "timezone": "Europe/London", "total": 42, "page": 1, "pages": 5},
  "data": [
    {
      "id": "sportsapi-f-98765",
      "sport": "football",
      "league": {"id": 1, "name": "Premier League", "country": "England", "season": 2026},
      "teams": {
        "home": {"id": 10, "name": "Arsenal", "logo": "..."},
        "away": {"id": 20, "name": "Manchester City", "logo": "..."}
      },
      "venue": {"id": 100, "name": "Emirates Stadium", "city": "London", "country": "England"},
      "datetime": "2026-11-15T15:00:00+00:00",
      "status": "not_started"
    }
  ]
}
```

**Pagination model:** `meta.page` and `meta.pages`. With 100/day free, a 5-page response = 5 request units.

**Integration blueprint (Python):**
```python
# providers.py
"sportsapi_football": (
    "Football · SportsAPI.app",
    "https://api.sportsapi.app/v1/fixtures",
    "sportsapi",
    100  # conservative free-tier daily limit
)

def sportsapi_events(data, sport="football"):
    payload = json.loads(data)
    if payload.get("status") != "success":
        raise ValueError("SportsAPI.app returned non-success status")
    meta = payload.get("meta", {})
    if int(meta.get("page", 1)) < int(meta.get("pages", 1)):
        # Return partial flag for multi-page handling
        raise ValueError("SportsAPI.app page incomplete; additional pages required")
    events = []
    for row in payload.get("data", []):
        try:
            when = datetime.fromisoformat(row["datetime"].replace("Z", "+00:00")).astimezone(timezone.utc)
            home = row.get("teams", {}).get("home", {}).get("name") or "TBC"
            away = row.get("teams", {}).get("away", {}).get("name") or "TBC"
            events.append({
                "id": f"sportsapi:{row['id']}",
                "sport": sport,
                "competition": row.get("league", {}).get("name", ""),
                "competition_country": row.get("league", {}).get("country", ""),
                "event_type": "match",
                "title": f"{home} v {away}",
                "participants": [home, away],
                "start_utc": when.isoformat(timespec="seconds"),
                "start_precision": "scheduled",
                "status": row.get("status", "not_started"),
                "venue": row.get("venue", {}).get("name", ""),
                "source_id": "sportsapi",
                "broadcasts": [], "broadcast_verified": False
            })
        except (KeyError, ValueError, TypeError):
            continue
    return events
```

**Quota management concern:**
With 100 req/day and 10+ sports, budget is 10 requests per sport. For a sport like football with 5+ leagues active on a typical day, 10 requests = 2 leagues per day. A sport priority order is required:
1. Football (highest priority; 30 requests)
2. Tennis (20 requests)
3. Rugby (15 requests)
4. Cricket (15 requests)
5. Boxing/MMA (10 requests)
6. Other sports (10 requests)

---

### 2.7 Candidate New Source: OpenLigaDB Multi-League

**URL:** `https://api.openligadb.de/`  
**Licence:** ODbL 1.0 (Open Database Licence)  
**Cost:** Free; no API key  
**Available leagues beyond bl1:**

| League ID | Name | Country | Season months |
|---|---|---|---|
| `bl1` | 1. Bundesliga | Germany | Aug–May |
| `bl2` | 2. Bundesliga | Germany | Aug–May |
| `bl3` | 3. Liga | Germany | Jul–May |
| `dfb` | DFB-Pokal | Germany | Aug–May |
| `oefb1` | Austrian Bundesliga | Austria | Jul–May |
| `ubl` | Swiss Super League | Switzerland | Jul–May |
| `mls` | Major League Soccer (community-maintained) | USA | Feb–Nov |

**Endpoints:**
```
GET /getmatchdata/{league}/{season}         # All matches in season
GET /getmatchdata/{league}/{season}/{group} # Specific matchday
GET /getlastchangedate/{league}/{season}/{group} # Update check
GET /getavailablegroups/{league}/{season}   # List matchdays
GET /getnextmatch/{league}                  # Next scheduled match
```

**ODbL attribution requirements:**
- Must credit "OpenLigaDB" as source when displaying data
- Derivative databases must be shared under ODbL (share-alike)
- "Factual information" (match results, teams, times) is freely usable; compilation is what's protected
- For the SportsLiveInfo private collection use case, full compliance requires attribution on any displayed output

**Integration improvement:**
```python
# engine.py _collect_sport refactoring for openligadb:
OPENLIGADB_LEAGUES = ["bl1", "bl2", "oefb1"]  # Configurable

for league in conf.get("openligadb_leagues", OPENLIGADB_LEAGUES):
    # Check last-change before fetching
    last_change_url = f"{base}/{league}/{season}"
    last_changed = check_last_change(league, season)
    if last_changed and last_changed <= snapshot_updated_at:
        continue  # No changes, skip
    self.store.increment("openligadb", 4)
    events = providers.openligadb_events(providers.fetch(last_change_url))
    all_events.extend(events)
```

---

### 2.8 Candidate New Source: Jolpica F1 — Extended Endpoints

**Current usage:** `https://api.jolpi.ca/ergast/f1/current.json` — current season races only

**Additional endpoints available:**

| Endpoint | Description | Daily budget cost |
|---|---|---|
| `/f1/{year}.json` | Specific year schedule | 1 |
| `/f1/{year}/{round}/results.json` | Race results | 1 |
| `/f1/{year}/{round}/qualifying.json` | Qualifying results | 1 |
| `/f1/{year}/{round}/pitstops.json` | Pit stop data | 1 |
| `/f1/drivers.json` | Driver registry | 1 |
| `/f1/constructors.json` | Constructor registry | 1 |
| `/f1/{year}/{round}/laps.json` | Lap data (paginated) | N |

**Licence:** CC BY-NC-SA 4.0 — Attribution, Non-Commercial, Share-Alike  
**Non-commercial constraint:** The SportsLiveInfo private home collector is non-commercial; the B1G Android app as a family personal use app is non-commercial. Attribution must appear wherever the data is displayed.

**Next season pre-season coverage:**
Jolpica/Ergast publishes next season's race calendar when confirmed by FIA (typically October/November). Adding `f1/{year+1}.json` fetch from October onwards would fill the December→February gap:
```python
# engine.py OpenLigaDB section equivalent for F1:
year = datetime.now().year
urls_to_try = [f"https://api.jolpi.ca/ergast/f1/{year}.json"]
if datetime.now().month >= 10:
    urls_to_try.append(f"https://api.jolpi.ca/ergast/f1/{year+1}.json")
```

---

### 2.9 Candidate New Source: football-data.org — Free Tier Limitations

**Free tier competitions (exhaustive list as of 2026):**

| Code | Name | Country | Matches/season |
|---|---|---|---|
| PL | Premier League | England | 380 |
| BL1 | Bundesliga | Germany | 306 |
| PD | La Liga | Spain | 380 |
| SA | Serie A | Italy | 380 |
| FL1 | Ligue 1 | France | 306 |
| DED | Eredivisie | Netherlands | 306 |
| PPL | Primeira Liga | Portugal | 306 |
| ELC | Championship | England | 552 |
| CLI | Copa Libertadores | South America | varies |
| BSA | Série A | Brazil | 380 |
| WC | FIFA World Cup | International | varies |
| EC | European Championship | International | varies |

**NOT in free tier:** UEFA Europa League (EL), UEFA Conference League (UECL), FA Cup, League Cup/Carabao Cup, MLS, Serie B, 2. Bundesliga, La Liga 2.

**Rate limits (free tier):** 10 requests per minute; no daily cap stated but typical usage suggests ~200/day before throttling.

**7-day window restriction:** The `dateFrom`/`dateTo` query parameters span at most 7 days. For competitions with matches spread across 2 weeks (international breaks), multiple fetches are needed.

**Improvement — dynamic competition selection:**
```python
# Instead of fetching all competitions with a date range,
# fetch only competitions known to have matches in the next 7 days:
ACTIVE_COMPETITIONS = ["PL", "BL1", "PD", "SA", "FL1"]
for comp in ACTIVE_COMPETITIONS:
    url = f"{base}?competitions={comp}&dateFrom={start}&dateTo={end}"
    self.store.increment("football_data", 45)
    events.extend(providers.football_data_events(providers.fetch(url, headers)))
```

---

### 2.10 Candidate New Source: API-Sports Multi-Sport

**Currently used for:** Football only (`v3.football.api-sports.io`)  
**Available same-key endpoints:**

| Sport | Endpoint | Free req/day | Notes |
|---|---|---|---|
| Rugby | `v1.rugby.api-sports.io/games` | 100 | Same API key as football |
| Basketball | `v3.basketball.api-sports.io/fixtures` | 100 | Covers NBA, EuroLeague |
| Formula 1 | `v1.formula-1.api-sports.io/races` | 100 | Separate from Jolpica |
| Baseball | `v2.baseball.api-sports.io/games` | 100 | MLB, NPB |
| Volleyball | `v1.volleyball.api-sports.io/fixtures` | 100 | World League, CEV |
| MMA | `v1.mma.api-sports.io/fixtures` | 100 | UFC, Bellator, ONE |

**Key insight:** A single `api_sports` account key unlocks ALL these sports. The current code uses only `v3.football.api-sports.io`. Each new sport needs its own `SPORTS` entry with its own `base_url` and quota tracking:

```python
SPORTS = {
    # Existing
    "api_sports_football": ("Football · API-Sports", "https://v3.football.api-sports.io/fixtures", "api_sports", 80),
    # New entries — same key, separate daily counters
    "api_sports_rugby": ("Rugby · API-Sports", "https://v3.rugby.api-sports.io/fixtures", "api_sports", 50),
    "api_sports_basketball": ("Basketball · API-Sports", "https://v3.basketball.api-sports.io/fixtures", "api_sports", 50),
    "api_sports_cricket": ("Cricket · API-Sports", "https://v1.cricket.api-sports.io/fixtures", "api_sports", 50),
    "api_sports_mma": ("MMA · API-Sports", "https://v1.mma.api-sports.io/fixtures", "api_sports", 30),
}
```

**Quota management across sports:** The same `api_sports` key governs all endpoints but each endpoint has its own rate limit. The `store.increment("api_sports_rugby", 50)` counter should be separate from `store.increment("api_sports_football", 80)` — the shared key doesn't share the per-endpoint daily limit.

**Rugby API response structure:**
```json
{
  "response": [
    {
      "id": 123456,
      "league": {"id": 1, "name": "Six Nations", "country": "World", "season": 2026},
      "teams": {
        "home": {"id": 1, "name": "England"},
        "away": {"id": 2, "name": "France"}
      },
      "date": "2026-02-07T16:45:00+00:00",
      "time": "16:45",
      "venue": {"id": 100, "name": "Twickenham Stadium", "city": "London"},
      "status": {"long": "Not Started", "short": "NS"},
      "scores": {"home": null, "away": null}
    }
  ]
}
```

**Parser:**
```python
def api_sports_rugby_events(data):
    payload = json.loads(data)
    if payload.get("errors"):
        raise ValueError("API-Sports rugby reported an error")
    rows = payload.get("response", [])
    if not isinstance(rows, list):
        raise ValueError("API-Sports rugby fixtures payload invalid")
    events = []
    for row in rows:
        try:
            when = datetime.fromisoformat(row["date"].replace("Z", "+00:00")).astimezone(timezone.utc)
            home = row.get("teams", {}).get("home", {}).get("name") or "TBC"
            away = row.get("teams", {}).get("away", {}).get("name") or "TBC"
            league = row.get("league", {})
            events.append({
                "id": f"api-sports-rugby:{row['id']}",
                "sport": "rugby_union",  # or "rugby_league" — needs league-to-code mapping
                "competition": league.get("name", ""),
                "event_type": "match",
                "title": f"{home} v {away}",
                "participants": [home, away],
                "start_utc": when.isoformat(timespec="seconds"),
                "start_precision": "scheduled",
                "status": row.get("status", {}).get("short", "NS"),
                "venue": row.get("venue", {}).get("name") or "",
                "source_id": "api_sports",
                "broadcasts": [], "broadcast_verified": False
            })
        except (KeyError, ValueError, TypeError):
            continue
    return events
```

**Rugby union vs league distinction** — requires a lookup table:
```python
RUGBY_LEAGUE_IDS = {4, 5, 55, 56}  # API-Sports league IDs for rugby league
def classify_rugby(league_id):
    return "rugby_league" if league_id in RUGBY_LEAGUE_IDS else "rugby_union"
```

---

### 2.11 Candidate New Source: OpenLigaDB Tennis

OpenLigaDB does not cover tennis. For tennis, the architecture requires a separate source.

**Tennis API (`docs.tennis-api.com`)**  
**Free tier:** 50 requests/day  
**Coverage:** ATP, WTA, Grand Slams, Davis Cup, Billie Jean King Cup  
**Authentication:** `x-api-key` header

**Critical tennis-specific logic — start precision:**  
Tennis fixtures at any Grand Slam have three distinct start concepts:
1. Session start: `11:00 BST` — when the day's programme of play begins
2. Order of play position: match X is "not before HH:MM" or "follows [previous match]"
3. Main feature match estimated start: typically mid-afternoon, TBC until live

The event data model must accommodate:
```python
{
    "sport": "tennis",
    "competition": "Wimbledon Championships",
    "event_type": "match",
    "start_utc": "2026-07-01T10:00:00Z",  # Session start (court opens)
    "start_precision": "not_before",        # Match could start much later
    "scheduled_court": "Centre Court",
    "order_of_play": 3,                     # 3rd match on court
    "players": ["Carlos Alcaraz", "Novak Djokovic"],
}
```

---

### 2.12 Candidate New Source: CricketData.org

**URL:** `https://api.cricketdata.org/api/v1/`  
**Free tier:** 100 requests/day  
**Coverage:** International Tests, ODIs, T20Is; domestic T20 leagues (IPL, The Hundred); county cricket  
**Authentication:** `apikey` query parameter (unusual — should use header to avoid key appearing in logs)  

**Multi-day match handling (critical):**  
A Test match spans up to 5 calendar days. The event record must appear on **each playing day separately** in the Sports Today rail. The collection logic for Test cricket must:

1. Fetch the upcoming series/fixtures list
2. For each Test match, expand to individual day records:
```python
def expand_test_match_to_days(match):
    start_date = datetime.fromisoformat(match["startDate"]).date()
    for day_offset in range(5):  # Up to 5 days
        day = start_date + timedelta(days=day_offset)
        yield {
            "id": f"cricket-test:{match['id']}:day{day_offset+1}",
            "sport": "cricket",
            "competition": match["series"]["name"],
            "event_type": "test_day",
            "day_number": day_offset + 1,
            "title": f"{match['team1']} v {match['team2']} — Day {day_offset+1}",
            "participants": [match["team1"], match["team2"]],
            "start_utc": (datetime.combine(day, time(11, 0)) + match["local_offset"]).isoformat(),
            "start_precision": "not_before",   # Day's play can be delayed by rain
            "match_type": "Test",
            ...
        }
```

**T20/ODI fixtures** are single-day and can be treated like football matches with a scheduled `start_utc` and `start_precision: "scheduled"`.

---

## Part 3: Canonical Channel Identity — Deep Forensic Analysis

### 3.1 Current `guide.py` KNOWN_SERVICES — Identified Gaps

The current 30-entry dict covers:
- BBC One/Two: basic — missing BBC Three, BBC Four, BBC News, BBC Parliament, CBBC, CBeebies, BBC Alba, S4C
- ITV 1: covers main — missing ITV2, ITV3, ITV4, ITVBe, ITVX
- Sky Sports: 8 entries — missing Sky Sports Action, Sky Sports Arena, Sky Sports Golf, Sky Sports Racing, Sky Sports Mix, Sky Sports News
- TNT Sports: 4 entries — covers current branding but `BT Sport 1-3` alias variants absent
- Premier Sports: 1-2 — missing Premier Sports Player
- France: covers main channels but missing Eurosport 1/2 France, L'Équipe, Canal+ Décalé, Canal+ Family, beIN MAX

**Complete hard-negative pairs that must be in the registry:**

| Channel A (should NOT match B) | Channel B | Reason |
|---|---|---|
| Sky Sports News | Sky Sports Premier League | "Sky Sports" prefix ambiguity |
| Canal+ Sport | Canal+ Sport 360 | Completely different channels |
| BT Sport 1 | TNT Sports 1 | Rebrand — same channel; now TNT Sports 1 |
| ITV 1 | ITV 1+1 | +1 channels are time-shifted versions |
| Premier League | Sky Sports Premier League | Standalone channel vs Sky Sports sub-channel |
| BBC One Scotland | BBC One | Regional variant, not main network |
| BBC Two Wales | BBC Two | Regional variant |
| Channel 4 +1 | Channel 4 | Time-shifted vs live |
| Sky Sports F1 | Sky Sports Main Event | Both carry F1 but are distinct services |

### 3.2 `normalized_name()` — Specific Improvements Required

```python
def normalized_name(name: str) -> str:
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode()  # drops accents
    name = name.casefold()
    # Remove country prefixes
    for prefix in ("uk:", "gb:", "fr:", "ie:", "de:"):
        if name.startswith(prefix):
            name = name[len(prefix):]
    # Remove quality suffixes
    for suffix in (" hd", " fhd", " 4k", " uhd", " sd", " +1", " plus1", " +7"):
        while name.endswith(suffix):
            name = name[:-len(suffix)]
    # Synonyms
    name = name.replace("be in sports", "bein sports")
    name = name.replace("bbc 1 ", "bbc one ").replace("bbc1 ", "bbc one ")
    name = name.replace("itv one", "itv 1").replace("itv one ", "itv 1 ")
    return name.strip()
```

**Missing from `normalized_name()`:**

1. **`bbc two`/`bbc 2` synonym** — `bbc two` and `bbc 2` should both normalise to `bbc two`
2. **`channel 4` / `c4` / `c 4`** — `c4` is a common abbreviation
3. **`channel 5` / `c5` / `five`** — `five` was the old name; should map to `channel 5`
4. **`sky sports main event` / `sky sports 1`** — historically interchangeable (Sky Sports 1 was renamed to Main Event)
5. **BT Sport → TNT Sports rebrand** — `bt sport 1` should map to `tnt sports 1`
6. **`france 2` / `france2`** — no space variant
7. **`tf1` / `tf 1`** — no space variant
8. **Dot removal** — `sky.sports.football` (Matt Huisman format) → `sky sports football`
9. **Number/word digit normalisation** — `bein sports 1` / `bein sports one` → `bein sports 1`

### 3.3 `canonical_channel()` Strict Country Gate — Assessment

```python
def canonical_channel(source_id, epg_id, display_name):
    name = normalized_name(display_name)
    market = COUNTRY_BY_SOURCE.get(source_id)
    cid = KNOWN_SERVICES.get(name)
    if not cid or not market or not cid.startswith(market.lower() + "."):
        return None
    return cid
```

This is **deliberately strict** and correct for its purpose: avoiding auto-matching ambiguous cross-regional channels. However, some real cases are incorrectly blocked:

- **Pan-European channels in a FR guide:** `Eurosport 1` appears in French EPG with `fr.eurosport.1` ID. The `market = "fr"` and `cid = "eu.eurosport.1"` don't match the strict prefix check → returns None. The fix is to allow `eu.` (pan-European) prefix channels in any European market's guide.
- **UK channels in an Irish guide:** An Irish XMLTV might carry BBC One with country code `gb.bbc.one` — but `market = "ie"` → prefix mismatch → None. The fix is a `MARKET_ALLOWS_FOREIGN` dict that specifies which markets allow which foreign IDs.

---

## Part 4: Storage System Deep Analysis

### 4.1 SQLite WAL Store — Schema Review

```sql
-- kv: configuration and CSRF token
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)

-- snapshots: last-good data per product
CREATE TABLE IF NOT EXISTS snapshots (
    product TEXT PRIMARY KEY,
    updated_at TEXT NOT NULL,
    data TEXT NOT NULL
)

-- jobs: operational log (last 300)
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    recorded_at TEXT NOT NULL
)

-- requests: daily quota accounting
CREATE TABLE IF NOT EXISTS requests (
    provider TEXT NOT NULL,
    utc_day TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(provider, utc_day)
)
```

**Schema gap A: No `source_etag` table for HTTP caching**  
Required:
```sql
CREATE TABLE IF NOT EXISTS source_etags (
    source_id TEXT PRIMARY KEY,
    etag TEXT,
    last_modified TEXT,
    last_checked_at TEXT NOT NULL
)
```

**Schema gap B: No `incidents` table for aggregated failure tracking**  
Required for HA notification threshold logic:
```sql
CREATE TABLE IF NOT EXISTS incidents (
    source_id TEXT PRIMARY KEY,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    first_failure_at TEXT,
    last_failure_at TEXT,
    notified_at TEXT,       -- NULL until notification sent
    resolved_at TEXT        -- NULL until source recovers
)
```

**Schema gap C: No `source_licences` table**  
Required for publication gate enforcement:
```sql
CREATE TABLE IF NOT EXISTS source_licences (
    source_id TEXT PRIMARY KEY,
    reviewed_at TEXT,
    allows_private_collection INTEGER NOT NULL DEFAULT 1,
    allows_public_event_facts INTEGER NOT NULL DEFAULT 0,
    allows_public_programme_text INTEGER NOT NULL DEFAULT 0,
    attribution_required TEXT,
    licence_url TEXT
)
```

### 4.2 Quota Logic — Identified Race Condition

```python
def increment(self, provider: str, limit: int) -> None:
    utc_day = datetime.now(timezone.utc).date().isoformat()
    with self._conn() as db:
        db.execute("INSERT OR IGNORE INTO requests VALUES (?,?,0)", (provider, utc_day))
        row = db.execute("SELECT count FROM requests WHERE provider=? AND utc_day=?", (provider, utc_day)).fetchone()
        if row and row[0] >= limit:
            raise RuntimeError("Daily quota exhausted for %s" % provider)
        db.execute("UPDATE requests SET count=count+1 WHERE provider=? AND utc_day=?", (provider, utc_day))
```

This SELECT-then-UPDATE pattern has a TOCTOU (time-of-check/time-of-use) race condition in WAL mode. If two threads call `increment()` for the same provider simultaneously:
- Both SELECT see count=98 (limit=100)
- Both decide not to raise
- Both UPDATE → count becomes 100 (but two requests were allowed at count=98, potentially both going over)

The fix is an atomic UPDATE with a check:
```python
db.execute("""
    UPDATE requests SET count=count+1
    WHERE provider=? AND utc_day=? AND count < ?
""", (provider, utc_day, limit))
if db.rowcount == 0:
    raise RuntimeError("Daily quota exhausted for %s" % provider)
```
If the row doesn't exist yet, `INSERT OR IGNORE` first, then the UPDATE.

---

## Part 5: Implementation Priority Matrix

This matrix summarises findings from both audit documents with implementation order.

### Sprint 1 (Foundation — 1 week)
1. Fix CI workflow (1-2 hours)
2. Add `subtitle`, `category`, `is_live`, `is_repeat` to `decode_xmltv` (3 hours)
3. Fix `root.clear()` to periodic rather than per-programme (1 hour)
4. Fix `xmltv_time` to handle bare `Z` suffix (1 hour)
5. Fix atomic quota `UPDATE` race condition (1 hour)
6. Add `channel.display-name lang="en"` preference (1 hour)
7. Add `max_programmes=500_000` configurable per-source (1 hour)

### Sprint 2 (Channel Identity — 1 week)
1. Build `schemas/channel_registry.json` (UK + FR full canonical list, 300+ entries) (2 days)
2. Replace inline `KNOWN_SERVICES` with JSON loader in `guide.py` (2 hours)
3. Extend `normalized_name()` with missing synonyms and dot-removal (2 hours)
4. Add `orphaned_programmes` counter to `decode_xmltv` (1 hour)
5. Download iptv-org `channels.json` as a local reference fixture (1 day)

### Sprint 3 (Sports Data Quality — 1 week)
1. Fix API-Sports pagination (replace ValueError with page-loop) (4 hours)
2. Add OpenLigaDB multi-league support with `getlastchangedate` (3 hours)
3. Store Jolpica F1 `circuit_id`, `venue_lat`, `venue_lon`, handle date-only events (2 hours)
4. Store football-data.org `shortName`, `tla`, `stage`, `competition_country` (2 hours)
5. Store API-Sports `goals`, `score` as nullable fields (1 hour)
6. Add API-Sports rugby adapter using same key (4 hours)
7. Add ETag caching to `fetch()` (3 hours)

### Sprint 4 (New Sports — 2 weeks)
1. Tennis adapter (Tennis API, `not_before` start model) (1 day)
2. Cricket adapter (CricketData.org, Test multi-day expansion) (1.5 days)
3. Boxing adapter (card hierarchy, PPV flag) (1 day)
4. SportsAPI.app multi-sport adapter with quota budget matrix (1.5 days)
5. Parallel collection threads (concurrent.futures) (1 day)

### Sprint 5 (Integration and Publication — 1 week)
1. `schemas/sports_events.schema.json` with golden fixtures (1 day)
2. Source licence registry (1 day)
3. Event→broadcaster evidence layer (2 days)
4. `add_allowed_hosts` additions for new providers (1 hour)
5. `/api/health` JSON endpoint (2 hours)
6. HA persistent notification integration (1 day)

---

*This document provides the complete forensic basis for all implementation work in SportsLiveInfo. Every finding is traceable to specific lines of code or specific source API characteristics. The companion audit document (`SOURCES_AND_IMPROVEMENTS_AUDIT_2026-11-12.md`) contains the high-level priority matrix; this document contains the technical specification for each change.*
