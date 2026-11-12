# Subscription-driven, multi-region EPG enrichment — mandatory scope

> **Current documentation context — reviewed 12 November 2026.** Candidate multi-market collection is implemented, but real subscription-driven coverage/import and TV Guide integration remain unverified. Both general EPG and sports are required.
> **Repository roles:** [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is PRIVATE source/installation and stays private; [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is PUBLIC daily data only. [Current status and evidence](CURRENT_STATUS.md).

**Decision 12 November 2026.** The owner wishes to serve up to ten personal B1G televisions using a single **Home Assistant OS mini-PC** collector. The collector must prioritise (1) comprehensive corrected EPG for **UK and French channels**, (2) other countries/channels genuinely found in the user's configured subscriptions, and (3) accurate Sports Today cards showing event, competitors, time and real playable broadcaster. Movie/series TMDB/OMDb/poster/hero lookup remains **in B1G**, outside SportsLiveInfo.

**Status:** required inventory-driven architecture; the v0.3.0 collector already has candidate multi-market EPG/sports adapters and diagnostics. Safe inventory export/import, actual subscription coverage and B1G stream binding remain unverified; no actual subscription inventory was inspected in this documentation review.

## Objective and source-of-truth boundaries

1. **Subscription catalogue** (what channels exist for a specific B1G account) is authoritative for which *local streams* B1G can play. It is **not** the authoritative source of actual EPG programme content.
2. **Provider/source EPG**, plus **permitted third-party EPG** and **sporting fixtures**, supply listings/verification. Source licences govern storage, use, and redistribution; a public repository does not become lawful merely because the user has a subscription.
3. **SportsLiveInfo** builds canonical, region-specific schedules and event/broadcast evidence from lawful sources, fetched centrally. TVs never call the sporting provider APIs.
4. **B1G on each television** retains per-account playlist inventory, stream IDs/URLs and credentials, manual EPG overrides, hidden categories, opt-outs and channel-to-stream mapping. Neither these credentials nor playback URLs go to GitHub.
5. **Completeness must be measured against actual channel inventory**, not against a presumed count of all channels worldwide. A subscription may carry thousands of channels from many countries; don't fetch every possible global EPG speculatively.

## What B1G code already provides — confirmed by audit, not live runtime verification

Source repository: https://github.com/jimmyfazz/B1 (main branch reviewed 12 November 2026).

- Android `platforms/android/app/src/main/java/com/b1giptv/player/data/XtreamClient.kt`: `liveCategories()` (and `fetchLiveCategories()`) loads channel categories and `get_live_streams`; `channelFromStream` reads `stream_id`, `name`, `category_id`, `epg_channel_id`. Actual provider account content is available **only when locally configured and connected**, not recoverable from repo source code. M3U/Stalker paths have different data fidelity.
- `platforms/android/app/src/main/java/com/b1giptv/player/ui/SkyGuideScene.kt`: provider and user XMLTV sources followed by bounded backup EPG feeds and source/identity-sensitive matching. Existing source entries:
  - UK: `https://epgshare01.online/epgshare01/epg_ripper_UK1.xml.gz`; `https://i.mjh.nz/SkyUK/epg.xml.gz`; `https://iptv-org.github.io/epg/guides/uk/sky.com.epg.xml.gz`.
  - France: `https://iptv-org.github.io/epg/guides/fr/programme-tv.net.epg.xml.gz`, `https://iptv-org.github.io/epg/guides/fr/telerama.fr.epg.xml.gz`, `https://xmltvfr.fr/xmltv/xmltv_fr.xml.gz`; `https://iptv-epg.org/files/epg-fr.xml.gz` is explicitly user-selected-only because programme data terms are not clear.
  - Sports-specific UK: `https://raw.githubusercontent.com/farleyflex/epg-guide/main/epg.xml` is manually enabled as “Sky / TNT / Premier Sports” by `fixSportsEpgNow()`.
  - US, Australia and other region feeds are also declared; don't claim French/foreign rights or coverage purely because URLs are listed.
- Android `EpgResolver.kt`, `EpgSourcePrecedencePolicy.kt`, `EpgScheduleMerger.kt` are account-aware; earlier source whole intervals are usually preserved, later ones fill genuine gaps. **Generic primary sports programme titles can block richer detailed schedules**, requiring an explicit verified enrichment/replace decision, not just adding another backup feed.
- Android `SkyHomeScene.kt` and `HomeSportsEvents.kt` scan EPG and match schedule-only events to playable channels; `SportsFixtures.kt` fetches API-Sports football schedules only when explicitly enabled with a per-device key, with 30-minute response cache. Move shared fixture fetch to HAOS; keep final stream/channel binding local.
- Mac `B1G-IPTV-Web/src/lib/epg/sports-epg-setup.ts` and `sports-epg-aliases.ts` match known Sky/TNT/Premier names; no blanket promise of support for Sky Sports+ and timeshift. `farleyflex/epg-guide` itself includes further TNT and Sky Sports+ IDs, but current B1G alias mapping intentionally excludes unsupported/ambiguous variants.
- **VOD APIs** are optional and separate: Android `CredentialsStore.kt` / `SettingsScene.kt` expose API-Sports, TMDB and OMDb credentials; title-specific imagery/metadata is locally cached. Do not migrate TMDB/OMDb to HAOS.
- Some providers supply encrypted/credential-bearing M3U stream URLs. `PlaylistClient.kt` already keeps stream URLs in an encrypted per-account index. Never export this index.

## Proposed canonical subscription-channel inventory

Codex should build an explicit, owner-initiated **sanitised channel-inventory export** from a running B1G installation or locally authenticated provider context. The GitHub repository alone cannot reveal the actual subscribed channels. Export from **all configured accounts/playlists**, not just current account, with opt-in and user review.

**Safe fields (example):**

    {
      "schema_version": "channel_inventory_v1",
      "created_at": "2026-11-12T09:00:00Z",
      "installation_label": "living-room-tv",
      "accounts": [{
        "account_alias": "local-a1",
        "channels": [{
          "inventory_id": "local-c1",
          "display_name": "France 2 HD",
          "tvg_id": "France2.fr",
          "group_name": "France",
          "declared_country": "FR",
          "declared_language": "fr",
          "visible": true,
          "playable": true
        }]
      }]
    }

Fictional example, **not a real inventory**. Use salted/ephemeral account aliases and local channel opaque IDs, not raw provider stream IDs; keep a stable local crosswalk only on each device. Do not export playlist URLs, Xtream host, usernames, passwords, access tokens, MAC/serial, stream URLs, playback data, private account names or any authenticated EPG link embedding secrets. Avoid exporting user behaviour/history. Avoid uploading full subscription inventories to **public** GitHub. Inventory is a sensitive personal asset: keep on local owner machine or private restricted upload, with explicit opt-in, retention and delete command.

For discovery, prefer a **summary-first inventory**: per country, language, channel names/EPG IDs, category, duplicates and counts. Then optionally provide the restricted full safe manifest to the local HAOS collector if required. No new B1G provider credential is needed on HAOS if inventory is transferred locally by the owner; inventory from a single subscription may differ across TVs or accounts.

## Coverage discovery, grouping and prioritisation

1. Determine effective *visible* channels for each account, including secondary playlists, manually hidden/suppressed channels and duplicate SD/HD/UHD variants. Coverage report may count all channels but collection should prioritise **visible, playable, actively selected channels**, preserving per-account hidden settings locally.
2. Infer country/language conservatively from explicit tags, groups and EPG IDs; `FR:`, `UK:`, `CANAL+`, `beIN`, `RMC` are hints, not absolute proof of region or entitlement. Mark uncertain region/language `unknown`, request owner review.
3. Build a **coverage matrix by region** with source URL, provider/source licence, source refresh time, channel count, programme interval availability, identifier/name match rate, first seven days' gaps and channel-match confidence.
4. Prioritise UK Sky/TNT/Premier plus French national, regional, premium/sports and general-entertainment channels found in inventory. Add EU, North America, Australia etc. **only where actual B1G inventory warrants** it and a permitted, reliable source exists.
5. Channel aliases must be exact ID first; then curated broadcaster names/language variants; then unique strict-name fallback. Never map similarly named channels or wrong-country editions automatically. Distinguish CANAL+ channels/tiers, beIN channels, RMC channels, timeshift, +1, SD/HD/UHD, and regional feeds.
6. Maintain an owner-editable **unmatched channel list**; per-account overrides and opt-outs on TV always take precedence over central suggestions. Record mapping rule, confidence and provenance.
7. EPG coverage should be budgeted: **collect only required source guides**; source fetch is once per day/revision (or licence-permitted interval), not once per TV. Use ETag/Last-Modified where supported, bounded compressed/decompressed size, streaming XML parser and cache; avoid parsing many enormous sources concurrently on HAOS.
8. Broad EPG coverage and Sports Today serve different outputs. Do not let one long French EPG job delay the 05:00 B1G sports cards or interfere with Home Assistant automations.

## Event/EPG precedence and enhanced correction policy

- **Never blanket-overwrite a provider EPG just because a third-party guide is detailed.** Match channel identity first and compare exact programme interval/time/actual sport evidence, with source confidence and provenance.
- Correction types: `add_missing`, `enrich_generic_title`, `verified_time_correction`, `preserve_provider`, `conflict_review`; track before/after and why. Matching two teams to a real fixture and matching programme/channel are mandatory for automatic sports corrections.
- For generic slots (e.g. `Live Premier League`) with a corroborated specific event (e.g. `Team A v Team B`) on the **same broadcaster**, enrich title/subtitle if transmission is verified and intervals are consistent. Otherwise leave generic title and flag missing evidence.
- For other categories (French general TV), replacement rules must be stricter: exact source/channel match, local time coherence, programme title and duration; ambiguity stays unresolved, especially during overlapping shows.
- Persist UTC dates, retain source timezone including `Europe/Paris` (CET/CEST) and `Europe/London` (GMT/BST); display in device/user locale. Preserve Unicode accents and original-language title/description. Do not use machine translation or LLM by default.
- Keep simultaneous and alternate broadcasts; do not confuse UK broadcast rights with availability on a *French* channel or vice versa.
- French sports coverage can include Canal+, beIN Sports and RMC Sport if channels are actually in subscriptions and licensed EPG evidence exists; no assumed rights or automatic channel mapping.
- Support EPG-only fixtures and sport rails even without a playable stream; label `not available in current playlist`, not `watch`.
- Keep coverage and sporting event status separate. EPG programme airing now does not prove match live if delayed/highlights.

## Publication format: don't push entire licensed EPG indiscriminately

For ten TVs, publish **small, versioned, rights-cleared manifests** rather than one massive schedule containing all global channels.

    manifest.json
    sports/today.json
    sports/next-7-days.json
    epg/uk/index.json
    epg/fr/index.json
    epg/{region}/{date-or-segment}.json.gz
    health/coverage.json

Only include country/channel subsets that have publication rights. If public redistribution is not permitted, **do not upload that guide or derived restricted metadata** to public GitHub. Alternatives: keep matching on B1G using the user-authorised local EPG, or obtain express permission / identify a legitimate private-delivery mechanism. A GitHub public repository is not access-controlled merely because its URL is obscure.

Each EPG segment: schema_version, generated_at, source_observed_at, applicable_date/local timezone, source/freshness/rights tags, canonical channel-id, source identities, programmes[] with UTC start/end, title, subtitle, description, category, verified correction type, and conflict/incomplete states. **Never export stream IDs/URLs, account aliases or credentials.**

Client behaviour: B1G fetches region manifests/as-needed channel segments, caches last-good and fetches selectively. Playback/Guide/Sports UI must never block on network; account/playlist changes rebind locally with existing account-scoped `EpgResolver`. Explicit per-TV local EPG fallback remains available.

## Scheduling and freshness

- Morning snapshot available for B1G checks around **05:00 UK**, sourced from the latest already validated nightly data.
- The farleyflex EPG upstream GitHub workflow is scheduled for **06:00 UTC**, with recent uploads occurring later; use GitHub commit/API validator and check whether a **newer valid source revision exists** before updating UK guide after ~07:00 UK in winter / ~08:00 UK in summer. Do NOT treat its 06:00 job as a guarantee of delivery.
- French sources may refresh on different schedules. Per-source version, `last_checked`, `last_success`, `programme_window`, `source_latency` and stale flag are mandatory.
- Refresh changes at sensible bounded windows; source fetch never scales with number of TVs. Respect limits/terms and rate-limit all 429/timeout retries.
- On source failure keep last-good snapshot and show Home Assistant health/error, not empty day/channel schedules.

## Acceptance criteria

- [ ] B1G local channel catalogue export is **explicit opt-in**, contains no provider credentials/stream URLs, handles all configured accounts and duplicate/missing EPG IDs.
- [ ] French FTA and premium channels (where actually found and licensed) included in region coverage matrix; UK Sky/TNT/Premier retain priority.
- [ ] Source coverage metrics split into **country, account (local/private only), visible channels, EPG-id matched, programme rows present, gaps, unmatched, stale/conflicting**.
- [ ] Unexpected or unknown countries create suggestions rather than automatically downloading unbounded global EPG.
- [ ] Primary generic sport EPG slot may be corrected only by verified same-channel sport programme; no replacement by unrelated or wrong regional sports coverage.
- [ ] Existing B1G account-scoped manual mapping/hidden-channel policies unchanged; any central source outage falls back smoothly.
- [ ] Partial 05:00 Sports Today payload available even when large multi-country EPG processing is incomplete.
- [ ] Clear rights gate prevents republishing French/UK/non-UK EPG programmes on public GitHub without permission.
- [ ] No TMDB/OMDb/movie/series artwork API in HAOS app or central sports publisher.
- [ ] 10 concurrent TVs use cached feed with zero incremental sporting API/EPG source requests.
