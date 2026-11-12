# SportsLiveInfo — implementation progress and agent handover
**Baseline established:** 12 November 2026.  
**Working project:** `jimmyfazz/SportsLiveInfo` (private).

## Current truthful status

| Area | Research/specification | Actual code | Tests | Live validated | Deployed |
|---|---|---|---|---|---|
| Full UK/FR/international EPG engine | Documented | **Not started** | **None** | **No** | **No** |
| Multi-sport event intelligence engine | Documented | **Not started** | **None** | **No** | **No** |
| Canonical broadcaster matching / event-to-programme | Documented | **Not started** | **None** | **No** | **No** |
| Python package, SQLite, schedulers, quotas | Planned | **Not started** | **None** | **No** | **No** |
| Home Assistant App, first-run wizard and errors | Detailed UI spec | **Not started** | **None** | **No** | **No** |
| GitHub public feed publisher | Rights-gated design | **Not started** | **None** | **No** | **No** |
| B1G read-only sport/EPG consumer | Forensic B1 source code reviewed | **Not started** | **None** | **No** | **No** |

This document is a starting record, **not evidence that the plan has been implemented**. Historic B1G code is real, but integration with SportsLiveInfo is still future work.

## Required first PRs

- [ ] **Codex:** CORE-001 and CORE-002 — reproducible package, v1 JSON Schema, synthetic golden fixtures and offline tests. Then SPORT-001/002.
- [ ] **Claude:** prepare EPG-001/002 and UK/FR source coverage against frozen schema; separate worktree, no edits to Codex-owned schema until agreed. Can begin synthetic XMLTV parser and UI mock without provider keys.
- [ ] **Both:** review contract fixtures, strict licence gate and source-identity hard negatives before either uses provider live keys.
- [ ] **Owner:** no new signups required until adapter needs exact test key; no public GitHub feed or Home Assistant port exposure during development.

See [work-package backlog](WORK_PACKAGE_BACKLOG.md), [master roadmap](MASTER_IMPLEMENTATION_ROADMAP.md) and [terminal-agent collaboration](CODEX_CLAUDE_COLLABORATION.md).

## Handover record template (agents append after REAL work)

### YYYY-MM-DD — WP-ID — agent — PR / SHA
- **Repository and branch:**
- **Tested at commit:**
- **Code files / contract changed:**
- **Feature demonstrated:**
- **Tests actually run:** commands and pass/fail totals
- **Coverage benchmark:** sport, competition, EPG country/channel, time horizon, sample size; mark unverified if not run
- **Source quota and licence decision:**
- **Security/privacy impact:**
- **HAOS or B1G actual device test:**
- **Open issues/next step:**
- **Reviewer / merge status:**

## Non-negotiables

User's actual HAOS mini-PC remains private; no WAN ports, no public HA hosting, no TV write access to GitHub. TMDB/OMDb/artwork remain separate in B1G. Sources, UK/French EPG, event/broadcaster truth and public feed rights must be separately measured/approved.
