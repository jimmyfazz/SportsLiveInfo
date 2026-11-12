# Forensic B1G EPG, Sports Today, API-credential and centralisation audit

> **Historical audit / receipt — reviewed 12 November 2026.** Preserved against its stated original revision. Findings, branch/merge positions, provider claims and pass counts below are historical, not freshly verified current facts. Current source is v0.3.0; the combined review attempted 86 tests (81 passed, five errors, three of those environment-blocked). Use CURRENT_STATUS for resolved/remaining work; no new live source, licence or device verification occurred.
> **Repository roles:** [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is PRIVATE source/installation and stays private; [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is PUBLIC daily data only. [Current status and evidence](CURRENT_STATUS.md).

**Date:** 12 November 2026  
**Source baseline:** jimmyfazz/B1 main at `9d77ebe7478dfb24f0ee9bceb2e20a149bb53180`; third-party farleyflex/epg-guide inspected independently.  
**Requested deployment:** directly installed Home Assistant mini PC, SportsLiveInfo as a local HAOS App; 10 B1G TVs; outbound-only publication to a separately approved public GitHub feed.  
**Status:** source-code audit and implementable specification, NOT a tested working integration. No live EPG accuracy benchmark, Android build, TV device acceptance or redistribution permission obtained.

## 1. Definitive user scope: EPG and sporting rail, not VOD artwork

**Priority A: UK sports EPG improvement.** Reliable, more descriptive programme listings for Sky Sports, TNT Sports, Premier Sports and relevant BBC/ITV/Channel 4 and other sports broadcasters. Show accurate programme name, fixture/competitors, scheduled sporting time, broadcast coverage start/end, live/repeat distinction, channel identity and provenance. Prefer a verified detailed sports listing to a generic baseline listing without corrupting an accurate original schedule or overriding an explicit user choice.

**Priority B: Sports Today cards.** One 10-card rail with the existing PPV-boxing 11th-card exception where supported by the relevant B1G platform, showing sport, competition, competitors/venue/F1 circuit, UK start time, programme status and **actual watchable user channel** if confidently matched. The collector knows national broadcaster/EPG identity; the individual B1G device knows the user's own playlists/accounts, channel visibility and stream ID.

**Explicitly OUT OF SCOPE for SportsLiveInfo:** TMDB, OMDb, movie and television series metadata, VOD search, films/series posters, VOD hero artwork and per-title artwork delivery. Their latency and per-title demand are unrelated to scheduled daily sports collection; keep lazy on-device caches and credentials in B1G. Also leave optional free-key TheSportsDB team crest/standings lookup in B1G for now (see inventory). A future small shared team-name/crest URL index is a **separate opt-in project** only if licence and performance justify it.

**Also OUT OF SCOPE:** central proxy of Xtream/M3U/Stalker playlists, IPTV provider logins, account-specific/catch-up EPG, channel URLs, actual streaming, user favourites, hidden-channel data, provider credential-bearing XMLTV URLs, per-TV playing status and artwork CDN traffic.

## 2. What existing B1G code actually does

### 2.1 Detailed UK sports XMLTV source: farleyflex, not a paid API

Mac:
- `B1G-IPTV-Web/src/lib/epg/sports-epg-aliases.ts` sets `SPORTS_EPG_SOURCE_URL` to `https://raw.githubusercontent.com/farleyflex/epg-guide/main/epg.xml`; 11 Sky Sports services, TNT 1–4, Premier Sports 1–2 (17 deliberately conservative aliases). Excludes unsupported Plus/+1 and variant channels.
- `B1G-IPTV-Web/src/lib/epg/sports-epg-setup.ts` adds that feed, sequentially inventories saved playlists and maps unconfigured programme IDs only. It respects user overrides and the 'cleared' tombstone; daily setup is guarded by local day success.
- `B1G-IPTV-Web/src/lib/home/sports-events.ts` extracts matches/events from programme title/subtitle and binds schedule-only fixtures to a real stream only if listing names both teams or explicit `TV:` metadata identifies broadcaster.

Android:
- `platforms/android/app/src/main/java/com/b1giptv/player/ui/BroadcasterEpgAliases.kt` uses the **same URL and equivalent 17 alias IDs**, but source identity is tested by literal equality to the farleyflex URL. A new SportsLiveInfo feed URL will **not** receive those aliases unless source IDs and mapping policy are adapted.
- `SkyGuideScene.kt` includes a user-invoked `Fix sports EPG now` action which adds this feed; it is not a mandated unconditional auto-download.
- The guide initially considers provider EPG and configured sources, then permitted automatic gap-fill backup feeds; retains account-scoped manually selected IDs and per-source preferences.
- Other referenced backups are EPG Share UK 1, Matt Huisman Sky UK, IPTV-org Sky UK, EPGTalk UK and EPGTalk Sports (plus non-UK options). They are **not the same** as farleyflex and have their own availability/rights issues.
- `SkyHomeScene.kt` Sports Today scans selected visible channels and configured/loaded EPG sources, plus synthetic schedule-only XMLTV channels, then ranks/links candidates. It does **not** verify an independently live sporting result simply because a programme window is current.
- `EpgSourcePrecedencePolicy.kt` does interval gap-only precedence: existing occupied programme windows normally block later whole overlapping listings. `EpgScheduleMerger.kt` supports limited generic-to-detailed promotion for same intervals. **Simply appending SportsLiveInfo as another source is not a reliable fix** for generic provider entries; audited source precedence and quality-based replacement are needed.

### 2.2 Fixture-provider input already exists on Android

- `platforms/android/app/src/main/java/com/b1giptv/player/data/SportsFixtures.kt`: optional **API-Sports** (`https://v3.football.api-sports.io/fixtures?date=...&timezone=Europe/London`), with user key sent via `x-apisports-key`. Uses a 30-minute positive/attempt cache with max 1,000 fixtures and 4 MiB response bound.
- `SkyHomeScene.kt`: if enabled, does the independent per-device fetch and runs `HomeSportsEvents.reconcile` against EPG-derived candidates.
- `HomeSportsEvents.kt` football reconciliation removes unmatched EPG football entries when the API returns a non-null list, even if free-tier competition coverage was incomplete or a provider supplied an empty but technically successful response. This creates a **false-omission risk**. It matches on unordered team pair without competition/day/round in its map; cannot be assumed universally unique. It infers 'live' from start + estimated duration, not independently verified in-progress state.
- Mac has equivalent user-key preference and `reconcileFootballWithApiSports` in `B1G-IPTV-Web/src/lib/home/sports-events.ts`.

**Centralisation gain:** put API-Sports key and all sports-fixture API keys on HAOS once. B1G should read only the permitted normalised event snapshot. If 10 TVs use the current per-device 30-minute cache, upstream requests can multiply; the central collector makes upstream usage independent of TV count.

### 2.3 Home rail 10/11 parity risk

- Mac `B1G-IPTV-Web/src/lib/home/sports-events.ts`: **10 body cards**, with 1 special PPV boxing headline card when present => 10 or 11.
- Android `HomeSportsEvents.rank(...limit=10)`: inserts PPV into the **same** overall 10-item limit. This differs from the Mac's 11-card PPV rule. Verify user expectation; migrate to common 10-body+optional PPV selector and tests without changing GUI layout inadvertently.
- Existing B1G Android cards already show team crests/sport fallback, title, time and channel badge; schedule-only cards are non-playable. Retain the same fast card rendering and focus model.

## 3. Exact user-entered API inventory (verified from Android Settings/CredentialsStore and Mac Settings)

| Credential/source | Actual use in B1G | User enters key? | Proposed disposition |
|---|---|---|---|
| API-Sports | Daily football fixtures to validate EPG Sports Today | YES, optional: Android Settings > Sources; Mac settings | **Move owner registration, key and scheduled calls to SportsLiveInfo**. B1G consumer should require no API-Sports key when shared feed enabled; existing direct integration stays as explicit optional backward-compatible fallback during migration. |
| TMDB | Movies/TV title matching, plot/cast/director, movie/series artwork metadata and images | YES, optional per device; Mac may have compile-time fallback | **Keep in B1G**. Never run through SportsLiveInfo. |
| OMDb | Film/series IMDb, Metacritic/Rotten Tomatoes rating enrichment | YES, optional per device; Mac may have compile-time fallback | **Keep in B1G**. Never run through SportsLiveInfo. |
| Xtream / M3U / Stalker account details | User's IPTV catalogue/streams and primary provider EPG; M3U may contain credentialed `url-tvg` | YES, account settings, not generic public sports API | **Keep local per B1G account**; do not upload/share on GitHub or proxy through Home Assistant. |
| Additional XMLTV EPG URL(s) and timezone settings | Individual EPG source configuration and manual user preferences | Feed URL usually keyless; may embed account tokens | **Centralise only universal, authorised, public UK sports source collection.** Keep manual/account-specific XMLTV and local mapping in B1G. |
| TheSportsDB | Team crests and Premier League table via shared public test key; Mac Rust and Android helpers | No normal user-supplied key; source uses public test key `123` | **Keep in B1G for now**. Existing cached/throttled lookup; licence/API restrictions make central republication of badges/standings a different project. |
| User's installed app icons or other artwork | Android installed-app/local/provider artwork, Glide/disk caching | No sporting API credential | **Keep local**. |
| NordVPN or network account settings (where configured) | Network/VPN behaviour, not sporting fixtures/EPG | Separate product credentials if used | **Keep outside**. |

**Observed exact Android saved API keys:** `CredentialsStore.KEY_API_SPORTS`, `KEY_TMDB`, `KEY_OMDB`, surfaced by `SettingsScene.kt` rows. This is the verified UI-level third-party API-key set; the IPTV account login and XMLTV URL are separate data-source credentials. No evidence in inspected Android Settings that TMDB/OMDb should be required for sports rail.

**TheSportsDB detail:** Mac `src-tauri/crates/b1g-core/src/sportsdb.rs` and Android `SportsCrestStore.kt` use cached/throttled team crest lookups. These are sports-related but not the principal fixture schedule. Local crest URL/image cache already avoids repeated requests across most Home revisits; centralising images now would introduce a new licensing/CDN/proxy burden for limited gain.

## 4. Farleyflex provenance, refresh and reliability — CRITICAL

Identified repository: https://github.com/farleyflex/epg-guide

- The README states 75 curated channels, 9,000+ programme rows and 5 days' XMLTV, with the UK channel groups using **mytelly.co.uk**. Its `channels.xml` supplies source-site IDs; these are **not independent verification** of a sporting fixture or official broadcaster rights.
- The upstream's `.github/workflows/generate-epg.yml` is scheduled for **06:00 UTC daily**, fetches five days through `iptv-org/epg`, then commits `epg.xml` and `epg.xml.gz`. GitHub Actions execution may be delayed. Example update commits in the inspected repository: 11 Nov 2026 13:05 UTC, 10 Nov 13:53 UTC, 9 Nov 14:33 UTC. **A 05:00 UK snapshot is necessarily before that day's scheduled upstream generation.** It may still have useful 5-day data, but is not the new day's edition.
- Therefore run a **05:00 UK B1G availability snapshot using last-good material**, and an **upstream-version-aware later refresh** after new EPG is actually committed. Do not simply assume the 06:00 workflow completed, nor use a fixed 06:05 time as proof.
- Farleyflex includes more UK services than B1G's 17 deliberate aliases, including Sky Sports+ and TNT 5–8, but IDs/service semantics for these **must be validated** before mapping. `Sky Sports Action` currently uses a source path labelled Sky Sports NFL in `channels.xml` — verify semantics in actual programme content. Do not unify Sky Sports Premier League with Premier Sports; do not map Sky Sports+ or region/+1 variants from suffix stripping.
- Source-feed freshness != event accuracy: the source's generation time and last programme timestamp are independent; events/TV transmissions need date-by-date benchmark against official sport fixture calendars and permitted broadcaster sources.
- **Rights warning:** the farleyflex repo is publicly readable, but programme descriptions are taken from third-party guide sources via a scraper. Its publication and software code do NOT automatically grant SportsLiveInfo a licence to redistribute a whole copied/derived EPG on another public GitHub repository. Confirm rights with original programme-data owners or a permitted licence. Public feed must explicitly exclude unapproved content.

## 5. Approved high-level architecture: two related outputs with separate licensing gates

### Output A — normalised sport-events JSON (core)

Schedule primary/backup fixtures for football, F1, boxing, tennis, rugby, cricket and other sports. Normalize UTC/local Europe/London, competition and identities, events/status/venue, explicit UK channel claims and confidence. Provide source health, freshness and completeness.

Suggested published path **only after provider-rights review**: `data/sports/YYYY-MM-DD.json` and `data/sports/manifest.json`.

Contains **NO stream IDs/URLs, user playlists, credentials or downloaded third-party images**. B1G maps verified UK channel identity to each account's visible/allowed local channels. Multiple broadcasters can be present; if channel unknown, show event as non-playable and label "UK channel not confirmed". Never fabricate a broadcaster from general rights.

### Output B — UK sports EPG corrections (optional rights-gated component)

From **authorised** UK programme inputs, collect channel-specific current/next programme intervals, title, subtitle, description, sport and sporting-event ID, broadcast coverage start/end, real sport start where corroborated, "live" versus highlights/replay, EPG source provenance, correction reason and confidence.

Proposed paths: `data/epg/uk-sports/YYYY-MM-DD.json` + small manifest; optionally compressed, only if licensed for publication. Prefer a compact EPG **delta/corrections** structure rather than republishing multi-megabyte raw XMLTV. Avoid using a tiny 10-card feed as a replacement for the full B1G Guide: Guide corrections require complete relevant channel/time-window coverage, not just top events.

**If no licence to redistribute source EPG:** do **not** upload that third-party programme content to public GitHub. Instead publish only cleared sporting facts and channel IDs, and keep B1G's original direct XMLTV connection for the actual EPG, or seek permission/a properly licensed source. A public source pointer, source-version hint or channel-ID alias table may still be useful, but never assume such a pointer transfers rights or guarantees downstream service.

### Central collector and consumer flow

    Sport fixtures/API keys ─┐
                             ├─ HAOS SportsLiveInfo collector/reconciler/cache
    Authorised UK EPG feeds ─┘             │
                                         │ outbound HTTPS only
                                         ▼
                            Separate rights-cleared public GitHub feed
                                         │
                              10 B1G Android televisions
                                         │
                   account-local playlist/EPG/channel identity & choice
                                         ▼
                 Home cards + Guide + Live Now/Next + player overlay

No TV should query sporting fixture APIs when central mode is active; TV downloads of public snapshots do not consume sports provider quotas. B1G may still download its own provider/account XMLTV and images.

## 6. B1G consumer implementation requirements

1. New Settings option **Sports & EPG > SportsLiveInfo feed** with URL (sensible default only after real public endpoint exists), status and last-refresh. Zero provider API keys required on the TV when central feed is active.
2. Versioned JSON schema, ETag or revision/sha cache; atomic on-device last-good snapshot; validate local UK day/time, expiry and source-health. Read asynchronously; never block Home hero, D-pad or player.
3. Keep provider EPG and custom per-account XMLTV sources **independent**. Do not disable existing fallback until central accuracy and rights are proven. Respect manual EPG source choice, `autoSuppressedIds`, source-specific ID binding and disabled-feed preferences.
4. Change hard-coded `sourceUrl == SPORTS_SOURCE_URL` alias policy to source-independent, **source-identity-aware** curated mappings with per-feed catalogue verification, or explicitly register SportsLiveInfo as a trusted `sourceId`. Never silently apply farleyflex IDs to unrelated feed catalogues. Preserve Plus/+1, service numbers and region.
5. **High-priority fix:** make source precedence quality-aware only when proven better: a detailed event title can replace a generic programme in the **same verified broadcast interval/channel**; prefer manual overrides; reject mismatched timezone/overlap/replay. "Generic" merely lower-quality, not invalid. Keep prior rows if external feed is stale/empty.
6. **Critical fix:** do not drop valid EPG events solely because a particular free fixture API has partial/unavailable league coverage or an empty list. Represent per-competition completeness; reconcile only verified matching coverage. Keep verified EPG evidence as provisional rather than fabricating/no-op. Prevent incorrect cross-date team-pair matches.
7. "Live" in the Sports Today rail should mean **independently confirmed in-progress sports status**, otherwise use "Live TV coverage" or "Scheduled"; a programme currently airing is not always a sporting event underway.
8. Distinguish actual event start from broadcaster's earlier coverage start and from optional boxing ring walk (estimate). Retain timezone and session structure for F1, multi-day cricket and tennis "not before".
9. Channel selection: central record names UK broadcaster/EPG ID, **never** assumes the local account contains the channel. Map only through visible, non-hidden channels; respect account, provider source, manual mapping, SD/HD/UHD variants, and aggregate multi-match feed constraints. The real stream must be independently identified locally before enabling "Watch".
10. Sports rail selection: preserve configured user priority; verify Android 10 vs Mac 10+PPV 11 mismatch, ensure no duplicate PPV headline. Event identity stable on update so D-pad focus does not jump.
11. Enforce fail-open for Guide: if SportsLiveInfo unreachable, existing provider EPG/curated source continues. Fail closed for unverified channel click-through: display event but don't route to guessed stream.
12. Continue existing user-specified EPG sources, category/visibility overlays, favourites and account switching. Integrate new source via generation-safe invalidation so old account or stale fetch cannot repaint wrong channel.

## 7. Collection and refresh plan, tied to source reality

- Around **04:00 Europe/London**: collect permitted fixture/calendar updates and any last-good UK sports EPG currently available; publish validated morning sports snapshot to be readable near 05:00, after checking GitHub Pages deployment/properties.
- **Post-06:00 UTC**: check farleyflex upstream commit SHA and last successful EPG timestamp at modest intervals; do not download a full XML file repeatedly if SHA/ETag unchanged. New upstream content may land **hours later**. If source rights permit, process and publish corrected EPG delta once the new source version is actually available; otherwise issue a metadata/health update only.
- Midday and early evening: limited authoritative fixture and broadcaster confirmation; publish on validated change. Source-specific rate quotas/terms, changed output and 429 backoff must gate requests.
- On B1G boot/wake: use local cache immediately and async-check manifest. During the day recheck opportunistically (stagger/jitter across ten TVs); no per-TV fixture API key or request. User's network and source account EPG remain local.
- Persist `source_sha`, `source_generated_at`, `retrieved_at`, `programme_window_start/end`, `fixture_verified_at`, `published_at`, `stale` and source-specific completeness. No "source successful" without actual guide coverage.
- HA persistent notifications: actionable repeated upstream outage, expired source, missing UK sports EPG, fixture provider key invalid, publication failure, licensing gate. Quiet normal operation and stable/deduplicated incident IDs.

## 8. Tests and release blockers — source-specific and ten-device

### EPG
- [ ] Compare per-broadcaster channel ID catalogue to real guide rows and UK official schedules on 7+ representative days, covering Sky Sports Main Event, Premier League, Football, F1, Cricket, Tennis, TNT1-4, Premier Sports 1-2, relevant free-to-air, TNT5-8 and Sky Sports+ exploratory only.
- [ ] Provider generic "Live Football" is upgraded only when independently confirmed exact matching interval; conflicting programmes do not get trimmed or mixed.
- [ ] Sky Sports Premier League is not Premier Sports 1. Sky Sports+ and TNT5-8 do not inherit unsafe aliases. Region and +1 channels not conflated.
- [ ] Actual upstream 06:00 UTC workflow / midday-late commit; 05:00 still returns a fresh-enough last-good day from 5-day guide with explicit provenance, not a false "just updated" claim.
- [ ] Multiple XMLTV sources, disabled feed, same tvg-id in competing feeds, ambiguous provider aliases, stale/failing backup, manual override, source removed/re-added, source-specific suppression.
- [ ] EPG data not licensed for publication -> no restricted raw or derived programme details in public JSON.

### Events and rail
- [ ] EPG soccer event missing from API-Sports free competition set is not silently discarded; explicit API 'no data' vs true no-event are different.
- [ ] Football EPG repeats/highlights/previous-day fixture -> not false "live now"; start time independently verified.
- [ ] F1 circuit/qualifying/race, boxing PPV vs normal card coverage, tennis court match not-before, cricket 5-day sessions, rugby union vs league.
- [ ] Event broadcast channel matches source and account-local real playable channel, not an aggregate multi-fixture hub unless genuinely showing that fixture.
- [ ] Android/desktop 10 vs 11 PPV parity; stable sports order/focus and existing channel navigation.
- [ ] 10 B1G TVs simultaneously fetch shared JSON: **zero additional upstream sporting API calls**.
- [ ] TMDB/OMDb/artwork, IPTV playlists and account credentials stay entirely outside SportsLiveInfo; unrelated B1G functions have no regressions.

### Release gates
1. Offline deterministic tests with known XMLTV/programme fixtures and expected changes.
2. Actual live-source sample verification and source freshness/coverage report.
3. Terms/license record for each field released to public GitHub.
4. Independent Android integration build and device acceptance on Fire TV/Shield.
5. Gradual rollout: local-only → one TV → all ten; explicit rollback to current guide/source behavior.

## 9. Prioritised implementation tasks

- **P0 EPG-01** — Central fixture provider key management, day events and evidence schema; no TV API calls.
- **P0 EPG-02** — Identity-aware UK sports source registry incl. farleyflex, EPG Share UK1, Matt Huisman, IPTV-org Sky, EPGTalk (collection only if terms allow).
- **P0 EPG-03** — Fully defined EPG corrections/delta schema with safe source quality and permission gate.
- **P0 B1-01** — B1G read-only feed client, last-good local cache, diagnostics and zero-secret setup, plus safe fallback.
- **P0 B1-02** — Correct generic programme upgrade precedence and manual override/suppression interaction.
- **P0 B1-03** — Fix incomplete/empty API-Sports filtering and date/competition-safe identity and live-status semantics.
- **P1 B1-04** — Maintain 10 body + optional PPV 11 card rule across Android/Mac.
- **P1 HA-01** — First-run wizard provider cards, EPG source status, GitHub token/repo settings, scheduler and quiet HA notifications.
- **P1 OPS-01** — Source-SHA based post-generation refresh and source-health counters; quota and licence gates.
- **P2 QA-01** — 7-day official EPG comparator, ten-TV emulator/device acceptance and corruption/restore tests.

**Original audit scope (superseded):** sporting fixture APIs + UK sports EPG. **Current required scope:** full international EPG (UK/France first) and worldwide sports events, equally mandatory. Keep film/series artwork and TMDB/OMDb in B1G. The B1G Android application remains authoritative for each user's playlists, available channels and playback. Documentation only; no B1G code changes have been made by this audit.

## 10. Verified code/research references

- B1 Android SportsFixtures: https://github.com/jimmyfazz/B1/blob/main/platforms/android/app/src/main/java/com/b1giptv/player/data/SportsFixtures.kt
- B1 Android Sky Home sports pipeline: https://github.com/jimmyfazz/B1/blob/main/platforms/android/app/src/main/java/com/b1giptv/player/ui/SkyHomeScene.kt
- B1 Android EPG Guide backup source list: https://github.com/jimmyfazz/B1/blob/main/platforms/android/app/src/main/java/com/b1giptv/player/ui/SkyGuideScene.kt
- B1 Android conservative sports source aliases: https://github.com/jimmyfazz/B1/blob/main/platforms/android/app/src/main/java/com/b1giptv/player/ui/BroadcasterEpgAliases.kt
- B1 Android source precedence: https://github.com/jimmyfazz/B1/blob/main/platforms/android/app/src/main/java/com/b1giptv/player/ui/EpgSourcePrecedencePolicy.kt
- B1 Android merger: https://github.com/jimmyfazz/B1/blob/main/platforms/android/app/src/main/java/com/b1giptv/player/ui/EpgScheduleMerger.kt
- B1 Android Sports Today rank/reconcile: https://github.com/jimmyfazz/B1/blob/main/platforms/android/app/src/main/java/com/b1giptv/player/ui/HomeSportsEvents.kt
- B1 Android CredentialsStore: https://github.com/jimmyfazz/B1/blob/main/platforms/android/app/src/main/java/com/b1giptv/player/data/CredentialsStore.kt
- B1 Android settings: https://github.com/jimmyfazz/B1/blob/main/platforms/android/app/src/main/java/com/b1giptv/player/ui/SettingsScene.kt
- B1 Mac curated aliases: https://github.com/jimmyfazz/B1/blob/main/B1G-IPTV-Web/src/lib/epg/sports-epg-aliases.ts
- B1 Mac source setup: https://github.com/jimmyfazz/B1/blob/main/B1G-IPTV-Web/src/lib/epg/sports-epg-setup.ts
- B1 Mac events/PPV rule: https://github.com/jimmyfazz/B1/blob/main/B1G-IPTV-Web/src/lib/home/sports-events.ts
- B1 Mac TMDB/OMDb clients: https://github.com/jimmyfazz/B1/tree/main/B1G-IPTV-Web/src-tauri/crates/b1g-core/src
- Upstream farleyflex curated EPG: https://github.com/farleyflex/epg-guide
- Upstream farleyflex daily workflow: https://github.com/farleyflex/epg-guide/blob/main/.github/workflows/generate-epg.yml
