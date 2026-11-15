# Forensic audit — SportsLiveInfo 0.3.21 (15 November 2026)

Two independent read-only reviews were run against `main` at 0.3.21:

- collection and feed logic;
- security, privacy and operations.

Every P1 item below was then checked against the code before it was accepted. "Verified" means the exact code path was read, or the scenario was reproduced. Items fixed in 0.3.22 carry their test.

## Fixed in 0.3.22

| # | Severity | Finding | Fix and test |
|---|---|---|---|
| S1 | P1 | The private/public visibility check ran only in the connection test. The publisher committed without it, so a private feed (every collected event plus guide-derived channel names and times) could land in a repository later made public or mistyped. | `_github_commit` re-checks `full_name` and `private` on every publish and stops before any read or write. Test: `test_publisher_refuses_a_private_feed_in_a_public_repository`. |
| S2 | P1 | A channel list with no M3U header in its first 50 raw lines (leading blank lines, indentation, or a bare URL list) stored stream URLs, which can carry the provider login, as channel names in SQLite, the coverage page and the CSV. | M3U is detected anywhere after stripping, and URL or credential lines are dropped in plain-text mode. Test: `test_stream_urls_never_become_channel_names`. |
| C3 | P1 | Public `broadcast_links` from the looser guide-listing matcher could name the wrong match. Reproduced: "Live: Man City v Liverpool" 14:30 was linked to Manchester United v Liverpool 17:30 and published as Sky Sports Main Event. | Links from `guide_listing_match` stay in the private feed only. Tests: `LooseLinkPublicationTests`. |

## Open — prioritised

### P1

- **C1 — Corroborated events disappear from the public feed when any contributing source is unapproved.** `feed.py licensed()` drops the merged event, so enabling a new private source silently removes approved fixtures. This probably explains why only 16 events are corroborated.
  - Plan: build the public feed from a merge of approved-source events only, and keep the full merge for the private feed.
- **C2 — "Live" can be stale or false.** The published reader rule trusts `status_normalized`, which is a snapshot from the 04:00, 12:00 and 17:00 runs. CricketData expands a started Test into five "live" day records.
  - Plan: publish `status_observed_at`; trust "live" only within start to start + 1.5 × typical duration and for 45 minutes after it was observed; give future Test days `scheduled`.
  - B1G applies the same limit on its side (see the B1G audit).
- **C4 — All enabled guides are loaded at once for linking.** `linking.py` calls `list(epg_guides)` and keeps 1,000-character descriptions it never uses. With 10–40 guides this risks out-of-memory on the mini PC.
  - Plan: stream guides one at a time; slim programme records to title, sub-title and times; keep only the next 8 days.
- **O1 — A slow upstream can hang the collector indefinitely.** Socket timeouts are per read, not per request, and the hang holds the busy lock.
  - Plan: chunked reads with an overall deadline, plus a "collector stuck" watchdog state.

### P2

- **C5 — Clustering for guide-listed live events is quadratic** (55 s on a synthetic Saturday). Index by sport, time slot and team token.
- **C6 — API-Sports live codes map to "unknown".** Unmapped: hockey P1–P3, baseball IN1–IN9, volleyball S1–S5, MMA. Add a mapping test per product.
- **C7 — Stale fixtures never leave.**
  - Deleted or re-dated fixtures stay on their old date.
  - Last-good snapshots are used regardless of age.
  - Plan: drop events missing from a complete scope; stop using snapshots after about 36 h.
- **C8 — Formula 1 duplicates between TheSportsDB and Jolpica/OpenF1:** TheSportsDB events have no session. Derive the session from the title.
- **C9 — A merged event takes its status from the most precise record.** Delayed football-data "TIMED" hides API-Sports 1H/FT. Use the most advanced, most recent status.
- **C10 — Public repository growth.**
  - `guide_map` programme counts change every run; at about 3 commits a day this is roughly 1 GB a year of history.
  - An optional asset over 8 MiB is skipped with no notice.
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

1. **Tiered public "today".** Publish named competitions, UK/IE/FR football, featured nations, PPV and the main sports; move the long tail to an optional asset or the private feed. About 1,900 events today, mostly low-tier football, would become a few hundred.
2. **A light live-status lane.** Call `fixtures?live=all` about every 15 minutes in match hours (around 40 of the roughly 100 daily calls per API-Sports product), together with `status_observed_at`.
3. **A free "verified broadcast" rule.** A strict match, the same slot, a curated registry channel and two or more independent guide families. This is the only free route to `verified_broadcasts` above 0.
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
- **Contract:** schemas, code and fixtures agree (`sli/1.5`).
