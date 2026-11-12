# Potential B1 Android IPTV integration (optional future phase)

This repository remains **independent** from the B1 application. B1 is one potential consumer of authorised sports information. Do not modify B1 until the standalone aggregator works and can be tested against live permitted inputs.

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
