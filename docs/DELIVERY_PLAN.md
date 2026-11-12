# Delivery plan — technical work packages

**Status 2026-11-12:** research complete/documented, implementation not started. This plan is for next development work; no claims that these tasks are done.

**Primary host decision:** owner chooses directly installed **Home Assistant on an always-on personal-home mini PC (no Proxmox)**. Build one portable collector plus local **HAOS App** wrapper if installation type confirmed. See [HOME_ASSISTANT_BARE_METAL_PRIMARY.md](HOME_ASSISTANT_BARE_METAL_PRIMARY.md). Public GitHub JSON publishing is a proposed outbound-only step **after** licence approval; 10 B1G clients never query provider APIs.

## Stage P0 — groundwork (highest priority)

- [ ] Scaffold Python package with typed canonical Event, Participant, Venue, Broadcast, SourceEvidence and SourceHealth models.
- [ ] Fixture and broadcast normalisation, Europe/London date filter, DST and 24-hour UTC-edge tests.
- [ ] HTTP fetcher with timeouts, retries, 429 Retry-After, quota cache, ETag and structured logging.
- [ ] Configurable provider approval/usage gate (prototype-only versus licensable production).
- [ ] Full synthetic fixture corpus; no network in unit tests.
**Exit:** deterministic sample JSON validates against schema; no missing mandatory identity/temporal fields.

## Stage P1 — minimal end-to-end proof

- [ ] football-data.org adapter for accessible free football competitions, plus absence-of-Europa handling.
- [ ] Jolpica-F1 adapter with individual FP, qualifying, sprint, race and circuit records.
- [ ] XMLTV reader for **authorised local test fixture data**, channel normaliser and EPG event candidate generation.
- [ ] Deterministic broadcast matcher (two teams, competition, live/replay negative markers, time overlap and evidence).
- [ ] CLI to build schedule for arbitrary UK date + source-health report and local JSON snapshot.
- [ ] Demonstrate at least 10 named synthetic scenarios: confirmed TV, unknown TV, conflicting broadcasters, highlights, repeat, simulcast, BST boundary, F1 qualification/race, postponed match and duplicated competition aliases.
**Exit:** repeatable offline demo and source-linked event+TV JSON. Live external source performance not yet proven.

## Stage P2 — broader coverage and real provider benchmark

- [ ] SportsAPI adapter including complete pagination/hasNextPage and meta.complete handling, free quota accounting, contract/rights review.
- [ ] Tennis calendar + order-of-play handling (TBC and not-before), rugby union + league, cricket multi-day sessions.
- [ ] Boxing card/bout hierarchy, heavyweight fights, PPV and subscription distinctions; free sources only where permitted.
- [ ] Expand competition registry: EPL, UCL, Europa, World Cup/qualifiers, internationals, Euros, F1, ATP/WTA Slam, Six Nations, domestic rugby, cricket formats, world title boxing.
- [ ] Source conflict resolution, alias directory, duplicate detection, freshness and accuracy report.
**Exit:** measured event completeness and UK broadcaster precision by sport, without invented accuracy percentages.

## Stage P2.5 — mandatory HA App first-run setup UI

Read [first-run wizard and notification specification](HOME_ASSISTANT_FIRST_RUN_WIZARD_AND_NOTIFICATIONS.md) and its required tests. These are **release blockers** for the Home Assistant package.

- [ ] HA Ingress initial setup wizard and main dashboard, no public inbound port.
- [ ] Supplier registry-driven setup cards for all eligible providers: name/sports/signup/docs, key/no-key classification, masked field, individual Save and Test, status/quota and rights.
- [ ] Save/resume first-run progress; explicit Finish; never redisplay after completion except owner-triggered Run Setup Again; add/replace/remove supplier credentials in normal Settings.
- [ ] GitHub source versus separately proposed feed destination clearly separated; owner/repo/branch/path/token Save and Test; publication default OFF until clearance.
- [ ] User-friendly `Europe/London` daily fetch/publish scheduler with individual Save, next-run preview, live quota accounting, catch-up/DST guards, change-only publication.
- [ ] Persistent Home Assistant error notifications outside the wizard, classified/deduplicated/cooldown-limited, detailed impact/next-action with secure redaction; quiet normal operation and diagnostics history.
- [ ] Validate no extra supplier API requests when 10 B1G TVs download the shared cache.
**Exit:** all wizard + HA notification acceptance tests pass on supported HAOS, and ordinary Home Assistant automations remain unaffected.

## Stage P3 — operation and deployment

- [ ] CI unit/integration tests and static type/lint; GitHub Actions may run tests, but routine production collection belongs on the personal-home HAOS mini PC.
- [ ] Confirm HA installation type and available Apps; package/install a local HAOS App with Supervisor-managed restart, persistent storage, backup and log/health monitoring.
- [ ] Outbound-only publisher: send a small, rights-approved JSON snapshot to a **separate proposed** public GitHub feed repository; no public ingress, no secrets in data.
- [ ] Verify 10 B1G TVs consume one shared published snapshot with zero incremental sports-provider API calls.
- [ ] Define schedule (7-day background, same-day refresh, near-start refresh) strictly within all provider limits.
- [ ] Choose authorised data distribution path; verify licences before any public feed and no Pages from private GitHub Free.
- [ ] Health manifest, failed-source warnings, stale data TTL, alerting, provenance inspection.
- [ ] Version v1 API/schema and backwards-compatibility policy.
**Exit:** stable, permitted JSON product, transparent health and recoverable failures.

## Stage P4 — optional B1 Android consumption

- [ ] B1 receives sports JSON, resolves UK programme and channel IDs to configured channels by existing channel-matching logic.
- [ ] Same-day sports rail and event cards; no guessed stream URL or channel if unverified.
- [ ] Cache and UI focus/navigation/performance integration, no playback regression.
**Exit:** B1 consumer renders events accurately with optional click-through to existing permitted channel.

## Working practice

Work on independent adapters/tests concurrently; merge only after tests pass and update docs and provenance. Distinguish "researched" / "prototype works with fixtures" / "validated live provider" / "licence approved" / "production ready" for every source. Create small PRs with evidence instead of one large speculative implementation.
