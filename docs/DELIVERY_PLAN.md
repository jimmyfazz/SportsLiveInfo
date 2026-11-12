# Current delivery sequence

> **Current documentation context — reviewed 12 November 2026.** Experimental v0.3.0 source is present. Current source/test evidence and open deployment gates are centralized in CURRENT_STATUS; historical version receipts elsewhere are not current pass claims.
> **Repository roles:** [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is PRIVATE source/installation and stays private; [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is PUBLIC daily data only. [Current status and evidence](CURRENT_STATUS.md).

**Reviewed 12 November 2026.** The experimental v0.3.0 App is implemented in source; implementation has started and must not be restarted from an empty scaffold. See [current status](CURRENT_STATUS.md), [master roadmap](MASTER_IMPLEMENTATION_ROADMAP.md) and [package backlog](WORK_PACKAGE_BACKLOG.md) for evidence, detailed requirements and ownership.

| Next stage | Existing foundation | Required exit evidence |
|---|---|---|
| Stabilize validation | Parser/storage/UI/feed regressions, six schemas and deterministic HTTP-handler tests | 88 local tests pass; confirm current GitHub Actions evidence and exercise real loopback where available |
| Private HAOS acceptance | App config/Dockerfile, Ingress and persistent SQLite | Install private App through local delivery; architecture builds, authenticated Ingress, restart, restore and measured HA resource impact |
| Advance EPG and sports together | 27 EPG candidates, 16 sports adapters, identity/coverage/taxonomy/fusion | Per-source live endpoint/quota/rights checks; independent EPG horizon and sport recall scorecards |
| Verify event/broadcaster and programme quality | Provisional links and local non-destructive suggestion evaluator | Reviewed independent evidence rule; preserve EPG-only/fixture-only uncertainty; no wrong-channel overlays |
| Finish programme contract and publishing | `sli/1.0` metadata/events builder, local preview and atomic writer | Rights-cleared programme-supplement schema/fixtures, authorized publication and anonymous asset verification; no full Guide claim from metadata |
| B1G then ten TVs | Shared contracts and matching fixtures | Read-only reader, local manual/hidden/account mapping, provider EPG fallback, one TV then ten-device acceptance |
| Production gate | Roadmap and QA targets | Both EPG and sports measured separately; rights, security, resilience, notifications and rollback accepted |

The **PRIVATE** [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) repository supplies App installation source and stays private. The **PUBLIC** [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) repository is daily static data only; it was README-only when checked. Neither data publication nor source-repository visibility changes are part of this documentation refresh.

The primary host is the directly installed always-on home mini PC; Proxmox is only a fallback. The collector requires no new public HA/App endpoint. Ten TVs never write GitHub, upload account inventory or hold central provider keys. TMDB/OMDb and movie/series artwork remain in B1G. Follow [collaboration](CODEX_CLAUDE_COLLABORATION.md) for separate branches, reciprocal review, small PRs and recorded rollback; a documentation rollback only reverts the documentation commit.
