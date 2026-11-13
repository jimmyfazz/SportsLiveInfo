# Handover: SportsLiveInfo ⇄ B1G (13 Nov 2026), for the next agent (ChatGPT/Codex)

**Read this first, then the two project files `CLAUDE.md` / `AGENTS.md` in each repo.**

**Repos:**
- `jimmyfazz/SportsLiveInfo`: Home Assistant app, the collector and publisher.
- `jimmyfazz/LiveSports-EPG`: public feed data only.
- `jimmyfazz/B1`: B1G Android TV app.

**Claude working branch (both repos):** `claude/sportsliveinfo-b1g-android-syyo8j`.

## 1. Live state (verified 13 Nov ~20:50 UTC)

**Home Assistant:**
- The SportsLiveInfo **store app `106c7bd5_sportsliveinfo` 0.3.8** is installed and running.
- Auto-update is on, so merges to SportsLiveInfo `main` reach Home Assistant automatically. **Back up before merging.**
- The old local app 0.3.4 is uninstalled. Its data is in backup `e0231a98`.
- **Backups:**
  - `45f2b6ea` (before 0.3.8);
  - `ab313282` (after 0.3.8);
  - `0ca8c4ea` / `1d5fde71` (0.3.5 → 0.3.6);
  - `e0231a98` (0.3.4).
  
  Updates were done in place; the `/data` keys, token and history were retained, confirmed by equal backup sizes.
- **The owner has enabled the new channel dictionary** and pressed refresh. Its success was not yet confirmed: success jobs are recorded only in the app DB (Diagnostics page), not the Home Assistant log.

**Feed:**
- `https://raw.githubusercontent.com/jimmyfazz/LiveSports-EPG/main/v1/manifest.json`.
- The last publish was 17:38 UTC (revision `1fe6052e…`, 3,398 events, format `sli/1.0`, by 0.3.6).
- The next publish (manual "Publish feed now", or scheduled at 04:00/12:00/17:00 UK with auto-publish on) should add the new optional `identity` and `dictionary` assets (format `sli/1.2`). **Verify after it happens:** sha256 and bytes of every asset, capabilities `channel_identity` and `channel_dictionary`, iptv-org attribution in `rights.attribution`.

**SportsLiveInfo `main`:** `c71b954` (squash of PR #18: v0.3.7 + v0.3.8). Earlier merges: PR #17 (0.3.6 background publish). 199 tests pass:
```
PYTHONPATH=sportsliveinfo/src python3 -m unittest discover -s tests
```
- The Claude branch still holds the pre-squash commits; one early commit contains a few verbatim lineup strings in tests, fixed later. **Always squash-merge from this branch, or recreate it from `main`.**

**B1:**
- All work is docs only, on the Claude branch, **not merged** into B1 `main`.
- No Android code has been written. The Android Gradle build cannot run in the cloud; pure-Kotlin JVM tests can, using the Gradle-embedded kotlinc 2.0.21 and JUnit (`-language-version 1.9`).

## 2. What was built in SportsLiveInfo (versions 0.3.6–0.3.8)

| Version | Feature | Files |
|---|---|---|
| 0.3.6 | Publish runs in the background, every attempt is recorded (Publishing page, Diagnostics, Home Assistant log), step-specific GitHub errors, and the token test proves write access with an unreferenced blob | `engine.py`, `server.py` |
| 0.3.7 | **Channel identity graph** (`identity.py`): private 36 h schedule fingerprints link the same channel across guides; +1/+2 detected; identity tokens (+1, plus/Sports+, numbers, regions incl. ROI/CI, languages) never merged; a review list for same-schedule/different-name pairs. Asset `identity` (`sli.identity/1`) | `identity.py`, `feed.py`, `schemas/sli-identity.schema.json` |
| 0.3.7 | **Provider naming conventions** in `normalized_name`; **keep-every-channel display labels** (`channel_variant`, `display_labels`: base name + tags such as "FHD · 50fps", with duplicates numbered) | `guide.py` |
| 0.3.8 | **UK and Europe channel dictionary** (`dictionary.py`) from the public-domain iptv-org database: about 10,264 channels and 12,958 feeds, region-expanded broadcast areas, daily conditional fetch, **opt-in** (`config.dictionary.iptvorg`). `Resolver` gives the reference lookup order (market countries, own country first, exact or no-spaces, decoration equality, broadcast area; ambiguous never applied). Asset `dictionary` (`sli.dictionary/1`) | `dictionary.py`, `storage.py`, `server.py`, `schemas/sli-dictionary.schema.json` |
| 0.3.8 | Provider **prefix grammar** (`|NO|`, `VIP RU |`, `C+PL|`, `ES TI|`, `[M+]`, `(VF)`, language tags), mis-encoding repair, export-junk removal, French "et" = "&", `market_key(name, market)` | `guide.py` |
| 0.3.8 | The standard `<!DOCTYPE tv SYSTEM "…xmltv.dtd">` is accepted from all sources (likely fixes the mjh Sky UK/NZ/Sydney and EPGShare NZ failures; **unverified**); specific guide failure reasons; 4 dead iptv-org-hosted guides retired | `providers.py`, `engine.py` |

**Docs:**
- `docs/FEED_CONTRACT_SLI_V1.md` §4.0–4.1 (reader rules for dictionary and identity);
- `docs/B1G_INTEGRATION_FEEDBACK_BACKLOG_2026-11-13.md`;
- `sportsliveinfo/CHANGELOG.md`.

## 3. Key measured findings

All measured on the owner's real lineup. The analysis is private: **no lineup data in any repo**.

**Lineup** (B1G workbook, 9 Nov cache): 27,084 entries in 204 categories.
- By kind: 22,477 linear, 3,231 event-slot, 771 24/7, 503 adult, 102 radio.
- Every channel appears in several quality copies.

**Name matching against real UK guides:**
- UK/IE linear: 25 % → 46 % with the new rules (49 % with a no-spaces fallback).
- UK sports were already strong through provider IDs: Sky 37/39, TNT 18/18, Premier 34/34.

**UK + Europe identity via the dictionary:** 37.9 % → **54.8 %** of 7,701 linear channels; 70/70 hand-checked matches correct. By country: France 61 %, Spain 59 %, Italy 72 %, Scandinavia 43 %, Poland 67 %, Netherlands 73 %, Germany 48 %, GB 53 %. GB is limited by music/FAST channels, not by matching.

**Identity graph on 3 real UK guides** (922 channels): 181 services, 402 guide channels, 59 timeshifts, no false merges after manual review.

**Display labels:** all 27,084 entries keep distinct labels.

**Home Assistant guide health** (13 Nov):
- 5 working UK guides, including iptv-epg GB (932 channels, TNT 1–10).
- 3 working FR guides: EPGShare FR (574), iptv-epg FR (485), xmltvfr (401).
- DE, IT, ES and NL guides work, but the registry recognised none of their channels before the dictionary.
- No catalogued guide for Scandinavia, TR, RU, AL, RO, BG, HU, CZ/SK, MENA.

**Owner-terminal inventory** (cache-only; see B1 review §4.12):
- Provider guide IDs: about 100 % for UK, sports and event slots; **0–2 % for most of Europe**.
- Only 39.7 % of provider IDs exist in the provider's own XMLTV, and they barely overlap public guides.
- The provider XMLTV has title and description only.
- The B1G FFI drops `series_id`, `episode_num`, `episode_system` and `icon_url`. Only the first M3U `url-tvg` is used, and `get_simple_data_table` is unused.

**Sports-to-channel matching** (this weekend's 172 top-priority 2-team fixtures vs 3 UK guides):
- Today's SportsLiveInfo matcher links **1**.
- **38** are present in the guides. They were lost because the guide channel is not in the 128-service registry (Wales v NZ, England v Japan on ITV1 regions and S4C), or because title matching is too strict.
- Naive loosening produces false positives (radio, shopping channels, generic words), so a careful matcher is needed.

**Feed shape:**
- 91 % of events are in `*.other` categories.
- Days 3–8 hold only 2–11 events (the API-Sports free plan).
- The largest day asset is 1.56 MB raw / 120 KB gzip.
- No broadcasts are published (`broadcast_candidates: not_published`).

## 4. Pending owner decisions

| ID | Decision | Recommendation |
|---|---|---|
| D1 | Ship the feed URL as the B1G default | Yes, editable |
| D2 | Show events with no local channel as information cards | Yes, for featured and top priorities |
| D3 | Stop per-TV API-Sports/Highlightly when the feed is on | Yes, after device QA |
| D4 | Bring back on-TV EPG mapping repair | No; review in Home Assistant instead |
| D5 | Publish provider-guide-derived broadcasts | Not initially |
| D6 | Feedback transport | LAN pull plus a file fallback |
| D7 | Approved household matches: public generic entries, or a private LAN endpoint | Public generic by default |
| **D8 (asked, unanswered)** | Publish **guide-listed, unverified** event → channel links (canonical channel ids + confidence, no programme text) from SportsLiveInfo's public-guide matching | Owner's call; otherwise keep them private |

## 5. Next work, in priority order

1. **SportsLiveInfo: stronger event → channel matcher.** **The owner APPROVED building and measuring it (13 Nov), then deciding D8.** Not started: Claude's usage ran out. This is the next task.
   - Distinctive team tokens and aliases; sport-family channel gating; exclude radio and shopping; women's/U21 markers.
   - Map every guide channel to a canonical id through registry + dictionary + identity graph, so matches are no longer discarded as "unmapped".
   - Group regional variants (all ITV1 regions → ITV1).
   - Measure on the weekend fixtures: today 1/38; estimate 25–30.
   - Publish only if D8 = yes.
2. **SportsLiveInfo small items:**
   - log success summaries (dictionary, identity, per-guide, collector) to the Home Assistant log, so remote verification works;
   - verify that the mjh/EPGShare NZ guides now import;
   - verify the next publish includes `identity` and `dictionary`.
3. **SportsLiveInfo producer backlog** (`docs/B1G_INTEGRATION_FEEDBACK_BACKLOG_2026-11-13.md`):
   - forward horizon (days 3–8 from round/season endpoints);
   - taxonomy coverage (reduce `*.other`);
   - a tiered `events-core` asset;
   - data quality (golf/snooker 00:00 → `date_only`, cricket names, missing `status_normalized`);
   - B1G feedback import (LAN pull and upload, with a review queue).
4. **B1G Android**, per the PR plan in the B1 review §7 (SLI-B1-00…08):
   - feed reader core (pure Kotlin, testable in the cloud);
   - `SportsEventLinker` (fixture-first rail, local guide join);
   - **event-slot name binder** (3,231 slot channels; names and titles carry fixtures);
   - dictionary/identity bridging for provider channels (the main route for Europe, and for UK channels whose provider ID has no rows);
   - port `normalized_name` / `market_key` / `channel_variant` with golden fixtures;
   - expose the dropped FFI fields; load all M3U `url-tvg` URLs;
   - **bug fixes:** `EpgSourceHealthStore` missing from `AccountDataPurge`; saving sports priorities doesn't refresh Sports Today; no 60 s live re-rank; "Australian rules football" can't be ordered.
5. **Owner-terminal follow-up:** count how many provider IDs equal iptv-org ids (B1 doc `OWNER_TERMINAL_TASK_XTREAM_FEED_INVENTORY_2026-11-13.md` §6); refresh the provider XMLTV horizon with the clock fixed.

## 6. Where the detail lives

**B1 branch `claude/sportsliveinfo-b1g-android-syyo8j`** (not on `main`):
- `docs/SPORTSLIVEINFO_B1G_INTEGRATION_REVIEW_2026-11-13.md`: the master design.
  - §0–3: rail.
  - §4: EPG; §4.8 identity; §4.9 display labels; §4.10 event slots; §4.11 dictionary; §4.12 inventory.
  - §5: feedback loop.
  - §7: PR plan.
  - §8: decisions.
- `docs/OWNER_TERMINAL_TASK_XTREAM_FEED_INVENTORY_2026-11-13.md`: the terminal task.
- The 12 Nov reader design and handover, with pointers to the above.

**SportsLiveInfo:** as in §2.

## 7. Binding rules (do not break)

- **Privacy:**
  - TVs are read-only. No credentials, stream URLs, lineups or hidden channels in any repo, feed or log.
  - The owner's lineup (xlsx) and inventory (zip) were analysed privately and **must never be committed**. Test fixtures use synthetic names.
- **Rights:**
  - No EPG programme text is published.
  - Sources are published only after an owner rights approval.
  - The dictionary is public domain; credit it with the attribution line.
- **Publishing behaviour:**
  - New sources are always **off by default**.
  - Ambiguous identities are never auto-applied.
  - Precision always comes before coverage.
- **Process:**
  - Report anything not run as **NOT RUN**.
  - Never claim a PR is merged without verifying it.
  - Back up Home Assistant before merging to SportsLiveInfo `main` (auto-update is on).
