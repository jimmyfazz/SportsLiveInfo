# SportsLiveInfo Home Assistant App

> **Repository roles:** [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is the public App source and installation repository; [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is PUBLIC daily data only. [Current status and evidence](../docs/CURRENT_STATUS.md).

**v0.3.19 · experimental · 14 November 2026.** The app:
- collects sporting events and TV guides on your Home Assistant;
- links live sport to channels;
- publishes a public feed (`sli/1.4`, owner-approved sources only) and an optional private feed for your own TVs;
- publishes a channel dictionary B1G uses to identify provider channels, with optional world regions.

Every guide source is off until you switch it on, and guide programme data is never published publicly.

[SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is the **public App source and installation repository**. [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is the **public daily-feed repository**, not an App installer. Use the installation or in-place local update steps as described in [installation and use](DOCS.md).

The offline test suite runs in CI on every change. Device acceptance in B1G is still to come. See [current status](../docs/CURRENT_STATUS.md) and [changelog](CHANGELOG.md).
