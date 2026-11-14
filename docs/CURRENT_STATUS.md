# Current implementation and verification status

**14 November 2026 · SportsLiveInfo 0.3.18.** Start with the [14 November handover](HANDOVER_2026-11-14_SPORTSLIVEINFO_B1G.md) and the [channel identification and EPG source research](RESEARCH_2026-11-14_CHANNEL_IDENTIFICATION_AND_EPG_SOURCES.md). The public [SportsLiveInfo source repository](https://github.com/jimmyfazz/SportsLiveInfo) builds the Home Assistant App. [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is the public data destination; `LiveSports-EPG-private` is the owner's private personal-use feed. Credentials, guide programme text and App settings stay on Home Assistant.

- **Installed:** 0.3.17 on the owner's Home Assistant (auto-update on), backed up before each update; 0.3.18 offered once merged.
- **Public feed:** `sli/1.3` (0.3.18 publishes `sli/1.4`: optional dictionary regions, country tags and rules), about 4,400 events from owner-approved sources, channel registry with UK regional services, UK/Europe channel dictionary with fallback rules, and D8 channel links (`broadcast_links`: canonical ids and confidence only, never verified).
- **Private feed:** implemented (0.3.14); every collected event plus guide-listed live sport with channel names and times. Enabled and connection test passed on 14 Nov 09:41 UTC; the first private publication is pending.
- **Live sport allocation (three public UK guides, 14–20 Nov):** 234 of 244 live UK sports broadcasts have a channel (25 of 251 before 0.3.12); 14 of 14 labelled fixtures match; no radio, shopping, +1 or radio-commentary candidates; regional opt-outs allocated correctly.
- **Channel identification (owner's list, 0.3.18):** UK + Europe 60.4 % by the dictionary (55.4 % at 0.3.17), UK + Europe sport channels 64.8 % (57.8 %), France 66.9 %; whole 21,250-channel list 49.1 % with all optional world regions (20.0 %).
- **New optional guides (0.3.18, off by default):** Sky Sport NZ, Kayo AU, UK FAST (Plex/Samsung/Pluto), Spain incl. Movistar Plus+, France + beIN MENA, Portugal; further EPG Share / IPTV-EPG.org country files to verify on Home Assistant.
- **Not verified:** French guide listing formats (French guides unreachable from the cloud session), Docker/Supervisor build internals, and B1G device acceptance (B1G does not read SLI yet).

## Validation

```sh
python3 -m compileall -q sportsliveinfo/src tests
PYTHONPATH=sportsliveinfo/src python3 -m unittest discover -s tests
```

**Local result:** 250 tests passed (0.3.18, 14 Nov 2026); CI passes on every merged PR. See [implementation progress](IMPLEMENTATION_PROGRESS.md) for measurements and [document index](DOCUMENTATION_INDEX.md) for earlier records.
