# Current implementation and verification status

**15 November 2026 · SportsLiveInfo 0.3.24.** How agents work: [AGENT_OPERATING_MANUAL.md](AGENT_OPERATING_MANUAL.md). Start with the [15 November handover](HANDOVER_2026-11-15_SPORTSLIVEINFO_B1G.md), the [15 November forensic audit](AUDIT_2026-11-15_FORENSIC_SPORTSLIVEINFO.md) (open work), the [B1G reconciliation spec](B1G_CHANNEL_AND_GUIDE_RECONCILIATION_SPEC.md) and the [feed contract](FEED_CONTRACT_SLI_V1.md). The public [SportsLiveInfo source repository](https://github.com/jimmyfazz/SportsLiveInfo) builds the Home Assistant App. [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is the public data destination; `LiveSports-EPG-private` is the owner's private personal-use feed. Credentials, guide programme text and App settings stay on Home Assistant.

- **Installed:** 0.3.24 on Home Assistant since 15 Nov 11:06 UTC (backup `2f1c1ebc` of 0.3.23 first) — channels ranked by evidence (ITV1 first, not Irish/Asian ids), past-year re-runs never live, free streaming channels not mistaken for broadcast services, rugby duplicates merged, and the feed now carries the decisions B1G follows (`rank`, `binds`, `live_until_utc`; [contract §4.3](FEED_CONTRACT_SLI_V1.md)). 329 tests pass.
- **Previously:** 0.3.23 (15 Nov 08:59 UTC). Backup `9542a582` of 0.3.21 was taken first, and auto-update is on. The App started cleanly ("Ingress HTTP ready").
- **Public feed:**
  - **`sli/1.6`:** live since 09:00 UTC on 15 Nov. At 10:30 UTC the manifest read `sli/1.6` (publisher 0.3.23) with the `live` and `events_extra` assets.
  - **What `sli/1.6` adds:** status observation times, a `live_state_rule`, an optional `live` asset, core and extra tiers, and guide-corroborated links (never "verified").
  - **No programme rows:** the feed still carries no EPG programme listings.
- **Live-status lane:** running on Home Assistant. It republishes the `live` asset every 15 minutes while matches are on: at 10:30 UTC it held 42 events (34 live, 8 unknown). One publish failed on a GitHub HTTP 500 and the next succeeded.
- **B1G:** has read the feed since B1 PR #827. PR #828 (merged 15 Nov, B1 `main` `7269e5f`) applies the `sli/1.6` reader rules. A B1 interop test reads this repository's golden 1.6 feed.
  - **Unit tests:** the Gradle unit suite (2,179 tests) passes, run in a cloud session.
  - **CI:** B1's GitHub Actions do not run (account billing; the owner does not use them).
  - **On a TV:** **device acceptance not yet run.**
- **Private feed:** enabled; publishes with the public feed.
- **Live sport allocation (three public UK guides, 14–20 Nov):** 234 of 244 live UK sports broadcasts have a channel; 14 of 14 labelled fixtures match; no radio, shopping, +1 or commentary candidates.
- **Channel identification (owner's list, 0.3.18):**
  - UK and Europe: 61.5 % by the dictionary; 71.2 % of their sport channels.
  - France: 66.9 %.
  - The whole 21,250-channel list: 50.1 % with all optional world regions.
- **Known limits:**
  - **API-Sports free key:** yesterday, today and tomorrow only.
  - **TheSportsDB free key:** at most 3 events per request.
  - **Not checked from the cloud session:** French guide listing formats and Docker/Supervisor build internals.

## Validation

```sh
python3 -m compileall -q sportsliveinfo/src tests
PYTHONPATH=sportsliveinfo/src python3 -m unittest discover -s tests
```

**Local result:** 315 tests passed (0.3.23, 15 Nov 2026). CI (`verify.yml`) passes on every merged PR. See [implementation progress](IMPLEMENTATION_PROGRESS.md) for measurements and the [document index](DOCUMENTATION_INDEX.md) for earlier records.
