# Universal channel identity, source-aware EPG allocation and safe local B1G binding

> **Current documentation context — reviewed 12 November 2026.** Partial service tables, source crosswalk and matching fixtures exist. A complete independently verified identity catalogue and account-local Android binding remain acceptance work.
> **Repository roles:** [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is the public App source and installation repository; [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is PUBLIC daily data only. [Current status and evidence](CURRENT_STATUS.md).

**Decision/specification date:** 12 November 2026  
**Owner requirement:** Enhance UK, French and subscription-driven multi-country EPG and Sports Today accuracy for ten B1G televisions. **SportsLiveInfo maintains shared canonical broadcaster/EPG intelligence. B1G alone maps to each device's actual playable IPTV channels**, while honouring hidden channels, local manual overrides and account state. TV devices are strictly **read-only** clients of the centrally published rights-cleared feed.

**Implementation status:** partial central implementation in `guide.py`, `feed.py` and synthetic matching fixtures: service tables, source crosswalk, normalization and diagnostic families exist. Complete identity/evidence acceptance and SportsLiveInfo-to-B1G device integration remain unverified. Baseline source read in B1G: `EpgResolver.kt`, `EpgChannelNameIndex.kt`, `EpgChannelMatcher.kt`, `BroadcasterEpgAliases.kt`, `EpgChannelMappingStore.kt`, `EpgScheduleMerger.kt`, `ChannelVisibilityStore.kt`, `ManualEpgSourcePolicy.kt`, Android Home Sports Today and macOS parity code. These findings must be rechecked against HEAD before edits.

## 1. Three mappings — do not conflate them

A. **Broadcast service identity:** UK Sky Sports Main Event is a specific channel/service, distinct from Sky Sports News, Sky Sports+, Sky Sports Premier League, a timeshift, or a non-UK variant. Resolve globally via a SportsLiveInfo `canonical_channel_id` and `broadcast_service_variant` model.

B. **EPG source identity:** Different legal EPGs may publish different identifiers and programme titles for the *same* service. SportsLiveInfo maintains per-source crosswalk: `(source_id, epg_channel_id) -> canonical_channel_id` with evidence and source licence state. Never treat an EPG ID as globally unique absent a defined namespace.

C. **Device/subscription identity:** Each B1G account/playlist has a local `streamId`, name, optional provider EPG ID, visibility settings and user override. B1G resolves `(account_scope, stream_id) -> canonical_channel_id` using the signed/versioned shared alias catalogue **without uploading that identity to GitHub**. A broadcaster-to-IPTV-stream match does NOT establish that a particular sporting event is actually live on that channel: a fourth event-specific `(event, broadcast programme, canonical channel, time)` relationship must be verified.

## 2. Definitive ownership split

| Task | Owner | Reason |
|---|---|---|
| Common canonical service names, country/region, language, variants, safe aliases | SportsLiveInfo | Maintain once, serve all TVs |
| Crosswalk from EPG source IDs to canonical service, with provenance/confidence/licence | SportsLiveInfo | Avoid hard-coded farleyflex URL-only mappings |
| Consolidate programme lineups, sport fixture calendars and independently verify live programme vs highlights/replays | SportsLiveInfo | Source-rich research done once |
| Parse current account/provider playlist, know streamId and visibility/hidden settings | B1G | Per-device private data |
| Resolve stream to canonical service using local identifiers and shared signed/versioned registry | B1G | No TV upstream credentials or uploads |
| Cache effective account-scoped mapping, render channel Guide and Sports Today, handle focus and stream playback | B1G | Must respect local user controls |
| Manual corrections of ambiguous mappings and an "unmatched channels" inspector | B1G | User-only corrections are local until explicitly exported by owner |
| Publish permitted JSON snapshots to GitHub using a token | SportsLiveInfo HAOS App only | TVs remain strictly read-only |

## 3. Existing B1G capability and exact gaps

### Present today

- `EpgResolver.match` ranks explicit user mapping, provider `epgChannelId` exact (trim/case), source-bound curated alias, generic unique name matching. The resolver's source binding respects the user's choice even if a previously mapped ID disappears. An automatically suppressed mapping disables new curated/generic matches, not provider-native exact IDs.
- `EpgChannelNameIndex` builds an index keyed by exact normalised names and token, preventing N×M rescans on large playlists. It removes picture-quality decorations, handles prefixes (UK/FR etc.), accent decomposition, BBC 1/BBC One forms and partial typo/fuzzy matching. Fuzzy needs equal non-generic token count, Jaccard >=0.65 and runner-up separation >=0.15, with specific guardrails for +/timeshift/region variants.
- `BroadcasterEpgAliases` supports 17 curated UK Sky/TNT/Premier mappings **only when the EPG source URL equals farleyflex/epg-guide** and target ID exists. This hardcoded URL/source coupling will not automatically extend to a SportsLiveInfo feed.
- `EpgChannelMappingStore` provides account-scoped explicit manual mappings, source associations and suppression. `ChannelVisibilityStore.visibleLiveCategoriesForAccount` projects category/channel hidden states and user custom names/numbers/orders locally.
- `EpgScheduleMerger` generally protects accepted whole intervals; it promotes a detailed title over a generic one only for strictly identical start/stop intervals with other conditions. Cross-source arrival order can preserve a generic slot where the verified detailed source has different coverage start.

### Gaps to address

1. Curated aliases are one supplier's `tvg-id` crosswalk, not a global broadcaster identity system.
2. Local provider EPG ID can be absent, reused for wrong services or assigned ambiguously. Do not treat the ID alone as infallible.
3. Numeric similarity alone cannot solve `SS ME`, `S Sport Event`, `CANAL+ SPORT`, `beIN SPORTS 1`, `BBC One Scotland`, local-language/abbreviated variants, service numbers, locale or confusing provider prefixes.
4. Need source-specific recognition for UK, France and dynamically discovered subscription countries; no hardcoded assumptions that only UK services exist.
5. Need transparent candidate evidence and refusal/confirmation mode, separate from evidence that an event is on that broadcaster.
6. Generic EPG may be incorrectly retained even where an independently verified, richer sports programme is available, if intervals differ. Do not blanket-overwrite or splice programme rows.
7. No automatic public-TV-to-GitHub feedback loop is permitted. Manual owner import of a sanitised inventory is the only optional update path.

## 4. SportsLiveInfo canonical registry schema (proposed, not existing)

Canonical service record (example contains **invented IDs and aliases for design only**, not verified providers or rights):

    {
      "schema_version": "channel_registry_v1",
      "revision": "sha256:...",
      "channels": [{
        "id": "gb.sky.sports.main_event",
        "display_name": "Sky Sports Main Event",
        "country": "GB",
        "distribution_region": "GB",
        "language": "en",
        "service_group": "Sky Sports",
        "service_kind": "linear",
        "service_variant": "main_event",
        "timeshift_minutes": 0,
        "parent_service_id": null,
        "names": [
          {"text":"Sky Sports Main Event","kind":"official","status":"verified"},
          {"text":"UK Sky Sports Main Event HD","kind":"provider_pattern","status":"verified"},
          {"text":"SS ME","kind":"candidate","status":"unverified"}
        ],
        "epg_crosswalk": [
          {"source_id":"farleyflex_epg","epg_channel_id":"skysportsmainevent.uk","confidence":"verified","last_checked":null}
        ],
        "restrictions": {"automatic_match_requires": ["unique_identity", "region_consistency", "variant_consistency"]},
        "provenance": []
      }]
    }

Do not publish unverified example aliases as authoritative. A canonical channel is **the service**, not each physical SD/HD picture-quality feed when its schedule is identical; model 4K/UHD as a separate variant if programmes/rights/local schedule differ. A `+1` time-shift is not the same schedule: different service or explicit `timeshift_minutes` with correct adjusted times. Never conflate a dedicated match channel with a multiplex/whip-around feed. Store regional BBC variants distinctly whenever programme differences exist.

Names/aliases include provenance, approved mode (`exact`, `curated`, `suggestion_only`, `blocked`), positive/negative examples, first/last verification and version. Support UTF-8 accents and Unicode normalisation (France, other territories). Keep the registry small, deterministic, independently distributable and versioned.

EPG channel crosswalk keys are **(source_id, source_epg_channel_id)**. The same raw ID in a different supplier may denote a different channel. Source ID must be stable and not literally dependent on one file-host URL.

## 5. B1G deterministic matching pipeline — mandatory decision tree

For each **visible** IPTV channel in its current account (the local user-specified display name must not erase original `providerName`):

**Step 0 — account and user policy.** Capture account scope and catalogue generation; apply `ChannelVisibilityStore.visibleLiveCategoriesForAccount`. If channel or parent category hidden -> do not render a matching card/Guide row. Preserve local manual source choice/suppression. A source-bound manual selection wins and may remain unmatched if no longer present.

**Step 1 — exact provider ID with provenance.** Check the provider `tvg-id`/EPG ID against the shared registry's **source-namespace crosswalks** or existing provider-native guide (not indiscriminate cross-source matching). Confirm region, service variant and uniqueness before auto-binding. Detect reused/generic/wrong IDs. Retain the original guide's ID as separate from central ID.

**Step 2 — trusted curated alias.** Match full broadcaster name, verified abbreviations, source names, channel number and country/language hints, all with explicit negative patterns. Alias such as `SS` alone is not adequate for auto-mapping. Preserve meaningful tokens: `Sports+`, `+1`, `France`, `Scotland`, `World`, `Arena`, `Premier League`, `F1`, `Main Event`, `Canal+`, `beIN 1/2` and `RMC Sport 1/2`.

**Step 3 — strict normalised-name exact match.** Normalise quality tags (HD/FHD/4K/HEVC), spacing, accents, punctuation, number-word differences and country prefixes. But never strip identity tokens. Require unique identity; preserve a regional service if name says it is regional.

**Step 4 — constrained fuzzy suggestion.** Use existing token index with boosted evidence for trustworthy exact identifiers and verified region. Reject or suggest-only if conflicting strong fields. Use calibrated thresholds, not a global magic number: keep current conservative >=0.65 / >=0.15 margin as baseline until real inventory labelled benchmark supports any change. Matching `SS MAIN EVENT` via a curator's verified alias can be safe; fuzzy `SPORT EVENT` cannot.

**Step 5 — programme compatibility as sanity check, not circular proof.** Compare programme schedules/source language, time windows and verified sport fixtures to detect contradictions or wrong-country listings. A false identity should fail. Agreement in generic words or overlap alone does not prove identity; don't auto-resolve using a single coincidence.

**Step 6 — confidence-based decision.**
- `verified`: explicit source-bound user override or a unique, compatible stable source/channel ID with no contradiction; may auto-map.
- `high`: unique confirmed curated alias or well-evidenced ID+name, all hard gates passed; may auto-map based on measured precision.
- `review`: ambiguous abbreviations, mismatched region or multiple plausible services; offer UI candidates but **do not auto-retune**.
- `unmatched`: no unique candidate or hard negative evidence; keep prior suitable provider EPG and show diagnostic, never guess.

**Step 7 — cache/migration.** Cache `(account_scope, stream_id, playlist_revision, registry_revision, source_catalogue_revision)` -> canonical identity + confidence + evidence. Invalidate/reconcile when playlist changes, account switches, registry/source changes, or manual override. No animation/per-card network fetch and no all-pairs quadratic scanning. Published updates must not silently override a local confirmed mapping.

### Explicit blockers

- Regional BBC One Scotland vs BBC One national; France 2 vs Francophone international/Canadian editions.
- Sky Sports News vs Sky News; Sky Sports Main Event vs Sky Sports Premier League; Sky Sports+ vs Sky Sports standard; individual Sky/TNT numbered variants.
- CANAL+ Sport vs CANAL+ Sport 360 vs CANAL+ main, beIN SPORTS 1 vs 2 vs 3, RMC Sport 1 vs 2; France vs Belgium/Swiss/Canada variants.
- `+1`/time-shift always requires a different EPG window, not merely the standard programme row.
- UK rights vs French rights: same event may show on different channels, but broadcast identity must be verified for requested territory/edition.
- `HD`/SD may share schedule only where service identity actually identical; 4K event-only feed may differ in schedule.
- Playlist aggregator/whip-around channel serving multiple concurrent fixtures must not be automatically treated as dedicated match stream.

## 6. Separate event-to-TV channel verification

After identifying a channel, verify **what the broadcaster is actually showing**:

1. SportsLiveInfo has an event from independent sporting schedule, with UTC kick-off, sport, teams/session and venue.
2. An authorised UK/FR/other region EPG or official event listing identifies an actual programme on a **particular canonical broadcaster**.
3. Link `event -> programme -> canonical channel` only where both identity and time overlap/coverage evidence are sufficient. Distinguish live, highlights, replay, preview, delayed, PPV main card/undercard and uncertain tennis starts.
4. Publish sporting-event/broadcast claims as verified, provisional or unknown, and source-specific effective dates; never derive `actual live on Channel X` solely from seasonal broadcasting rights.
5. B1G maps verified broadcaster to **local channel(s)** and selects a playable stream only if visible and actually present. More than one mapped HD/SD channel may be available; prefer user's existing stream preference, quality and account policy, never a guessed stream.
6. Do not label a sporting event `Live now` just because a coverage programme started; verify sporting live status separately or label `Live coverage`.

## 7. EPG programme-quality reconciliation

- Never alter the underlying provider EPG stream or manual source mapping globally; assemble a **display-time enriched view** from source evidence and account scope.
- Allow `generic -> specific title/subtitle` when **same canonical service, same sporting event, same plausible broadcast time window**, and a verified detailed programme exists. The coverage start can precede kick-off; intervals need not be identical, but require strong programme/broadcast alignment and no conflicting event.
- Preserve broadcaster start/end unless the alternative broadcast window is demonstrably more accurate. Never naïvely take `min(start)`/`max(end)` across inconsistent feeds or splice a show.
- Correct timezone before comparison (GB GMT/BST and FR CET/CEST), support multi-day cricket and event/PPV sessions. Keep original programme metadata in provenance and offer reversible override/source preference.
- Keep provider complete interval if central source stale, not licensed, unverified or contradictory; fill genuine gaps conservatively.
- To avoid regression, implement as a **separate quality-scored overlay** tested against the present `EpgScheduleMerger` before modifying its general precedence semantics.

## 8. Privacy, distribution and cost

- B1G devices always **read-only**, no GitHub write token, no fixture-provider keys, no inventory upload on every change. A central `channel_registry.json` can be loaded once/day or on revision; an `events.json`/per-region EPG segment loaded as needed. Ten TVs do not multiply provider calls.
- Source-derived EPG programme content may not be redistributable just because the raw XMLTV is public. The public GitHub feed must enforce a **field-level licence gate**. Alias facts/canonical identities are not a blanket exemption for copying copyrighted descriptions or restricted dataset crosswalks.
- Owner may manually and safely import a sanitised inventory into Home Assistant for coverage planning. No live personal account/channel data committed to public GitHub.
- Prefer sparse precompiled alias indexes and indexed token lookup for 27k–50k channel catalogues. The Home screen and player remain independent of fresh network requests.
- Keys/TMDB/OMDb/artwork remain separate (TMDB/OMDb on B1G) as decided.

## 9. Developer implementation sequence

P0: Add canonical IDs and versioned source-specific crosswalk/alias registry in SportsLiveInfo. Cover common UK and French broadcasters with verified aliases and **negative test examples**. Preserve other regions as modular.
P0: Implement reusable **Kotlin matching core** in B1G consuming registry JSON: manual override, exact ID, curated alias, strict normalised name, constrained fuzzy candidates, evidence/confidence, strict variant/country gates.
P0: Keep `EpgResolver` and `EpgChannelMappingStore` account/source/user precedences; adapt the hard-coded farleyflex URL identity to stable source IDs/catalogue verification instead of applying aliases to every arbitrary feed.
P0: Build a `Channel mapping diagnostics` view in B1G Settings showing `Matched (manual/exact/alias)`, `Needs review`, `No suitable EPG` for visible current-account channels. Show selected EPG source, candidate aliases and reason. User-confirmed mapping remains local.
P1: Add event-to-programme broadcaster evidence and quality-scored generic-to-specific programme overlay; verify no wrong channel, repeated/highlights or interval regressions.
P1: Batch source matching and cache per account/catalogue/registry revisions; tests for 50k channels and ten simultaneous read-only consumers.
P2: Optional owner-triggered safe inventory export, HAOS import, provider coverage matrix; no automatic device feedback, no per-TV endpoint.
P2: Tune fuzzy thresholds **only after a labelled real inventory accuracy benchmark**. Never trade mapping precision for nominal coverage.

## 10. Release acceptance matrix

- [ ] B1G Android names `UK: BBC 1 FHD`, `BBC One`, `BBCOne.uk` map to same canonical **national** service where IDs/source consistent.
- [ ] `BBC One Scotland` and national BBC One never collapse; `France 2` and Canadian `TV5` remain separate identities.
- [ ] `UK | SKY SPORTS MAIN EVENT 4K` resolves to Main Event only if variant/service/EPG catalogue constraints pass; `Sky Sports News` never becomes `Sky News`.
- [ ] `Sky Sports+` never falls back to standard Sky Sports; `BBC One +1` must keep timeshift, and numbered TNT variants remain distinct.
- [ ] `FR CANAL+ SPORT HD` maps only to exact permitted Canal+ Sport service, not Canal+ Sport 360/main; `beIN SPORTS 1` never becomes beIN 2.
- [ ] No false match on a known wrong/reused provider tvg ID; source-specific namespace compatibility enforced.
- [ ] Source-bound user manual choice remains authoritative; user suppression prevents new automatic alias assignment; account switch invalidates cache.
- [ ] Hidden live category/channel never appears as a playable central sports card even if included in shared feed.
- [ ] Generic programme title upgraded only on independently verified same-service event; conflicting programme stays original; stale central feed never erases provider schedule.
- [ ] Sport event on Sky Main Event not assumed from football league rights; independently verify broadcaster/programme; highlights and PPV correctly classified.
- [ ] Under 50,000 playlist channels, resolution is indexed/batched and Home/D-pad/player do not block; define real-device timing threshold via profiling.
- [ ] Two B1G devices with different subscription lineups/mappings independently resolve same shared registry and EPG, with **zero GitHub write calls and no extra upstream sporting API calls**.
- [ ] Compute accuracy over a manually labelled, realistic multi-country corpus; require **zero wrong-channel automatic matches in hard-negative tests**, with a **proposed** >=99.5% auto-map precision target on the held-out benchmark and documented abstention rate. This target is aspirational, not achieved.
- [ ] Source licensing checked before any public JSON programme content export; no passwords or subscription URLs enter public or private builds.

## Source paths inspected

- https://github.com/jimmyfazz/B1/blob/main/platforms/android/app/src/main/java/com/b1giptv/player/ui/EpgResolver.kt
- https://github.com/jimmyfazz/B1/blob/main/platforms/android/app/src/main/java/com/b1giptv/player/ui/EpgChannelNameIndex.kt
- https://github.com/jimmyfazz/B1/blob/main/platforms/android/app/src/main/java/com/b1giptv/player/ui/BroadcasterEpgAliases.kt
- https://github.com/jimmyfazz/B1/blob/main/platforms/android/app/src/main/java/com/b1giptv/player/data/EpgChannelMappingStore.kt
- https://github.com/jimmyfazz/B1/blob/main/platforms/android/app/src/main/java/com/b1giptv/player/data/ChannelVisibilityStore.kt
- https://github.com/jimmyfazz/B1/blob/main/platforms/android/app/src/main/java/com/b1giptv/player/ui/EpgScheduleMerger.kt
- https://github.com/jimmyfazz/B1/blob/main/platforms/android/app/src/main/java/com/b1giptv/player/ui/EpgChannelMatcher.kt
