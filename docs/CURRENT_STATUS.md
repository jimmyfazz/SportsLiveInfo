# Current implementation and verification status

**15 November 2026 · SportsLiveInfo 0.3.21.** Start with the [14 November handover](HANDOVER_2026-11-14_SPORTSLIVEINFO_B1G.md), the [B1G reconciliation spec](B1G_CHANNEL_AND_GUIDE_RECONCILIATION_SPEC.md) and the [channel identification and EPG source research](RESEARCH_2026-11-14_CHANNEL_IDENTIFICATION_AND_EPG_SOURCES.md). The public [SportsLiveInfo source repository](https://github.com/jimmyfazz/SportsLiveInfo) builds the Home Assistant App. [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is the public data destination; `LiveSports-EPG-private` is the owner's private personal-use feed. Credentials, guide programme text and App settings stay on Home Assistant.

- **Installed:** 0.3.21 on the owner's Home Assistant (15 Nov 07:17 UTC; backup `6feebca2` of 0.3.20 first; auto-update on). It started cleanly.
  - 0.3.21 stops asking API-Sports for dates the plan refuses.
  - It also fills the week ahead from TheSportsDB per competition (rugby internationals, Six Nations, URC, Premiership, Champions Cup, Super League, PDC darts, World Snooker, UFC). See the [changelog](../sportsliveinfo/CHANGELOG.md).
- **Public feed (measured 15 Nov 04:15, before 0.3.21):**
  - **Format:** `sli/1.5` from 0.3.20.
  - **Events:** 2,271 events from owner-approved sources: 1,923 today, 229 tomorrow, then 2–68 a day.
  - **Assets:** channel registry, identity, dictionary (3.1 MB), `guide_map` (1.7 MB) and D8 channel links (never "verified").
  - **Expected after 0.3.21:** more rugby, darts, snooker and UFC fixtures beyond tomorrow.
- **B1G:** reads the feed since B1 PR #827 (merged 15 Nov). It reconciles channels with the same rules (conformance fixtures pass), uses the guide map for gap-fill guides and channel details, shows event-slot fixtures in the Guide, and builds Sports Today from the feed. GitHub Actions on B1 are blocked by account billing; the Gradle unit suite (2,127 tests) passes in a cloud session. **Device acceptance not yet run.**
- **Private feed:** implemented (0.3.14); enabled and connection-tested on 14 Nov.
- **Live sport allocation (three public UK guides, 14–20 Nov):** 234 of 244 live UK sports broadcasts have a channel; 14 of 14 labelled fixtures match; no radio, shopping, +1 or commentary candidates.
- **Channel identification (owner's list, 0.3.18):** UK + Europe 61.5 % by the dictionary, UK + Europe sport channels 71.2 %, France 66.9 %; whole 21,250-channel list 50.1 % with all optional world regions.
- **Known limits:**
  - **API-Sports free key:** today and tomorrow only.
  - **TheSportsDB free key:** at most 3 events per request.
  - **Not checked from the cloud session:** French guide listing formats and Docker/Supervisor build internals.

## Validation

```sh
python3 -m compileall -q sportsliveinfo/src tests
PYTHONPATH=sportsliveinfo/src python3 -m unittest discover -s tests
```

**Local result:** 286 tests passed (0.3.21, 15 Nov 2026); CI passes on every merged PR. See [implementation progress](IMPLEMENTATION_PROGRESS.md) for measurements and [document index](DOCUMENTATION_INDEX.md) for earlier records.
