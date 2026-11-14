# SportsLiveInfo public feed contract — format `sli/1`

> **Current documentation context — reviewed 12 November 2026.** Experimental v0.3.0 source is present. Current source/test evidence and open deployment gates are centralized in CURRENT_STATUS; historical version receipts elsewhere are not current pass claims.
> **Repository roles:** [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is the public App source and installation repository; [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is PUBLIC daily data only. [Current status and evidence](CURRENT_STATUS.md).

**Status:** v0.3.0 source implements `sli/1.0`, schemas, golden fixtures, preview and atomic writer. Current verification: [CURRENT_STATUS.md](CURRENT_STATUS.md), 88 tests passed on Python 3.12.15; HTTP handler tests use an in-memory transport because loopback bind is denied here. The public daily-feed repo `jimmyfazz/LiveSports-EPG` was README-only when checked. The source/installation repo `jimmyfazz/SportsLiveInfo` stays private. B1G reader/device acceptance remains unverified.
**Supersedes** the proposed layout in `FEED_CONTRACTS_AND_PUBLICATION.md` §3 for asset paths and versioning. The rights, state-machine and safety rules there remain in force.

---

## 1. Goal

**Design goal:** a compatible data-driven B1G reader should receive added events, taxonomy entries and identity metadata without a new release. New capabilities, programme-supplement rendering, unsupported rules and breaking changes can require reader updates. This is a contract goal, not tested device behavior:

1. **Everything a TV needs to classify, label, order and match is data in the feed**, not code in B1G. That covers sports, competitions, national rows, tags, live-state rules, priority groups, the channel registry, normalisation rules, families, the guide catalogue and the display policy.
2. **Compatibility rules are strict.** Minor versions only add things; readers ignore what they don't know and fall back safely for unknown values.
3. **Time-relative state is computed on the TV.** A cached schedule can support an explicitly qualified time estimate later; stale provider live status is not proof of actual play.
4. **Assets are content-addressed.** Unchanged assets keep their URL, so TVs download only what changed and can cache immutably.
5. **Publication is atomic.** One Git commit adds all new assets plus the manifest, so the Git tree changes consistently. Raw/Pages caching may still delay individual files; readers must verify every asset and retain last-good.

## 2. Layout (feed repository, served via GitHub Pages or raw)

```
v1/manifest.json                      latest manifest (the only mutable path; poll this)
v1/manifests/<revision>.json          last 10 manifests (history, rollback, slow TVs)
v1/assets/<kind>/<sha256[:24]>.json   immutable, content-addressed assets
```

| Asset kind | Schema | Required | Purpose |
|---|---|---|---|
| `taxonomy` | `sli.taxonomy/1` | yes | Sports (label, order, typical minutes, B1G priority group), 127+ competitions, national rows (England, England Women, home nations, U21), tags, live states, precisions, live-state rule |
| `channels` | `sli.channels/1` | yes | Canonical services per market with names, exact source tvg-id crosswalk (farleyflex), normalisation spec, 41+ lineup families, matching precedence and gates, guide catalogue (URLs, market, upstream family, verified flag) |
| `events:YYYY-MM-DD` ×8 | `sli.events-day/1` | today yes, others no | De-duplicated, classified events for each Europe/London day (today + 7), field whitelist |
| `today` | `sli.today/1` | yes | Default grouping (sport → competition → event ids) and featured ids for today |
| `health` | `sli.health/1` | no | Source states and guide coverage per family, measured on the HA host |
| `identity` (since 1.1, capability `channel_identity`) | `sli.identity/1` | no | **Channel identity graph.** Guide channels linked across guides because they show the same programmes at the same times and their names agree apart from decoration. Members `{source_id, channel_id}` per service; `timeshifts` (+1/+2 channels with their base channel); `sources` with guide URLs. Channel ids and names only, never programme data. Generated `<mk>.auto.*` ids are join keys valid within one revision; curated ids are stable |

JSON is UTF-8, compact, keys sorted. The SHA-256 in the manifest covers the exact bytes.

## 3. Manifest essentials

- `format_major` / `format_minor`, and `compatibility`: `reader_major`, `unknown_fields: ignore`, `unknown_assets: ignore`, `unknown_enum_fallback`, `on_major_mismatch`.
- `revision` is a hash of the asset hashes, so it is stable when data is unchanged. `previous_revision` is also given.
- `refresh`: `reader_poll_minutes` (30), `stale_after_hours` (30), `expires_at` (+48 h), `expected_interval_minutes` (from the HA schedule).
- `capabilities`: readers may only rely on features listed here. New features add a capability string.
- `coverage`: counts by sport, today, corroborated, verified broadcasts, known sports/competitions/services/families.
- `rights`: approved and omitted sources, `epg_programmes: not_published`, `broadcast_candidates: not_published`, and the attribution lines the TV must display (ODbL, CC BY-NC-SA…).
- `display_policy`: default 10 body cards plus a pinned PPV card, featured tags. User settings on the TV always override.

## 4. Compatibility rules (binding on both sides)

| Change in SportsLiveInfo | Version impact | B1G reader behaviour |
|---|---|---|
| New events, sources, days of data, corrections | none (new revision) | Automatic |
| New sport / competition / national row / tag | none (taxonomy data) | Automatic. Shown with feed labels and order; new `b1g_priority_group` appended to the user's sport order |
| New channel service, name variant, market, crosswalk id, family | none (channels data) | Automatic for matching suggestions; user manual mappings and hidden channels still win |
| New guide in the catalogue | none | Automatic. Listed as user-selectable with HA-measured coverage; never auto-loaded (`automatic_fallback: false`) |
| New optional field on an existing object | minor +1 | Ignored by old readers; used by readers that know it |
| New asset kind | minor +1 + capability | Ignored by old readers |
| New enum value (status, precision, live state) | minor +1 | Old readers use `unknown_enum_fallback` |
| Removing or renaming a field, or changing meaning or units | **major +1** | Old readers keep the last good feed and show "update B1G"; publish v1 and v2 in parallel during migration |

SportsLiveInfo **must not** make a breaking change inside `v1/`. A future `v2/` lives beside `v1/` until all TVs are updated.

| `dictionary` (since 1.2, capability `channel_dictionary`) | `sli.dictionary/1` | no | **UK and Europe channel dictionary** from the public-domain iptv-org database (when the owner enables it), plus any **optional world regions** the owner switched on (`regions`, since 0.3.18): channel id, name, alternative names, country, network, owners, categories, website, launched, closed/replaced_by, and feeds (regional/HD/+1) with broadcast-area countries. Includes `market_countries`, `bare_market_codes`, `group_markets`, `country_tags`, `aliases`, `language_variants` and lookup `rules` |

### 4.0 Using the dictionary (B1G reader)

1. Determine the channel's market from the provider category (e.g. "UK |" → GB, "INT \| France" → FR) or from its name prefix ("|NO|" → NO). World markets (only present when the owner enabled the region): US, CA, AU, NZ, IN, PK, BD, NP, IR, VN, PH, and the multi-country **group markets** MENA, AFRICA, CARIB, LATAM, KU (Kurdish) for provider sections that mix countries.
2. Compute `market_key(name, market)`: the published normalisation after removing, once, a bare code equal to the market ("US Example", "Carib (FLOW) Example"), leading provider market/platform tags ("|SENEGAL| ", "IN-TM | ", "EG: ", "JOYN DE: ", "DE ||VIP| ", "Shahid | "), leading bracket tags in world markets ("(MX) (IZ) "), the LATAM platform word "Claro " and trailing platform marks ("(FL)", "(C)", "|TN|"). Bare codes of *other* markets are never removed ("Al Jazeera" in an Albanian list).
3. **Group markets:** a leading tag naming a country (`country_tags`, or a two-letter code in `market_countries[market]`) restricts every step to that country ("|NIGERIA| AIT" is Nigeria's AIT). Without a tag, each lookup method pools all the market's countries, so a name found in two countries is ambiguous.
4. Look up, in order:
   - exact normalised name, alternative name, or "base + feed" name of a channel in `market_countries[market]`, in list order (own country first), allowing a no-spaces fallback;
   - then decoration-only equality;
   - then channels whose feeds broadcast into those countries.
   Cyrillic and Greek names and alternative names are also indexed in Latin script (published transliteration: Cyrillic per-letter with ya/ia, yu/iu, kh/h variants; Greek both look-alike letters "EPT" and sound "ERT").
5. Only when nothing is found, the fallbacks in `rules.fallbacks`, in order: aliases, singular/plural, language variant, **(4)** a trailing code of the channel's own market ("ZDF HD DE"), **(5)** a closed channel's live successor (below). In US/CA/CARIB a **station callsign** in brackets ("NBC 5 (KXXX) City") matches feeds named after it; when several networks share the callsign, the one named in the provider name wins (`rules.callsign`).
6. One channel id is **high** confidence. Several ids are **ambiguous**: never apply them automatically.
7. Precedence: below user manual mappings, provider tvg-id exact and `channels.source_crosswalk`.
8. A resolved id may select a guide whose channel id equals it (many guides use these ids), or link through `identity` members.
9. **Closed channels** never supply their own guide. Since 0.3.18 a name whose closed channel(s) all name the same live successor (`replaced_by`, followed up to three times) resolves to that successor with method `replaced_by` ("FOX" in a Turkish list → NOW; "C More Hits" → TV4 Hits): the provider stream now carries it. Closures without a live successor are only explained.
10. For channels without any guide, `name`, `network`, `categories` and `website` may be shown as an information card.
11. Attribution "Channel dictionary from the iptv-org database" (Unlicense) is listed in `rights.attribution`.

### 4.1 Using the identity graph (B1G reader)

The identity graph lets a provider tvg-id from one guide family use another guide's rows for the same channel:
1. Precedence is unchanged: user manual mapping, then the provider tvg-id in the source being read, then `channels.source_crosswalk`.
2. **New step after these:** if the provider tvg-id (or the curated id resolved for the channel) is a member `channel_id` of an `identity.channels[]` entry, any other member in a loaded guide may supply rows. The reader picks the member whose guide has rows in the window, in the user's source order.
3. `timeshifts[]`: a channel listed here may show its `base` channel's rows shifted by `offset_minutes`, labelled as timeshifted. Never the reverse.
4. Never use a generated `*.auto.*` id as a stored key, because it may change between revisions. Store the provider tvg-id and source instead.

The merge rules are published inside the asset (`rules`): identity tokens (+1/+2, plus/Sports+, numbers, regions including ROI and Channel Islands, languages) must be equal, names must agree apart from decoration, and schedules must agree for at least 50 % of comparable slots. Pairs whose schedules agree but whose names differ are **never** published; they wait for owner review in the Home Assistant app.

## 5. Rights and privacy (unchanged laws)

- Events are published only when the primary source and every fused contributor are listed in `publication_approvals`. Others are omitted and reported. This conservative source-level gate is not the complete per-field licensing model in the design.
- Events use a **field whitelist** (`feed.EVENT_FIELDS`). EPG programme text, EPG-derived broadcast candidates, fetch scopes and live state never leave the HA box.
- `broadcasts` appear only when `broadcast_verified` is true, `broadcast_verification_rule` is `approved_v1`, and evidence is present. A reviewed independent rule and real evidence remain acceptance gates; a boolean alone is insufficient.
- The feed never contains stream URLs, provider credentials, user lineups, hidden channels or IP addresses. The guide catalogue lists only public guide URLs.

## 6. Publishing

- **Manual:** Ingress → Publishing → *Build feed preview (no upload)* writes the exact feed to `/data/feed-preview/`. *Publish feed now* commits it.
- **Automatic:** tick *Publish automatically after every scheduled refresh*. It is attempted after collection only when enabled and approved sources exist, with at least one successful source refresh; `publish()` additionally requires setup, token and a sports snapshot.
- **One commit per revision** via the GitHub Git Data API (blobs → tree with base → commit → ref update, no force). Only new assets are uploaded; an unchanged revision is skipped. The last 10 manifests and every asset they reference are retained; older ones are deleted in the same commit.
- **Token:** fine-grained, contents read/write on the feed repository only.

## 7. Contract fixtures and cross-language parity

- `schemas/*.schema.json` — JSON Schema for every asset.
- `schemas/fixtures/sli-v1/` — a complete golden feed for a fixed day (14 Nov 2026, 14:00 UTC). It is byte-identical to the publisher output, so the manifest hashes verify.
- `schemas/fixtures/sli-v1/matching-cases.json` — channel names → expected canonical id/families, including hard negatives. The B1G Kotlin matcher must reproduce every case.
- `tests/test_feed.py` fails if code and fixtures drift. Regenerate with `PYTHONPATH=sportsliveinfo/src python tools/generate_feed_fixtures.py` and copy the directory to `platforms/android/app/src/test/resources/sli-v1/` in the B1 repo in the same change.

## 8. Owner prerequisites before the first TV reads the feed

1. Install and test SportsLiveInfo on the HAOS mini PC; Test-connect the sources you want.
2. Obtain and record documented redistribution permission and required attribution for every contributing source before configuring `publication_approvals`; personal acceptance alone is not a licence grant.
3. The public feed repository [jimmyfazz/LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) already exists. In the Home Assistant Publishing page use owner `jimmyfazz`, repository `LiveSports-EPG`, branch `main`. Set up a fine-grained token restricted to **that repository only** with Contents read/write, and enable GitHub Pages if choosing the Pages address. A public raw-content URL is also possible once the JSON files actually exist; neither URL is live yet.
4. After test/rights gates, perform an authorized publication and anonymously verify manifest plus every referenced hash/byte count. Implement and validate the B1G reader before configuring its eventual feed setting; that reader is not verified by this repository review.
