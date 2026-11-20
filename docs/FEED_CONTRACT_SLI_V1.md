# SportsLiveInfo public feed contract — format `sli/1`

> **Current documentation context — reviewed 12 November 2026.** Experimental v0.3.0 source is present. Current source/test evidence and open deployment gates are centralized in CURRENT_STATUS; historical version receipts elsewhere are not current pass claims.
> **Repository roles:** [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is the public App source and installation repository; [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is PUBLIC daily data only. [Current status and evidence](CURRENT_STATUS.md).

**Status:** v0.3.0 source implements `sli/1.0`, schemas, golden fixtures, preview and atomic writer. Current verification: [CURRENT_STATUS.md](CURRENT_STATUS.md), 88 tests passed on Python 3.12.15; HTTP handler tests use an in-memory transport because loopback bind is denied here. The public daily-feed repo `jimmyfazz/LiveSports-EPG` was README-only when checked. The source/installation repo `jimmyfazz/SportsLiveInfo` stays private. B1G reader/device acceptance remains unverified.
**Current minor version: `sli/1.6` (SportsLiveInfo 0.3.23).** It adds honest live state, an optional `live` asset, tiered day assets and guide-corroborated broadcast links; see §4.2.
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
| `events:YYYY-MM-DD` ×8 | `sli.events-day/1` | today yes, others no | De-duplicated, classified events for each Europe/London day (today + 7), field whitelist. Since 1.6 only tier `core` |
| `events:<window.history_from>` (optional, since SportsLiveInfo 0.3.25, capability `event_history`) | `sli.events-day/1` | no | Yesterday (the London day before `window.from`): that day's core events with their last known status (finished, final score when approved and known) and channel links, for replay detection. Never part of `today`. Manifest entry carries `history: true` (§4.5) |
| `events_extra:YYYY-MM-DD` (since 1.6, capability `event_tiers`) | `sli.events-day/1` | no | The long tail (tier `extra`, mostly low-tier football abroad) for days that have any. Readers that ignore unknown kinds simply do not show it |
| `live` (since 1.6, capability `live_status`) | `sli.live/1` | no | Status observations from the live-status lane since the last full feed: `{id, status_normalized, status_observed_at}` per event. Present only when there are such observations |
| `today` | `sli.today/1` | yes | Default grouping (sport → competition → event ids) and featured ids for today (since 1.6: core events only) |
| `health` | `sli.health/1` | no | Source states and guide coverage per family, measured on the HA host |
| `identity` (since 1.1, capability `channel_identity`) | `sli.identity/1` | no | **Channel identity graph.** Guide channels linked across guides because they show the same programmes at the same times and their names agree apart from decoration. Members `{source_id, channel_id}` per service; `timeshifts` (+1/+2 channels with their base channel); `sources` with guide URLs. Channel ids and names only, never programme data. Generated `<mk>.auto.*` ids are join keys valid within one revision; curated ids are stable |

JSON is UTF-8, compact, keys sorted. The SHA-256 in the manifest covers the exact bytes. No asset exceeds 8 MiB (B1G's `MAX_ASSET_BYTES`): an optional asset above it is left out of the feed and a required one stops the build.

## 3. Manifest essentials

- `format_major` / `format_minor`, and `compatibility`: `reader_major`, `unknown_fields: ignore`, `unknown_assets: ignore`, `unknown_enum_fallback`, `on_major_mismatch`.
- `revision` is a hash of the asset hashes, so it is stable when data is unchanged. `previous_revision` is also given.
- `refresh`: `reader_poll_minutes` (30), `stale_after_hours` (30), `expires_at` (+48 h), `expected_interval_minutes` (from the HA schedule).
- `capabilities`: readers may only rely on features listed here. New features add a capability string.
- `coverage`: counts by sport, today (core), corroborated, verified broadcasts, known sports/competitions/services/families. Since 1.6 also `tiers` (`core`, `extra`), `today_extra` and `guide_corroborated_broadcasts`.
- Since 1.6, `compatibility` also carries `live_state_rule`, `live_overlay_rule` and `tier_rule` (§4.2).
- Since 1.7 (only while a source is approved for scores) the manifest also carries `capabilities: scores`, `compatibility.scores` and `rights.scores.approved_sources` (§4.4).
- `rights`: approved and omitted sources, `epg_programmes: not_published`, `broadcast_candidates: not_published`, and the attribution lines the TV must display (ODbL, CC BY-NC-SA…).
- Since 0.3.25 `window.history_from`, `compatibility.display_state_rule`, `history_rule`, `time_precision_rule`, `starting_soon_minutes`, and capabilities `event_history` and `display_state` (§4.5). All optional; `min_reader_minor` is unchanged.
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

| `guide_map` (since 1.5, capability `guide_map`) | `sli.guide-map/1` | no | For every guide enabled on the SLI host: each guide channel's `id`, `name`, the `service` it is (SLI service id or dictionary id) with `method`, and `programmes_7d`. Ids, names and counts only. Optional `service_aliases` (dictionary id → SLI service id). B1G uses it to pick the guide channel for an identified provider channel (reference: `coverage.choose_guide_channels`). |

**The complete order of work for B1G is in [B1G channel and guide reconciliation — authoritative specification](B1G_CHANNEL_AND_GUIDE_RECONCILIATION_SPEC.md).**

### 4.0 Using the dictionary (B1G reader)

1. Determine the channel's market from the provider category (e.g. "UK |" → GB, "INT \| France" → FR) or from its name prefix ("|NO|" → NO). World markets (only present when the owner enabled the region): US, CA, AU, NZ, IN, PK, BD, NP, IR, VN, PH, and the multi-country **group markets** MENA, AFRICA, CARIB, LATAM, KU (Kurdish) for provider sections that mix countries.
2. Compute `market_key(name, market)`: the published normalisation after removing, once, a bare code equal to the market ("US Example", "Carib (FLOW) Example"), leading provider market/platform tags ("|SENEGAL| ", "IN-TM | ", "EG: ", "JOYN DE: ", "DE ||VIP| ", "Shahid | "), leading bracket tags in world markets ("(MX) (IZ) "), the LATAM platform word "Claro " and trailing platform marks ("(FL)", "(C)", "|TN|"). Bare codes of *other* markets are never removed ("Al Jazeera" in an Albanian list).
3. **Group markets:** a leading tag naming a country (`country_tags`, or a two-letter code in `market_countries[market]`) restricts every step to that country ("|NIGERIA| AIT" is Nigeria's AIT). Without a tag, each lookup method pools all the market's countries, so a name found in two countries is ambiguous.
4. Look up, in order:
   - exact normalised name, alternative name, or "base + feed" name of a channel in `market_countries[market]`, in list order (own country first), allowing a no-spaces fallback;
   - then decoration-only equality;
   - then channels whose feeds broadcast into those countries.
   Cyrillic and Greek names and alternative names are also indexed in Latin script (published transliteration: Cyrillic per-letter with ya/ia, yu/iu, kh/h variants; Greek both look-alike letters "EPT" and sound "ERT").
5. Only when nothing is found, the fallbacks in `rules.fallbacks`, in order:
   - aliases;
   - singular/plural;
   - the sport word in its other spellings (sport/sports/spor);
   - language variant;
   - the market's own numbered channel ("beIN Sports 1" → "beIN Sports 1 Turk" in TR). This is also preferred whenever a numbered name is otherwise found only as a foreign channel broadcasting into the market;
   - a closed channel's live successor (below);
   - a trailing code of the channel's own market ("ZDF HD DE");
   - an implied first number ("Diema Sport 1" = "Diema Sport" when "Diema Sport 2" exists).

   When candidates differ only by a 4K/UHD version and the provider name has no 4K/UHD marker, the plain channel is chosen. In US/CA/CARIB a **station callsign** in brackets ("NBC 5 (KXXX) City") matches feeds named after it; when several networks share the callsign, the one named in the provider name wins (`rules.callsign`).
6. One channel id is **high** confidence. Several ids are **ambiguous**: never apply them automatically.
7. Precedence: below user manual mappings, provider tvg-id exact and `channels.source_crosswalk`.
8. A resolved id may select a guide whose channel id equals it (many guides use these ids), or link through `identity` members.
9. **Closed channels** never supply their own guide. Since 0.3.18 a name whose closed channel(s) all name the same live successor (`replaced_by`, followed up to three times) resolves to that successor with method `replaced_by` ("FOX" in a Turkish list → NOW; "C More Hits" → TV4 Hits): the provider stream now carries it. Closures without a live successor are only explained.
10. For channels without any guide, `name`, `network`, `categories` and `website` may be shown as an information card.
11. Attribution "Channel dictionary from the iptv-org database" (Unlicense) is listed in `rights.attribution`.

### 4.0a US/Canadian local stations (B1G guide-name fallback)

A local station with no id match uses `guide.local_station_key`:
- the lineup name ("US NBC 5 (KXYZ) City") gives (network, city);
- it matches a guide channel named "NETWORK City" or "US - NETWORK City" (EPGTalk US local and US guides).

"News" streams ("US - ABC News City") are different channels and never match. Only one guide channel per (network, city) counts. Measured: about 380 of the owner's 1,847 otherwise guideless local stations.

### 4.0b Event-slot channels (B1G, on the TV only)

Numbered event channels whose name announces the programme are matched on the TV; their names are local lineup data and are never uploaded. Examples: "EPL 05 | Home vs Away (Sat 17:30 UK)", "DAZN 52: League| Home vs. Away| Sat 18 Oct 12:30 PM", "NFL 01: 8:15PM Away @ Home".

The reference is `sportsliveinfo/src/sportsliveinfo/event_slots.py`. B1G must reproduce `schemas/fixtures/sli-v1/slot-cases.json` exactly.

1. **`parse_slot(name, now, default_tz)`** reads, in order:
   - the slot label, leading ("EPL 05 |") or trailing (":NBA  04");
   - the start time;
   - the fixture ("vs", "v", "@", lower-case "x");
   - the competition text.

   Time formats, in order:
   - ISO, including `start:`… which is UTC;
   - day + date + month;
   - month + day;
   - numeric date (UK "21/07" is understood);
   - weekday + time;
   - time alone.

   Time zones:
   - A zone word sets the zone (UK, GMT, ET, CET…), including "// UK Sat …" before a second "// ET …" copy, which is ignored.
   - Otherwise the section's default applies: US/CA sections America/New_York, all others Europe/London.

   Names that are channels, not fixtures, give no result: "V Sport 1", "X Premium", "CA V Montreal".
2. **`match_slot(parsed, events, now)`** links the slot to exactly one SportsLiveInfo event:
   - Both sides must match (either order), ignoring bracketed country codes.
   - With a full date and time, the start must be within 3 hours.
   - With a clock time alone, it must be the same time of day (±30 min) between 4 hours ago and 36 hours ahead. Two meetings of the same teams then stay unresolved.
   - Without a time, the event must fall in that window.
   - Otherwise, no link.
3. **What the TV shows for a slot channel:**
   - With a link: one guide entry, the event's title and time, plus its sport and competition from the feed.
   - Without a link: the parsed fixture and time, marked "from the channel name".
   - Never a "Live" state from the name alone.

### 4.1 Using the identity graph (B1G reader)

The identity graph lets a provider tvg-id from one guide family use another guide's rows for the same channel:
1. Precedence is unchanged: user manual mapping, then the provider tvg-id in the source being read, then `channels.source_crosswalk`.
2. **New step after these:** if the provider tvg-id (or the curated id resolved for the channel) is a member `channel_id` of an `identity.channels[]` entry, any other member in a loaded guide may supply rows. The reader picks the member whose guide has rows in the window, in the user's source order.
3. `timeshifts[]`: a channel listed here may show its `base` channel's rows shifted by `offset_minutes`, labelled as timeshifted. Never the reverse.
4. Never use a generated `*.auto.*` id as a stored key, because it may change between revisions. Store the provider tvg-id and source instead.

The merge rules are published inside the asset (`rules`): identity tokens (+1/+2, plus/Sports+, numbers, regions including ROI and Channel Islands, languages) must be equal, names must agree apart from decoration, and schedules must agree for at least 50 % of comparable slots. Pairs whose schedules agree but whose names differ are **never** published; they wait for owner review in the Home Assistant app.

### 4.2 Format 1.6: live state, tiers and corroborated links (since SportsLiveInfo 0.3.23)

**Honest live state.** Every event has `status_observed_at` (ISO-8601 UTC ending in `Z`): when its `status_normalized` was last read from its source(s). Events with a start time that is not date-only also have `expected_end_utc`: the start plus the typical duration (football and rugby 2 h, tennis 3 h, cricket T20 4 h / ODI 8 h / Test day 7 h 30, F1 race 2 h 30, golf round 6 h, darts and snooker session 4 h, boxing card 4 h, basketball 2 h 30, ice hockey 2 h 45, NFL and baseball 3 h 30, otherwise 3 h). When a source gives the event's own end time (OpenF1 sessions), that end is used. The manifest rule (`compatibility.live_state_rule`) is:

> status_normalized == 'live' is trusted only when status_observed_at is at most 45 minutes old AND start_utc <= now <= expected_end_utc + 30 minutes. Otherwise treat it as unknown and fall back to the clock (start..expected_end) shown as 'should be on now', never 'LIVE'.

A cricket Test split into day records has only the day in play `live`; later days are `scheduled` and earlier days `finished` (that day's play). When sources disagree, a merged event takes the most advanced status (finished, postponed or cancelled, then live, then scheduled), then the most recently observed.

**Live asset.** The live-status lane on the SportsLiveInfo host reads the API-Sports live boards (`fixtures?live=all` for football, `games?live=all` for the other team-sport products; not MMA) at most every 15 minutes, and only while the collected feed has an event between its start and expected end (the 15 minute cadence applies only while events are in play; outside play the lane makes no provider call, stays quiet 3 minutes either side of a scheduled refresh, and only expires stale statuses). A stored `live` that has not been re-confirmed within 45 minutes is downgraded to `unknown` without a provider call and the lane republishes, and `live` asset rows whose `live_until_utc` has passed are omitted when the feed is built. The manifest declares this in the optional `refresh.live_lane` (`enabled`, `interval_minutes` 15, `active_only_while_events_in_play`, `quiet_slots_guard_minutes` 3, `last_run_utc`) and `refresh.live_stale_after_minutes` (45); readers that ignore them are unaffected and `min_reader_minor` is unchanged. Automatic publication is refused (the previous feed stays live) when the new feed has more than 20 % fewer events or guide-corroborated bindings than the last published one; a manual publish overrides. It uses at most 40 calls a day per product, counted in that product's own daily quota, and keeps 20 calls for the scheduled refreshes; provider back-off and learned plan dates apply. An event that leaves the live board becomes `unknown`, never `finished`. When a status changes, or play in progress is confirmed (at most every 30 minutes), the feed gains or updates the `live` asset; with automatic publishing on, a commit then uploads only that asset and the manifests. Readers overlay it on the day assets by `id` when its `status_observed_at` is newer. A feed older than 45 minutes never makes anything "LIVE". No programme data. Scores are carried only under the opt-in rule in §4.4 and are absent from every feed unless the owner approved a source for scores.

**Tiers.** Every event has `tier`. `core`: named taxonomy competitions (including the NFL, NBA, NHL and MLB), national-team categories, featured tags (`display_policy.featured_tags`, including `ppv`), the main non-football sports (motorsport, rugby union and league, cricket, tennis, golf, darts, snooker, boxing, MMA, horse racing), and football leagues and cups of England, Scotland, Wales, Northern Ireland, Ireland and France (youth competitions excepted). Everything else is `extra`. `events:<date>` and `today` carry core only; `events_extra:<date>` carries the rest.

**Guide-corroborated links.** `broadcast_links[].status` is `guide_corroborated`, with `verification: independent_guides_v1`, when all of these hold: the strict title matcher found it (never the loose guide-listing matcher); the programme starts between kick-off − 60 min and + 20 min; the channel is a curated registry channel (not a dictionary-only id); and two or more independent guide families list it. Families come from `providers.EPG_FAMILY` after a lineage audit (15 Nov 2026): farleyflex is a mytelly.co.uk grab; Freeview-EPG (dp247) and every M3UPT file are built from Sky's own EPG and form one family; all EPGTalk files are Schedules Direct data; Matt Huisman's files are one family. Guides whose upstream could not be checked (EPG Share, IPTV-EPG.org, Fazzani/grab, dobleM) never count towards the two. `broadcast_verified` stays false: it is reserved for provider or official evidence. B1G binds a channel for Sports Today or "on now" only from `guide_corroborated` links or links with `confidence: high`; others are shown as "may be on <channel>".

### 4.3 SportsLiveInfo decides, readers follow (since SportsLiveInfo 0.3.24)

The owner's aim is that corrections and improvements are made once, in SportsLiveInfo, and reach every TV with the feed, with no B1G update. So decisions that B1G used to make itself are now published as data. All of it is additive; `sli/1.6` readers without these fields keep the §4.2 rules.

- **Link order.** `broadcast_links` are published best first, each with `rank` (1 = best), and the manifest says `compatibility.link_order: "best_first"`. The order is, in turn: guide-corroborated; a channel of the home market (GB); a curated registry channel before a dictionary-only id; more independent guide families, then more guides; high confidence; network before regional; then the channel id (case-insensitive tie-break). Readers keep the published order. (Before 0.3.24 links were sorted by channel id, so any capitalised dictionary id such as `VirginMediaTwo.ie` came before every curated id such as `gb.itv.one`.)
- **Binding.** Each link has `binds`: true when it may name the channel showing the event (Sports Today, "on now"); false means "may be on" only. Readers use it as published.
- **LIVE window.** An event whose `status_normalized` is `live` has `live_until_utc` = min(`status_observed_at` + `compatibility.live_max_age_minutes` (45), `expected_end_utc` + `compatibility.live_end_grace_minutes` (30)). `live` asset rows carry it too. Readers show LIVE only while `start_utc <= now < live_until_utc`; otherwise the clock decides "should be on now" as in §4.2.
- **Data, not code.** Channel identities (dictionary, `guide_map`, `service_aliases`), event selection and tiers, statuses and the fixtures themselves were already published data; a correction there reaches every TV on its next feed read (at most 30 minutes). Only a new kind of decision, or a change to the B1G matching algorithms themselves (dictionary resolver, event-slot parser), needs a B1G update.

- **Team crests (capability `team_crests`, additive, `min_reader_minor` unchanged).** SportsLiveInfo publishes crest *references*, never images; the TV fetches and caches the image itself and draws an on-device monogram whenever there is no usable crest.
  - Event field `participant_crests`: array index-aligned with `participants` (same length); each entry is `{"src":"apisports","ref":"<product>/teams/<id>"}` (for example `football/teams/42`, `rugby/teams/3`) or `null`. Absent when no side has a reference. A side is `null` when the merged sources disagree or the home/away orientation was uncertain: never a guessed crest.
  - Manifest `rights.crests` (always present): `sources.apisports = {enabled, url_template: "https://media.api-sports.io/{ref}.png", attribution, cache_days: 30}`, `device_lookup.thesportsdb = {enabled, attribution}` and `monogram_only`. This is the master kill switch: readers show a crest only when its source has `enabled: true`, otherwise a monogram; `monogram_only: true` means no crest of any kind. Switching crests off therefore needs no TV update.
  - The capability `team_crests` is listed only when `sources.apisports.enabled` is true. Default: disabled, with no `participant_crests` in the feed, until the owner sets `publish_crest_refs` (and an API-Sports source is in `publication_approvals`).
  - Readers: use `url_template` with `{ref}` replaced; cache for `cache_days`; never mirror or re-host; show the attribution. football-data.org, Wikimedia and OpenLigaDB crests are not used.

Also in 0.3.24 (producer only, no reader change):

- listings that name a past year or season ("England v Samoa — Rugby World Cup 2023", "2023-24") are treated as repeats: never linked to a fixture and never guide-listed live events;
- free streaming (FAST) platform guides (Pluto TV, Samsung TV Plus, Plex, Roku) are identified by the curated registry only, never by a dictionary name match (Pluto's "Rugby Pass TV" was mapped to Premier Sports 1 Asia);
- rugby suffix words (`Rugby`, `RFC`, `RUFC`, `RLFC`, `RC`) are ignored when merging rugby fixtures across sources, so "Scotland Rugby vs Australia Rugby" (TheSportsDB) merges with "Scotland v Australia" (API-Sports).

### 4.4 Scores (format 1.7, capability `scores`; off by default)

Until a source is approved for scores, the feed is byte-for-byte what it was before this section existed: no `score` field anywhere, no `scores` capability, no `compatibility.scores` or `rights.scores`, and the manifest still says `sli/1.6`. Scores are a separate right from fixture facts (§5): the owner approves each source on its own in `score_approvals` (Ingress → Publishing → Score approvals), after reading that source's terms.

**When approved sources exist** the manifest says `sli/1.7` (`min_reader_minor` stays 0: old readers ignore every new field), adds the capability `scores`, `compatibility.scores` = `{enabled: true, rule}` and `rights.scores.approved_sources` (the owner's list). **Kill switch:** remove every source from `score_approvals` and the next feed has none of these and no `score`; a reader must treat a missing `compatibility.scores` as scores off and show none, even from an older cached feed.

**The exact rule (also `compatibility.scores.rule`).** An event row (day assets) or a live-asset row may carry `score` = `{home: int, away: int, period: string|null, observed_at: ISO-8601 UTC "Z", source: string}`.

- `home` is the score of `participants[0]` and `away` of `participants[1]`, whatever their home or away role (a US "Away @ Home" listing is just participants in that order). SportsLiveInfo re-expresses each source's own home and away into the published event's participants order when sources merge, including when two sources name the sides in opposite order; if the pairing is not certain, or the event does not have exactly two participants, no score is published. A reader that cannot pair a score with exactly two participants ignores it.
- `period` is one of `1H`, `HT`, `2H`, `ET`, `PEN`, `FT`, `AET` (also "after overtime"), `Q1`-`Q4`, `P1`-`P3`, `OT`, or `null` (break times, baseball innings, volleyball sets and unknown codes). Unknown values are treated as `null`. For `PEN` the score is the score before the shootout. **There is no minute field.**
- Day assets (`events:<date>`, `events_extra:<date>`) carry the **final** score of a `finished` event only. The `live` asset carries the live score of an event whose status is `live` (show it only while LIVE holds under §4.3, never after `live_until_utc`) and the final score read after the event ended. A row's `score` is read in the same observation as its `status_observed_at`; an older score is never attached to a newer status.
- A score is absent when unknown, uncertain, not started, postponed, cancelled, abandoned, awarded or when two approved sources disagree about a final. Absent means unknown, never 0-0.
- `source` is the SportsLiveInfo source id and `observed_at` when SportsLiveInfo read it; readers show the score as provided and may credit the source.
- **Sports in v1:** football, rugby (union and league), basketball, ice hockey, American football, baseball, handball and AFL; volleyball as sets won. **Excluded:** tennis, cricket, golf, motorsport (F1), boxing, MMA and everything else.
- **Sources:** only API-Sports (live and final) and football-data.org (final scores of regular-time results only; wired but never approved by default). TheSportsDB, Jolpica, OpenF1 and all other sources are never eligible; the API-Sports MMA product carries no scores.
- **Cost and commits:** no extra provider calls (the live boards and the settle pass already return scores). With scores approved the live lane also republishes when a score changes, not only a status, subject to the same quiet-slot guard and the same regression gate. During play that is at most one commit per 15 minute pass (higher scoring sports can change every pass, roughly doubling live commits compared with the 30 minute status confirmation); each commit uploads only the small `live` asset and the manifests. When no source is approved nothing changes.

### 4.5 History, display state and guarantees (since SportsLiveInfo 0.3.25; additive, `min_reader_minor` unchanged)

Readers that ignore these fields keep §4.2 and §4.3. Nothing here removes or renames anything.

**Yesterday (capability `event_history`).** `window.history_from` is the Europe/London day before `window.from`. The optional asset `events:<history_from>` (`required: false`, `history: true` on its manifest entry, schema `sli.events-day/1`, tier `core` only) carries that day's events as last known: `status_normalized` including `finished`, `finished_at_utc` and the final `score` when known (the score only under §4.4), and the original `broadcast_links` (channel ids and confidence, never guide text), so B1G can recognise a replay. Yesterday is never in `today` or in the required `events:<window.from>` asset, and the optional `events_extra:<date>` assets do not cover it. The day before yesterday is not published. A source that does not cover yesterday leaves the status at what was last read (often `scheduled`: then `display_state` is `finished` without `finished_at_utc`, "probably finished"). If the asset is absent, treat history as unavailable.

**Display state (capability `display_state`).** Events (day assets and history) and `live` rows may carry `display_state`, one of `upcoming`, `starting_soon`, `live`, `should_be_on`, `finished`, `postponed`, `cancelled`, `tbc` (an unknown value: let the clock decide), plus:

- `state_until_utc`: the instant the state expires; absent when it lasts until the status changes.
- `finished_at_utc`: present only when `finished` is known from a source: the event had finished no later than this (the time the final status was read, which is not the end of play).

The order below is the whole rule; the first line that fits wins. `now` is the build time for `live` rows and the collection time for day assets (so a live republish leaves the day assets byte-identical and uploads only the `live` asset), and a reader whose clock is past `state_until_utc` applies the same lines with its own clock.

| # | Condition | `display_state` | `state_until_utc` |
|---|---|---|---|
| 1 | `status_normalized` is `postponed` or `cancelled` | that status | none |
| 2 | `status_normalized` is `finished` | `finished` (with `finished_at_utc`) | none |
| 3 | `status_normalized` is `live` and `start_utc <= now < live_until_utc` (§4.3) | `live` | `live_until_utc` |
| 4 | `start_precision` is `date_only` or `time_tbc` | `tbc` | 00:00 London after that date, if still ahead |
| 5 | `now < start_utc - 30 min` (`compatibility.starting_soon_minutes`) | `upcoming` | `start_utc - 30 min` |
| 6 | `now < start_utc` | `starting_soon` | `start_utc` |
| 7 | `now < expected_end_utc + 30 min` (`live_end_grace_minutes`) | `should_be_on` (a `live` status that is untrusted, expired or unobserved lands here, never `live`) | `expected_end_utc + 30 min` |
| 8 | otherwise | `finished`, without `finished_at_utc` (probably finished) | none |

A `live` row's `display_state` replaces the event's when the row's `status_observed_at` is newer (the overlay rule of §4.2); B1G may delete its own clock rules for the states above and keep only the row-8-style fallback when it is past `state_until_utc` and no newer feed has arrived.

**Guarantees.** Every event in every day asset has:

- `competition_id`: the taxonomy id, or the catch-all `<sport>.other` (for example `football.other`) when the competition is not in the taxonomy. It does not change `tier`, which is still decided from the taxonomy, and it can differ from `category_id` (national-team categories).
- `status_normalized`: `scheduled` when the source gave none.
- `expected_end_utc`: the source's own end or start plus the sport default (§4.2). For `date_only` and `time_tbc` events it is only that default after the placeholder start below; do not show it.
- `status_observed_at` (as since 1.6).

**Time precision.** An event whose `start_precision` is `date_only` or `time_tbc` never carries a clock-looking `start_utc`: it is 00:00 Europe/London on its date (`T00:00:00+00:00` in winter, `T23:00:00+00:00` of the evening before in summer), it has no `end_utc`, and its day in the day assets is that London date. Show the date or "time TBC", never the clock. Other precisions (`scheduled`, `provisional`, `not_before`, `estimated`) carry real times, unchanged.

## 5. Rights and privacy (unchanged laws)

- Events are published only when the primary source and every fused contributor are listed in `publication_approvals`. Others are omitted and reported. This conservative source-level gate is not the complete per-field licensing model in the design.
- Since 0.3.23 the public feed is built from a merge of approved-source records only, so a fixture an approved source reports stays public when an unapproved source also reports it (audit C1). The published record then names the approved sources only. If the approvals change after the last collection, the feed falls back to dropping any fused event with an unapproved contributor until the next collection.
- Scores (§4.4) are published only for sources listed in `score_approvals`, which is separate from `publication_approvals`, empty by default, and limited to the eligible sources and sports of §4.4. An event's score also needs the event itself to be publishable under the rules above.
- Events use a **field whitelist** (`feed.EVENT_FIELDS`). EPG programme text, EPG-derived broadcast candidates, fetch scopes and live state never leave the HA box.
- `broadcasts` appear only when `broadcast_verified` is true, `broadcast_verification_rule` is `approved_v1`, and evidence is present. A reviewed independent rule and real evidence remain acceptance gates; a boolean alone is insufficient.
- Team crests are published as references only (§4.3, `rights.crests`), never as images, and only when the owner has set `publish_crest_refs` and approved an API-Sports source. API-Sports crest use is recorded as identification only, private household use, with the terms to be re-read and recorded by the owner (`SOURCE_REGISTRY.md`); until then the feed is monogram-only.
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
