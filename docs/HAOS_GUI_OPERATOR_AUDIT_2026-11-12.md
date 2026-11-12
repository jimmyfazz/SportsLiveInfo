# Home Assistant Ingress GUI — operator audit and implementation
**Date:** 12 November 2026  
**Repository:** private `jimmyfazz/SportsLiveInfo`  
**Branch/PR:** `feat/haos-operator-dashboard-ux-20261112`, PR #7  
**Status:** CODE IMPLEMENTED (experimental v0.3.1); GITHUB CI CHECK NOT VERIFIED; REAL HAOS/MOBILE VISUAL ACCEPTANCE NOT RUN.

## Scope and source of truth
This audit covers `sportsliveinfo/src/sportsliveinfo/server.py`, storage/engine interaction, the persistent source catalogues, GitHub fine-grained-token workflow and the current suite. The separate **public** `jimmyfazz/LiveSports-EPG` is a read-only destination and contains no Home Assistant GUI. None of these changes publish a feed or approve redistribution.

## Findings addressed

| Finding | Baseline behaviour | Implemented correction | Acceptance proof needed |
|---|---|---|---|
| GUI-001, severe | Numeric `0` displayed as blank due to `e(value or "")`. | Escape helper preserves `0` and `False` while retaining HTML escaping. | Regression test and Overview 0-event screenshot. |
| GUI-002, high | Horizontal navigation wrapped awkwardly on small screens; no active-page semantics or skip link. | Responsive scrollable sticky navigation, `aria-current`, keyboard focus, skip link, reduced-motion styles, improved contrast, larger touch targets. | Real Ingress mobile/tablet/desktop visual+keyboard audit. |
| GUI-003, high | Initial Overview exposed counters but not what to do next or whether cached data was stale. | Readiness checklist, status indicators, last-good age, running refresh state, direct operational shortcuts. | Real refresh, source failure and restart test. |
| GUI-004, high | 16 sports adapters and 27 EPG feeds produced a very long undifferentiated page. | Grouped collapsible family/market panels, sport/EPG tabs, per-provider latest job state, saved-key indicator and EPG 24h coverage counters. | Expanded panels, save/test, mobile scrolling, large source list. |
| GUI-005, high | Guide coverage was mostly a numerical table, with little proportional feedback. | 24/72/168h accessible percentage bars, clipped 0–100%, expandable channel-family and missing-coverage tables. | Test zero/full/invalid totals and real full-country report. |
| GUI-006, medium | Diagnostics required interpreting a raw event table; quota data could dominate page. | High-level failure/warning/request counters, status badges and collapsible quota ledger. | Check statuses against local jobs. |
| GUI-007, high | Public publish button appeared active even without token, approvals or enabled publishing (backend already refused). | Visible independent prerequisites, disabled publish control until all are satisfied. | Confirm backend still refuses unapproved data. |
| GUI-008, medium | Browser user experience relied on implicit click feedback. | Semantic `role=status` save/test notices, visual status colours with explicit text, labelled navigation. | Screen-reader inspection and keyboard-only manual test. |
| GUI-009, high | First-run setup contained only a banner and a completion button at the end of long forms. | Persistent three-stage sources → scheduler → optional GitHub step shortcuts, with accessible setup group and separately styled validation errors. | Interrupt/resume setup on Home Assistant Ingress. |
| SRC-010, high | EPG Test Connection accepted a syntactically valid but fully expired programme list, falsely implying usable guide coverage. | A non-destructive preflight now requires at least one programme overlapping the next 24h; returns an unsuccessful test and local diagnostic otherwise. | Synthetic current/expired XMLTV unit tests plus real expired-feed negative. |
| GUI-011, high | Sports Events page silently omitted matches beyond the first 200, with no date filter. | Added stable server-side 100-row pagination, UK-local date, sport/competition/title filters and saved filter state in page links. | Synthetic 235-event pages, BST midnight boundary and XSS tests; browser interaction pending. |
| HAOS-012, P0 | Private source URL could not be assumed accessible to Supervisor as an external Apps repository; no safe first-install path. | Documented authenticated Mac ZIP → HAOS `local_apps/sportsliveinfo`, rebuild and troubleshooting; no public source disclosure. | Actual HAOS `local_sportsliveinfo` installation, restart and restore required. |
| PERF-013, P1 | Full EPG scoring was performed before rejecting stale or collapsed imports. | Defer private quality analysis until after source freshness and collapse checks. | Synthetic old/current XMLTV tests; real CPU/memory benchmark pending. |
| RELEASE-014, P1 | App/config/Docker versions might diverge across development changes. | Align all to experimental v0.3.1 and add static consistency test. | Docker image label/build inspection pending. |

## Behaviour deliberately unchanged
1. No browser JavaScript, third-party UI assets, analytics or external CSS; the existing private Home Assistant Ingress/CSRF boundaries are retained.
2. Each sports and EPG provider still has its own Save/Test form. API-Sports keys are shared according to existing config rules; blank keys do not overwrite a saved key.
3. Unknown, estimated and unverified sports-to-broadcaster matches are not presented as confirmed channels.
4. Provider collection remains opt-in and quota-limited; partial imports retain last-good.
5. `sli/1` publishing is still denied by default and must pass back-end per-source rights approval. No external EPG programme text is published.
6. Operator diagnostics display only locally sanitised job details. Do not log private stream URLs or actual API keys.

## Manual HAOS acceptance matrix — not performed

1. Install Home Assistant App using **SportsLiveInfo** private/custom Apps repository (not LiveSports-EPG), and open Ingress on an authorised desktop browser. Verify routes Overview, Today, Sports, Guide, Sources, Scheduler, Publishing and Diagnostics.
2. Repeat at widths about 375 px, 768 px and 1280 px; check no page-level horizontal scroll, deliberate table overflow, contrast, headers, sticky nav, `details` controls and focus navigation.
3. First run with no collection: all zero-valued metrics visible; no false green EPG state. Enable a no-key adapter; save; test; inspect source status and quota ledger.
4. Save a key-required adapter key and revisit: only "Key stored privately", not key contents, should render; saving an unrelated adapter should not erase it.
5. Attempt overlapping collections: start button indicates refresh running and backend rejects duplicate jobs. Restart HAOS App and ensure prior valid sports/EPG snapshots remain visible.
6. Analyse a large guide: percentages should be reasonable, missing channels individually listed in collapsed panel; no personal playlist or programme data should appear on the public feed.
7. Publishing: before configuring a token, preview remains available but publish is disabled; save/test token using fine-grained GitHub steps; **do not** approve unlicensed redistribution to test a publish.
8. Verify `Home Assistant` mobile embedded webview behaviour, including touch hit targets and horizontal guide tables.

## Known limits / priority next steps
- **P0 – Actual installation:** No real HAOS Supervisor, local Docker build, credential storage/restore or ingress session validation run in this execution environment.
- **P0 – CI visibility:** GitHub Actions PR #7 produced a completed `failure` check without step detail or retrievable logs. Previous SportsLiveInfo PRs had the same runner/BlobNotFound symptom. This is not evidence of passing source tests. Run `PYTHONPATH=sportsliveinfo/src python -m compileall -q sportsliveinfo/src` and `PYTHONPATH=sportsliveinfo/src python -m unittest discover -s tests -v` on a local clone if CI remains unavailable.
- **P0 – Product scope:** World EPG source presence is not source correctness. Benchmark actual UK/FR and chosen international channel coverage, inspect service/variant hard negatives and confirm provider rights before any public feed.
- **P1 – Browser visuals:** Obtain real HA Ingress screenshots for 375/768/1280 widths and compare against the attached checklist; adjust density, typography and spacing based on observed output.
- **P1 – Source ops:** Provider-state UI currently reflects the latest local saved job, not independently measured external service uptime; job retention is capped at 300.
- **P1 – Access policy:** Home Assistant Ingress does not independently prove `admin-only` at individual form-route level. Confirm HA policy/installation and avoid exposing the app to non-administrators.
- **P1 – Large UI data:** Server-side HTML for the EPG attention list should be paginated if benchmark data shows high row counts.
- **P1 – B1G:** Read-only Android `sli/1` consumer, feed revision validation, channel/source matching and eventual legally clear programme enrichments are outside this GUI PR.

### Source-aware release gate
Do not call the Home Assistant app "install-accepted" or "visual parity accepted" until an actual HAOS installation and browser acceptance matrix pass. No source accuracy, redistributability or ten-TV readiness is implied by these GUI updates.
