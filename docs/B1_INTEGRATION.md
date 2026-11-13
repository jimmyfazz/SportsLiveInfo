# Required B1G Android read-only integration

> **Current documentation context — reviewed 12 November 2026.** Experimental v0.3.0 source is present. Current source/test evidence and open deployment gates are centralized in CURRENT_STATUS; historical version receipts elsewhere are not current pass claims.
> **Repository roles:** [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is PRIVATE source/installation and stays private; [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is PUBLIC daily data only. [Current status and evidence](CURRENT_STATUS.md).

This repository remains **independent** from the B1 application. B1G integration is a mandatory delivery target for both international EPG and sports events; device acceptance remains outstanding. Do not modify B1 until the standalone aggregator works and can be tested against live permitted inputs.

## Verified B1 code audit and integration scope (12 November 2026)

Full source-based specification: **[B1 forensic EPG, Sports Today and API inventory](B1_FORENSIC_EPG_SPORTS_API_SCOPE_AUDIT_2026-11-12.md)**.

B1's enhanced UK sport EPG source is farleyflex XMLTV, not API-Sports. API-Sports independently verifies football fixtures; TheSportsDB is a separately cached public-key team crest/standings dependency. Android Settings has API-Sports, TMDB and OMDb credential inputs. **Centralise only sport-fixture providers and, where authorised, common international full-channel EPG information, with UK/France priority.** TMDB/OMDb, VOD posters and hero art remain local B1G. Xtream/M3U/Stalker passwords and user-provider XMLTV URLs never go to the central feed.

The user has prioritised **accurate detailed UK sporting TV EPG programmes AND the correct B1G Sports Today playable channel**. Implement a two-product, separately licensed feed: versioned daily events, plus licensed verified programme correction deltas (or no public delta if rights absent). Treat existing B1 provider EPG as a safe independent fallback. Source mapping is keyed by provider/service identity, not literal URL. Do not append a lower-priority source and assume generic programmes will be upgraded; use validated same-channel/same-interval quality promotion, retaining explicit local user selections and source provenance.

**Critical Android parity issues for B1 team:** partial API-Sports response can incorrectly remove football cards, team-pair matching is too weak, programme-in-progress is not proof of sport-live, and Android includes optional PPV card inside 10 while Mac allows 10 body + PPV headline 11. These are audit findings requiring separate tests/implementation.

## Read-only shared feed, local per-TV visibility

**Mandatory:** [B1G read-only and inventory policy](B1G_READ_ONLY_FEED_AND_INVENTORY_POLICY.md). Every B1G device only reads public, licence-cleared sports/EPG JSON. The HAOS App alone holds any publishing credential. **Never build automatic GitHub writes from B1G.** The central feed can include a superset of channels; each TV applies its current account's `ChannelVisibilityStore.visibleLiveCategoriesForAccount` (hidden live categories and hidden live channels) and its `EpgResolver` manual mappings before rendering guide rows or playable Sports Today cards. Other TVs may have different hidden states. Any actual lineup discovery is an optional owner-triggered safe export and HAOS import, not a normal TV request.

## Required shared broadcaster-ID registry and two-stage B1G mapping

See [canonical channel identity and EPG allocation specification](CHANNEL_IDENTITY_AND_EPG_ALLOCATION_SPEC.md). The current builder can export canonical channel IDs, source crosswalks and guide metadata. Verified programme/fixture-to-channel evidence remains incomplete; no public programme rows are exported. The required B1G integration must consume only rights-approved metadata and independently verified links. B1G's current account-scoped `streamId` mapping remains local. The local matcher must prioritise explicit user mapping, validated exact provider ID, source-aware curated aliases, strict unique-name matching, and only then conservative fuzzy **suggestions**, with hard negative variant/country/region checks. Show unmatched candidates for manual resolution; never silently choose a wrong stream. Preserves `ChannelVisibilityStore.visibleLiveCategoriesForAccount`, `EpgChannelMappingStore` source binding and auto-suppression, and no TV GitHub write/API keys. Current hardcoded farleyflex source URL alias rules must be explicitly migrated to safe canonical `source_id` identity, not blindly applied to all feed URLs.

## Proposed sports rail

A "Live Sport Today" / "Upcoming Sport" rail where cards present sport icon, competition, teams/fighters/session and country, start in Europe/London, broadcaster and verified/unverified TV status. A card may show "UK channel not confirmed" rather than guessing.

## Distinct mapping layers

1. Fixture data: this service's canonical event ID.
2. UK broadcast metadata: verified UK broadcaster name/channel ID/EPG service and coverage start.
3. B1 user-specific source: B1's already configured playlist channels, account entitlements and local EPG source/provenance.
4. Resolve (2) -> (3) through B1's existing improved universal channel matching and channel alias table, with clear unresolved state.

Never return or synthesise stream URLs, unlicensed IPTV links, or broadcaster credentials. An external provider's claim of TNT/Sky/DAZN does not mean that user's playlist contains it.

## Performance / UX constraints

- Load rail from a small cached JSON snapshot; no remote sports API request on Android Home layout/navigation.
- Keep one full rail visible below hero where B1 design requires; don't couple sport polling to D-pad movement.
- Use existing focus treatment and channel navigation so one D-pad press advances exactly one rail as required by B1.
- Programme status/TV may change; apply non-blocking background refresh only after a usable snapshot exists.
- Match results/status require source freshness; do not mislabel "live now" from time alone.

## Tests before merge into B1

Mocked JSON load, empty sports day, unknown channels, multiple channels, postponed match, BST conversion, offline cache, provider down, hidden category/channel visibility constraints, account switching, EPG origin consistency and channel playback/navigation regression.
