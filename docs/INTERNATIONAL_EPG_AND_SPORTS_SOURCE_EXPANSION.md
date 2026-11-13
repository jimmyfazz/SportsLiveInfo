# International EPG and worldwide sporting-event source strategy

> **Current documentation context — reviewed 12 November 2026.** Current source has 27 EPG candidates and 16 sports adapter entries. The larger provider strategy below includes research-only candidates; external endpoint, quota and terms claims retain their original research date.
> **Repository roles:** [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is PRIVATE source/installation and stays private; [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is PUBLIC daily data only. [Current status and evidence](CURRENT_STATUS.md).

**Research and specification:** 12 November 2026. **Status:** candidate sources, not live integrations or granted redistribution licences. **Products E and S have equal importance.**

## A. Discovery strategy: EPG and sport are independent

**EPG coverage:** inventory real channels and programmes across UK, France, then additional countries actually received in B1G. Need *all genres* for the channel Guide, not merely sports. Collect rolling programme intervals, descriptions/ratings where permitted, source attribution and last-verified timestamps. Pair compatible sources and retain manual/source-specific mapping.

**Sport coverage:** discover actual events on a specified date **even if no TV EPG lists them**, including F1 venue and sessions, boxing bouts/card, football clubs, rugby, cricket and tournament-specific start precision. A second pass finds *verified* per-event UK/FR/other territory broadcasts, as linear channels and OTT/PPV. TV programme existence alone is not a full fixture calendar.

**Convergence:** link event→programme→canonical broadcaster and independent time evidence, while preserving orphan EPG programmes and untelevised fixtures. Never infer TV carriage solely from season rights.

## B. EPG: international source candidates and realistic coverage

| Source/family | Priority scope | Role | Limitation and owner action |
|---|---|---|---|
| B1G native provider XMLTV (Xtream/M3U/other) | Per-subscription | Local existing baseline, source of available streams | Account-specific URL may embed credentials; NEVER central/public by default; retain local B1G processing |
| [farleyflex/epg-guide](https://github.com/farleyflex/epg-guide) | GB sports/premium | Existing B1 supplemental Sky/TNT/Premier detailed channel guide | Upstream origin may be mytelly via iptv-org; derivative EPG may not be redistributable; late 06:00 UTC scheduled collection; compare actual commit revision |
| [EPG Share UK1](https://epgshare01.online/) | GB | Additional existing B1 backup | Verify freshness, channel programme quality, licence, source independence |
| [Matt Huisman](https://i.mjh.nz/) | GB Sky / AU/NZ | Existing B1 candidate | Source-specific service ids, rights and uptime must be validated |
| [iptv-org/epg](https://github.com/iptv-org/epg) | International | Guide collection references; curated output feeds | Collector software licence is not blanket programme-data reuse licence; source websites retain rights |
| [iptv-org/api](https://github.com/iptv-org/api) | International | Channel identity, languages/countries/guide-ID catalogues | `channels.json`, `guides.json`, `feeds.json` are useful for identities; NEVER use `streams.json` for subscription or playback stream selection |
| [IPTV-EPG.org guides](https://iptv-epg.org/guides) | 65-country index, including GB/FR | Candidate source inventory for identified countries | Provider-listed "free" refers to fetch, not proven redistribution; large US/CA feeds especially expensive to parse; source quality by channel must be benchmarked |
| Existing B1 French guides | FR | `programme-tv.net`, `telerama.fr`, `xmltvfr.fr` guide paths in B1 Android | Legal access/redistribution not established; validate Canal+/beIN/RMC service editions |
| [Freeview-EPG](https://github.com/dp247/Freeview-EPG) | GB free-to-air | Regional UK FTA testing and backup | Personal-use programme dataset; not whole Sky/TNT coverage |
| [TVmaze schedule API](https://www.tvmaze.com/api) | Selected TV shows / episode air dates | Optional *secondary* cross-check for serialised programme air dates, CC BY-SA | Not a replacement for a linear nationwide full-channel XMLTV guide; licence/attribution and sharealike; never claim programme-level time completeness |
| Broadcaster official programme schedules | GB, FR and discovered markets | Best independent spot-check for named programme | No general globally licensed public bulk API established; check exact terms/structured calendars, use only permitted endpoints |
| B1 user-approved custom feeds | Any | Local extras | Keep per-account source URLs and authentication in B1; do not publish externally |

**Verified from B1 Android source:** Existing `SkyGuideScene.kt` already references FR programme-tv.net, Télérama, XMLTV France, and UK EPG Share/other backups. Don't automatically declare those free for central republishing. The Android `BroadcasterEpgAliases.kt` has 17 farleyflex-specific IDs; maintain source-aware crosswalks, and expand only when validated against real channel lists.

### Tiered geographical coverage

- **Tier E0 (mandatory):** GB + FR general TV, sport, regional variants and premium channels actually in B1G and permitted by source rights. Verified day+next seven days where available.
- **Tier E1 (conditional from inventory):** IE, BE, CH, DE, ES, IT, PT, NL, AU, US, CA, Latin-American and other European countries received in account; include language/region/variant constraints.
- **Tier E2 (opt-in):** other countries from safe inventory; discovery can cover the world, but an actual guide requires an authorised source and measured coverage.
- **Never import all 65 countries blindly**, and never copy an entire 1m-programme US guide unless actual selected channels warrant it and the rights permit.
- **Priority within a region:** visible/played channels; current/future horizon; then hidden/unsubscribed only as lightweight non-personal channel identity metadata. Hidden settings remain local TV state, no server uploads.

### Programme-quality scorecard (per channel/source/market)

Measure: recognised channel ID rate; actual forward hours available 0/6/24/72/168; blank/generic title fraction; valid interval share; overlap/replay/timezone errors; stale/future programme window; programme-source lineage; agreement with official spot-checks. Source 'last GitHub commit' does not establish channel programme correctness.

Support `present`, `partial`, `stale`, `no_licence`, `unmatched`, `conflict`, `source_down`. A real programme schedule is more than a channel name or a programme category.

## C. Sports — priority competitions and source candidates

### Cross-sport foundation

| Candidate | Key coverage and official link | Free allowance / actual caveat | Activation |
|---|---|---|---|
| [SportsAPI.app](https://sportsapi.app/docs/catalog/sports-coverage) | Publisher advertises 24 sports and fixtures vs race endpoint families; coverage API shows actual leagues/sports | [Rate docs](https://sportsapi.app/docs/limits) say 1000/day beta; [pricing](https://sportsapi.app/pricing) says 100/day. **Conflict. Use 100/day planning budget, inspect real response headers and contract.** Some sport-wide requests paginate by 10 leagues | Targeted candidate, not complete-source guarantee |
| [SportAPI.ai](https://sportapi.ai/pricing) | Football and basketball; documented date fixtures, 100+ football competitions | 1000/day, **7000/month from Dec 1, 2026** (2000/day/14000 until Nov 30 according to pricing). Every API call may count, even errors. | Excellent optional football cross-check, budget monthly first |
| [football-data.org](https://www.football-data.org/pricing) | 12 free football comps including PL/UCL/World Cup | 10/min and delayed schedule/results; Europa League absent in free competition list | Stable priority football adapter |
| [OpenLigaDB](https://www.openligadb.de/en/license) | Community German and other user-contributed leagues | No account, ODbL 1.0 attribution/sharealike, fair use `getlastchangedate`; no editorial review | Legal-friendly reference/cross-check for covered competitions |
| [OpenFootball](https://github.com/openfootball/football.json) | CC0 historical/selected football fixture JSON | Auto-regenerated files can be stale if original source text not updated | Fallback/reference only |
| [TheSportsDB](https://www.thesportsdb.com/docs/api) | Sports and some TV listings | Free endpoint result caps; 2026 terms restrict published app-store usage; logo/trademark rights | Restricted, no production dependency |
| [API-Sports](https://api-sports.io/) | Existing B1 football API, separate rugby and F1 APIs | Verify exact individual product quotas, competition completeness, terms and 429 handling | Migration target for owner's existing personal key |

### Motorsports

- **Formula 1:** [Jolpica F1](https://api.jolpi.ca/ergast/f1/2026.json) (race/FP/quali/sprint/circuit) with [noncommercial CC BY-NC-SA terms](https://github.com/jolpica/jolpica-f1/blob/main/TERMS.md), plus [official F1 calendar](https://www.formula1.com/en/racing/2026) for permitted manual accuracy comparison. Model race weekend as meeting→session; exact UTC start, country, circuit, session type and provisional statuses. No claim of freely licensed live telemetry.
- [OpenF1](https://openf1.org/docs/): historical completed sessions from 2023 free without credentials; **live is paid**, not suitable as a free live status dependency. Website says free intended personal use with rate 3/sec, 30/min; verify licensing if republishing.
- **MotoGP, Formula E, WEC, endurance, NASCAR, rally:** official event calendars if permitted and SportsAPI `motorsport` race endpoint only if specific series is present. Do not assert all series covered on 'motorsport' label; benchmark by season/round. Offseason should not be interpreted as failed lookup.

### Football

Prioritise EPL, UCL, Europa League, Conference League, FA Cup, EFL Cup, Championship, Scottish Premiership, La Liga, Bundesliga, Ligue 1, Serie A, FIFA World Cup, qualifiers/internationals, UEFA Euros, national friendlies, women's major competitions. A fully scoped fixture table includes event ID, home/away, kickoff local/UTC, venue, competition, stage, postponed/cancelled/live state, **source coverage completeness**. Do not filter EPG-found fixtures out because a free API lacked league rights.

### Tennis

- [Tennis API](https://docs.tennis-api.com/getting-started): FREE 50 requests/day, 4/sec; ATP/WTA calendar, upcoming, order-of-play/tournament discovery. Match start may be `not_before`, `approximate` or `TBC`; broadcast session start ≠ court match start.
- Target ATP, WTA, Wimbledon, Roland-Garros, US/Australian Open, Davis/Billie Jean King Cups, Masters, ATP/WTA Finals, ITF where covered. Official tournament draw/order-of-play spot-check, but permissions required for ingestion.
- Tennis 24/7 matches can greatly exceed a 10-card rail. Fetch broadly within quota, rank locally, present complete optional events by sport.

### Boxing and combat sports

- [Open Boxing](https://www.openboxing.org/api/): scheduled world-title bouts API `https://openboxing.org/api/bouts/scheduled/index.json`; **early development**, lacks many non-title fights and broadcaster/PPV; great cross-check.
- [Boxerbook](https://boxerbook.com/developers): schedule/cards/bouts and `where_to_watch` by country; API/MCP free for point lookups but bulk and commercial data **by agreement**, and app publication rights require review. Attribution and link to origin; no assumption about public GitHub redistribution.
- [BoxingAPI](https://boxingapi.net/): free tier candidate, 50/day claim needs account verification and current terms.
- MMA/UFC/PFL/ONE, kickboxing: explicit expansion targets, not assumed complete because boxing source exists. Show fight card/round/main-event separately; OTT/PPV event access vs linear channel.
- Unknown ring-walk time stays null; program coverage start may be many hours earlier.

### Rugby union and rugby league

- Six Nations (men/women/under-20), Rugby World Cup/qualifiers, international tests, Premiership Rugby, URC, European Champions Cup, Top 14, Super Rugby, NRL, Super League, State of Origin. Official competition calendars (e.g. [Six Nations support](https://www.sixnationsrugby.com/en/support) including fixture calendar downloads) for permitted corroboration. Rugby union vs league are *distinct sports/subsports*. API-Sports rugby product and SportsAPI rugby category coverage require actual tournament IDs and quota check.

### Cricket

- [CricketData.org](https://cricketdata.org/pricing/): 100 free hits/day, updates may lag minutes; fields/rights require check. Include Tests/Ashes, T20/ODI, national internationals, ICC world competitions, IPL/Big Bash/The Hundred, domestic competitions where source actually supports.
- A five-day Test must show on **each playing day**; rain/delay/session state and overnight start across UK midnight separate. Team-name canonical identities and tournament cross-check.

### Other sports and international expansion

- **Tier S2:** basketball (NBA, WNBA, EuroLeague, NCAA), American football NFL/NCAA, NHL/ice hockey, MLB/baseball, golf PGA/DP World/majors, cycling Grand Tours/classics, darts PDC, snooker World Snooker Tour, athletics, Olympic sports, motorsport beyond F1, volleyball, handball, table tennis, badminton, winter sports and more.
- Turn on each sport adapter only once a valid competition catalogue, complete date pagination, start-time schema, UK/FR broadcaster evidence policy and licence status have been recorded. Propose sports by real TV service inventory as well as user priority, never invent fixture coverage.

### Independent discovery and source verification

1. Source A supplies actual sporting fixture; source B an official competition calendar; source C one or more EPG programme rows. Record lineage family to prevent mirrored feeds counting as independent corroboration.
2. EPG can discover an event missing fixture API, but label `candidate_epg_only` pending sporting-source verification, not 'confirmed live'.
3. Fixture may not be on TV. `broadcasts=[]` and `broadcast_state=unverified` is valid, not evidence of 'no broadcast anywhere'.
4. National broadcasters often own rights but not every fixture; require per-event named listing in requested territory, hard-negative highlights/replay controls, and actual channel/programme window.
5. Represent verified free-to-air/subscription/PPV/OTT and confidence, coverage start vs event start vs boxing walk time, final results only if free/verified and required.

## D. Source validation checklist (one row per adapter/source/competition)

- [ ] URL, signup route, API status, docs revision and example real payload recorded.
- [ ] Authentication and actual account daily+monthly quotas verified, plus minute throttling/reset zone and `Retry-After`.
- [ ] Terms: private testing, family personal app, local caching, images/crests, derivative works, public feed, redistribution, attribution, rate-bulk use — explicitly distinct.
- [ ] Actual named league/event coverage, last dated successful fixture, historical sample and upcoming event vs an official truth reference.
- [ ] Date-scoped and sport-wide pagination meta, error-state vs successful-empty semantics and source freshness.
- [ ] Timezone/offset consistency and temporary TBC/estimated start times.
- [ ] Feed lineage, upstream parent, correlated outages and independent evidence family.
- [ ] Rate-budget projection for multiple schedules without exceeding a conservative cap.
- [ ] XMLTV size/decompress-bomb, HTML response masquerading as XML, malformed UTF-8, duplicate channel IDs and stale programme horizon tested.
- [ ] Named accountable owner, current approval status and restrictions captured in machine-readable registry.
- [ ] No app-store/public GitHub publication unless allowed; if rights unknown only reference/test with allowed usage.

## E. Coverage target definitions

Maintain `coverage_by_country_channel.csv` and `coverage_by_competition_sport.csv` (synthetic samples committed; real sensitive inventory kept private local only). Fields: target, expected test records/hours, received valid, time-stale, matched IDs, conflicts, licence status, source health, last reviewed, approval state, reason for absent/partial. **Do not call incomplete data comprehensive simply because feed returns HTTP 200.**

Document targets: proposed >=95% sport event recall in explicitly supported priority competitions, >=99.5% channel/broadcast precision for confirmed automation on held-out labelled samples, and >=95% of source-eligible priority visible TV services with 24h rolling EPG data (pending actual licensing and per-source feasibility). These are **targets**, not achievements. Report abstention and true unknown separately.
