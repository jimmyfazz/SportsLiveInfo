# Handover — SportsLiveInfo and B1G, 14 November 2026

**Supersedes** [the 13 November handover](HANDOVER_2026-11-13_SPORTSLIVEINFO_B1G.md). Start here. For the feed contract read [FEED_CONTRACTS_AND_PUBLICATION.md](FEED_CONTRACTS_AND_PUBLICATION.md) (§6.1 D8 channel links, §6.2 private feed); for change history read [the changelog](../sportsliveinfo/CHANGELOG.md); for measurements read [IMPLEMENTATION_PROGRESS.md](IMPLEMENTATION_PROGRESS.md).

## 1. What exists

| Part | Where | State |
|---|---|---|
| SportsLiveInfo (SLI) Home Assistant app | `jimmyfazz/SportsLiveInfo` (public source) → owner's Home Assistant, slug `106c7bd5_sportsliveinfo` | **0.3.17** installed, auto-update on |
| Public feed | `jimmyfazz/LiveSports-EPG` (public), `v1/manifest.json` | `sli/1.3`; ~4,400 events; D8 channel links on ~50 events; published on the schedule 04:00/12:00/17:00 Europe/London |
| Private feed | `jimmyfazz/LiveSports-EPG-private` (private) | Code ready (0.3.14); **owner still to enable** on the Publishing page |
| B1G Android app | `jimmyfazz/B1`, `platforms/android/` | Does **not** read SLI yet; next project (§6) |

Home Assistant backups of the app are taken before every update (named "SportsLiveInfo <old> before <new> update"; e.g. `f4d5a9e9` before 0.3.15).

## 2. What changed 13–14 November (0.3.9 → 0.3.17)

| Version | Change | Measured effect |
|---|---|---|
| 0.3.9 | Matt Huisman NZ and Sydney guides fixed (direct URLs); Sky UK guide retired (gone upstream) | Both import on Home Assistant |
| 0.3.10 | Stricter event→channel matcher (team rules, women's/age variants, club suffixes, +1/radio/shopping excluded, one id per service) | Labelled UK broadcasts 6/14 → 14/14, all candidates correct |
| 0.3.11 | Regional channel model: BBC/ITV nations, STV, UTV as separate services with a parent; per-region allocation (`coverage`, `not_on`, `parent_channel_id`) | Wales v Portugal (BBC One Wales only) no longer allocated to national BBC One |
| 0.3.12 | **Guide-listed live sport**: live listings on recognised channels with no event become private events with channels | Live UK sports broadcasts with a channel: 25/251 (10 %) → 234/244 (96 %) |
| 0.3.13 | **D8 approved**: public events carry `broadcast_links` (canonical ids, coverage, confidence, guide count; no guide text) | Public feed `sli/1.3` |
| 0.3.14 | **Private feed** to a private repository: all events + guide-listed events + channel names/times | Awaiting owner enablement |
| 0.3.15 | France/Europe channel identification: dictionary fallbacks (aliases, plural, guarded language variants), closed-channel explanation, UHD markers, FR/DE/ES/IT sport words | France 60.2 % → 65.5 % resolved; UK+Europe 53.4 % → 55.3 % |
| 0.3.17 | Connection tests run in the background and log their result (remote access dropped the page before the answer) | — |
| 0.3.16 | Radio/audio commentary listings on TV channels excluded (MUTV "Radio Commentary"); repository fields accept GitHub links (private feed settings appeared not to save) | UK benchmark unchanged |

## 3. Decisions (owner)

- **D8 — approved:** publish event→channel links as canonical ids and confidence only, never guide text, never "verified".
- **Guide-listed events are never public.** Their guide sources forbid republication (EPGTalk: personal use only). The public repository stays public and unchanged.
- **Delivery to TVs = on-TV computation + private repository.** Some TVs are away from home. TVs use a separate **read-only** token for the private repository; the Home Assistant publishing token never goes on a TV.
- **Deferred by the owner:** remaining unmatched channels; event coverage beyond tomorrow (free API-Sports serves yesterday/today/tomorrow only; extending needs a paid plan and owner approval).

## 4. How matching works (reference for B1G)

All in `sportsliveinfo/src/sportsliveinfo/`; B1G must reproduce the published rules exactly.

1. **Channel registry** (`guide.py`): `SERVICES` names per market, `SOURCE_ID_CROSSWALK`, `REGIONAL_RULES` + `REGIONAL_PARENTS` (published as `regional_services` in the channels asset). English regions → network id; nations are separate services.
2. **Dictionary** (`dictionary.py`, iptv-org database, public domain): exact/compact → decoration → broadcast area; then fallbacks: aliases → singular/plural → language variants (only with a market code or a distinctive name). Closed channels are explained, never matched. Rules published in the dictionary asset (`aliases`, `language_variants`, `rules.fallbacks`).
3. **Event→channel** (`linking.broadcast_candidates`): strict fixture match (both sides, competition/programme words only, women's/age variants agree, guide may add a club suffix), sport-eligible channels (no radio/shopping/+1), then `_allocate_regions` (network only when every observed nation carries or simulcasts it).
4. **Guide-listed live sport** (`linking._guide_live_events`): live listings on recognised channels, sport from listing words or channel, merged across guides/simulcasts, women's and men's kept apart, attached to a feed event when the names differ only in form. Spec tests: `tests/test_guide_listed_events.py`, `tests/test_broadcast_matcher_safety.py`.

## 5. Outstanding

**Owner actions**
1. Enable the private feed: edit the *SportsLiveInfo Publisher* fine-grained token on GitHub to include `LiveSports-EPG-private` (Contents: Read and write); then Publishing → Private feed → repository `LiveSports-EPG-private` (a GitHub link also works from 0.3.16), Enable, Save, *Test private feed connection* (refresh for the result), *Publish now*.
2. Check Home Assistant results (Collect now → Live today / Sports events), especially **French live sport** (Ligue 1, Top 14, cyclisme on Canal+/beIN/RMC): French guide listings could not be fetched from the cloud session, so French listing formats are unit-tested only.
3. When the B1G reader exists: create a TV token — fine-grained, **Contents: Read-only**, `LiveSports-EPG-private` only.

**Deferred (owner will return to)**
- Unmatched channels: France 151 of 777 (plus 46 closed, 71 event slots/Molotov); elsewhere mostly international brands whose local version the public database lacks — needs B1G guide-name matching on the TV.
- Event coverage beyond tomorrow (paid API decision).

**Minor**
- Success summaries per guide in the Home Assistant log (today only failures are logged).

## 6. Next project: B1G reads SLI

Phases (one small PR each, real emulator evidence, report anything NOT RUN):
- **P0** baseline build/tests and reference-APK gate status.
- **P1** feed client: public + optional private manifest, sha256/size verification, last-good cache, staleness, compatibility rules; read-only token stored encrypted, never logged.
- **P2** channel identity for the **current account**: channels + dictionary assets; precedence user mapping > provider epg id > crosswalk > service name > dictionary; never merge regional/+1/Sky Sports+/numbered; hidden channels respected; reproduce `schemas/fixtures/sli-v1/matching-cases.json`.
- **P3** Sports Today: events + `broadcast_links` mapped to the account's channels; a *TV region* setting (England/Scotland/Wales/NI) applies `coverage`/`not_on`; "listed in TV guide (unverified)"; no "Live now" from programme start alone.
- **P4** on-device guide-listed live sport: port §4.4 to Kotlin over the provider's own EPG cache; local only.
- **P5** event-slot channels (fixture + time in the name) bound to feed events; local only.
- **P6** guide matching fallback via canonical ids/dictionary; closed-channel notes.

The full terminal prompt for this work was given to the owner on 14 November; its constraints are those in B1 `CLAUDE.md` (no TiviMate decompilation, no DRM circumvention, no credentials or personal data in commits, no paid APIs, TMDB/OMDb local, persistent player, D-pad and focus rules).

## 7. Operating notes

- **Release:** bump `sportsliveinfo/config.yaml`, `sportsliveinfo/Dockerfile` (`BUILD_VERSION`) and `sportsliveinfo/src/sportsliveinfo/__init__.py`; changelog entry; `PYTHONPATH=sportsliveinfo/src python3 tools/generate_feed_fixtures.py`; full test suite; PR; CI green; Home Assistant backup of the app; squash-merge; on Home Assistant refresh the app store (it caches the repository) and update.
- **Validation:** `PYTHONPATH=sportsliveinfo/src python3 -m unittest discover -s tests` (241 tests at 0.3.17).
- **Benchmarks** used public UK guides (farleyflex, Freeview, EPGTalk UK), feed revisions from `LiveSports-EPG`, the iptv-org CSVs and the owner's private channel list; scripts and data are kept outside the repositories. Only GitHub-hosted guides are reachable from cloud sessions; iptv-epg.org, epgshare01 and xmltvfr.fr are blocked there.
- **Privacy:** never commit the owner's channel list, credentials, tokens, LAN addresses or personal details; use synthetic names in tests.
