# CLAUDE.md — SportsLiveInfo project startup for Claude Code

> **Repository roles:** [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is the public App source and installation repository; [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is PUBLIC daily data only. [Current status and evidence](docs/CURRENT_STATUS.md).

**Every agent: read [docs/AGENT_OPERATING_MANUAL.md](docs/AGENT_OPERATING_MANUAL.md) first** (how to work, the gate, release and deploy, the design rule). This file is intentionally concise; the detailed and binding rules are in [AGENTS.md](AGENTS.md). Do not rely on older UK-only, "B1 optional", or sports-only architecture notes.

## Current state and binding rules (25 Nov 2026, v0.3.33; 15 Nov text below is history)

**Start with the [15 November handover](docs/HANDOVER_2026-11-15_SPORTSLIVEINFO_B1G.md)** (state, Mac setup, release and Home Assistant deploy steps, prioritised open work), then [current status](docs/CURRENT_STATUS.md), the [15 November audit](docs/AUDIT_2026-11-15_FORENSIC_SPORTSLIVEINFO.md) and the [B1G reconciliation spec](docs/B1G_CHANNEL_AND_GUIDE_RECONCILIATION_SPEC.md); older audits are in [docs/archive](docs/archive/). The installed version is in [current status](docs/CURRENT_STATUS.md) (0.3.31 and 0.3.33 fix the publish-gate stalls and add publish retries); since 0.3.24 readers follow the feed's decisions ([contract §4.3](docs/FEED_CONTRACT_SLI_V1.md)). **Design rule:** decisions belong in SportsLiveInfo and are published as data; B1G follows them, so improvements need no TV update. The public feed (`sli/1.7`) does **not** carry EPG programme listings: B1G's provider Guide stays primary and any future licensed supplement must be non-destructive and user-account-aware. The separate public data repo is `jimmyfazz/LiveSports-EPG`. Do not confuse a token connection test with write or licensing approval. The B1G Android reader is implemented (B1 PRs #827 and #828, conformance and `sli/1.6` interop tests pass); `sli/1.6` and the live-status lane have been publishing since 09:00 UTC on 15 Nov; device acceptance remains outstanding.

## Scope

Build **two full equal-priority engines**, not a quick proof-of-concept sports rail alone:

1. **International EPG**: UK and French general/premium/sport channels; further countries based on optional owner-imported safe B1G subscription inventory; canonical broadcaster identities, legal source registry, rolling schedules, exact language/region/time-zone handling, complete 24/72/168h coverage reports, verifiable quality improvements and safe B1 Guide overlay.
2. **Worldwide Sports Events**: football, F1/motorsport, tennis, rugby union/league, cricket, boxing/PPV, other international sports; exact participants/venues/start precision and *verified* broadcast link to local B1G channel, separate from EPG and sporting status.

Home Assistant OS App on owner's always-on **direct-installed home mini PC** does all shared collection and publishing. No public Home Assistant or inbound WAN ports. **Only outbound** permitted source fetch and GitHub feed uploads. All 10 B1G TVs **read-only** from rights-cleared published static data; local account/channel/stream/hidden state never uploaded to GitHub. The film/series **TMDB/OMDb/artwork API belongs to B1G**, never this collector.

## Essential reading order

1. [AGENTS.md](AGENTS.md)
2. [Master implementation roadmap](docs/MASTER_IMPLEMENTATION_ROADMAP.md)
3. [15 November forensic audit](docs/AUDIT_2026-11-15_FORENSIC_SPORTSLIVEINFO.md) (the 12 November 34-finding audit is archived in [docs/archive](docs/archive/))
4. [Task backlog](docs/WORK_PACKAGE_BACKLOG.md)
5. [Agent collaboration/branch ownership](docs/CODEX_CLAUDE_COLLABORATION.md)
6. [International EPG and sports source strategy](docs/INTERNATIONAL_EPG_AND_SPORTS_SOURCE_EXPANSION.md)
7. [Shared feed JSON/rights contract](docs/FEED_CONTRACTS_AND_PUBLICATION.md)
8. [Quality/security acceptance](docs/QUALITY_SECURITY_AND_ACCEPTANCE.md)
9. [HA first-run wizard/quiet notifications](docs/HOME_ASSISTANT_FIRST_RUN_WIZARD_AND_NOTIFICATIONS.md)
10. [B1 canonical channel identity](docs/CHANNEL_IDENTITY_AND_EPG_ALLOCATION_SPEC.md)

## Your workstream

- **Owner:** EPG-001–007 streaming XMLTV, multi-country guide adapter/source/coverage, source namespace + broadcaster crosswalk, hard-negative mapping tests; later HA-001–005 first-run Ingress wizard and errors; B1-001–005 Android read-only consumer in the separate B1 repo.
- **Codex owns:** CORE initial Python scaffolding/contracts, SPORT adapters/sports modelling, persistence/quotas/publisher. **Do not edit Codex-owned common schema/model files concurrently.** Start EPG synthetic fixtures/parser in separate worktree while Codex freezes contracts. Review contracts before integration.
- Separate worktree and dedicated branch; small PR, cross-review, actual tests. Never claim a PR merged without verification. Update [implementation progress](docs/IMPLEMENTATION_PROGRESS.md) with real results, blockers and source rights.
- B1-specific rules: current account local `ChannelVisibilityStore` hidden categories/channels, `EpgChannelMappingStore` source-specific user mappings, `EpgResolver` precedences and original provider EPG fallback are mandatory. Do not auto-match ambiguous Sky+/BBC regional/France Canal/beIN/RMC streams. No API/GitHub write keys on TV.

## Stop/go gates

No public EPG programme republication unless the source data's public rights are documented. Free/readable XMLTV is not sufficient. No paid provider, no LLM calls in runtime, no credential in logs/URLs/repo. If provider keys, source licence or actual owner's subscription list are unavailable, implement safe synthetic tests and explicitly mark live verification blocked.

See [current status and validation](docs/CURRENT_STATUS.md) and the [Home Assistant operator guide](sportsliveinfo/DOCS.md).
