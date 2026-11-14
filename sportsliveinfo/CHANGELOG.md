# Changelog

[SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) hosts the App source. [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is the separate feed repository.

## 0.3.15 — France and Europe: channel identification and live sport

- **Channel dictionary fallbacks**, tried only when a name does not resolve as written, and published in the dictionary asset so B1G applies the same rules:
  - Known alternative spellings: everywhere "Nat Geo" → National Geographic, "Nick Jr/Junior" → Nickelodeon Junior, "RMC Sports" → RMC Sport, "Euro Sport" → Eurosport; in France HD1 → TF1 Séries Films, Automoto → Automoto la chaîne, LCI - La Chaîne Info → LCI, Canal+ Cinéma → Canal+ Cinémas and others; in Germany Pro7 → ProSieben, Kabel 1 → kabel eins.
  - Singular/plural of the last word ("Sky Sport Top Events").
  - Language variants ("CGTN FR" → CGTN French, "Africanews" in a French list → Africanews French), only when the name carries the market code or is distinctive; short global brands such as CNN are never guessed.
  - Broadcast-area lookups now ignore spacing ("Euro Sport 1").
- **Closed channels are explained**, not left unknown: C8, NRJ 12, J-One, Game One, MCM, the OCS channels and others closed in 2023–2026; the dictionary gives the closure date and replacement.
- **Normalisation**: "4K Ultra", "(UHD/4K)", "Ultra HD" and "SD+" are quality markers; text mis-encoded via Windows-1252 ("ÃŽle-de-France") is repaired.
- **Live sport in French, German, Spanish and Italian guides**: sport words such as cyclisme, basket, Formule 1, hippisme, boxe, Pro D2, Ligue 1, Fußball, Radsport, baloncesto, pallavolo now classify guide-listed live sport.
- Measured on the owner's channel list (private): France resolves 65.5 % (60.2 % before); of 777 French linear entries 509 resolve, 46 are closed channels and 71 are event slots or Molotov virtual channels. UK and Europe overall 55.3 % (53.4 %): Netherlands 77.8 %, Poland 68.2 %, Spain 60.1 %, Portugal 52.3 %, Germany 49.7 %. Every new fallback match was checked by hand. UK live-sport benchmark unchanged.

## 0.3.14 — Private feed for your own TVs

- New optional **private feed** (Publishing page): a personal-use copy for your B1G televisions, published to a separate **private** GitHub repository after each publication. It holds every collected event (no publication approval needed) and the guide-listed live sport from 0.3.12, with the guide's channel names and programme times in each channel link.
- Uses the existing publishing token (add the private repository to it with Contents: Read and write). The TVs use a separate read-only token. The connection test and publisher refuse a public repository and refuse the public feed repository, so private data cannot reach a public location by mistake.
- The public feed is unchanged, and a private-feed failure never blocks it. The contract is documented in the feed contract §6.2.

## 0.3.13 — Publish channel links (owner decision D8)

- Published events now carry `broadcast_links`: the channels the guides list the event on, as SportsLiveInfo canonical ids with coverage (network or regional, `parent_channel_id`, `not_on`), confidence and the number of guides. No guide channel names, programme titles or programme times are published, and a link never marks an event as verified (`broadcast_verified` stays false).
- Feed format `sli/1.3` (new optional field; 1.x readers ignore it), capability `broadcast_links`, manifest `rights.broadcast_candidates = "channel_links_published_unverified"`. The event schema and feed contract (§6.1) document the field.
- Guide-listed events (0.3.12) remain private: their guide sources do not permit republication.

## 0.3.12 — Allocate live action from the TV guides

- **Guide-listed live sport.** Free event sources only cover a day or two ahead (API-Sports' free plan serves yesterday, today and tomorrow), so most of the week's live sport on UK channels had no event to attach a channel to. Live listings on recognised channels that no event matched now become private events with their channels: fixtures ("Spain v England", ITV1), sessions ("Grand Slam of Darts: Day 2", Sky Sports Main Event and Sky Sports+), with the same regional allocation as fixtures. They are shown in Live today and Sports events as "Listed live in TV guide".
  - The same broadcast in several guides or on several channels is one event; names written differently ("NY Rangers at Vancouver" / "Vancouver Canucks v New York Rangers", a truncated "Lionesse") are merged; women's and men's fixtures between the same teams stay separate.
  - When a feed event exists but its title differs from the listing, the listing's channels are attached to the feed event instead.
  - Never published: they come from guide programme text, so the feed excludes them, and "guide_listing" cannot be approved for publication.
- Registry: TNT Sports 5–10 by name in UK guides, Sky Mix (the free channel that simulcasts some WSL), Channel 4's regional names. "Rep. of Ireland" matches "Republic of Ireland"; "NY" matches "New York".
- Measured on three public UK guides for 14–20 November: live UK sports broadcasts allocated to a channel rose from 25 of 251 (10 %) to 234 of 244 (96 %; the total fell as duplicate guide slots merged). The labelled benchmark is unchanged (14 of 14 fixtures matched, no radio, shopping or +1 candidates).

## 0.3.11 — Correct regional channel allocation

- UK regional channels are modelled properly. BBC One/Two Scotland, Wales and Northern Ireland, ITV1 Wales, ITV Border Scotland, STV and UTV are separate services with a parent network; English regions carry network sport and resolve to the network id. A provider channel is never merged with another region.
- Events are allocated per region: the network id only when the guides show every observed nation carrying the event (a same-slot shortened title such as STV's "Nations Championship" counts as a simulcast). Nations that showed something else are listed in `not_on`; an event shown on one nation only is allocated to that nation (`coverage: regional`). Example from the 17 November guides: Wales v Portugal on BBC One Wales only (England had The One Show) was allocated to national BBC One in 0.3.10 and is now `gb.bbc.one.wales`, with BBC Two (England, not on BBC Two Wales/NI) and S4C.
- Registry additions: Sky Sports+ (previously unrecognised under its usual spelling), BBC Alba, BBC Scotland, and Irish channels (RTÉ One, RTÉ2, TG4, Virgin Media One) when listed in UK guides.
- Fixtures written after a competition prefix ("Northern Series: Wales v New Zealand", "Group A4: Norway v Wales") and Welsh home-nation names ("Cymru", "Lloegr") now match.
- The channels asset publishes the regional rules, parents and allocation rule so B1G applies the same model. Cross-language matching fixtures: "Sky Sports+" and "BBC One Scotland" now resolve to `gb.sky.sports.plus` and `gb.bbc.one.scotland`.
- Measured on the same public UK guides: 14 of 14 known live broadcasts still matched; 24 channel suggestions (S4C added for two Wales matches), all correct on a hand check.

## 0.3.10 — Stronger event-to-channel matching

- Sports fixtures are matched to guide listings with stricter team rules: distinctive team words and exact aliases are required, generic words ("North", "West") never identify a side, and women's and age-group variants must agree. A guide may add a club suffix the feed omits ("Cheltenham Town"), but never change it ("Manchester City" is not "Manchester United").
- Women-only competitions (WSL, NWSL, SWPL, WBBL, AFLW) count as the women's game even when a listing does not say so.
- Guide decorations are ignored when matching: trailing dates ("14.11"), "[NEW]"-style tags and league badges ("⚽ [EPL]").
- Radio, shopping, +1/+2 timeshift and wrong-sport channels are never offered as the live channel.
- Guide channels resolve through the broadcaster registry, the optional channel dictionary and the identity graph, with one id per service (e.g. every ITV1 region as `gb.itv.one`).
- Measured on three public UK guides for 14–15 November: 14 of 14 known live broadcasts matched (6 before), and all 22 channel suggestions were correct on a hand check.
- Channel suggestions stay private in the app. They are not published in the feed; that needs a separate owner decision.

## 0.3.9 — Repair Matt Huisman guide sources

- Point the New Zealand and Sydney XMLTV sources directly at their final raw GitHub URLs, avoiding the cross-origin redirects from `i.mjh.nz` that the collector correctly blocks.
- Retire the UK Sky source: `SkyUK/` is absent from the publisher's current root listing and returns 404. The available `SkyGo/` feed is New Zealand Sky Go, not a UK guide.
- Report blocked cross-origin redirects and unapproved HTTPS source URLs with explicit diagnostics.
- Validated the current New Zealand and Sydney files with the app's XMLTV parser: both contain programmes beyond 24 hours. Their current sizes remain within the default byte, expanded-byte and programme limits.

## 0.3.8 — UK and Europe channel identification

- New optional **channel identity dictionary** for UK and Europe, built from the public-domain iptv-org database. It is off until you enable it under Sources. When on, it downloads about 3 MB at most once a day, using conditional requests and keeping the last good copy.
  - It covers about 10,000 channels and 13,000 regional, HD and +1 feeds, with alternative names, rebrands, closures, genre and website.
  - Pan-regional channels such as beIN, DAZN and Eurosport are included through feeds that broadcast into Europe, with region codes expanded to countries.
  - It is published as feed asset `dictionary` (format `sli/1.2`, capability `channel_dictionary`). A reference resolver gives B1G the exact lookup order and confidence rules.
- **Measured on a real 7,701-channel UK and Europe lineup** (private, not committed): channels identified by name rose from 37.9 % to 54.8 %. Every one of 70 hand-checked matches was correct. Examples: France 50 → 61 %, Spain 0 → 59 %, Italy 38 → 72 %, Scandinavia 12 → 43 %.
- **Provider prefix grammar:** "|NO|", "VIP RU |", "C+PL|", "ES TI|", "[M+]", "(VF)/(OP)/(M)", "[IT-EN]" and "[Multi-Language]" are now understood. Mis-encoded accents ("DÃ©couverte") are repaired, broken-export fragments are removed, and French "et" is treated as "&". A bare country code such as "IT " is removed only when it matches the channel's own market, so "Al Jazeera" and "De Ochtend" are untouched.
- Guides that start with the standard `<!DOCTYPE tv SYSTEM "xmltv.dtd">` prologue are now accepted from every source; embedded DTDs and entities are still refused. This is the likely cause of the Matt Huisman Sky UK, NZ and Sydney and EPGShare NZ failures. Guide failures now give a specific reason: blocked declaration, not XMLTV, empty, not well-formed, or truncated.
- Retired four dead guides that iptv-org no longer hosts (HTTP 404): programme-tv and Télérama (France), Sky UK and Foxtel. iptv-epg.org and EPGShare cover the same markets. Retired sources disappear from saved choices automatically.

## 0.3.7 — Channel identity across guides

- New channel identity graph. After each guide refresh, channels in different guides that show the same programmes at the same times, and whose names agree apart from decoration (HD, TV, country prefixes), are linked as one service. B1G can then use another guide's data for a provider channel whose guide ID comes from a different guide family.
- +1 and +2 channels are detected from schedules shifted by exactly 60 or 120 minutes and published as timeshift links to their base channel.
- Never merged: +1/+2, Sports+/plus, channel numbers, UK regions (including ROI and Channel Islands) and language feeds. Different names with identical schedules (rebrands, aliases, sister channels) are listed for owner review on the EPG coverage page and are not published.
- New optional feed asset `identity` (`sli.identity/1`, capability `channel_identity`); feed format `sli/1.1`. Old readers ignore it. Only channel ids, names and timeshift relations are published; programme data never leaves Home Assistant.
- Channel names: the matching key now understands common provider conventions. It ignores a trailing "*", "(UK)", "(From 19:00 UK)", "(Live Event Only)", "(X)/(D)/(M)", " - HEVC", and 50fps/HDR/VIP/RAW anywhere in the trailing run. It also reads a leading "(FR)"-style country and decodes HTML entities. It keeps "(IE)" as the Irish feed, bracketed markets and cities, and beIN feed letters. Measured on a real household lineup (private, not committed), UK/IE linear name matches against three real guides rose from 25 % to 46 %. No published matching case changed.
- Every channel is kept. New reference display labels give a tidy base name plus variant tags (4K, FHD, HD, SD, HDR, fps, HEVC, Ireland, "from hh:mm", Events only, VIP/RAW/Backup/Alt, Alt feed, Source X/D/M). Identical visible names are numbered in provider order. The rules are published in the `channels` asset (`display_variants`) so B1G can follow them exactly. On a 27,084-entry lineup every entry kept a distinct label.
- Tested on three real UK guides (922 channels, 159,514 programmes). 181 services were linked across 402 guide channels and 59 timeshifts were found, with no false merges after manual review. 26 pairs were held back for owner review.

## 0.3.6 — Reliable publishing feedback

- Publish feed now runs in the background. The Publishing page shows progress, refreshes itself and reports the result. Previously the request blocked for 15–25 s with no feedback, repeated clicks queued, and a failure reason was lost when the browser stopped waiting.
- Every manual or automatic publication attempt now records its outcome in Diagnostics, on the Publishing page and in the App log.
- GitHub failures name the step that failed (reading the branch, uploading files, creating the commit, moving the branch), give the fix, and include GitHub's own short message.
- Test saved GitHub connection now proves write access with an unreferenced blob. No commit or file is created. A read-only token is reported before you try to publish.
- The Publish button explains, and is disabled, when first-run setup is not finished.

## 0.3.5 — Source connections and refresh budgets

- Reserve EPG requests for scheduled refreshes and distinguish deferred work from provider failures. Reuse unchanged guide downloads when validators are available.
- Report partial sports scopes, reuse recently fetched future dates and honour provider throttling. Cache Jolpica season calendars between collections.
- Test ATP, WTA and live tennis separately. Add optional PandaScore esports fixtures and source-scoped UK, US and Canada guide mappings.
- Match guide listings for upcoming events and show channel, region, guide start time and source. Add optional Open Boxing world title bout dates.
- Add the official British racing meeting calendar, per-source contribution counts and retry times in Diagnostics.
- Match named live tournament listings in golf, snooker, cycling, darts, athletics and horse racing, with checks for rounds, stages and variants.
- Explain missing guide data, dates outside guide coverage and matching listings on unmapped channels. Identify guide matches that share an upstream source.

## 0.3.4 — Collector and dashboard audit integration

- Keep group source saves and independent refresh actions. Add collapsible source settings, UK-date event filtering and pagination.
- Recalculate Live Today on view. Retain future fixtures when a provider omits them from a response of unknown completeness.
- Recover from scheduler errors, isolate corrupt guides, reject expired guide probes and reduce the number of guide payloads held in memory.
- Keep regional feed and sports coverage additions. Tighten fixture matching and add source health and publication diagnostics.

## 0.3.3 — Regional guides and fixture coverage

- Add five opt-in regional guides and expose generic-title gaps in full schedules.
- Add four selectable OpenLigaDB competitions and an optional keyed tennis adapter.
- Expire reported tennis live status when its observation becomes stale.

## 0.3.2 — EPG coverage repairs

- Replace unavailable EPG Share US1 and CA1 endpoints with US2 and CA2 under the saved source IDs.
- Add optional UK and Australian IPTV-EPG.org guides and the EPG Share US sports guide for private collection.
- Restore XML TV Fr and EPGTalk imports by removing their fixed XMLTV DTD marker before parsing. Other declarations and entities are still rejected.
- Set source-specific import limits from measured guide sizes.

## 0.3.1 — Home Assistant dashboard maintenance

- Label mixed fallback competition groups accurately and show when the Live today list is truncated.
- Display zero counts and distinguish incomplete programme coverage from missing channel identity.
- Show latest collection activity and label live statuses as of the snapshot refresh.
- Explain common EPG failures without logging raw provider exception text.
- Display date-only and time-TBC fixtures without an exact start time and exclude them from time-based EPG matching.
- Save keyless sports providers and private EPG guides in separate groups with Tick all controls.
- Raise only the Freeview download and XML TV Fr expanded-size caps to accommodate their listed files.
- Add Hong Kong Now Sports and beIN channel identities and reject conflicting explicit country prefixes. Display non-UK markets on provisional channel matches.
- Commit related dashboard snapshots together and show a collector failure if the combined write fails.
- Skip expired guide programmes before comparing fixture titles to programme text.
- Read dashboard snapshots together and fetch only provider timestamps where the feed health report needs no raw payload.
- Validate key changes before saving provider toggles, then save both together.
- Add manual Sports-only and EPG-only refreshes and show last-good imports, latest activity and local request budgets on source cards.
- Add a Live Today sport filter, prioritise live fixtures, collapse completed or disrupted results and flag prior-day snapshots.
- Keep the same App slug and persistent SQLite path for in-place updates. The feed fixture updates the producer version and channel registry.

## Documentation reconciliation — 12 November 2026 (no runtime version change)

- Reconciled all Markdown documents against source main `579541fa`; added a current-status authority and full document index, with historical audits explicitly labeled.
- Corrected private source/installation versus public daily-feed roles and removed instructions to make the source public. The operator guide uses private local App delivery.
- Recorded measured source inventory and the initial Python 3.12 validation: 86 tests attempted, 81 passed, five errors (three loopback binds denied). This was superseded by the follow-up correction below; earlier 7/19/43/55 receipts remain historical.
- Distinguished the local enrichment suggestion evaluator from an unimplemented public EPG programme contract, and source-implemented publisher from a deployed public feed. No runtime code, schema, fixture, HA setting, repository visibility or source-rights approval changed.

## Validation correction — 12 November 2026

- Fixed rights-feed test inputs to use production taxonomy classification and a pinned clock.
- Added a shared ingress-test transport that uses loopback where available and dispatches through the real HTTP handler/parser with in-memory streams when socket binds are denied; added forced-memory CSRF and origin tests.
- Python 3.12.15 compileall passed and all 88 tests passed. Real loopback transport remains unverified in this socket-restricted runner; see [current status](../docs/CURRENT_STATUS.md).
- Production runtime, schemas, golden fixtures, HA settings and repository visibility are unchanged.

## 0.3.0 — 12 November 2026

- Sports sources 4 → 16: new OpenF1, TheSportsDB (free public key; darts, snooker, golf, rugby, cricket, fighting and more), CricketData.org (Test matches per playing day) and API-Sports rugby, basketball (NBA/WNBA), ice hockey, NFL, baseball, AFL, handball, volleyball and MMA. One API-Sports key now serves every API-Sports sport. OpenLigaDB covers Bundesliga 1–3; Jolpica fetches next season from October.
- Sports taxonomy: 24 sports and 127 competition rows, including England (men), England Women, home-nation and U21 internationals, Premier League, Champions League, Europa League, Conference League, FA Cup, EFL Cup, Championship, WSL and Scottish football; ambiguous names are resolved per sport and country.
- New "Live today" Ingress page grouped by sport and competition, with a featured England / home nations / PPV row and live-state estimates; events page filters by sport, competition and team.
- Cross-source fixture fusion with corroboration count and start-time conflict flag; scoped partial saves keep the last good data per day/league/sport; parallel sports lanes with per-provider pacing.
- EPG feeds 4 → 27, including the B1G backup feeds (EPG Share UK1/US1, Matt Huisman Sky UK, iptv-org Sky UK/Foxtel, EPGTalk, IPTV-EPG.org) and HK, MY, GE (Setanta), IE, CA, AU, NZ, PT, PL, GR, SG and IN guides. All disabled by default; "verify" feeds must pass Test EPG.
- XMLTV now keeps sub-title, categories, live/repeat/premiere flags and channel icons. Channel identity covers 8 markets plus B1G's exact farleyflex tvg-ids; 41 lineup families (Sky Sports+, beIN, Setanta, Now HK, Astro, DAZN, ESPN+, Peacock, Kayo, Fubo, SSC, Fite, FloSports…) are reported per guide.
- Unverified EPG broadcast candidates for today's events, with hard negatives (highlights, repeats, wrong opponent, unrecognised channel); EPG-derived fields are stripped from publication.
- B1G feed format `sli/1`: taxonomy, channel registry and guide catalogue, eight daily event files, today grouping and source health, content-addressed under `v1/assets/` and referenced by `v1/manifest.json`, with compatibility rules so later coverage changes need no B1G release.
- Atomic publishing in one GitHub commit (Git Data API): only new assets uploaded, unchanged revisions skipped, last 10 manifests retained; local feed preview; optional auto-publish after each scheduled refresh.
- JSON Schemas, byte-exact golden fixtures and channel-matching parity cases for the B1G reader; 55 local tests pass. No live provider call, Docker build, HAOS install or publication was performed.

## 0.2.0 — 12 November 2026

- Add private multi-country EPG channel identity hints and forward guide coverage analysis (24, 72, 168 hours), with strict country, variant and name safeguards.
- Add UK/France EPG coverage page and a separate sport fixture/event viewer in the Home Assistant Ingress UI.
- Add optional no-key OpenLigaDB Bundesliga fixture adapter and Jolpica Sprint Shootout session support.
- Add one-call sports source connection tests and full EPG parser connection tests with quota accounting.
- Preserve last-good on stale guide and invalid/partially paginated provider responses; avoid duplicate refresh queues and excessive API-Sports repeat 7-day requests.
- Preserve all previously saved API keys/source settings during version migration.
- 19 local deterministic tests including private Ingress HTTP/CSRF smoke; actual Home Assistant OS and B1G device validation still pending.
- Experimental stage: **not a production-ready or comprehensive global coverage release**; no public HA ingress, no unapproved third-party EPG redistribution.

## 0.1.0 — 12 November 2026

- Initial installable Home Assistant OS App layout, Ingress interface and setup state.
- Persistent settings, quotas and independent local sporting / international EPG collection.
- Built-in UK/FR source registry; Jolpica, football-data.org and API-Sports adapters.
- Source-level last-good cache, scheduler, status and errors.
- Default-disabled outbound licence-gated GitHub publisher foundation.
- New SportsLiveInfo app icon and wordmark logo.

Not yet a worldwide-complete EPG/sports product or a verified B1G integration.

## Development integration hardening (unreleased / v0.3.0, 12 November 2026)

- Integrated Claude's unmerged v0.3 candidate sports/EPG source expansion, taxonomy, sli/1 contract and test fixtures.
- Fixed cross-process quota reservations, scheduler restarts, partial source data preservation, failed job reporting, API-Sports pages, XMLTV memory bounds, credential redirects and config validation.
- Public feed now rejects fused events contributed by unapproved sources; broadcaster claims need reviewed evidence, not a boolean alone.
- Added conservative non-destructive programme enrichment suggestions. The original B1G EPG remains authoritative.
- Added targeted regression tests; exact merged-branch Python suite and physical Home Assistant installation **not yet verified**. Keep experimental stage.

### Home Assistant installer hardening — 12 November 2026

- Add Supervisor-required Docker image labels (io.hass.version, io.hass.type and io.hass.arch) with version/architecture build arguments.
- Add static App packaging tests for Ingress-only configuration, private admin panel, logo/icon and store repository layout.
- Actual Docker build and Home Assistant OS install **still not executed**; experimental designation retained.
