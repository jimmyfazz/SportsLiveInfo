# CLAUDE.md — SportsLiveInfo project startup for Claude Code

**Read this first.** This file is intentionally concise; the detailed and binding rules are in [AGENTS.md](AGENTS.md). Do not rely on older UK-only, "B1 optional", or sports-only architecture notes.

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

**As of 12 Nov 2026:** Experimental **v0.2.0 HAOS App** source exists under `sportsliveinfo/` (Ingress, persistent SQLite, first-run provider setup, source connection tests, EPG coverage diagnosis, sport event viewer, initial XMLTV/football/F1/OpenLigaDB adapters). **19 local tests pass** including localhost HTTP/CSRF. Actual HAOS Docker/Ingress deployment and live provider accuracy remain untested; full international guide/competitions, canonical stream/broadcast evidence, notifications and B1G consumer remain outstanding. Extend existing code, particularly `sportsliveinfo/src/sportsliveinfo/guide.py` and `engine.py`; never recreate the skeleton. Test: `PYTHONPATH=sportsliveinfo/src python -m unittest discover -s tests -v`.
