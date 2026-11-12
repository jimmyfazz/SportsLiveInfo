# SportsLiveInfo — authoritative master architecture, construction sequence and rollout
**Version:** plan 1.0, dated 12 November 2026  
**Priority:** NORMATIVE BUILD PLAN. Supersedes earlier documents where they treat UK-only EPG, optional B1 consumption, or future-proofing of sports coverage as a lesser priority.  
**Owner-selected deployment:** private HAOS App on a directly installed, always-on home mini PC; no Proxmox needed. Ten B1G televisions use rights-cleared read-only GitHub-hosted snapshots. No inbound home-network ports.  
**Implementation status:** specification and work programme; no deployed service, verified feeds, live integration or finished code.

## 0. Non-negotiable product definition

Build **two full independent engines** on a shared, testable foundation. Neither is a subset of the other.

### Product E — International Electronic Programme Guide (EPG)

1. Discover **which channels should be covered** from optional safe subscription inventories plus default UK/FR priority coverage.
2. Discover **authorised guide sources** for each country/region/channel; maintain publisher origin and licensing metadata, not merely scrape any URL.
3. Collect and parse XMLTV/structured schedules within bounded memory/CPU; validate programme intervals, language, genre, premiere/replay/live flags and freshness.
4. Create a **canonical cross-source service identity registry** and crosswalk, including region/edition, time-shifts, channel number and premium/event-only variants.
5. Resolve **programme quality/corrections** without erasing valid earlier listings or forcing identical coverage and sporting kick-off windows.
6. Measure programme coverage per visible service and time window, with an exception list for absent/ambiguous/expired feed/source.
7. Publish only licence-cleared regional/channel schedule segments and identity crosswalks. If rights forbid public redistribution, keep data local where permitted and let B1G use its account-authorised direct EPG; never quietly publish it.
8. B1G locally maps canonical service to its current account's visible stream; manual mapping and hidden channel/category are authoritative.

Minimum planned regions: **UK and France**, including mainstream general entertainment plus premium sports channels insofar as selected subscriptions/source rights permit. Additional regions (e.g. Ireland, Belgium, Germany, Spain, Italy, Portugal, Netherlands, Switzerland, US/CA/AU, South Asia) are driven by actual channel inventory and permitted sources, not an indiscriminate global scrape.

**EPG product is not complete merely because a Sports Today rail appears.** It needs whole-channel rolling programme windows, multi-source coverage, correction rules, diagnostics, manual override compatibility and channel-appropriate on-device Guide integration.

### Product S — Sports event and broadcast intelligence

1. Discover all events in the chosen priority sports/competitions for today and the next horizon independently of TV EPG listings.
2. Support football domestic/international/women's/youth, F1, motorsport, tennis, rugby union/league, cricket, boxing/PPV and expandable international sports.
3. Canonical event IDs, participants, competition, round, session, venue/circuit, status/precision, local UK date/time (UTC stored), multiple independent sources and disagreements.
4. Attach **verified** per-event, per-region broadcaster/TV programme, actual event start and coverage start. Never infer actual transmission from rights ownership; retain unknown channel honestly.
5. Publish all in-scope permitted event candidates and source completeness, not just a truncated 10-card output. **B1G** applies user priority, optional PPV 11th card and local-playable channel mapping.
6. Sport-specific models for tournament/stage/card hierarchy (F1 sessions, boxing undercard/main event, tennis court and not-before, multi-day cricket and golf, cycling stages).
7. Monitor cancellation, postponement, schedule drift and late changes without exceeding free provider quotas.

**Sports product is not complete just because EPG programme titles are recognised.** It requires independent fixture coverage and accuracy verification.

### Shared outcome

One Home Assistant App, one SQLite/local cache and provider quota/scheduler coordinator, separate EPG and sports pipelines, a **linking/evidence layer**, two distinct feed families and one health dashboard. Dependencies cannot cause one pipeline to starve the other or block Home Assistant automations.

## 1. End-to-end logical architecture

    [sports APIs / official fixtures]             [authorised XMLTV/guide sources]
                  |                                              |
                  v                                              v
    sports provider adapter(s)                  EPG provider adapter(s)
                  |                                              |
    fixtures, races, cards, sessions             programmes, service IDs
                  |                                              |
                  v                                              v
    SPORTS: canonical events                      EPG: canonical channels
    sport-specific validation                     schedule/time validation
                  |                                              |
                  +---------------+------------------------------+
                                  |
                             EVIDENCE JOIN
                (event <-> exact programme <-> broadcaster)
                source independence / confidence / conflict
                                  |
              +-------------------+---------------------+
              |                                         |
        Local SQLite and                             Health, QA,
        last-good snapshots                           quota ledger
              |
      per-field public-licence gate
              |
       versioned immutable JSON assets
              |
       GitHub outbound HTTPS upload
              |
         atomic manifest update
              |
        public Pages HTTPS endpoint
              |
      ten independent read-only B1G clients
              |
     local provider/account visible channels
     + manual EPG source mapping + hidden flags
              |
         B1G Guide and Sports Today

**Security:** HAOS wizard and diagnostics available via Home Assistant Ingress only; no WAN port forwarding, server token on TV, provider credential in public JSON or TV-to-GitHub writes.

## 2. Repository structure to create (not current reality)

    SportsLiveInfo/
      AGENTS.md
      README.md
      pyproject.toml
      .gitignore
      src/sportsliveinfo/
        __init__.py
        cli.py
        configuration.py
        api/
          app.py                    # internal Ingress controller
          schemas.py
        domain/
          channels.py              # service and variant model
          epg.py                   # original programme and correction
          events.py                # fixture/race/card hierarchy
          broadcasts.py            # EPG-event evidence links
          provenance.py            # source-family and accuracy
          quotas.py
        providers/
          registry.py
          transport.py
          sports/
            football_data.py
            sportsapi.py
            sportapi_ai.py
            jolpica.py
            tennis.py
            cricket.py
            boxerbook.py
            ...                    # gated plugins for more sports
          epg/
            xmltv.py
            public_guides.py
            farleyflex_reference.py
            ...                    # permitted sources only
        epg/
          canonical_registry.py
          source_crosswalk.py
          interval_quality.py
          coverage.py
        sports/
          normalize.py
          dedupe.py
          hierarchy.py
          completeness.py
        matching/
          broadcast_evidence.py
          confidence.py
        storage/
          sqlite.py
          migrations/
          last_good.py
        scheduling/
          jobs.py
          budget.py
          locks.py
        publishing/
          licence_policy.py
          asset_builder.py
          github.py
          manifest.py
        monitoring/
          health.py
          incidents.py
          notifications.py
      haos/
        sportsliveinfo/
          config.yaml
          Dockerfile
          run.sh
          DOCS.md
      frontend/
        package.json              # optional small TS/Vite client
        src/
          wizard/
          sources/
          epg/
          sports/
          scheduler/
          diagnostics/
      schemas/
        feed-manifest.schema.json
        channel-registry.schema.json
        epg-segment.schema.json
        sports-events.schema.json
      tests/
        unit/
        integration/
        contract/
        fixtures/
        security/
        performance/
      tools/
        example_inventory_export.py
        benchmark_report.py
        licensing_audit.py
      .github/workflows/
        ci.yml
        docs-check.yml
      docs/
        MASTER_IMPLEMENTATION_ROADMAP.md
        AUDIT_2026-11-12_FORENSIC_SPEC_AND_ARCHITECTURE.md
        INTERNATIONAL_EPG_AND_SPORTS_SOURCE_EXPANSION.md
        FEED_CONTRACTS_AND_PUBLICATION.md
        QUALITY_SECURITY_AND_ACCEPTANCE.md
        CODEX_CLAUDE_COLLABORATION.md

This is a **target tree, not a claim that code exists**. Build Python and test contracts first, then UI and integrations. Avoid heavyweight frontend tooling if a simple web interface suffices.

## 3. Technical architectural decisions

**ADR-01 — Python 3.12+ core.** Typed Python (dataclasses/Pydantic) for adapters, IO and scheduled data; unit-testable offline. No LLM inference or paid AI service in production path.

**ADR-02 — HAOS App, not HA Core integration.** Supervised container using `config.yaml`, a Dockerfile, persistent `/data` and admin-only Ingress. HA Core companion sensors optional; collection never runs in Home Assistant's event loop. Official: https://contributors.home-assistant.io/apps/how-apps-work/ and https://contributors.home-assistant.io/apps/guides/ingress/.

**ADR-03 — SQLite with WAL.** Store source snapshots/ETags, quotas, canonical entities, evidence, mappings, schedules, job runs, last-good manifests and incidents; schema migrations mandatory. Avoid database in immutable image. Bounded backup/restore and migration rollback.

**ADR-04 — Independent dual pipelines.** Separate EPG and sports schedules/budgets/concurrency. They share identities, evidence and publishing but **not a blocking common collection job**. Issue degraded status per product.

**ADR-05 — Source-specific licensing and independent-source provenance.** `source_id`, upstream family, data origin, country, policy and output permission. Mirrored sources do not count as independent evidence.

**ADR-06 — Read-only consumer.** B1G pulls only public licence-cleared JSON. No GitHub or sports API credentials on any TV, no automatic channel inventory upload. Explicit owner-initiated safe import is optional.

**ADR-07 — Immutable asset + manifest publication.** Assemble candidate offline, validate, write new versioned assets, verify read availability, only then switch manifest. Retain last-good. No consumer dependence on a partially published batch.

**ADR-08 — Strict matching and abstention.** Country/service/variant gates, exact source ID and manual overrides first; curated aliases second, strict name uniqueness next, fuzzy suggestion only if controlled; broadcast programme separately verified.

**ADR-09 — Data rights before public feed.** Do not assume community-provided EPG XMLTV can be copied into another public repository. Keep a prohibited/allowed-field matrix and default deny. If EPG rights cannot be cleared, B1G retains permitted original source access while central matching metadata remains available.

**ADR-10 — Versioned contracts.** JSON Schema, stable IDs, explicit major/minor schema evolution and golden test fixtures. Central and Android implementations independently consume the same fixtures.

**ADR-11 — CPU/IO limits.** Streaming XMLTV parse with decompression cap and timeouts; one heavy EPG parse at a time; bounded fetch concurrency; application resource budgets so household HA services remain responsive.

**ADR-12 — Visible-channel selection is local.** Central feed is a legal regional superset; B1G locally filters current account hidden categories/channels and only maps to an existing playable stream.

## 4. Implementation phases and exit gates

### Phase 0 — Baseline, consensus, contracts, environment (first)

**Owner:** Codex leads contract; Claude reviews and builds UI mock against frozen fixtures.  
**Deliverables:**
- Create actual Python package/pyproject/README setup, package import and deterministic offline test suite.
- Reconcile existing docs: classify historical vs normative; remove accidental promises of unrestricted free use or universal EPG publication.
- Pin primary B1 main commit, inspect EPG pipeline and actual versioned input expectation.
- Draft and freeze `schemas/*.json` plus 3–5 distinct example payloads: UK/FR channels, F1+football+boxing events, source conflict, no-broadcast and partial data.
- Define licence enforcement configuration and provider registry, disabled by default.
- Define integration contracts between Python and HA UI and B1G; agents may branch independently **after freeze**.
**Exit P0:** clean clone installs, imports, validates golden JSON and executes offline CLI using synthetic inputs; no HTTP required. CI green.

### Phase 1E — EPG full pipeline vertical slice (parallel with 1S)

**Owner:** Codex or assigned EPG adapter specialist; Claude reviews matching and UK/FR UI mock.
- Build bounded streaming XMLTV parser (XMLTV time offsets, Unicode and locales), source manifest downloader with ETag/Last-Modified, cache/timeout/retry and source-size ceilings.
- Build canonical broadcaster identity registry + explicit source namespace/crosswalk. Seed UK Sky/TNT/Premier/BBC/ITV and FR France Télévisions/TF1/Canal/beIN/RMC **only from verified allowed IDs**.
- Parse two *approved* synthetic guides into full rolling-channel schedules; report gaps, duplicate/overlap and source freshness.
- Generic-to-detailed interval-quality overlay, inspect preserved original programme and provenance, manual-mapping boundary and per-country timezones.
- Test 50k-channel metadata index without quadratic full-scan or memory blow-up. No unlicensed live ingestion in CI.
**Exit P1E:** 7-day full-channel EPG reference payload and correction report on synthetic UK+FR corpus; no wrong-channel matches and no data published illegally.

### Phase 1S — Sports full pipeline vertical slice (parallel with 1E)

**Owner:** Codex sports adapter specialist; Claude builds results previews and B1 mock against frozen fixtures.
- Sport model supports match/race/session/bout/card/tournament/day.
- At least football-data.org fixtures and Jolpica F1 under permitted prototype mode. Add versioned source adapters and a mock provider with fixture completeness states.
- Preserve event precision and UTC / Europe/London dates. Calendar import and competition registry.
- De-duplicate across sources without merging distinct races/tennis matches or two bouts on same card.
- Build source health / pagination metadata / quota engine and incomplete-day detection.
**Exit P1S:** football+F1 events on selected date and rolling horizon, fully testable offline, source evidence retained; unknown channel explicit.

### Phase 2 — Independent source expansion (two parallel tracks)

**EPG track:**
- UK + French permitted guide inventory, at least two candidate sources each; source lineage/independence and canonical ID acceptance.
- Build *opt-in*, secret-free B1G channel inventory export and HAOS import. Report matched, unmatched, hidden/visible counts by country/account (account data never public).
- Add only actual discovered country feeds (IE, BE, CH, DE, ES, IT, PT, NL, US/CA/AU, etc.) with explicit rights + channel count and freshness; avoid indiscriminate 65-country download.
- Validate full Guide programme windows, not just current events, with quality comparison against independently confirmed schedules and preserved original.

**Sports track:**
- Complete first-priority fixture lists for EPL/UCL/Europa/World Cup/internationals, F1 races/sessions, tennis Grand Slams/ATP/WTA, boxing world-title/major PPV, rugby union/league and cricket incl multi-day matches.
- Add quota-conscious SportsAPI and SportAPI.ai when key+terms validated; specialist providers (tennis, cricket, boxing) only when approved; source independence graph.
- Expand competition reference/aliases, status mapping, scheduled/TBC precision and quality reports.
**Exit P2:** quantified EPG coverage for real permitted UK/FR scope **and** independently measured fixtures for high-priority sports, including dated missing-coverage exceptions.

### Phase 3 — Evidence fusion, permissions, production-grade matching

- Link event -> specific EPG programme -> canonical service for each region, with negative highlights/replay/aggregate examples; never infer from league rights.
- Implement provenance and confidence finite-state logic, contradiction detection, independent-source weighting, generic programme correction overlay.
- Licence-gated per-field exports; private internal/testing snapshot may include allowed fields not approved for public, but public GitHub builder omits/rejects all unapproved fields (including prohibited EPG-derived text).
- Decide lawful fallback when UK/FR programme data cannot be publicly redistributed.
**Exit P3:** no false live-programme pairing in hard negatives; public builder passes fixture approval and publication gate tests.

### Phase 4 — HAOS App, settings and operations

**Owner:** Claude leads HA Ingress/web UI; Codex owns backend APIs/schema adapters.
- Local app install via `local_apps`, Supervisor config, Dockerfile, boot/watchdog, admin-only Ingress, persistent `/data`.
- First-run wizard only once: each eligible sports provider/EPG source has labelled signup URL and independent masked key Save/Test; no-key and restricted cards distinguished; optional source choices.
- Optional safe channel-inventory upload, UK/FR/country coverage dashboard, unmatched list and profile of allowed source rights.
- Separate GitHub target/token configuration and test (private code repo remains private); publish OFF by default.
- Accessible scheduler with Europe/London default, per-source quota-aware next-run preview, start-up recovery, no burst on missed jobs, last-good data.
- Low-noise persistent HA notifications for actionable failures; detailed local error history and redaction; no broad Core API access without review.
**Exit P4:** app installs on actual HAOS mini PC; initial config persists across reboot/upgrade/backup; Ingress auth/CSRF tested; HA automation responsiveness baseline preserved.

### Phase 5 — Publication and feed consumer

**Codex:** source gate/manifest/CI plus GitHub publishing writer. **Claude:** B1G Android reader and UI integration.
- Define public feed repo/Pages only with owner approval and source licences; never expose secrets.
- Publish versioned sports, EPG, identity and health assets, then atomic last manifest, and verify via read-only HTTP with cache header tolerance.
- B1G reader parses versioned schema, fetches manifest then selective required channels/countries and events, validates hashes, caches last-good; uses local visible-channel resolution, manual mappings and local provider guide fallback.
- Correct Android Sports Today 10 body + optional 11th PPV parity, actual channel/playback binding, event freshness and UI navigation.
**Exit P5:** one Fire TV/Shield demonstrates correct EPG by channel AND 10/11 sports cards, without storing provider keys or GitHub write token. Source errors leave Guide functional.

### Phase 6 — QA, evidence, multi-TV and production gate

- Historical fixture truth set (known past dates), forward-looking daily benchmark and independent human review of 7+ distinct sports windows and UK/FR regional schedule.
- Accuracy metrics: event recall by competition, verified UK/FR broadcaster precision, correct channel mapping precision, full-EPG programme time coverage and gap minutes, error/unknown rate, report freshness.
- Simulated ten-TV simultaneous reads, different hidden/category settings, account switching, renamed channels, ambiguous variants, offline and partial GitHub update.
- Actual HAOS resource profiling (memory, compressed EPG peaks, 24h uptime under normal HA workload), watchdog/backup restore/clock DST and key rotation.
- Security/terms gate, optional staged public data launch, incident playbook and rollback.
**Exit P6:** release receipt signed-off against both **EPG** and **sports** requirements; measurable supported-scope completeness; no claims of unsupported worldwide perfection.

### Phase 7 — Expansion and optimisation (post-baseline)

- Additional countries selected by actual safe subscription inventory.
- Sports expansion: MotoGP/Formula E/WEC/NASCAR, NBA/NFL/NHL/MLB, darts, snooker, golf, cycling, MMA, athletics, winter/Olympic sports, volleyball, handball, basketball, ice hockey and regional sports where genuinely covered.
- Optional user-configurable 24h/48h or 7-day international sport filter in B1, while 10-card default and PPV headline remain.
- Automated source drift detection, alias review suggestions, background source-coverage regression and manual correction UX.

## 5. Cross-cutting engineering acceptance targets (proposals, NOT measured)

| Metric | Proposed acceptance gate |
|---|---|
| Public source rights | 100% of published fields mapped to documented permitted-use source/path; default DENY if unknown |
| No false mapping in hard-negative tests | 0 |
| Confirmed event-to-UK channel precision | >=99.5% on held-out, manually labelled in-scope sample; report sample size/abstentions |
| Canonical channel auto-map precision | >=99.5% on labelled in-scope multi-region benchmark, with separate coverage/abstention metrics |
| High-priority fixture recall | Target >=95% for explicitly supported competitions, separately by sport; record unavailable competitions |
| EPG coverage | >=95% of selected source-eligible visible priority channels should have a >=24h valid forward programme window, subject to provider rights and source availability; report per-country/time-window gaps |
| Time correctness | 100% deterministic UTC->London/Paris DST test corpus; real-world time error tracked separately |
| Upstream provider calls from B1G | Exactly 0 when central mode active |
| Ten client simultaneous reads | Same valid feed revision or safe last-good; no source quota change |
| Failed provider/publication | Last-good retained; health degraded, never publish false empty-day |
| Secrets in public/CI logs | 0 |
| Home Assistant impact | No significant home automation delay/crash in profiled HAOS test; set thresholds from measured baseline rather than inventing RAM limit |
| Sports rail | 10 body cards when enough eligible events + separate PPV card if enabled; no duplicate, wrong-stream or hidden-channel playback |

A metric can be marked N/A only with a documented out-of-scope explanation; a provider outage is not a successful empty day. Targets should be recalibrated using an independently labelled baseline, never proclaimed achieved by code existence.

## 6. Build governance and two-agent ownership

The authoritative agent handbook is `CODEX_CLAUDE_COLLABORATION.md`. In brief:
- **Codex:** core/data contracts, adapters, identity/EPG/event logic, SQLite, licence/publisher/scheduler backend and backend tests.
- **Claude:** HAOS web UI/Ingress/configuration, B1 Android central-feed client and remote-control UX, UI tests and integration acceptance.
- Contract/schema edits require cross-agent review before either relies on them.
- Work in distinct git worktrees/branches, submit small PRs, merge in dependency order after CI. Do not modify the same file on two branches without explicit rebase plan.
- Use synthetic test data and keep credentials/provider responses/user's actual subscription inventories out of Git.
- Store dated receipts and next-work checklist in `docs/IMPLEMENTATION_PROGRESS.md` once engineering begins. No fabricated 'implemented' checkmarks.

## 7. One-page execution order for terminal agents

1. Both agents read README, AGENTS and **this** file; record repo HEAD and HA installation type when accessible.
2. Codex creates P0 package + frozen JSON contract PR; Claude reviews and works on mock UI fixtures in a separate branch.
3. In parallel build **P1E XMLTV+identity** and **P1S fixture provider+event** foundations; neither blocked by full HA UI.
4. Integrate source data, produce independent EPG and sports benchmark receipts; do not skip licence gate.
5. Build app Ingress onboarding and backend contract, plus mocked B1 reader/last-good selection.
6. Add evidence fusion, international EPG, broadcaster matching and reliable publisher.
7. Install on actual HAOS, use one B1 TV, then all ten after tests, with rollback ready.
8. Expand sports/countries based on measured gaps; avoid paid APIs, artwork scope creep and speculative near-real-time promises.

## 8. Explicit non-goals

No central VOD/movie/series poster/hero/TMDB/OMDb metadata; no new IPTV streaming server; no scraping or mirroring without rights, no paywalled data, no premium EPG subscription by default, no login upload, no device-to-GitHub write credentials, no universal live-score SLA, no artificial intelligence in the runtime critical path, no silent assumptions that a user subscribes to a specific broadcaster.
