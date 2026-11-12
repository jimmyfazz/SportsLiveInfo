> **SUPERSEDED AS PRIMARY DEPLOYMENT (12 November 2026):** The owner has selected **Home Assistant installed directly on an always-on personal-home mini PC with no Proxmox**. The primary plan is [HOME_ASSISTANT_BARE_METAL_PRIMARY.md](HOME_ASSISTANT_BARE_METAL_PRIMARY.md). The Proxmox and office-host options below are preserved only as fallbacks. Statements below describing Proxmox as the selected environment are historical and should not direct implementation.

# Deployment decision — Home Assistant App or Proxmox LXC

> **Superseded reference — reviewed 12 November 2026.** Preserved as an earlier proposal, not installation or current wire-format instructions. Use the master roadmap, implemented sli/1.0 contract and private local App operator guide. UK-only/optional-B1/Proxmox-primary assumptions are superseded.
> **Repository roles:** [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is PRIVATE source/installation and stays private; [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is PUBLIC daily data only. [Current status and evidence](CURRENT_STATUS.md).

**Research date:** 2026-11-12. **Status:** architecture proposal only; no installation or integration implemented.

## User requirements, superseding earlier standalone-host assumptions
- Always-on office Windows/Linux PC available; alternatively existing Proxmox host runs Home Assistant 24/7.
- SportsLiveInfo must collect sporting fixtures and verified UK broadcaster information, periodically publish a daily *rights-cleared* JSON cache outward to GitHub. No external access to the office/home NAS/PC/HAOS VM.
- B1G is a private-use Android TV application on 10 televisions, Home sports rail around 10–11 event cards. Ten TVs must **not** produce ten sets of calls to upstream sports providers.
- User wants easiest, least-cost deployment using existing always-on resources, no paid LLM/cloud/API requirement.

## Recommendation
**Develop one host-independent Python collection core with a packaged container.** Run it either:
1. **Home Assistant OS App (formerly add-on)** in the already-running HAOS VM — best ease of management, HA Settings > Apps install/config/start/logs/backup, no separate Linux VM. App is an isolated supervised container running alongside HA, *not* inside Home Assistant Core.
2. **Separate unprivileged Proxmox LXC** running Python directly under systemd — best failure isolation, independent upgrades/restarts and low overhead, no extra hardware. Docker inside LXC is unnecessary; if Docker is required on Proxmox, use a small Ubuntu VM instead of nested Docker.
3. **Existing office computer** only if Proxmox is not available or is overloaded; Windows service/task scheduler works but increases operational differences.

## Important installation-type gate
The user says 'Home Assistant via Proxmox' but **the Home Assistant installation type is not yet verified**:
- Home Assistant **OS** VM provides Supervisor and **Apps**. Local apps are built/installed from `local_apps` (older terminology `addons`). Official docs: https://www.home-assistant.io/installation ; https://contributors.home-assistant.io/apps/how-apps-work/ ; https://contributors.home-assistant.io/apps/first-app/
- Home Assistant **Container** inside Linux/Docker does **not** have Home Assistant Apps. Run SportsLiveInfo as a separate container/LXC (or integrate only for monitoring).
- Do not make the full event collector a `custom_components` integration running inside Home Assistant Core. That would entangle long-running scraping, provider retries, quotas, heavyweight XMLTV ingestion, SQLite I/O and GitHub publishing with home-automation availability. Official distinction: https://www.home-assistant.io/docs/apps-and-integrations/

## High-level operation (identical engine in either host)
1. Scheduler fetches permitted competition data/UK broadcast evidence once per provider cycle, never per-TV.
2. Quota guard & rate limit; normalize events and broadcast claims; cache SQLite / atomic JSON snapshot; preserve last-good file on failures.
3. Source-rights gate controls what **may** be posted to public GitHub. Raw third-party EPG and provider keys never go into public feed absent permission.
4. Publish via **outbound HTTPS only** with a narrowly scoped credential to a **separate proposed public feed repository**, not to private source repo. No incoming NAT, firewall port or public HA access needed.
5. Every B1G TV downloads one small common JSON snapshot over HTTPS, maintains local cache and renders cards. A 10-card rail **does not** require 10 calls to sports providers.
6. Optional HA monitoring integration reads local collector health/events via read-only socket/endpoint and exposes status to dashboard; this is a thin companion, not the engine.

## Proposed Home Assistant App design
Suggested relative tree (not present yet):

    homeassistant/
      sportsliveinfo/
        config.yaml
        Dockerfile
        run.sh
        DOCS.md
    src/sportsliveinfo/
      core/
      providers/
      matching/
      publishing/
      scheduler/
    tests/
    Dockerfile
    compose.yaml

- Home Assistant App packaging: app `config.yaml`, Dockerfile/container, settings for timezone, provider keys, cache dir, GitHub target, publish schedule and safe logging.
- Use Supervisor persistent `/data` for cache/database and `/data/options.json` for app options; keep secrets in protected local configuration and do not put them into exports/logs.
- Use single process/scheduler with lock, catch-up-after-downtime, backoff, 429 handling, daily quota counters and restart policy; no independent scheduler in HA Core.
- Provide Home Assistant App status with last-successful-collection and last-successful-publication, source health and warnings.
- Apps are available only on HAOS; on other installation types use the same core in LXC or Docker.
- Local prototype can remain in a **private repo** and be installed from `local_apps` without adding a publicly accessible HA app repository. Do not make code public merely for app installation.
- A separate HA integration is optional: sensors such as `sensor.sportsliveinfo_last_publish`, `sensor.sportsliveinfo_uk_events_today`, `sensor.sportsliveinfo_licence_gate`, binary sensor `sportsliveinfo_feed_stale` and `button.sportsliveinfo_refresh` with rate guard. Integrations should coordinate reads via `DataUpdateCoordinator`; official pattern: https://contributors.home-assistant.io/core/integrations/fetching-data/

## Proxmox dedicated LXC fallback
- An unprivileged Debian 13 or current Ubuntu LXC (exact choice dependent on Proxmox availability), Python environment, systemd unit and timer. No HAOS dependency.
- Provisional sizing **not benchmarked**: 1 vCPU, 512 MB RAM–1 GB RAM and a few GB storage are reasonable starting assumptions for modest fixture and EPG XML; verify actual resource usage. Avoid claiming a precise measured minimum.
- Local-only management. Persistent data volume, restart on failure, monitored backups and quota dashboard (optional API for HA).
- For more complicated container lifecycle, a minimal Ubuntu Docker VM can run the identical Python image with no app-package dependencies.

## Scheduling / Github publication plan
- Collect several hours ahead. Publish the **morning** snapshot sufficiently before the requested **05:00 Europe/London** B1G download; confirm a successful GitHub Pages deployment rather than assuming a commit is immediately served.
- Additional afternoon/early evening updates and more frequent event-day changes within quota to catch reschedules, tennis order-of-play and late announced boxing times. Example *starting point*: 04:15, 12:00, 17:00 and an event-triggered update when provider allowances permit.
- B1G performs a first successful read near 05:00 UK time, again during day/after wake, with stagger+jitter between TV clients and ETag/If-None-Match where supported. On no network or missing fresh revision, show last-good snapshot clearly stale.
- Include `schema_version`, `generated_at`, `valid_for_local_date`, `expires_at`, `revision`, `source_health`, `coverage_state`; B1G parses stable contract. Never expose GitHub API write token to TVs.
- Private GitHub repo is for code; separate **public** Pages feed would require permission to redistribute each included datum and is **already `jimmyfazz/LiveSports-EPG` (PUBLIC), but live publication remains unapproved and was absent at the current review**. If rights not cleared, publish only permitted fixture metadata or keep broadcaster matching inside B1 from user-authorised local EPG.
- GitHub Pages can deploy public static content on GitHub Free: https://docs.github.com/en/pages/setting-up-a-github-pages-site-with-jekyll . Watch cache/deployment propagation and avoid guarantees of instantaneous refresh.

## Failure boundaries
- HAOS reboot / update: collector app may pause. GitHub last-good feed stays accessible; B1G must show freshness status.
- Proxmox reboot: both HA VM and LXC temporarily offline, same last-good behavior.
- Provider down or quota exhausted: keep previous data, mark incomplete/stale, never publish "nothing on today" from an error.
- GitHub returns 403/429 or publishing fails: retry bounded, keep signed local pending snapshot, health red, don't turn LAN inbound on.
- No public inbound port to Proxmox, Home Assistant, office computer or NAS. All GitHub/provider traffic outbound TLS; protect GitHub fine-grained write credentials.
- EPG licensing: collector on local HA host does **not** make provider data free for internet publication.

## Decision / to validate
- [ ] Confirm HA installation type: **HAOS VM** vs **HA Container**.
- [ ] Check HA VM free RAM/CPU/disk headroom and whether EPG ingestion may contend with heating/blinds/lights automations.
- [ ] Choose Home Assistant App (ease) or separate Proxmox LXC (isolation); build both thin host wrappers from one common core, but avoid maintaining two processing engines.
- [ ] Confirm initial source licences/terms before turning on GitHub public publishing.
- [ ] Test one-to-many 10-TV B1G fixture consumption and no per-TV upstream API usage.
- [ ] Document rollback, backups, last-good cache and successful publish health.
