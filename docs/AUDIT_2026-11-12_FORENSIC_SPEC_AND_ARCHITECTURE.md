# Forensic audit: SportsLiveInfo specification, source feasibility, skeleton and delivery readiness

> **Historical audit / receipt — reviewed 12 November 2026.** Preserved against its stated original revision. Findings, branch/merge positions, provider claims and pass counts below are historical, not freshly verified current facts. Current source is v0.3.0; the combined review attempted 86 tests (81 passed, five errors, three of those environment-blocked). Use CURRENT_STATUS for resolved/remaining work; no new live source, licence or device verification occurred.
> **Repository roles:** [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is the public App source and installation repository; [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is PUBLIC daily data only. [Current status and evidence](CURRENT_STATUS.md).

**Date:** 12 November 2026  
**Audit scope:** All 20 tree entries on `jimmyfazz/SportsLiveInfo` main `d375ced20f3333f8162efd3a52778c7753c476e2` at inspection; previous code-based audit of `jimmyfazz/B1` main and its Android EPG/Sports Today pipeline; contemporary provider and Home Assistant documentation.  
**Evidence categories:** CODE = directly read implementation; DOC = existing project specification; OFFICIAL = vendor/maintainer documentation; HYPOTHESIS = requires runtime validation; LICENCE-UNVERIFIED = externally accessible but reuse not established.  
**Status:** audit + prescribed remediation, NOT evidence that SportsLiveInfo is running or has complete coverage.

## A. Executive assessment

SportsLiveInfo must be treated as **two equally complete products on one shared platform**:

- **Product A: International EPG intelligence.** Subscription-aware discovery of needed television services; source catalogue, licensed guide import, source namespaces and aliases, quality-based programme enhancement, coverage/accuracy reports for UK, France and additional countries from the actual B1G channel inventory, while maintaining B1G local channel identity, hidden flags and user overrides.
- **Product B: International sports event intelligence.** Independent discovery of dated fixtures across football, rugby, tennis, Formula 1 and other motorsport, boxing/MMA, cricket and expansion sports; sport-specific event/session hierarchy; actual confirmed broadcaster and coverage time where the evidence supports it; complete selected priority-competition calendars, plus 10–11 curated Home cards.

Shared platform owns provider adapters, quota controls, scheduler, normalisation/evidence, event/channel crosswalk, persistent last-good cache, licensing gate, GitHub publication, Home Assistant Ingress onboarding and quiet notifications. Only **B1G** maps canonical broadcasters to local streams and respects per-account visibility. Ten TVs are read-only and never hold API/GitHub write keys.

### Audit conclusion

The repository currently contains documentation and a candidate file layout but **no runnable collector, HAOS App, real providers, schema validation, test suite, build, feed or instrumented accuracy reports**. It is premature to label either feature operational or comprehensive. Building only one side and leaving the other as an aspirational later feature would fail the owner's request. See `docs/MASTER_IMPLEMENTATION_ROADMAP.md` for the replacement execution plan.

## B. Forensic findings register

Severity: **P0 blocker**, **P1 major**, **P2 enhancement**. Each entry includes a proposed acceptance proof.

| ID | Priority | Finding / consequence | Required correction | Proof required |
|---|---|---|---|---|
| AUD-001 | P0 | Entire repo is research/docs only; no importable Python package, CI, CLI, migrations or HAOS App. | Bootstrap reproducible Python package, tests, fixtures, local CLI and HAOS App shell. | Fresh clone installs and offline tests pass on Linux. |
| AUD-002 | P0 | No single canonical requirement order; earlier documents imply UK-only and 'optional B1' while user now mandates multi-region EPG AND sports. | Master implementation roadmap and ADRs supersede earlier conflicting scope statements. | Agent PRs cite roadmap gates; both A and B have complete release gates. |
| AUD-003 | P0 | Public GitHub feed vs provider-derived guide/event data licensing unresolved. Public-read access is redistribution regardless of owner's private TV use. | Per-provider, per-field source licence approval; local-only/private test outputs; explicit public publish denial until approved; legal review or provider permission for uncertain rights. | Unit test proves restricted EPG cannot appear in public export, even from a delta/rephrasing. |
| AUD-004 | P0 | Programme identity and fixture identity can be conflated, enabling wrong TV channel/false 'live' badges. | Four separate relations: canonical channel; source EPG ID; local B1G channel; sporting event-to-live-programme evidence. Separate broadcast/live-event statuses and start times. | Hard negatives: studio preview/highlights, multiplex feed, UK/FR rights, F1 qualifying. |
| AUD-005 | P0 | B1G source-bound farleyflex 17-alias mapping will not automatically recognise new SportsLiveInfo URL/source. | Versioned `source_id`, per-source EPG ID namespace, canonical-channel registry, confidence/evidence; B1 local account mapping. | BBC regional, Sky Sports+ and France Canal/beIN/RMC regression tests; no wrong auto-map. |
| AUD-006 | P0 | Current B1G gap-only precedence can preserve generic baseline 'Live Football' instead of verified match names. | Bounded quality-overlay processor promoting specific verified broadcast title under compatible channel and interval; retain whole originals for reversible fallback. | Generic-to-specific replacement; conflicts/overlap unchanged; no filler/highlights promotion. |
| AUD-007 | P0 | EPG-only discovery and fixture-only discovery need both directions. Source-only fixture APIs miss channels/events; EPG-only fails non-televised sport. | Dual discovery pipelines, independent inventories, explicit dedupe/reconciliation, orphan-event and orphan-EPG diagnostics. | Feed includes fixture-only and EPG-only provisional records with state provenance. |
| AUD-008 | P0 | No measurable 'complete' contract; millions of worldwide programmes cannot be promised free. | Owner-ranked channel/service tiers, country and competition coverage matrix, per-source coverage age and benchmarked recall/precision. State missed/unavailable explicitly. | Per region & sport dashboard; documented hold-out benchmark and failures. |
| AUD-009 | P0 | Missing actual subscription channel inventory; GitHub B1 source code does not reveal playlists. | Optional owner-triggered local secret-free inventory export/import; start UK+FR baseline even without it. No TV GitHub writes. | Export has zero credentials/stream URLs; large-account and hidden category tests. |
| AUD-010 | P0 | SportsAPI free quota advertised inconsistently (pricing 100/day, docs 1000/day), and all-sport fixtures pagination costs calls. | Conservatively configure quota at 100/day until key headers/account verify; reserve emergency budget, separate month cap for other APIs, stop incomplete pagination. | Contract tests 429, out-of-quota, incomplete pages, header change, no false empty-day. |
| AUD-011 | P0 | Cross-source 'agreement' may reflect mirrors of same upstream (farleyflex -> iptv-org -> mytelly). | Track `data_lineage`, upstream family and actual independence; corroborate with official calendar/legit broadcaster when available. | Two mirrors count as one evidence family, not independent votes. |
| AUD-012 | P0 | Authentication and publishing credential boundary not implemented. HA options storage is plaintext in container; UI masking is not encryption. | HAOS App Ingress admin-only, restricted persistent data, safe secret handling, OS backup warnings, least GitHub contents permission, no logs/URLs with credentials. | Secret-scanner and restore test; no key in JSON/log/TV; no WAN listener. |
| AUD-013 | P0 | GitHub static publication can be partially updated if assets/manifest order/caching not controlled. | Content-addressed versioned assets, publish all and validate before switching manifest pointer, client revision validation/last-good. | Simulate failure between stages and stale CDN; old feed still valid. |
| AUD-014 | P0 | No HA runtime/busy-host safeguards: XMLTV decompress and provider polling can monopolise mini PC. | Bounded decompression/streaming XML parser, max byte/rows, memory/CPU/time budgets, job concurrency=1 for heavy EPG, SQLite WAL, cancellation/health/watchdog. | Load-test >50k-channel catalogues and large compressed XMLTV without HA degradation. |
| AUD-015 | P1 | App first-run wizard is detailed but no tested UI/adapters, and includes numerous non-eligible sources. | Registry-driven wizard; each implemented/eligible provider independently Save/Test; no-key label; optional sources; user selections survive restart; GitHub publishing disabled by default. | HA Ingress automated UI test plus real HAOS smoke test. |
| AUD-016 | P1 | HA notification design has potential broad Core admin API privilege. | Security-review direct Supervisor Core API or implement minimal companion bridge; dedupe/cooldown/persistence; no repeated push. | Only actionable incidents generate notifications; no secret leakage. |
| AUD-017 | P1 | Daily 05:00 snapshot cannot be same-day farleyflex newest data: upstream job scheduled 06:00 UTC and can run later. | Morning last-good + later source-version-aware refresh; track upstream commit and actual programme horizon. | Timezone/DST and delayed upstream release tests. |
| AUD-018 | P1 | Source may return `200 []` despite outage/partial competition coverage; B1 football reconcile can discard EPG fixtures absent in API-Sports. | Completeness as per provider/competition/day, strict non-destructive reconcile; preserve credible EPG fixtures where coverage missing. | Empty-page/partial-fixture tests show no valid event disappeared. |
| AUD-019 | P1 | Mac's 10-body+PPV 11-card rail and Android's PPV within 10 differ. | Shared feed returns all candidates and explicit event type; B1 parity selection logic: 10 body + optional distinct PPV headline if chosen. | Platform-specific parity tests, never duplicate card. |
| AUD-020 | P1 | Sport-specific start models insufficient: cricket multi-day, tennis not-before, boxing card/walk, F1 session/race, cycling stage, golf tournament, darts session. | Common event hierarchy + sport extensions, scheduled/estimated/unknown precision, UTC and local dates/regions. | Synthetic date/time and hierarchy tests across all priority sports. |
| AUD-021 | P1 | Country and channel name expansion may mix rights or regions (France, Belgium, Switzerland, Canada). | ISO territory + service edition, language and parent/child variants; locale-specific alias rules and hard negative mapping cases. | CANAL+/beIN/RMC and BBC/France/TV5 regional negatives. |
| AUD-022 | P1 | Stale local account/hidden-channel state can cause central feed to retune hidden/missing streams. | B1 current-account visible projection first; generation-safe resolution; manual mappings/suppression take priority; no server-side stream IDs. | Hide/unhide, account switch, 10-TV different-user views. |
| AUD-023 | P1 | Few source APIs can reliably supply PPV and OTT-only TV carriage (no linear XMLTV); many EPGs omit event-only feeds. | OTT/PPV evidence adapter distinct from linear EPG; separate broadcaster/platform/entitlement and event card vs bout/ring-walk. | At least one verified PPV card in test, TBC time not fabricated. |
| AUD-024 | P1 | Country-wide EPG downloads may be huge and legally unclear; 65-country catalogue is not an approval list. | Country/source opt-in from visible subscription inventory, provenance/legal gate, strict size and source refresh budgets; UK+FR first. | Source source-budgets, absence of unneeded country downloads. |
| AUD-025 | P1 | No stable versioned schemas/migrations for future two-agent parallel implementation. | Version contracts with golden JSON fixtures; explicit compatibility and rejection policy; ADR owner, branches and merge sequence. | Consumer fixture tests pass against pinned schema and backwards compatible changes. |
| AUD-026 | P1 | Provider quotas partly daily, partly monthly, and reset in UTC or provider timezone, not local scheduler timezone. | Budget ledger per key/provider/endpoint day+month, reserve threshold, `Retry-After`, adaptive polling and circuit breaker. | 10 TV downloads create zero sporting API calls; no overspend at BST boundary. |
| AUD-027 | P1 | Source results can be inconsistent independent of EPG timestamp due to ambiguous daylight-saving offsets, incomplete/invalid broadcast intervals. | Explicit UTC normalization, IANA Europe/London/Paris, authoritative XMLTV offsets, interval quality validation, reject inverted/stale records. | DST spring/fall, 23/25-hour UK days, overnight sport, timeshift. |
| AUD-028 | P1 | No QA/observability dashboard or sampled verification results. | By-source coverage, match precision, event recall, stale guide horizon, missed jobs, publish freshness, provider call counts, incident history. | Live benchmark report and HA dashboard with tracked actual metrics. |
| AUD-029 | P1 | Inconsistent publication plan with availability of GitHub Pages on private GitHub Free. | Keep `SportsLiveInfo` private; optional separate public `SportsLiveInfoFeed` only if approved; no premature repo creation or visibility change. | Verification of actual published URL/rights and read-only client. |
| AUD-030 | P1 | Codex and Claude might overwrite common code and docs, introducing divergent schemas. | Assign branch/file owners and handoff checkpoints; one contract owner; integration fixtures; no parallel same-file edits. | Each work package has lead, reviewer, explicit merge order and green tests. |
| AUD-031 | P2 | Additional sports absent (MotoGP, Formula E, NFL, NBA, NHL, MLB, darts, snooker, golf, cycling, MMA, esports). | Expand plugin registry and sport taxonomy with published coverage claims tested per league; not all mandatory day-one. | Sport-by-sport coverage benchmark and enabled status. |
| AUD-032 | P2 | International free EPG discovery metadata can improve mapping but may contain stale or unapproved EPG sources. | Add IPTV-org guide/channel directories, XMLTVProject and country guides as discovery-only candidates subject to terms and field-level review. | Safe catalogue import with no copied programme data absent rights. |
| AUD-033 | P2 | Debugging wrong EPG mappings on ten TVs can become difficult. | B1 diagnostics screen: exact/alias/fuzzy/manual, confidence, region/variant, source/version, why no match, manual resolution. | Repro report without streaming URL/token and deterministic input fixture. |
| AUD-034 | P2 | Artwork/crest/ratings scope creep could consume quotas and delay rails. | Keep TMDB/OMDb/film/series/poster/hero and local crest handling in B1G, excluded from SportsLiveInfo. | No artwork metadata services in collector dependencies or wizard. |

## C. Source research corrections (dated, not permanent facts)

1. **SportsAPI.app**: official /pricing shows Free 100/day, official /docs/limits shows 1000/day during beta; homepage references returning to 100/day. These pages conflict. Design for 100/day until actual account headers and provider terms establish the live allowance. `https://sportsapi.app/pricing`, `https://sportsapi.app/docs/limits`, `https://sportsapi.app/docs/catalog/sports-coverage`.
2. **SportAPI.ai**: separate football/basketball supplier with free 1000/day but 7000/month on pricing (from 1 December 2026), so budget monthly and daily independently. `https://sportapi.ai/pricing` and `https://sportapi.ai/docs`.
3. **SportsDataIO**: free trial **can contain deliberately scrambled data**; not a trustworthy actual live sports source even if a test endpoint returns real-looking records. `https://sportsdata.io/developers`.
4. **OpenFootball JSON**: CC0 repository files regenerate daily but README states upstream Football.TXT inputs are not updated automatically; freshness cannot be claimed from commit time. `https://github.com/openfootball/football.json`.
5. **TheSportsDB**: free app-store publication restricted in 2026 terms; free per-endpoint data limits; no blanket B1 published data permission. `https://www.thesportsdb.com/docs_terms_of_use.php`.
6. **Boxerbook**: schedule/broadcaster fields valuable, but terms updated Nov 2026 require personal/non-commercial usage for free API; bulk/redistribution rights require separate approval. `https://boxerbook.com/developers`, `https://boxerbook.com/terms`.
7. **IPTV-EPG.org**: 65 countries listed; the website's 'free feed' does not prove free **redistribution** of EPG rows on public GitHub or fitness for a specific subscription. `https://iptv-epg.org/guides`.
8. **IPTV-org**: `/api/channels.json` and `/api/guides.json` are promising service/guide crosswalk discovery; user data never read from this public catalogue. `https://github.com/iptv-org/api`.
9. **Home Assistant**: apps are supervised containers under HAOS, persistent `/data`, local `local_apps`, Ingress. Building an App is different from a Core integration. `https://contributors.home-assistant.io/apps/how-apps-work/`, `https://contributors.home-assistant.io/apps/guides/ingress/`.

## D. Risks requiring explicit acceptance

**R1 — Public EPG rights (highest):** If no suitable licence for the UK/FR programme descriptions, use B1G's legitimately configured direct EPG and publish only licensed event/identity metadata. This is a genuine deployment blocker for a publicly republished central full EPG, not a technical bug.

**R2 — Absolute 'completeness' unsupported:** Upstream free plans, country variations, date-dependent tennis schedules, boxing PPV and unknown subscriptions cannot justify 100% worldwide claims. Define a bounded **supported coverage set**, publish missing/partial status, and expand based on real inventory and benchmark.

**R3 — False channel playback:** Highest user-impact technical error. Require hard identity gates and actual event-to-programme evidence; abstain rather than guess.

**R4 — Home Assistant household reliability:** Collector and XMLTV parser must be bounded; a failing app must not affect Home Assistant automations.

**R5 — Two-agent integration drift:** Contract PR lands first; subsequent parallel PRs target unique folders and gate on consumer integration tests.

**R6 — Security of provider tokens and publishing credential:** Never put secrets, provider-specific authenticated URLs or user account data into public feed or logs. Treat HA backups as sensitive.

## E. Decisions and outstanding externally verifiable facts

**Confirmed owner decisions:** direct-installed home mini PC with HAOS expected; ten B1G TV clients read-only; one-time supplier keys entered in HA first-run wizard; outbound-only GitHub publication; high-priority UK and French EPG and international expansion based on visible subscriptions; sporting rail with correct broadcaster; no film/series art/TMDB/OMDb centralisation; two terminal agents Codex and Claude.

**Not known without live tests / owner setup:** exact HA installation type/CPU architecture; current B1 subscription channel inventory; selected supplier keys and actual limits; permissions to republish third-party EPG/programmes or sports-derived records; user-approved public-feed repository and URL; live fixture and EPG accuracy; Android B1 build/runtime on Fire TV/Shield. No audit may treat these as accomplished.

## F. Implementation control

The normative next-step documents are:
- `MASTER_IMPLEMENTATION_ROADMAP.md` — authoritative architecture/phase gates/ownership.
- `INTERNATIONAL_EPG_AND_SPORTS_SOURCE_EXPANSION.md` — source/country/sport coverage and validation.
- `CODEX_CLAUDE_COLLABORATION.md` — branches, file ownership and integration process.
- `FEED_CONTRACTS_AND_PUBLICATION.md` — canonical schema, licence gate and manifest protocol.
- `QUALITY_SECURITY_AND_ACCEPTANCE.md` — quality metrics, CI, security and runtime tests.

Older docs remain historically useful but cannot override newly confirmed user scope or these updated gates. Keep changes to this audit dated and traceable.
