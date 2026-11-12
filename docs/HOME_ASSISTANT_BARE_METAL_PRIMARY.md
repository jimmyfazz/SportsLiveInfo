# Primary deployment: dedicated home mini PC running Home Assistant OS

**Decision recorded 12 November 2026.** The owner has an always-on **personal-home mini PC with Home Assistant installed directly on the hardware**, ample disk and RAM. **No Proxmox on this machine.** This is the **preferred SportsLiveInfo host**. Proxmox LXC/VM, Synology and the office PC are fallback platforms only.

**Implementation status:** architecture agreed; SportsLiveInfo collector, Home Assistant App and GitHub publishing are not yet built or installed. Exact Home Assistant installation type has not been verified. Direct installation on a mini PC strongly suggests HAOS, but do not assume: confirm in **Settings > System > Repairs > menu > System information** or **Settings > About** depending on HA version, looking for the installation type, or check whether **Settings > Apps** is present.

## 1. Installation-type gate

- **Home Assistant OS (HAOS)**: supports managed **Apps** (previously add-ons). This is the target: a locally installed, Supervisor-managed app with its own Python process/container and persistent `/data`.
- **Home Assistant Container**: does *not* support Apps. If this is the actual installation, don't attempt the HAOS App package; choose a companion container on the same underlying Linux system, or a separate host. Do not modify or replace the owner's Home Assistant installation without approval.
- Official: https://www.home-assistant.io/docs/apps-and-integrations/ ; https://www.home-assistant.io/installation ; https://contributors.home-assistant.io/apps/how-apps-work/

## 2. Selected topology

    PERMITTED SPORTS APIs / OFFICIAL CALENDARS / AUTHORISED EPG
                         |
                  outbound HTTPS
                         v
       PERSONAL HOME MINI PC: HOME ASSISTANT OS
       +-----------------------------------------+
       | HA Core: home automations (independent) |
       | SportsLiveInfo HA App (separate process)|
       |   scheduler + provider quota budget     |
       |   competition/UK TV matching            |
       |   SQLite + last-good JSON snapshots     |
       |   provenance, licence/publication gate  |
       +-----------------------------------------+
                         |
          outbound HTTPS only (no port forward)
                         v
       GITHUB (PROPOSED SEPARATE PUBLIC DATA FEED)
       only licensed, non-secret, small versioned JSON
                         |
                      HTTPS GET
                         v
       B1G ON 10 TVs — same cached data, ~10–11 cards
       (no TV ever calls sporting provider directly)

The project code remains in PRIVATE jimmyfazz/SportsLiveInfo. A separate public static JSON feed repo is **not yet created** and requires **source licensing clearance**; private/personal use on ten TVs does not itself authorise public redistribution. For source-restricted TV EPG data, use B1's own permitted local EPG for broadcaster matching rather than putting those records on public GitHub.

## 3. Home Assistant App packaging and installation (planned)

Proposed tree:

    homeassistant/apps/sportsliveinfo/
      config.yaml
      Dockerfile
      run.sh
      DOCS.md
      icon.png                   # only if authored/allowed
    src/sportsliveinfo/
      collector/
      providers/
      matching/
      cache/
      publisher/
    tests/

- An App is a folder containing `config.yaml` and Dockerfile or an approved image reference. Home Assistant Supervisor builds/runs it independently of Core. Official: https://contributors.home-assistant.io/apps/how-apps-work/
- For a **private, owner-only application**, install from the HAOS `local_apps` folder rather than making the code repository publicly accessible. With Samba share: add under `local_apps/sportsliveinfo/`; with Terminal & SSH: path `/local_apps/sportsliveinfo`. Refresh the App Store and find it under Local apps. https://contributors.home-assistant.io/apps/first-app/ ; https://www.home-assistant.io/common-tasks/os
- The user-facing path is **Settings > Apps > Install app** (current Home Assistant terminology). No separate VM or manual Docker engine install.
- Preserve state in App's `/data` volume (SQLite, last-good snapshots, quota counters, source health). Never store database solely inside immutable container image. Ensure backups include the App's persistent data/config and store backup off-device.
- App settings: sports/competitions, daily/weekly schedule, GB timezone, optional token/credentials, data retention, publish target and health indicators. Mask tokens in logs; avoid logging API responses indiscriminately.
- App process should run with the least permissions/privileges needed, no host network or inbound port unless explicitly necessary, with restricted persistent paths. GitHub and provider HTTPS requests only.
- Do not implement the main collector inside `custom_components` or home-automation YAML. A small *optional* HA integration/sensor to report collector health may be developed separately.

## 4. Resource and automation protection

Collector is light relative to a typical mini PC, but memory and CPU limits **must be benchmarked on the actual hardware**; avoid a promise that it has zero impact. Schedule CPU/IO-bound work conservatively; streaming EPG files may be large. Home Assistant's lighting, heating, blinds and other home automations must take precedence.

- Single scheduler; one active collection per source; no overlapping jobs after reboot.
- Network request timeout, retries/backoff, daily quotas, rate limits, cancellation and circuit breaker.
- SQLite WAL or simple single-writer mode with safe snapshots and integrity check.
- Catch-up run after prolonged outage; no full repeated batch that burns a daily allowance.
- Preserve last successful `today` and 7-day snapshot, and expose `generated_at`, `expires_at` and source completeness.
- On an HAOS update/restart, remain recoverable and republish only after successful validation.
- Avoid credentials in exported JSON, app logs, source control or B1 clients.

## 5. Proposed schedule and ten-TV delivery

**Example starting configuration**, subject to source quotas, venue changes and actual measured runtimes:

- Fetch rolling fixtures/official calendars in advance (e.g. twice daily, not on Home-screen requests).
- Early collection at **04:00 Europe/London**, validation/rights gate then outbound JSON push, aiming to complete **before 05:00**.
- B1G TVs fetch the latest successful snapshot at launch and around **05:00 local time** when awake, with random per-client staggering and conditional GET/ETag; no need to wake a powered-down TV just to fetch.
- Subsequent collector updates around midday and late afternoon; optional narrowly scoped nearer-event change checks within free quotas. B1G checks for a newer revision on wake or periodically while in use, without touching upstream providers.
- **5 a.m. alone is insufficient** for postponements, rescheduled kick-offs, tennis order of play, boxing walkout changes or broadcaster moves.
- Source budget counts **only central collector requests**. Ten televisions downloading eleven cards each adds **zero provider calls**, though it adds low-volume reads to GitHub Pages/CDN.
- Default publish at most one changed snapshot per collection, using hash/revision; if GitHub Pages deployment propagation lags, let B1G use last-good cached data and validate timestamp/revision rather than rely on upload being instantly visible.

## 6. Outbound-only security

No WAN port forwarding, reverse proxy, Tailscale public sharing, inbound Home Assistant integration, exposed API server or home public IP is needed.

- API keys are kept in a protected HA App configuration/secret storage (and never returned to clients).
- GitHub credential: fine-grained token or preferably GitHub App installation credential with minimum write permissions **only to the eventual separate public feed repo**; scope down, rotate and monitor.
- Public feed is intentionally **world-readable**, regardless of private use of B1G; licence gate must block any source that doesn't allow public output.
- Use TLS and normal GitHub outbound port 443, handle GitHub 401/403/429 gracefully and retain local last-good payload.
- Add publication log of snapshot hash, source rights, final URL and GitHub commit/deploy status.

## 7. Acceptance criteria before claiming completion

- [ ] Confirm mini PC runs Home Assistant OS and supports **Settings > Apps**.
- [ ] Install local SportsLiveInfo App with no change to HA Core/automations.
- [ ] Test restart, backup/restore, power failure, and low-RAM/low-disk guard.
- [ ] Collect at least one actual allowed football/F1 fixture and one authorised EPG example, distinguish scheduled/live/highlights and unknown broadcast.
- [ ] Demonstrate quota counters do not change when 10 simulated clients request the cached feed concurrently.
- [ ] Prove no inbound ports and no provider/GitHub secrets in logs/public data.
- [ ] Verify source licensing before any public JSON publish.
- [ ] Test GitHub upload, URL retrieval, update propagation, 05:00 UK-time behaviour including BST switch, bad fetch and last-good fallback.
- [ ] B1G Android integration tests: 10–11 relevant unique cards, correct names/times/broadcaster, refresh on launch, local cache, hidden-channel/account filters.

## Engineering guidance and fallback

Build **one portable Python engine**, with a very thin Home Assistant App wrapper. That preserves a Docker/Ubuntu/Proxmox fallback if the home installation changes. Do not spend development time on Proxmox or Synology deployment until HAOS compatibility is assessed.

Further references: [Home Assistant App development](https://contributors.home-assistant.io/apps/first-app/), [Home Assistant Apps versus integrations](https://www.home-assistant.io/docs/apps-and-integrations/), [Home Assistant OS local apps folder](https://www.home-assistant.io/common-tasks/os).
