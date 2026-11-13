# SportsLiveInfo — private installation and operation

> **Current documentation context — reviewed 12 November 2026.** Experimental v0.3.0 source is present. Current source/test evidence and open deployment gates are centralized in CURRENT_STATUS; historical version receipts elsewhere are not current pass claims.
> **Repository roles:** [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is PRIVATE source/installation and stays private; [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is PUBLIC daily data only. [Current status and evidence](../docs/CURRENT_STATUS.md).

**v0.3.0 · experimental · reviewed 12 November 2026.** Read [current status and test evidence](../docs/CURRENT_STATUS.md) before deployment. Source code, a package layout and offline checks exist; actual Docker/HAOS and TV acceptance remain open.

## Two repositories

- **Private source/installation:** [jimmyfazz/SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo). Keep this private. Its `sportsliveinfo/` folder is the App build context.
- **Public daily data feed:** [jimmyfazz/LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG). This is not an App installation repository. Only its README was present when checked on 12 November 2026.

## Private local installation on HAOS

1. Confirm the host is Home Assistant OS and its architecture is amd64 or aarch64. An entity-only MCP connection cannot establish this.
2. On your computer, authenticate to the private SportsLiveInfo repository with your existing GitHub access and obtain the reviewed source revision. Keep source-download credentials separate from the feed-publishing token; do not embed credentials in clone URLs or copied files.
3. Copy the **contents of the repository's `sportsliveinfo/` folder** to `local_apps/sportsliveinfo/` on Home Assistant using an existing local file-transfer method. Terminal & SSH exposes this as `/local_apps/sportsliveinfo/`. The resulting folder must contain `config.yaml`, `Dockerfile`, `src/`, `icon.png`, `logo.png` and the App documentation. Do not copy only the Python source or nest the full repository inside the App folder.
4. Open **Settings → Apps → Install app**, select **Check for updates**, and look under **Local apps** for SportsLiveInfo. Install, inspect the build log, then Start and Open web UI. Enable Start on boot after confirming startup.
5. Choose permitted sources. In Sources & API keys, use Tick all or select individual keyless sports sources, then Save selected sources. The private EPG guide group has its own save. Test unfamiliar guides individually. Save/test optional keys separately, set refresh times and finish setup. Use **Refresh both engines now** and Diagnostics to inspect source results. Publishing may remain disabled while local collection is tested.
6. Verify settings survive restart and backup/restore before relying on it. Back up private `/data` before upgrades; retain the previous App source revision for rollback. A documentation update alone requires no App rebuild or version bump.

This follows Home Assistant's [local App tutorial](https://contributors.home-assistant.io/apps/first-app/), checked 12 November 2026. It is an App, not a HACS integration. Do not make the source repository public for installation, place a private-source credential in the public feed, or assume an unauthenticated custom-repository URL can fetch private code. A separately implemented authenticated installation path would need its own validation.

## Features present in source

| Screen / component | Current behavior |
|---|---|
| Sources / setup | Individual source selection and Save/Test; optional key settings for API-Sports, football-data.org and CricketData.org; keyless providers identified |
| Live today / events | Classified and fused fixtures, UK times, featured groups, filters and explicitly provisional EPG channel candidates |
| EPG coverage | Private source programmes, canonical identity hints, 24/72/168-hour gaps and family/service diagnostics |
| Schedule | Europe/London daily refresh slots, durable claims, manual-refresh overlap protection; defaults 04:00, 12:00 and 17:00 |
| Diagnostics | Last-good snapshots, source errors, daily UTC request counts and bounded recent job history |
| Publishing | Local preview, masked fine-grained token setup, separate GET-only connection check and optional atomic static-feed publication |

There are 16 sports adapter entries and 30 EPG candidates across 15 markets. The 24-sport/127-competition taxonomy is classification data, not a promise of actual source coverage. Ten API-Sports adapters share one saved key setting. OpenLigaDB's configured budget is 12/day; all configured budgets are local limits, not verified supplier allowances. Jolpica is initially selected; collection waits for setup completion. New adapters and all EPG candidates are opt-in.

Sports source tests make one quota-accounted request. EPG tests download and parse a bounded guide. Tests may update diagnostics/quota usage but do not replace source snapshots or authorize publishing. A successful test is not a completeness or rights check.

## Important limits

The current `sli/1.0` output has events, taxonomy, channel/guide metadata, Today grouping and health, **no EPG programme rows**. The local suggestion evaluator in `supplement.py` does not implement a public programme supplement or a B1G Guide reader. Keep provider EPG primary and preserve local account, manual mapping and hidden choices. Provisional candidates are not verified broadcasts or playable streams.

The current Python 3.12.15 suite passes all 88 tests. HTTP-handler tests use an in-memory transport in this socket-restricted runner; real loopback is not verified. No actual HAOS install, Docker build, live provider benchmark, source redistribution approval, public feed deployment or B1G one/ten-TV acceptance was established. Persistent Home Assistant notifications, monthly/provider-timezone budgets, ETag/304 and full Retry-After/backoff remain outstanding. See [current status](../docs/CURRENT_STATUS.md) for exact errors and release gates.

## GitHub token: first-time setup (public read-only feed destination)

The **Publishing** tab now includes this guide and a nonpublishing **Test saved GitHub connection** button. You do **not** need a token to use the app's local EPG/sports dashboards; this is only for uploading *rights-approved* JSON snapshots to the public output repository.

1. Sign into GitHub as `jimmyfazz`, then open **[Generate a fine-grained token](https://github.com/settings/personal-access-tokens/new)** under Settings → Developer settings → Personal access tokens → Fine-grained tokens. Avoid a broad classic `repo` token.
2. Choose a clear name, e.g. `SportsLiveInfo Publisher`, and an expiry, e.g. **90 days**. Record the renewal date; the token will stop working after expiration or revocation.
3. Set **Resource owner = jimmyfazz**. Under **Repository access**, choose **Only select repositories**, then select **LiveSports-EPG** (and no other repository).
4. Under **Repository permissions**, select **Contents: Read and write**. Leave unnecessary permissions disabled/default; click **Generate token** and copy it directly into Home Assistant.
5. In SportsLiveInfo → **Publishing**, confirm owner `jimmyfazz`, repository `LiveSports-EPG`, branch `main`; paste the token into the masked input and click **Save GitHub settings**. Saving does not alter other provider API keys or automatically enable publishing.
6. Click **Test saved GitHub connection**. This issues only authenticated GET requests against the repository and branch; it cannot verify `Contents:write` with certainty without an actual authorised publication. Fix any 401/403/404 message and repeat.
7. Keep **Enable publishing** and **Publish automatically** OFF until there are correctly collected events, approved public redistribution rights and a reviewed feed preview. Enabling the switch is not evidence of source permission. After a permitted upload, verify the public manifest/asset checksums anonymously.

The **public data repository** is [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG); the **Home Assistant App installation/source repository** is the separate `SportsLiveInfo` repository, currently private. Publishing is outbound-only: no incoming Home Assistant access, port forwarding, TV GitHub tokens or TV uploads.

**Security:** Never put this token in chat, Issues, code, logs, screenshots or the public data repository. Saved credentials remain private to the HAOS App volume; Home Assistant backups containing `/data` must be protected. To rotate an expiring token, generate a replacement and use the same masked input to save it. Official instructions: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens.

## Keys, data and security

- API keys, the publishing token, settings and snapshots remain in `/data/sportsliveinfo.sqlite3`. Masked HTML is not encryption at rest; protect App storage and backups and rotate expiring keys.
- The default GitHub destination is owner `jimmyfazz`, repository `LiveSports-EPG`, branch `main`; both publishing switches default OFF. The fine-grained publisher token must be restricted to that public feed repository. It is not a private-source installation credential.
- The UI uses an internal listener on port 8099, trusted peer checks and CSRF. App config exposes no host ports. Use Home Assistant Ingress; do not forward a WAN port or publish the App endpoint. Existing owner remote administration remains separate.
- The database retains 300 recent job results; diagnostics must stay free of secrets. Source failures preserve last-good data. No persistent notifications are currently sent to HA Core.
- TVs must only read the eventual public feed; no GitHub write credentials, source API keys, private accounts or stream URLs belong in that feed. TMDB/OMDb and VOD artwork remain in B1G.

## Build and updates

The Dockerfile uses `python:3.12-alpine`, a floating minor-family tag rather than a digest-pinned image, and standard-library application code. It declares amd64/aarch64 support and Supervisor labels, but real architecture builds remain unverified. For a code upgrade, refresh the private local App files and follow the installed Supervisor's rebuild/update flow; preserve `/data` and verify the chosen revision. No release readiness is implied by this documentation refresh.
