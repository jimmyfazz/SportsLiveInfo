# SportsLiveInfo

> **Current documentation context — reviewed 12 November 2026.** Experimental v0.3.0 source is present. Current source/test evidence and open deployment gates are centralized in CURRENT_STATUS; historical version receipts elsewhere are not current pass claims.
> **Repository roles:** [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is PRIVATE source/installation and stays private; [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is PUBLIC daily data only. [Current status and evidence](docs/CURRENT_STATUS.md).

SportsLiveInfo is an experimental **v0.3.0 Home Assistant OS App** for two equally required products: international full-channel EPG and multi-sport event intelligence. It collects centrally on the owner's always-on home mini PC; the planned ten B1G TV clients read shared static data and resolve playable channels locally.

**Current source and test status, reviewed 12 November 2026:** 16 sports adapter entries, 27 candidate EPG feeds, private coverage diagnostics, Live today/events UI, SQLite, scheduling and a rights-gated static feed writer exist. Python 3.12.15 validation: **88 tests passed**. HTTP-handler tests use an in-memory transport in this socket-restricted runner; see current status for limits. Docker/actual HAOS operation, live provider accuracy, source rights and B1G device integration remain unverified. See [current status and evidence](docs/CURRENT_STATUS.md).

| Repository | Visibility | Purpose |
|---|---|---|
| [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) | **Private; stays private** | Source and Home Assistant App installation package |
| [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) | **Public** | Daily static feed destination; not an App installation repository |

The public repository contained only its README when checked on 12 November 2026. The writer exists, but a live feed is not deployed. Token setup, successful GET tests and repository creation do not grant redistribution rights or authorize publication.

## Install and operate

Follow the [private App installation and operator guide](sportsliveinfo/DOCS.md). Obtain the private source using your existing GitHub access and copy the `sportsliveinfo/` App directory into HAOS `local_apps/sportsliveinfo/`. Do not change source-repository visibility or use the public feed repo as an installation source. Actual installation acceptance remains open.

The Ingress UI provides provider/source setup, separate Save/Test controls, schedule, Live today, events, EPG coverage, Publishing and Diagnostics. Optional sports-key settings are API-Sports, football-data.org and CricketData.org. GitHub credentials are only for optional rights-approved publishing. Secrets stay in private App storage and sensitive backups.

## Product and privacy boundaries

- **International EPG:** UK and France first, with subscription-driven additional markets; complete rolling schedules, source identity, time zones, coverage and safe enrichment. Current source counts are candidate catalogues, not measured coverage.
- **Sports:** independent fixtures/races/sessions and broader sport categories, source conflicts, timing precision and separately verified broadcaster evidence. A programme airing does not prove an event is live.
- **Current public format:** `sli/1.0` exports taxonomy, channel identities/guide catalogue, events, Today grouping and health. **It contains no EPG programme rows.** Local `supplement.py` suggestions are not a published EPG supplement or integrated B1G Guide.
- **TV behavior required:** anonymous read-only feed access, current-account playable stream resolution, manual mapping and hidden-channel/category precedence, provider EPG fallback. No provider/GitHub write keys or account uploads on TV.
- **Home Assistant:** no new incoming WAN port, public SportsLiveInfo endpoint or TV-to-HA connection. Existing authenticated owner administration is separate.
- **Excluded:** central TMDB/OMDb, VOD metadata/posters/hero artwork, IPTV credentials/streams and per-TV preferences.

## Documentation and development

Start with [current status](docs/CURRENT_STATUS.md), the [document index](docs/DOCUMENTATION_INDEX.md), [AGENTS.md](AGENTS.md), [master roadmap](docs/MASTER_IMPLEMENTATION_ROADMAP.md), [current backlog](docs/WORK_PACKAGE_BACKLOG.md) and [handover](docs/IMPLEMENTATION_PROGRESS.md). The [implemented feed contract](docs/FEED_CONTRACT_SLI_V1.md) governs current paths/fields; [publication policy](docs/FEED_CONTRACTS_AND_PUBLICATION.md) governs required rights and safety. Dated audits preserve historical findings and explicitly identify their baseline.

```sh
python3.12 -m compileall -q sportsliveinfo/src
PYTHONPATH=sportsliveinfo/src python3.12 -m unittest discover -s tests -v
```

The current layout uses Python's standard library; no `pyproject.toml`, pip-installable development package or general-purpose collection CLI is supplied. Continue the existing source rather than recreating a scaffold. Use separate branches/worktrees and PRs; record actual tests, rights, blockers and rollback. Both products need measured acceptance before production or ten-TV rollout.
