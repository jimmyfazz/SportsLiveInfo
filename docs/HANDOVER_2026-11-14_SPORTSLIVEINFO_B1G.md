# Handover — SportsLiveInfo and B1G, 14 November 2026

**Supersedes** [the 13 November handover](HANDOVER_2026-11-13_SPORTSLIVEINFO_B1G.md). Start here. For the feed contract read [FEED_CONTRACTS_AND_PUBLICATION.md](FEED_CONTRACTS_AND_PUBLICATION.md) (§6.1 D8 channel links, §6.2 private feed); for change history read [the changelog](../sportsliveinfo/CHANGELOG.md); for measurements read [IMPLEMENTATION_PROGRESS.md](IMPLEMENTATION_PROGRESS.md).

## 1. What exists

| Part | Where | State |
|---|---|---|
| SportsLiveInfo (SLI) Home Assistant app | `jimmyfazz/SportsLiveInfo` (public source) → owner's Home Assistant, slug `106c7bd5_sportsliveinfo` | **0.3.17** installed, auto-update on |
| Public feed | `jimmyfazz/LiveSports-EPG` (public), `v1/manifest.json` | `sli/1.3`; ~4,400 events; D8 channel links on ~50 events; published on the schedule 04:00/12:00/17:00 Europe/London |
| Private feed | `jimmyfazz/LiveSports-EPG-private` (private, `main` exists) | Enabled; **connection test passed 14 Nov 09:41 UTC** (token authenticated, repository confirmed private, write access confirmed). First publication pending: *Publish now* or the next scheduled run |
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
1. ~~Enable the private feed~~ — done 14 Nov (token has the repository; settings saved; connection test passed). Remaining: the first private publication (*Publish now*, or wait for 12:00/17:00/04:00 UK). Verify: a new commit "SportsLiveInfo private feed …" on `LiveSports-EPG-private` and an App log line "Private feed publication finished".
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

## 8. Prompt for ChatGPT Codex (terminal, local B1 checkout with the emulator)

```text
You are working in the B1G repository (github.com/jimmyfazz/B1), Android app in platforms/android/.
Goal: make B1G read the SportsLiveInfo (SLI) feed and use it for (1) live sport with the correct
channel and (2) better guide matching — as a READ-ONLY client. Work in small PRs on your own branch;
never push to main or merge without the owner; squash-merge only.

READ FIRST (in order)
1. B1: CLAUDE.md, AGENTS.md, docs/B1G_DELIVERY_PLAN_FOR_ALL_AGENTS.md,
   docs/ANDROID_BUILD_AND_INSTALL_CHECKLIST.md, docs/SPORTSLIVEINFO_SHARED_EPG_AND_SPORTS_B1G_HANDOVER_2026-11-12.md.
2. SLI (github.com/jimmyfazz/SportsLiveInfo, main — the contract owner; do NOT edit it):
   docs/HANDOVER_2026-11-14_SPORTSLIVEINFO_B1G.md (start here), docs/FEED_CONTRACTS_AND_PUBLICATION.md
   (esp. §6.1 D8 broadcast_links, §6.2 private feed), sportsliveinfo/CHANGELOG.md (0.3.8–0.3.17),
   schemas/*.schema.json, schemas/fixtures/sli-v1/ (golden feed + matching-cases.json),
   sportsliveinfo/src/sportsliveinfo/{guide.py,dictionary.py,linking.py} (reference algorithms).
3. Existing B1G code: ui/HomeSportsEvents.kt, data/SportsPriorityStore.kt, ui/EpgResolver.kt,
   data/ChannelVisibilityStore.kt, data/EpgChannelMappingStore.kt, ui/BroadcasterEpgAliases.kt,
   ui/SkyHomeScene.kt, ui/SkyGuideScene.kt, data/CatalogueCache.kt, data/XtreamClient.kt,
   data/PersistentProgrammeCache.kt (all under platforms/android/app/src/main/java/com/b1giptv/player/).

FEEDS
- Public: https://raw.githubusercontent.com/jimmyfazz/LiveSports-EPG/main/v1/manifest.json
  (format sli/1.3). Assets are content-addressed: verify sha256 and size before use; keep the
  last good feed; obey compatibility rules (unknown fields/assets ignored; major mismatch -> keep last good).
- Private (optional): jimmyfazz/LiveSports-EPG-private, same layout, manifest "visibility":"private".
  Superset: all events + guide-listed live sport (origin "guide_listing") + channel_name and
  programme times in broadcast_links. Access with a fine-grained READ-ONLY token entered by the owner
  in Settings, stored encrypted (Android Keystore), never logged, never in URLs/commits. Prefer the
  private manifest when readable; fall back to public; never write to GitHub from a TV.

PHASES (one PR each; tests + real emulator evidence each time)
P0 Baseline: git status/branch/latest main; build and run unit tests; record the reference-APK
   gate status (follow the plan's instruction). Report anything NOT RUN.
P1 Feed client: fetch/verify/cache manifest + assets (public, optional private), staleness display,
   background refresh at reader_poll_minutes, offline last-good. Unit tests against SLI golden fixtures.
P2 Channel identity: map the CURRENT ACCOUNT's live channels to SLI canonical ids using the channels
   asset (services, normalisation steps, regional_services rules with parent/region, source_crosswalk)
   and the dictionary asset (aliases, language_variants, fallbacks, closed channels).
   Precedence: user manual mapping > provider epg_channel_id exact > crosswalk > service name >
   dictionary. Never auto-merge regional versions, +1/+2, Sky Sports+ or numbered variants.
   Respect ChannelVisibilityStore hidden categories/channels. Reproduce matching-cases.json exactly
   (cross-language test). Store mappings locally only.
P3 Sports Today rail: ingest events (events:<date> + today assets) and broadcast_links; map each
   link's canonical id to the account's channel(s); honour coverage/not_on/parent_channel_id with a
   new setting "TV region" (England/Scotland/Wales/Northern Ireland; default England) so regional
   matches go to the right channel. Rank with SportsPriorityStore; keep PPV card behaviour.
   Label links "listed in TV guide (unverified)"; never say "Live now" just because a programme
   started; "Watch" only for a mapped, visible channel.
P4 On-device guide-listed live sport: port SLI linking._guide_live_events (+ _allocate_regions,
   _listing_parts, _guide_listing, _guide_sport, fixture/variant/team rules) to Kotlin and run it on
   the PROVIDER's own EPG cache for the current account; merge with feed events (attach channels to
   a feed event when it is the same fixture; otherwise create a local event). Local only, never
   uploaded. Use SLI tests/test_guide_listed_events.py and test_broadcast_matcher_safety.py as specs.
P5 Event-slot channels: bind provider event-slot channels whose names carry a fixture/time
   (e.g. "EPL 03 | Everton vs Coventry (Fri 20:00 UK)") to feed events by teams + time; local only.
P6 Guide matching: use canonical ids/dictionary to improve EpgResolver fallback for channels with no
   usable provider guide id; show "channel closed (date, replacement)" for closed channels.

NON-NEGOTIABLE
- Do not decompile TiviMate; no DRM circumvention; stream proxy stays token-gated.
- No credentials, personal names, LAN addresses, emails or the owner's channel list in commits.
- No paid APIs; TMDB/OMDb/artwork stays local to B1G. No LLM calls at runtime.
- One persistent player (never remount); D-pad: cross-region in MainActivity.dispatchKeyEvent +
  global focus listener, in-scene SpatialFocusNavigator; focus visuals are Sky hairline drawables
  (no scale/raise); keep rail geometry and one-rail-per-DOWN.
- Provider guide stays primary; SLI never republishes programme text.

BUILD/TEST
cd platforms/android && ./gradlew --no-daemon :app:testDebugUnitTest :app:assembleDebug
Install: tools/android-install-latest.sh (debug package .debug, versionName carries the commit).
Evidence per PR: unit test output, emulator screenshots of the rail/guide, install proof,
and a list of what was NOT RUN and why. Commit format per CLAUDE.md with your own attribution.
```
