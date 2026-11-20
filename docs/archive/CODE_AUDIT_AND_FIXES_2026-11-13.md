# SportsLiveInfo — code, GUI and source audit with fixes (13 November 2026)

**Baseline:** `main` at `56ea1be` (v0.3.0, 88 tests), merged into `claude/sportsliveinfo-b1g-android-syyo8j`.
**Result:** v0.3.1, **118 tests pass** on Python 3.12.3 and 3.13. 30 of those are new regression tests in `tests/test_audit_fixes.py`, plus updates to existing tests.
**Method:** four parallel read-only audits, one per area: Ingress server and security; engine, storage and scheduler; providers, matching and taxonomy; feed, packaging, tests and documentation. Each finding was reproduced against the real modules before fixing. The Ingress UI was rendered with realistic fixture data in Chromium at 1280 px and 390 px. A separate web search covered further EPG sources.
**NOT RUN:** live provider calls (blocked in this sandbox), Docker build, real Home Assistant Supervisor/Ingress, B1G devices.
**Relation to the 12 Nov audit:** that audit's TF-01 to TF-32 items are strategy and architecture level. This report adds concrete code defects. Where one maps to a TF item, it is noted.
**Ownership:** sports adapters, engine and publisher are Codex-owned in the collaboration plan. They were changed at the owner's direct request with no concurrent Codex branch, so cross-review is requested before merge.

---

## 1. Defects fixed (all covered by tests)

### Ingress server and GUI (`server.py`)

**S1 (high). Unhandled exceptions dropped the connection with no response.**
- Previously the HA proxy showed a blank page or a 502.
- Fix: catch-all GET and POST handling. A failed page returns a 500 page; a failed action redirects with "Unexpected error (Type)" and records a `ui/error` job.

**S2. A non-ASCII CSRF value crashed the handler.**
- Fix: compare bytes.

**S3. The "Live today" page was frozen at collection time.**
- Previously it showed yesterday's list as "today" after midnight, and a 15:00 match as "Upcoming" at 16:30.
- Fix: live state is recomputed at view time, and a stale-day banner appears when the snapshot is not for today.

**S5. `?message=` rendered any text as an official app alert (content spoofing).**
- Fix: notices are now server-side flash tokens (`?m=`).

**S6. Weak, inconsistent GitHub owner/repository/branch validation.**
- Previously `..` was accepted.
- Fix: one `validate_github_target()` shared by save, test and publish.

**S7. A new key plus "Remove key" in one submit silently removed the key.**
- Fix: both together are rejected (the same rule applies to the token).

**S8. There was no UI for `publication_approvals`.**
- Previously publishing was impossible without editing SQLite.
- Fix:
  - a new **Publication rights register** with an attestation tick box and a change log;
  - the destination text is built from real settings and the publish state;
  - "Publish feed now" is disabled with the reasons listed.

**S9. No socket timeout.**
- Fix: `timeout = 20`, safely skipped for in-memory test connections.

**GUI-1. Every zero rendered blank.**
- This hid "API calls today", turned "0 / 1 channels" into "/ 1", and blanked guide counts.
- Fix: `e()` now renders `0` and `False`.

**GUI-2. The icon was broken outside Docker, and the route sent 200 before reading the file.**
- Fix: read first, fall back to the package icon, return 404 if missing.

**GUI-3. Labels and accessibility.**
- Several inputs had no associated label; there was no visible focus style; there was no `aria-current`.
- Fix: `for`/`id` labels, a 2 px focus outline, `aria-current` and `role=status`.

**GUI-4. Today tables misaligned, with the category shown twice.**
- Fix: one fixed-layout table per sport with competition sub-header rows; "N more" is shown when a competition exceeds 60 rows.

**GUI-5. Events page layout and labelling.**
- Before: stacked full-width filters; ambiguous categories (the Ashes and football both showed "England (men) internationals"); duplicate competition sublines; no day separation.
- Fix: labelled one-row filters, "Sport · category" labels, day header rows, and an empty-filter message.

**GUI-6. Raw ISO UTC timestamps everywhere.**
- Fix: friendly local times, e.g. "13 Nov 09:50 GMT (2 h ago)".

**GUI-7. Sources page was 16,800 px tall on a phone, with 87 forms.**
- Fix: an "Enabled sources at a glance" table (key status, last result, calls today), with sports and EPG markets in collapsible groups.

**GUI-8. Diagnostics had no per-source view.**
- Fix: per-source last result, last success, consecutive failures, calls against limit, scheduler heartbeat, empty states and status colours.

**GUI-9. Dashboard copy and labels were out of date.**
- Before: outdated "broadcaster confirmation not implemented" text, and sources listed by raw ID.
- Fix: accurate copy and human-readable source labels.

**HA-1. No health endpoint.**
- Fix: `/healthz`, wired to `watchdog:` in `config.yaml`.

### Engine and storage (`engine.py`)

**E-01. Multi-day fixture discovery never re-ran.**
- The 12 h test used `updated_at`, which every today-only run refreshes.
- Fix: a `full_discovery_at` timer that runs once per London day (at most every 20 h).

**E-02. Fixtures withdrawn by a provider lived forever.**
- Fix: removed after **two consecutive successful** refreshes of their scope omit them. This keeps `main`'s safeguard against partial free-plan responses.

**E-03. The pacing lock was held while sleeping, serialising all lanes.**
- Fix: reserve a slot under the lock, then sleep outside it.

**E-04. A corrupt gzip (`zlib.error`) escaped and stopped every later guide in the EPG lane.**
- Fix: per-guide catch-all.

**E-05. The scheduler thread died permanently on any exception.**
- Fix: per-tick error handling plus a persisted heartbeat.

**E-08. A crash in `_materialize` or auto-publish left the collector "started" forever.**
- Fix: the failure is recorded.

**E-10. Concurrent manual and automatic publish or preview could race.**
- Fix: publish/preview lock.

### Feed and publisher (`feed.py`, `engine.publish`)

**FA-01/E-07. The revision changed on every collection.**
- Health timestamps fed into it, producing about 1,100 needless commits a year and making retention cover only about 3 days.
- Fix: the revision covers the data assets plus meaningful settings (approvals, schedule, version, format), but not health.

**FA-02. Changes that only affected the manifest were never published, and a static feed's `expires_at` would lapse.**
- Fix: approvals, schedule and version are now in the revision. An unchanged revision is republished after 24 h to renew expiry, without duplicating history.

**FA-03/E-09. Uploads and deletions trusted local state.**
- A reset repo or restored backup meant missing assets, or a 422 on every publish.
- Fix: the remote tree is read. Missing referenced assets are uploaded, and only paths that exist are deleted (TF-19 related).

**FA-04. Plural `/git/refs` was used for the branch read, and a ref race gave an opaque error.**
- Fix: singular `/git/ref/heads/`; 409/422 now gives a clear "retry next run" message.

**FA-05. `omitted_unapproved_sources` listed approved sources.**
- Fix: only unapproved sources are listed.

**FA-06. A test would start failing after 21 Nov 2026 (real clock against a fixed event date).**
- Fix: the clock is pinned in that test.

**FA-07. A stale duplicate block appeared in `IMPLEMENTATION_PROGRESS.md` after the merge.**
- Fix: removed; the file now matches `main`.

**FA-08. Python ran as PID 1 without init, so stop and restart waited for SIGKILL.**
- Fix: `init: true`.

**FEED-1. A legacy snapshot without `category_id` crashed the feed build.**
- Fix: such events are classified before export.

### Providers, taxonomy, linking and guide

**D1. The standard `<!DOCTYPE tv SYSTEM "xmltv.dtd">` rejected the whole guide.**
- Fix: a prolog doctype without an internal subset is accepted. Entities, internal subsets, second doctypes and late doctypes are still rejected.

**D2. A null `teams.home` failed the whole API-Sports day.**
- Fix: null-safe; `AttributeError` is caught.

**D3. A provider "live" flag stayed LIVE forever, including on expanded future cricket days.**
- Fix: trusted only from 30 min before start to 1.5× typical duration. A finished Test no longer gets future days.

**D4. AFL events classified as `other`.**
- Fix: `sport_id` accepts the underscore form.

**D5. Women's competitions went to men's national rows.**
- Fix: they map to the women's rows. Women's World Cup, Women's Euro, Women's FA Cup and WSL/UWCL aliases were added, and "Friendlies Clubs" is excluded from national rows.

**D6. A bare rugby "Championship" decided union vs league.**
- Fix: it is now ambiguous and decides nothing.

**D7. TheSportsDB "Fighting" boxing events (including PPV) landed under MMA.**
- Fix: moved to boxing.

**D8. Missing TheSportsDB-style names.**
- Fix: added English FA Cup, English League 1/2, American MLS, English Premiership Rugby, Six Nations Women and U20 Six Nations.

**D9. False merges.**
- Previously merged: Inter with Inter Miami, Paris FC with PSG, Rangers with QPR, Ireland with Northern Ireland, Jong Ajax with Ajax, United with Man Utd.
- Fix: a subset now only matches when the extra words are generic club words (United, City, Hotspur…).

**D10. Same teams in different competitions on the same day (e.g. WSL and Premier League) were fused.**
- Fix: different competition IDs block a merge.

**D11. Duplicate IDs from the same source were not collapsed.**
- Fix: the freshest copy wins.

**D12. Broadcast-candidate false positives.**
- Previously matched: Northern Ireland v Wales, Man Utd for Man City, women's fixtures, a 4-day programme, Sky Sports News, chat shows, F1 practice for the race, TBC v TBC.
- Fix: candidates now need a "home v away" phrase surrounded only by programme words. Programmes over 9 h and news channels are excluded, and other F1 sessions are rejected.

**D13. IPTV decorations broke identity.**
- Fix: `[VIP]`, `(SD)`, `(Backup)`, `®` and `50FPS` are stripped; `+1` and region words are kept.

**D14. Family patterns misfired.**
- Fix: German "Sky Sport 1" no longer counts as NZ; TNT Sports is no longer a US network.

**Minor provider fixes:**
- TheSportsDB `strTime="TBC"` now keeps the event as `date_only`.
- "Match Postponed" now maps to `postponed`.
- The OpenF1 double space is gone.

## 2. Logo and icon

The old raster icon (globe, ball and waves) was noisy at small sizes, and the wordmark's near-white "SPORTS" was **invisible on Home Assistant's light theme**. The replacement:
- **Icon:** a navy tile with a TV guide (one row lit in the app's cyan→lime live gradient), a live-signal dot, and a classic black-and-white football. The football is generated from a real truncated icosahedron (12 pentagons, 20 hexagons), so it reads as a match ball at 32 px.
- **Logo:** a self-contained navy badge, legible on both light and dark themes.
- **Sources:** `branding/build_svg.py` writes the SVG masters, and `branding/render.js` produces `icon.png` (128×128) and `logo.png` (250×100) deterministically.

## 3. Further EPG sources (web research; nothing fetched live from this sandbox)

**Existing sources at risk:**
- **iptv-org guides (four sources):** iptv-org reportedly stopped publishing pre-built guides [1]. `fr_programmetv`, `fr_telerama`, `iptvorg_sky_uk` and `iptvorg_foxtel_au` are labelled accordingly.
- **EPG Share:** works, but some country files are stale or tiny, and UK1 is roughly 3 days [2]. Guides now report **horizon hours** (on the EPG coverage page and in stored quality data) so thin files are visible.
- **Matt Huisman:** some playlists were removed after a DMCA notice [3].

**Added as private, disabled sources:** Matt Huisman NZ (`i.mjh.nz/nz/epg.xml.gz`) and Sydney AU (`i.mjh.nz/au/Sydney/epg.xml.gz`) [3]. Both are marked "verify".

**Recommended next, in priority order (not implemented):**

| Priority | Source | Why | Integration needed |
|---|---|---|---|
| P0 | Self-hosted **iptv-org/epg grabber** [1] | Restores the four at-risk feeds; hundreds of sites; per-channel targeting | Run as a separate HA app or container on the same host. Needs a reviewed local-source exception, because only allowlisted HTTPS hosts are fetchable today |
| P0 | **jtee3d/sky_epg_grab** [4] | 7-day Sky UK guide by region (Sky/TNT/Premier) | Same local-source exception |
| P1 | XMLTV project grabbers `tv_grab_uk_freeview`, `tv_grab_fr`, `tv_grab_pt_vodafone`, `tv_grab_dtv_la` [5] | UK, FR, PT and Latin America | Self-host |
| P1 | globetvapp/epg [6] | FR, AU, Argentina and other per-country files, refreshed daily | Inspect file names, then add |
| P1 | daoudeddy/xmltv-epg (beIN EN/AR) [7] | beIN MENA gap | GitHub release asset; the allowlist must cover GitHub's release-asset redirect host |
| P1 | weareblahs/epg (Astro, unifi) [8] | Malaysia / Astro lineup | Private source |
| P1 | TVmaze schedule API [9] | Episode titles and numbers for matched programmes; enrichment only | New JSON adapter |
| P1 | Schedules Direct [10] | Best US/Canada (about 21 days); paid, personal use | Owner decision (paid) |
| P2 | Rakuten UK EPG, sjurtf/xmltv (Norway), IceTV / xmlepg.net (AU), WebGrab+Plus | Niche gaps | As needed |
| — | zap2xml, JioTV generators | Unofficial or account-bound | Reject |

No suitable source was found for Now TV Hong Kong, SSC/Shahid or Sky NZ beyond the existing entries.

## 4. Open items (prioritised; not fixed here)

1. **E-06 / TF-14 (P1): memory and lock contention.** Whole-guide JSON blobs are parsed while holding the store lock (about 5.5 s and 580 MB for a 300k-programme guide), and `_materialize` loads every guide on every run. Move EPG into an indexed `programmes` table, parse outside the lock, and load only a ±1 h window for linking.
2. **Self-hosted guide support (P0 for EPG growth):** design a safe local-source exception (fixed HA add-on hostname, HTTP on the internal network, no user-typed URLs) so the iptv-org and Sky grabbers can feed the compiler.
3. **S4 (P2):** Test EPG, preview and publish still run on the request thread. Move them to background jobs with progress shown in Diagnostics.
4. **E-11 (P3):** a scheduled slot that hits a running collection is skipped. Add a "pending" flag. Document that the BST start hour (01:xx) never runs.
5. **E-12 (P3):** the API-Sports Test button bypasses pagination handling and uses the collection budget. Route it through `_request` and give tests a separate small budget.
6. **E-13 (P3):** `configure()` does not type-check nested values (`options`, `github.enabled`).
7. **Packaging (P2):**
   - pin the base image by digest and adopt `build.yaml` / `BUILD_FROM`;
   - remove the unused `run.sh`;
   - add `backup_exclude` for `/data/feed-preview`;
   - add CI steps for `docker build` on amd64/aarch64 and a secret scan.
8. **Feed (P2):**
   - verify anonymous Pages/raw serving after each commit (TF-19);
   - use URI-form schema `$id`s;
   - validate with a real JSON-Schema validator in CI;
   - describe the `approved_v1` broadcast rule in the events schema.
9. **Taxonomy (P2):** keep extending aliases from real provider payloads once sources are live, especially TheSportsDB league names and women's and youth competitions.

## 5. Verification receipts

```sh
python3 -m compileall -q sportsliveinfo/src tools branding         # OK
PYTHONPATH=sportsliveinfo/src python3.12 -m unittest discover -s tests   # Ran 118 tests — OK
PYTHONPATH=sportsliveinfo/src python3.13 -m unittest discover -s tests   # Ran 118 tests — OK
```

**GUI checks (Chromium, 1280 px and 390 px, all 8 pages):**
- no horizontal overflow, no broken images, no unlabeled inputs;
- no saved secret in any page;
- focus outline: solid 2 px.

## Sources

1. [tohenk/iptv-org-epg fork note](https://github.com/tohenk/iptv-org-epg) · [iptv-org/epg](https://github.com/iptv-org/epg)
2. [free-codecs EPG URL guide](https://free-codecs.com/guides/free-epg-urls-for-iptv-tv-guide-links-that-still-work.htm) · [VideoHelp UK 7-day EPG thread](https://forum.videohelp.com/threads/410986-UK-7-Day-EPG)
3. [NextPVR forum (i.mjh.nz regions)](https://forums.nextpvr.com/showthread.php?tid=66570)
4. [jtee3d/sky_epg_grab](https://gh.hhj520.top/jtee3d/sky_epg_grab)
5. [xmltv-grabbers package](https://mankier.com/package/xmltv-grabbers) · [XMLTV project](https://github-redirect.dependabot.com/XMLTV/xmltv)
6. [globetvapp/epg](https://github.com/globetvapp/epg)
7. [daoudeddy/xmltv-epg](https://awesome.ecosyste.ms/projects/github.com%2Fdaoudeddy%2Fxmltv-epg)
8. [weareblahs/epg](https://awesome.ecosyste.ms/projects/github.com%2Fweareblahs%2Fepg)
9. [TVmaze API](https://www.tvmaze.com/api)
10. [Schedules Direct (MythTV wiki)](https://www.mythtv.org/wiki/TMS)
