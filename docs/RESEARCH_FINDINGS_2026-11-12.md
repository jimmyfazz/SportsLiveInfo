# Forensic research findings — 12 November 2026

> **Historical audit / receipt — reviewed 12 November 2026.** Preserved against its stated original revision. Findings, branch/merge positions, provider claims and pass counts below are historical, not freshly verified current facts. Current source is v0.3.0; the combined review attempted 86 tests (81 passed, five errors, three of those environment-blocked). Use CURRENT_STATUS for resolved/remaining work; no new live source, licence or device verification occurred.
> **Repository roles:** [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is PRIVATE source/installation and stays private; [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is PUBLIC daily data only. [Current status and evidence](CURRENT_STATUS.md).

## 1. Precisely defined purpose

A daily UK-centric electronic sports schedule, not a live-scores or streaming platform. For any queried UK date return sport, competition, event/team or fighter names, venue/city/circuit/country where known, event/round/session, date and start time in UK local time, whether it is scheduled/in progress/completed/postponed, and the **actual UK live broadcaster**, possibly including channel number, coverage start time, platform and entitlement (FTA/subscription/PPV). Show source provenance and confidence. Support today's events, tomorrow and the next seven days.

**Separate facts**: a fixture exists; a sport start time is scheduled; an EPG programme is listed; a UK broadcaster carries that specific match live; and the event is *currently* underway. One fact does not prove the others.

## 2. Findings by discipline

### Football — broad, but no single complete free provider
- football-data.org free: 12 competitions including Premier League, Champions League and FIFA World Cup, with 10 requests/minute; scores and schedule updates are delayed. **Europa League and many internationals are outside its published free competition list**. Sources: https://www.football-data.org/coverage and https://www.football-data.org/pricing.
- SportsAPI advertises fixtures across many football leagues and date-based fixtures, but requests for a whole sport are paginated (ten leagues per page). Implement all pagination and inspect completeness flags; a single API call is not the full day's worldwide schedule. Sources: https://sportsapi.app/docs/fixtures/list and https://sportsapi.app/docs/catalog/sports-coverage.
- OpenFootball football.json is CC0/public-domain reference for multiple leagues; upstream sources may be stale, despite daily JSON regeneration. Use as a cross-check, never sole source of today's confirmed fixtures. https://github.com/openfootball/football.json.
- Include English domestic cups, Scottish leagues, Europa/Conference League, international qualifiers, friendlies and women's competition as expansion targets. Validate **actual** coverage against competition IDs.

### Formula One
- Jolpica-F1 provides race calendar, venue/circuit, session UTC starts including practice, qualifying and sprint where present. Suitable for scheduling, not a stand-in for live telemetry. Free API subject to CC BY-NC-SA non-commercial licence and rate limits (currently burst 4/sec, sustained 500/hour). https://api.jolpi.ca/ergast/f1/2026.json ; https://github.com/jolpica/jolpica-f1/blob/main/TERMS.md ; https://github.com/jolpica/jolpica-f1/blob/main/docs/rate_limits.md.
- Separate all on-track sessions. An F1 race may be on a Sunday while practice and qualifying take place on other days; store local Grand Prix name, circuit, municipality, country and session.
- A broadcaster's highlights must not be mistaken for a live session.

### Tennis
- Tennis API advertises 50 requests/day on free tier, calendar and match endpoints; match start times may be unknown until order of play/court scheduling. https://docs.tennis-api.com/getting-started.
- Include ATP/WTA/ITF, Wimbledon, Australian Open, French Open, US Open, Davis Cup/Billie Jean King Cup. Validate actual coverage; a Grand Slam is a tournament, not one match.

### Rugby union and league
- API-Sports and cross-sport providers are candidates; exact competition-specific free quotas, separate union/league coverage, fixture fields and reuse rights require verification before activation. Include Six Nations, internationals, Premiership Rugby, URC, Rugby Championship, major league competitions and rugby league if possible.
- Union and league are never merged into one competition taxonomy.

### Cricket
- CricketData.org advertises 100 free hits/day with some live data delayed; schedule, format, teams and multi-day sessions are most relevant. https://cricketdata.org/pricing/.
- Test/First Class matches remain displayed on **every date with scheduled play**, not only on initial match date. Include ODI/T20, World Cups, The Ashes, domestic and franchise competitions, with timezone and session handling.

### Boxing
- Boxerbook advertises event schedules, card start times, fighters and broadcaster fields: free key 100 requests/day, restricted to personal, non-commercial and testing use; commercial use is paid. https://boxerbook.com/developers and https://boxerbook.com/terms.
- BoxingAPI (boxingapi.net) free key advertises upcoming fights with 50 requests/day and 10/min; complete card/other fields may be paid-only. https://boxingapi.net/documentation/plans-and-limits.
- **Card start**, **main event**, **approximate ring-walk time**, **broadcast start** and **UK PPV product** are different concepts. Never invent a ring-walk time from the programme start. Explicitly label estimated times.
- PPV may not appear in a normal linear XMLTV feed. Use permitted promoter and broadcaster event information to corroborate the exact card and access model.

### Other sports
- Architecture must be expandable to darts, snooker, golf, cycling, basketball, NFL and others, but no coverage claims until adapters and benchmark evidence exist.

## 3. UK broadcaster coverage is the decisive challenge

A fixture API is not a programme/broadcast rights database. Broadcasters and channels must be matched using permitted UK EPG (XMLTV) data, actual broadcaster schedules and independently verified event announcements.
- https://github.com/noodlemctwoodle/epg-guide demonstrates UK channel XMLTV collection via Sky, Freeview, Freesat, Radio Times, YouView and Rytec merges, including some premium channels. Its **code** is GPLv3 and programme data remains provider-owned. It explicitly lacks some event-only/PPV channels.
- https://github.com/dp247/Freeview-EPG provides regional free-to-air XMLTV and is labelled personal-use; not a comprehensive Sky Sports/TNT/PPV source.
- https://www.wheresthematch.com/ and https://www.fanzo.com/en/tvguide are excellent UK broadcast *manual benchmark* resources, not assumed licensed scrape/redistribution APIs.
- Official broadcaster schedule/competition announcements are authoritative sources for specific TV rights/transmissions, but TV rights for a season do NOT prove broadcast of an individual event. Do not assume a Premier League Saturday blackout fixture is live on a UK channel.
- Record actual broadcast start, sport start, transmission type (live, delayed, highlights, replay), UK jurisdiction and access (free-to-air, subscription, PPV, streaming).

## 4. No-cost system viability

**Feasible as a private development prototype with zero recurring API/LLM spend.** No single identified free provider gives complete fixtures for every requested sport *and* reliable UK TV channel allocation, with unrestricted downstream redistribution rights.
- Python event adapters + XMLTV + normaliser + verified EPG-to-fixture matching + SQLite cache + JSON output.
- A deterministic rules engine plus optional RapidFuzz is sufficient for the first version; no LLM in the critical path.
- GitHub Actions on a private GitHub Free repository have an included usage allowance; public GitHub Pages is not available while the repo remains private under GitHub Free. Do not publish or schedule a live feed until licensing and deployment are cleared.

## 5. Confidence and known unknowns

The preceding findings come from **published product/docs and selected open-source projects**; no API authentication was performed, provider uptime measured, or complete current-day schedule benchmark run for this project. Free API availability, quota, coverage and terms are changing variables. This repository deliberately keeps a source registry, validation checklist and acceptance plan. Do not claim 100% events, correct live TV channels, or approved redistribution until empirical testing and permissions justify it.

See SOURCE_REGISTRY, UK_BROADCAST_MATCHING and TEST_PLAN.
