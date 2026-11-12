# Codex handover — discover actual B1G subscription channels and drive SportsLiveInfo EPG coverage

> **Current documentation context — reviewed 12 November 2026.** This is an execution handover, not permission to upload real accounts. No private subscription inventory was obtained in this review; any future export/import must remain owner-triggered and local.
> **Repository roles:** [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is PRIVATE source/installation and stays private; [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is PUBLIC daily data only. [Current status and evidence](CURRENT_STATUS.md).

**Priority: HIGH.** This is an actionable instruction set for Codex operating on the owner's **local terminal**. Do not confuse repo code inspection with live authenticated subscription inventory. No account credentials, playlist URLs or tokens may be committed to GitHub.

## Confirmed owner decision — no TV write operations

All ten TVs are **strictly read-only** clients of the sports/EPG GitHub feed. **Do not build a per-device GitHub writer, GitHub token configuration, background playlist upload, channel-change push, hosted webhook, or automatic synchronisation of hidden preferences.** Hidden categories and channels are account-scoped locally in Android's `ChannelVisibilityStore`, which calls `EffectiveLiveCatalogue.project`; those choices must continue to govern EPG and Sports Today UI regardless of central superset contents. Optional channel discovery is a **manual owner-triggered safe export**, then **local HAOS import**. Consult [read-only B1G policy](B1G_READ_ONLY_FEED_AND_INVENTORY_POLICY.md).

## Required architecture — canonical identity + local matching

**New mandatory specification:** [CHANNEL_IDENTITY_AND_EPG_ALLOCATION_SPEC.md](CHANNEL_IDENTITY_AND_EPG_ALLOCATION_SPEC.md). Do not implement EPG enrichment by downloading a broader XMLTV source alone. Create the shared `canonical_channel_id` registry (UK/France/other discovered channels, source-specific EPG IDs, verified aliases, region/variant/timeshift, provenance), and upgrade B1G's indexed channel resolver to use it, retaining account-local stream IDs, manual source selection, hidden categories/channels and per-device overlays. Verify event-to-programme-to-broadcaster separately. Include hard-negative regression tests for regional BBC, Sky News vs Sky Sports News, Sky Sports+ vs standard, TNT numbered channels, CANAL+/beIN/RMC editions and +1 feeds. No TV GitHub write permission; ambiguous matches remain unmatched. Benchmark precision with labelled real safe inventory and retain fallback to existing B1 EPG if central sources are missing.

## Goal

Extend private `jimmyfazz/SportsLiveInfo` Home Assistant OS App to serve **UK, French and other countries actually available in B1G subscription(s)**, plus accurate sporting rail cards with real channel information. Keep TV-side playable-stream and per-account EPG mappings local. Do NOT centralise movie/series TMDB/OMDb/poster/hero APIs.

Read in order:
1. `README.md`, `AGENTS.md`, `docs/SUBSCRIPTION_DRIVEN_MULTIREGION_EPG.md`, `docs/HOME_ASSISTANT_BARE_METAL_PRIMARY.md`, `docs/HOME_ASSISTANT_FIRST_RUN_WIZARD_AND_NOTIFICATIONS.md`.
2. B1G repo `jimmyfazz/B1` main, especially:
   - `platforms/android/app/src/main/java/com/b1giptv/player/data/XtreamClient.kt` (`liveCategories`, `get_live_streams`, `channelFromStream`)
   - `PlaylistClient.kt` and `M3uParser.kt` (M3U with credential-bearing URLs), plus Stalker/MAG path.
   - `ui/SkyGuideScene.kt` (`backupFeeds`, `fixSportsEpgNow`, source limits)
   - `ui/BroadcasterEpgAliases.kt`, `ui/EpgResolver.kt`, `ui/EpgSourcePrecedencePolicy.kt`, `ui/EpgScheduleMerger.kt`
   - `ui/SkyHomeScene.kt`, `ui/HomeSportsEvents.kt`, `data/SportsFixtures.kt` and `data/SportsPriorityStore.kt`
   - `ui/EpgChannelNameIndex.kt`, `data/EpgChannelMappingStore.kt`, `data/ChannelVisibilityStore.kt`, `data/CredentialsStore.kt`
   - Mac parity: `B1G-IPTV-Web/src/lib/epg/sports-epg-setup.ts`, `sports-epg-aliases.ts`, `src/lib/home/sports-events.ts`.
3. Source audit for `farleyflex/epg-guide` plus French fallback links listed in the new scope specification.

## Phase A — forensic discovery, no subscription changes

- Pull latest B1G and SportsLiveInfo; record HEAD SHAs and changes since this handover.
- Determine which local installation has a legitimately configured account and whether Codex can access a supported runtime data export **with explicit owner consent**. GitHub B1 repo alone contains no current private channel catalogue.
- Design and implement an **owner-triggered Export Safe Channel Inventory** action/CLI inside B1G (or local authenticated provider query as appropriate) for **all accounts**, without exposing credential fields or URLs; do not decrypt/extract/copy credentials outside app's normal secure storage.
- Export only channel name, safe TVG ID, channel group, optional country/language, visible flag, playable flag, anonymised account alias and an opaque local inventory ID. Never export raw provider stream IDs, server hostname, stream or account URLs, MAC/device identifiers, username/password, API keys or viewing history.
- Store this export locally, or move only into the private restricted owner-operated HAOS collector by a user-approved import mechanism. The complete inventory must **never** be uploaded to a public GitHub feed.
- If actual runtime access is unavailable, do not fabricate a channel list. Provide working export action, synthetic tests and explicit steps for the owner to run it.

## Phase B — coverage matrix and provider selection

- Produce sorted report by country, subscription/account, category, channel name and EPG ID, duplicate HD/SD/UHD variants, non-EPG channels and missing/ambiguous country or language. Keep account-sensitive reports local.
- Create channel-to-source coverage probes (id match; source channel exists; programme rows today + next 7 days; title/description quality; window and freshness).
- Confirm sources and terms, prioritising UK Sky/TNT/Premier; France (`programme-tv.net`, `telerama.fr`, `xmltvfr.fr`, any permitted others), then other countries from inventory. Do not assume all French providers or paid channels are covered by free sources.
- Avoid pulling massive public global EPG sources without targeting actual channels and measuring provider publication rights and resource usage. Flag incomplete/no-rights feeds separately.
- Build and test alias registry with accented names, regional variants, timeshift, Sky Sports+/TNT extra channels, Canal+/beIN/RMC (only when inventory and source evidence justify).

## Phase C — code development

- Python core: source registry, XMLTV streaming parser, per-country source selection, per-source quotas/cache/validators, normalisation, channel coverage index, programme enrichment decision, conflict provenance and last-good cache.
- Publish **separate** event schedule and channel/region EPG artefacts **only where rights cleared**. Validate schemas and sizes. `manifest.json` identifies revisions and segments; client fetches only necessary countries/sources.
- Build Home Assistant Ingress first-run setup wizard: provider cards with source URLs and enabled modes; separate `Channel inventory` (secure local import, diagnostics of UK/France/unknown coverage); GitHub token/destination/scheduler configuration; errors via quiet HA persistent notifications.
- Integrate Android B1G through optional central feed with local EPG fallback and source provenance. Preserve player, channel switching, focus and per-account manual mapping. A fixture must not automatically become a playable stream.
- **Do not add TMDB/OMDb/film hero/poster fetches** to SportsLiveInfo. Leave them lazy/account-local within B1G.

## Phase D — tests, receipts and merge discipline

Write automated test fixtures, independent of live accounts: UK + French mixed catalogue, accents/case, `FR:` group without language, ambiguous France/Canada channel, duplicates SD/HD, account change, hidden channel, missing TVG ID, wrong-channel mapping, premium-channel unknown, mismatched programme timezone, DST London/Paris, credential leakage, 429/503, stale source, large 50k-channel discovery with narrow EPG selection, permission-denied publication, PPV boxing and generic-to-specific Sky sports EPG correction.

Use representative real-source integration tests only with explicit licence/credential approval and rate budget. Do not push any real subscription inventory, EPG cache or secret, including in test logs or PR artifacts. Produce a concise dated report of code paths, changes, observed coverage metrics, missing rights, remaining issues and tests. Use multiple independent tasks/agents for parser, UI, data-source coverage, and B1G integration when available, but coordinate shared data contracts. Merge only after tests pass and owner-appropriate publication gates are verified.

## Intended UX

Home Assistant (one-time): signup/input sports API keys (individually saved), select permitted EPG sources and countries, optionally import sanitized B1G channel inventory, set outbound GitHub feed destination, set UK local refresh schedule. Later: dashboard shows source health, UK/FR/other EPG coverage, errors, last-good and publish status.

B1G TV (ongoing): retrieve cached daily sporting events and country-specific EPG enhancements from common feed, select correct *local* channel using local account inventory/EPG IDs, display up to ten sports cards plus distinct PPV headline as applicable. No TV sporting API account registrations, no external access into HAOS.

## Audit receipt

This handover reflects code source inspection on 12 November 2026, not a live audit of the owner's subscription or an implemented feature. Prefer current repo code when it conflicts with a documented implementation path, and update this handover accordingly.
