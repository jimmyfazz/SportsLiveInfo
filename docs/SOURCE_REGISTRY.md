# Free provider/source registry

> **Current documentation context — reviewed 12 November 2026.** The current inventory is separated below from dated research. Registry entries and code budgets do not establish supplier availability, free-tier allowance or publication rights.
> **Repository roles:** [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is PRIVATE source/installation and stays private; [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is PUBLIC daily data only. [Current status and evidence](CURRENT_STATUS.md).

**Research date:** 2026-11-12. **Status legend:** DOC-CONFIRMED = specific published claims verified against docs; CANDIDATE = must inspect exact endpoints/terms; RESTRICTED = restricted/unsuitable for production publication; NONE = no approved data ingest. These statuses are **not** successful integration tests.

## Current implementation inventory (source checked 12 November 2026)

`providers.SPORTS` contains 16 entries: Jolpica, OpenF1, OpenLigaDB, football-data.org, TheSportsDB, CricketData.org, and ten API-Sports adapters (football, rugby, basketball, hockey, NFL, baseball, handball, volleyball, AFL, MMA). All API-Sports entries share the saved `api_sports` key setting. Three optional owner-entered sports keys are API-Sports, football-data.org and CricketData.org. Jolpica is initially selected, new sources disabled; setup completion is required before collection.

`providers.EPG` contains 27 candidate feeds across 15 source markets, all opt-in. `guide.py` has service tables for eight markets and 41 diagnostic lineup families. [Current status](CURRENT_STATUS.md) records measured code counts and validation; [source expansion report](SOURCE_EXPANSION_SPORTS_TAXONOMY_AND_B1G_LINEUP_2026-11-12.md) records the original expansion. SportsAPI.app, SportAPI.ai, specialist Tennis API and Boxerbook are research candidates, not implemented adapters in this snapshot. Do not confuse SportsAPI.app with API-Sports.

The tables below retain dated research claims. Endpoint operation, supplier quotas/free eligibility and legal terms were **not newly reverified** in this review and test correction. DOC-CONFIRMED refers to the original research, not current deployment approval. Even a working source is not automatically licensed for public redistribution.

## Fixture / event data

| Provider | Sports and role | Advertised free limit | Restrictions / caveats | Initial decision |
|---|---|---|---|---|
| [SportsAPI](https://sportsapi.app/) | 24 sports; first-choice broad prototype including football, tennis, cricket, motorsport (verify each discipline's actual completeness) | 1,000/day temporarily in beta, reverting to 100/day; 10/min | Key; date-based all-sport queries page 10 leagues at a time; test quota and reuse rights; core data free, not all advanced fields | DOC-CONFIRMED; validate licensing and real-world coverage |
| [football-data.org](https://www.football-data.org/coverage) | Premier League, Champions League, World Cup, Euros, European domestic football | 12 free competitions; 10/min | Schedules/scores delayed; Europa League not in free list | DOC-CONFIRMED; strong backup |
| [Jolpica-F1](https://api.jolpi.ca/ergast/f1/2026.json) | F1 GP calendar, circuit, practice, qualifying, sprint, race | 4/sec burst, 500/hour | CC BY-NC-SA 4.0, non-commercial, attribution/share-alike | DOC-CONFIRMED; private prototype only pending downstream licence |
| [Tennis API](https://docs.tennis-api.com/getting-started) | ATP/WTA calendar and upcoming tennis | 50/day; 4/sec | Key, per-match times sometimes TBC; redistribution terms to check | DOC-CONFIRMED; validate |
| [CricketData.org](https://cricketdata.org/pricing/) | Cricket match schedules and near-live status | 100 hits/day | Some data delayed; verify coverage and redistribution terms | DOC-CONFIRMED; validate |
| [Boxerbook](https://boxerbook.com/developers) | Boxing cards, bout schedule, broadcaster metadata, PPV research | 100/day with free key; unauthenticated trial 50/day | Personal/non-commercial/testing; commercial app needs paid agreement; no bulk harvesting | RESTRICTED; personal prototype only |
| [BoxingAPI](https://boxingapi.net/documentation/plans-and-limits) | Boxing upcoming fights and ratings | 50/day, 10/min | Prices held back, cards/history may require paid tiers; licensing to assess | CANDIDATE |
| [TheSportsDB](https://www.thesportsdb.com/docs/api) | Multiple sports and some TV data | Free key 123; per-endpoint response restrictions | [Terms](https://api.thesportsdb.com/docs_terms_of_use.php): free API cannot publish app-store apps; third-party rights apply. Some daily event / TV endpoint outputs heavily limited | RESTRICTED supplementary source, never sole source |
| [OpenFootball JSON](https://github.com/openfootball/football.json) | Public-domain football fixture baseline | No service quota for files subject to GitHub fair use | CC0 data, but upstream changes not automatically supplied; may be stale | DOC-CONFIRMED fallback only |
| [API-Sports](https://api-sports.io/) | Football, rugby and motorsport candidate | Free tier advertised in previous research, exact 2026 quotas **not reverified** here | Must confirm exact free plans per product, permissions, competition coverage | CANDIDATE, not approved |
| [OpenF1](https://openf1.org/) | F1 sessions/data and timing research | Historical accessibility varies; true real-time often gated | Not needed for calendar-first MVP; check current live-access terms | CANDIDATE for later |
| Yahoo Sports / ESPN unofficial endpoints | Cross-check for schedules when lawful | No stable official, free, broadly licensed API established | Endpoint fragility, legal/ToS and redistribution risks. No unapproved scraping | NONE until permitted access confirmed |

**Important SportsAPI paging detail:** [date fixture API](https://sportsapi.app/docs/fixtures/list) returns ten leagues per page for sport-wide queries, with meta.hasNextPage and meta.complete. A single successful call does NOT prove completeness. A country/category/league query has different paging rules. Obtain the authenticated [coverage directory](https://sportsapi.app/docs/catalog/sports-coverage) and benchmark selected competitions.

**Boxerbook current provider discrepancy caution:** separate pricing and developer pages are subject to change; treat [terms](https://boxerbook.com/terms) and current account agreement as authoritative before implementation.

## B1G code-verified existing sports/EPG source map (12 Nov 2026)

Full audit with precise code paths: [B1 forensic EPG and credentials](B1_FORENSIC_EPG_SPORTS_API_SCOPE_AUDIT_2026-11-12.md).

| Existing B1G input | Role and actual source | Key needed | Aggregator action |
|---|---|---|---|
| [farleyflex/epg-guide](https://github.com/farleyflex/epg-guide) | B1G's enhanced UK Sky Sports/TNT/Premier detailed XMLTV; generated via iptv-org from mytelly and other source guides; 5-day data | No | Important *reference* for EPG parsing/quality; central download only if terms allow, **no public re-hosting** without cleared programme rights |
| [EPG Share UK1](https://epgshare01.online/epgshare01/epg_ripper_UK1.xml.gz) | Android automatic permitted UK gap-fill | No key visible in B1 source | Candidate for source benchmark and optional permitted ingest; rights unverified |
| [Matt Huisman Sky UK](https://i.mjh.nz/SkyUK/epg.xml.gz) | Android automatic UK backup | No key visible in B1 source | Candidate for guide coverage benchmark; rights unverified |
| [IPTV-org Sky UK](https://iptv-org.github.io/epg/guides/uk/sky.com.epg.xml.gz) | Android automatic UK backup | No key visible in B1 source | Candidate for guide coverage benchmark; data rights unverified |
| [EPGTalk UK National](https://raw.githubusercontent.com/acidjesuz/EPGTalk/master/UK_guide.xml.gz) | Android manually selected EPG | No key visible | Candidate/user-opt-in only, no automatic replication without permission |
| [EPGTalk Sports](https://raw.githubusercontent.com/acidjesuz/EPGTalk/master/Sports_guide.xml.gz) | Android manually selected EPG | No key visible | Candidate/user-opt-in only, rights unverified |
| [API-Sports football v3](https://v3.football.api-sports.io/) | Android and Mac opt-in date-scoped football schedule validation | **Yes**, user currently enters key per B1G device | Move credential and fixture polling to HAOS for 10-TV sharing, subject to provider terms |
| [TheSportsDB](https://www.thesportsdb.com/docs/api) public test key 123 | Existing B1G crests and standings; not primary EPG provider | No owner signup input normally | Keep in B1G for now; per-device existing cache; do not redistribute artwork |
| TMDB and OMDb | Existing B1G VOD movie/series metadata, ratings, poster/hero enrichment | **Yes**, optional device keys | **Exclude from SportsLiveInfo**; leave in B1G |

**Important:** farleyflex upstream GitHub Action scheduled at 06:00 UTC, but inspected EPG commits on Nov 9–11 landed between 13:05 and 14:33 UTC; check the new source SHA/commit time rather than assuming a 05:00 UK download is latest. Its published channel catalogue includes additional variants not covered by B1's 17 conservative aliases; verify channel identity and programme content before using Sky Sports+ or TNT 5–8.

**Legal status:** URL readability and source project's public GitHub code licence are not licence grants to republish original provider programme texts. A separate public GitHub feed must not contain unapproved XMLTV programme data. The B1 app may retain its own permitted direct source subscription as fallback.

## UK broadcaster and EPG candidates

| Source | What it is useful for | Legal and technical status |
|---|---|---|
| [noodlemctwoodle/epg-guide](https://github.com/noodlemctwoodle/epg-guide) | Reference implementation for multi-source UK/Ireland XMLTV including premium channel guides | GPLv3 code; underlying programme descriptions owned by providers; not an automatic licence to republish |
| [dp247/Freeview-EPG](https://github.com/dp247/Freeview-EPG) | Freeview 7-day XMLTV reference and parser testing | Regional FTA; project describes personal use; inspect data terms |
| [Where's the Match](https://www.wheresthematch.com/) | UK manual TV schedule accuracy benchmark | Do **not** scrape or republish in absence of permission; site terms restrict copying |
| [FANZO TV guide](https://www.fanzo.com/en/tvguide) | Independent UK live-sport schedule reference | No verified open licensed API |
| [BBC Sport](https://www.bbc.co.uk/sport) / [ITV](https://www.itv.com/) / [Sky Sports](https://www.skysports.com/) / [TNT Sports](https://www.tntsports.co.uk/) / [Channel 4](https://www.channel4.com/) / [DAZN](https://www.dazn.com/) / [Premier Sports](https://premiersports.com/) | Official channel/event announcements | Prefer official structured programme data where licensed; no general scraping entitlement established |

## Required onboarding worksheet (before activating each provider)

- [ ] Verify full documented endpoint URLs, authentication and example payloads against live schema.
- [ ] Confirm quotas in free account, reset time, minute limits, 429/Retry-After.
- [ ] Confirm UK-date coverage and competition/entity IDs; sample normal weekday, European night, weekend, international break and major boxing PPV.
- [ ] Confirm **personal/private test use** rights, caching duration, redistribution/commercial/app-store use, attribution obligations and any image/logo restrictions.
- [ ] Record data freshness, updated_at and source's timezone conventions.
- [ ] Test partial responses, pagination, malformed schedules, empty days and outages.
- [ ] Mark source approved only after technical and licensing review; keep terms/source screenshots or dated URLs in internal records.
