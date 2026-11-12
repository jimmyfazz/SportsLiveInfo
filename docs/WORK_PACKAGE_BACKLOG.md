# Build backlog — PR-sized independent tasks for Codex and Claude

> **Current documentation context — reviewed 12 November 2026.** Experimental v0.3.0 source is present. Current source/test evidence and open deployment gates are centralized in CURRENT_STATUS; historical version receipts elsewhere are not current pass claims.
> **Repository roles:** [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is PRIVATE source/installation and stays private; [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is PUBLIC daily data only. [Current status and evidence](CURRENT_STATUS.md).

**Issued 12 November 2026**. This is a **dependency-ordered, auditable backlog**; packages below are acceptance requirements; current implementation is mixed and none should be marked fully accepted without its evidence. Evidence must be checked in before any change to DONE. Required for BOTH comprehensive EPG and sports event products.

Legend: `[C]` Codex lead; `[L]` Claude Code lead; `[B]` both review; `[O]` owner input required for secrets/subscription/rights; `BLOCKED` cannot legitimately finish without owner input.

## Current package disposition — 12 November 2026

| Packages | Current implementation / remaining gate |
|---|---|
| CORE-001–006 | App entrypoint, flat offline tests/CI, six feed schemas, SQLite, daily quotas and source-level publication checks exist. Complete packaging CLI, per-field rights, migration/restore and performance matrices remain partial. |
| EPG-001–005 | Streaming parser, source registry, partial identity, coverage and conservative local overlay evaluator exist. Full specified corpus, quality proof and B1 integration remain open. |
| EPG-006–007 | 27 source candidates / 15 markets; live validation, permissions and inventory-driven coverage unverified. |
| SPORT-001–003, 005–006 | 16 adapter entries and taxonomy/fusion exist; richer hierarchy, omissions, real competition recall and independent acceptance incomplete. |
| SPORT-004 | SportsAPI.app / SportAPI.ai remain research-only; current API-Sports adapters are a different supplier. |
| LINK-001–003 | Provisional candidates and export evidence gate exist; reviewed verification, EPG-only event handling and benchmarks incomplete. |
| HA-001–004 | Package, setup/Save/Test, schedule, diagnostics and token GET checks exist; actual HAOS, full wizard acceptance and safe inventory import incomplete. |
| HA-005–006 | HA persistent notifications and real-host resource/restore acceptance outstanding. |
| PUB-001 | `sli/1.0` builder/atomic writer/preview exist; target is PUBLIC `jimmyfazz/LiveSports-EPG`, checked README-only. Live rights-approved publication/deployment verification outstanding. |
| B1-001–005 / RELEASE | Contracts and handover only in this source review; Android and one/ten-TV acceptance not verified. |

**Immediate validation blocker:** 86 tests attempted on Python 3.12; 81 passed, two rights-feed tests error on missing `category_id`, three HTTP tests cannot bind localhost in this runner. See [exact receipt and next steps](CURRENT_STATUS.md). Historic all-TODO and old pass counts do not describe this baseline. Source/installation remains PRIVATE; daily feed PUBLIC.

## 0 — prerequisite contract, package, dev tooling (merge in order)

- **CORE-001 [C,B]** Create `pyproject.toml`, Python 3.12+ src-layout, package import, `python -m sportsliveinfo` CLI, lint/typecheck/test config and offline CI. Acceptance: fresh clone import, `--help`, synthetic offline smoke; no required credentials. No third-party network calls.
- **CORE-002 [C,B]** Freeze JSON Schema v1 for service registry, EPG interval, sports event, verified broadcast link, manifest, source health/coverage, provider licence and quota state. Acceptance: 5+ complete synthetic fixtures for UK/FR and multiple sports, validators pass, optional/null/unknown contract explicit.
- **CORE-003 [C,B]** Generic provider transport: timeout, response ceilings, Retry-After/backoff, ETag, request-id, quota ledger by key/reset timezone, daily+monthly calls, source-family lineage, default secret redaction. Acceptance: 200 partial/empty, 304, 401, 403, 429, 5xx, bad JSON, incomplete pages.
- **CORE-004 [C,B]** SQLite database/migrations and atomic last-good snapshots with WAL/restart; immutable event/EPG source evidence. Acceptance: rollback and restart tests, source-health persists, no corruption/lost programme rows.
- **CORE-005 [C,B]** Licence class model and public export deny-by-default with per-field permission, attribution, verified approval records and source payload sanitiser. Acceptance: disallowed raw/derived EPG never enters public fixture, logs/credential redaction pass.
- **CORE-006 [C,B]** Test matrix seeds for 50k channel names/large XMLTV, UK/France GMT/BST/CET/CEST, 10 TVs and failed publications. Acceptance: deterministic CI no external credentials.

## 1E — EPG first vertical slice (Claude-owned, parallel with 1S)

- **EPG-001 [L,C]** Secure streaming XMLTV parser: gz, encoding, display-name, tz offsets, languages and interval validation; caps bytes/decompressed size/rows and prohibits unsafe XML entities. Acceptance: UK/FR synthetic 7-day guide, malformed and bomb negative tests.
- **EPG-002 [L,C]** Source registry/extractor for authorised UK/FR EPG adapters; full source namespaces, observed generator version SHA, original upstream family and legal status. Acceptance: one imported synthetic allowed guide per region with last-good and source health; no unlicensed public export.
- **EPG-003 [L,C]** Canonical service identity and alias/crosswalk registry; source IDs independent of literal URL, country/region/variant/timeshift guards and confidence; source-specific positive/negative corpus. Acceptance: BBC regional, Sky+, Sky News, numbered TNT/Canal/beIN/RMC all safe.
- **EPG-004 [L,C]** Programme coverage engine: detect missing horizon/short shows/generic text/time errors/overlaps, source independence, quality grade, per-source/channel/date report. Acceptance: 0/24/72/168h coverage and unmatched cases reported.
- **EPG-005 [L,C]** Quality-based non-destructive programme correction overlay respecting manual/account source/interval; verify actual same service and broadcast rather than superficial name. Acceptance: generic Sky sport promotion and invalid cross-service/other-sport refusal; fallback original retained.
- **EPG-006 [L,C,O]** Source candidates UK and France catalogue plus first approved live-source benchmarks. Owner only required for private account/local inventory; no forced scraping or publication until rights verified. Acceptance: dated source report and licence state for priority channels.
- **EPG-007 [L,C,O]** Additional countries/country sources selected by actual safe inventory import; channel-coverage matrix and opt-in. Acceptance: no global unbounded fetch, country/lang edition and coverage report.

## 1S — sports first vertical slice (Codex-owned, parallel with EPG)

- **SPORT-001 [C,L]** Event hierarchy with competition/season, fixture/race/session/tournament/card/bout, participants, venue, status, precision. Acceptance: real-world-shaped synthetic football/F1/boxing/tennis/cricket/rugby examples.
- **SPORT-002 [C,L]** Football-data.org & Jolpica F1 initial adapters and no-key/calendar fallback under test-use conditions. Acceptance: complete specified free competition IDs, all F1 sessions, no incorrect actual live claim; quota/backoff tests.
- **SPORT-003 [C,L]** Strict dedup/canonical ID and source independence/completeness per competition/date; preserve EPG-only events and provider omissions. Acceptance: two different legs/doubleheader don't merge; partial source never deletes fixture.
- **SPORT-004 [C,L,O]** SportsAPI.app and SportAPI.ai optional adapters including date-scope pagination, 100/day safe default despite SportsAPI pricing ambiguity, SportAPI.ai 7000/month, actual key/rights review. Acceptance: incomplete page labelled and no rate overspend.
- **SPORT-005 [C,L]** Tennis, rugby union/league, cricket, boxing specialist plugins; F1 and motorsport race families; correct schedule/card/day semantics. Acceptance: representative sport hard negatives and per-sport source/competition coverage.
- **SPORT-006 [C,L]** Tiered international sports catalogue: football beyond EPL/UCL, F1 and MotoGP etc, boxing/PPV, rugby, cricket, tennis, plus golf/darts/snooker/cycling/basketball/NFL and region-driven expansions. Acceptance: each enabled sport has declared competitions and a benchmark receipt.

## 2 — linking two complete engines

- **LINK-001 [C,L]** Independently verified event→EPG programme→canonical broadcaster by territory, exact identity + plausible time, live/highlights/replay/OTT/PPV distinctions. Acceptance: wrong rights/channel false positives zero in hard-negative corpus.
- **LINK-002 [C,L]** EPG finds sports that fixture APIs miss, sport lists events EPG doesn't; status `confirmed`, `probable`, `unverified`, `conflicting`, `source_partial` with source-verified dates. Acceptance: both independent views preserved, no inferred TV carriage.
- **LINK-003 [C,L]** Dated accuracy benchmark on all priority sports and country EPGs; report false positives, coverage/unknown, source family independence, confirmed UK/FR broadcasters. Acceptance: source benchmark evidence separate from unit tests.

## 3 — Home Assistant App and operator UX

- **HA-001 [L,C]** HAOS App config.yaml/Dockerfile/run.sh with `ingress: true`, app-only `/data` storage, no advertised host ports, admin-only settings and runtime resource guards. Acceptance: starts and restarts on actual HAOS mini-PC.
- **HA-002 [L,C]** Ingress first-run wizard only on initial run: each supported provider link/key/save/test, key-free source, rights and quota indicator; UK/FR EPG sources. Acceptance: interrupted setup resumed and unrelated keys never overwritten; all credentials masked.
- **HA-003 [L,C]** GitHub feed repo/branch/token Save+Test, publishing OFF until rights approved; Europe/London scheduler with 04:00 pre-05:00 objective, midday/evening refresh and source-SHA checks. Acceptance: scheduling/resets/DST/outage tests.
- **HA-004 [L,C]** Dashboard for per-product EPG/sport coverage, missing channels/competitions, quotas/rights, import sanitized inventory, last-good and errors. Acceptance: owner sees why channel or sport missing.
- **HA-005 [L,C]** Non-intrusive persistent HA notifications (deduped/quiet) and detailed local logs, no overly broad HA admin API without review. Acceptance: 3 repeat failures produce 1 incident; recovery clears.
- **HA-006 [L,C,O]** Actual home mini-PC HAOS resource test and backup/restore; no inbound WAN, no disruption to lights, blinds or heating. Acceptance: measured report not estimated RAM figure.

## 4 — distribution and B1 integration

- **PUB-001 [C,L,O]** Licence-gated GitHub writer and immutable content-hashed assets, manifest pointer, deploy verification/rollback, token scoping, source of truth. **Live publication blocked pending documented source rights and owner authorization; the feed target is already `jimmyfazz/LiveSports-EPG` (PUBLIC).**
- **B1-001 [L,C]** Read-only Android manifest fetch, schema validation, one cached last-good revision, independent sports and EPG region segments, fallback if CDN stale. Acceptance: no GitHub/API-sports keys on TV; local network only for its IPTV account.
- **B1-002 [L,C]** Channel identity: exact provider/source ID→verified alias→unique strict name→review suggestion; keep manual overrides, account visible projection and hidden category/channel choice. Acceptance: 0 wrong auto mappings in hard-negative tests.
- **B1-003 [L,C]** Guide integration of safe EPG enrichment, full multi-day programmes, per-country source priority and cache; no playback/EPG regressions. Acceptance: actual channel shows correct programme, not just sports card.
- **B1-004 [L,C]** Sports Today rail with real verified event↔channel binding, local playable channel, optional headline PPV 11, no misleading live badges; 10-TV account variants. Acceptance: one device and then ten, zero extra upstream calls.
- **B1-005 [L,C,O]** Optional owner-triggered, **local only** safe channel-inventory export and HAOS import. No background uploads and no public account data. Acceptance: owner reviews content, delete/replace import supported.

## 5 — release and expansion

- **RELEASE-001 [B,O]** P6 joint EPG+sport scorecards, legal gates, HAOS/Android resilience, package/rollback, no key leak, 10 device concurrent read test; both workstreams complete or explicitly blocked.
- **RELEASE-002 [B]** Continued source discovery driven by actual missing channels, programme gaps and priority sports, with no paid API or artwork scope creep.

## Merge / go-no-go rule

Each task has one branch/PR, owner, reviewer, actual tests/benchmarks, precise source-use rights and rollback. Contract changes require cross-agent acceptance. A task with missing real API credentials or unknown source licence can be **coded and unit-tested** but must be marked `live-validation-blocked` / `public-use-blocked`, not DONE. Never make 95% accuracy claims before measuring a labelled sample.
