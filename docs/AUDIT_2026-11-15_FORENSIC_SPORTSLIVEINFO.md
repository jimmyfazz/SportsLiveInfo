# Forensic audit — SportsLiveInfo 0.3.21 (15 November 2026)

Two independent read-only reviews were run against `main` at 0.3.21:

- collection and feed logic;
- security, privacy and operations.

Every P1 item below was then checked against the code before it was accepted. "Verified" means the exact code path was read, or the scenario was reproduced. Items fixed in 0.3.22 and 0.3.23 carry their test.

## Fixed in 0.3.23

| # | Severity | Finding | Fix and test |
|---|---|---|---|
| C1 | P1 | Corroborated events disappeared from the public feed when any contributing source was unapproved. | The engine also merges approved-source records only (snapshot `sports-public`) and the public feed is built from it; the private feed keeps the full merge. Published records name approved sources only, and a change of approvals falls back to the old fail-closed filter until the next collection. Tests: `ApprovedOnlyPublicMergeTests`. |
| C2 | P1 | "Live" could be stale or false; a started Test became five "live" day records. | Every event publishes `status_observed_at` and `expected_end_utc`; the manifest's `live_state_rule` trusts "live" only within 45 minutes of the observation and from the start to 30 minutes after the expected end. Only the Test day in play is live. A light live-status lane (API-Sports live boards, at most every 15 minutes in match hours, at most 40 calls a day per product inside the product quota) publishes a small `live` asset. Tests: `HonestLiveStateTests`, `LiveLaneTests`, `test_tiers_live_overlay_and_observation_times`. |
| C6 | P2 | API-Sports live codes mapped to "unknown" (hockey P1–P3, baseball IN1–IN9, volleyball S1–S5, MMA). | Per-product live codes in `providers.status_of`, passed by each decoder. Test: `ApiSportsLiveCodeTests` (every product). |
| C9 | P2 | A merged event took its status from the most precise record. | `linking.status_choice`: the most advanced status, then the most recent observation. Test: `MergedStatusTests`. |

C3 (loose guide-listing links kept private) is unchanged: the loose matcher was not tightened, so its links stay out of the public feed. The new `guide_corroborated` status is given only to links from the strict matcher.

## Fixed in 0.3.22

| # | Severity | Finding | Fix and test |
|---|---|---|---|
| S1 | P1 | The private/public visibility check ran only in the connection test. The publisher committed without it, so a private feed (every collected event plus guide-derived channel names and times) could land in a repository later made public or mistyped. | `_github_commit` re-checks `full_name` and `private` on every publish and stops before any read or write. Test: `test_publisher_refuses_a_private_feed_in_a_public_repository`. |
| S2 | P1 | A channel list with no M3U header in its first 50 raw lines (leading blank lines, indentation, or a bare URL list) stored stream URLs, which can carry the provider login, as channel names in SQLite, the coverage page and the CSV. | M3U is detected anywhere after stripping, and URL or credential lines are dropped in plain-text mode. Test: `test_stream_urls_never_become_channel_names`. |
| C3 | P1 | Public `broadcast_links` from the looser guide-listing matcher could name the wrong match. Reproduced: "Live: Man City v Liverpool" 14:30 was linked to Manchester United v Liverpool 17:30 and published as Sky Sports Main Event. | Links from `guide_listing_match` stay in the private feed only. Tests: `LooseLinkPublicationTests`. |

## Open — prioritised

### P1

- **C4 — All enabled guides are loaded at once for linking.** `linking.py` calls `list(epg_guides)` and keeps 1,000-character descriptions it never uses. With 10–40 guides this risks out-of-memory on the mini PC.
  - Plan: stream guides one at a time; slim programme records to title, sub-title and times; keep only the next 8 days.
- **O1 — A slow upstream can hang the collector indefinitely.** Socket timeouts are per read, not per request, and the hang holds the busy lock.
  - Plan: chunked reads with an overall deadline, plus a "collector stuck" watchdog state.

### P2

- **C5 — Clustering for guide-listed live events is quadratic** (55 s on a synthetic Saturday). Index by sport, time slot and team token.
- **C7 — Stale fixtures never leave.**
  - Deleted or re-dated fixtures stay on their old date.
  - Last-good snapshots are used regardless of age.
  - Plan: drop events missing from a complete scope; stop using snapshots after about 36 h.
- **C8 — Formula 1 duplicates between TheSportsDB and Jolpica/OpenF1:** TheSportsDB events have no session. Derive the session from the title.
- **C10 — Public repository growth.**
  - `guide_map` programme counts change every run; at about 3 commits a day this is roughly 1 GB a year of history.
  - An optional asset over 8 MiB is skipped with no notice (0.3.23: now reported in the manifest notices).
  - Plan: bucket the counts; add a manifest notice; squash history periodically.
- **C11 — TheSportsDB "00:00:00" times are treated as confirmed midnight** (suspected; TheSportsDB uses it for "to be confirmed"). Treat as `time_tbc`.
- **O2 — Backups.**
  - SQLite in WAL mode is backed up live, with no `backup: cold` and no pre-backup checkpoint.
  - Snapshots of disabled guides are never deleted.
  - Backups grow with every guide and hold the tokens in plain text.
  - Plan: a small config DB plus an excluded cache DB, a pre-backup checkpoint, and pruning.
- **O3 — Concurrent XMLTV parses** (survey, test button, scheduled lane) can exhaust memory. Add a global parse semaphore and run tests in the background.
- **O4 — Guide-derived metadata (`guide_map`, `identity`) is published once any sport is approved;** the public `health` asset names the providers in use. Add a per-guide public-metadata approval and an aggregate public health asset.
- **O5 — One broad GitHub token for both feeds, and an unsigned manifest.**
  - Plan: separate tokens; warn before token expiry.
  - Optionally sign the manifest (Ed25519) and pin the key in B1G.
- **O6 — Observability.** The watchdog is TCP-only; there are no Home Assistant sensors or notifications.
  - Plan: sensors (last collection, last publish, manifest age, failing sources, token expiry); one quiet persistent notification; an HTTP watchdog on a real health check.

### P3

- Container hardening: runs as root, no AppArmor profile, base image not pinned by digest, Dockerfile `BUILD_VERSION` lags.
- Config: unknown keys dropped on save; retired sources pruned permanently; no `config_version`.
- `/coverage.csv` formula injection: escape `= + - @` at the start of a cell.
- Scheduler heartbeat writes to SQLite every 10 s.
- `requests` table never pruned.
- TheSportsDB is always "partial" because results hit its 3-row cap.
- 30-minute backoff on a daily API-Sports limit.

## Highest-value enhancements (free sources)

1. **Tiered public "today".** Done in 0.3.23: core events in the day assets and `today`, the long tail in optional `events_extra:<date>` assets.
2. **A light live-status lane.** Done in 0.3.23 (see C2).
3. **A free corroboration rule.** Done in 0.3.23 as the `guide_corroborated` link status (strict match, same slot, curated registry channel, two independent guide families after a lineage audit). It is deliberately not `broadcast_verified`, which stays reserved for provider or official evidence.
4. **Forward fixtures.**
   - Widen the football-data.org range.
   - More OpenLigaDB leagues.
   - The TheSportsDB per-competition week view (added in 0.3.21).
   - Drop TheSportsDB whole-sport requests.
5. **Mini PC efficiency.** Slim programme records, one guide at a time, team-token indexes, and a stable `guide_map`.

## What the audit found sound

- **Ingress:** access by peer IP only, no forwarded headers trusted, no exposed ports.
- **Forms:** CSRF tokens on every POST; escaped HTML with a strict CSP.
- **Fetching:** allowlisted HTTPS hosts; no cross-host redirects; size-capped streaming decompression; DTD and entities refused (no XXE or billion-laughs).
- **Secrets:** never logged, rendered or published.
- **Publishing:** atomic single-commit publishing reconciled with the remote file tree; 10 revisions kept.
- **Quotas:** reserved atomically before each call, paced per provider family, with learned plan windows.
- **Matching:** the strict channel matcher refuses wrong teams, +1, radio, shopping and foreign ids; regional allocation is conservative.
- **Rights:** the public event-field allowlist and the rights gate on programme text hold; the owner's channel list never reaches any feed.
- **Contract:** schemas, code and fixtures agree (`sli/1.5`; `sli/1.6` from 0.3.23).
