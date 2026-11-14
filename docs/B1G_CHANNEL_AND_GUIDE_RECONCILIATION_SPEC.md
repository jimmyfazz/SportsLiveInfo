# B1G channel and guide reconciliation — authoritative specification

Status: binding for the B1G reader from SportsLiveInfo 0.3.20 (feed format `sli/1.5`). It brings together the rules spread across the [feed contract](FEED_CONTRACT_SLI_V1.md) (§4.0, §4.0a, §4.0b, §4.1) into one order of work.

**Goal.** Every channel of the **current account** is reconciled to the right service and the right guide, exactly as SportsLiveInfo would do it. This covers entertainment, movies, kids, news, documentaries, music, regional and sport channels. B1G does the matching **on the TV**: the account's channel list, hidden channels and mappings never leave the device.

## 1. Inputs

| Input | Where | What it contains |
|---|---|---|
| Provider channel list (Xtream/M3U) | on the TV | category, name, `tvg-id` / `epg_channel_id`, stream (never uploaded) |
| Provider guide (XMLTV / short EPG) | on the TV | **always the primary guide** |
| `channels` asset | published feed | SLI services (names per market), regional rules, `source_crosswalk`, guide catalogue |
| `dictionary` asset | published feed | channel identities, rules, aliases, market countries, country tags (optional; owner switch) |
| `identity` asset | published feed | the same service across guides, found by schedule |
| `guide_map` asset (1.5+) | published feed | for every guide enabled on SLI: guide channel id, name, the **service** it is, `method`, `programmes_7d` |
| Events + `broadcast_links` | published / private feed | fixtures and their channels |

## 2. Per provider channel, in this order

0. **Skip and classify.**
   - Hidden categories and channels (`ChannelVisibilityStore`) are skipped entirely.
   - Kind is VOD (stream path `/movie/`, `/series/`), radio, adult, 24/7 loop, event feed or linear (reference: `coverage.classify_kind`).
   - Market comes from the category, then the name prefix (reference: `coverage.market_of`).
1. **User manual mapping** (`EpgChannelMappingStore`, per source): always wins.
2. **Provider `tvg-id`.**
   - If it equals a guide channel `id` in `guide_map`, take that guide channel. Its `service` is the identity.
   - Else, if it equals an SLI service id or a `dictionary` channel id, take that identity.
   - This is the most accurate route. Use it before any name rule.
3. **`channels.source_crosswalk`**: an exact guide id for that guide only.
4. **Service name in the market** (`channels.services`, `regional_services` rules): the normalised name in the channel's own market only.
5. **Dictionary** (`dictionary.rules`, exactly as `dictionary.Resolver.resolve`).
   - Steps, in order: market key; country tag; exact / decoration / broadcast area; callsign (US/CA/CARIB); aliases; singular/plural; sport word; language variant; own-country numbered channel; live successor; own-market suffix; implied first number; plain over 4K.
   - **Identity** of a hit: `dictionary.service_identity` — `id` for the main or a picture-quality feed, `id@Region` for exactly one regional feed ("BBCOne.uk@Wales"), none for a timeshift feed, several channels or several regions.
   - Must reproduce `schemas/fixtures/sli-v1/dictionary-cases.json` and `dictionary-conformance/cases.json` exactly (ids, method, confidence and identity).
6. **Event feeds and slot channels.**
   - Use `event_slots.parse_slot` and `match_slot`; the guide entry comes from the name or the linked event (contract §4.0b).
   - Must reproduce `slot-cases.json`.
   - An event feed with no fixture in its name gets no fixed guide.
7. **US/Canadian local stations**: network + city (`guide.local_station_key`, contract §4.0a).
8. **Schedule fingerprint** (when implemented on the TV): the provider guide's programme sequence compared with guide channels (`identity`). Only a unique, high-similarity match counts.
9. **Ambiguous** results (several ids) and anything below "high": **never applied**. They go to the owner's review list, and a confirmed choice becomes a user mapping (step 1).

Never auto-merge any of these, whatever the name says:
- regional versions (BBC One Scotland, Wales, NI; ITV/STV/UTV);
- `+1`/`+2`;
- Sky Sports+;
- numbered channels with a different number;
- another country's feed (`.de`, `@GermanyHD`, `beINSports1.qa@MENA` in a French list);
- Sky / BBC regional, France Canal+ / beIN / RMC, or the beIN MENA vs national channels.

## 3. Choosing the guide for a reconciled channel

1. **The provider's own guide stays primary.** If it has programmes for the channel over the next 24 hours, show it and stop. Any SLI-mapped guide is a non-destructive supplement only.
2. Otherwise choose exactly as `coverage.choose_guide_channels` (conformance: `guide-choice-cases.json`):
   - a guide channel whose `id` equals the provider `tvg-id`; else
   - the `guide_map` channels whose `service` is the identity, or its `service_aliases` partner (both directions); plus
   - the same iptv-org channel (`id` before `@`) in guides that did not identify it, when the feed after `@` is exactly the identity's region ("Wales"/"WalesHD" for `…@Wales`; none, "HD", "SD", "UK", "UKHD" for the national channel), never a timeshift feed, and never another country's feed for the channel's market.
   - Only guides the owner has enabled on the TV; only guide channels with `programmes_7d` > 0; most programmes first.
   - Never take a guide channel of another service, region, country or timeshift.
3. Event slot channels show the slot's fixture and time from the name, or the linked event. Never a "Live" state from the name alone.
4. Nothing found: show the dictionary description (name, network, categories, website) as an information card, and offer the channel in the review list.

## 4. Conformance (must pass before release)

| Fixture | Covers |
|---|---|
| `schemas/fixtures/sli-v1/matching-cases.json` | guide channel → service (registry, crosswalk, foreign-id hard negatives) |
| `schemas/fixtures/sli-v1/dictionary-cases.json` | provider name + market → dictionary identity (every rule) |
| `schemas/fixtures/sli-v1/dictionary-conformance/` | 15,794 provider-style names over 3,138 public channels: ids, method, confidence, identity |
| `schemas/fixtures/sli-v1/slot-cases.json`, `slot-conformance.json` | event slot parsing and event linking (2,516 names, five clocks, both UK clock changes) |
| `schemas/fixtures/sli-v1/guide-choice-cases.json` | guide channel choice from `guide_map` (1,200 combinations) |
| golden feed `schemas/fixtures/sli-v1/v1/` | reading every asset, including `guide_map` |

**Acceptance on the owner's real list (local):**
1. SLI's Home Assistant *Channel coverage* page exports `coverage.csv`. It gives, per channel: market, genre, identity, guide source, guide channel and state. The file stays on the owner's device.
2. B1G exports its own per-channel result in the same columns, locally (debug export on the TV).
3. Compare the two.
   - **Identity:** where both give a result, agreement ≥ 99 %.
   - **Wrong regions:** zero regional, +1 or foreign mismatches.
   - Every difference is reviewed and becomes either a B1G fix or an SLI rule change, with a new fixture case.

## 5. Privacy

- The account's channel list, `tvg-id`s, hidden state, mappings and the review list stay on the TV.
- Nothing is uploaded to GitHub or to SLI.
- The SLI coverage report runs on the owner's Home Assistant from a list the owner imports there. It is never published.
