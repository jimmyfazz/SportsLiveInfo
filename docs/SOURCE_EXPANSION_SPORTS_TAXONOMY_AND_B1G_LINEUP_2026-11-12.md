# SportsLiveInfo v0.3.0 — Source expansion, sports sub-categories and B1G lineup cross-reference

> **Historical audit / receipt — reviewed 12 November 2026.** Preserved against its stated original revision. Findings, branch/merge positions, provider claims and pass counts below are historical, not freshly verified current facts. Current source is v0.3.0; the combined review attempted 86 tests (81 passed, five errors, three of those environment-blocked). Use CURRENT_STATUS for resolved/remaining work; no new live source, licence or device verification occurred.
> **Repository roles:** [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is PRIVATE source/installation and stays private; [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is PUBLIC daily data only. [Current status and evidence](CURRENT_STATUS.md).

**Dated:** 12 November 2026 · **Branch:** `claude/sportsliveinfo-b1g-android-syyo8j`
**Status:** SOURCE IMPLEMENTED + LOCAL TESTED (43/43 offline tests). **No live provider call was made from this environment** (outbound access to provider hosts is blocked here). Every new source is **disabled by default** and must pass the Ingress *Test connection / Test EPG* button on the HAOS mini PC before use. HAOS install, real quotas and live accuracy remain **NOT VERIFIED**.

This document supersedes the source counts in `SOURCES_AND_IMPROVEMENTS_AUDIT_2026-11-12.md` and `FORENSIC_SOURCE_AND_LOGIC_INVESTIGATION_2026-11-12.md`. Both now carry a corrections banner; see §8.

---

## 1. What changed, in numbers

| Area | v0.2.0 | v0.3.0 |
|---|---|---|
| Sports fixture sources | 4 (Jolpica, OpenLigaDB bl1, football-data.org, API-Sports football) | **16** (see §2) |
| Sports recognised | football, F1 | **24 sports** (football, rugby union, rugby league, cricket, tennis, motorsport, boxing, MMA, golf, darts, snooker, horse racing, cycling, athletics, basketball, American football, ice hockey, baseball, handball, volleyball, Australian rules, netball, other) |
| Competition sub-categories | none | **127**, of which **47 football** (§4) |
| EPG guide feeds | 4 (UK sports + 3 FR) | **27** across GB, IE, FR, US, CA, AU, NZ, HK, MY, SG, GE, PT, PL, GR, IN (§3) |
| Recognised channel services | 31 (GB/FR) | **~74** across 8 markets, plus exact farleyflex tvg-id crosswalk |
| Lineup families reported | none | **41** (Sky Sports, Sky Sports+, TNT, Premier Sports, beIN, Setanta, Now HK, Astro, DAZN, ESPN/ESPN+, Peacock, Paramount+, Kayo/Stan, Fubo, Coupang, Vidio/Mola, SSC, Fite, FloSports/SuperLeague+…) |
| Cross-source fixture fusion | last-write-wins by provider id (duplicates shown twice) | **de-duplicated**, with corroboration count and start-time-conflict flag |
| "Live today" view | none | **New Ingress page** grouped by sport → competition with featured England / home nations / PPV row |
| Event → channel | none (`broadcast_verified: false` always) | **EPG broadcast candidates** (unverified) with hard negatives |

---

## 2. Sports sources

| ID | Coverage | Key | Free allowance (as researched) | Implementation notes |
|---|---|---|---|---|
| `jolpica` | F1 practice, qualifying, sprint, race | none | conservative 6/day | Now also fetches **next season from October** (closes the Dec–Feb gap); date-only races kept as `date_only` instead of dropped; normalised `session` field |
| `openf1` **new** | F1 sessions with **end times** (2023+) | none | free public API [1] | Independent second F1 source → corroboration and accurate "live now" windows |
| `openligadb` | Bundesliga, **2. Bundesliga, 3. Liga** (configurable) | none | conservative 12/day | One scope per league; a failed league keeps its previous fixtures |
| `football_data` | Free 12 competitions: **PL, Championship, Champions League**, BL1, Serie A, La Liga, Ligue 1, Eredivisie, Primeira Liga, Brazil Série A, World Cup, Euros [2] | yes | 10 calls/min; delayed scores [2] | `SCHEDULED` now maps to `provisional` (kick-off not fixed), `TIMED` to `scheduled`; adds competition code, stage, matchday, short names |
| `api_sports` | Football worldwide incl. **FA Cup, EFL Cup, Europa League, Conference League, internationals**, WSL, Scottish football | yes | 100/day per API [3] | Adds league id/country/round; `TBD` → `time_tbc` |
| `api_sports_rugby` **new** | Rugby union & league | same key | 100/day [3] | Union vs league resolved only by named competition |
| `api_sports_basketball` **new** | NBA, **WNBA**, EuroLeague… | same key | 100/day | |
| `api_sports_hockey` **new** | NHL, EIHL… | same key | 100/day | |
| `api_sports_nfl` **new** | NFL, NCAA | same key | 100/day | Decoder handles the nested `game` object |
| `api_sports_baseball` **new** | MLB… | same key | 100/day | |
| `api_sports_afl` **new** | AFL | same key | 100/day | |
| `api_sports_handball`, `api_sports_volleyball` **new** | | same key | 100/day each | |
| `api_sports_mma` **new** | UFC, PFL… bouts | same key | 100/day | Bout times marked `estimated` |
| `thesportsdb` **new** | Soccer, rugby, cricket, motorsport, fighting, golf, **darts, snooker**, tennis, ice hockey, basketball, American football, cycling, horse racing (selectable) | public free key `123` [4] | ~30/min; free-tier event data is partial [4] | One call per sport per day; paced at 2.1 s. Whether `eventsday.php` is free-tier is disputed in third-party docs [4] — the Test button settles it |
| `cricketdata` **new** | Tests, ODIs, T20Is, franchise T20 | yes | 100 hits/day lifetime free [5] | **Test matches expand to one record per playing day** (Day 1 `scheduled`, Days 2–5 `not_before`). Provider requires the key in the query string; it is never logged or stored, and the echoed `apikey` field is discarded |

**One API-Sports key now serves all ten API-Sports sports.** Keys are stored by provider account, not by sport. Each sport API has its own daily allowance and its own local quota counter.

**Collection engine changes** (`engine.py`): a table-driven `_plan()` per provider; per-provider pacing; **scoped partial saves**, so a failed day, league or sport keeps its previous data while the others refresh; a quota exhaustion mid-run keeps the scopes already fetched; sports providers run in **parallel lanes** (thread pool, max 6) while EPG guides share one sequential lane to bound memory on the mini PC; past day-scoped fixtures are pruned after 2 days.

---

## 3. EPG guide feeds

All feeds are private (programme text never published). "Verify" means the URL follows a confirmed naming pattern but has not been fetched; use Test EPG.

| ID | Market | Source of URL | Notes |
|---|---|---|---|
| `farleyflex` | GB sports | existing; B1G `BroadcasterEpgAliases` | Detailed Sky/TNT/Premier fixtures in `<sub-title>`; **exact tvg-id crosswalk added** |
| `uk_freeview` **new** | GB FTA | Freeview-EPG (dp247) [6] | ~48 h, refreshed ~8-hourly, personal use, scraped from Sky/Freeview/Freesat [6] |
| `mjh_sky_uk` **new** | GB Sky | **B1G backup feed list** | |
| `iptvorg_sky_uk` **new** | GB Sky | B1G backup feed list (verify) | iptv-org may no longer publish pre-built guides [7]; also affects `fr_programmetv`/`fr_telerama` |
| `epgtalk_uk`, `epgtalk_sports` **new** | GB / multi-country sports | B1G suggested feeds | `epgtalk_sports` has no single market, so no exact identity; family coverage only |
| `epgshare_uk` **new** | GB broad | B1G backup feed list | |
| `epgshare_ie`, `_fr`, `_us`, `_hk`, `_my`, `_ca`, `_au`, `_nz`, `_pt`, `_pl`, `_gr`, `_sg`, `_in` **new** | IE, FR, US, HK, MY, CA, AU, NZ, PT, PL, GR, SG, IN | `epg_ripper_<CC>1` pattern; UK1/US1 in B1G, FR1 [8], HK1 in B1G register | Market set taken from the owner's provider categories |
| `iptv_epg_fr` **new** | FR | B1G backup feed list | Terms not explicit (B1G keeps it user-selected only) |
| `iptv_epg_hk`, `iptv_epg_ge` **new** | HK (Now/beIN), GE (**Setanta**) | B1G 10 Nov register entry (verify) | |
| `iptvorg_foxtel_au` **new** | AU | B1G backup feed list (verify) | |
| `fr_programmetv`, `fr_telerama`, `fr_xmltv` | FR | existing | `fr_xmltv` is the racacax/XML-TV-Fr project [9] |

Upstream **families** are recorded (`EPG_FAMILY`): epgshare, iptv_org, iptv_epg_org, epgtalk, mjh, farleyflex, freeview_epg, xmltvfr. Two guides from one family never count as independent evidence.

**XMLTV parser additions** (`decode_xmltv`): `sub-title`, up to 5 `category`, `<live/>`, `<previously-shown/>`, `<premiere/>`, `episode-num`, HTTPS channel icon URL, English `display-name` preferred, `...Z` times accepted, orphaned-programme count, per-source download/programme limits (up to 60 MB / 300k programmes for national guides), bounded `root.clear()`.

---

## 4. Sports sub-categories ("live action today")

`taxonomy.py` classifies every event deterministically. It uses a provider code first (football-data code, API-Sports league id, OpenLigaDB shortcut), then an exact country-qualified name, then a name prefix. Anything else stays in `<sport>.other` under its raw competition name. Ambiguous names are resolved **within a sport and country**:

- "Premier League" (England) is the Premier League; in Egypt it goes to `football.other`; in darts it is Premier League Darts.
- "League Cup" in England is the EFL Cup; in Scotland it is the Scottish League Cup.
- "FA Cup" with country Scotland is the Scottish Cup.
- "Serie A" in Brazil is the Brasileirão.
- "Super League" is rugby league in rugby and Greek football in Greece.
- "US Open" is resolved separately in tennis and golf.
- "Challenge Cup" is resolved separately in rugby union and rugby league.

**Football rows, in display priority order:**
1. **England (men) internationals.** A participant must be exactly "England" in an international competition (World Cup, Euros, Nations League, qualifiers, friendlies) or an unclassified one.
2. England Women internationals.
3. Scotland, Wales, Northern Ireland & Ireland internationals.
4. England U21.
5. Premier League, Champions League, Europa League, Conference League, FA Cup, EFL Cup (Carabao), Championship, League One, League Two, EFL Trophy, Community Shield, WSL, Women's Champions League.
6. Scottish Premiership, Scottish Cup, Scottish League Cup.
7. World Cup, Euros, Nations League, World Cup and Euro qualifying, international friendlies, Club World Cup, UEFA Super Cup.
8. La Liga, Serie A, Bundesliga, Ligue 1, Eredivisie, Primeira Liga, 2. Bundesliga, 3. Liga, European domestic cups.
9. MLS, Brasileirão, Saudi Pro League, Libertadores, Liga MX, Argentina, NWSL, A-League, K League, Liga 1 Indonesia, Ekstraklasa, Greek Super League, Scandinavian leagues, ISL.

The other sports have equivalent tables:

| Sport | Competitions |
|---|---|
| Rugby union | Six Nations, Women's Six Nations, Autumn internationals, World Cup, Premiership, URC, Champions Cup, Challenge Cup, Rugby Championship, Tests, Top 14, Super Rugby, PWR |
| Rugby league | Super League, Challenge Cup, internationals, NRL, State of Origin, Championship |
| Cricket | England (men) and England Women internationals, Ashes, ICC events, The Hundred, T20 Blast, County Championship, IPL, BBL, SA20, other T20 leagues |
| Tennis | Grand Slams, Tour Finals, Davis Cup, BJK Cup, United Cup, ATP Tour, WTA Tour |
| Motorsport | F1, MotoGP, Formula E, WEC, IndyCar, BTCC, WRC, F2/F3, NASCAR |
| Combat | Boxing world and British titles; UFC, PFL, ONE, Bellator (PPV tag for B1G's pinned PPV card) |
| Golf | Majors, Ryder/Solheim Cup, DP World Tour, PGA Tour, LPGA/LET, LIV |
| Darts | Worlds, Premier League, majors |
| Snooker | Worlds, UK Championship, Masters, ranking events |
| Horse racing | Major festivals |
| Cycling | Grand Tours |
| US and other sports | NBA, WNBA, NFL, NCAA, NHL, EIHL, MLB, AFL |

**Featured row:** any event tagged England, England Women, Scotland, Wales, Northern Ireland, Ireland, British & Irish Lions, Great Britain, or PPV, in any sport. Rugby and other non-football sports keep their competition row (e.g. Six Nations) and appear in the featured row through the tag.

**Live state:** `live` (provider says so), `live_probable` (now is between start and end, or start + typical duration for the sport), `upcoming`, `probably_finished`, `finished`, `postponed`, `cancelled`, `time_tbc`. No future event is labelled live.

---

## 5. B1G repository cross-reference (requested)

**There is no channel roster in the B1 repo.** The master register states the requested "channel roster workbook awaits a sanitized source catalogue; no local M3U/channel export exists". Channels come from the owner's IPTV provider at runtime and stay on each TV, which is correct for privacy. What B1 does contain, and how it is now used:

| B1 artefact | Content | Used in SportsLiveInfo |
|---|---|---|
| `SkyGuideScene.kt` `backupFeeds` | EPG Share UK1/US1, Matt Huisman Sky UK, iptv-org Sky UK/Foxtel/TVTV, iptv-org FR ×2, XMLTV France, IPTV-EPG.org FR, EPGTalk UK/Sports, farleyflex | All added as `EPG` sources (TVTV US excepted; EPG Share US1 covers US) |
| `BroadcasterEpgAliases.kt` / `sports-epg-aliases.ts` | farleyflex tvg-ids for Sky Sports ×11, TNT 1–4, Premier 1–2 (incl. source spelling `skysportspremiereleague.uk`) | `SOURCE_ID_CROSSWALK` — exact, strongest identity evidence |
| `HomeSportsEvents.kt` | Aggregate/red-button exclusions, previously-shown exclusion, sub-title fixture reading | Mirrored in `linking._NEGATIVE` and `is_repeat` exclusion |
| Register 9 Nov | Owner categories `LIVE\|EPL Hub`, `LIVE\|Rugby Events`, `LIVE\|Cricket events`, `LIVE\|EUFA CL/EL/CFL`, `LIVE\|F1/MOTO GP`, `PPV`, `LIVE\|PPV Events`; example `MYS \| Astro Premier League FHD` | Taxonomy rows, PPV tag, `my.astro.premier_league` |
| Register 10 Nov | 54 category families; EPG Share HK1, IPTV-EPG.org Hong Kong/Georgia; beIN/PPV/FloSports/Setanta event slots | HK/GE feeds, Setanta/beIN/FloSports families. **Gap:** the referenced `audit/SPORTS_EPG_COVERAGE_AUDIT_2026-11-10.md` and the HK1 feed code are **not on any of the 248 B1 branches**. That work appears unpushed |
| Owner screenshots (this session) | UK Sky Sports / Sky Sports+ / TNT / Premier Sports GB / Amazon Prime / HBO Max; IE; IN/PK; US networks + MLB/NBA/WNBA/NFL(+Game Pass)/NHL + team channels; CA; AR Shahid SSC; INT Australia/NZ/Caribbean/Scandinavia; PT/SC Sports; Argentina, Latin, Asian Sports, Poland, Singapore, Greek, Malaysian, Fite TV; SPORTS \| Now HK, NZ Sky Sports, OneFootball, Paramount+, Peacock, Setanta, Stan Sports, SuperLeague+/Florugby, Tennis Channel, TSN+, Vidio/Mola, beIN MAX/Media, Astro Sports, Coupang Play, DAZN CA/GB, ESPN+, FloSports, Fubo, Hub Sports, Kayo, World Sports | 41 channel families; 13 EPG Share regional guides; API-Sports US-sport/AFL adapters; taxonomy rows for WNBA, NWSL, A-League, K League, Liga 1, Ekstraklasa, Greek SL, Argentina, Liga MX, Scandinavia, AFL |

**Important finding: most streaming event families have no XMLTV guide.** Peacock, Paramount+, ESPN+, DAZN, Fubo, Kayo, Stan, Coupang, Vidio, OneFootball, Fite, FloSports, Amazon Prime and HBO Max usually expose numbered event slots ("Peacock 05: …") rather than a schedule. For those, the only safe binding is **event-name matching on the TV** against SportsLiveInfo's fixture list (B1G `bindScheduleOnlyEvents` already does this). The EPG Coverage page now shows per-family channel counts so you can see which families each guide actually covers.

---

## 6. EPG broadcast candidates (event → channel)

For each of today's events, `linking.broadcast_candidates()` looks for a programme on a **recognised channel** (exact crosswalk id or market service table) that:

- covers kick-off (starts by kick-off + 20 min and runs until at least kick-off + 30 min), and
- has title/sub-title containing **both teams' full token sets** (for F1: "F1/Formula 1/Grand Prix" plus the session word).

**Hard negatives** exclude:
- highlights, review, reaction, preview, classic, replay, magazine, build-up, debate and analysis programmes;
- repeats (`previously-shown`);
- unrecognised channels (e.g. Sky Sports+ or regional variants);
- wrong opponents (Manchester United is never Manchester City).

**Status values:** `single_guide_match`, or `multi_guide_match` when two different upstream families agree on the same channel. **`broadcast_verified` stays false** until guide upstream independence is proven and the owner signs off the verification rule (LINK-002). These EPG-derived fields are stripped from any GitHub publication.

---

## 7. Further sources identified but not implemented

| Source | Why not yet | Next step |
|---|---|---|
| MotoGP Pulselive JSON (`…pulselive…/motogp/v1`) [10] | Undocumented; two conflicting hostnames | Owner confirms; probe once; then an adapter |
| ESPN site API (unofficial scoreboards incl. tennis/golf) [11] | Undocumented, single-vendor risk; B1G audit already flags it | Only with owner acceptance |
| TheSportsDB v2 `filter/tv/day` (televised events) [12] | Premium-only | If the owner buys a supporter key, this gives broadcaster evidence |
| AcesAPI / Oddspapi tennis [11] | Small free credits; tennis order-of-play precision | Evaluate after the TheSportsDB tennis test |
| iptv-org `channels.json` / `guides.json` [13] | Identity crosswalk, not schedules | Import as a local reference fixture for EPG-007 |
| globetvapp/epg (FR and others) [8] | File names unknown | Inspect the repo, then add |
| Boxerbook / Open Boxing | Redistribution needs agreement; coverage immature | Private test only |
| SportsAPI.app / SportAPI.ai | Live quota and terms unverified; not reachable from this sandbox | Verify on the HAOS box |

---

## 8. Corrections to earlier documents (now bannered in both)

1. football-data.org's free plan **includes the Champions League** (`CL`) [2]. The earlier claim that it was excluded, and the `EL1`/`CLI` codes, were wrong.
2. API-Sports has **no cricket API**. Rugby and the other sports are `v1.<sport>.api-sports.io/games`, not `v3`.
3. The quota "race condition" does not exist: `Store.increment` is serialised by an `RLock`.
4. The API-Sports "10 results per page" claim was unfounded. The guard is defensive.
5. The CI workflow YAML is valid. PR #2's 404 BlobNotFound is a GitHub-side log fetch failure.
6. Response shapes described as "traced from actual responses" were written from documentation knowledge; the SportsAPI.app shape was hypothetical.

---

## 9. Remaining improvements (forensic deep dive, prioritised)

**P0, before relying on live data**
1. Run Test connection for every source you intend to enable on the HAOS box. Record the result, real quota headers and terms in `IMPLEMENTATION_PROGRESS.md`.
2. Verify the API-Sports league ids in `taxonomy.py` against one `/leagues` call. Names remain the fallback match.
3. Measure memory/time for the large guides (EPG Share UK1/US1). If too heavy, move EPG storage from one JSON blob to a streamed SQLite `programmes` table (EPG-001).
4. Get owner sign-off on the broadcast verification rule (which family combinations, plus the live flag, count as verified).

**P1**
5. Add HTTP `ETag`/`If-Modified-Since` caching and `Retry-After` handling for 429 responses.
6. Add a monthly quota ledger (SportAPI.ai-style caps) and provider-timezone resets.
7. Add a per-sport/per-competition **recall benchmark** against a hand-checked day (target ≥95% for priority rows).
8. Import a sanitised owner lineup (names only, no URLs) to compute coverage per family. This is the missing B1G "54 families" workbook.
9. Publish fixture-only feed rows (no EPG text) for name-binding of streaming event slots on the TV.
10. Add HA persistent notifications for repeated source failures (HA-005).
11. Expand `SERVICES` per market from real guide channel lists (start with the HK/MY/GE/US/AU guides once fetched).

**P2**
12. Add a tennis order-of-play adapter.
13. Add a boxing card hierarchy (ring-walk vs coverage start).
14. Expand MotoGP sessions.
15. Make the Ingress Today page auto-refresh.
16. Add CSV export of the family coverage table.

---

## 10. Verification receipts

```
PYTHONPATH=sportsliveinfo/src python -m compileall -q sportsliveinfo/src   # OK
PYTHONPATH=sportsliveinfo/src python -m unittest discover -s tests        # Ran 43 tests — OK
```

The 24 new tests cover:
- taxonomy (England, home nations, U21, country-qualified ambiguous names, sport-scoped names, PPV);
- all new decoders, including failure payloads;
- XMLTV new fields;
- B1G crosswalk and international markets;
- lineup families;
- cross-source fusion and its no-merge cases;
- F1 merge with OpenF1 end times;
- start-time conflicts;
- single- and multi-guide candidates and their hard negatives;
- Today grouping, featured row and live state;
- day-scoped partial failure, and quota exhaustion mid-plan;
- materialisation end-to-end;
- stripping private fields from publication;
- shared API-Sports key, source options, and the Today/Events pages.

**NOT RUN:** any live provider request, Docker build, HAOS install, B1G device test.

## Sources

1. [OpenF1 (jentic listing)](https://jentic.com/apis/openf1.org/openf1) · [OpenF1 API overview](https://freeapihub.com/apis/openf1-api)
2. [football-data.org quickstart](https://api.football-data.org/documentation/quickstart) · [football-data.org free tier limits 2026](https://www.thestatsapi.com/blog/football-data-org-free-tier-limits-2026)
3. [API-Sports rugby (free 100 requests/day)](https://api-sports.io/sports/rugby) · [api-football.com sports list](https://api-football.com/sports)
4. [TheSportsDB API documentation](https://www.thesportsdb.com/documentation) · [TheSportsDB provider notes (teamarr)](https://pharaoh-labs.github.io/teamarr/reference/providers/tsdb)
5. [CricketData.org pricing](https://cricketdata.org/pricing/) · [CricketData.org live score API](https://cricketdata.org/cricket-live-score-api/)
6. [Freeview-EPG (dp247)](https://git.tdem.in/dp247/Freeview-EPG)
7. [iptv-org/epg fork note on pre-made guides](https://github.com/tohenk/iptv-org-epg) · [iptv-org/epg](https://github.com/IPTV-org/epg)
8. [globetvapp/epg](https://github.com/globetvapp/epg) · [NextPVR forum: epgshare01 UK/FR files](https://forums.nextpvr.com/showthread.php?tid=66275)
9. [HACF forum: xmltvfr.fr / racacax/XML-TV-Fr](https://forum.hacf.fr/t/programme-tnt-fr-programme-tv-des-chaines-francaises-dans-home-assistant-sans-iframe-filtrage-par-chaine/83653)
10. [MotoGP Pulselive notes](https://aractetool.pages.dev/motogp) · [Apify MotoGP scraper](https://apify.com/artsiom_k/motogp-scraper.md)
11. [Tennis API review (sportsapis.dev)](https://sportsapis.dev/tennis-api)
12. [TheSportsDB v2 migration notes](https://epgoat-internal-docs.pages.dev/reference/API_V2_MIGRATION.html)
13. [iptv-org/api README](https://cdn.jsdelivr.net/gh/iptv-org/api@master/README.md)
