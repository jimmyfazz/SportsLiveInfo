# SportsLiveInfo Home Assistant App

> **Current documentation context — reviewed 12 November 2026.** Experimental v0.3.0 source is present. Current source/test evidence and open deployment gates are centralized in CURRENT_STATUS; historical version receipts elsewhere are not current pass claims.
> **Repository roles:** [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is PRIVATE source/installation and stays private; [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is PUBLIC daily data only. [Current status and evidence](../docs/CURRENT_STATUS.md).

**v0.3.0 · experimental · reviewed 12 November 2026.** Private Ingress administration, persistent SQLite, bounded EPG/sport collection, coverage diagnostics, Live today, event filters, schedule and optional rights-gated `sli/1.0` publication are implemented in source.

[SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is the **private source/installation repository and stays private**. [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is the **public daily-feed repository**, not an App installer. Install the App directory through local private delivery as described in [installation and use](DOCS.md).

The current Python 3.12.15 suite passes all 88 tests. HTTP-handler tests use an in-memory transport in this socket-restricted runner; real loopback and HAOS remain unverified. Actual Docker/HAOS deployment, live source accuracy/rights and B1G device acceptance remain unverified. The feed has no EPG programme rows; provider EPG remains primary. See [current status](../docs/CURRENT_STATUS.md) and [changelog](CHANGELOG.md).
