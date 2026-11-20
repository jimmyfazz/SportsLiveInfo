# Current implementation and verification status

**15 November 2026 · SportsLiveInfo 0.3.24.** How agents work: [AGENT_OPERATING_MANUAL.md](AGENT_OPERATING_MANUAL.md). Start with the [15 November handover](HANDOVER_2026-11-15_SPORTSLIVEINFO_B1G.md), the [15 November forensic audit](AUDIT_2026-11-15_FORENSIC_SPORTSLIVEINFO.md) (open work), the [B1G reconciliation spec](B1G_CHANNEL_AND_GUIDE_RECONCILIATION_SPEC.md) and the [feed contract](FEED_CONTRACT_SLI_V1.md). The public [SportsLiveInfo source repository](https://github.com/jimmyfazz/SportsLiveInfo) builds the Home Assistant App. [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is the public data destination; `LiveSports-EPG-private` is the owner's private personal-use feed. Credentials, guide programme text and App settings stay on Home Assistant.

- **Installed:** 0.3.24 on Home Assistant since 15 Nov 11:06 UTC (backup `2f1c1ebc` of 0.3.23 first) — channels ranked by evidence (ITV1 first, not Irish/Asian ids), past-year re-runs never live, free streaming channels not mistaken for broadcast services, rugby duplicates merged, and the feed now carries the decisions B1G follows (`rank`, `binds`, `live_until_utc`; [contract §4.3](FEED_CONTRACT_SLI_V1.md)). 329 tests pass.
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

**Local result on `chore/defaults-owner-assertion` (20 Nov 2026):** 451 tests passed (442 baseline plus 9 in `tests/test_owner_defaults_20nov.py`). **Earlier result:** 329 tests passed on 0.3.24 (`origin/main` 8da6e83, re-run 20 Nov 2026). The 315 figure belongs to the earlier 0.3.23 run (15 Nov 2026) and is kept only in [implementation progress](IMPLEMENTATION_PROGRESS.md). CI (`verify.yml`) passes on every merged PR. See [implementation progress](IMPLEMENTATION_PROGRESS.md) for measurements and the [document index](DOCUMENTATION_INDEX.md) for earlier records.

## SportsLiveInfo — 20 Nov 2026 handover (release/20nov, merged to main)

Written so Claude or ChatGPT can resume. Nothing was deployed and no version file was bumped; the owner updates Home Assistant.

**Branch map (all merged into `release/20nov`, in this order):** `integration/all` (live-lane expiry and publish regression gate, cross-source dedupe, settle pass, F1 and cricket fixes, crest refs, scores, health alerts, rights docs) → `feat/history-display-state` (yesterday asset `events:<history_from>`, `display_state`, `state_until_utc`, `finished_at_utc`, guaranteed `competition_id`; contract 4.5) → `feat/event-metadata-ranking` (icons, short names, participant ids, competition logos, `feature_rank`, PPV, F1 weekends; contract 4.3) → `feat/standings-asset` (optional `standings:<competition_id>` assets; contract 4.6, kill switch `publish_standings`) → `chore/defaults-owner-assertion` (fresh-install defaults: scores for `api_sports` and `football_data`, crest refs on) → `docs/runbook-and-consolidation` (`docs/RUNBOOK.md`) → `feat/channel-hints-and-binds` (`channel_hints` asset, narrow `binds` rule with `binds_rule: legacy` kill switch, link coverage and binds dry run in health) → `fix/ops-hardening` (collection deadline, asset size budget with 80% alert, dictionary and guide-map parts above the 8 MiB reader cap).

**Open items (owner or next agent):**
- Defaults: crest refs, scores, standings and the narrow binds rule are on for fresh installs; existing installs keep their saved values. `publication_approvals` is still empty, so nothing is public until the owner ticks a source and attests. Rights rest on the owner's statement only (`docs/RIGHTS_RECORD.md`); supplier terms were not read.
- Standings (football-data.org, API-Sports) and several score payload shapes follow public documentation and are NOT verified against a live response.
- Home Assistant verification NOT RUN: the Supervisor watchdog request may be refused by the Ingress address check (403 risk, restart loop); check `/healthz?scope=liveness`.
- Rollback is unsupported by the App (manual git procedure in the runbook).
- A regression-gate refusal is recorded as publisher state `blocked` and is silent: no notification, no stall count.
- Dictionary and guide-map parts (`dictionary:*`, `guide_map:<n>`, capabilities `channel_dictionary_parts`, `guide_map_parts`) are not read by B1G yet; the plain `dictionary` kind is kept as an alias of the UK/Europe part.
- B1G reader changes for history, display state, metadata, standings, hints and binds are not done; B1G device acceptance not run.
- Release gate result: compileall clean; `unittest discover` 597 tests pass at the final merge (MemoryError line from a mock is expected).
