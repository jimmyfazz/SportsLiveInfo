# Potential B1 Android IPTV integration (optional future phase)

This repository remains **independent** from the B1 application. B1 is one potential consumer of authorised sports information. Do not modify B1 until the standalone aggregator works and can be tested against live permitted inputs.

## Verified B1 code audit and integration scope (12 November 2026)

Full source-based specification: **[B1 forensic EPG, Sports Today and API inventory](B1_FORENSIC_EPG_SPORTS_API_SCOPE_AUDIT_2026-11-12.md)**.

B1's enhanced UK sport EPG source is farleyflex XMLTV, not API-Sports. API-Sports independently verifies football fixtures; TheSportsDB is a separately cached public-key team crest/standings dependency. Android Settings has API-Sports, TMDB and OMDb credential inputs. **Centralise only sport-fixture providers and, where authorised, common UK sport EPG information.** TMDB/OMDb, VOD posters and hero art remain local B1G. Xtream/M3U/Stalker passwords and user-provider XMLTV URLs never go to the central feed.

The user has prioritised **accurate detailed UK sporting TV EPG programmes AND the correct B1G Sports Today playable channel**. Implement a two-product, separately licensed feed: versioned daily events, plus licensed verified programme correction deltas (or no public delta if rights absent). Treat existing B1 provider EPG as a safe independent fallback. Source mapping is keyed by provider/service identity, not literal URL. Do not append a lower-priority source and assume generic programmes will be upgraded; use validated same-channel/same-interval quality promotion, retaining explicit local user selections and source provenance.

**Critical Android parity issues for B1 team:** partial API-Sports response can incorrectly remove football cards, team-pair matching is too weak, programme-in-progress is not proof of sport-live, and Android includes optional PPV card inside 10 while Mac allows 10 body + PPV headline 11. These are audit findings requiring separate tests/implementation.

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
