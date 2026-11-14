# Current implementation and verification status

**14 November 2026 · SportsLiveInfo 0.3.19.** Start with the [14 November handover](HANDOVER_2026-11-14_SPORTSLIVEINFO_B1G.md) and the [channel identification and EPG source research](RESEARCH_2026-11-14_CHANNEL_IDENTIFICATION_AND_EPG_SOURCES.md). The public [SportsLiveInfo source repository](https://github.com/jimmyfazz/SportsLiveInfo) builds the Home Assistant App. [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is the public data destination; `LiveSports-EPG-private` is the owner's private personal-use feed. Credentials, guide programme text and App settings stay on Home Assistant.

- **Installed:** 0.3.18 on the owner's Home Assistant (14 Nov 17:05, backup 19f20a4b of 0.3.17 first; auto-update on). 0.3.19 fixes the EPGTalk UK import limit and makes matching about 8× faster.
- **Public feed:** `sli/1.3` (0.3.18 publishes `sli/1.4`: optional dictionary regions, country tags and rules), about 4,400 events from owner-approved sources, channel registry with UK regional services, UK/Europe channel dictionary with fallback rules, and D8 channel links (`broadcast_links`: canonical ids and confidence only, never verified).
- **Private feed:** implemented (0.3.14); every collected event plus guide-listed live sport with channel names and times. Enabled and connection test passed on 14 Nov 09:41 UTC; the first private publication is pending.
- **Live sport allocation (three public UK guides, 14–20 Nov):** 234 of 244 live UK sports broadcasts have a channel (25 of 251 before 0.3.12); 14 of 14 labelled fixtures match; no radio, shopping, +1 or radio-commentary candidates; regional opt-outs allocated correctly.
- **Channel identification (owner's list, 0.3.18):** UK + Europe 61.5 % by the dictionary (55.4 % at 0.3.17), UK + Europe sport channels 71.2 % (57.8 %), France 66.9 %; whole 21,250-channel list 50.1 % with all optional world regions (20.0 %). Downloadable guide (GitHub-hosted files): France 75.4 %, Spain 72.8 %, Italy 72.7 %, UK 69.8 %, Portugal 62.7 %, Germany 56.8 %.
- **New optional guides (0.3.18, off by default):** Sky UK/DE/IT and Sky Italia (M3UPT, xz), EPGTalk US/US local/Latin/free streaming, Sky Sport Now and Sky Go NZ, Kayo and all-cities AU, UK and US free streaming (Plex/Samsung/Pluto/Roku), DStv South Africa, Spain incl. Movistar Plus+, France + beIN MENA, Portugal; further EPG Share / IPTV-EPG.org country files to verify on Home Assistant.
- **Not verified:** French guide listing formats (French guides unreachable from the cloud session), Docker/Supervisor build internals, and B1G device acceptance (B1G does not read SLI yet).

## Validation

```sh
python3 -m compileall -q sportsliveinfo/src tests
PYTHONPATH=sportsliveinfo/src python3 -m unittest discover -s tests
```

**Local result:** 263 tests passed (0.3.19, 14 Nov 2026); CI passes on every merged PR. See [implementation progress](IMPLEMENTATION_PROGRESS.md) for measurements and [document index](DOCUMENTATION_INDEX.md) for earlier records.
