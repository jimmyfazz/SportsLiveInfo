# SportsLiveInfo installation and operation

[SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) provides the Home Assistant App.
[LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is the separate data-feed destination.
See [current status](../docs/CURRENT_STATUS.md) for verification and release checks.

## Update an existing local installation

1. Make an App backup and retain the prior App source revision for rollback. Keep the existing `local_sportsliveinfo` installation.
2. Copy the reviewed revision’s `sportsliveinfo/` directory contents into the existing `/local_apps/sportsliveinfo/` directory. That folder should contain `config.yaml`, `Dockerfile`, `src/`, `icon.png`, `logo.png` and the App documentation.
3. In the Home Assistant App store, check for updates. Update the existing SportsLiveInfo App and check its build log. The App stores credentials, selections and snapshots in `/data/sportsliveinfo.sqlite3`, separate from the source directory.
4. Open the App and verify the version, saved-key indicators, source selections and scheduler settings. Run **Refresh EPG**, then **Refresh sports**, and inspect Diagnostics. Restore the App backup and prior source if rollback is needed.

## Install on a new Home Assistant OS host

Add the public [SportsLiveInfo repository](https://github.com/jimmyfazz/SportsLiveInfo) in the Home Assistant App store and install SportsLiveInfo, or copy the reviewed App directory to `/local_apps/sportsliveinfo/` and install it from Local apps. Supported architectures in the package are amd64 and aarch64. See the [Home Assistant local App tutorial](https://contributors.home-assistant.io/apps/first-app/).

In **Sources & API keys**, select the keyless sports and private guide groups with **Tick all** or individual checkboxes, then save each group. Test unfamiliar sources individually and enter keys where required. Review the scheduler, finish setup and check the first collection in Diagnostics.

## Features present in source

| Screen / component | Current behavior |
|---|---|
| Sources / setup | Individual source selection and Save/Test; optional key settings for API-Sports, football-data.org and CricketData.org; keyless providers identified |
| Live today / events | Classified and fused fixtures, UK times, featured groups, filters and explicitly provisional EPG channel candidates |
| EPG coverage | Private source programmes, canonical identity hints, 24/72/168-hour gaps and family/service diagnostics |
| Schedule | Europe/London daily refresh slots, durable claims, manual-refresh overlap protection; defaults 04:00, 12:00 and 17:00. **Live status lane** (0.3.23, on by default once an API-Sports key is saved): while a collected event is between its start and expected end, the API-Sports live board is read at most every 15 minutes, at most 40 calls a day per product inside that product's quota (20 calls always kept for the scheduled refreshes). Status changes are published as the small `live` asset when automatic publishing is on. Switch it off here |
| Diagnostics | Last-good snapshots, source errors, daily UTC request counts and bounded recent job history |
| Publishing | Local preview, masked fine-grained token setup, separate GET-only connection check and optional atomic static-feed publication |

New guide sources and newly added sports adapters are opt-in. API-Sports products share one saved key setting. Configured daily limits are local budgets.

Sports source tests make one quota-accounted request. EPG tests download and parse a bounded guide. Tests may update diagnostics/quota usage but do not replace source snapshots or authorize publishing. A successful test is not a completeness or rights check.

## Stall alerting and health (unreleased, after 0.3.24)

SportsLiveInfo now tells you when the feed stops moving. On 20 Nov the published manifest stayed at 03:42Z for more than three hours and nothing said so.

**What is checked** (Diagnostics > Service health shows all of it, with a red banner on every page while stalled):

| Check | Counts as a stall (HTTP 503) | Notes |
|---|---|---|
| Scheduler heartbeat | older than 180 s | clears when under 60 s; a restart gets a 180 s grace |
| Manifest overdue | a scheduled refresh slot (Europe/London) passed more than the threshold ago and nothing has been published since | threshold default 3 h; only when automatic publishing is on and approved |
| Manifest too old | no publication activity for 30 h | the manifest expires at 48 h |

"Publication activity" is a commit, or a publish attempt that found the feed unchanged. Between a slot's grace period and the next slot there is nothing to alert on, so overnight (after the 17:00 run) and the gaps between runs are the quiet periods; nothing needs configuring. A stall latches and clears only after the condition has been false for 10 minutes (2 minutes for the scheduler), so it cannot flap.

Also reported, each as one notification but **not** a 503: publishing failed twice in a row, the GitHub token expires within 7 days (read from GitHub's response header; fine-grained tokens with an expiry only), a source failed three refreshes in a row, a collection started more than 90 minutes ago and never finished.

**`/healthz`:** `200` healthy, `503` with `{"ok": false, "reason": "...", "reasons": [codes]}` when stalled. `/healthz?scope=liveness` looks at the scheduler heartbeat only; the Supervisor watchdog uses that one, because restarting the App cannot fix a stale manifest caused by a revoked token or a failing source. Like every page it answers only to the Ingress/Supervisor address.

**Home Assistant notifications:** the App declares `homeassistant_api: true` and posts a persistent notification through the Supervisor (`persistent_notification.create`, id such as `sportsliveinfo_feed_stalled`) once per incident, and dismisses it when the incident has recovered. A failed notification is logged (error type only, never the token) and retried every 15 minutes; it never affects collection or publishing. Without a Supervisor token (development) nothing is sent. Installing this version asks you to approve the new Home Assistant API permission.

**Option:** *stall_threshold_hours* (default 3, range 0.5 to 48) in the App Configuration tab: how long after a scheduled refresh the manifest may stay unpublished before it counts as overdue.

Not done: Home Assistant sensor entities (for example `sensor.sli_manifest_age`). States posted through the REST API disappear on every Home Assistant restart and have no unique id, so they cannot be placed on dashboards reliably; the notification, `/healthz` and the status page cover the need. A proper integration would be a separate task.

## Channel coverage (your channel list, kept on Home Assistant)

1. Open **Channel coverage**. Import your provider's M3U playlist or a text file with one channel per line.
   - The list is stored only in this App's database. It is never published or sent to GitHub.
   - Stream addresses (which contain your provider login) are discarded while the file is read.
2. The report shows, for every channel (entertainment, movies, kids, news, documentaries, music, sport …):
   - whether it is identified;
   - which guide carries it;
   - which guides and dictionary regions to switch on.

   **Download the per-channel table (CSV)** keeps a copy on your device. It is also the reference that B1G's channel matching is checked against.
3. **Survey every guide** downloads each guide in the catalogue once, including those marked "verify". It keeps only channel names and counts and switches nothing on. Allow 20–40 minutes and about 1 GB.
4. **Delete channel list** removes the list and the report.

## Important limits

The current `sli/1.0` output has events, taxonomy, channel/guide metadata, Today grouping and health, **no EPG programme rows**. The local suggestion evaluator in `supplement.py` does not implement a public programme supplement or a B1G Guide reader. Keep provider EPG primary and preserve local account, manual mapping and hidden choices. Provisional candidates are not verified broadcasts or playable streams.

See [current validation](../docs/CURRENT_STATUS.md) for tested behaviour and open deployment checks.

## GitHub token: first-time setup (public read-only feed destination)

The **Publishing** tab now includes this guide and a nonpublishing **Test saved GitHub connection** button. You do **not** need a token to use the app's local EPG/sports dashboards; this is only for uploading *rights-approved* JSON snapshots to the public output repository.

1. Sign into GitHub as `jimmyfazz`, then open **[Generate a fine-grained token](https://github.com/settings/personal-access-tokens/new)** under Settings → Developer settings → Personal access tokens → Fine-grained tokens. Avoid a broad classic `repo` token.
2. Choose a clear name, e.g. `SportsLiveInfo Publisher`, and an expiry, e.g. **90 days**. Record the renewal date; the token will stop working after expiration or revocation.
3. Set **Resource owner = jimmyfazz**. Under **Repository access**, choose **Only select repositories**, then select **LiveSports-EPG** (and no other repository).
4. Under **Repository permissions**, select **Contents: Read and write**. Leave unnecessary permissions disabled/default; click **Generate token** and copy it directly into Home Assistant.
5. In SportsLiveInfo → **Publishing**, confirm owner `jimmyfazz`, repository `LiveSports-EPG`, branch `main`; paste the token into the masked input and click **Save GitHub settings**. Saving does not alter other provider API keys or automatically enable publishing.
6. Click **Test saved GitHub connection**. This issues only authenticated GET requests against the repository and branch; it cannot verify `Contents:write` with certainty without an actual authorised publication. Fix any 401/403/404 message and repeat.
7. Keep **Enable publishing** and **Publish automatically** OFF until there are correctly collected events, approved public redistribution rights and a reviewed feed preview. Enabling the switch is not evidence of source permission. After a permitted upload, verify the public manifest/asset checksums anonymously.

The **public data repository** is [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG); the **Home Assistant App installation/source repository** is the separate `SportsLiveInfo` repository. Publishing is outbound-only: no incoming Home Assistant access, port forwarding, TV GitHub tokens or TV uploads.

**Security:** Never put this token in chat, Issues, code, logs, screenshots or the public data repository. Saved credentials remain private to the HAOS App volume; Home Assistant backups containing `/data` must be protected. To rotate an expiring token, generate a replacement and use the same masked input to save it. Official instructions: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens.

## Keys, data and security

- API keys, the publishing token, settings and snapshots remain in `/data/sportsliveinfo.sqlite3`. Masked HTML is not encryption at rest; protect App storage and backups and rotate expiring keys.
- The default GitHub destination is owner `jimmyfazz`, repository `LiveSports-EPG`, branch `main`; both publishing switches default OFF. The fine-grained publisher token must be restricted to that public feed repository. It is not an App installation credential.
- The UI uses an internal listener on port 8099, trusted peer checks and CSRF. App config exposes no host ports. Use Home Assistant Ingress; do not forward a WAN port or publish the App endpoint. Existing owner remote administration remains separate.
- The database retains 300 recent job results; diagnostics must stay free of secrets. Source failures preserve last-good data. No persistent notifications are currently sent to HA Core.
- TVs must only read the eventual public feed; no GitHub write credentials, source API keys, private accounts or stream URLs belong in that feed. TMDB/OMDb and VOD artwork remain in B1G.

## Build and updates

The Dockerfile uses `python:3.12-alpine`, a floating minor-family tag rather than a digest-pinned image, and standard-library application code. It declares amd64/aarch64 support and Supervisor labels, but real architecture builds remain unverified. For a code upgrade, refresh the local App files and follow the installed Supervisor's rebuild/update flow; preserve `/data` and verify the chosen revision. No release readiness is implied by this documentation refresh.
