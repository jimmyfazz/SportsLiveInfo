# Operating protocol for Codex and Claude Code — independent terminals, coordinated deliverables

> **Current documentation context — reviewed 12 November 2026.** Worktree/file ownership and reciprocal review rules remain in force. The initial scaffold/contract phases and illustrative paths below are historical planning; extend the existing v0.3.0 modules and contracts.
> **Repository roles:** [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is the public App source and installation repository; [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is PUBLIC daily data only. [Current status and evidence](CURRENT_STATUS.md).

**Mandatory instructions for both agents — 12 November 2026**  
**Baseline:** `SportsLiveInfo` private GitHub repository. In this plan, BOTH the comprehensive international EPG engine and the comprehensive multi-sport/event/broadcast engine are first-class, parallel deliverables. Existing private B1G is a separate repo; its read-only Android feed consumer remains a required integration, not a verified implementation in this review.

## 0. Read order and authoritative instructions

1. `AGENTS.md` and `README.md`.
2. `docs/MASTER_IMPLEMENTATION_ROADMAP.md` (**normative main plan**, phases 0–7, priorities).
3. `docs/AUDIT_2026-11-12_FORENSIC_SPEC_AND_ARCHITECTURE.md` (forensic P0/P1/P2 problem IDs).
4. `docs/INTERNATIONAL_EPG_AND_SPORTS_SOURCE_EXPANSION.md` (source registry and regional/competition matrix).
5. `docs/FEED_CONTRACTS_AND_PUBLICATION.md` (versioned interfaces and licensing).
6. `docs/QUALITY_SECURITY_AND_ACCEPTANCE.md` (tests, acceptance and failure gates).
7. `docs/HOME_ASSISTANT_BARE_METAL_PRIMARY.md` and `docs/HOME_ASSISTANT_FIRST_RUN_WIZARD_AND_NOTIFICATIONS.md`.
8. `docs/CHANNEL_IDENTITY_AND_EPG_ALLOCATION_SPEC.md`, `docs/SUBSCRIPTION_DRIVEN_MULTIREGION_EPG.md`, `docs/B1G_READ_ONLY_FEED_AND_INVENTORY_POLICY.md`.
9. `docs/CODEX_B1G_SUBSCRIPTION_INVENTORY_HANDOVER.md` for B1 account inventory audit and the optional local safe import.

Prior dated specs are background and cannot override the confirmed owner instructions: **HAOS on personal home mini-PC, no inbound WAN/Home Assistant exposure, outbound-only authorised GitHub publishing, B1 TV clients read-only, 10–11 sports cards and full programme EPG, UK/FR + subscription discovered countries, no TMDB/OMDb/poster/hero in SportsLiveInfo**.

## 1. Git branch and terminal coordination — do not edit the same worktree

Use a **different local clone or `git worktree`** for each terminal, a unique branch per task, and small PRs. Do not give Codex and Claude the same writable checkout. Use GitHub Free features; don't assume paid PR merge queues/actions minutes.

Illustrative terminal commands:

    git clone git@github.com:jimmyfazz/SportsLiveInfo.git sportsliveinfo
    cd sportsliveinfo
    git fetch origin
    git worktree add ../sli-codex -b codex/p0-foundation origin/main
    git worktree add ../sli-claude -b claude/p0-ui-contract origin/main

For independent work from each terminal, `cd ../sli-codex` and `cd ../sli-claude`; never run both agents concurrently in the same worktree. New task, new branch from current main. Rebase PR when contract owner merges; no forced pushes over the other's work. If network/auth isn't available, work locally and report inability to push—never claim a merged PR that hasn't actually merged.

**No multiple agents editing `AGENTS.md`, master roadmap, `schemas/` or shared Python model files simultaneously.** The coordinator assigns one owner and review/merge gate for each.

## 2. Agreed ownership: exploit parallelism without conflicts

| Workstream | Initial code owner | Reviewer / collaborator | Owned folders (proposed) | Required handoff |
|---|---|---|---|---|
| FND-01 Python package, CLI, config, CI | **Codex** | Claude | `pyproject.toml`, `src/sportsliveinfo/cli.py`, `.github/workflows` | Clean import/install and synthetic smoke result |
| CON-01 canonical model/schema | **Codex** | **Claude must approve before parallel dependencies** | `schemas/`, `domain/` models | Golden JSON fixtures + version contract, then freeze |
| EPG-01 XMLTV parser/source EPG adapters/coverage | **Claude** | Codex | `providers/epg/`, `epg/`, EPG-specific tests | EPG UK/FR 7-day sample, quota/rights tags and coverage stats |
| SPORT-01 sports adapters/normalise/competition matrix | **Codex** | Claude | `providers/sports/`, `sports/`, sport-specific tests | Named team/session fixtures, precision, per-competition completeness |
| LINK-01 event→programme→broadcaster | **Codex**, after EPG+sport integration | Claude | `matching/` and test fixtures | Verified positive/negative evidence, conflicts |
| OPS-01 quota ledger, SQLite, scheduler, licence/publication | **Codex** | Claude | `storage/`, `scheduling/`, `publishing/` | Quota/last-good/recovery tests, no public upload without rights |
| HAUI-01 HAOS App, Ingress wizard/dashboard/errors | **Claude** | Codex | `haos/`, `frontend/`, UI acceptance tests | First-run provider Save/Test/GitHub/schedule/notifications with local mock backend |
| B1-01 Android feed consumer/EPG mapper/10–11 rail | **Claude** in **B1 separate repo** | Codex | `jimmyfazz/B1`: Android UI/data and tests | Device acceptance with Android Kotlin source priorities; no stream/exposure risk |
| QA-01 contract/security/performance | Both independently in their own folders | Reciprocal | `tests/contract`, `tests/security` and reports | 10-TV, source/country precision, last-good, HA resource report |

**Both EPG and SPORT shall advance in parallel from Phase 1, not one after the other.** Claude's HA UI work can begin against frozen golden schemas while EPG source tests are underway; Codex can build generic transport before live API keys arrive. Avoid idle agents by allocating unit tests/docs/source-audit tasks while waiting for live credentials/licensing.

## 3. Dependency gates and merge order

A. Merge **P0 package and contract schema** first. Claude should concurrently prepare mock UI and source research but cannot merge APIs that assume an unapproved shape. Use versioned fixture files to decouple.

B. Once JSON schemas frozen, merge independently reviewed **EPG parser** and **sports model/adapters** in either order. EPG tests may use offline synthetic XMLTV; sport tests may use offline fixture JSON. Both must meet their own initial milestones.

C. Merge source crosswalk/alias registry and sports-EPG evidence link only after both engines pass contract tests.

D. Add HAOS App shell/UI with bounded mock source; integrate real backend and wizard, then publishing. Don't make a public repository/feed until licensed.

E. Introduce B1 Android consumer first as **opt-in** with current EPG fallback, then test one Fire TV/Shield and all ten TVs. Preserve account-source overrides and hidden categories.

F. Only mark P6 complete after **both EPG Guide and sport rail** acceptance reports pass.

## 4. Required PR template

**Title:** `[P{n}][EPG|SPORT|CORE|HAOS|B1|QA] concise change`

**Description:** requirement ID(s) (AUD-###), branch and baseline SHAs; files touched; API/schema version; source/terms change (even if "none"); tests with exact commands/results; fixtures and benchmark dates; performance/security impact; HA resource impact; fallback/rollback; unresolved blockers. No claims of live completeness without evidence. If backend changes a schema, must update canonical JSON fixtures and B1 consumer tests in same coordinated milestone.

**Review:** other agent reviews domain/contract/security changes; all tests pass before merge; never silently merge incompatible JSON. If two PRs touch same file, merge owner PR then rebase other and rerun tests. Keep a dated handover report `docs/IMPLEMENTATION_PROGRESS.md` updated after merges with actual commit IDs and verified state.

## 5. Current commands and future CLI targets

Current source checks are `python3.12 -m compileall -q sportsliveinfo/src` and `PYTHONPATH=sportsliveinfo/src python3.12 -m unittest discover -s tests -v`. See [CURRENT_STATUS.md](CURRENT_STATUS.md) for the latest passing offline suite and remaining live acceptance gates. Source is in `sportsliveinfo/src/sportsliveinfo/`; the ownership paths in §2 are target modular paths, not existing folders.

The following pip/pytest/general CLI commands remain future targets, not working setup instructions:

    python -m pip install -e '.[dev]'
    python -m pytest -q
    python -m sportsliveinfo --help
    python -m sportsliveinfo collect --date 2026-11-12 --offline-fixtures tests/fixtures --output ./tmp/sports.json
    python -m sportsliveinfo epg import --xmltv tests/fixtures/uk-fr.xml --output ./tmp/epg.json
    python -m sportsliveinfo coverage report --date 2026-11-12 --offline
    python -m sportsliveinfo publish --dry-run

Do not claim these commands currently work until actual CLI implemented. Prefer `uv` only if both agents agree and there is no platform incompatibility. Build in documented Python 3.12+ environment; validate HA mini PC CPU architecture (amd64 or aarch64).

B1 Android current project test command from its existing handover (verify current task names before use):

    cd platforms/android
    ./gradlew --no-daemon :app:testDebugUnitTest :app:assembleDebug

No app-store publication or external distribution is assumed; owner uses ten personal devices.

## 6. Source and credential rules

- A supplier signup page and key acquisition is an owner action; do not create provider accounts without approval. Some no-key sources should show "No key required" rather than meaningless input.
- TMDB/OMDb/VOD artwork APIs explicitly stay on B1; abandon central metadata proxy/relaying work. These keys have nothing to do with SportsLiveInfo.
- Never move IPTV credentials, B1 playlist server, streams or real channel inventory into GitHub. Optional owner's manual sanitised export can be imported privately into HAOS.
- Do not scrape pages that prohibit it or use developer trials with scrambled sample data as factual evidence.
- GitHub publishing is outbound-only and disabled pending actual rights. A private code repo plus separate public feed is the **confirmed** topology, not a grant of permissions to republish.
- GitHub Pages is for static files; no API server magic. Reader caches and public manifest revisions must handle delays.

## 7. Machine-readable progress and transparent blockers

Each major work package must record:

    Work package: SPORT-01
    Branch / latest commit:
    Status: researched | code-in-progress | unit-tested | live-tested | rights-cleared | deployed
    Exact tests and results:
    Actual competition or channel coverage benchmark:
    Schema revision and consumer impact:
    Provider quota/rights:
    Last verified date:
    Next open task:
    Owner / Reviewer:

Never turn a research note into 'implemented' merely because code was written but not executed. If required API key or real subscription inventory isn't available, implement offline tests and mark live validation blocked, not skipped or passed.

## 8. Direct prompts for the two terminals

### Prompt for Codex (copyable)

> Work in your own branch/worktree in `jimmyfazz/SportsLiveInfo`. Read `AGENTS.md`, then `docs/MASTER_IMPLEMENTATION_ROADMAP.md`, `docs/AUDIT_2026-11-12_FORENSIC_SPEC_AND_ARCHITECTURE.md`, `docs/INTERNATIONAL_EPG_AND_SPORTS_SOURCE_EXPANSION.md`, `docs/FEED_CONTRACTS_AND_PUBLICATION.md`, `docs/QUALITY_SECURITY_AND_ACCEPTANCE.md` and `docs/CODEX_CLAUDE_COLLABORATION.md`. You own foundation/JSON contracts/sports engine/transport/persistence/quota/licence-gated publisher. Build Python package and frozen golden JSON schema first; tell Claude the contract revision. Develop sports source adapters/competition verification alongside Claude's EPG engine and UI, with deterministic tests. Do not touch Claude-owned EPG/frontend or B1 files unless coordinated. NO public publishing, paid API, inbound HA access or TMDB/OMDb. Create PR(s), report actual test results and merge only after review.

### Prompt for Claude Code (copyable)

> Work in your own branch/worktree in `jimmyfazz/SportsLiveInfo` and separately `jimmyfazz/B1` only when Android phase starts. Read `AGENTS.md`, `docs/MASTER_IMPLEMENTATION_ROADMAP.md`, `docs/INTERNATIONAL_EPG_AND_SPORTS_SOURCE_EXPANSION.md`, `docs/CHANNEL_IDENTITY_AND_EPG_ALLOCATION_SPEC.md`, `docs/HOME_ASSISTANT_FIRST_RUN_WIZARD_AND_NOTIFICATIONS.md`, `docs/QUALITY_SECURITY_AND_ACCEPTANCE.md` and `docs/CODEX_CLAUDE_COLLABORATION.md`. You own EPG XMLTV source adapters, international source/channel registry and Guide quality/coverage, then Home Assistant Ingress wizard/health UI and B1 Android read-only feed client. Use Codex's reviewed canonical schemas/golden fixtures; do not edit Codex-owned model/pub files concurrently. Preserve B1 per-account manual mappings, hidden categories and existing playback. All source ingestion is licence-gated, client read-only, no inbound WAN, no artwork/TMDB/OMDb proxy. Build multiple independent tests and PRs; report what works versus what requires keys/licence/runtime verification.

## 9. Last-mile acceptance

Provide an owner-readable audit result showing **separate** EPG and SPORT coverage (UK/France/other), source rights, actual EPG programme correctness, event times and competition completeness, B1 mapping performance, individual missing channels, 10-TV quota neutrality, HAOS status and next actions. Never say "application complete" if one tier is only a placeholder.
