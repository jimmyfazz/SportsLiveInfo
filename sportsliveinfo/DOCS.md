# SportsLiveInfo — installation and use

## Install from the Home Assistant Apps store

1. This GitHub repository **must be public** for Home Assistant to fetch it as an external app repository. Do not change its visibility until you review the existing private documentation and are ready to publish the code.
2. On **Home Assistant OS**, go to **Settings → Apps → Install app → ⋮ → Repositories**, add `https://github.com/jimmyfazz/SportsLiveInfo`, then refresh the store.
3. Select **SportsLiveInfo**, install it, enable **Start on boot**, and select **Start** then **Open web UI**. Build-on-device is used; an external GHCR image is not necessary.
4. Complete the Ingress wizard: choose providers, enter free API keys when needed, enable lawful guide sources and set refresh times. Each Save keeps keys for unrelated providers.
5. Return to Overview, select **Refresh both engines now**, and inspect **Diagnostics** for detailed source results. The local SQLite database is stored in `/data` and survives app restart or upgrade.

**This is an App, not a HACS custom integration.** Do not use Settings → Marketplace → custom HACS repository for installation; use the **Apps** repository manager. Ingress requires no router port-forwarding and this app config exposes **no host ports**.

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

## Keys, data and security

- API-Sports, football-data.org and GitHub token values are stored in the app's private `/data/sportsliveinfo.sqlite3` file; masked in the web UI. Home Assistant backup files containing `/data` must be treated as sensitive.
- No keys or real IPTV provider account details are published, no TV needs GitHub write access, and no Home Assistant router port is opened.
- Native ingress proxy only: UI accepts internal Home Assistant Ingress requests from `172.30.32.2` and localhost (development only), and POST requests require a persisted CSRF token.
- The GitHub token should be fine-grained and limited to the separate approved feed repository with Contents read/write. The private source repo remains a different repository.
- The app stores up to 300 recent redacted job results. If a guide is malformed/oversized, previous last-good data remains intact.
- This release does not yet send persistent notifications into Home Assistant Core, to avoid broad access permissions until a least-privilege design is reviewed.

## Build and platform

This app supports **amd64 and aarch64** Home Assistant OS installations. It uses a pinned Python 3.12 minor-family Alpine base and Python standard library only. HAOS Supervisor builds the container from the app's Dockerfile at install time. If your Home Assistant installation is Container/Core rather than HAOS/Supervised, it does not have the Apps store and this installation method is not supported.

Official documentation: https://contributors.home-assistant.io/apps/guides/repository/ and https://contributors.home-assistant.io/apps/reference/configuration/.
