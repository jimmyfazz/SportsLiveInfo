# SportsLiveInfo — implementation progress and agent handover
**Updated:** 12 November 2026  
**Repository:** `jimmyfazz/SportsLiveInfo` (remains PRIVATE).  
**Latest development branch:** `feat/haos-epg-coverage-openligadb-v0.2-20261112`; PR #2. Historical PR #1 delivered v0.1.0.

## Source expansion and sports sub-categories — v0.3.0, 12 November 2026

**Branch:** `claude/sportsliveinfo-b1g-android-syyo8j`. **Status:** SOURCE IMPLEMENTED + LOCAL TESTED (43/43). Live provider calls, Docker build and HAOS install **NOT RUN** (provider hosts unreachable from the build environment). Full detail: [SOURCE_EXPANSION_SPORTS_TAXONOMY_AND_B1G_LINEUP_2026-11-12.md](SOURCE_EXPANSION_SPORTS_TAXONOMY_AND_B1G_LINEUP_2026-11-12.md).

| Workstream | New runnable work | Remaining gate |
|---|---|---|
| Sports | 16 sources, 24 sports, 127 competition rows (England internationals, PL, UCL, UEL, UECL, FA Cup, EFL Cup…), fusion/corroboration, Live today page | Per-source Test connection on HAOS; verify API-Sports league ids; recall benchmark |
| EPG | 27 private feeds across 15 markets, richer XMLTV fields, 8-market service tables, farleyflex tvg-id crosswalk, 41 lineup families | Fetch the "verify" feeds; memory test on UK1/US1; streamed programme table |
| Linking | Unverified EPG broadcast candidates with hard negatives; never sets `broadcast_verified` | Owner sign-off on the verification rule (LINK-002) |
| Ownership note | Sports adapters/engine are Codex-owned in the collaboration plan; changed at the owner's direct request with no concurrent Codex branch present | Codex cross-review before merge |

**B1G feed (sli/1):** implemented and fixture-tested (`feed.py`, `schemas/`, `docs/FEED_CONTRACT_SLI_V1.md`); atomic Git Data API publisher, retention 10, preview, optional auto-publish. NOT published (no feed repository/token; no approved sources). B1G reader design: B1 repo `docs/SPORTSLIVEINFO_FEED_READER_IMPLEMENTATION_2026-11-12.md` (not implemented). Local tests: 55/55.

**API keys needed:** three, all free and optional — API-Sports (covers all 11 API-Sports adapters), football-data.org, CricketData.org. Jolpica, OpenF1, OpenLigaDB, TheSportsDB (public key) and all EPG feeds need none. A GitHub token is only for optional publishing.

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
