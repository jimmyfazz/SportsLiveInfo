# Operations hardening (unreleased, after 0.3.24)

What keeps the collector alive, small and observable, and what the owner does for the three things code cannot do (history squash, release bump, the dead-man workflow). Findings: [audit](AUDIT_2026-11-15_FORENSIC_SPORTSLIVEINFO.md) O1, O3, C4, C10. Status: implemented on branch `fix/ops-hardening`, **not released, not run on Home Assistant**.

## 1. A slow upstream cannot hold the collector (O1)

| Limit | Value | Where |
|---|---|---|
| One HTTP request, including the body (read in 64 KiB chunks) | `providers.REQUEST_DEADLINE` 120 s | `providers.fetch` |
| One source collection (all its requests and the XMLTV parse) | `providers.SOURCE_DEADLINE` 900 s | `Engine._collect_sport`, `_collect_epg`, survey and test button |
| One whole collection | `engine.COLLECTION_DEADLINE` 2700 s | `Engine._collect_run` |

The per-read `timeout=30` stays, and before each chunk the socket timeout is set to the time left. Deadlines travel in a thread-local (`providers.deadline_scope`), so `providers.fetch` keeps its signature. Past a request or source deadline the call fails with `DeadlineExceeded` (a `TimeoutError`): the source is recorded as failed ("Upstream too slow") and last-good data stays.

Last resort: a lane still running at the whole-collection deadline is abandoned (`pool.shutdown(wait=False)`), the `collector` job is recorded as `stuck`, the busy lock is released and whatever lanes finished is still materialised and published. Health reports `collector_stuck` (advisory, a Home Assistant notification) until the next collection finishes. The older `collector_hung` (a `started` job older than 90 min) still catches a crashed worker.

Known gap: the connect and response-header phase is bounded by the 30 s per-read timeout only, not by the wall-clock deadline (urllib gives no hook before the response exists). A header-dripping server could stretch one request; the source and collection deadlines still end the collection.

## 2. Memory (C4, O3)

- `providers.decode_xmltv` takes a process-wide gate (`PARSE_GATE`, one parse at a time, `PARSE_CONCURRENCY`), so the scheduled lane, the coverage survey and the Test button never parse two guides at once. A parse waits at most `PARSE_WAIT` (600 s, never longer than its source deadline), then fails cleanly.
- Programme records no longer keep the description (never read anywhere).
- Linking streams guides: `Engine._guide_sources` returns a `linking.GuideStream`. Pass 1 loads each guide for its channel names only; pass 2 loads each guide again, slims it (`linking.slim_guide`: ids, title, sub-title, times, `is_live`, `is_repeat`; programmes within now-3 days to now+10 days) and discards it before the next. Peak memory is one guide. The guide's full coverage span is kept so "guide does not cover this time" verdicts are identical to before (test `GuideStreamTests`).
- Not done: moving the Test button to a background job; `identity.build_from_store` already fingerprints one guide at a time.

## 3. Asset size (C10)

See [feed contract §2.1](FEED_CONTRACT_SLI_V1.md). Deployed TVs refuse an asset over 8 MiB; B1G is being updated separately to accept up to 40 MiB, but SportsLiveInfo keeps every part under 8 MiB so TVs that are not updated keep working. At 80% a manifest notice, a `health.asset_budget` field and a Home Assistant notification (`asset_size`) appear; over the cap the dictionary (and guide map) is split into parts, never dropped. Tests: `AssetPartsTests`.

## 4. History budget and alert (C10)

Every revision is a git commit; its new files stay in history forever. `engine._commit_feed` writes a ledger (`feed_growth`: time, bytes uploaded, files) per public commit. `feed.growth_report` projects a year from the last 7 days.

| Budget | Value | Why |
|---|---|---|
| Commits per day (7-day average) | 8 | about 3 a day is normal (04:00, 12:00, 17:00) plus live-lane changes |
| Live-lane commits per day (7-day average) | 60 | Decision 20 Nov 2026 (CA-18): `LIVE_REFRESH` is 15 minutes, so an unchanged live status is re-committed about 4 times an hour while events are in play (a busy Saturday is 40 or more). The ledger marks these commits `kind: live`; they are exempt from the 8-a-day budget and counted against this one, so the alert cannot fire permanently just because matches are on. They are small (live asset plus manifests) and still count towards the bytes budget |
| New blobs per year | 1 GB | audit estimate at 3 commits a day with `guide_map` counts changing every run |

Over either budget health raises `feed_growth` (advisory, a Home Assistant notification); no projection is made from less than a day of history. Tests: `FeedGrowthTests`.

## 5. Squashing the feed repository history (owner, about once a year or when `feed_growth` fires)

The feed repository is data only, so history has no value beyond the 10 retained manifests. Squash with a force push; this rewrites a public branch, so it is the owner's decision (manual, not automated, not done by any agent):

1. Pause publishing (Ingress, Publishing, untick automatic) and wait for any publication to finish.
2. Clone the feed repository. Check the working tree is the current feed (`v1/manifest.json` is fresh).
3. `git checkout --orphan squashed && git add -A && git commit -m "Squash feed history"`.
4. `git push --force origin squashed:main` (temporarily allow force pushes on `main` in the branch protection, if enabled; restore afterwards).
5. GitHub keeps unreferenced objects for a while; to reclaim space contact GitHub support or recreate the repository (the TVs read the same URL only if the owner and name are unchanged, so prefer the force push).
6. Resume publishing and check the next manifest. The publisher reads the remote tree each time, so the local ledger needs no reset.

Not done: bucketing `guide_map` `programmes_7d` (it would cut growth most but changes what B1G ranks by; needs a B1G-side check first).

## 6. Releases (owner)

The version lives in `sportsliveinfo/config.yaml`, the `ARG BUILD_VERSION` default in `sportsliveinfo/Dockerfile` and `sportsliveinfo/src/sportsliveinfo/__init__.py`. `python3 tools/bump_version.py <X.Y.Z> --title "..."` changes all three and adds `## X.Y.Z` to `sportsliveinfo/CHANGELOG.md` (the `## Unreleased` topics above the previous release become `###` sections under it); `--dry-run` shows the change and `--check` only verifies agreement. After a bump run `PYTHONPATH=sportsliveinfo/src python3 tools/generate_feed_fixtures.py` (the manifest carries the version), the unit gate, and copy the fixtures to B1 if the wire changed. CI (`.github/workflows/verify.yml`) fails on disagreement, on a fixture diff after running the generator, on an unparsable `schemas/*.json`, on a pyflakes finding, and on any failing test.

## 7. Dead-man workflow for the public feed repository (owner installs; not installed anywhere)

The add-on can only alert while it runs. [`examples/liveSports-epg-deadman.yml`](examples/liveSports-epg-deadman.yml) runs on GitHub every 30 minutes inside the **LiveSports-EPG** repository, reads `v1/manifest.json` and opens one issue (label `feed-stalled`) when `generated_at` is older than the newest scheduled slot (`refresh.schedule_europe_london`, London time) that passed more than 3 hours ago. GitHub e-mails the owner about a new issue. It closes the issue itself when a later run finds a fresh manifest.

Install:
1. In `jimmyfazz/LiveSports-EPG` create `.github/workflows/deadman.yml` with the file's contents (web editor: Add file, Create new file, commit to the default branch).
2. Settings, Actions, General: Actions allowed; Workflow permissions can stay read-only (the file asks for `issues: write` itself, which a read-only default does not block for the workflow's own declared permissions; if the first run reports "Resource not accessible by integration", select Read and write).
3. Settings, General, Features: Issues enabled. Check Watch settings so issue e-mails reach you.
4. Actions tab, Feed dead-man, Run workflow once; it should end green with "Healthy". To test the alert, temporarily set `GRACE_HOURS` to `0` and the cron to a time right after a slot, or run it against a copy with an old `generated_at`.
5. GitHub pauses scheduled workflows in a repository with no activity for 60 days. A feed that is dead for 60 days therefore disables its own dead-man switch; re-enable it in the Actions tab.

Note on Actions: the owner decided not to pay for CI in the B1 repository. This workflow runs in the public LiveSports-EPG repository (free for public repositories) and needs no paid minutes. The tests for its decision logic are `DeadManWorkflowTests` in `tests/test_ops_hardening.py`.
