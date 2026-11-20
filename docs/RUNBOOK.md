# SportsLiveInfo operations runbook

**Status:** 20 November 2026 · for the Home Assistant App (source at `13a8994`, version string `0.3.24`) · docs only.
**How this was checked:** each step was traced to the code (file and function in brackets). Where a step is a manual
operator action that the code does not automate, it says so. Anything that could not be run from the cloud session
is marked **NOT RUN**. Context: [CURRENT_STATUS](CURRENT_STATUS.md), [AGENT_OPERATING_MANUAL](AGENT_OPERATING_MANUAL.md),
[operator guide](../sportsliveinfo/DOCS.md).

## 0. Where things are

| What | Where |
|---|---|
| The App (Home Assistant) | Slug `106c7bd5_sportsliveinfo` on the owner's Home Assistant OS host, per the 15 November handover. Source: public `jimmyfazz/SportsLiveInfo`. Watchdog: `/healthz?scope=liveness` ([`config.yaml`](../sportsliveinfo/config.yaml)) |
| The App's UI | The SportsLiveInfo sidebar panel (Ingress), or **Settings > Apps > SportsLiveInfo**. Pages: Overview, Live today, Sources & API keys, Sports events, EPG coverage, Channel coverage, Scheduler, Publishing, Diagnostics |
| The App's log | Home Assistant **Settings > Apps > SportsLiveInfo > Log** |
| Public feed | `jimmyfazz/LiveSports-EPG`, branch `main`: `v1/manifest.json` (index), `v1/manifests/<revision>.json` (last 10 revisions) |
| Private feed | `jimmyfazz/LiveSports-EPG-private` (private; owner's TVs only) |
| Persistent state | `/data/sportsliveinfo.sqlite3` inside the App: keys, the GitHub token, settings, snapshots, request counters, the last 300 job rows |

Every page and `/healthz` answer only through Home Assistant Ingress. A direct request is refused with 403, and that is correct.

## 1. The feed has stalled (no new manifest)

**Symptom:** TVs show old data, the Service health card is red, or a "SportsLiveInfo: feed not published" or "scheduler stopped" notification has appeared.

**Step 1. Measure the manifest age.**
- Open `v1/manifest.json` in `LiveSports-EPG`. Read `generated_at` (build time of the last commit), `expires_at` (`generated_at` + 48 h) and `publisher.version`.
- Or open the App's **Diagnostics** page, Service health card:
  - **Last publication (manifest)** is the time of the last real commit. This is the `manifest_age_s` value in `/healthz`.
  - **Last publication activity** also counts an "unchanged" check. The stall rules use this value, not the commit time.

**Step 2. Read what the App says.** The stall checks below are described as unreleased in the [operator guide](../sportsliveinfo/DOCS.md#stall-alerting-and-health-unreleased-after-0324). If the Service health card is missing from Diagnostics, the installed build predates them, and the job rows below are the only evidence.
- **Diagnostics > Service health.** The verdict line lists the stall reasons. The incidents list uses these codes (from `health.py`):

| Code | Meaning | Look next at |
|---|---|---|
| `scheduler_stalled` | The scheduler heartbeat is older than 180 s. The scheduler ticks every 10 s and writes `scheduler_heartbeat`. | App log; restart the App only if the heartbeat stays stale |
| `manifest_overdue` | A scheduled refresh (04:00, 12:00, 17:00 London by default) passed more than `stall_threshold_hours` (default 3) ago and nothing was published since. Only when automatic publishing is on. | Collector and publisher rows below |
| `manifest_old` | No publication activity for 30 h (`MAX_MANIFEST_AGE`). | As above |
| `collector_hung` | A collection started more than 90 minutes ago and has not finished. | Collector row, state `started` with no later `finished` |
| `publish_blocked` | Two publisher rows in a row with state `failed`. | Publisher rows and the message |
| `publish_gate_blocked` | The last publisher row is `blocked`: the pre-publish regression gate refused an automatic publish. Advisory (no 503). One notification (`sportsliveinfo_publish_gate_blocked`) naming events and guide-confirmed bindings before and after; dismissed when a later publisher row is not `blocked` (a manual override, or an automatic run that passes). Not the same as `publish_blocked` (two `failed` rows). | Section 4 |
| `token_expiring` | The GitHub token expires in 7 days or less, or has expired. | Section 2 |
| `source_failing:<name>` | A source failed three refreshes in a row. | That source's row |

- **Diagnostics > Last 35 operations** gives the job rows. Each row has `provider`, `state` and `details`. The rows that matter for a stall:

| `provider` | States written by the code | Meaning |
|---|---|---|
| `collector` | `started`, `finished`, `degraded`, `failed`, `deferred`, `no_sources`, `skipped`, `lane_error` | Summary of a refresh. `skipped` = setup not completed. `degraded` = some sources failed; last-good data kept |
| `publisher` | `preview`, `submitted`, `unchanged`, `blocked`, `failed` | `submitted` = a new commit. `unchanged` = same revision, no commit. `blocked` = the regression gate (section 4). `failed` = GitHub or validation error (message in `details`) |
| `private_publisher` | `failed` | The private feed failed; the public one is unaffected |
| `scheduler` | `error` | The scheduler loop caught an exception (`scheduler still running`) |
| `live_status` | `ok`, `partial`, `failed` | The live-status lane (matches in play) |
| `ui` | `error` | A page action failed; the message says which |
| `dictionary`, `identity` | `ok`, `failed` | Channel dictionary and identity refresh |
| per source (for example `jolpica`, `api_sports`) | `ok`, `deferred`, `failed`, `needs_key`, `unchanged`, `empty`, `stale`, `coverage_collapse` | One source's refresh. `needs_key` = no key saved |

The settle pass (final scores after matches end) writes no job row. Its last run is on the Scheduler page.

**Step 3. Read the App log** (Settings > Apps > SportsLiveInfo > Log). The useful lines:
- `SportsLiveInfo Ingress HTTP ready on internal port 8099`: the web server started. Its absence means the App did not start (check the build log).
- `Feed publication started (<trigger>)` and `Feed publication finished` / `refused` / `failed`. The trigger is `automatic`, `live` or `manual`.
- `Scheduler tick failed` (with a traceback) and `Live status lane failed`.

**Step 4. /healthz.** Reached through Ingress only.
- `200` with `"ok": true`: healthy. Advisory incidents (for example a failing source) still return 200.
- `503` with `"ok": false`, `reason` (text), `reasons` (codes) and `incidents`: a stall. The stall codes are `scheduler_stalled`, `manifest_overdue` and `manifest_old`.
- The body also has `version`, `scheduler_heartbeat`, `manifest_age_s`, `last_publish` and `last_collect_ok`.
- `?scope=liveness` looks at the heartbeat only. The Supervisor watchdog uses it, and a restart cannot fix a stale manifest. Do not restart the App to fix a manifest stall alone.

**Step 5. Likely causes, in order of frequency:**
1. Publishing is off or was turned off (`github.enabled` / `auto_publish`). Then `manifest_overdue` cannot fire. Check the Publishing page.
2. The token was rejected or has expired (section 2): `publisher` `failed` with a 401 or 403 message.
3. The regression gate refused the automatic publish (section 4): `publisher` `blocked`.
4. Every source failed, so the collection was `failed` or `deferred` (section 3 for quotas).
5. The scheduler stopped: heartbeat stale, or the App is not running.

**Expected manifest age (derived from code, not yet observed on the device):** an unchanged feed is recommitted once the last commit is 24 h old, so `manifest_age_s` normally stays near 24 h. A run that lands just inside that window can push it toward 35 h. That is not a stall, because the stall rules use publication activity and the feed expires at 48 h.

## 2. The GitHub token has expired or is about to expire

**Where the token is used:** the public feed and, if enabled, the private feed (`storage.py`, `github.token`).

**Warning:** the App reads the expiry from GitHub's `github-authentication-token-expiration` response header. This works only for fine-grained tokens with an expiry date. A classic token has no expiry, so there is no warning. The warning appears seven days before expiry and as a notification (`token_expiring`). The Diagnostics card shows **GitHub token expiry** and the days left.

**Symptoms:** publisher `failed` rows with `GitHub rejected the saved token (401)` or `GitHub denied access (403)`. These text messages come from `engine.py`.

**Steps (owner, in the UI):**
1. On GitHub, create a new fine-grained token as described in [the operator guide](../sportsliveinfo/DOCS.md#github-token-first-time-setup-public-read-only-feed-destination). Resource owner `jimmyfazz`; repository access **only `LiveSports-EPG`** (and `LiveSports-EPG-private` if the private feed is used); **Contents: Read and write**.
2. In the App, open **Publishing**. Paste the token into the masked input and press **Save GitHub settings**. Do not change the other fields unless they are wrong.
3. Press **Test saved GitHub connection**. The check authenticates, confirms the repository and branch, and then makes a write probe: it creates one unreferenced blob (`POST /git/blobs`). It adds no commit and changes no file. The "no upload" card on the page describes this. (The operator guide still says the test is read-only; that sentence is out of date.)
4. Press **Publish feed now**. This is the only proof of a real commit. If the feed is unchanged and the last commit is less than 24 h old, the publish reports "unchanged" and makes no GitHub write.
5. Check Diagnostics: the publish status should read `succeeded`, and the token expiry should show the new date.

Remove the old token from GitHub after the new one works. Never paste a token into chat, an issue, a log or a commit.

**Provider API keys** (API-Sports, football-data.org, CricketData) have no expiry tracking in the App. An expired key shows as a source failure: `HTTP 401: check the saved key` (or "Provider rejected the API key"). After three failed refreshes the source is reported as `source_failing`. Replace the key on **Sources & API keys** and press **Test** for that source.

## 3. A quota is exhausted

There are three kinds of counter, all stored per UTC day in the `requests` table.

| Counter | Name in the table | Limit (code constant) | What happens at the limit |
|---|---|---|---|
| Sports sources | the source name, for example `api_sports` | the source's daily limit in `providers.SPORTS` | A scheduled refresh raises `QuotaExhausted`. The source is recorded as `deferred` with `Provider quota or throttling; retry after …`, or `Local daily request budget exhausted`. Last-good data is kept. |
| Live status lane | `live:<product>` | `LIVE_DAILY_BUDGET` = 40 per product | The lane skips a product once its usage reaches the product limit minus `LIVE_RESERVE` (20). It records the note "remaining calls kept for scheduled refreshes". It is not a failed job. |
| Settle pass (final results) | `settle:<product>` | `SETTLE_DAILY_BUDGET` = 4 per product | At most one call an hour, and it also counts against the product quota. |
| EPG guides | the guide name | the guide's daily limit | `Local daily guide request budget exhausted; resets at 00:00 UTC`, recorded as `deferred`. |

**Where to read the counters:** Scheduler page (live status card: live calls, settle calls and the last settle summary); Diagnostics: **Requests reserved today (UTC)**, the **Calls today** column, and the **Live-lane calls today** row in Service health.

**Standings:** once `feat/standings-asset` is merged (release/20nov), tables are collected once per London day by `standings.py` from football-data.org (own counter `standings:football_data`, up to 12 calls a day) and optionally API-Sports (`standings_api_sports`, counter `standings:api_sports`, 4 calls a day). Kill switch: config `publish_standings` (contract §4.6). On code before that merge there is no standings source.

**What to do:**
- Do not raise a limit to clear the message. The limits protect the free plans.
- Counters reset at 00:00 UTC.
- A 429 or `Retry-After` sets a backoff (`sports_backoff:<name>`). The App waits until that time. There is no UI to clear it early.
- To stop live calls, switch off the live lane (section 6, `live_status`). This also stops the settle pass.
- The API-Sports free plan covers only yesterday, today and tomorrow. The App learns the plan window from a refusal (`PlanWindow`). A "today is outside the provider plan's dates" note is expected, not a fault.

## 4. A publish is blocked by the regression gate

**What it means:** an **automatic** publish (scheduled, or after a live-lane change) was refused because the new feed has more than 20 % fewer events, or fewer guide-corroborated bindings, than the feed last published. The baseline must be at least 5 (`PUBLISH_REGRESSION_THRESHOLD`, `PUBLISH_REGRESSION_MIN_BASELINE`, `publish_regression` in `engine.py`). The last published feed stays live.

**Where it shows:**
- Diagnostics: a `publisher` row with state `blocked` and the message `Automatic publish refused: events fell from N to M (more than 20%)…; Publish manually to override`.
- Publishing page: the publish status is `failed`, with the same message.
- The key `publish_gate` in the App database holds the last refusal (reason, events and bindings before and after). Diagnostics > Service health lists it as `publish_gate_blocked`, `/healthz` shows it under `advisories` (still HTTP 200), and one Home Assistant notification is sent per incident.

**Caveat (verified in `health.py`):** a `blocked` row is not a failed publish. It does not count toward the "publishing is failing" notification (`publish_blocked`, which needs two `failed` rows in a row), and it is not a stall code. It raises its own advisory incident, `publish_gate_blocked` (since the follow-ups branch). The App will raise "feed not published" (`manifest_overdue`) only if no publication activity follows a scheduled refresh.

**What to do:**
1. Decide whether the drop is real. Check the failing sources (section 1, Step 2) and whether the Sports events page has lost a whole competition. A source outage causes a drop that is not real. Fix the source first.
2. If the drop is real (a source removed a competition, the season ended, a source was turned off), override deliberately: **Publishing > Publish feed now**. A manual publish uses `allow_regression=True` for that run only.
3. The override becomes the new baseline. The next automatic run compares against it, so a deliberate override is not blocked again.
4. Record the decision in `IMPLEMENTATION_PROGRESS.md` if the change is material.

Never edit the threshold to get past a block. Changing the threshold is a code change that needs review.

## 5. Rollback (republishing a previous revision)

**Supported by the App: no, but a tool builds the rollback manifest.** Nothing in `src/` republishes an earlier revision; `tools/republish_revision.py` does it as a manual operator step.

**Why restoring the old `manifest.json` does not work (audit 20 Nov 2026, CA-07).** B1G ignores any manifest whose `generated_at` is older than the one it already holds (`SliFeedUpdater.kt`, the cache guard). A restored manifest keeps its old `generated_at` (and an `expires_at` that is probably past), so every TV keeps the bad feed. The correct rollback is therefore a **new revision**: the old asset set under a fresh `generated_at`, `expires_at`, `revision` and `previous_revision`.

**What exists to work with:**
- The public repository keeps the last 10 revisions: `v1/manifests/<revision>.json` and the assets they reference (`FEED_RETAIN = 10`). Older files are deleted in the same commit and are only in git history.
- Every feed commit is a single atomic commit with the message `SportsLiveInfo feed <revision> (<n> events)`.

**Manual rollback (operator action outside the App; not run against the real feed, owner approval required):**
1. **Stop the App writing first.** Untick **Enable publishing** on the Publishing page and save. Otherwise its next run commits its own current build over the rollback.
2. Update a clone of `LiveSports-EPG` (`git pull`). Pick the target revision from `v1/manifests/` (or `git log --oneline -- v1/manifest.json`; restore missing asset files from that commit first).
3. Dry run: `python3 tools/republish_revision.py --repo <clone> --revision <old revision>`. It checks that every asset file exists and matches its sha256, and prints the new revision, `generated_at` and `expires_at`. It refuses a clock behind the current manifest.
4. Apply: the same command with `--apply`. It writes `v1/manifest.json` and `v1/manifests/<new revision>.json`. Commit both as **one new commit** and push. Never force-push or rewrite history.
5. Check from a TV or `curl`: the manifest has `rollback_of` set, a newer `generated_at`, and the old asset hashes. `refresh.collected_at` still shows the old collection time, which is honest.
6. Re-enable publishing only when you know what the next run should publish. The next App run will replace the rollback with its own build; fix the data problem first, or keep publishing off.

**Limits:** the `live` asset in an old revision holds old statuses (readers treat anything older than 45 minutes as not live). If the Home Assistant clock ever jumps forward, TVs reject later manifests until `generated_at` passes it: use the same tool with a correct clock, never a forged time. A monotonic `sequence` (audit suggestion) is not implemented.

**App code rollback** (not the feed): restore the App backup taken before the update (section 7). Whether a backup restore also reverts the App image is **not verified**. Check on the device. Otherwise reinstall the previous source revision as described in [the operator guide](../sportsliveinfo/DOCS.md#update-an-existing-local-installation).

## 6. Kill switches

All keys live in the App's `config` row in `/data/sportsliveinfo.sqlite3`. The defaults are in `DEFAULT` in `storage.py`. The "Set by" column says whether the UI can change the key.

| Config key | Default | Effect when off | Set by |
|---|---|---|---|
| `live_status` | `True` | Stops the live-status lane and the settle pass. Scheduled refreshes continue. | Scheduler page: "Check live statuses during matches" (action `live_status`) |
| `score_approvals` | `[]` | No scores are read, stored or published. The feed stays `sli/1.6`. Removing a source from the list is the kill switch for that source (the next feed says `enabled: false`). | Publishing page: Score approvals (action `score_approvals`). Only `SCORE_ELIGIBLE` sources are accepted |
| `publish_crest_refs` | `False` | Team crest references (API-Sports) are not published; `rights.crests.monogram_only` stays true. Also needs the API-Sports source in `publication_approvals`. | Publishing page: Team crests (action `crest_settings`); switching on needs the attestation tickbox, switching off does not |
| `crest_device_lookup_thesportsdb` | `False` | Only sets the manifest flag `rights.crests.sources.device.enabled`. No lookup code exists in `src/`. | Publishing page: Team crests (same form) |
| `binds_rule`, `rights_holder_prior` | `narrow`, `False` | `legacy` restores the 0.3.24 binding rule; `rights_holder_prior` false publishes no prior links. | Shown read-only on the Publishing page (Channel link policy); change in the stored config |
| `broadcaster_rank_override`, `rights_holder_prior_override` | empty | Empty = the built-in seeded tables (byte-identical feed). JSON text corrects them; validated on save. See `docs/SEEDED_TABLES_REVIEW.md`. | Publishing page: Correct the seeded tables (action `hint_overrides`) |
| `publication_approvals` | `[]` | Publishing is refused with "No sport source has an approved public redistribution licence". Removing a source stops its events in the next publish. It does not withdraw data already published. | Publishing page: approvals (action `approvals`) |
| `github.enabled` | `False` | No publishing (manual or automatic). | Publishing page: Enable publishing |
| `github.auto_publish` | `False` | No automatic publishing; manual publish still works. | Publishing page: Publish automatically after every scheduled refresh |
| `private_feed.enabled` | `False` | No private feed. The public feed is unaffected. | Publishing page: Enable private feed |
| `sports.<name>`, `epg.<name>` | `False` (`jolpica` is on) | That source is not collected. | Sources & API keys (checkbox) |
| `dictionary.<region>` | `False` | That region is left out of the published channel dictionary. | Sources & API keys |
| `schedule` | `04:00, 12:00, 17:00` (London) | Changes refresh times. | Scheduler page |
| `setup_complete` | `False` | Nothing collects or publishes until the first-run setup is finished. | Sources page (finish) |

Note on the crest keys: both are now on the Publishing page. Crest references publish the provider media address (media.api-sports.io) for team crests, so switching either on requires the owner to tick that the crest and badge terms were read; untick both and save to switch both off. **Standings:** no switch exists (see section 3).

## 7. Backing up the App

1. Before any update, create a Home Assistant backup that includes the SportsLiveInfo App. Name it `SportsLiveInfo <old version> before <new version>` (Settings > System > Backups). The App's data is `/data/sportsliveinfo.sqlite3`.
2. **Treat the backup as a secret.** The database holds API keys and the GitHub token in plain text. Masked HTML in the UI is not encryption. Keep the backup off the device and protect it.
3. Confirm the backup appears in the list **before** you update. If the Home Assistant MCP connector reports "SSE stream ended", the backup may still have completed. Check the list before you retry.
4. The public repository is itself a backup of the feed. A full copy can be made with `git clone --mirror` of `LiveSports-EPG`.
5. Known leftover: `local_sportsliveinfo` (0.3.4), a stale local copy on the device. Removing it is optional and is an owner decision.

## 8. Checking after an update

1. **Log line:** the App log has `SportsLiveInfo Ingress HTTP ready on internal port 8099`. If it is missing, the App did not start. Check the build log before anything else.
2. **Version:** every page footer shows the version (`server.py`). `/healthz` returns it in the `version` field. Both come from `__version__` in `__init__.py`.
3. **Settings:** the saved keys, source checkboxes and the Publishing and Scheduler settings are unchanged. A backup restore is the fallback.
4. **Refresh:** press **Refresh EPG**, then **Refresh sports** on the Overview page, and check Diagnostics for `collector` and per-source rows.
5. **Next manifest:** after the next scheduled slot (04:00, 12:00 or 17:00 London), `v1/manifest.json` should show the new `publisher.version`, a newer `generated_at` and `expires_at` 48 h after it. The Diagnostics **Last publication (manifest)** should move too.
6. **Live lane:** the Scheduler page should show the live card; its counters should tick up during matches.

If step 5 fails, go to section 1. Do not publish manually to force it before reading the publisher row.

## 9. Who to ask

- **The owner (`jimmyfazz`)** decides on: merges, deployments, Home Assistant changes, provider keys and plan changes, publication approvals, new kinds of public data, and any deletion. See [AGENT_OPERATING_MANUAL section 7](AGENT_OPERATING_MANUAL.md#7-when-to-stop-and-ask-the-owner).
- For a stall you cannot explain, give the owner: the manifest's `generated_at` and `revision`; the Diagnostics **Service health** verdict and the last 35 operations; the App log lines above; and the App version. Leave out keys, tokens, channel lists and stream URLs.
- The TV side (B1G) is a separate repository, `jimmyfazz/B1`. See its handover.

## 10. What this runbook does not cover

- Adding a source, changing a matcher or changing a wire format. Those follow the contract in [FEED_CONTRACT_SLI_V1.md](FEED_CONTRACT_SLI_V1.md) and the release steps in [the 15 November handover](HANDOVER_2026-11-15_SPORTSLIVEINFO_B1G.md).
- Rights: no public programme text is published without documented rights ([RIGHTS_RECORD.md](RIGHTS_RECORD.md)).
