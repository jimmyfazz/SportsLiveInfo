# CLAUDE.md — SportsLiveInfo project startup for Claude Code

> **Current documentation context — reviewed 12 November 2026.** Experimental v0.3.0 source is present. Current source/test evidence and open deployment gates are centralized in CURRENT_STATUS; historical version receipts elsewhere are not current pass claims.
> **Repository roles:** [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is PRIVATE source/installation and stays private; [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is PUBLIC daily data only. [Current status and evidence](docs/CURRENT_STATUS.md).

**Read this first.** This file is intentionally concise; the detailed and binding rules are in [AGENTS.md](AGENTS.md). Do not rely on older UK-only, "B1 optional", or sports-only architecture notes.

## Current additional audit and required follow-up

See [12 Nov GitHub onboarding and deep EPG/sports/manifest audit](docs/FORENSIC_AUDIT_TOKEN_SETUP_EPG_SPORTS_MANIFEST_2026-11-12.md). Critical: the current `sli/1` public output does **not** carry enhanced EPG programme listings; B1G's provider Guide must remain primary and any future licensed supplement must be non-destructive and user-account-aware. The separate public data repo is `jimmyfazz/LiveSports-EPG`. Do not confuse token connection test with write or licensing approval. Source verification, cross-language fixtures and Android reader remain outstanding.

## Scope

Build **two full equal-priority engines**, not a quick proof-of-concept sports rail alone:

1. **International EPG**: UK and French general/premium/sport channels; further countries based on optional owner-imported safe B1G subscription inventory; canonical broadcaster identities, legal source registry, rolling schedules, exact language/region/time-zone handling, complete 24/72/168h coverage reports, verifiable quality improvements and safe B1 Guide overlay.
2. **Worldwide Sports Events**: football, F1/motorsport, tennis, rugby union/league, cricket, boxing/PPV, other international sports; exact participants/venues/start precision and *verified* broadcast link to local B1G channel, separate from EPG and sporting status.

Home Assistant OS App on owner's always-on **direct-installed home mini PC** does all shared collection and publishing. No public Home Assistant or inbound WAN ports. **Only outbound** permitted source fetch and GitHub feed uploads. All 10 B1G TVs **read-only** from rights-cleared published static data; local account/channel/stream/hidden state never uploaded to GitHub. The film/series **TMDB/OMDb/artwork API belongs to B1G**, never this collector.

## Essential reading order

1. [AGENTS.md](AGENTS.md)
2. [Master implementation roadmap](docs/MASTER_IMPLEMENTATION_ROADMAP.md)
3. [34-finding forensic audit](docs/AUDIT_2026-11-12_FORENSIC_SPEC_AND_ARCHITECTURE.md)
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

**Current baseline (reviewed 12 Nov 2026):** Experimental **v0.3.0** includes expanded source candidates, taxonomy, provisional linking, `sli/1.0` contracts and local supplement suggestions. [Current status](docs/CURRENT_STATUS.md) records the pinned source and **86 tests attempted: 81 passed, two feed/test input errors, three localhost tests blocked by this runner**. Actual HAOS/Docker install, provider accuracy/rights, notifications, public programme supplements and B1G acceptance remain open. Continue the existing modules; do not recreate a scaffold. Source/installation stays PRIVATE; `LiveSports-EPG` is PUBLIC daily data only. Use [private local installation](sportsliveinfo/DOCS.md). Current test command: `PYTHONPATH=sportsliveinfo/src python3.12 -m unittest discover -s tests -v`.
