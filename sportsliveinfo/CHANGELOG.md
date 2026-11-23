# Changelog

[SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) hosts the App source. [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is the separate feed repository.

## 0.3.30 — fix(logging): suppress /healthz spam, consolidate EPG family failures, enrich regression gate message

- **server.py** `log_message`: skip logging for `/healthz` requests (~720 redundant INFO entries/day from the 2-min supervisor poll)
- **engine.py** `_collect_epg_run`: demote per-source failure from WARNING→DEBUG; `_collect_run` emits one consolidated WARNING when any EPG sources fail (groups by family, lists names)
- **engine.py** `_publish`: attach recently-failed EPG source names to `PublishRegression.details`; `_publish_job` appends them to the blocked message so the cause is visible without log-diving

## 0.3.29 — fix(providers): reroute iptv_epg_* from iptv-epg.org (403) to epgshare01.online

## 0.3.27 — 20 Nov 2026: audit fixes (expected_end_utc gaps, year boundary, Z-suffix)

- **`EXPECTED_MINUTES` gaps filled:** `horse_racing` 300 min, `cycling` 300, `mma` 240, `aussie_rules` 150, `netball` 90; corrected `handball` 120→100, `volleyball` 150→120. B1G was showing wrong LIVE status for these sports.
- **Year-boundary fix in `names_past_year`:** used `window_start.year` instead of the programme's own `start.year` — wrong at the Dec/Jan boundary.
- **`expected_end_utc` Z-suffix:** now always `…Z` (was `…+00:00`), matching every other UTC field in the feed.
- **Python < 3.11 `fromisoformat` Z-guard:** `.replace("Z", "+00:00")` before `fromisoformat` in engine and feed.
- **Dead code removed:** redundant `db.commit()` in `storage._put()`, unreachable code after `return` in `server.e()`.
- Tests: `test_live_tiers_corroboration`, `test_event_titles_and_durations`, `test_history_display_state` updated; golden fixtures regenerated.

### owner decisions of 20 Nov 2026 (CA-09, CA-16, CA-17, CA-18; no version bump)

- **CA-09: no change (owner).** `LIVE_DAILY_BUDGET` (40) and the live candidate gating are untouched.
- **CA-18: `LIVE_REFRESH` 30 to 15 minutes.** An unchanged live status is re-stamped every 15 minutes, so LIVE no longer flickers (15 + 5 CDN + 15 poll is inside `LIVE_MAX_AGE` 45, which is unchanged; `refresh.live_stale_after_minutes` stays 45). No extra API calls. About 4 live commits an hour in play: the growth ledger now marks live-lane commits (`kind: live`), `feed.growth_report` gains `live_commits`, `live_per_day` and a separate `live_commits_per_day` budget of 60 (7-day average); `commits_per_day` (8) counts only the other commits, so the alert does not fire just because matches are on. Contract section 4.2, RUNBOOK section 3, OPERATIONS_HARDENING section 4.
- **CA-16: wrestling and sumo removed.** `providers.is_not_carried` (whole words WWE, WWF, AEW, NXT, TNA, wrestling, sumo, basho in sport, league or title) drops them in `thesportsdb_events` and again in `build_feed`, so no day, extra, live or history asset (also from snapshots collected before the upgrade) carries them. Boxing, MMA/UFC, BKFC and kickboxing are untouched, and the midnight `date_only` rule is unchanged.
- **CA-17: tennis.** (a) A tennis row with no final status is omitted from every asset once the collection time is past `expected_end_utc` + 30 minutes (`feed.tennis_lapsed`); never published as `finished`. (b) Tennis is core only for Grand Slams, ATP/WTA main tour, Davis Cup, Billie Jean King Cup, United Cup and the Olympics; ITF, Challenger, UTR, WTA 125, exhibitions and unknown tours are `extra` (`feed.tennis_tier`). Day assets are evaluated at collection time, so lapsed rows leave at the next collection, not at every live build (keeps live commits small). The first automatic publish after the upgrade may fall under the 20 % regression gate because past tennis rows disappear at once; a manual publish overrides.
- Tests: `tests/test_owner_calls_20nov.py`; live-lane tests updated for the 15 minute re-stamp. Golden fixtures regenerated: unchanged (they hold no tennis or wrestling).

## 0.3.26 — 20 Nov 2026 follow-ups: blocked-publish alert, crest toggles, seeded tables review and overrides

### Audit 20 Nov follow-ups (SLI side of `COMBINED_AUDIT_2026-11-20`; no version bump)

- **CA-08 F1 sessions published twice.** `linking._same_event` merges motorsport rows of one competition when both name the same session (own `session`, or one found in the title) within 90 minutes, or when one row names no session (TheSportsDB titles the weekend, for example "Las Vegas Grand Prix") and starts within 15 minutes of the other's session. A title that names a different session ("Reverse Grid Race") stays separate; two sessionless rows never merge. `tests/test_f1_practice_dedupe.py`.
- **CA-06 `refresh.collected_at`** (optional) and `refresh.collected_at_expected` in the manifest, and `collected_at` in the health asset: the last full collection (`sports` snapshot `generated_at`), not renewed by a live-lane publish. Contract section 3, schema, golden fixtures regenerated. B1G does not read it yet.
- **CA-07 rollback.** RUNBOOK section 5 rewritten (republish as a NEW revision); `tools/republish_revision.py` (dry run by default) builds that manifest; `tests/test_republish_revision.py`.
- **CA-03 dictionary budget.** Confirmed existing: parts splitter, 80% alert, plain `dictionary` alias when UK/Europe fits in one part. Added `tests/test_audit_20nov_sli.py` with the recorded live size (6,969,653 bytes, 83%) and a headroom test (fails when the recorded size plus 15% reaches the cap). B1G cannot read parts yet.
- **CA-12 crest preview.** The Publishing page says "Crest references: OFF/ON, N of M collected events would carry / carry crests" (`feed.crest_preview`). Enabling is still owner configuration.
- **CA-24** README, CLAUDE.md, CURRENT_STATUS and the contract header now say `sli/1.7` / 0.3.26 with the capability list.
- Not done at that point: CA-09, CA-18, CA-16, CA-17 (decided by the owner later on 20 Nov: see the Unreleased entry above), CA-19.

## 0.3.25 — 20 Nov 2026 release: history, scores, crests, standings, channel hints, health alerts, ops hardening

### Follow-ups: blocked-publish alert, crest toggles, seeded-table overrides (after 0.3.25 was cut; the lead bumps the version)

- **Health:** new advisory incident `publish_gate_blocked` for an automatic publish refused by the regression gate (previously stored only as publisher state `blocked`, with no notification). One de-duplicated Home Assistant notification naming events and guide-confirmed bindings before and after and the override (Publish feed now), dismissed on recovery; shown in Service health and `/healthz` `advisories`; never a 503. `publish_gate` now also stores the before/after counts.
- **Publishing page:** toggles for `publish_crest_refs` and `crest_device_lookup_thesportsdb` (attestation to switch on), read-only `binds_rule` / `rights_holder_prior` line.
- **Seeded tables:** optional config overrides `broadcaster_rank_override` and `rights_holder_prior_override` (JSON, validated on save, empty = built-in, feed byte-identical when absent) with a form on the Publishing page; owner review checklist in `docs/SEEDED_TABLES_REVIEW.md`. No wire change, golden fixtures unchanged, version not bumped.

### Owner statement 20 Nov 2026: scores and crest references on for fresh installs

- **Fresh installs:** `score_approvals` defaults to `["api_sports", "football_data"]` (the eligible football sources; other API-Sports products stay off) and `publish_crest_refs` defaults to `true`. This follows the owner's statement that rights are permitted for this application's use. Supplier terms were not independently read or verified. `docs/RIGHTS_RECORD.md` ("Owner statement 20 Nov 2026") records the statement and lists every kill switch.
- **Upgrades are unchanged:** a stored configuration that predates a key keeps the legacy value (`storage.LEGACY_ABSENT_DEFAULTS`: `[]` and `false`). A saved configuration keeps what was saved.
- **Unchanged:** `publication_approvals` stays empty by default, so nothing reaches the public feed until the owner ticks a source and attests. Eligibility validation is unchanged: TheSportsDB, Jolpica, OpenF1, MMA and every other ineligible source are rejected.
- **Kill switches:** an empty `score_approvals` or `publish_crest_refs: false` restores the legacy output byte for byte (tested). The golden fixtures are pinned to the legacy values in `tools/generate_feed_fixtures.py`, so `schemas/fixtures/` did not change.
- **Tests:** 9 new in `tests/test_owner_defaults_20nov.py`; 451 pass (442 before). Existing score, crest and golden tests that assumed defaults off now set them explicitly. No version bump.

### Yesterday history, display state, competition id and status guarantees (additive, `min_reader_minor` unchanged)

- **History (contract 4.5).** Manifest `window.history_from` (the London day before today) and the optional asset `events:<history_from>` (`required: false`, tier core, same `sli.events-day/1` schema, `history: true` on the manifest entry) carry yesterday's events with their last known status, including `finished` and, when scores are approved and known, the final score, and the guide-listed `broadcast_links`, so B1G can recognise a replay. Yesterday is never in `today` or in the required `events:<today>` asset. Collection: the first full discovery of each London day adds yesterday to the API-Sports plan (+1 request per enabled API-Sports product per day; more only if that day paginates; the learned free-plan window drops it when the plan does not cover it, and the product's quota reserve applies as for every other day) and football-data asks `dateFrom=yesterday` (same single request). Source snapshot retention is 3 days (was 2) so the day before yesterday is not lost at the boundary; the materialised window is yesterday..today+7 (dashboards list yesterday's events too).
- **`display_state`, `state_until_utc`, `finished_at_utc`.** Computed centrally from status, clock, `live_until_utc` and the expected end (rules and table in contract 4.5); day assets state it as of the collection that produced the event, `live` rows as of their build. Day assets stay byte-identical across live republishes.
- **Guarantees.** Every event has `competition_id` (catch-all `<sport>.other` when the taxonomy does not know it; the tier is still decided from the taxonomy, so the catch-all does not make an event core), `status_normalized` (default `scheduled`) and `expected_end_utc` (sport default; now also for date-only events, as a placeholder). `date_only` and `time_tbc` events carry `start_utc` = 00:00 Europe/London of the date (was noon UTC) and no `end_utc`.
- Schemas (events-day, live, manifest), golden fixtures (a finished match yesterday with its channel link, a date-only event) and `tests/test_history_display_state.py` updated; no version bump, `format` stays `sli/1.6`.


### Event metadata, feature ranking and F1 weekends (all optional, `sli/1.6`, `min_reader_minor` unchanged)

- **Taxonomy:** `icon_key` on every sport and on competitions that have an emblem; `default_sport_order` (all `b1g_priority_group` values, including Horse racing, Handball, Volleyball, Esports, Bowling, Netball, Australian rules football and Other sport), also `display_policy.sport_order`; `display_policy.featured_competition_ids`, `featured_event_count` and `ranking.rule`.
- **Events:** `participants_short` for every event with participants (source's own kept, otherwise derived); `participant_ids` (`apisports:football:42` or `key:<name>`); `competition_logo` `{src, ref}` from the API-Sports league id, gated by the same crest switch (`publish_crest_refs`) and `url_template`, capability `competition_logos`; `feature_rank` 0-100 on every event; `ppv` and `ppv_label` for boxing and MMA PPV cards; F1 `session_label` and `weekend_id`.
- **Today:** `featured_event_ids` is now the top 10 by `feature_rank` (was: every featured-tag event); new `ordered_event_ids`, `today_extra_ids` and `today_extra_summary`.
- **Tags:** nation detection accepts "England Rugby", "England XV", "England Men", "England Under 21", "Scotland (W)"; the live "0 of 121 tagged" could not be reproduced offline.
- **Extra tier:** policy reviewed and unchanged (youth and reserve football stays extra, nothing dropped, ids stable); extras are summarised in `today`.
- **Capabilities:** `taxonomy_icons`, `participant_metadata`, `feature_rank`; `competition_logos`, `ppv_flag`, `f1_weekends` when present. Schemas updated; golden fixtures regenerated (an F1 weekend was added to the fixture day); contract section 4.3 documents the exact semantics. Tests: 27 new in `tests/test_event_metadata.py` (469 pass). No version bump.

### League standings asset (`standings:<competition_id>`, capability `standings`, on by default)

- **New optional asset kind** `standings:<competition_id>` (schema `sli.standings/1`, `required: false`): season, groups of rows (position, team name, `participant_id` `fd:<id>`, played, won, drawn, lost, goals for and against, goal difference, points, optional form), `table_complete`, `expected_teams`, `observed_at`, `source`. Cup groups are named groups; the Champions League league phase is one table with a null group name. Nine competitions: the six B1G leagues (Champions League 36, Premier League 20, La Liga 20, Serie A 20, Bundesliga 18, Ligue 1 18) plus Championship 24, Eredivisie 18, Primeira Liga 18. About 4.5 KB per 20-team table, far under the 8 MiB reader cap. Additive: no format minor change. New contract section §4.6.
- **Source.** football-data.org free competitions (`/v4/competitions/<code>/standings`), read by the 04:00 refresh (the first collection of each London day) through the existing key, pacing and shared 429 backoff. Own counter `standings:football_data` (12 calls a day, nine needed), never into the last 10 of the source's 45 daily calls. A failed refresh keeps the last good table; a competition the plan refuses (403/404) is skipped for 3 days; an incomplete answer never replaces a complete table of the same season; tables older than 7 days are no longer published.
- **Optional API-Sports standings** only with config `standings_api_sports` (default false), only for a competition football-data.org did not supply completely, own counter `standings:api_sports` (4 calls a day), never into the 20 calls kept for the live lane.
- **Rights and kill switch.** Config `publish_standings` (default true, per the owner's statement of permission; Ingress → Scheduler → League tables). Off, or no table within 7 days: no assets, no capability, no `compatibility.standings`, no `rights.standings`, and nothing is collected. While on, `rights.standings` carries the master switch, `max_age_days` and the attribution ("Football data provided by the Football-Data.org API"), also added to `rights.attribution`.
- **Fixtures regenerated** (`schemas/fixtures/sli-v1` and `sli-v1-scores`: a complete synthetic Premier League and a partial Champions League table, decoded from stub payloads by the production decoder); schemas `sli-standings.schema.json` and `sli-manifest.schema.json`; `docs/SOURCE_REGISTRY.md` and `docs/RIGHTS_RECORD.md` §7 rows.
- No version bump. The football-data.org and API-Sports payload shapes follow the public documentation and are **not verified against a live response**; Home Assistant verification **NOT RUN**. The B1G reader change (drop Highlightly, ESPN and Pulselive standings clients, copy the regenerated fixtures to B1's `sli-v1-6` test resources) is NOT DONE.
- Gate: `python3 -m compileall -q sportsliveinfo/src tests` and `PYTHONPATH=sportsliveinfo/src python3 -m unittest discover -q -s tests` passed, 469 tests (27 new in `tests/test_standings.py`).

### Operations runbook and documentation consolidation (docs only)

- **New [`docs/RUNBOOK.md`](../docs/RUNBOOK.md):** feed stalled (manifest age, Diagnostics, job rows, `/healthz`), GitHub token expiry, quota counters, the publish regression gate and its manual override, rollback, the exact kill-switch config keys, App backup, checks after an update, and who to ask. Each step was traced to the code.
- **Gaps recorded there, not fixed:** the App cannot republish an earlier revision (rollback is a manual git procedure); at the time of writing there was no standings source, counter or kill switch (since added by the standings asset above); the crest keys have no UI; a regression refusal does not raise the publish-failure notification.
- **Moved:** `docs/CODE_AUDIT_AND_FIXES_2026-11-13.md` to `docs/archive/` (superseded by the 15 November audit). Its two inbound links are updated. No code changed.

### Scores per source behind a rights flag (feed `sli/1.7`, default off at the time; see the 20 Nov entry above)

### Narrow binds rule, channel hints, link coverage (S2, additive `sli/1.6`, no version bump)

- **Binds rule ([contract §4.3](../docs/FEED_CONTRACT_SLI_V1.md)).** `binds` = guide-corroborated, or (identity confidence high AND a curated registry channel AND the channel's market is the owner's market or one of the event's home markets). New optional link field `home_market`. Weak foreign listings (`NBCUniverso.us` for Bayern v Köln, `hk.bein.*`, `nz.sky.sport.*`) are still listed and ranked but no longer bind. Config `binds_rule` ("narrow" default, "legacy" kill switch; invalid values are refused on save and read as "narrow"), published as `compatibility.binds_rule`. Staging: `link_report.dry_run_binds` and `tools/link_report.py --db <sqlite>` report binds true->false per market and the demoted links on a stored snapshot; the optional `health` asset carries the same counts (`binds_dry_run`, ids only) next to `link_coverage`. The default was switched to narrow only after the dry-run output was produced in `tests/test_binds_hints_coverage.py` (8 synthetic links: 8 legacy binds, 3 narrow, 5 demoted: hk 2, ie 1, nz 1, us 1; golden fixture: 0 demoted).
- **Channel hints.** New optional asset `channel_hints` (`sli.channel-hints/1`, capability `channel_hints`, ~18 KB): per curated channel `sports_class`, `tier`, `broadcaster`, `sports`; per-sport `broadcaster_rank` (GB) seeded from the owner's B1G tiers and `UK_BROADCAST_MATCHING.md`; `competition_rights`. B1G can later delete `SportsChannelPriorityPolicy` keyword tiers.
- **Slot hint.** Optional event field `slot_hint` (`starts_from_utc`, `starts_to_utc`, `match`) on events with links: the corroboration window, derived from the event's own start.
- **Link coverage.** `health.link_coverage` publishes the per-event gap reason histogram (core and extra) that was only in the Home Assistant snapshot. German exonym and club-form aliases (Koeln/Köln/Cologne, Nuernberg, Gladbach, Muenchen, Kiev/Kyiv, Bruges, Prague, Vienna, PSG, Sporting CP, Hertha, prefixes Borussia/Eintracht/Bayer/Olympique/RB/TSG, founding numbers 04/05/07/96/98 ignored by the guide-title check only): 10/23 labelled guide-title cases correct before, 23/23 after, with 9 must-not-match cases still unlinked.
- **Own EPG.** Sky's own EPG family (`sky_epg`) alone corroborates `gb.sky.*` channels (`verification: broadcaster_own_epg_v1`; never other broadcasters' channels; config `own_epg_corroboration`). **Rights-holder prior** links (`status: rights_holder_prior`, never binding, Saturday 3 pm blackout guarded) are implemented but OFF by default (`rights_holder_prior`).
- Schemas: new `sli-channel-hints.schema.json`; events-day, health and manifest schemas extended. Golden fixtures regenerated. Tests: `tests/test_binds_hints_coverage.py` (30 new) and deliberate updates to `test_live_tiers_corroboration.py` and `test_feed.py`.

### Operations hardening: deadlines, bounded memory, asset parts, history budget, CI, release tooling

Audit 15 Nov O1, O3, C4, C10. Details and owner steps: [`docs/OPERATIONS_HARDENING.md`](../docs/OPERATIONS_HARDENING.md). No version bump; no change to the golden fixtures (the new feed fields appear only when a size or growth limit is near).

- **A slow upstream cannot hold the collector (O1).** Every fetch has a 120 s wall-clock deadline (read in 64 KiB chunks, the per-read 30 s timeout kept), every source collection 900 s and every collection 2700 s. A lane still running at the collection deadline is abandoned: the busy lock is freed, the finished lanes are still materialised, the `collector` job reads `stuck` and health raises `collector_stuck` (advisory notification). Failures read "Upstream too slow". Tests with a fake one-byte-per-20-seconds stream and a hung lane.
- **Memory (C4, O3).** One XMLTV parse at a time process-wide, with a bounded wait; programme descriptions (never read) are no longer kept; linking now streams guides one at a time as slim records (`linking.GuideStream`), with the full coverage span preserved so gap verdicts are unchanged. Tests: bounded concurrency (limit 1 and 2, release on failure, clean timeout), one guide alive at a time, identical links/gaps/guide map against the dict path.
- **Asset size (C10).** The dictionary (and guide map) over the 8 MiB reader cap is published as parts, never silently dropped: `dictionary:uk-eu`, `dictionary:world-<region>` (`-2`... when a group is still too large) and `guide_map:<n>`, each a complete document with `part` metadata and under the cap (cut at 75%), capabilities `channel_dictionary_parts` / `guide_map_parts`. A dictionary that fits is published as before; when the UK/Europe part fits alone, the old `dictionary` kind also points at the same file for deployed TVs. At 80% of the cap: manifest notice, optional `health.asset_budget`, and a `asset_size` Home Assistant notification. Contract §2.1 and the manifest, dictionary, guide-map and health schemas updated (all additive).
- **History growth (C10).** A per-commit ledger and a documented, tested budget (8 commits a day, 1 GB of new blobs a year); health raises `feed_growth` when exceeded. The yearly squash procedure is written down for the owner. Not done: bucketing `guide_map` counts.
- **CI.** `verify.yml` now also compiles tests and tools, runs pyflakes (four unused names fixed), parses every `schemas/**/*.json`, checks the three version files agree, and fails when `tools/generate_feed_fixtures.py` changes committed fixtures.
- **Release tooling.** `tools/bump_version.py` updates `config.yaml`, the Dockerfile and `__init__.py` and writes the CHANGELOG heading (`--check`, `--dry-run`); a unit test and CI keep the three in step.
- **Dead-man example for the public feed repository.** `docs/examples/liveSports-epg-deadman.yml` (not installed): every 30 minutes, opens one issue when `generated_at` is older than the last scheduled slot plus 3 hours, closes it on recovery. Install steps in the operations document; decision logic tested.
- Tests: 481 pass (39 new in `tests/test_ops_hardening.py`; one assertion in `tests/test_feed.py` changed from "dictionary skipped" to "dictionary published as parts").

### Scores per source behind a rights flag (feed `sli/1.7`, default off)


- **Nothing is published until the owner approves a source.** New config `score_approvals` (list of source ids, default empty, separate from `publication_approvals`; Ingress → Publishing → Score approvals, with an attestation checkbox). Eligible: the API-Sports products except MMA (live and final) and football-data.org (final scores of regular-time results only). TheSportsDB, Jolpica, OpenF1 and every other source are rejected by validation. The owner must still read each source's terms and approve.
- **Disabled means byte-identical.** With no approved source the manifest is still `sli/1.6`, there is no `score` field, no `scores` capability and the revision hash is unchanged (the golden `schemas/fixtures/sli-v1` fixtures did not change). With approved sources the manifest is `sli/1.7` (`min_reader_minor` unchanged), capability `scores`, `compatibility.scores` and `rights.scores.approved_sources`; removing the approvals is the kill switch.
- **Wire (additive):** optional event and live-row `score` = `{home, away, period, observed_at, source}`; `home` is `participants[0]`'s score, `away` `participants[1]`'s, no minute; periods `1H HT 2H ET PEN FT AET Q1-Q4 P1-P3 OT` or null. Day assets carry a finished event's final score; the live asset carries live scores and a final score read after the event. Contract §4.2, §4.4 and §5, the sli-live, events-day and manifest schemas and the Ingress text were updated (the old "No scores are kept" wording is gone).
- **Sports:** football, rugby, basketball, ice hockey, American football, baseball, handball, AFL, and volleyball as sets won. Tennis, cricket, golf, F1, boxing and MMA never carry scores.
- **Plumbing, no extra API calls:** the decoders keep the goals and scores the boards already return; the live lane stores a score with its status observation and treats a changed score as a change (so it republishes the live asset, subject to the same quiet-slot guard and regression gate); the settle pass stores the final score with the final status; materialisation folds observations into the records. Commit volume: with scores on, at most one extra commit per 15 minute pass while play is in progress (a higher scoring sport can change every pass); with scores off, none.
- **Alignment:** when sources merge, each contributor's score is re-expressed in the merged event's participants order (swapped, same, or dropped when the pairing is uncertain, for example two sides with identical keys). Disagreeing final scores from two approved sources publish nothing.
- Fixtures: `tools/generate_feed_fixtures.py` also writes `schemas/fixtures/sli-v1-scores/` (a `sli/1.7` variant: a football match reported by two sources in opposite order, plus a live rugby score). Tests: 30 new in `tests/test_scores.py` (Ingress form, decoders, alignment and swap, disabled identical, kill switch, excluded sports, periods, live republish, settle final score).
### Live status expires; manifest declares the live lane; publish regression gate

- **Stale "live" no longer lingers.** `live_document` now takes the build time and drops rows whose `live_until_utc` has passed. The live lane downgrades any stored `live` observation older than 45 minutes to `unknown` with no API call, counts it as a change, and so republishes.
- **Manifest (additive, `sli/1.6`, `min_reader_minor` unchanged at 0):** `refresh.live_stale_after_minutes` (45) and optional `refresh.live_lane` (`enabled`, `interval_minutes` 15, `active_only_while_events_in_play`, `quiet_slots_guard_minutes` 3, `last_run_utc`). Schema and contract §4.2 updated: the 15 minute cadence applies only while events are in play.
- **Pre-publish regression gate.** Automatic publication (after a collection or a live change) is refused, with the previous feed left live, when events or guide-corroborated bindings fall by more than 20% against the last published feed (`PUBLISH_REGRESSION_THRESHOLD`; baselines under 5 are ignored). The refusal is logged, recorded as a `publisher` job in state `blocked`, stored in `publish_gate`, and shown as the last publication attempt. A manual publish overrides.
- Golden manifest fixture regenerated. Tests: 335 pass (6 new; baseline 329).
### Cross-source duplicate fixtures merge across club-name forms

- **Before:** `same_team` only allowed generic words to differ, so real duplicates stayed as two rows: "Arminia Bielefeld"/"DSC Arminia Bielefeld", "Havelse"/"TSV Havelse", "Heidenheim"/"Heidenheim 1846", "Espanyol"/"RCD Espanyol de Barcelona", "Estac Troyes"/"ES Troyes AC", "Union Berlin W"/"Union Berlin Frauen".
- **Now:** club-form prefixes (dsc, tsv, vfl, vfb, fsv, ssv, spvgg, rcd) are ignored; a four-digit founding year may be dropped (never the only difference between two different years); frauen/damen/feminin* mean women; Koeln/Cologne, Nuernberg/Nuremberg and Gladbach/Moenchengladbach are one team each; Troyes spellings are aliased (team spellings live in `linking`, the dictionary aliases only rewrite channel names).
- **Anchored rule** in `_same_event`: kick-offs within 15 minutes, same sport, compatible competition, one side equal and the other a strictly contained shorter name. Women, youth, reserve and squad words (U21, II, Castilla, ...) and rugby-only words (RC) still block it.
- Not changed: contract, versions. Tests: 343 pass (14 new in `tests/test_event_dedupe_names.py`).
### Settle pass: events that ended are settled by the provider's final status

- **Before:** collection fetched only `date>=today` at 12:00 and 17:00 and the live lane watched only start..expected end + 30 min, so an event that ended stayed `scheduled` (or fell to `unknown` when it left the live board) until it dropped out of the window; nothing ever said `finished`.
- **Now:** for events past expected end + 30 min (and at most 12 h after that) whose status is not final, the engine makes at most one `date=<London start day>` call per API-Sports product per hour, only while unsettled events exist, decodes it with the existing decoders and stores an explicit `finished`, `postponed` or `cancelled` as a `live_observation`; the `live` asset then carries that row. Leaving the live board still never means finished: absence from the response, or any non-final status, writes nothing.
- **Quota:** own counter `settle:<product>`, 4 calls a day per product (also counted in the product's quota), same reserve check as the live lane (`usage >= daily_limit - 20` skips), provider back-off and plan-window checks. Counters are shown on the Live status lane card and in the usage table. Estimate: at most 4 extra calls per product per day (a paged response costs one call per page).
- No wire change: the `live` schema already allows `finished`, `postponed` and `cancelled`; no new fields, providers or secrets. MMA has no live board and is not settled.
- Tests: 340 pass (11 new in `tests/test_settle_pass.py`).
### event titles, status defaults and expected durations

Mechanical clean-up from the event-source review. No contract field is added and no version is bumped; the wire changes are titles, a status default and the expected end.

- **F1 sessions are titled by session.** Jolpica titles are now "<race name> — Race", "— Practice 1", "— Qualifying" and so on (were the race name for every session). The `session` field is unchanged and is what EPG matching uses.
- **F1 status is always published.** Jolpica and OpenF1 sessions are "scheduled". OpenF1 is "finished" only when the provider's own `date_end` has passed.
- **Missing status defaults to "scheduled".** Any event published without `status_normalized` now carries "scheduled" (it previously carried nothing).
- **CricketData placeholders.** When both teams are "TBC", "TBA" or "to be confirmed", there are no participants and the title is the name's first part, not "Tbc v Tbc". A placeholder first part falls back to the competition.
- **TheSportsDB day-only times.** A `strTimestamp` of `T00:00:00` for golf, snooker, darts or motorsport is `date_only` at noon UTC. Other sports keep the stated time.
- **Expected durations.** F1 practice and qualifying 90 minutes; handball 120; volleyball 150; knockout football (round of N, quarter, semi, final, third place, play-off stages) 150. The defaults and all other sports are unchanged.
- Tests: 338 pass (329 existing plus 9 in `tests/test_event_titles_and_durations.py`). Two existing duration assertions were changed deliberately (handball 180 to 120, F1 qualifying 180 to 90).
- Golden feed fixtures regenerated: the only change is `status_normalized` on one event asset and the manifest hash.
### Team crest references (capability `team_crests`, off by default)

- **References, not images.** The API-Sports decoders carry each side's team id; the merge aligns them to the merged `participants` (home/away swaps handled with `same_team`; a side is `null` when contributors disagree or orientation is uncertain). The feed publishes `participant_crests` (index-aligned, `{"src":"apisports","ref":"football/teams/42"}` or null) only when `publish_crest_refs` is true AND an API-Sports source is in the publication approvals. Default false: no event field changes, so asset hashes and the revision are unchanged.
- **Master kill switch in the manifest:** `rights.crests` (`sources.apisports.enabled`/`url_template`/`attribution`/`cache_days`, `device_lookup.thesportsdb`, `monogram_only`) is always present; the `team_crests` capability is listed only when enabled. SLI never fetches, stores or mirrors a crest image. Additive; `min_reader_minor` unchanged; no version bump.
- Owner to verify the API-Sports terms for crest use before setting `publish_crest_refs`. Tests: 15 new in `tests/test_crest_refs.py`.
### Stall alerting and a real `/healthz`

Cause: on 20 Nov 2026 the manifest stayed at 03:42Z for 3.5+ hours (the 04:00 collection did not publish; cause unproven) and the owner was not told. `/healthz` always answered ok, the watchdog only checked the TCP port, and there was no Home Assistant notification code.

- New `health` module: last successful collection, last publication, manifest age, failing sources, GitHub token expiry (from GitHub's response header), live-lane budget use and scheduler heartbeat age.
- `/healthz` answers 503 with a JSON reason when the scheduler heartbeat is stale or a scheduled refresh slot passed more than the threshold (default 3 h) with nothing published; hysteresis stops flapping. `?scope=liveness` is the heartbeat-only check now used by the Supervisor watchdog (HTTP instead of TCP).
- One Home Assistant persistent notification per incident (stalled, publishing failing, token expiring, source failing repeatedly, collection stuck), dismissed on recovery; notification errors are swallowed and logged without secrets. New permission `homeassistant_api: true`; new option `stall_threshold_hours`.
- Diagnostics shows the same data; a banner appears on every page while stalled.
- Not included: Home Assistant sensor entities (not restart-safe through the REST API).
- Tests: 354 pass (25 new). No version bump.
### Other changes

- **Documentation only.** New [`docs/RIGHTS_RECORD.md`](../docs/RIGHTS_RECORD.md): publication status per source and data kind, the kill-switch for each, and an owner checklist. The repository records no supplier permission; provider terms could not be read from the cloud session.
- **Status corrections.** Test count on 0.3.24 is 329 (re-run on `origin/main` 8da6e83); the repository is public, not private; API-Sports is "used by the running collector; owner approval not recorded". No code, schema or version change.

## 0.3.24 — The right channel first; re-runs are not live; TVs follow SportsLiveInfo's decisions

Owner report 15 Nov 2026: Scotland v Australia and Spain v England showed an Irish or Asian channel before ITV1, and Pluto's re-run of "England v Samoa — Rugby World Cup 2023" was "probably live". ITV1 had been found (five guides; corroborated for Spain v England) but was listed last.

- **Channels are ranked by evidence, not alphabet.**
  - **Before:** candidates and published links were sorted by channel id. Capitals sort first, so any dictionary id ("VirginMediaTwo.ie", "PremierSports1Asia.ie") came before every curated id ("gb.itv.one"), and the Home Assistant page showed that channel first.
  - **Now:** best first: guide-corroborated, then UK channels, then curated registry channels, then more independent guides, high confidence and network coverage. The Home Assistant page labels a corroborated first channel "Guide-corroborated" and shows the right market (GB, IE, NZ) instead of the id.
- **Re-runs are never live.** A listing that names a past year or season ("Rugby World Cup 2023", "2023-24") is treated as a repeat. Current seasons ("2025/26") and future years are unaffected.
- **Free streaming channels keep their own identity.** Pluto TV, Samsung TV Plus, Plex and Roku guide channels are identified by the curated registry only; a dictionary name match had made Pluto's "Rugby Pass TV" into Premier Sports 1 Asia (also in the guide map B1G uses).
- **Rugby duplicates merged.** "Scotland Rugby vs Australia Rugby" and "Ampthill RUFC" (TheSportsDB) now merge with the API-Sports fixtures; rugby suffix words are ignored for rugby only.
- **TVs follow the feed** ([contract §4.3](../docs/FEED_CONTRACT_SLI_V1.md)). Links are published best first with `rank` and `binds`, and live events carry `live_until_utc` (also in the `live` asset); the manifest declares `link_order: best_first` and the live limits. With the matching B1G update (once), ranking, binding and the LIVE window are decided here and later corrections need no TV update. Older readers ignore the new fields.
- Version 0.3.24 everywhere; schemas, golden fixtures and the feed contract updated.
- Tests: 329 pass (14 new, built from the reported cases).

## 0.3.23 — Honest live state, a light live-status lane, approved fixtures kept, tiered "today", guide-corroborated links (feed `sli/1.6`)

From the [15 November forensic audit](../docs/AUDIT_2026-11-15_FORENSIC_SPORTSLIVEINFO.md) (C1, C2, C6, C9) and the feed contract agreed with B1G on the same day. The feed format is now `sli/1.6`; every change is additive, so a 1.5 reader keeps working.

- **"Live" can no longer be stale or false (C2).**
  - **Before:** an event's status was a snapshot from the 04:00, 12:00 or 17:00 run, and the reader trusted it. A started cricket Test became five "live" day records.
  - **Now:** every event carries `status_observed_at` (when its status was last read) and `expected_end_utc` (start plus a typical duration for the sport, or the source's own end). The manifest rule says "live" is trusted only when the observation is at most 45 minutes old and the time is between the start and 30 minutes after the expected end; otherwise readers show "should be on now", never "LIVE". Only the Test day in play is live; later days are scheduled.
- **A merged event takes the most advanced, most recent status (C9).**
  - **Before:** it took the status of its most precise record, so a delayed football-data "TIMED" hid API-Sports "1H" or "FT".
  - **Now:** finished, postponed or cancelled outrank live, which outranks scheduled; ties go to the most recent observation.
- **API-Sports live codes are understood (C6).** Ice hockey periods (P1–P3, OT, PT, BT), baseball innings (IN1–IN9 and extra innings), volleyball sets (S1–S5), MMA (IN, EOR) and AFL quarter time (QT) read "live" instead of "unknown". The codes are kept per product, so MMA's "IN" never changes another source. A test covers every product.
- **A light live-status lane.**
  - While the collected feed has an event between its start and expected end, SportsLiveInfo reads the API-Sports live board at most every 15 minutes: `fixtures?live=all` for football and `games?live=all` for the other team sports (the MMA API has no live board).
  - At most 40 calls a day per product. They count in the product's own daily quota, and 20 calls are always kept for the scheduled refreshes. Provider back-off and the learned plan dates apply, it stays quiet for 3 minutes either side of a scheduled refresh, and a product that refuses the live board is not asked again for 3 days.
  - Status changes go into a small optional `live` asset. With automatic publishing on, a commit then uploads only that asset and the manifests; unchanged assets are reused. An event that leaves the live board becomes "unknown", never "finished". No scores are kept.
  - On by default once an API-Sports key is saved; switch it off on the Scheduler page. Its last pass and calls are shown there and in Diagnostics.
- **Approved fixtures no longer vanish from the public feed (C1).**
  - **Before:** a fixture was dropped from the public feed when any source that also reported it was unapproved, so switching on a private source silently removed approved fixtures.
  - **Now:** the public feed is built from a merge of approved sources only; the private feed keeps the full merge. A published record still names approved sources only. If approvals change after the last collection, the feed falls back to the old fail-closed filter until the next collection.
- **Tiered public "today".** Each event is `core` or `extra`. Core: named competitions, internationals, featured nations, PPV, the main non-football sports, and football leagues and cups of the UK, Ireland and France (youth competitions excepted). The day assets and `today` carry core events; the long tail moves to optional `events_extra:<date>` assets. The manifest reports both counts. An optional asset over the 8 MiB reader limit is now reported in the manifest notices instead of being skipped silently.
- **Guide-corroborated broadcast links.**
  - A link becomes `guide_corroborated` when the strict matcher found it, the programme starts between kick-off − 60 and + 20 minutes, the channel is a curated registry channel and at least two independent guide families list it. `broadcast_verified` stays false. The manifest counts these links.
  - The guide families were audited from each publisher's own files: farleyflex is a mytelly grab; Freeview-EPG (dp247) and M3UPT both come from Sky's own EPG, so they now count as one family; EPGTalk is Schedules Direct data. Guides whose upstream could not be checked (EPG Share, IPTV-EPG.org, Fazzani/grab, dobleM) never count towards the two.
- Version 0.3.23 everywhere; schemas, golden fixtures and the feed contract updated (new schema `sli.live/1`).
- Tests: 315 pass (25 new).

## 0.3.22 — Forensic audit fixes: private feed guard, channel-list privacy, no loose channel links in public

From the [15 November forensic audit](../docs/AUDIT_2026-11-15_FORENSIC_SPORTSLIVEINFO.md). Every fix was checked against the code and has a test.

- **The private feed can never be published to a public repository.**
  - **Before:** the private/public check ran only in the connection test, and the publisher itself never repeated it.
  - **Now:** every publish re-checks the destination's name and visibility first, and publishes nothing if the private repository has become public or the name is wrong. The public feed is checked the same way.
- **Your channel list never stores stream addresses.**
  - **Before:** a list without an M3U header in its first 50 lines (leading blank lines, indentation or a bare list of URLs) could store stream URLs, which may contain your provider login, as channel names on Home Assistant.
  - **Now:** the M3U header is recognised anywhere in the file, and any URL or credential line is dropped.
- **No loose channel links in the public feed.**
  - **Before:** links found only by the looser guide-listing matcher could name the wrong match. It was reproduced: "Man City v Liverpool" at 14:30 was linked to Manchester United v Liverpool at 17:30.
  - **Now:** those links stay in your private feed until that matcher is made strict.
- **Open items** (prioritised in the audit):
  - approved events lost when an unapproved source corroborates them;
  - stale "live" states;
  - guide memory use on the mini PC;
  - a collector that a slow host can hang;
  - backups and observability.
- Tests: 290 pass (5 new).

## 0.3.21 — API-Sports stops asking for dates the plan cannot read; TheSportsDB fills the week ahead per competition

- **Measured on the live feed (15 November, 04:15):** every API-Sports source (football, basketball, rugby, hockey, handball, volleyball, NFL, baseball, AFL, MMA) returned events for today and tomorrow only. The other five days of each run were refused with a plan restriction, so every one of them was reported "partial". The once-a-day full discovery was never recorded, and the refused days were requested again on every run.
- **Fix:** when API-Sports refuses a date with its plan message ("try from … to …"), SportsLiveInfo reads just the two dates and remembers which days the key can read. Days outside that window are no longer requested and are not counted as failures, so the source reports "ok". The window is forgotten after 3 days, so an upgraded plan is picked up by the next full discovery. Only the dates are taken from the message.
- **Effect:** about five wasted requests per API-Sports source per run are saved, out of a 100-a-day quota per sport. Source health stops showing "partial" for a normal free key, and the job summary says "N outside the provider plan's dates".
- **Week ahead from TheSportsDB, per competition.** TheSportsDB's documentation (checked 15 November) states that the free key "123" allows 30 requests a minute and returns at most 3 events per day request (1 for "next league", 15 for a season). A whole-sport day request therefore loses most fixtures.
  - **What changes:** SportsLiveInfo now also asks, once a day, for each chosen **competition** on each of the next 7 days (`eventsday.php?d=…&l=…`). Later runs that day ask for today only.
  - **Defaults:** Nations Championship (the November rugby tests), Six Nations, United Rugby Championship, Premiership Rugby, European Champions Cup, Super League, PDC darts, World Snooker and UFC. Rugby World Cup, Challenge Cup and the DP World Tour are optional, under Sources → Source options.
  - **Whole-sport day requests** now cover today only.
  - **Budget:** the local daily budget is 200 requests (was 120); a normal day uses about 130.
  - **Measured live:** next Saturday's Ireland v South Africa, Italy v Fiji and France v Argentina, which the published feed did not have.
  - **Still partial:** a competition with more than 3 fixtures on one day still shows only 3 on the free key.
- Tests: 4 new (window learned and honoured, parser reads only two dates, window forgotten after 3 days, competitions cover the week once a day); 2 updated for the new TheSportsDB plan. 286 tests pass.

## 0.3.20 — Channel coverage on Home Assistant; guide channel map; B1G reconciliation spec

- **New *Channel coverage* page (local only).** Import your provider's channel list (M3U or text).
  - **Privacy:** it is stored only in the App's database on Home Assistant, never published or sent to GitHub. Stream addresses, which contain your provider login, are discarded while the file is read; only category, name and the provider's own guide id (`tvg-id`) are kept.
  - **What the report shows, for every linear channel** (entertainment, movies, kids, news, documentaries, music, sport, religious …):
    - whether it is identified (the provider's `tvg-id` first, then the channel dictionary);
    - which guide carries it, from the guides you have on or the guides available.
  - **Breakdowns** by type of channel and by market.
  - **Recommendations:** which guides to switch on, in order of new channels covered, and which dictionary regions you need.
  - **Download:** a per-channel CSV that stays on your device.
- **Guide survey** (button on the same page): every guide in the catalogue, including those marked "verify", is downloaded once in the background. Only channel ids, names and programme counts are kept. Nothing is switched on, and unreachable guides are reported, not retried in a loop. This measures Scandinavian, Eastern European, Turkish, Middle East and Indian guides that cannot be tested from outside your network.
- **Guide channel map** (feed format 1.5, asset `guide_map`, public and private feeds):
  - **Contents:** for every guide you have enabled, each guide channel's id, name, the service it is and its programme count for the next 7 days. Ids and names only, never programme text.
  - **Use in B1G:** to reconcile a provider channel to the right guide channel by id instead of by name.
- **[B1G channel and guide reconciliation specification](../docs/B1G_CHANNEL_AND_GUIDE_RECONCILIATION_SPEC.md):** one binding order of work for the TV.
  - **Precedence:** provider guide primary; user mapping, then provider `tvg-id`, crosswalk, service name, dictionary, event slots, local stations, fingerprint; ambiguous results never applied.
  - **Guide choice:** feed-aware, never another region, country or +1.
  - **Conformance:** fixtures, plus acceptance by comparing B1G's per-channel result with the Home Assistant CSV (≥ 99 % agreement, zero region/+1/foreign errors).
- **Regional versions never merge with the national service (fix).** A guide channel identified through the dictionary as a regional feed was reported as the national channel ("France 3 Alsace" as France 3, "ITV1 Granada" as ITV1, "BBC One Wales" as BBC One wherever the curated list did not catch it first). The identity is now `id@Region` ("France3.fr@Alsace"). One rule, `dictionary.service_identity`, is used for guide channels, for the coverage report and by B1G:
  - the main or a picture-quality feed ("HD", "UKHD") is the channel itself;
  - exactly one regional feed keeps its region;
  - a timeshift feed, several channels or several regions give no identity (ambiguous, review only).
  - A side effect: each BBC One / ITV region now gets its own dictionary-to-service alias, where before the regions collided and none was published.
- **Guide choice reference for B1G** (`coverage.choose_guide_channels`): picks guide channels from the published `guide_map` by provider `tvg-id`, then service, then the same iptv-org channel in guides that did not identify it. Regions must agree exactly ("London" never takes "London East"); never +1, never another country's feed, never a guide channel with no programmes in the next 7 days. The coverage report uses the same exact-region rule.
- **`guide_map.service_aliases`:** dictionary id → SLI service id where SLI reports a dictionary channel under a curated service (`ITV1.uk` → `gb.itv.one`), so a TV that identifies a channel by its dictionary id finds the same guide rows.
- **Feed assets stay within B1G's 8 MB limit.** The dictionary no longer carries feed languages, picture format or owners (none identify a channel): with every world region switched on it is 6.7 MB (was 8.8 MB, which B1G rejected); UK/Europe only is 2.2 MB (was 2.8 MB). An optional asset over 8 MB is now left out of the feed instead of being published; a required one stops the build with an error.
- **The TV's per-channel order of work as reference code** (`coverage.reconcile_channel`): skip VOD/radio/adult/24-7, provider `tvg-id`, dictionary name rules in the channel's market, event-slot names, then guide choice. Output columns `coverage.TV_FIELDS` (the coverage CSV plus slot, slot start and linked event). Fixture `dictionary-conformance/reconcile-cases.json` (6,162 channels).
- **Compare with B1G** (Channel coverage page, local only): import the TV's per-channel export; every channel in your imported list is checked against what SportsLiveInfo computes from the same published feed. It shows identity agreement (target 99 %), wrong region or +1 (must be 0), guide channels outside SportsLiveInfo's choice, and type/market/genre agreement, with a table of differences, serious ones first.
- **B1G can build the dictionary itself** when this App's feed is missing or stale: `standalone/dictionary-rules.json` holds the rule tables and scope definitions B1G bundles, and `standalone/expected.json` is `build_document` over a fixed public slice of the iptv-org database (3,743 channels, 6,057 feeds, three region choices), which B1G's own build must reproduce exactly.
- **B1G conformance fixtures** (exact answers from SportsLiveInfo's reference code, all public or synthetic):
  - `dictionary-conformance/`: 15,794 provider-style names over 3,138 public iptv-org channels, with ids, method, confidence and identity;
  - `slot-conformance.json`: 2,500 generated event-slot names (fictional teams) across five clocks, including both 2026 UK clock changes;
  - `guide-choice-cases.json`: 1,200 guide choices covering regions, +1, foreign feeds, aliases and disabled guides;
  - `dictionary-cases.json` now embeds its dictionary document.
- Measured on the owner's list with the guides available from GitHub: the report builds in about 8 s for 25,700 channels. Its recommendations put the Sky guide first, then France + beIN, Portugal, EPGTalk US and Spain.

## 0.3.19 — EPGTalk UK fixed; 8× faster channel matching; Sky guide reads its ids

- **EPGTalk UK guide failed at every refresh** since it grew past 100,000 programmes (14 Nov: 102,312, 10.7 MB). Its limits are now 20 MB / 180,000 programmes, and the current file imports.
- **Event→channel matching is about 8× faster.** On the three current UK guides (about 160,000 programmes) a run took 78.5 s and now takes 9.6 s, with identical results. Channel names, team names and titles were re-normalised for every programme row; pure functions are now cached (`normalized_name`, `taxonomy.norm`, `name_signature`, channel families, sport eligibility, team options). This shortens every collection and publication on Home Assistant.
- **Guides that abbreviate names but use iptv-org ids** (M3UPT Sky: "TNTSports1 HD", "BBC One Wal HD", "SkySp ActionHD") are read from the id ("TNTSports1.uk@HD", "BBCOne.uk@WalesHD"). Sky Sports, TNT Sports, Premier Sports and BBC One Scotland/Wales/NI are recognised; 111 of the file's 393 UK/Irish channels map (52 before). The sport-channel check also uses the recognised service, so these channels are no longer skipped as "not sport".
- **Foreign feeds never become UK services:** a guide channel whose id names another country ("SkySportTennis.de@HD") or whose feed names one ("DAZN2.uk@GermanyHD") is excluded on the registry and dictionary paths. German listings from the multi-country Sky file therefore no longer appear on UK channels.
- **Display names:** a UK service shows a UK feed's name over an Irish feed's ("Sky Mix HD", not "Sky Mix HD ROI").
- **Measured** with the current UK guides plus the optional Sky guide (14–21 Nov): guide-listed live sport rises from 196 to 218 and linked fixtures from 42 to 44 (e.g. Las Vegas GP on Sky Sports F1), with no German listings. The current three guides alone give exactly the 0.3.18 result.
- The add-on README is brought up to date.

## 0.3.18 — Channel identification worldwide; renames; new sport and FAST guides

Results of a broad research pass over the owner's channel list (private, never committed), the public-domain iptv-org database and EPG site lists, and free guide sources. Full report: [channel identification and EPG source research](../docs/RESEARCH_2026-11-14_CHANNEL_IDENTIFICATION_AND_EPG_SOURCES.md).

- **Provider name grammar for every market** (`market_key`): leading market and platform tags such as "|SENEGAL| ", "IN-TM | ", "EG: ", "JOYN DE: ", "DE ||VIP| ", "Shahid | ", "(MX) (IZ) ", "Carib (FLOW) ", "Claro ", trailing "(FL)"/"(C)"/"|TN|", and quality glued to a number ("DAZN 1HD"). The market's own code is removed only once ("US USA Network" keeps "USA"), and other markets' codes never ("Al Jazeera").
- **Renames followed:** a closed channel whose database entry names a live successor now resolves to it ("FOX" in a Turkish list → NOW, "C More Hits" → TV4 Hits, "Viasat Sport" → V Sport, "C More Sport" (FI) → MTV Urheilu, L'Équipe 21 → L'Équipe). Closures with no successor (C8, Game One) are still only explained. Russian Viasat channels → viju (alias). Premier Sports 1/2 (listed as Irish in the database) now resolve in UK lists.
- **Own-market suffix:** "ZDF HD DE" in a German list resolves as ZDF.
- **Cyrillic and Greek** names in the database also match Latin spellings ("Rossiya 1", "EPT 1").
- **Optional world regions for the channel dictionary** (Sources page, all off by default): North America; Latin America and the Caribbean; Middle East and North Africa; South Asia; Sub-Saharan Africa; Asia-Pacific. With them: US/Canadian **station callsigns** ("NBC 5 (KFYR) Minot" → NBC's KFYR feed), and **country tags** in multi-country sections ("|NIGERIA| AIT" is Nigeria's AIT, never Ghana's). An untagged name found in two countries of such a section is ambiguous, never guessed.
- **New guides, all off by default, private use only:**
  - New Zealand sport · Sky Sport Now (Sky Sport 1–9, Premier League, Select, ESPN), Australia sport · Kayo (Fox Sports 503–506, Fox Cricket/League/Footy);
  - UK free streaming channels · Plex, Samsung TV Plus, Pluto TV (Stingray, Qwest TV, Vevo, Rakuten TV, Sky Sports Stories/Classics);
  - Spain including Movistar Plus+ (M+ LaLiga, Liga de Campeones, Vamos) and DAZN · EPG dobleM; France + beIN Sports MENA/FR/EN, OSN and MBC · Fazzani/grab; Portugal (Sport TV 1–7, DAZN PT) · M3UPT;
  - to verify with *Test EPG*: EPG Share DE, ES, IT, NL, CH, SE, NO, DK, FI, TR, RO, BG, HU, CZ, SK, HR, BA, AL, SA, EG and beIN MENA; IPTV-EPG.org SE, NO, DK, TR, PT, PL, RU, AL, BG, CZ, HU, RO.
- **Channel registry:** Sky Sport NZ 1–9/Premier League/Select and Fox Sports AU 503–507/More/News.
- **Hard negative:** a guide channel whose own id names another country ("beINSports1.qa@MENA" in the France + MENA guide) never becomes this market's service (beIN Sports 1 France).
- Feed format 1.4: the dictionary asset adds `regions`, `group_markets`, `country_tags` and the rules above; new cross-language fixture `schemas/fixtures/sli-v1/dictionary-cases.json` for B1G.
- **Second pass: per-channel guide reconciliation.** Every channel in the owner's list was matched against 49 downloadable guide files, by dictionary id (regional feed included: BBC One Wales gets the Wales guide, never East) and by name within its market. Results:
  - **Resolver additions:**
    - "Sport"/"Sports"/"Spor" spellings anywhere (Sky Sport Uno, Novasports, Tivibu Spor);
    - an implied "1" ("Diema Sport 1" = Diema Sport, only when a "2" exists);
    - the market's own numbered channel ("beIN Sports 1" in a Turkish list is beIN Sports 1 Turk), which is also preferred over a foreign channel that merely broadcasts into the market;
    - the plain channel over its 4K sister;
    - "beINSport" and "Xtra" spellings.
  - **Correction:** Turkish beIN Sports 1–4 previously resolved to the Middle East channels and Polish Eurosport 1/2 to the pan-European feed; both now resolve to their own national channels.
  - **XMLTV `.xz` files** are read, with the same size bounds as gzip.
  - **13 more guides**, off by default, each downloaded and parsed:
    - Sky UK + Germany/Austria + Italy (1,243 channels including every BBC/ITV region) and Sky Italia, both from M3UPT;
    - Freeview UK (M3UPT);
    - EPGTalk US (738 channels including regional sports networks), US local stations, Latin America (595) and free streaming channels (1,173);
    - Roku and Plex US, DStv South Africa (SuperSport), Samsung TV Plus India, Australia all cities, Sky Go NZ (100 channels, 3 months).
  - EPGTalk's existing sports guide carries per-team channels for the NFL, NBA, NHL, MLB, MLS, WNBA and European leagues; 365 of the owner's team channels match it.
- **Event-slot channels** (new `event_slots.py`, reference for B1G; the channel names stay on the TV):
  - The parser reads slot label, competition, fixture and start time from names such as "EPL 05 | A vs B (Sat 17:30 UK)", "DAZN 52: League| A vs. B| Sat 18 Oct 12:30 PM", "PL+ 017| A v B (2026-08-29 16:20:00)", "NFL 01: 8:15PM A @ B" and "… @ Nov 9 7:00 PM :NBA 04". It understands time zones and day/month or month/day dates.
  - A slot links to exactly one SportsLiveInfo event: both sides must match and the start must be within 3 hours. A clock time alone never picks between two meetings of the same teams.
  - Round-trip test on this week's real feed: 1,483 of 1,500 slot names built in five provider formats link to the right event; 17 stay unlinked, none wrong.
  - New fixture `slot-cases.json`; feed contract §4.0b.
- **US/Canadian local stations** without an id match: network + city ("NBC 5 (KXXX) City" → guide "NBC City"), never a "News" stream. This covers about 380 of the owner's otherwise guideless stations (`guide.local_station_key`, contract §4.0a).
- **Latin American country tags:** "(MX)", "(PY)", "(AR)" … at the start of a name in US, CA, LATAM or CARIB lists search that country first, then Latin America, with Brazil (Portuguese) last. Latin America identification rises from 59.1 % to 69.1 %, US from 40.3 % to 41.4 %, and Mexican channels get their Mexican feeds (FX, National Geographic, History, TUDN).
- **Measured on the owner's 21,250 linear channels:**
  - Identification: UK/Europe 61.5 % (55.4 % before), UK/Europe sport channels 71.2 % (57.8 %), whole list with all world regions 50.1 % (20.0 %).
  - Guide found, including local stations and event slots: US 30.3 %, Canada 38.0 %.
  - Downloadable guide from the GitHub-hosted files: France 75.4 %, Spain 72.8 %, Italy 72.7 %, UK 69.8 %, Portugal 62.7 %, Germany 56.8 %; sport channels 47.8 %.
  - Scandinavia, Poland, Turkey, Russia, the Balkans, Greece, MENA and India depend on the EPG Share / IPTV-EPG.org files, which can be tested only on Home Assistant. Ambiguous results are never applied. Two hand-checked samples (70 and 85 new matches) found the errors described in the report. The country errors were fixed before release; one short-brand mismatch remains.

## 0.3.17 — Connection tests run in the background

- *Test saved GitHub connection* and *Test private feed connection* now start the test in the background and return at once; refresh the Publishing page to see "Last test: Passed/Failed" with the reason. Running up to three GitHub requests inside the page request let Home Assistant remote access drop the connection before the answer arrived ("unexpectedly closed the connection"), so the result was never shown.
- Each test result is also written to the App log (never the token), so it can be checked from Home Assistant's logs.

## 0.3.16 — Radio commentary excluded; repository fields accept links

- Listings for radio or audio-only commentary on a TV channel (for example a club channel's "Live: Radio Commentary") are no longer offered as a channel for the match, either as a fixture link or as a guide-listed event.
- The Publishing page's repository fields (public and private feed) accept a GitHub link (`https://github.com/owner/name`), `owner/name` or the bare name, and say which field is invalid. Previously a pasted link was rejected with a generic message, so the private feed settings appeared not to save.
- Documentation: new [14 November handover](../docs/archive/HANDOVER_2026-11-14_SPORTSLIVEINFO_B1G.md) (state, decisions, outstanding work, B1G plan) and refreshed current status.

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
