# Changelog

## 0.3.1 — 12 November 2026 (experimental, pending HAOS acceptance)

- Responsive Home Assistant Ingress operator UI: accessible navigation, visible numerical zeros, collection readiness and live-status indicators, source freshness and guided first-run shortcuts.
- Sports/EPG source catalogue grouped by family and region; independently saved keys, per-source test states and optional provider filters.
- Sports event search now supports 100-row server-side pages, UK calendar dates (including BST boundary) and competition/title filters; no silent 200-row truncation.
- Private guide coverage now has accessible percentage bars, expandable channel-family and missing-coverage lists; diagnostics show source failures and quota reservations.
- GitHub token instructions are progressively revealed, with explicit publication prerequisites and a disabled publish action until enabled, token and approved source are all present.
- EPG source preflight rejects a parseable but expired guide; stale/collapsed source imports skip expensive quality scoring while retaining last-good.
- Added first-run local `local_apps` installation instructions for the still-private source repository and offline regression tests.
- **Release gate:** code and tests are committed, but the private repository's GitHub Actions jobs report failure without executed steps/log access. No actual HAOS install, Docker build or desktop/mobile visual test has passed. Do not treat this as install-accepted or as clearance to redistribute unlicensed data.


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
