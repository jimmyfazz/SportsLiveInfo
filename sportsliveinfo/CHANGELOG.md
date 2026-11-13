# Changelog

[SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) hosts the App source. [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is the separate feed repository.

## 0.3.4 — Collector and dashboard audit integration

- Keep group source saves and independent refresh actions. Add collapsible source settings, UK-date event filtering and pagination.
- Recalculate Live Today on view. Retain future fixtures when a provider omits them from a response of unknown completeness.
- Recover from scheduler errors, isolate corrupt guides, reject expired guide probes and reduce the number of guide payloads held in memory.
- Keep regional feed and sports coverage additions. Tighten fixture matching and add source health and publication diagnostics.

## 0.3.3 — Regional guides and fixture coverage

- Add five opt-in regional guides and expose generic-title gaps in full schedules.
- Add four selectable OpenLigaDB competitions and an optional keyed tennis adapter.
- Expire reported tennis live status when its observation becomes stale.

## 0.3.2 — EPG coverage repairs

- Replace unavailable EPG Share US1 and CA1 endpoints with US2 and CA2 under the saved source IDs.
- Add optional UK and Australian IPTV-EPG.org guides and the EPG Share US sports guide for private collection.
- Restore XML TV Fr and EPGTalk imports by removing their fixed XMLTV DTD marker before parsing. Other declarations and entities are still rejected.
- Set source-specific import limits from measured guide sizes.

## 0.3.1 — Home Assistant dashboard maintenance

- Label mixed fallback competition groups accurately and show when the Live today list is truncated.
- Display zero counts and distinguish incomplete programme coverage from missing channel identity.
- Show latest collection activity and label live statuses as of the snapshot refresh.
- Explain common EPG failures without logging raw provider exception text.
- Display date-only and time-TBC fixtures without an exact start time and exclude them from time-based EPG matching.
- Save keyless sports providers and private EPG guides in separate groups with Tick all controls.
- Raise only the Freeview download and XML TV Fr expanded-size caps to accommodate their listed files.
- Add Hong Kong Now Sports and beIN channel identities and reject conflicting explicit country prefixes. Display non-UK markets on provisional channel matches.
- Commit related dashboard snapshots together and show a collector failure if the combined write fails.
- Skip expired guide programmes before comparing fixture titles to programme text.
- Read dashboard snapshots together and fetch only provider timestamps where the feed health report needs no raw payload.
- Validate key changes before saving provider toggles, then save both together.
- Add manual Sports-only and EPG-only refreshes and show last-good imports, latest activity and local request budgets on source cards.
- Add a Live Today sport filter, prioritise live fixtures, collapse completed or disrupted results and flag prior-day snapshots.
- Keep the same App slug and persistent SQLite path for in-place updates. The feed fixture updates the producer version and channel registry.

## Documentation reconciliation — 12 November 2026 (no runtime version change)

- Reconciled all Markdown documents against source main `579541fa`; added a current-status authority and full document index, with historical audits explicitly labeled.
- Corrected private source/installation versus public daily-feed roles and removed instructions to make the source public. The operator guide uses private local App delivery.
- Recorded measured source inventory and the initial Python 3.12 validation: 86 tests attempted, 81 passed, five errors (three loopback binds denied). This was superseded by the follow-up correction below; earlier 7/19/43/55 receipts remain historical.
- Distinguished the local enrichment suggestion evaluator from an unimplemented public EPG programme contract, and source-implemented publisher from a deployed public feed. No runtime code, schema, fixture, HA setting, repository visibility or source-rights approval changed.

## Validation correction — 12 November 2026

- Fixed rights-feed test inputs to use production taxonomy classification and a pinned clock.
- Added a shared ingress-test transport that uses loopback where available and dispatches through the real HTTP handler/parser with in-memory streams when socket binds are denied; added forced-memory CSRF and origin tests.
- Python 3.12.15 compileall passed and all 88 tests passed. Real loopback transport remains unverified in this socket-restricted runner; see [current status](../docs/CURRENT_STATUS.md).
- Production runtime, schemas, golden fixtures, HA settings and repository visibility are unchanged.

## 0.3.0 — 12 November 2026

- Sports sources 4 → 16: new OpenF1, TheSportsDB (free public key; darts, snooker, golf, rugby, cricket, fighting and more), CricketData.org (Test matches per playing day) and API-Sports rugby, basketball (NBA/WNBA), ice hockey, NFL, baseball, AFL, handball, volleyball and MMA. One API-Sports key now serves every API-Sports sport. OpenLigaDB covers Bundesliga 1–3; Jolpica fetches next season from October.
- Sports taxonomy: 24 sports and 127 competition rows, including England (men), England Women, home-nation and U21 internationals, Premier League, Champions League, Europa League, Conference League, FA Cup, EFL Cup, Championship, WSL and Scottish football; ambiguous names are resolved per sport and country.
- New "Live today" Ingress page grouped by sport and competition, with a featured England / home nations / PPV row and live-state estimates; events page filters by sport, competition and team.
- Cross-source fixture fusion with corroboration count and start-time conflict flag; scoped partial saves keep the last good data per day/league/sport; parallel sports lanes with per-provider pacing.
- EPG feeds 4 → 27, including the B1G backup feeds (EPG Share UK1/US1, Matt Huisman Sky UK, iptv-org Sky UK/Foxtel, EPGTalk, IPTV-EPG.org) and HK, MY, GE (Setanta), IE, CA, AU, NZ, PT, PL, GR, SG and IN guides. All disabled by default; "verify" feeds must pass Test EPG.
- XMLTV now keeps sub-title, categories, live/repeat/premiere flags and channel icons. Channel identity covers 8 markets plus B1G's exact farleyflex tvg-ids; 41 lineup families (Sky Sports+, beIN, Setanta, Now HK, Astro, DAZN, ESPN+, Peacock, Kayo, Fubo, SSC, Fite, FloSports…) are reported per guide.
- Unverified EPG broadcast candidates for today's events, with hard negatives (highlights, repeats, wrong opponent, unrecognised channel); EPG-derived fields are stripped from publication.
- B1G feed format `sli/1`: taxonomy, channel registry and guide catalogue, eight daily event files, today grouping and source health, content-addressed under `v1/assets/` and referenced by `v1/manifest.json`, with compatibility rules so later coverage changes need no B1G release.
- Atomic publishing in one GitHub commit (Git Data API): only new assets uploaded, unchanged revisions skipped, last 10 manifests retained; local feed preview; optional auto-publish after each scheduled refresh.
- JSON Schemas, byte-exact golden fixtures and channel-matching parity cases for the B1G reader; 55 local tests pass. No live provider call, Docker build, HAOS install or publication was performed.

## 0.2.0 — 12 November 2026

- Add private multi-country EPG channel identity hints and forward guide coverage analysis (24, 72, 168 hours), with strict country, variant and name safeguards.
- Add UK/France EPG coverage page and a separate sport fixture/event viewer in the Home Assistant Ingress UI.
- Add optional no-key OpenLigaDB Bundesliga fixture adapter and Jolpica Sprint Shootout session support.
- Add one-call sports source connection tests and full EPG parser connection tests with quota accounting.
- Preserve last-good on stale guide and invalid/partially paginated provider responses; avoid duplicate refresh queues and excessive API-Sports repeat 7-day requests.
- Preserve all previously saved API keys/source settings during version migration.
- 19 local deterministic tests including private Ingress HTTP/CSRF smoke; actual Home Assistant OS and B1G device validation still pending.
- Experimental stage: **not a production-ready or comprehensive global coverage release**; no public HA ingress, no unapproved third-party EPG redistribution.

## 0.1.0 — 12 November 2026

- Initial installable Home Assistant OS App layout, Ingress interface and setup state.
- Persistent settings, quotas and independent local sporting / international EPG collection.
- Built-in UK/FR source registry; Jolpica, football-data.org and API-Sports adapters.
- Source-level last-good cache, scheduler, status and errors.
- Default-disabled outbound licence-gated GitHub publisher foundation.
- New SportsLiveInfo app icon and wordmark logo.

Not yet a worldwide-complete EPG/sports product or a verified B1G integration.

## Development integration hardening (unreleased / v0.3.0, 12 November 2026)

- Integrated Claude's unmerged v0.3 candidate sports/EPG source expansion, taxonomy, sli/1 contract and test fixtures.
- Fixed cross-process quota reservations, scheduler restarts, partial source data preservation, failed job reporting, API-Sports pages, XMLTV memory bounds, credential redirects and config validation.
- Public feed now rejects fused events contributed by unapproved sources; broadcaster claims need reviewed evidence, not a boolean alone.
- Added conservative non-destructive programme enrichment suggestions. The original B1G EPG remains authoritative.
- Added targeted regression tests; exact merged-branch Python suite and physical Home Assistant installation **not yet verified**. Keep experimental stage.

### Home Assistant installer hardening — 12 November 2026

- Add Supervisor-required Docker image labels (io.hass.version, io.hass.type and io.hass.arch) with version/architecture build arguments.
- Add static App packaging tests for Ingress-only configuration, private admin panel, logo/icon and store repository layout.
- Actual Docker build and Home Assistant OS install **still not executed**; experimental designation retained.
