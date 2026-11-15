# Current implementation and verification status

**15 November 2026 · SportsLiveInfo 0.3.23.** Start with the [15 November handover](HANDOVER_2026-11-15_SPORTSLIVEINFO_B1G.md), the [15 November forensic audit](AUDIT_2026-11-15_FORENSIC_SPORTSLIVEINFO.md) (open work), the [B1G reconciliation spec](B1G_CHANNEL_AND_GUIDE_RECONCILIATION_SPEC.md) and the [feed contract](FEED_CONTRACT_SLI_V1.md). The public [SportsLiveInfo source repository](https://github.com/jimmyfazz/SportsLiveInfo) builds the Home Assistant App. [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is the public data destination; `LiveSports-EPG-private` is the owner's private personal-use feed. Credentials, guide programme text and App settings stay on Home Assistant.

- **Installed:** 0.3.23 on the owner's Home Assistant (15 Nov 08:59 UTC). Backup `9542a582` of 0.3.21 was taken first, and auto-update is on. The App started cleanly ("Ingress HTTP ready").
- **Public feed:**
  - **Last observed publish:** `sli/1.5` at 04:17 UTC on 15 Nov, from 0.3.21.
  - **First `sli/1.6` publish:** due at the next scheduled run (04:00, 12:00 or 17:00 UK time). **Not yet observed.**
  - **What `sli/1.6` adds:** status observation times, a `live_state_rule`, an optional `live` asset, core and extra tiers, and guide-corroborated links (never "verified").
  - **No programme rows:** the feed still carries no EPG programme listings.
- **Live-status lane:** implemented and tested offline. The API-Sports `live=all` calls have **not yet run** against the live service.
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
