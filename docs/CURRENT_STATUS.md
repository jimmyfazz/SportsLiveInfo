# Current implementation and verification status

**21 November 2026 · SportsLiveInfo 0.3.28 (installed on Home Assistant on 21 Nov after the merge of this change, the lead checks the version and the "Ingress HTTP ready" log line; public feed `sli/1.7`, published as `sli/1.6` while no score source is approved).** How agents work: [AGENT_OPERATING_MANUAL.md](AGENT_OPERATING_MANUAL.md). Start with the [15 November handover](HANDOVER_2026-11-15_SPORTSLIVEINFO_B1G.md), the [15 November forensic audit](AUDIT_2026-11-15_FORENSIC_SPORTSLIVEINFO.md) (open work), the [B1G reconciliation spec](B1G_CHANNEL_AND_GUIDE_RECONCILIATION_SPEC.md) and the [feed contract](FEED_CONTRACT_SLI_V1.md). The public [SportsLiveInfo source repository](https://github.com/jimmyfazz/SportsLiveInfo) builds the Home Assistant App. [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is the public data destination; `LiveSports-EPG-private` is the owner's private personal-use feed. Credentials, guide programme text and App settings stay on Home Assistant.

- **Format and capabilities (20 Nov 2026):** `sli/1.7`, `min_reader_minor` 0. Capabilities: taxonomy, channel_registry, channel_families, guide_catalogue, events_by_day, today, source_health, fixture_corroboration, status_observed_at, event_tiers, event_history, display_state, channel_identity, channel_hints, channel_dictionary, channel_dictionary_parts and guide_map_parts (only when over the 8 MiB reader cap), guide_map, live_status, broadcast_links, guide_corroborated_broadcasts, scores, standings, team_crests (when crest references are published), taxonomy_icons, participant_metadata, feature_rank, ppv_flag, f1_weekends, competition_logos. Audit fixes are in the CHANGELOG under 0.3.27. Measured on the live feed: dictionary 6,969,653 bytes (83% of the 8 MiB reader cap, alert at 80%), crest references: 0 of 265 core events on 20 Nov, about 440 of 488 on the 21 Nov feed (owner config, see the Publishing page preview).
- **Installed (21 Nov):** 0.3.28 (live budget fix, below). 0.3.27 carried the owner decisions CA-16 (wrestling and sumo removed), CA-17 (tennis lapse and extra tier) and CA-18 (live re-stamp every 15 minutes) and the audit fixes; the first automatic publish after it passed the regression gate. Live crest references on the 21 Nov feed: about 440 of 488 core events. B1G now reads history, display state, standings, channel hints and dictionary/guide-map parts.
- **Installed (15 Nov, older):** 0.3.24 on Home Assistant since 15 Nov 11:06 UTC (backup `2f1c1ebc` of 0.3.23 first) — channels ranked by evidence (ITV1 first, not Irish/Asian ids), past-year re-runs never live, free streaming channels not mistaken for broadcast services, rugby duplicates merged, and the feed now carries the decisions B1G follows (`rank`, `binds`, `live_until_utc`; [contract §4.3](FEED_CONTRACT_SLI_V1.md)). 329 tests pass.
- **Previously:** 0.3.23 (15 Nov 08:59 UTC). Backup `9542a582` of 0.3.21 was taken first, and auto-update is on. The App started cleanly ("Ingress HTTP ready").
- **Public feed:**
  - **`sli/1.6`:** live since 09:00 UTC on 15 Nov. At 10:30 UTC the manifest read `sli/1.6` (publisher 0.3.23) with the `live` and `events_extra` assets.
  - **What `sli/1.6` adds:** status observation times, a `live_state_rule`, an optional `live` asset, core and extra tiers, and guide-corroborated links (never "verified").
  - **No programme rows:** the feed still carries no EPG programme listings.
- **Live-status lane:** running on Home Assistant. It republishes the `live` asset every 15 minutes while matches are on: at 10:30 UTC it held 42 events (34 live, 8 unknown). One publish failed on a GitHub HTTP 500 and the next succeeded.
- **B1G:** has read the feed since B1 PR #827. PR #828 (merged 15 Nov, B1 `main` `7269e5f`) applies the `sli/1.6` reader rules. A B1 interop test reads this repository's golden 1.6 feed.
  - **Unit tests:** the Gradle unit suite (2,179 tests) passes, run in a cloud session.
  - **CI:** B1's GitHub Actions do not run (account billing; the owner does not use them).
  - **On a TV:** **device acceptance not yet run.**
- **Private feed:** enabled; publishes with the public feed.
- **Fresh-install defaults (20 Nov 2026):** scores for `api_sports` and `football_data`, and crest references, are on for a fresh install. Publication approvals stay empty, so nothing is public until the owner approves a source. A configuration saved before these keys existed keeps them off. Kill switches: `score_approvals` empty, `publish_crest_refs` false. See [RIGHTS_RECORD.md](RIGHTS_RECORD.md) (owner statement 20 Nov 2026).
- **Live sport allocation (three public UK guides, 14–20 Nov):** 234 of 244 live UK sports broadcasts have a channel; 14 of 14 labelled fixtures match; no radio, shopping, +1 or commentary candidates.
- **Channel identification (owner's list, 0.3.18):**
  - UK and Europe: 61.5 % by the dictionary; 71.2 % of their sport channels.
  - France: 66.9 %.
  - The whole 21,250-channel list: 50.1 % with all optional world regions.
- **Known limits:**
  - **API-Sports free key:** yesterday, today and tomorrow only.
  - **TheSportsDB free key:** at most 3 events per request.
  - **Not checked from the cloud session:** French guide listing formats and Docker/Supervisor build internals.
  - **Publication rights:** no supplier permission is recorded in the repository for any source. The owner stated on 20 Nov 2026 that rights are permitted for this application's use: used with owner-stated permission; supplier terms not independently verified. Per-source status and the owner checklist are in [RIGHTS_RECORD.md](RIGHTS_RECORD.md). Provider terms could not be read from the cloud session.

## Validation

```sh
python3 -m compileall -q sportsliveinfo/src tests
PYTHONPATH=sportsliveinfo/src python3 -m unittest discover -s tests
```

**Local result on 0.3.28 (21 Nov 2026):** 657 tests pass (646 on 0.3.27 plus 11 in `tests/test_live_budget.py`). **Earlier:** 451 tests passed on `chore/defaults-owner-assertion` (20 Nov 2026). **Earlier result:** 329 tests passed on 0.3.24 (`origin/main` 8da6e83, re-run 20 Nov 2026). The 315 figure belongs to the earlier 0.3.23 run (15 Nov 2026) and is kept only in [implementation progress](IMPLEMENTATION_PROGRESS.md). CI (`verify.yml`) passes on every merged PR. See [implementation progress](IMPLEMENTATION_PROGRESS.md) for measurements and the [document index](DOCUMENTATION_INDEX.md) for earlier records.

## Owner decisions, 20 and 21 Nov 2026 (shipped in 0.3.27 and 0.3.28)

- **CA-09 (changed 21 Nov, 0.3.28):** the live lane polls only for core-tier events (extra-tier events never trigger a call but are updated when a call is made); the live budget is computed from the plan, 60 calls a day per product (limit 80 minus reserve 20; it was 40, which ran out at about 11:13 UTC on 21 Nov while six events were live at 12:00); 30% of it (18 calls) is held back until 17:00 UTC; below 25% left the lane polls every 30 minutes while a core event is live; advisory `live_budget_exhausted` with a Home Assistant notification; counters (used/limit, last live call, core/extra in play) on the Scheduler page and in Service health.
- **CA-18: live refresh 15 minutes** (`LIVE_REFRESH`), `LIVE_MAX_AGE` stays 45. About 4 live commits an hour in play, tracked in a separate live budget (60 a day, 7-day average) so the `feed_growth` alert is not tripped by live commits.
- **CA-16: wrestling and sumo removed** from the feed entirely (decoder and feed build).
- **CA-17: tennis.** Unsettled rows dropped after expected end + 30 minutes (never published `finished`); only Grand Slams, ATP/WTA main tour, Davis Cup, BJK Cup, United Cup and Olympics are core, all other tennis is extra.
- 0.3.27: the first automatic publish after the upgrade passed the regression gate.

## SportsLiveInfo — 20 Nov 2026 handover (release/20nov, merged to main)

Written so Claude or ChatGPT can resume (history: 0.3.25 to 0.3.27 have since been released; see the CHANGELOG).

**Branch map (all merged into `release/20nov`, in this order):** `integration/all` (live-lane expiry and publish regression gate, cross-source dedupe, settle pass, F1 and cricket fixes, crest refs, scores, health alerts, rights docs) → `feat/history-display-state` (yesterday asset `events:<history_from>`, `display_state`, `state_until_utc`, `finished_at_utc`, guaranteed `competition_id`; contract 4.5) → `feat/event-metadata-ranking` (icons, short names, participant ids, competition logos, `feature_rank`, PPV, F1 weekends; contract 4.3) → `feat/standings-asset` (optional `standings:<competition_id>` assets; contract 4.6, kill switch `publish_standings`) → `chore/defaults-owner-assertion` (fresh-install defaults: scores for `api_sports` and `football_data`, crest refs on) → `docs/runbook-and-consolidation` (`docs/RUNBOOK.md`) → `feat/channel-hints-and-binds` (`channel_hints` asset, narrow `binds` rule with `binds_rule: legacy` kill switch, link coverage and binds dry run in health) → `fix/ops-hardening` (collection deadline, asset size budget with 80% alert, dictionary and guide-map parts above the 8 MiB reader cap).

**Open items (owner or next agent):**
- Defaults: crest refs, scores, standings and the narrow binds rule are on for fresh installs; existing installs keep their saved values. `publication_approvals` is still empty, so nothing is public until the owner ticks a source and attests. Rights rest on the owner's statement only (`docs/RIGHTS_RECORD.md`); supplier terms were not read.
- Standings (football-data.org, API-Sports) and several score payload shapes follow public documentation and are NOT verified against a live response.
- Home Assistant verification NOT RUN: the Supervisor watchdog request may be refused by the Ingress address check (403 risk, restart loop); check `/healthz?scope=liveness`.
- Rollback is unsupported by the App; the corrected manual procedure (republish as a new revision) and `tools/republish_revision.py` are in the runbook section 5.
- A regression-gate refusal now raises the advisory `publish_gate_blocked` (0.3.26); the budget advisory `live_budget_exhausted` is new in 0.3.28.
- Dictionary and guide-map parts (`dictionary:*`, `guide_map:<n>`, capabilities `channel_dictionary_parts`, `guide_map_parts`): the plain `dictionary` kind is kept as an alias of the UK/Europe part.
- B1G now reads history, display state, standings, hints and dictionary/guide-map parts (B1 side); B1G device acceptance is not run.
- Release gate result: compileall clean; `unittest discover` 597 tests pass at the final merge (MemoryError line from a mock is expected).
