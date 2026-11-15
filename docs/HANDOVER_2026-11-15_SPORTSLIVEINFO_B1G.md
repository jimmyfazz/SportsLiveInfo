# Handover — SportsLiveInfo and B1G, 15 November 2026 (to terminal agents on the Mac)

**Supersedes** [the 14 November handover](archive/HANDOVER_2026-11-14_SPORTSLIVEINFO_B1G.md). Start here, then read [AGENTS.md](../AGENTS.md) (binding rules), [current status](CURRENT_STATUS.md) and the [15 November forensic audit](AUDIT_2026-11-15_FORENSIC_SPORTSLIVEINFO.md) (open work). The B1 repository has a matching handover: `docs/HANDOVER_2026-11-15_TERMINAL_AGENTS_MAC.md` in `jimmyfazz/B1`.

Work so far was done in a cloud session. That session could not reach the owner's TVs, an emulator, or the Home Assistant host except through the Home Assistant MCP connector. Agents on the Mac can run what the cloud session marked **NOT RUN**.

## 1. What exists and where it runs

| Part | Where | State on 15 Nov 2026 |
|---|---|---|
| SportsLiveInfo Home Assistant App | Source: `jimmyfazz/SportsLiveInfo` (public), folder `sportsliveinfo/`. Installed on the owner's Home Assistant OS mini PC as slug `106c7bd5_sportsliveinfo` | **0.3.23 installed and running** (08:59 UTC). Backup of 0.3.21 taken first: `9542a582` "SportsLiveInfo 0.3.21 before 0.3.23". Auto-update **on**; watchdog on |
| Public feed | `jimmyfazz/LiveSports-EPG` (public), `v1/manifest.json` | Last published 04:17 UTC as `sli/1.5` (from 0.3.21). The **first `sli/1.6` publish is the next scheduled run** (04:00, 12:00, 17:00 Europe/London) — **not yet observed** |
| Private feed | `jimmyfazz/LiveSports-EPG-private` (private) | Enabled; publishes with the public feed |
| B1G Android app | `jimmyfazz/B1`, `platforms/android/` | Reads the feed (B1 PR #827, then #828 merged 15 Nov at `7269e5f`): reconciliation, gap-fill guide, event slots, Sports Today with the `sli/1.6` live rules. **Not yet installed on any TV from this build; device acceptance NOT RUN** |

`main` of SportsLiveInfo is `f335c4e` (PR #35). 315 tests pass.

## 2. What changed 14–15 November (0.3.20 → 0.3.23)

| Version | Change |
|---|---|
| 0.3.21 | API-Sports plan window learnt and respected (no requests for refused dates). TheSportsDB week-ahead per competition (`THESPORTSDB_DEFAULT_LEAGUES`: rugby internationals, Six Nations, URC, Premiership, Champions Cup, Super League, PDC darts, World Snooker, UFC), league scopes `<sport>|league:<id>`, 200 calls a day |
| 0.3.22 | Forensic audit fixes: the publisher re-checks repository name and visibility on every publish (private feed can never land in a public repository); stream URLs and credential lines never become channel names; loose `guide_listing_match` links stay private |
| 0.3.23 | Feed `sli/1.6`: `status_observed_at` and `expected_end_utc` on every event plus a manifest `live_state_rule` (live only ≤ 45 min after an observation and between start and expected end + 30 min); a light API-Sports live-status lane and optional `live` asset (schema `sli.live/1`); approved-only public merge (snapshot `sports-public`); core/extra tiers with `events_extra:<date>` assets; `guide_corroborated` links (strict match, same slot, curated channel, two independent guide families). `broadcast_verified` stays false |

Details: [changelog](../sportsliveinfo/CHANGELOG.md), [feed contract](FEED_CONTRACT_SLI_V1.md), schemas in `../schemas/`.

## 3. Working on the Mac

### Setup and tests

```sh
git clone https://github.com/jimmyfazz/SportsLiveInfo.git && cd SportsLiveInfo
python3 --version          # 3.12 is what the App runs; the standard library only, nothing to install
python3 -m compileall -q sportsliveinfo/src tests
PYTHONPATH=sportsliveinfo/src python3 -m unittest discover -q -s tests
```

- Expect **315 tests, OK**. A `MemoryError` line in the output comes from a test that mocks memory exhaustion; it is expected.
- After any change to feed format, schema or version: `PYTHONPATH=sportsliveinfo/src python3 tools/generate_feed_fixtures.py`, then rerun the tests. The B1 repo keeps a copy of these fixtures (`platforms/android/app/src/test/resources/sli-v1-6/`) for its interop test; refresh it when the wire format changes.
- CI: `.github/workflows/verify.yml` runs on every PR (this repository is public, so Actions are free and do run).

### Code map (`sportsliveinfo/src/sportsliveinfo/`)

| Module | Role |
|---|---|
| `engine.py` | Scheduler, collection lanes, plan windows, live lane (`live_lane`, `_live_tick`, `_publish_live`), publishing (`_github_commit`, `_commit_feed`) |
| `providers.py` | Sports sources (API-Sports products, football-data.org, TheSportsDB, OpenLigaDB, Jolpica/OpenF1, CricketData), quotas, `status_of` live codes |
| `guide.py` | Streaming XMLTV parsing, guide registry and survey |
| `linking.py` | Event merge, `status_choice`, broadcast candidates, strict and loose matchers, `guide_corroborated`, `UNVERIFIED_LINEAGE_FAMILIES` |
| `feed.py` | Public/private feed assets, tiers (`event_tier`), rights gate, manifest |
| `identity.py`, `dictionary.py`, `coverage.py`, `event_slots.py` | Channel identity, iptv-org dictionary, owner lineup coverage, event-slot channels (B1G ports these exactly) |
| `server.py` | Ingress UI (CSRF, CSP, peer-IP access) |
| `storage.py` | SQLite (`/data/sportsliveinfo.sqlite3`): settings, secrets, snapshots, quotas |

### Releasing a new version

1. Bump the version in **all** of: `sportsliveinfo/config.yaml`, `sportsliveinfo/Dockerfile` (`BUILD_VERSION`), `sportsliveinfo/src/sportsliveinfo/__init__.py`, `sportsliveinfo/CHANGELOG.md`, `sportsliveinfo/README.md`, `README.md`, `CLAUDE.md` and [CURRENT_STATUS.md](CURRENT_STATUS.md). Regenerate fixtures.
2. Small PR from a fresh branch off `main`; tests green; the owner asks for the merge.
3. Deploy on Home Assistant, in this order:
   - **Back up the App first**, named "SportsLiveInfo <old> before <new>" (Settings → System → Backups, or the update dialog's backup option; with the HA MCP connector: `ha_manage_backup(scope="snapshot", action="create", include_addons=["106c7bd5_sportsliveinfo"], name=...)`).
   - Refresh the store (Settings → Apps → ⋮ → Check for updates; MCP `ha_manage_app(action="check_updates")`), then **Update** (MCP `ha_manage_app(action="update", slug="106c7bd5_sportsliveinfo")`). Supervisor builds the image locally from the Dockerfile.
   - Verify: App version, state `started`, and the App log line `SportsLiveInfo Ingress HTTP ready on internal port 8099`.
   - Auto-update is on, so Home Assistant also updates by itself once the store notices the new version.
4. The HA MCP connector often answers "SSE stream ended without a response" on backup and store calls while the operation still completes. **List backups / read the App back before retrying.**
5. Ingress answers 403 to anything not coming through Home Assistant's own Ingress proxy; that is correct.

## 4. Binding rules (short form; the full text is in AGENTS.md and CLAUDE.md)

- No public EPG programme text unless the source's public rights are documented. Guide-listed events and loose links are private-feed only.
- TVs are read-only: no API keys, no GitHub write tokens, nothing uploaded from a TV. The owner's channel list, stream URLs and credentials never reach any feed, log or commit.
- No paid providers or paid CI without the owner's approval; no LLM calls at runtime.
- Never claim a merge, a deployment or a test without checking it. Mark what you did not run as **NOT RUN**.
- Small PRs from a branch off `main`; the owner asks for each merge.

## 5. Open work, in priority order

From the [15 November audit](AUDIT_2026-11-15_FORENSIC_SPORTSLIVEINFO.md); IDs match it.

1. **Observe the first `sli/1.6` publish** (Publishing page or `LiveSports-EPG/v1/manifest.json`): format `sli/1.6`, `live_state_rule` present, events carry `status_observed_at`; once API-Sports has a match on, the `live` asset appears. The live-lane calls against API-Sports (`live=all`) have **not been run** yet.
2. **0.3.24 — stability and fixture correctness:**
   - **C4 (P1):** stream guides one at a time for linking; slim programme records to title, sub-title and times; keep the next 8 days. Out-of-memory risk with 10–40 guides.
   - **O1 (P1):** an overall deadline per request (chunked reads) and a "collector stuck" state; today a slow upstream holds the busy lock indefinitely.
   - **C7:** drop events missing from a complete scope; stop using last-good snapshots after about 36 h.
   - **C11:** TheSportsDB `00:00:00` → `time_tbc`.
   - **C8:** derive the F1 session from TheSportsDB titles so they merge with Jolpica/OpenF1.
   - **C5:** index guide-listed live clustering by sport, time slot and team token (quadratic today).
3. **Operations:** O6 Home Assistant sensors (last collection, last publish, manifest age, failing sources, token expiry) and one quiet persistent notification; O2 backups (tokens in plain text in backups, WAL checkpoint, prune disabled guides' snapshots); O3 one XMLTV parse at a time.
4. **Feed hygiene:** C10 bucket `guide_map` programme counts (repository growth), O4 per-guide approval for public guide metadata, O5 separate tokens per feed and optional manifest signing.
5. **P3 list** in the audit (container hardening, CSV formula escaping, heartbeat writes, request-table pruning).

## 6. Owner actions outstanding

- Update the TVs from B1 `main` with `tools/android-install-latest.sh` (in the B1 repo) and do the device checks in the B1 handover.
- Optional: remove the stale local copy of the App (`local_sportsliveinfo`, 0.3.4) on Home Assistant.
- Old remote branches can be deleted (the cloud session's git proxy refused deletes). All are merged or superseded: `chore/configure-livesports-epg-public-feed-20261112`, `codex/audit-integration`, `codex/epg-coverage-gaps`, `codex/epg-sports-followup`, `codex/event-channel-matcher-2026-11-13`, `codex/haos-live-dashboard-fixes`, `codex/mobile-overview`, `codex/source-refresh`, `codex/sports-catalogue`, `docs/current-documentation-20261112`, `feat/github-token-setup-and-forensic-audit-20261112`, `feat/haos-app-first-installable-2026-11-12`, `feat/haos-epg-coverage-openligadb-v0.2-20261112`, `feat/haos-operator-dashboard-ux-20261112`, `feat/supplement-epg-hardening-v0-3-0`, `fix/claude-integration-forensic-hardening-20261112`, `fix/haos-custom-app-image-labels-20261112`, `fix/mjh-guide-source-urls`, `perf/epg-broadcast-window-index-20261112`, and the cloud session's `claude/sportsliveinfo-b1g-android-syyo8j` once this handover is merged. Delete only with the owner's go-ahead (`git push origin --delete <name>`).

## 7. Known limits

- API-Sports free plan: yesterday, today and tomorrow only (the learnt plan window enforces it).
- TheSportsDB free key: at most 3 events per request (so it always reads "partial").
- Not checked from the cloud: French guide listing formats on Home Assistant, Supervisor build internals, real amd64/aarch64 image builds.
