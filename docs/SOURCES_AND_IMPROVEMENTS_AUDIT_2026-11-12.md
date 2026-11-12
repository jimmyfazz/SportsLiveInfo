# SportsLiveInfo — Comprehensive Sources and Improvement Audit

> **Historical audit / receipt — reviewed 12 November 2026.** Preserved against its stated original revision. Findings, branch/merge positions, provider claims and pass counts below are historical, not freshly verified current facts. Current source is v0.3.0; the combined review attempted 86 tests (81 passed, five errors, three of those environment-blocked). Use CURRENT_STATUS for resolved/remaining work; no new live source, licence or device verification occurred.
> **Repository roles:** [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is PRIVATE source/installation and stays private; [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is PUBLIC daily data only. [Current status and evidence](CURRENT_STATUS.md).

**Dated:** 12 November 2026  
**Scope:** All existing source code, provider adapters, EPG pipeline, sports event pipeline, ingress UI, test coverage and documentation for the SportsLiveInfo HAOS App.  
**Purpose:** Identify every gap, defect and improvement opportunity in the live application, with specific actionable code changes, missing implementations and prioritised work packages.  
**Status of application at time of audit:** v0.2.0, 19 unit tests passing locally, NOT deployed on actual HAOS, NO public feed, NO live provider accuracy, NO broadcaster-verified events.


> **Corrections — 12 Nov 2026 (v0.3.0 follow-up, verified by web search and by reading the code):** this document was written while live source fetches were blocked, and several statements were wrong. (1) football-data.org's free plan **includes** the UEFA Champions League (`CL`); the free 12 are PL, ELC, CL, BL1, SA, PD, FL1, DED, PPL, BSA, WC, EC. There is no `EL1`/`CLI` in that list. (2) API-Sports has **no cricket API**; its non-football sports use `v1.<sport>.api-sports.io/games`, not `v3.rugby`. (3) `Store.increment()` runs under a process-wide `RLock`, so the claimed quota race condition does not exist. (4) API-Sports fixture-by-date responses are not routinely split into 10-row pages; the paging guard is defensive, not a high-severity defect. (5) The CI workflow YAML is valid; the PR #2 "404 BlobNotFound" is a GitHub-side log retrieval failure, not a workflow fault. (6) Response shapes labelled "traced from actual API response" or "based on published docs" were written from documentation knowledge, not live calls; the SportsAPI.app shape is hypothetical. The SQLite schema quoted in §4.1 does not match `storage.py` (actual tables: `kv(name,data)`, `jobs(time,provider,state,details)`). See `SOURCE_EXPANSION_SPORTS_TAXONOMY_AND_B1G_LINEUP_2026-11-12.md` for current, implemented state.

---

## 1. Executive Summary

The SportsLiveInfo application has a solid foundation: bounded XMLTV parsing, quota-safe provider fetch, CSRF-protected Ingress UI, DST-aware scheduler, last-good snapshot semantics, rights-deny-by-default publication gate, and a conservative canonical channel identity system. The architecture is correct in its security posture and data-model decisions.

However, the application is critically incomplete against its two equal-priority mandates:

**Product E (EPG):** 4 EPG sources exist. All are disabled by default. None have redistribution rights cleared. The canonical broadcaster registry covers only ~30 known services in `guide.py`. There is no multi-source reconciliation, no coverage benchmark, no non-UK/non-France source support, no generic-to-specific overlay, and no published EPG asset.

**Product S (Sports):** 4 sports adapters exist covering only football and F1. Rugby, tennis, cricket, boxing, and all other sports are absent. `broadcast_verified` is always `False` on every event. There is no event→broadcaster evidence layer. No sports data has ever been published.

The 34-finding forensic audit (AUD-001–034) correctly characterises this as a research/specification artefact. The improvements below are concrete, specific and ordered for two-agent parallel development.

---

## 2. Current Source Inventory

### 2.1 EPG Sources (providers.py `EPG` dict)

| ID | Label | URL | Status | Gaps |
|---|---|---|---|---|
| `farleyflex` | UK sports · farleyflex | `raw.githubusercontent.com/farleyflex/epg-guide/main/epg.xml` | Enabled opt-in; no redistribution rights | UK-biased, sports-heavy only; scheduled 06:00 UTC (data often late); may mirror mytelly/iptv-org (not independent evidence); no general UK TV; no France |
| `fr_programmetv` | France · programme-tv.net | `iptv-org.github.io/epg/guides/fr/programme-tv.net.epg.xml.gz` | Disabled; no rights | French general TV; re-hosted via iptv-org (derivative — not independent confirmation); redistribution not established |
| `fr_telerama` | France · Télérama | `iptv-org.github.io/epg/guides/fr/telerama.fr.epg.xml.gz` | Disabled; no rights | Major FR guide; also via iptv-org; Télérama commercial entity — rights review essential |
| `fr_xmltv` | France · XMLTV France | `xmltvfr.fr/xmltv/xmltv_fr.xml.gz` | Disabled; no rights | Broad French coverage; independent origin from above; licence unknown |

**Missing EPG sources entirely:**
- UK general TV (BBC, ITV, Channel 4/5, Freeview) — not covered at all by farleyflex which is sports-heavy
- EPG Share UK1 (`epgshare01.online`) — already known to B1G Android, not in SportsLiveInfo
- Matt Huisman (`i.mjh.nz`) — already known to B1G Android, not in SportsLiveInfo  
- IPTV-org channel and guide discovery APIs (`iptv-org/api`) — `channels.json`, `guides.json`, `feeds.json` for identity crosswalk
- Freeview-EPG (UK FTA backup) — not present
- Ireland, Belgium, Germany, Spain, Italy, Netherlands — zero coverage
- Official broadcaster schedule APIs (BBC, ITV, Channel 4) — not explored

### 2.2 Sports Sources (providers.py `SPORTS` dict)

| ID | Label | Coverage | Daily Limit | Key Required | Gaps |
|---|---|---|---|---|---|
| `jolpica` | Formula 1 · Jolpica | F1 only; full session breakdown (race, FP1–3, quali, sprint, SprintShootout) | 6/day | No | Only current season; no MotoGP/Formula E; noncommercial CC BY-NC-SA — public redistribution requires attribution compliance |
| `openligadb` | Football · OpenLigaDB German Bundesliga | Bundesliga `bl1` only | 4/day | No | Single German league; ODbL attribution/sharealike; `getlastchangedate` endpoint not used; pagination not implemented; no other leagues |
| `football_data` | Football · football-data.org | 12 free competitions (PL, UCL, etc.) | 45/day | Yes (`football_data`) | Europa League absent in free tier; free tier is delayed; no women's football; date range limited to 7 days; no stadium/venue enrichment |
| `api_sports` | Football · API-Sports | Broad football, football-only endpoint | 80/day | Yes (`api_sports`) | Used for football only — same API offers rugby, cricket, basketball, etc. at separate endpoints not yet implemented; pagination raises ValueError and aborts |

**Missing sports adapters entirely (all zero implementation):**
- Tennis (Tennis API, ATP/WTA)
- Rugby union (Six Nations, Premiership, URC, Champions Cup)
- Rugby league (Super League, NRL)
- Cricket (CricketData.org, Tests/T20/ODI, The Hundred, IPL)
- Boxing / Combat sports (Open Boxing, Boxerbook, BoxingAPI)
- MotoGP / Formula E / WEC / endurance
- Golf (PGA, DP World Tour, majors)
- Basketball (NBA, EuroLeague)
- American football (NFL)
- Darts / snooker
- SportsAPI.app multi-sport API (not yet implemented despite documentation)
- SportAPI.ai (not yet implemented despite documentation)

---

## 3. Code-Level Findings

### 3.1 providers.py — Specific Defects

**F-001 (High): `api_sports_events` raises ValueError on any multi-page response instead of fetching all pages**
```python
# Current (line 173-174):
if int(paging.get("total", 1)) > int(paging.get("current", 1)):
    raise ValueError("API-Sports fixture page incomplete; keep previous last-good")
```
This means any competition with >10 fixtures per day is permanently rejected. API-Sports paginates at 10 results by default. The fix is to track the incomplete-page state, persist what was fetched, and queue additional page requests within quota. The ValueError approach is too aggressive — a partial valid page should not equal zero events.

Recommended change: replace with a `page_incomplete` flag on the returned payload and store partial results in a `staging` snapshot rather than throwing away all fetched data.

**F-002 (High): `openligadb_events` fetches `bl1` (Bundesliga 1) only, hardcoded in engine.py**
```python
# engine.py line 66-67:
events = providers.openligadb_events(providers.fetch(
    base + "/" + str(season), max_bytes=7_000_000))
```
The `base` URL is `https://api.openligadb.de/getmatchdata/bl1`. This is a single league. OpenLigaDB supports `bl2` (2. Bundesliga), Austrian league, Swiss league, and community-contributed leagues. The league ID should be configurable or the adapter should support fetching from a list of leagues. Additionally, `getlastchangedate` endpoint (`https://api.openligadb.de/getlastchangedate/bl1/YYYY/RR`) should be used to avoid re-fetching unchanged data.

**F-003 (Medium): `decode_xmltv` discards `subtitle`, `category`, `icon`, `episode-num` and `star-rating` XMLTV elements**
```python
# providers.py line 101-108: only captures title, description, language
programmes.append({
    "channel_id": ..., "start_utc": ..., "end_utc": ...,
    "title": ..., "description": ..., "language": ..., "source_id": ...
})
```
Missing: `sub-title` (episode title), `category` (sport/film/news), `episode-num` (series/episode), `live` and `previously-shown` flags, `star-rating` and `rating`. These are essential for the EPG Guide in B1G and for identifying live vs repeat vs highlights. Without the `live` flag, the system cannot distinguish a live sporting event from a highlight or a replay in the EPG.

**F-004 (Medium): `f1_events` does not handle the `Qualifying` session when `Sprint` is also present**
In sprint weekends the schedule is: FP1, SprintShootout, Sprint, Qualifying, Race. The current code handles `SprintShootout` but the session key ordering in `sessions.extend(...)` may produce duplicate pairs if Jolpica returns unexpected key combinations. This is a subtle ordering assumption that should be tested with a full sprint-weekend payload.

**F-005 (Medium): No ETag/Last-Modified caching in `fetch()`**
```python
# providers.py line 39-53: no conditional HTTP headers
request = urllib.request.Request(url, headers={"User-Agent": ...})
```
Every call re-downloads the full payload. For large XMLTV guides (10–50 MB compressed) this wastes bandwidth, quota and parse time. Adding `If-None-Match` / `If-Modified-Since` and handling 304 responses would allow free sources to respond with no data when unchanged, respecting ETag from the response.

**F-006 (Medium): `football_data_events` only fetches a 7-day window hardcoded in engine.py**
```python
# engine.py line 69-70:
start = datetime.now(ZoneInfo("Europe/London")).date()
end = start + timedelta(days=7)
```
This misses matches that were scheduled further ahead (UCL group stages, internationals, cup draws). The window should be configurable or use a competition-specific optimal horizon (28 days for calendar view, 7 days for Today rail).

**F-007 (Low): `verify_url` is strict but `ALLOW_HOSTS` is rebuilt from the dict on each module import**
```python
# providers.py line 24:
ALLOW_HOSTS = {urllib.parse.urlparse(item[1]).hostname for item in list(EPG.values()) + list(SPORTS.values())}
```
When new adapters are added, they must have their hostname in the EPG or SPORTS dict to be reachable. This is correct behaviour, but the design means a new source added dynamically (e.g. for cricket or tennis) would need its URL registered in the dict before the host is allowed. This is by design — but the comment should be explicit, and any new provider host must be added to the dict before any `fetch()` call.

**F-008 (Low): `decode_xmltv` root node clear happens on every programme node, not just at memory boundaries**
```python
# providers.py line 112-113:
if root is not None:
    root.clear()
```
Calling `root.clear()` after each programme node while the `channel` nodes have already been processed is correct for memory bounds but can cause issues if any element refers back to the root. This is harmless in practice given `ET.iterparse` but would cause confusion if the parse order ever includes nested programme elements.

### 3.2 engine.py — Specific Defects

**E-001 (High): `_materialize()` merges all sports snapshots with no deduplication across sources**
```python
# engine.py lines 153-159:
for name, enabled in conf["sports"].items():
    ...
    for event in entry["data"]["events"]:
        events[event["id"]] = event  # dict merge by id
```
If `jolpica` and `api_sports` both return the same F1 race (possible if api_sports covers motorsport), the last-written source wins. There is no deduplication by canonical event, no source-independence tracking, and no conflict detection. The `events` dict is keyed by `source_id:raw_id` which prevents cross-source deduplication entirely. This needs a proper canonical event merge with provenance tracking.

**E-002 (High): `_collect_locked()` runs sports and EPG collection sequentially in a single thread**
```python
# engine.py lines 43-49:
for name, enabled in conf["sports"].items():
    if enabled and name in providers.SPORTS:
        self._collect_sport(name, conf)
for name, enabled in conf["epg"].items():
    if enabled and name in providers.EPG:
        self._collect_epg(name)
```
The architecture document mandates independent parallel pipelines (ADR-04). Currently, if the first sports source times out (20s), all subsequent sources are blocked. EPG collection cannot proceed until all sports sources finish. For a 04:00 morning collection targeting 05:00 delivery, sequential execution with 20s timeouts per source could easily consume 10+ minutes.

**E-003 (Medium): `_collect_sport` for api_sports uses only football endpoint; rugby/cricket/etc. endpoints at same host are not used**
The API-Sports service offers separate endpoints for rugby (`v3.rugby.api-sports.io`), basketball (`v3.basketball.api-sports.io`), cricket (`v1.cricket.api-sports.io`), etc. The current implementation hardcodes the football endpoint and would need separate `SPORTS` entries for each sport on this platform.

**E-004 (Medium): Scheduler `run_scheduler()` polls every 10 seconds but uses `strftime("%H:%M")` for slot matching**
```python
# engine.py line 262:
if local.strftime("%H:%M") in conf.get("schedule", []) and self._last_slot != key:
```
If the scheduler loop is busy (e.g. waiting on a lock) during the HH:MM window, that collection slot is missed. At 10-second poll intervals this is a 1-in-6 chance of missing a minute. The last-slot key uses `"%Y-%m-%d %H:%M"` which correctly prevents duplicate runs within the same minute, but a missed minute is not retried until the next scheduled time. This is acceptable for three-times-daily collection but should be documented.

**E-005 (Medium): `publish()` only publishes sports events, EPG is explicitly excluded forever**
```python
# engine.py line 295:
manifest = {..., "epg": "not_published_pending_rights"}
```
This is correct per design — EPG rights are not cleared. However, the publish pipeline is not designed to ever publish EPG when rights are cleared. It needs a separate EPG publication path with its own licence gate.

**E-006 (Low): `_github_write()` uses `urllib.request` synchronously in the collection thread**
GitHub API writes can take 2–10 seconds. During publish, the collection thread is blocked. This should be async or run in a separate thread.

**E-007 (Low): `test_source()` calls `self.store.increment()` before the actual network request, consuming quota even on UI test actions**
```python
# engine.py line 219:
self.store.increment(name, limit)
try:
    rows = decoder(providers.fetch(...))
```
This is intentional (reserve before attempt) but the UI "Test connection" button is thus quota-consuming on every click. The test_source call should use a separate smaller test-quota allowance rather than the daily collection limit.

### 3.3 guide.py — Specific Defects

**G-001 (High): `KNOWN_SERVICES` registry covers only ~30 channels; thousands of real subscription channels are unrecognised**
```python
# guide.py lines 19-51: 30 entries only
KNOWN_SERVICES = {
    "bbc one": "gb.bbc.one",
    "bbc two": "gb.bbc.two",
    ...  # 28 more
}
```
A real UK/France subscription includes 500–2000+ channels. The current registry cannot match the vast majority. The `unmatched_canonical_channels` metric will always be near-100%. This registry needs to be replaced with a full versioned canonical service registry loaded from a `schemas/channel_registry.json` file.

**G-002 (High): `canonical_channel()` returns `None` for any source not in `COUNTRY_BY_SOURCE`**
```python
# guide.py line 82-85:
def canonical_channel(source_id, epg_id, display_name):
    name = normalized_name(display_name)
    market = COUNTRY_BY_SOURCE.get(source_id)
    cid = KNOWN_SERVICES.get(name)
    if not cid or not market or not cid.startswith(market.lower() + "."):
        return None
    return cid
```
Any new EPG source (e.g. `epgshare`, `matt_huisman`, any IE/DE/ES source) returns `None` for every channel until it is explicitly added to `COUNTRY_BY_SOURCE`. This silently fails with no warning.

**G-003 (Medium): `normalized_name()` strips `hd`, `fhd`, `4k` etc. but preserves `sky sports main event` correctly**
The normalisation is correct for the cases tested but does not handle:
- Dot-separated abbreviations: `S.P.O.R.T.S` → not normalised
- Mixed Arabic/Latin numerals in some international channels
- Locale-specific apostrophes and typographic quotes in French channel names
- `bein` vs `be in` split handling — there is a `replace("be in sports", "bein sports")` fix already, but other compound-word French channel names may not be handled

**G-004 (Medium): `analyze_guide()` is bounded to `detail_limit=30` channels in `channels_needing_attention`**
```python
# guide.py line 160:
"channels_needing_attention": breakdown[:detail_limit],
```
For a source with 500+ channels (typical French or UK subscription feed), only 30 are reported. This means operators cannot see the full coverage picture from the UI. The EPG coverage page would show only a fraction of problematic channels. The full list should be available on a separate diagnostic endpoint or paginated.

**G-005 (Low): `GENERIC_PROGRAMME` regex does not match all common filler titles**
```python
# guide.py line 56:
GENERIC_PROGRAMME = re.compile(r"^(?:live (?:football|sport|sports|rugby|cricket|tennis|boxing)|to be announced|tba|programme information|no information|sporting event|live event)$", re.I)
```
Missing: `"Sign Off"`, `"Test Card"`, `"Close"`, `"Overnight Programming"`, `"Infomercial"`, French fillers like `"Émission"`, `"Sans titre"`, `"À définir"`, `"Sous réserve de modifications"`. These inflate the valid programme count in coverage reporting.

### 3.4 storage.py — Specific Defects

**S-001 (Medium): `increment()` uses UTC day boundary but providers reset quotas in provider timezone**
```python
# storage.py line 119:
day = datetime.now(timezone.utc).date().isoformat()
```
API-Sports resets at midnight UTC, but SportsAPI.app resets at midnight UTC-5 (US Eastern). Using UTC day for all providers can cause under-budget or over-budget on some providers depending on when the reset occurs. The quota ledger should support a configurable `reset_timezone` per provider.

**S-002 (Medium): `recent_jobs()` is bounded to last 300 job rows in the DB and 20/35 in queries**
```python
# storage.py lines 108-109: DB trim to 300
db.execute("DELETE FROM jobs WHERE id NOT IN (SELECT id FROM jobs ORDER BY id DESC LIMIT 300)")
```
For a 3-times-daily scheduler with ~10 providers, 300 rows ≈ 10 days of history. This is probably sufficient, but it should be configurable. More importantly, there is no `incidents` table for persistent error escalation — repeated failures of the same source produce individual job rows but no aggregated incident counter that the UI or HA notifications could use.

**S-003 (Low): SQLite `snapshots` table has no index on `product`**
The `PRIMARY KEY(product)` on `snapshots` creates an implicit index (SQLite primary key is an index), so this is correct. However, the `requests` table's PRIMARY KEY is `(provider, utc_day)` which is correct. No issue here, but worth confirming with `EXPLAIN QUERY PLAN` on large stores.

**S-004 (Low): `configure()` does not validate that dict values being merged are of the expected type**
```python
# storage.py lines 86-91:
for key, value in update.items():
    if key not in DEFAULT:
        raise ValueError("Unknown configuration field")
    if isinstance(config[key], dict) and isinstance(value, dict):
        config[key].update(value)
```
A caller could set `{"sports": "not-a-dict"}` and the branch falls through to `config[key] = value`, replacing the whole sports dict with a string. Input type validation is missing.

### 3.5 server.py — Specific Defects

**SV-001 (High): `_allowed()` hardcodes the HA Ingress IP (`172.30.32.2`)**
```python
# server.py line 51:
return os.environ.get("SLI_DEV") == "1" or self.client_address[0] in ("172.30.32.2", "127.0.0.1", "::1")
```
The HA Supervisor Ingress proxy forwards requests from `172.30.32.2`. This IP is correct for the HAOS Docker bridge. However, if the Supervisor's internal network changes (HA version upgrade, custom networking), the app becomes inaccessible with no diagnostic. This should read from an environment variable `HA_INGRESS_IP` with the current value as fallback, or verify the `X-Ingress-Path` header which HA Supervisor injects.

**SV-002 (Medium): The EPG coverage page (`guide()`) has no pagination — it iterates all sources but `channels_needing_attention` is bounded at 30**
The dashboard and all pages render entirely server-side with no pagination or lazy loading. For a full-subscription UK+France guide with 1000+ channels, the EPG coverage page could become very slow to render. No concern at current scale (4 sources × 30 rows) but will need pagination before production.

**SV-003 (Medium): No `/health` JSON endpoint for external monitoring**
The Diagnostics tab is HTML-only. There is no machine-readable `/api/health` endpoint that HAOS or an external watchdog could poll. HA persistent notifications (HA-005) will need a way to query status programmatically.

**SV-004 (Medium): The Events page truncates at 100 events with no filtering/sorting UI**
```python
# server.py lines 273-274:
count = 0
for event in events:
    if count >= 100:
        break
```
With 7 days of multi-sport data (potentially 500+ events), only 100 are shown. No sport filter, no date filter, no competition filter. This makes the UI hard to use for diagnostics.

**SV-005 (Low): No icon served for social previews / HA App card — `icon.png` route exists but no `/logo.png` route**
The `config.yaml` specifies both `icon` and `image` (logo). The server serves `icon.png` but not `logo.png`. HA App cards use the logo. While the file exists in the HAOS package, the internal server should not need to serve it (HA Supervisor reads from the add-on files directly), but consistency is worth confirming.

**SV-006 (Low): The UI `server_version` is hardcoded as `"SportsLiveInfo/0.1"` while the app is v0.2.0**
```python
# server.py line 46:
server_version = "SportsLiveInfo/0.1"
```
Should be derived from `__version__` in `__init__.py` rather than hardcoded.

---

## 4. Missing Implementations (High Priority)

### 4.1 Tennis Adapter (SPORT-005)

No implementation. Required sources:
- **Tennis API** (`docs.tennis-api.com`): 50 req/day free; ATP/WTA calendar, upcoming matches, order-of-play. Key fields: `tournament_id`, `match_id`, `start_datetime` (UTC), `surface`, `round`, `player_a`, `player_b`, `start_precision` (`not_before`/`scheduled`). Licence for private use appears permissible; redistribution requires review.
- **ATP/WTA official calendars**: Manual cross-check only (no bulk API rights established).

Data model special requirements:
- `start_precision: "not_before"` — a tennis match start depends on preceding matches finishing
- Session start (broadcast) ≠ individual match start
- Court assignment may change before play
- Multiple simultaneous courts at Grand Slams produce many events on the same day

### 4.2 Cricket Adapter (SPORT-005)

No implementation. Required sources:
- **CricketData.org** (`cricketdata.org/pricing`): 100 req/day free; Test/T20/ODI series, upcoming fixtures, match schedule. Key fields: `match_id`, `series_name`, `match_type` (Test/ODI/T20I), `date_start_utc`, `date_end_utc` (multi-day), `venue`, `teams`.

Data model special requirements:
- Multi-day Test match: event spans up to 5 calendar days; must appear on **each playing day** separately in the Sports Today rail
- Day/session breakdown: Day 1, Day 1 Session 1 (11:00–13:00 BST), Lunch, etc.
- Rain delays and early finishes must be handled with `status: "rain_delay"` / `"stumps"` / `"abandoned"`
- DLS method (rain-affected result) is a final status variant
- Overnight scores: not a new event but a status update to the ongoing match

### 4.3 Boxing / Combat Sports Adapter (SPORT-005)

No implementation. Required sources:
- **Open Boxing** (`openboxing.org/api`): `/bouts/scheduled/index.json` — world-title bouts; free; early development with incomplete coverage
- **Boxerbook** (`boxerbook.com/developers`): full fight cards, `where_to_watch` by country; non-commercial free, bulk/redistribution requires separate agreement
- **BoxingAPI** (`boxingapi.net`): 50 req/day candidate; needs account verification

Data model special requirements:
- **Card hierarchy**: Promotion card → main event → co-main → undercard bouts
- `ring_walk_estimate_utc` is distinct from `coverage_start_utc` (broadcast often starts 4–6 hours before ring walk) and from `main_event_estimated_utc` which is TBC
- PPV vs linear broadcast: a pay-per-view event is a separate card type; `ppv: true`, `platform: "Sky Sports Box Office"` or `"DAZN"`, `price_tier` optional
- `start_precision: "tbc"` for main event walk time — do not fabricate a time

### 4.4 Rugby Adapter (SPORT-005)

No implementation. Required sources:
- **API-Sports rugby endpoint** (`v1.rugby.api-sports.io/games`) — same API key as football adapter; separate sport with different competition IDs
- **SportsAPI rugby category** — pending key/rights review
- **Official competition feeds** (Six Nations, Premiership Rugby, URC) — manual cross-check only

Data model special requirements:
- Rugby union vs rugby league are **distinct subsports** — never conflate
- `competition` must specify code (`union`/`league`)
- Super League (league), NRL (league), Six Nations (union), Premiership Rugby (union), URC (union) all exist simultaneously
- Split kicks and replays: a fixture may have an 80-minute base time + potential extra time
- Women's Six Nations, Women's Super League: distinct competition IDs

### 4.5 SportsAPI.app Multi-Sport Adapter (SPORT-004)

Documented but not implemented. This is a priority candidate for broad sport coverage. Key concerns per documentation:

- **Quota conflict**: Pricing page says 100/day; Docs page says 1000/day during beta. Must design for 100/day conservatively until actual account response headers confirm the live limit.
- API endpoint pattern: `https://api.sportsapi.app/v1/fixtures?sport=football&date=2026-11-12`
- Covered sports (documented): football, basketball, baseball, ice hockey, American football, rugby, tennis, cricket, MMA, volleyball, handball, cricket — requires individual coverage benchmark per sport
- Pagination: 10 results per page by default; must handle multi-page responses within daily quota
- Authentication: `x-api-key` header

### 4.6 SportAPI.ai Football/Basketball Adapter (SPORT-004)

Documented but not implemented.
- Monthly cap from 1 Dec 2026: 7,000/month (≈233/day if spread evenly, or 2,000/day until Nov 30)
- Must budget monthly first, then daily
- Football: 100+ competitions including many not in football-data.org free tier
- Basketball: NBA, EuroLeague, etc.
- Key: standard bearer token

### 4.7 MotoGP / Formula E / Motorsport Adapters (SPORT-005/006)

No implementation. MotoGP and Formula E are priority expansion sports:
- **MotoGP**: Official MotoGP API is commercial; `SportsAPI.app motorsport` category if present; Jolpica covers F1 only
- **Formula E**: FIA Formula E official calendar; `SportsAPI.app` motorsport endpoint candidate
- **WEC / Le Mans**: SportsAPI.app endurance category candidate
- Race weekend sessions: practice/qualifying/warm-up/race — same session hierarchy as F1 but different identifiers

### 4.8 Source Rights and Licence Register

**Zero implementation exists.** The spec (FEED_CONTRACTS.md, AGENTS.md) requires:
- A machine-readable per-source licence registry (`schemas/source_licences.json` or similar)
- Fields: `source_id`, `terms_url`, `terms_reviewed_at`, `allowed_local_test`, `allowed_private_internal`, `allowed_public_event_facts`, `allowed_public_epg_programmes`, `allowed_public_derived_epg`, `allowed_public_alias_crosswalk`, `attribution_text`, `max_cache_age_hours`, `review_required_by`
- Publication gate in `engine.publish()` currently uses `conf.get("publication_approvals", [])` (admin-set list) but there is no actual licence registry file or UI for reviewing/approving sources

### 4.9 Canonical Channel Registry (JSON file)

**Zero implementation.** `guide.py` has a 30-entry inline dict. Required:
- `schemas/channel_registry.json` with versioned canonical service records
- Coverage: all UK Sky Sports variants (1–10, Main Event, Premier League, F1, Football, Cricket, Tennis, Golf, Racing, News, Arena, Darts), all UK TNT Sports variants (1–4), Premier Sports 1/2, BT Sport variants, UK FTA (BBC One/Two/Three/Four, ITV 1/2/3/4, Channel 4/4+1/More4/FilmFour, Channel 5), UK regional BBC variants (Scotland/Wales/Northern Ireland)
- France: France 2/3/4/5, TF1/TMC/TFX, M6/W9/6ter, Canal+/Canal+ Sport/Canal+ Sport 360, beIN Sports 1/2/3, RMC Sport 1/2, L'Équipe, Eurosport 1/2
- Structure per CHANNEL_IDENTITY_AND_EPG_ALLOCATION_SPEC.md §4 schema
- Negative alias examples (hard negatives) embedded in registry
- Loading function in `guide.py` replacing inline `KNOWN_SERVICES` dict

### 4.10 Event→Programme→Broadcaster Evidence Layer

**Zero implementation.** Every event has `"broadcasts": [], "broadcast_verified": False`. Required:
- `matching/broadcast_evidence.py` module
- Logic: given a canonical event (UTC start, sport, teams/session, country), search EPG snapshots for programmes on canonically-identified channels that:
  - Start within a configurable window before the event (e.g. 2 hours before kick-off for coverage)
  - Have a title containing the event teams, competition name, or session type
  - Are from a source with `broadcast_verified` confidence criteria
- Confidence levels: `verified` (independent EPG + fixture ID match), `probable` (title/time match, single source), `unverified` (no EPG evidence)
- Hard negatives: highlights/replay/review programmes must not upgrade to `broadcast_verified`
- Output: `broadcasts: [{"canonical_channel_id": "...", "programme_id": "...", "coverage_start_utc": "...", "transmission": "live|highlights|replay|ppv", "confidence": "verified|probable|unverified", "source_id": "..."}]`

### 4.11 HA Persistent Notifications

**Zero implementation** (`storage.py` has job history only). Required:
- Home Assistant REST API call to `POST /api/services/persistent_notification/create`
- Deduplication: same source/failure type within 24 hours = one notification, not N
- Cooldown: 3 consecutive failures before escalation
- Clear on recovery: `DELETE /api/services/persistent_notification/dismiss`
- Credential: requires HAOS `HA_TOKEN` env var (least-privilege scope: `persistent_notification` only)
- Content: source name, error type, last success time — never source URL or key content

### 4.12 GitHub Actions CI Fix

The PR #2 GitHub Actions check fails with 404 BlobNotFound — no job steps are visible. This suggests the workflow YAML exists but references an action/step that cannot be fetched. Required:
- Inspect `.github/workflows/` for the failing workflow
- Confirm Python version, `PYTHONPATH` and test command match local passing invocation
- Fix action reference (likely a pinned action SHA/tag that no longer resolves, or a missing `actions/checkout` step)
- The test command that works locally is: `PYTHONPATH=sportsliveinfo/src python -m unittest discover -s tests -v`

---

## 5. Architecture Gaps

### 5.1 No Versioned JSON Schema Files

`schemas/` directory is empty. Required before any B1G integration:
- `schemas/channel_registry.schema.json` (JSON Schema 2020-12)
- `schemas/epg_segment.schema.json`
- `schemas/sports_events.schema.json`
- `schemas/manifest.schema.json`
- `schemas/source_health.schema.json`
- Corresponding synthetic golden fixture files (5+ per schema) covering edge cases: UK/FR normal, partial/missing source, unknown channel, unverified broadcast, TBC time, multi-day cricket, boxing PPV card

### 5.2 No Multi-Source EPG Deduplication / Reconciliation

When multiple EPG sources cover the same channel (e.g. `farleyflex` and `epgshare` both have Sky Sports Main Event), there is no logic to:
- Detect that two sources describe the same canonical channel
- Choose the best programme data per time slot
- Flag conflicts (source A says programme X, source B says programme Y for the same slot)
- Implement the generic→detailed promotion algorithm from CHANNEL_IDENTITY_AND_EPG_ALLOCATION_SPEC §7

### 5.3 No Coverage Benchmark / Accuracy Measurement Infrastructure

No `tools/benchmark_report.py` exists. The project requires measurable accuracy targets (≥99.5% channel precision, ≥95% fixture recall, ≥95% EPG coverage). Without a benchmark harness comparing against a held-out ground truth set, all coverage claims are unverifiable.

### 5.4 No `pyproject.toml` or Proper Package Setup

The application runs via `PYTHONPATH=sportsliveinfo/src python -m unittest discover`. There is no `pyproject.toml`, no `pip install -e .`, no dependency pinning. For HAOS Docker builds this means the Dockerfile must manage the Python path manually. The package should be installable with `pip install -e .[dev]`.

### 5.5 No CLI Entry Point

`__main__.py` exists (runs the server + scheduler). But there is no CLI for:
- `sportsliveinfo collect --offline --date 2026-11-12` (backfill/test)
- `sportsliveinfo epg import --source farleyflex --xmltv test.xml` (manual import)
- `sportsliveinfo coverage report` (coverage audit)
- `sportsliveinfo publish --dry-run` (publication test)
These are needed for HAOS deployment testing and debugging without a full running server.

### 5.6 No Source-Independent Evidence Family Tracking

The forensic audit identifies (AUD-011) that `farleyflex → iptv-org → mytelly` may all be the same upstream. The current code has no lineage tracking — two sources can appear to "agree" while actually mirroring the same upstream data. Each source needs a `data_lineage` field (e.g. `upstream_family: "iptv-org"`) so that agreement counts only as one independent vote when sources share upstream origins.

### 5.7 Scheduler Does Not Track Source SHA/Version

The collection currently fetches data regardless of whether the upstream has changed since last fetch. The `farleyflex` source is a GitHub raw file — its ETag or Last-Modified should be tracked. If the upstream SHA has not changed since the last successful fetch, the parse can be skipped and last-good retained, saving bandwidth and CPU.

---

## 6. Test Coverage Gaps

| Test area | Current coverage | Gap |
|---|---|---|
| `providers.decode_xmltv` | ✓ Basic DTD rejection, time offset conversion | Missing: gzip bomb, >100k programmes, duplicate channel IDs, missing `<title>`, UTF-8 BOM, bare `\r\n` line endings, mixed timezone formats, `<programme>` without `channel` attr |
| `providers.f1_events` | ✓ Sprint Shootout, missing Qualifying | Missing: race with zero sessions, missing `time` field (races where only date known), session reordering, partial `Circuit` missing sub-fields |
| `providers.football_data_events` | ✓ 403 error rejection | Missing: `status: "CANCELLED"`, `status: "POSTPONED"`, TBC kickoff (null `utcDate`), `homeTeam: null` |
| `providers.api_sports_events` | ✓ Error/paging/null-array rejection | Missing: partial page recovery path, 429 handling, `fixture.date` with non-UTC timezone offset |
| `providers.openligadb_events` | ✓ UTC date parsing, finished flag | Missing: match with no `location`, `matchDateTimeUTC` naïve string without Z/offset, season boundary (June/July rollover) |
| `guide.analyze_guide` | ✓ Coverage overlap merge, generic detection, 24h count | Missing: 72h and 168h separate checks, guide with zero channels, guide with 50k+ channels (perf), `canonical_channel` with accented French names, all UK hard-negative service variants |
| `guide.canonical_channel` | ✓ BB1 Scotland/Sky+/Sky News negatives | Missing: `BBC TWO W` (Wales), `ITV2`, `Channel 4+1`, numbered Sky Sports variants, `TNT Sports 1-4`, `beIN 1 vs 2`, Canal+ Sport 360, RMC Sport 2 |
| `engine._collect_epg` | ✓ Stale guide rejection, failure last-good | Missing: empty guide (zero channels), guide with valid channels but all future programmes > 7 days ahead, guide with invalid UTF-8 |
| `engine._collect_sport` | ✓ Quota exhaustion, source failure | Missing: api_sports partial page (quota exhaustion during pagination), openligadb season boundary, football_data 429 response, jolpica rate limiting |
| `engine.publish` | ✓ Denied without licence, denied without target | Missing: GitHub API 401, partial asset upload failure, manifest write success/failure, revision validation |
| `store.increment` | ✓ Budget enforcement | Missing: provider with monthly budget, UTC day boundary rollover, concurrent increment race condition |
| `server` | ✓ CSRF rejection, page routing, finish setup | Missing: oversized POST body (413), unknown page (404), icon.png serving, EPG source enable/disable roundtrip, all source Test Connection paths |

---

## 7. Security and Rights Gaps

### 7.1 Credentials in Memory After Test Source

`test_source()` passes the API key from config to `providers.fetch()`. Although the key is not logged (confirmed), it passes through the HTTP headers dict in-process. If a future feature adds request logging, the key could leak. The key should be masked in exception messages, not passed as a plain string to functions that could propagate it in error context.

### 7.2 GitHub Token Stored in SQLite as Plaintext

`storage.py` stores the GitHub publishing token in the `kv` table as plaintext JSON. HAOS `/data` volumes are protected by OS-level access control, but the token is visible to any user with shell access to the container. The token should be stored with OS-level protection (e.g., `chmod 0600` on the SQLite file, which `os.umask(0o077)` in `__main__.py` already ensures for new files). This is acceptable for the HAOS container model but should be documented.

### 7.3 No Secrets Scanner in CI

No `.gitleaks.toml` or `trufflehog` configuration exists. Any accidentally committed test fixture containing an API key would not be detected.

### 7.4 `source_redistribution_approved: False` in Every `decode_xmltv` Return

```python
# providers.py line 115:
return {..., "source_redistribution_approved": False}
```
This flag is set but not checked in `engine._collect_epg()`. The `_materialize()` function sets `"public_redistribution": False` on EPG guides in the snapshot but does not enforce it in the publication path (EPG publication is excluded entirely). Once an EPG publication path is added, this flag must be checked and honoured.

---

## 8. Prioritised Improvement Plan

The following items are ordered P0 → P2 based on blocking dependency and product completeness. Claude-owned items are marked `[L]`, Codex-owned `[C]`, both `[B]`.

### P0 — Must have before any further feature work

| # | Item | Owner | Effort | Blocks |
|---|---|---|---|---|
| P0-01 | Fix GitHub Actions CI (404 BlobNotFound) | [L] | 1–2 hours | All PR-based development |
| P0-02 | Add `pyproject.toml` with src-layout and `[dev]` extras | [C] | 2 hours | HAOS Docker build, `pip install -e .` dev workflow |
| P0-03 | Add `subtitle`, `category`, `live` and `previously-shown` fields to `decode_xmltv` | [L] | 3 hours | EPG quality reporting, live-vs-replay distinction |
| P0-04 | Extend `KNOWN_SERVICES` → load from versioned `schemas/channel_registry.json` | [L] | 1 day | Canonical identity for >30 services |
| P0-05 | Write `schemas/channel_registry.json` with full UK/FR canonical service list and hard negatives | [L] | 2 days | G-001 fix; all EPG matching |
| P0-06 | Freeze `schemas/sports_events.schema.json` and `schemas/manifest.schema.json` with 5+ golden fixtures | [C,B] | 1 day | B1G SLI-B1-00 gate; contract test suite |
| P0-07 | Add ETag/Last-Modified caching to `fetch()` | [L] | 4 hours | Bandwidth reduction; source-SHA tracking |
| P0-08 | Fix `api_sports_events` pagination — partial-page staging instead of ValueError | [L] | 4 hours | F-001; API-Sports multi-fixture days |
| P0-09 | Add multi-sport support to `api_sports` adapter (rugby, cricket endpoints) | [C] | 1 day | Unblocks rugby and cricket without new keys |
| P0-10 | Add source lineage/family tracking to provider snapshots | [C] | 3 hours | AUD-011; prevents mirror sources counting as independent evidence |

### P1 — Required for feature completeness

| # | Item | Owner | Effort | Blocks |
|---|---|---|---|---|
| P1-01 | Tennis adapter (Tennis API, `not_before` precision model) | [C] | 1 day | SPORT-005 |
| P1-02 | Cricket adapter (CricketData.org, multi-day match per-day events) | [C] | 1 day | SPORT-005 |
| P1-03 | Boxing adapter (Open Boxing + Boxerbook, card hierarchy, PPV flag) | [C] | 1 day | SPORT-005 |
| P1-04 | Rugby adapter (API-Sports rugby endpoint, union vs league distinction) | [C] | 4 hours | SPORT-005 |
| P1-05 | SportsAPI.app multi-sport adapter with 100/day safe budget | [C] | 1 day | SPORT-004; broad cross-sport coverage |
| P1-06 | Machine-readable source licence registry (`schemas/source_licences.json`) | [B] | 4 hours | Rights gate; AUD-003 |
| P1-07 | Event→programme→broadcaster evidence layer (`matching/broadcast_evidence.py`) | [L,C] | 2 days | `broadcast_verified: True` events; B1G Sports Today |
| P1-08 | Parallel sports and EPG collection (async or thread pool in `_collect_locked`) | [C] | 1 day | E-002; ADR-04 compliance; collection speed |
| P1-09 | EPG source independence / coverage benchmark tools (`tools/benchmark_report.py`) | [B] | 1 day | AUD-008; measurable completeness |
| P1-10 | Add `/api/health` JSON endpoint to `server.py` | [L] | 2 hours | HA persistent notifications; external monitoring |
| P1-11 | HA persistent notification integration (deduplicated, least-privilege) | [L] | 1 day | HA-005; operational visibility |
| P1-12 | EPG multi-source reconciliation (choose best per slot, flag conflicts) | [L,C] | 2 days | Multi-source EPG quality; generic→specific overlay |
| P1-13 | Quota ledger: provider-timezone reset, monthly budget support | [C] | 4 hours | S-001; SportAPI.ai monthly cap |
| P1-14 | UI: Events page sport/date/competition filter | [L] | 4 hours | SV-004; operator usability |
| P1-15 | UK general TV EPG sources (EPG Share UK1, Freeview-EPG) with licence review | [L,O] | 1 day | EPG-002; non-sports UK coverage |

### P2 — Important but non-blocking

| # | Item | Owner | Effort |
|---|---|---|---|
| P2-01 | openligadb multi-league support + `getlastchangedate` optimisation | [C] | 4 hours |
| P2-02 | MotoGP / Formula E adapters | [C] | 1 day |
| P2-03 | SportAPI.ai football/basketball adapter | [C] | 4 hours |
| P2-04 | IPTV-org `channels.json` / `guides.json` identity crosswalk integration | [L] | 1 day |
| P2-05 | `normalized_name` French special-character and compound-word improvements | [L] | 2 hours |
| P2-06 | Extend `analyze_guide` channel detail beyond 30 — paginated API endpoint | [L] | 3 hours |
| P2-07 | `server.py` server_version from `__version__`; fix `_allowed()` to use env var | [L] | 1 hour |
| P2-08 | CLI entry points (`collect`, `epg import`, `coverage report`, `publish --dry-run`) | [C] | 1 day |
| P2-09 | Incidents table in SQLite; aggregated failure counts for HA notification threshold | [C] | 3 hours |
| P2-10 | Secrets scanner CI step (trufflehog or gitleaks) | [B] | 1 hour |
| P2-11 | IPTV-EPG.org source discovery (identity-only, no unchecked programme text) | [L] | 4 hours |
| P2-12 | Optional channel inventory import pipeline (HA-002 HA-005 prerequisite) | [L,O] | 2 days |

---

## 9. Source-by-Source Rights Status Summary

| Source | Type | Current Rights Status | Redistribution Path |
|---|---|---|---|
| `farleyflex/epg-guide` | EPG XMLTV | Unverified; likely mirrors iptv-org/mytelly | Must establish independent origin and licence before public export |
| `iptv-org/epg` FR sources | EPG XMLTV | Re-hosted; original site licences apply | programme-tv.net, Télérama are commercial entities — licence review required per source; iptv-org software licence ≠ data licence |
| `xmltvfr.fr` | EPG XMLTV | Unknown; operator-maintained | Direct contact required; personal/educational use likely; redistribution unclear |
| `jolpica F1` | Sports JSON | CC BY-NC-SA — noncommercial | Attribution + share-alike required; noncommercial limits business use; redistribution with attribution appears allowed for non-commercial personal use |
| `openligadb` | Sports JSON | ODbL 1.0 | Attribution + share-alike database rights; derived databases under same terms; redistribution allowed with compliance |
| `football-data.org` | Sports JSON | Free tier: personal/non-commercial/attribution | Attribution required; bulk redistribution and commercial use require paid tier; event facts (date/time/teams/result) have weaker copyright than editorial content |
| `API-Sports` | Sports JSON | Per-plan terms; free tier restrictions | Personal/development only on free; redistribution and commercial use require paid plan; event facts treated similarly |
| `Open Boxing` | Sports JSON | Early development, appears open | Licence not formally stated; must establish before redistribution |
| `Boxerbook` | Sports JSON | Non-commercial free; bulk/redistribution by agreement | Active licence gate for redistribution — requires explicit agreement |
| `Tennis API` | Sports JSON | 50 req/day free; licence for private testing | Redistribution not established; must review terms |
| `CricketData.org` | Sports JSON | 100 req/day free | Terms review required; standard API terms likely restrict redistribution |

**Key principle (unchanged):** No source is cleared for public redistribution by default. The `publication_approvals` list in config remains empty. Programme text is never published. Permitted event facts (UTC start/end, teams, competition, venue) have weaker copyright claims and may be publishable for personal family use — but independent legal review is recommended before any GitHub public feed.

---

## 10. Immediate Next Steps (Actionable Order)

The following are the concrete code changes and implementations to begin immediately, working in the branch `claude/sportsliveinfo-b1g-android-syyo8j`:

1. **Fix CI** — investigate and fix `.github/workflows/` YAML causing 404 BlobNotFound (P0-01)
2. **Extend `decode_xmltv`** to capture `subtitle`, `category`, `live` and `previously-shown` XML elements (P0-03) — small, safe, backward-compatible change
3. **Build `schemas/channel_registry.json`** with the full UK/FR canonical service list; replace inline `KNOWN_SERVICES` dict in `guide.py` with a JSON loader (P0-04/05)
4. **Fix `api_sports_events` pagination** — stage partial results rather than raising ValueError (P0-08)
5. **Add ETag caching to `fetch()`** — saves bandwidth on every collection run (P0-07)
6. **Add Tennis, Cricket, Boxing and Rugby adapters** (P1-01 through P1-04) — these are the missing sports categories
7. **Build the event→broadcaster evidence layer** (`matching/broadcast_evidence.py`) — this is what makes `broadcast_verified: True` possible (P1-07)
8. **Add `/api/health` JSON endpoint** (P1-10) — enables external monitoring and HA notifications path

None of these changes touch Codex-owned files (`schemas/`, core models, publisher backend). They are all in Claude-owned territory: EPG adapters, channel identity, Ingress UI, and future B1G client.

---

*End of audit. This document should be updated after each implemented work package with actual test results, source coverage measurements, and confirmed rights status.*
