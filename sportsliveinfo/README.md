# SportsLiveInfo Home Assistant App

> **Repository roles:** [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is the public App source and installation repository; [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is PUBLIC daily data only. [Current status and evidence](../docs/CURRENT_STATUS.md).

**v0.3.0 · experimental · reviewed 12 November 2026.** Private Ingress administration, persistent SQLite, bounded EPG/sport collection, coverage diagnostics, Live today, event filters, schedule and optional rights-gated `sli/1.0` publication are implemented in source.

[SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is the **public App source and installation repository**. [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is the **public daily-feed repository**, not an App installer. Use the installation or in-place local update steps as described in [installation and use](DOCS.md).

The current suite passes all 182 tests (13 Nov 2026, Python 3.13). HTTP-handler tests use an in-memory transport in this socket-restricted runner; real loopback and HAOS remain unverified. Actual Docker/HAOS deployment, live source accuracy/rights and B1G device acceptance remain unverified. The feed has no EPG programme rows; provider EPG remains primary. See [current status](../docs/CURRENT_STATUS.md) and [changelog](CHANGELOG.md).
