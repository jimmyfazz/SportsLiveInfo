# Confirmed design decision: B1G devices are read-only consumers

> **Current documentation context — reviewed 12 November 2026.** This is the required TV security boundary. The central feed builder exists; an installed B1G reader, safe inventory workflow and ten-TV acceptance are not established by this review.
> **Repository roles:** [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is the public App source and installation repository; [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is PUBLIC daily data only. [Current status and evidence](CURRENT_STATUS.md).

**Decision date:** 12 November 2026. **Confirmed by owner.** Implement this as an architecture and security invariant. No B1G TV writes to GitHub, holds a GitHub API token, registers an API account, or exposes an inbound endpoint.

## Data flow

1. The Home Assistant OS SportsLiveInfo collector on the always-on home mini PC fetches allowed sports and EPG sources once, validates and caches them, then publishes *only rights-approved* JSON via its own outbound HTTPS GitHub credential.
2. All B1G televisions fetch only published, read-only public HTTPS JSON and maintain local last-good cache. Their stream and playlist accounts, credentials, subscribed-channel lists, manual guide mappings, hidden states, and device preferences remain local.
3. Each TV applies its own **current account's effective visible channel/category projection** when choosing which EPG channels to render and which Sports Today cards may be associated with playable streams. A hidden channel or category must never be reintroduced, recommended or made playable by the central feed. Check override/suppression and account switches.
4. The published feed is **the shared superset** of legally publishable UK, French and other identified channel-programme data; an individual TV filters it to its own current visible channel set. Never create a separate feed version or GitHub commit for a TV's hidden-channel toggle.
5. No auto-upload of the subscribed channel catalogue, hidden-list changes, user identity, or playback behaviour from B1G. A hidden-channel change is a **local-only operation**, with immediate local projection and no new upstream API quota calls.

## Grounding in B1G code

Source: https://github.com/jimmyfazz/B1/blob/main/platforms/android/app/src/main/java/com/b1giptv/player/data/ChannelVisibilityStore.kt

`ChannelVisibilityStore` stores account-scoped `live-category` and `live-channel` hidden IDs in private local preferences. `visibleLiveCategoriesForAccount` loads those sets once and calls `EffectiveLiveCatalogue.project` with hidden category/channel IDs plus custom names/numbers and ordering. The corresponding B1G Sports Today flow uses `ChannelVisibilityStore.visibleLiveCategories` before scanning sport candidates. Preserve this behaviour in the central-feed consumer. No screenshot or running subscription catalogue was inspected; this is a source-code finding.

## How the central collector learns about channels (optional, not required day to day)

- **Preferred initial setup:** Codex implements an *owner-triggered*, local **Export Safe Channel Inventory** action on one B1G installation (or another permitted local catalogue reader), and an **Import Inventory** screen inside the HAOS App. Local transfer/manual import avoids any writable GitHub endpoint on TVs and avoids embedding a GitHub token in Android.
- Export only channel display name, EPG/tvg ID, country/language hints, group, and optional coarse coverage counts; keep account/stream identity, source host, credentials, streaming URLs, serial numbers, viewing history and hidden flags local whenever possible. If visible-only scope is useful, export a **snapshot** for owner review without permanent tracking of per-TV hidden preferences.
- This is **not** automatic subscription synchronisation. On major provider lineup changes the owner may re-import an updated safe inventory. A full lineup may differ across subscriptions; aggregate only voluntarily imported snapshots; never assume one TV is authoritative for ten.
- Reconciliation of changed/new/removed channels occurs locally whenever B1G refreshes an account catalogue. SportsLiveInfo's shared coverage catalogue can remain a superset; stale unused programme rows are not an immediate correctness issue because B1G filters to visible playable channels.
- Avoid the complexity of devices sending channel-change events through GitHub issues, Git pushes, pull requests, cloud functions, or authenticated write APIs. Such mechanisms create extra attack surface, credentials, synchronisation conflicts and public exposure for little benefit.

## Subscriptions and licensing

A private repository is not itself a licence; a public feed of source-derived UK/French EPG content requires permission. If rights cannot be cleared, do not republish the restricted rows. Continue local authorised per-TV EPG sources or use another explicitly authorised private delivery channel (design separately). The use of a **public read-only feed** does not change this restriction.

## Acceptance tests

- [ ] B1G contains no GitHub write token or GitHub write APIs; all TVs consume cached feed anonymously over HTTPS.
- [ ] Ten simultaneous TV requests create **zero additional** sporting-provider or EPG-source calls.
- [ ] A hidden live category and all its channels are absent from that TV's EPG/sports projection even if shared feed includes those channel IDs.
- [ ] A hidden channel within a visible category is excluded; a separate TV that has the same channel visible may still receive its programme information.
- [ ] Account switching or category visibility changes update locally without waiting for GitHub publish, API registration or server-side filtering.
- [ ] No TV inventory or hidden-channel preferences appear in public GitHub, published JSON, logs or error reports.
- [ ] Owner-initiated inventory export contains no secret or stream URL; import is explicit, reversible and local-only.
- [ ] Offline/stale GitHub feed falls back to existing B1G EPG safely, with current local visibility and account-specific manual mapping retained.
