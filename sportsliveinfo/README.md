# SportsLiveInfo Home Assistant App

> **Repository roles:** [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is the public App source and installation repository; [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is PUBLIC daily data only. [Current status and evidence](../docs/CURRENT_STATUS.md).

**v0.3.31 · experimental · 24 November 2026.** The app:
- collects sporting events and TV guides on your Home Assistant;
- links live sport to channels, best channel first, with channel hints for B1G;
- publishes a public feed (`sli/1.7` with scores on, otherwise `sli/1.6`; owner-approved sources only) and an optional private feed for your own TVs: yesterday's history, display state (live, finished, upcoming), league standings, team crest and competition logo references, event metadata and the channel hints;
- publishes a channel dictionary B1G uses to identify provider channels, with optional world regions;
- reads the API-Sports live board for core-tier events within a daily call budget, and tells you in Home Assistant when that budget is used up.

Every guide source is off until you switch it on, and guide programme data is never published publicly.

[SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is the **public App source and installation repository**. [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is the **public daily-feed repository**, not an App installer. Use the installation or in-place local update steps as described in [installation and use](DOCS.md).

The offline test suite (657 tests) runs in CI on every change. Device acceptance in B1G is still to come. See [current status](../docs/CURRENT_STATUS.md) and [changelog](CHANGELOG.md).
