# Rights record: what each source and data kind may be published as

**Recorded 20 November 2026 · documentation only (branch `docs/rights-record-and-status`, from `origin/main` 8da6e83).**

This page records what the repository already says about each source and data kind, and marks every gap. **It grants no permission.** A row says "NOT RECORDED" unless the repository itself records an approval. Read it with [CURRENT_STATUS.md](CURRENT_STATUS.md), [SOURCE_REGISTRY.md](SOURCE_REGISTRY.md), [LICENSING_AND_HOSTING.md](LICENSING_AND_HOSTING.md) and [FEED_CONTRACTS_AND_PUBLICATION.md](FEED_CONTRACTS_AND_PUBLICATION.md) §5 and §6.1.

> **Provider terms could not be read from the cloud session.** The terms pages listed below were not available from this session. Every "terms" entry is only the URL the repository already holds. What the terms say is **unknown** until the owner reads them (checklist at the end).

## Legend

- **Public feed**: world-readable `LiveSports-EPG` (`sli/1.x`). Events reach it only from sources in `publication_approvals`.
- **Private feed**: `LiveSports-EPG-private`, the owner's own TVs only (personal use).
- **Local only**: the Home Assistant App database and Ingress pages. Never uploaded.
- **Not published**: no code path puts the data in any feed.
- **Recorded permission**: `NOT RECORDED` means no supplier permission, and no approval in this repository. "Owner decision" means a design decision recorded in the repository; it is not a supplier licence.
- **Kill-switch**: the Home Assistant Ingress control that stops the data. Tabs are named as on the Ingress page.

## Gate that already exists in code

- `publication_approvals` is empty by default (`storage` defaults). An event reaches the public feed only when its primary source and every fused contributor are approved (contract §5). Since 0.3.23 the public feed is built from approved-source records only (audit C1).
- The Publishing tab's approval form requires an attestation tick ("Confirm you have reviewed each selected source's redistribution terms"). That tick is an attestation by the person saving it. It is **not** a licence record. The approval history is kept on the Home Assistant App (`approval_log`), **not in this repository**. The owner must check it on the App.
- "Enable publishing" and "Publish automatically" both default OFF (Publishing tab).

---

## 1. Fixtures and event facts (sports adapters)

Fixtures are collected for the private feed for personal use. They reach the public feed only when approved.

| Source | What we publish | Publication channel | Recorded permission | Terms URL (in repo) | Date checked | Owner action needed | Kill-switch location |
|---|---|---|---|---|---|---|---|
| API-Sports (ten products: football, rugby, basketball, ice hockey, NFL, baseball, handball, volleyball, AFL, MMA) | Fixture rows (title, participants, start, status, competition, venue) | Private feed always; public feed only if `api_sports` approved. Approval in repo: **none** | NOT RECORDED | https://api-sports.io/ (homepage only; no terms page in repo) | Repo text 20 Nov 2026; terms NOT READ | Read terms: display, caching, redistribution of data and media. Decide whether public fixtures are allowed. Confirm `approval_log` on the App. | Sources & API keys: untick Enabled per product, or remove saved key. Publishing: approvals. |
| football-data.org | Fixture rows (PL, CL, Championship, top European leagues) | Private feed always; public only if `football_data` approved | NOT RECORDED | https://www.football-data.org/coverage ; https://www.football-data.org/pricing | Repo text 20 Nov 2026; terms NOT READ | Read terms (display, caching, redistribution). Schedules are delayed on the free plan (repo note). | Sources & API keys: untick Enabled. Publishing: approvals. |
| TheSportsDB (free public key `123`) | Multi-sport fixture rows (eventsday, league week) | Private feed always; public only if `thesportsdb` approved | NOT RECORDED | https://api.thesportsdb.com/docs_terms_of_use.php | Repo text 20 Nov 2026; terms NOT READ | Repo note: the free API is development-oriented; app-store publication requires a paid subscriber; third-party content and image rights apply separately. Decide before any public use. | Sources & API keys: untick Enabled. Publishing: approvals. |
| OpenLigaDB | Bundesliga and other German football rows | Private feed always; public only if `openligadb` approved | NOT RECORDED. Licence stated in code: ODbL 1.0 (attribution text only) | None in repo | Repo text 20 Nov 2026 | Confirm ODbL attribution and share-alike duties if public. | Sources & API keys: untick Enabled. Publishing: approvals. |
| Jolpica-F1 (Ergast-compatible) | F1 calendar, sessions, results rows | Private feed always; public only if `jolpica` approved | NOT RECORDED. Licence in repo: CC BY-NC-SA 4.0 (non-commercial, share-alike) | https://github.com/jolpica/jolpica-f1/blob/main/TERMS.md | Repo text 20 Nov 2026; terms NOT READ | **Owner decision needed.** A public feed republishes this data. The repo says "private prototype only pending downstream licence" (SOURCE_REGISTRY). | Sources & API keys: untick Enabled. Publishing: approvals. |
| OpenF1 | F1 sessions | Private feed; public only if `openf1` approved | NOT RECORDED. Attribution text says "OpenF1 terms" | https://openf1.org/ (homepage only) | Repo text 20 Nov 2026; terms NOT READ | Read live-access terms. SOURCE_REGISTRY marks it "CANDIDATE for later". | Sources & API keys: untick Enabled. |
| CricketData.org (CricAPI) | Cricket matches | Private feed; public only if `cricketdata` approved | NOT RECORDED | https://cricketdata.org/pricing/ | Repo text 20 Nov 2026; terms NOT READ | Read terms; repo says some data is delayed and redistribution is unverified. | Sources & API keys: untick Enabled, or remove key. |
| Tennis API (RapidAPI) | ATP/WTA events | Private feed; public only if `tennis_api` approved | NOT RECORDED | https://docs.tennis-api.com/getting-started | Repo text 20 Nov 2026; terms NOT READ | Read terms (repo: redistribution to check). | Sources & API keys: untick Enabled, or remove key. |
| British Horseracing Authority (ICS feed) | Racing fixtures | Private feed; public only if `bha_racing` approved | NOT RECORDED | None in repo (endpoint `crate.horseracing.software` in code) | Repo text 20 Nov 2026 | Find and read the feed's terms. | Sources & API keys: untick Enabled. |
| Open Boxing (bouts JSON) | Boxing bouts | Private feed; public only if `openboxing` approved | NOT RECORDED | None in repo (endpoint `openboxing.org` in code) | Repo text 20 Nov 2026 | Find and read terms. | Sources & API keys: untick Enabled. |
| PandaScore | Esports matches | Private feed; public only if `pandascore` approved | NOT RECORDED | None in repo (endpoint `api.pandascore.co` in code) | Repo text 20 Nov 2026 | Find and read terms. | Sources & API keys: untick Enabled, or remove key. |

Not implemented, so not published, and no row is needed here: SportsAPI, SportAPI.ai, Boxerbook (repo: "personal/non-commercial/testing; commercial app needs paid agreement"), BoxingAPI. They are research candidates in [SOURCE_REGISTRY.md](SOURCE_REGISTRY.md).

---

## 2. Live status

| Source | What we publish | Publication channel | Recorded permission | Terms URL (in repo) | Date checked | Owner action needed | Kill-switch location |
|---|---|---|---|---|---|---|---|
| API-Sports live boards (`fixtures?live=all`, `games?live=all`; not MMA) | Status and `status_observed_at` per event, and the `live` asset (ids, statuses and times only; no scores, per `feed.py`) | Public feed as `live` asset when the API-Sports events are published; private feed | NOT RECORDED. The live lane reads API-Sports under the same unrecorded terms as section 1 | https://api-sports.io/ (homepage only) | Repo text 20 Nov 2026; terms NOT READ | Same as API-Sports fixtures. The lane uses at most 40 calls a day per product (contract §2). | Scheduler tab: **Live status** toggle (config `live_status`). Sources & API keys: remove the API-Sports key. |

---

## 3. Broadcast links (channel for an event)

| Source | What we publish | Publication channel | Recorded permission | Terms URL (in repo) | Date checked | Owner action needed | Kill-switch location |
|---|---|---|---|---|---|---|---|
| Event fixtures from approved sources, matched to EPG guide listings (`broadcast_links`) | Only SportsLiveInfo canonical channel ids, coverage, confidence, status `guide_listed_unverified` (D8). Public feed: **no** guide channel names, programme titles or times. | Public feed (`sli/1.3`+, for events from approved sources only). Private feed additionally carries guide channel names and times. | **Owner decision D8** (13 Nov 2026, [FEED_CONTRACTS_AND_PUBLICATION.md §6.1](FEED_CONTRACTS_AND_PUBLICATION.md#61-owner-decision-d8-approved-13-november-2026-guide-listed-channel-links)). This is the owner's design approval, **not** a licence from the guide providers | None in repo for the guide sources (see section 4) | Repo text 20 Nov 2026 | Confirm D8 still stands given the guide-source terms in section 4. Note: [FEED_CONTRACT_SLI_V1.md](FEED_CONTRACT_SLI_V1.md) §3 says `broadcast_candidates: not_published` in the general rights line; the code publishes `channel_links_published_unverified` (D8). See section 6. | Publishing tab: approvals (no approved source means no public links). Private feed toggle on Publishing. |

---

## 4. EPG guide listings (programme rows)

| Source | What we publish | Publication channel | Recorded permission | Terms URL (in repo) | Date checked | Owner action needed | Kill-switch location |
|---|---|---|---|---|---|---|---|
| EPG programme rows (`providers.EPG`, 27 candidate guides across about 15 markets, all disabled by default) | **Programme text: not published.** Manifest says `epg_programmes: not_published`. Guide-listed events (`origin: guide_listing`) are built from programme text. | Public: **not published**. Private feed: guide-listed events (personal use). | NOT RECORDED. The repo's own notes: EPGTalk is "personal use only, no republishing without written permission" (FEED_CONTRACTS §6.1). Other guides are "rights unverified" (SOURCE_REGISTRY) | farleyflex: https://github.com/farleyflex/epg-guide (repo states GPLv3 code, not a licence for programme data) · Freeview-EPG (dp247): https://github.com/dp247/Freeview-EPG (personal-use reference) · Matt Huisman i.mjh.nz: data URL only, no terms in repo · EPG Share, EPGTalk, iptv-epg.org, XMLTV France: **none in repo** | Repo text 20 Nov 2026; terms NOT READ | Owner to decide the private-feed use for each guide. No public programme text without written permission. | EPG sources on Sources & API keys: each guide is off until ticked. Private feed toggle on Publishing. |

---

## 5. Scores

| Source | What we publish | Publication channel | Recorded permission | Terms URL (in repo) | Date checked | Owner action needed | Kill-switch location |
|---|---|---|---|---|---|---|---|
| All sports sources | **Not yet published.** The published event schema has no score field (`feed.EVENT_FIELDS`), and the live asset carries no scores (`feed.py`). | Not published | Not applicable | Not applicable | 20 Nov 2026 (code check) | Before any score is added, record the source's display and redistribution terms in this file, and add a row here. | Not applicable (no code path). |

---

## 6. Team crest references

| Source | What we publish | Publication channel | Recorded permission | Terms URL (in repo) | Date checked | Owner action needed | Kill-switch location |
|---|---|---|---|---|---|---|---|
| TheSportsDB (crests, used by B1G today) | **Not yet published by SportsLiveInfo.** No crest or badge field exists in the feed. B1G caches crests on each device (SOURCE_REGISTRY, B1G table). | Not published | NOT RECORDED. Repo says "do not redistribute artwork" | https://api.thesportsdb.com/docs_terms_of_use.php | Repo text 20 Nov 2026; terms NOT READ | Read artwork terms before any crest reference is published. | Not applicable in SportsLiveInfo. |

---

## 7. Standings

| Source | What we publish | Publication channel | Recorded permission | Terms URL (in repo) | Date checked | Owner action needed | Kill-switch location |
|---|---|---|---|---|---|---|---|
| football-data.org (standings, 9 competitions) | League tables as the optional `standings:<competition_id>` assets (`sli.standings/1`): positions, team names, played/won/drawn/lost, goals, points, form. Contract §4.6. | Public feed and private feed, on by default (config `publish_standings`) | **Owner statement, 20 Nov 2026: rights are permitted for this app's use** (instruction to the implementing agent; not a supplier licence and not a written terms record). Terms themselves NOT READ | https://www.football-data.org/coverage and https://www.football-data.org/pricing | Code check 20 Nov 2026; terms NOT READ | Read and record the display and redistribution terms (checklist item 3) and confirm the attribution wording the feed carries: "Football data provided by the Football-Data.org API". | Ingress → Scheduler → League tables (**Publish league tables**), or config `publish_standings` false. The next feed has no standings assets, capability or `rights.standings`. |
| API-Sports standings | The same asset, only for a competition football-data.org could not supply completely | Same as above, only when `standings_api_sports` is true (**off by default**) | NOT RECORDED. Same unrecorded API-Sports terms as section 1. The owner statement above covers this app's use, but the API-Sports switch stays off until the owner turns it on | https://api-sports.io/ (homepage only) | Code check 20 Nov 2026; terms NOT READ | Read the API-Sports terms first (checklist item 1). | Ingress → Scheduler → League tables (**Also use API-Sports**), or config `standings_api_sports` false. |
| TheSportsDB, ESPN, Pulselive, Highlightly (B1G on-device standings) | **Never published by SportsLiveInfo.** B1G reads these on the device today; the goal is to replace them with the feed's standings. | Not published | NOT RECORDED | https://api.thesportsdb.com/docs_terms_of_use.php | Repo text 20 Nov 2026; terms NOT READ | None for SportsLiveInfo. | Not applicable. |

---

## 8. Channel identity metadata (published today)

Not on the list in the brief, but it is published now, so it belongs here.

| Source | What we publish | Publication channel | Recorded permission | Terms URL (in repo) | Date checked | Owner action needed | Kill-switch location |
|---|---|---|---|---|---|---|---|
| Channel dictionary (iptv-org database) and `guide_map` (what each guide channel is) | Canonical channel ids, aliases and `guide_map` (`sli.guide-map/1`). Published once any sport is approved (audit O4, not yet fixed). | Public feed (when any source is approved). Private feed. | Licence stated in code: "Channel dictionary from the iptv-org database", Unlicense (public domain). This is a licence statement, not a permission from the guides | None in repo for iptv-org | Repo text 20 Nov 2026 | Confirm `guide_map` carries no guide channel names or programme text. Audit O4 asks for a per-guide public-metadata approval. | Publishing tab: approvals (no approvals means no `guide_map`). |

---

## Owner checklist (read the terms; record each decision)

The cloud session could not read these. Read each page, then fill in the decision. Do not publish any row above as "Public feed" until its decision is recorded.

| # | Item | What to read | Questions to answer | Decision (owner) | Date |
|---|---|---|---|---|---|
| 1 | API-Sports | https://api-sports.io/ and the account terms (the repo has no terms page) | Display in an app; caching duration; redistribution of data; redistribution of media (logos and images); free-plan limits | | |
| 2 | TheSportsDB | https://api.thesportsdb.com/docs_terms_of_use.php | Repo note: app-store publication requires a paid subscriber; does a public feed or a shipped app need a paid key? Artwork rights. | | |
| 3 | football-data.org | https://www.football-data.org/coverage and https://www.football-data.org/pricing | Display and redistribution; attribution wording; free-plan delay | | |
| 4 | Jolpica-F1 (CC BY-NC-SA 4.0) | https://github.com/jolpica/jolpica-f1/blob/main/TERMS.md | Non-commercial and share-alike: is a public feed in scope? | | |
| 5 | EPG guides | Section 4 URLs; EPGTalk, EPG Share, iptv-epg.org, XMLTV France have no terms in repo | Private-feed personal use only? Any guide that permits neither | | |
| 6 | Publication approvals | Home Assistant App, Publishing tab, `approval_log` | Which sources are approved today, and does a written record exist outside this repo? | | |

**Decision record (fill in):** Approved for public feed: ____ · Approved for private feed only: ____ · Not approved: ____ · Recorded by: ____ · Date: ____

---

## 6a. Conflicts found in the repository (not changed here)

- **Broadcast candidates.** [FEED_CONTRACT_SLI_V1.md](FEED_CONTRACT_SLI_V1.md) §3 says `rights.broadcast_candidates: not_published`. `feed.py` publishes `channel_links_published_unverified` in the public manifest (D8). The feed contract and code disagree; the owner should decide which is correct.
- **Repository visibility.** [LICENSING_AND_HOSTING.md](LICENSING_AND_HOSTING.md) describes Actions-minutes billing for a private repository. The App source repository is public (see [CLAUDE.md](../CLAUDE.md)), so that billing note needs an owner check.
- **Ownership split.** [CLAUDE.md](../CLAUDE.md) "Your workstream" still assigns work to Codex. This was not changed here because it is a binding working rule.
- **Jolpica.** The public manifest attributes CC BY-NC-SA 4.0 data when `jolpica` is approved (`feed.ATTRIBUTION`). See item 4 above.

## What this page does not do

- It changes no publication setting, approval, key or feed.
- It does not decide any licence question. Those decisions belong to the owner.
- It does not replace the provider terms.
