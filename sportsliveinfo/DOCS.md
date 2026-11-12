# SportsLiveInfo — installation and use

## Install on Home Assistant OS (private-source testing)

The **SportsLiveInfo application source is private**. Entering its GitHub URL into Home Assistant's standard Apps repository installer does not establish that Supervisor can authenticate or clone it. The separate public `LiveSports-EPG` repository is a *data feed destination*, not an installable App.

**Recommended private test route:** On a Mac authenticated to the private source, download the development branch ZIP, extract the inner `sportsliveinfo` app folder and copy it into Home Assistant OS's `local_apps/sportsliveinfo` folder using the Samba share (Finder → Cmd+K → `smb://homeassistant.local`) or authorised Terminal & SSH. In **Settings → Apps → Install app → Local apps**, install **SportsLiveInfo**, enable Start on boot and Open web UI. This keeps the source repository and credentials private.

See **[Complete private HAOS installation and update checklist](../docs/PRIVATE_HAOS_TEST_INSTALL.md)** for detailed folder-layout checks, safe rebuilding and troubleshooting. The full local slug is `local_sportsliveinfo`. Do not expose port 8099 or forward Home Assistant through the router.

If the project later has a **genuinely accessible public** installation repository or image, use **Settings → Apps → Install app → ⋮ → Repositories** with its Git URL; do **not** make the private development source public without a separate decision. This is an App, not a HACS/Marketplace integration.

After the app starts, select sources and save optional API keys, configure refresh times, finish setup and manually refresh; review Diagnostics. Private SQLite state is held in the app's persistent `/data` volume and should survive a normal restart. Actual HAOS install and backup/restore are still unverified.

## What's new in development release v0.2.0

- **Independent Sports events page:** shows up to 100 locally collected fixture/race/session records with Europe/London start times. Broadcasts are explicitly unverified unless independently confirmed; the page does not claim any IPTV stream is playable.
- **International EPG coverage dashboard:** private per-source GB/FR channel counts, generic programme entries, 24/72/168-hour complete coverage and the worst programme gaps. Channel identity suggestions are deliberately conservative; B1G still makes final per-account stream matches.
- **No-key OpenLigaDB Bundesliga source:** opt-in community football fixture coverage, conservatively budgeted at four requests/day; source reuse/public redistribution rights must be assessed independently.
- **Test connection buttons:** one actual quota-accounted call for each selected sports API; EPG test downloads and parses the full guide, but does not change stored source data.
- **Safer collection:** a source with stale/no current EPG cannot wipe a good guide; a malformed/partial API-Sports page raises an error rather than returning a false empty day. In-day API-Sports refreshes reuse the prior seven-day cache instead of fetching seven days each time. Duplicate manual refreshes no longer queue silently. Existing user keys and source choices survive this version upgrade.
- **Automated validation:** 19 offline/local tests, including real HTTP Ingress response/CSRF behaviour, source errors, conservative broadcaster matching, coverage windows and quotas. These are NOT equivalent to actual Home Assistant OS installation, provider quotas or real-device TV acceptance.

**Scope still outstanding:** universal full international guide source catalogue/licensing, actual B1G shared feed integration and stream mapping, official per-event broadcast verification, additional specialist sport sources, Home Assistant persistent notifications and legally approved static public publishing. These remain explicitly unimplemented. No public access to Home Assistant is needed or enabled.

## Currently working features

- Private, Ingress-only dashboard and one-time setup completion; restart-persistent settings and key entry.
- UTC request budgets, provider health and last-good source snapshots in SQLite.
- Sports: no-key Jolpica Formula 1 calendar (race weekends/sessions); football-data.org matches (optional account key), API-Sports fixtures (optional account key).
- International EPG: explicit opt-in to farleyflex UK sports, and France programme-tv.net/Télérama/XMLTV France feeds. Bounded decompression/XML validation; stored privately and grouped by source.
- Daily Europe/London refresh times; manual refresh; cached summaries and diagnostics.
- Outbound GitHub writer implementation for event records; disabled until permission to publish source-derived data is independently recorded. **The current GUI deliberately does not issue blanket copyright permission.**
- All TVs remain read-only consumers **after** an actual rights-cleared public feed and B1G reader are deployed; neither currently exists.

## Important limitations in v0.2.0

This is an **experimental development version**, not an assertion of complete EPG accuracy. It does not yet contain the complete international broadcaster identity/crosswalk, quality-based EPG correction, all sporting source adapters, independently verified TV broadcast matching, 10-TV B1G consumer, official rights approvals, HA persistent notifications or a publicly deployed static JSON feed. It must not be treated as a complete replacement for B1G's existing provider EPG. EPG entries are source-specific, not conclusively mapped to an IPTV stream. Sporting event records omit TV channels unless independently verified, avoiding guessed playback links.

Guide source terms have **not** been verified for external redistribution; original content remains private in `/data`. Do not enable public GitHub publishing until licence/permission review passes. Some data-provider free tiers may restrict caching or republishing.

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

- API-Sports, football-data.org and GitHub token values are stored in the app's private `/data/sportsliveinfo.sqlite3` file; masked in the web UI. Home Assistant backup files containing `/data` must be treated as sensitive.
- No keys or real IPTV provider account details are published, no TV needs GitHub write access, and no Home Assistant router port is opened.
- Native ingress proxy only: UI accepts internal Home Assistant Ingress requests from `172.30.32.2` and localhost (development only), and POST requests require a persisted CSRF token.
- The confirmed separate **public data feed** repository is [jimmyfazz/LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG). The Publishing screen defaults to owner `jimmyfazz`, repository `LiveSports-EPG`, branch `main`. Its GitHub token must be fine-grained and restricted to **this feed repository only** with Contents read/write. Publishing and auto-publishing are OFF by default and cannot proceed without approved source rights. The **private code/App** repository `jimmyfazz/SportsLiveInfo` is different; only that source repo (when made public or distributed through a separate approved public App repository) can be installed in the Home Assistant Apps store. Adding `LiveSports-EPG` as a Home Assistant Apps repository will not install the application.
- The app stores up to 300 recent redacted job results. If a guide is malformed/oversized, previous last-good data remains intact.
- This release does not yet send persistent notifications into Home Assistant Core, to avoid broad access permissions until a least-privilege design is reviewed.

## Build and platform

This app supports **amd64 and aarch64** Home Assistant OS installations. It uses a pinned Python 3.12 minor-family Alpine base and Python standard library only. HAOS Supervisor builds the container from the app's Dockerfile at install time. If your Home Assistant installation is Container/Core rather than HAOS/Supervised, it does not have the Apps store and this installation method is not supported.

Official documentation: https://contributors.home-assistant.io/apps/guides/repository/ and https://contributors.home-assistant.io/apps/reference/configuration/.
