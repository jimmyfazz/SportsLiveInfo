# SportsLiveInfo — implementation progress and agent handover

> **Current documentation context — reviewed 12 November 2026.** Experimental v0.3.1 source is present (13 Nov code audit fixes: see docs/CODE_AUDIT_AND_FIXES_2026-11-13.md). Current source/test evidence and open deployment gates are centralized in CURRENT_STATUS; historical version receipts elsewhere are not current pass claims.
> **Repository roles:** [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is the public App source and installation repository; [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is PUBLIC daily data only. [Current status and evidence](CURRENT_STATUS.md).

**Updated:** 12 November 2026  
**Repository:** `jimmyfazz/SportsLiveInfo` (remains PRIVATE).  
**Historical v0.2 development branch:** `feat/haos-epg-coverage-openligadb-v0.2-20261112`; PR #2. Historical PR #1 delivered v0.1.0.

## 13 November 2026 — 0.3.5 source connections and coverage

Baseline: main at `7253381` (App 0.3.4). Local EPG refreshes reserve space for the remaining scheduled slots before midnight UTC. An exhausted local budget is a deferral. Guide revalidation uses HTTP validators while saved programmes still cover upcoming airings. Sports collection reuses recent future-date results, retries failed dates and backs off after upstream throttling. The tennis connection test checks upcoming ATP, upcoming WTA and the live board. PandaScore is an optional, disabled-by-default private esports fixture source. [PandaScore upcoming matches reference](https://developers.pandascore.co/reference/get_matches_upcoming).

An offline replay of sampled XMLTV files produced these counts. Each count is the number of distinct canonical services recognised in that feed.

| Guide sample | Programmes parsed | 0.3.4 | 0.3.5 |
| --- | ---: | ---: | ---: |
| IPTV-EPG.org GB | 123,236 | 32 | 42 |
| EPG Share US2 | 82,110 | 6 | 11 |
| EPG Share CA2 | 67,277 | 0 | 12 |
| IPTV-EPG.org CA | 122,781 | 0 | 11 |
| EPG Share US SPORTS1 | 102,292 | 0 | 0 |

Python 3.12 compiled the package and passed 154 tests. The mappings match exact channel IDs within each source. The US SPORTS1 sample provided no verified canonical service IDs. Programme and fixture coverage, provider reachability from HAOS and the authenticated PandaScore response still need verification. Dedicated calendars for the remaining sports and event-specific boxing PPV broadcast confirmation remain open. Publication permissions are unchanged. The App uses the existing slug and database with no migration. Roll back through the previous App build or the App backup.

### Upcoming broadcasts and boxing follow-up

The local Sports Events view matches listings across today and the following seven UK dates, where saved guide slots overlap fixture times. It shows the channel, market, guide start and source, and distinguishes unconfirmed times, missing usable guide slots and unmatched programme titles. The windowed matcher reads one saved guide at a time and bounds each lookup by the accepted maximum programme duration. Guide matches remain unverified.

Open Boxing is disabled by default. A live probe of the documented endpoint decoded 14 scheduled world-title bouts, all date-only. Card times, ring walks, non-title bout coverage and event-specific UK broadcaster or PPV evidence remain open. [Open Boxing API](https://www.openboxing.org/api/). The app slug and database schema are unchanged. Home Assistant runtime verification remains pending.

### Source contribution and British racing follow-up

Sports Events counts deduplicated fixtures per source, including how many that source alone supplied. EPG Coverage counts fixture/channel pairs and exclusive matches per guide. Diagnostics shows known quota or throttle retry times in UK time.

The optional British Horseracing Authority adapter uses the calendar download offered by the [official fixture list](https://www.britishhorseracing.com/racing/fixtures/full-year/). The live files produced 1,451 meetings in 2026 and 1,443 in 2027 across 59 venues in each year. Meetings carry dates and session labels. Individual race times and broadcast evidence require separate sources. A successful annual refresh replaces that season only after the calendar passes the structural and date-coverage checks. The source is disabled by default and redistribution still requires review under the existing publication gate. [BHA website terms](https://www.britishhorseracing.com/terms-conditions/).

### Named tournament and session matching

The local guide matcher accepts explicitly live listings for selected named tournaments in golf, snooker, cycling, darts, athletics and horse racing. It requires matching round, stage, day and session details where present, distinguishes women's and other variants, and rejects repeats and highlights. A date-only fixture cannot create a time-based candidate. Match details show the evidence type. Coverage against a live Home Assistant snapshot remains to be measured.

### Guide gap diagnostics

Sports Events and Live Today distinguish no saved programme data, dates outside the saved guide ranges, no usable recognised channel slot, no fixture title match and an exact listing on an unmapped channel. Unmapped listings remain local diagnostics. Matching details show when multiple guides share an upstream family. Diagnostics now renders the quota-reset time for an exhausted local budget.

## 13 November 2026 — 0.3.4 audit integration

The integration combines mobile/coverage head `17786a8` and audit head `95f79d5`, with selected operator-dashboard behaviour and the older indexing branch’s differential tests. It keeps fixture retention for sources of unknown completeness and the source-specific XMLTV declaration allowlist. Removed the unused launcher, superseded architecture and data-contract proposals, and obsolete golden-feed assets. Earlier revisions remain in Git history.

The upgrade uses the existing App slug and database. See [current status](CURRENT_STATUS.md) for open deployment checks and [operator instructions](../sportsliveinfo/DOCS.md) for backup and rollback.

## Collection consistency and EPG matching — 13 November 2026

Baseline: private PR #10 commit `b963f66e5e37c2d08a934df2a42abc4c580d64eb`. SQLite commits the sports, today and EPG dashboard snapshots together. Guide data and its quality report also commit together. A failed combined write leaves the previous dashboard available and records a collector failure. This requires no database migration.

EPG matching parses each fixture time once, skips expired programmes using an end-time index and retains source order for representative matches. Python 3.12.14 compiled the package and passed 98 tests, including a forced SQLite rollback and programme boundary tests. A synthetic run with 457 fixtures and 8,000 programme rows produced identical candidates for 443 fixtures. Runtime was 5.782 seconds before and 1.508 seconds after on this runner. HAOS runtime and live coverage are still unmeasured for this revision. Source rights and the public feed contract are unchanged. Rollback uses the prior App build and existing SQLite schema.

Follow-up on baseline `49e6795ce7df695ed903afdb901fb7e1e5cb1caa`: Overview reads its three related snapshots in one SQLite statement. Feed builds similarly read combined sports and source snapshots together, fetching timestamps only for raw provider snapshots. Provider health can still show newer attempts while a refresh is in progress. The keyed provider form validates first and saves its enable switch and credential together. Python 3.12 compile and 100 tests passed, including byte-identical golden feed fixtures and regression tests for timestamp-only reads and rejected key edits. Live HAOS verification remains pending.

Manual refresh follow-up on `0fbbcc6e430eef914563f465fe94076cfcb52e2e`: Overview offers Sports-only and EPG-only refreshes. Both use the existing worker lock and rebuild the dashboard from last-good inputs. Scoped refreshes call only the selected engine and skip automatic publication. Source cards show the last successful refresh, latest recorded activity and remaining local UTC-day requests. The existing scheduled collection path still refreshes both engines. Python 3.12 compile and all 103 tests passed. No provider, schema or source-rights changes. Live HAOS verification remains pending.

Live Today follow-up on `3f689396dd1282a44985856e514c25561b8afa43`: filter the saved UK-day snapshot by sport, put live fixtures first within each competition and show finished, postponed or cancelled fixtures in collapsed details. The view flags a prior-day snapshot and retains the event list. The ordering uses saved provider statuses. Python 3.12 compiled the package and all 104 tests passed. No extra provider calls, data migration or feed contract changes. Live Ingress verification remains pending.

Distribution note, 13 November: GitHub now reports the App source repository as public. The Home Assistant store identifies a GitHub repository installation by a repository-prefixed slug. The existing `local_sportsliveinfo` installation uses its local App files and retains its own data. To test v0.3.1 while keeping that data, use an in-place local update. A move to the repository-backed App needs a separate migration and verification of the saved data before removing the local App. The public daily data feed remains a separate repository.

## v0.3.1 dashboard maintenance — 12 November 2026

Baseline: private main `56ea1bee0611d1343f4a05f2d7983e146f415606`. The live v0.3.0 HAOS snapshot showed 1,223 sports events and eight EPG guides. This maintenance build fixes the fallback labels, zero rendering and misleading full-coverage rows using existing snapshots. It adds no provider requests, licence changes, schema changes or storage migrations.

Verification: Python 3.12 compile and 95 tests, including regressions for dashboard rendering, collector status, EPG error handling and unconfirmed start times. The golden fixture includes the updated producer version and channel registry. The v0.3.1 Home Assistant update and persistence check are pending. Keep the existing local App installed for an in-place update, take an App backup first, and retain v0.3.0 App files and the backup for rollback.

Follow-up: Overview displays the latest collector activity and live badges are explicitly as of the refresh. EPG diagnostics distinguish upstream HTTP status, network or timeout, size or record limits, local quota and invalid input without logging raw exception text. Events marked time TBC cannot create time-based EPG candidates or estimated live statuses.

The 22:02–22:04 GMT v0.3.0 refresh reproduced generic failures across UK, France, US, Canada and Australia candidates. Both Hong Kong guides returned programmes but recognised zero canonical services. Next priorities are to measure repeat failure reasons using the new diagnostics, then add region-specific aliases against captured channel names and variants. Compare the clustered midnight starts against provider timestamps and schedules before treating them as missing times.

Source setup now has separate bulk selections for keyless sports providers and private EPG guides. Tick all only changes the checkboxes; each group is saved independently in one transaction. Save leaves API keys, keyed provider switches and the other group intact. Provider tests remain individual and Save makes no network requests.

Source research, 12 November: [dp247's Freeview file](https://github.com/dp247/Freeview-EPG/blob/master/epg.xml) is listed at 20.7 MB, beyond the former 14 MB download cap. [XML TV Fr](https://xmltvfr.fr/xmltv/) lists the France-only guide at about 70 MiB expanded, beyond the former 65 MB cap. Targeted limits are now 30 MB download and 85 MB expanded, respectively. Parser and record safeguards remain enabled. Retest both on HAOS before claiming a successful import. The same publisher lists a smaller France TNT candidate for further testing.

[EPGTalk](https://github.com/acidjesuz/EPGTalk) lists both configured filenames; keep them pending the new diagnostics. [iptv-org](https://github.com/iptv-org/epg) documents locally generated guides; the failing static Sky, French and Foxtel URLs remain unverified. Matt Huisman's [Foxtel](https://i.mjh.nz/Foxtel/) and [Kayo](https://i.mjh.nz/Kayo/) indexes list guide files but their forward coverage needs measuring before use. No new feed endpoints or redistribution permissions were added.

Hong Kong channel identity: added 25 distinct Now Sports and beIN services from the [Hong Kong Communications Authority Now TV lineup](https://www.coms-auth.hk/filemanager/en/content_1788/info_doc.pdf) (December 2025). Numbered Premier League and 4K services stay distinct. Conflicting explicit geographic prefixes are rejected for market-scoped name matches; exact source ID crosswalks retain precedence. The additive channel registry and synthetic golden manifest were regenerated. Actual recognition counts on the two HAOS guides and B1G reader acceptance remain pending. No live guide or event records were added to GitHub.

## Code audit and fixes — 13 November 2026 (v0.3.1)

**Branch:** `claude/sportsliveinfo-b1g-android-syyo8j` (merged `main` `56ea1be`). **Status:** SOURCE IMPLEMENTED + LOCAL TESTED, **118/118** tests (Python 3.12.3 and 3.13). Report: [CODE_AUDIT_AND_FIXES_2026-11-13.md](CODE_AUDIT_AND_FIXES_2026-11-13.md).

**Fixed:**
- server/GUI S1–S9 and GUI-1 to GUI-9;
- engine E-01 to E-05, E-08 and E-10;
- feed/publisher FA-01 to FA-08 and FEED-1;
- matching D1–D14;
- new icon/logo.

**Open:**
- E-06/TF-14: EPG storage memory and lock contention;
- a self-hosted guide (local-source) exception;
- background jobs for long UI actions;
- packaging hardening (pinned base image, CI docker build, secret scan);
- post-publish anonymous verification.

**Ownership note:** Codex-owned engine/feed/adapter files were edited at the owner's direct request; Codex cross-review requested before merge. **NOT RUN:** live provider requests, Docker build, HAOS Supervisor/Ingress, B1G devices.

## Current documentation reconciliation — 12 November 2026

**Baseline:** `main` at `579541fa9a8f7f0108e454f654221c01049b6e76`; documentation branch `docs/current-documentation-20261112`. This baseline already contains the v0.3.0 expansion, forensic hardening, token onboarding and packaging source. Older branch-specific sections below are historical receipts, not unmerged-work or current-green claims.

**Work:** reconcile every Markdown document, add [current status](CURRENT_STATUS.md) and [document index](DOCUMENTATION_INDEX.md), correct installation and repository roles, current source counts, feed limits and acceptance gates; repair deterministic feed-test inputs and make ingress tests exercise the real handler/parser under socket-restricted runners. Production runtime, schemas/golden fixtures, HA settings and visibility unchanged.

**Verification:** the original documentation pass recorded a failing 86-test baseline; the follow-up correction now passes **88/88 tests** on Python 3.12.15 and compileall passes. Rights-test events now use taxonomy classification and a pinned clock. Ingress tests share a fallback that invokes the real handler/parser in memory when loopback binds are denied. Golden fixture/hash tests pass unchanged. The local runner denied socket binds, so real loopback and GitHub Actions require separate evidence; details are in CURRENT_STATUS.

**Owner-confirmed roles:** SportsLiveInfo is PRIVATE source/installation; LiveSports-EPG is PUBLIC daily feed, checked README-only. No rights-approved feed or device deployment established. HA connector in this session exposed no Supervisor/App tools; no exposed SportsLiveInfo entity was found, which does not establish installation absence. Existing owner authenticated remote administration is separate from the project's no-new-public-App-endpoint requirement.

**Coverage/rights:** source counts are 16 sports entries (10 API-Sports), 27 EPG candidates across 15 markets, 24 taxonomy sports / 127 competitions, service tables in 8 markets / 41 families. Live completeness and terms were not reverified. Local programme suggestions exist; public `epg_supplements` contract and TV rendering do not.

**Next:** confirm current GitHub Actions evidence and real-loopback behavior, then validate private HAOS and live source/rights. **Rollback:** revert this documentation/test commit; no runtime migration. **Review:** PR #9 contains the documentation and test corrections.

## Historical implementation receipts

The following sections preserve what their original revisions reported. Statements such as “no public feed repo created”, “not executed” and “55 tests pass” must be read against that section's revision; current facts and results are above and in CURRENT_STATUS.

## Source expansion and sports sub-categories — v0.3.0, 12 November 2026

**Branch:** `claude/sportsliveinfo-b1g-android-syyo8j`. **Status:** SOURCE IMPLEMENTED + LOCAL TESTED (43/43). Live provider calls, Docker build and HAOS install **NOT RUN** (provider hosts unreachable from the build environment). Full detail: [SOURCE_EXPANSION_SPORTS_TAXONOMY_AND_B1G_LINEUP_2026-11-12.md](SOURCE_EXPANSION_SPORTS_TAXONOMY_AND_B1G_LINEUP_2026-11-12.md).

| Workstream | New runnable work | Remaining gate |
|---|---|---|
| Sports | 16 sources, 24 sports, 127 competition rows (England internationals, PL, UCL, UEL, UECL, FA Cup, EFL Cup…), fusion/corroboration, Live today page | Per-source Test connection on HAOS; verify API-Sports league ids; recall benchmark |
| EPG | 27 private feeds across 15 markets, richer XMLTV fields, 8-market service tables, farleyflex tvg-id crosswalk, 41 lineup families | Fetch the "verify" feeds; memory test on UK1/US1; streamed programme table |
| Linking | Unverified EPG broadcast candidates with hard negatives; never sets `broadcast_verified` | Owner sign-off on the verification rule (LINK-002) |
| Ownership note | Sports adapters/engine are Codex-owned in the collaboration plan; changed at the owner's direct request with no concurrent Codex branch present | Codex cross-review before merge |

**B1G feed (sli/1):** implemented and fixture-tested (`feed.py`, `schemas/`, `docs/FEED_CONTRACT_SLI_V1.md`); atomic Git Data API publisher, retention 10, preview, optional auto-publish. **Public repository `jimmyfazz/LiveSports-EPG` exists but no feed JSON has been published** (no configured publishing token or approved sources). B1G reader design: B1 repo `docs/SPORTSLIVEINFO_FEED_READER_IMPLEMENTATION_2026-11-12.md` (not implemented). Local tests: 55/55.

**API keys needed:** three, all free and optional — API-Sports (shared by the 10 API-Sports adapter entries in the reviewed source), football-data.org, CricketData.org. Jolpica, OpenF1, OpenLigaDB, TheSportsDB (public key) and all EPG feeds need none. A GitHub token is only for optional publishing.

## New functional implementation — v0.2.0, 12 November 2026

**PR:** [#2](https://github.com/jimmyfazz/SportsLiveInfo/pull/2); initial branch commit `71d74058da751611283597e52e7eaaea369dc2b7`. **Status:** SOURCE IMPLEMENTED + LOCAL TESTED; actual Home Assistant OS installation and live source accuracy NOT VERIFIED.

| Workstream | New runnable work | Evidence | Remaining release gate |
|---|---|---|---|
| International EPG | Private source-aware UK/FR identity hints and 24/72/168-hour per-channel schedule-coverage metrics, generic title counts, EPG Coverage Ingress page, last-good preservation for stale/no-current guide | `guide.py`, `engine.py`, `server.py`; interval and hard-negative tests | Canonical international service crosswalk, real subscription inventory/FR source validation, generic-to-specific verified correction and legally redistributable public EPG |
| Sporting events | Optional no-key OpenLigaDB Bundesliga, Jolpica SprintShootout, defensive football-data/API-Sports response/partial-page errors, Sports Events page with UK times and explicit unverified channel | `providers.py`, `engine.py`, HTTP viewer and adapter tests | Rugby, cricket, boxing, tennis, other motorsport; independent event→programme→verified broadcaster |
| Source operations | One-API-request-per-provider Test Connection, optional full-EPG parser test, day-count-aware API-Sports fetching, quota reservations, no duplicate concurrent refresh, v0.1 user-key/source migration | 19 local test cases, manual HTTP/CSRF smoke | HAOS/actual provider quotas, source-specific backoff and ongoing health notifications |
| Home Assistant package | `version: 0.2.0`, `stage: experimental`, local source docs and changelog; CI trigger on main pushes | YAML layout and Python compile/local tests | Real Supervisor Apps custom-repo installation, ingress, Docker image build, storage restore |

**Actual local test commands and result:**

```bash
PYTHONPATH=sportsliveinfo/src python -m compileall -q sportsliveinfo/src
PYTHONPATH=sportsliveinfo/src python -m unittest discover -s tests -v
# Ran 19 tests in under 1 second — OK
```

The 19 tests include a real loopback HTTP server exercising Ingress pages and CSRF rejection/acceptance, source-poll quota, source errors and stale EPG, conservative UK/France names, source completeness, SprintShootout and optional Bundesliga. The GitHub Actions test check on PR #2 reports **failure without populated job steps; job logs unavailable (404 BlobNotFound)**. Its cause cannot be independently diagnosed from the available CI result. **This is not a successful CI or device test**, despite passing offline/local checks.

**Do not conflate** the separate SportsLiveInfo private source repository and a public data-feed repository; no public feed or write token has been created. Home Assistant remains local/Ingress-only; TVs read-only; user TMDB/OMDb/artwork remain B1G-local.

**Immediate follow-on:** test the app on a real HAOS installation before calling it install-accepted, then build UK/FR source-validation and verified event/broadcaster intelligence with licence gating, and finally the separate static publication/B1G reader.

## Verified status after v0.1.0 first implementation

| Area | Source code | Test state | Live HAOS/device state |
|---|---|---|---|
| Home Assistant Apps repository discovery | `repository.yaml`, `sportsliveinfo/config.yaml`, Dockerfile, README/DOCS, 128px icon, 250×100 logo | Parsed YAML and checked files exist | **Not yet added to an actual HAOS Apps store** |
| Python app runtime and persistent SQLite | `sportsliveinfo/src/sportsliveinfo/{__main__,storage}.py` | SQLite, credentials, UTC budget unit tests PASS | **No HAOS persistence/backup restore acceptance** |
| Ingress UI and first-run setup | `server.py`, CSS, per-provider key Save and source enable, scheduler and GitHub settings | Local HTTP GET/POST, first-run completion, masked keys and scheduler save PASS | **Not yet verified behind actual Supervisor Ingress** |
| Independent sporting engine | `providers.py` and `engine.py`: Jolpica F1 calendar, football-data.org & API-Sports optional keys | F1 event model, no fabricated broadcast, quota/failure tests PASS | **No live provider request benchmark or competition coverage proof** |
| International EPG engine | Opt-in UK farleyflex and three French XMLTV sources, gzip/time offsets, private last-good | XMLTV UK/France time conversion/DTD rejection and source failure tests PASS | **Not yet full-channel multi-country coverage or legal public redistribution** |
| Source/channel identity and event-broadcast matching | Models for source ID, event and no verified broadcast | Unverified channel deliberately omitted | **Not yet implemented for full B1G consumption** |
| GitHub feed publisher | Code for immutable sports asset then manifest, default disabled and rights gate | Public export with no approval rejected in unit test | **No feed target created; no public output or publication licence cleared** |
| Home Assistant persistent notifications | Local dashboard job history works | No HA Core API permissions granted | **Not yet implemented; avoid broad privilege until reviewed** |
| B1G Android read-only consumer | Detailed handover in `jimmyfazz/B1` docs | No central-feed Android tests | **Not implemented** |

## Executed tests — actual receipts

Local container environment, Python 3.13.5, 12 November 2026:

```bash
PYTHONPATH=sportsliveinfo/src python -m unittest discover -s tests -v
# Ran 7 tests ... OK
```

Tested independent key persistence, safe HTTPS source-host check, XMLTV explicit offset and DTD refusal, Jolpica F1 session shape, per-source budget accounting, source failure last-good retention and public licence-deny default.

Additional localhost HTTP smoke (port 18199, temporary SQLite): GET initial setup, POST football-data key, POST 04:00/12:00/17:00 scheduler, Finish setup, GET dashboard, verify plaintext API key **does not appear in HTML** — PASS. Installed-app YAML parsed with PyYAML and checked `slug`, Ingress, `ingress_port`, arch list, no exposed host `ports` — PASS. Actual Docker build and actual HAOS Supervisor App install were **not run** in this environment (no Docker daemon/HAOS runtime).

## Immediate next PRs

1. **HA-01** — install from custom repository on actual HAOS mini PC (amd64/aarch64), test start/stop/reboot, Ingress proxy path/auth and last-good retention; correct issues found in real deployment before declaring install accepted.
2. **EPG-01** — source right-to-use/licence register, full canonical UK+France channel catalogue, multi-source programme coverage, regional variant guards, safe generic-to-specific schedule overlay.
3. **SPORT-01** — broader rugby/tennis/cricket/boxing/motorsport sources, audited quotas, actual verified UK/FR broadcasting evidence and per-competition daily completeness.
4. **PUB-01** — legally allowed separate public static GitHub feed destination, deploy verification and robust multi-file publish; **no** Home Assistant public ingress.
5. **HA-02** — Home Assistant persistent notifications with least privilege and dedupe; better per-source Save/Test; access-controlled inventory import.
6. **B1-01** — read-only Android client only after versioned feed schema and rights gates; preserve per-device manual mappings/hidden channels/stream IDs.

## Operational constraints

Never make Home Assistant publicly accessible or forward router ports. TV clients must never write GitHub or carry publishing/provider credentials. TMDB/OMDb/film/series artwork APIs remain local to B1G. No one may claim that an installable app skeleton equals worldwide EPG/sports completeness or a verified live source. Update this page with actual new commit SHA, tests, coverage and device receipts after every PR.

## GitHub token onboarding and source-to-manifest audit (12 November 2026)

- In this follow-up development branch, the Home Assistant Publishing screen gains a direct GitHub fine-grained token creation walkthrough, explicit owner/repository selection, Content write permission explanation and a **separate read-only Test Connection** action. It never commits data, enables publishing, discloses the stored token or grants data-source rights. A GitHub API redirect with a publishing credential is rejected.
- Full source-to-manifest audit: [findings and 32-task backlog](FORENSIC_AUDIT_TOKEN_SETUP_EPG_SPORTS_MANIFEST_2026-11-12.md). Most important pending gap: public `sli/1` is a sports-event/channel-identity feed, **not a full rights-cleared EPG programme supplement**. Proposed `epg_supplements/1` is not implemented; do not imply full Guide parity.
- Added mocked GitHub onboarding/connection tests. **The exact combined suite has not been executed from this branch, CI has been failing and actual Home Assistant device install remains unverified.** The current stage is still experimental; publication is still disabled by default.

## Claude v0.3.0 integration and independent forensic hardening — 12 November 2026

Claude's previously unmerged branch was located and examined across all five repository branches, then integrated on a separate repair branch without deleting its original commits. Scope includes 16 candidate sports adapters, 27 EPG candidates, 24-sport taxonomy, sli/1 JSON feed schemas/fixtures, source lineage and provisional event-to-broadcast matching. **Candidate providers are disabled by default and not live-verified.**

Implemented in the integration repair branch: atomic multi-connection API quota ledger; durable scheduler claims; bounded streaming XMLTV parser and cross-origin credential redirect block; non-destructive generic-to-specific EPG supplement suggestions; actual failed/degraded refresh reporting; protection from partial fixtures and large EPG collapses; quota-aware API-Sports pagination; mixed-origin licence gate; proof-gated broadcast publication; input type validation and regression tests.

**TEST STATUS:** Claude recorded 55 passing offline tests on its original branch. New integrated hardening tests and the combined branch have **not** been executed in a complete local checkout here. Existing GitHub Actions returned failures without readable logs. Do not mark this branch green, deployable or HAOS-accepted until the full source test suite and actual App installation pass.

See [forensic integration and corrections](FORENSIC_INTEGRATION_AND_CORRECTIONS_2026-11-12.md) for per-module findings, code fixes and blocking tasks. B1G provider EPG remains primary; the new programme overlay is an opt-in verified *suggestion*, never an unconditional replacement.


## EPG coverage repairs — 13 November 2026

The Home Assistant 0.3.1 baseline (4045f46) imported 9 of 19 enabled guides. The EPG Share index and downloaded XMLTV samples confirmed US2 and CA2 as replacements for the endpoints returning 404. The Sky UK and Foxtel iptv-org URLs, the two French iptv-org URLs and the Matt Huisman Sky UK redirect destination also returned 404.

| Feed | Channel entries | Full 24h | Full 168h |
| --- | ---: | ---: | ---: |
| EPG Share CA2 | 696 | 695 | 0 |
| EPG Share US2 | 792 | 771 | 0 |
| EPG Share US SPORTS1 | 299 | 299 | 245 |
| IPTV-EPG.org GB | 932 | 899 | 426 |
| IPTV-EPG.org AU | 490 | 483 | 210 |
| XML TV Fr | 401 | 352 | 206 |
| EPGTalk UK | 560 | 560 | 0 |

The UK IPTV-EPG.org sample included 18 Sky Sports, 13 TNT Sports and five Premier Sports entries with full 24-hour schedules. EPGTalk Sports parsed but its long programme blocks need quality review. Source counts include variants. They do not establish unique services, stream matches or redistribution rights.

Only the fixed external XMLTV marker is removed from the known prologues. Other DTDs and entity declarations are rejected. New sources default to disabled. This preserves the existing App slug, SQLite volume and saved provider settings. Retain a scoped backup for rollback. Home Assistant deployment and post-update verification are pending.

## EPG and fixture coverage follow-up — 13 November 2026

Baseline: 6471322, the checked v0.3.2 EPG repair branch.

Downloaded guides from [IPTV-EPG.org](https://iptv-epg.org/guides) and analysed them with the app parser on 13 November at 08:45 GMT. Counts include regional and quality variants.

| Market | Entries | Full 24h | Full 7 days |
| --- | ---: | ---: | ---: |
| Germany | 438 | 410 | 25 |
| Italy | 306 | 289 | 123 |
| Spain | 300 | 297 | 20 |
| Netherlands | 184 | 183 | 0 |
| Canada backup | 808 | 802 | 173 |

Each of these samples had specific programme titles for every entry that met the 24-hour threshold. The dashboard now exposes generic-title gaps separately. That measure detects known placeholder titles and does not establish schedule accuracy. The five new guides are optional and for private collection.

[OpenLigaDB](https://www.openligadb.de/) returned 56 DFB-Pokal, 182 Frauen-Bundesliga, 144 Champions League and 380 La Liga records for season 2026. For 13–20 November UTC the downloads contained 0, 8, 0 and 1 matches respectively. The Nations League endpoint returned an empty list and was left out. OpenLigaDB provides fixtures and results with ODbL attribution/share-alike. Existing selected leagues are retained.

[Tennis API](https://docs.tennis-api.com/live-event-and-odds) documents a live singles board and upcoming ATP and WTA pages. The optional RapidAPI adapter makes three calls per refresh and uses a local cap of 40 against the documented free allowance of 50 per day. Upcoming coverage is capped at the first 50 per tour. Live state expires after 45 minutes and clears when a successful live-board refresh omits the match. The adapter was tested against synthetic payloads derived from the documented schema. A saved key is needed for an authenticated smoke test. ESPN's terms restrict automated extraction, so its undocumented scoreboard is not integrated. No odds or broadcaster claims are derived from the tennis data.

HAOS deployment is pending. Roll back by restoring the prior app version and scoped backup. No SQLite schema changes.

## Additional sport coverage — 13 November 2026

TheSportsDB daily API samples returned athletics, esports, golf, darts and snooker records. The esports sample included an event with an inconsistent year in its title, so this source remains optional and its entries are provider reports. Bowling and Boxing returned no records in the 14 November sample. Cycling and horse racing were also empty that day. Several subsequent requests returned HTTP 429. Existing F1 sources are Jolpica and OpenF1. Motorcycle coverage uses the existing Motorsport filter, with additional Moto2, Moto3 and superbike classification when supplied.

Added optional Athletics, Bowling, eSports and Boxing filters. Boxing distinguishes explicit PPV and premium labels, and a mixed Fighting record with explicit boxing wording routes to Boxing. No broadcast or access entitlement is inferred. Independent boxing card, ring-walk, regional PPV and bowling sources remain open.

## Mobile Overview

The Overview now puts refresh status and controls ahead of four linked metrics, separates provider-reported and estimated live counts, and uses readable source rows with the latest collection outcome and saved import time. The mobile navigation has three main tabs and a More menu. Desktop retains the full navigation. API usage remains in Diagnostics.

## Matt Huisman XMLTV source repair — 13 November 2026

Branch `fix/mjh-guide-source-urls` starts at main `c71b9549bb6eee2d1f1067bd6635c8aa7a94c1b7`.

**Diagnosis:** all three configured `https://i.mjh.nz/...` URLs return HTTP 302 to `raw.githubusercontent.com`; the collector correctly blocks cross-origin redirects. The configured UK path then returns 404 at its redirect target. The current publisher root listing has no `SkyUK/` folder. Its `SkyGo/` guide is explicitly the New Zealand Sky Go service, so it is not a UK replacement ([Matt Huisman Sky Go NZ description](https://www.matthuisman.nz/2021/05/sky-go-nz-kodi-add-on.html)). The UK-specific source is retired from the selectable EPG catalogue and size overrides; `COUNTRY_BY_SOURCE["mjh_sky_uk"]` and source identity rules remain for existing snapshots and historical mappings.

**Current source paths:**

| Source | Direct URL status | Current compressed size | Parsed channels | Parsed programmes | Furthest programme end from check time |
| --- | --- | ---: | ---: | ---: | ---: |
| NZ | 200 | 1,237,696 bytes | 44 | 9,756 | 691.2 h |
| AU Sydney | 200 | 729,267 bytes | 174 | 13,788 | 386.2 h |
| UK Sky | retired | former path's final target is 404 | — | — | — |

The New Zealand and Sydney raw GitHub files decompress to 12,434,405 and 7,221,703 bytes. Both fit the existing defaults (14,000,000 compressed bytes, 100,000 programme rows, 65,000,000 expanded bytes). The unrelated `SkyGo/` candidate is a NZ source; it is 6,857,631 compressed / 69,519,612 expanded bytes and exceeds the default expanded limit, so it is not added or used as UK coverage.

The collector now points NZ and Sydney directly at their final raw GitHub URLs. This avoids redirects without weakening `RedirectGuard`. Known cross-origin redirect and unapproved HTTPS source failures now have explicit messages. The per-source limits are now 5 MB compressed / 50,000 programmes / 25 MB expanded for NZ and 5 MB / 50,000 / 15 MB for Sydney. The golden `sli/1` fixtures were regenerated after removing the retired guide from the catalogue.

Validation commands/results:

```text
curl -sSIL --max-time 30 https://i.mjh.nz/SkyUK/epg.xml.gz
HTTP/2 302
location: https://raw.githubusercontent.com/matthuisman/i.mjh.nz/master/SkyUK/epg.xml.gz
HTTP/2 404

curl -sSIL --max-time 30 https://raw.githubusercontent.com/matthuisman/i.mjh.nz/master/nz/epg.xml.gz
HTTP/2 200
content-length: 1237696

curl -sSIL --max-time 30 https://raw.githubusercontent.com/matthuisman/i.mjh.nz/master/au/Sydney/epg.xml.gz
HTTP/2 200
content-length: 729267
```

App-parser checks used `providers.decode_xmltv(..., max_programmes=400000)` and confirmed the counts/horizons in the table. Three new synthetic tests cover direct source URLs, retirement/market retention, redirect rejection and diagnostic text. Golden fixtures were regenerated with `PYTHONPATH=sportsliveinfo/src python3 tools/generate_feed_fixtures.py` (14 assets). `PYTHONPATH=sportsliveinfo/src python3 -m compileall -q sportsliveinfo/src tests` and `git diff --check` passed. `PYTHONPATH=sportsliveinfo/src python3 -m unittest discover -s tests -v` completed with **202 tests, OK**.

**Home Assistant acceptance:** NOT RUN at this documentation point. Before merging, create the required Home Assistant backup. After merge, verify version 0.3.9 is offered/installed, run “Collect now,” then check the app Diagnostics/logs for nonzero NZ and Sydney imports and the retired UK source no longer being selected. Do not claim live HA verification until those steps complete.
