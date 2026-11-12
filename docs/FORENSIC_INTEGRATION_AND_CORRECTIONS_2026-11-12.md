# All-branch forensic audit and Claude integration: SportsLiveInfo

> **Historical audit / receipt — reviewed 12 November 2026.** Preserved against its stated original revision. Findings, branch/merge positions, provider claims and pass counts below are historical, not freshly verified current facts. Current source is v0.3.0; the combined review attempted 86 tests (81 passed, five errors, three of those environment-blocked). Use CURRENT_STATUS for resolved/remaining work; no new live source, licence or device verification occurred.
> **Repository roles:** [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is PRIVATE source/installation and stays private; [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is PUBLIC daily data only. [Current status and evidence](CURRENT_STATUS.md).

**Date:** 12 November 2026. **Scope:** all GitHub branches, unmerged development, production Python modules, Home Assistant App packaging, JSON contracts, automated tests and owner requirements.
**Status:** source-reviewed and corrected experimental implementation. No live provider, Docker build, HAOS install, client-device or licence-approval proof is implied.

## 1. GitHub inventory and critical discovery

At the audit outset, main was 4f01814022484b023f957bb98e3fed54adf9a034 (v0.2.0). Five branches existed:

| Branch | Position | Assessment |
|---|---|---|
| main | 4f018140 | Existing v0.2 EPG and sports foundation |
| claude/sportsliveinfo-b1g-android-syyo8j | fb23268c | TWO complete unmerged commits containing major EPG/sport expansion and source audits; now reviewed as integration base |
| feat/haos-app-first-installable-2026-11-12 | b5c3e41 | Prior PR #1 already merged; no new work |
| feat/haos-epg-coverage-openligadb-v0.2-20261112 | 3f61026 | Prior PR #2 already merged; no new work |
| feat/supplement-epg-hardening-v0-3-0 | 4f01814 | Empty branch at original main; no changes |

Integration branch fix/claude-integration-forensic-hardening-20261112 was branched FROM the unmerged Claude commit, retaining its original branch and full history. It includes 16 configured sporting adapters, 27 EPG guide candidates, 24 sports, about 127 competition groupings, EPG country/alias crosswalks, source-aware provisional broadcaster candidates, content-addressed public sli/1 feed with JSON schemas, golden contract fixtures, expanded Today grouping and tests.

**Important factual limitation:** a provider entry or classifier is not proof that a source endpoint works, has the advertised coverage, or may legally be redistributed. All newly added providers remain opt-in. Neither programme text nor provisional broadcaster matches is approved for public publication.

## 2. Code-level review scope

All executable application modules were enumerated, every source line scanned for unsafe exception, permission, mutable state and unfinished-work markers; named functions and critical transitions were then examined with source-level comparisons and targeted regression assertions. The reviewed modules comprise approximately 3,100+ lines: application entrypoint, engine, providers, guide, feed, linking, taxonomy, server, storage and the new supplement module. Home Assistant config/Dockerfile/Ingress rules, CI workflow, six JSON schema files (syntax checked), golden fixtures, expanded unit tests and four long Claude audit/contract documents were inspected. This is source-code analysis, **not** a proof of complete external-provider behaviour.

| Domain | Forensic findings and final disposition |
|---|---|
| Collection engine | Separate EPG/sport lanes retained; previously marked all-source failures as fresh; fixed true failure/degraded reporting and no false new aggregate on total failure |
| Provider requests | Added quota-aware API-Sports paginated fetch with all-page validation and last-good fallback; shared API-Sports pacing serialized by provider family |
| Sporting-event snapshots | Reconcile by stable ID; retain unexpired known fixtures omitted from incomplete free responses instead of erasing them |
| XMLTV parsing | Replaced whole-document expanded gzip allocation with bounded chunk reader; blocked DTD/ENTITY across chunk boundaries, preserved subtitle/category/live/replay metadata |
| EPG integrity | Quarantine severe 24-hour programme-count collapses from partially successful providers; preserve last-good; provider EPG in B1G remains authoritative |
| Storage and scheduling | BEGIN IMMEDIATE transactional quota claims across multiple Store connections; persistent scheduler slot claims across restart; malformed config rejected |
| Security | Blocked cross-origin API credential redirects; validated malformed Content-Length; configurable trusted Ingress proxy peers; no public HAOS listener |
| Rights and feed | Public static assets require all fused-source contributors approved; unpublished EPG text remains private; broadcaster boolean alone never grants verified publication |
| Channel/broadcast matching | Claude provisional candidates kept provisional; no guessed playable stream, no automatic override of B1G hidden categories or manual EPG mapping |
| Supplement feature | Added suggestion-only conservative programme enrichment evaluation; returns new display metadata without mutating provider schedule; tests for source, channel, event, region, replay/hidden/manual negatives |
| HA packaging | Experimental app files, icon/logo and Ingress structurally present; Docker/actual HAOS install not tested |
| Test/CI | Added hardening, paging, licensing and suggestion tests; GitHub Actions failures could not be diagnosed because detailed logs were unavailable |

## 3. Implemented corrections and regression cases

CR01 multi-process API quota overspend → transactional SQLite BEGIN IMMEDIATE; concurrent Store test.
CR02 duplicate scheduler after reboot → durable daily-slot table; claim/release and restart tests.
CR03 decompression memory spike → bounded streaming gzip; compressed XMLTV, expansion cap and split DTD tests.
CR04 credential-bearing cross-host redirects → block even when both domains are listed; redirect test.
CR05 free-tier partial or zero response wipes earlier fixtures → preserve unexpired IDs, merge updates; regression test.
CR06 refresh marked successful when every upstream failed → count actual successful sources and preserve prior aggregate; test prevents automatic publication.
CR07 HTTP 200 with near-empty guide replaces valid schedules → 24-hour coverage-collapse quarantine; test.
CR08 incomplete API-Sports pages → fetch all pages with quota reservations; reject inconsistencies without destroying previous scope; tests.
CR09 fused event contains unapproved contributor → public events default-deny unless all contributors approved; test.
CR10 unverified broadcaster flag results in public channel → enforce approved rule and evidence; test.
CR11 concurrent same-key provider burst → family-wide pacing.
CR12 configuration accepts wrong types/provider names → explicit validation; test.
CR13 malformed Ingress Content-Length → HTTP 400; proxy peer configuration.
CR14 generic sports guide needs better description → non-destructive evidence-gated enrichment proposal, with six guardrail tests.

## 4. Critical scope decisions retained

- SportsLiveInfo **supplements** B1G; it does not replace the playlist/provider EPG. Never overwrite B1G original programme rows or per-account user-selected EPG/visibility. Final IPTV stream ID and playback always chosen locally by B1G.
- Multi-country general programme EPG and international sports event intelligence are TWO independent, equally important engines. Sports Today cards are not equivalent to a complete Guide.
- Ten televisions only READ rights-cleared static GitHub snapshots. Only the private HAOS server initiates outbound publisher HTTPS; no incoming public Home Assistant connection.
- Movie/series poster, TMDB, OMDb and hero artwork requests remain in B1G. Personal channel inventories and subscription credentials never appear in public feed.
- A broadcaster being a rights-holder or showing a generic EPG slot does not independently verify an exact live fixture. Provisional matches remain non-playable until B1G resolves local channel and verified evidence.

## 5. Testing honesty

Claude's branch docs report 43 offline tests after source expansion and 55 after JSON feed/fixtures. The present integration adds 13 independent forensic hardening tests, 6 non-destructive supplement tests and replaces one obsolete auto-publish expectation. These tests **have not been executed end-to-end from the exact integration GitHub tree in this environment** because the connected private repository was accessible through GitHub actions but not mounted as a clone in the Python runner. A prior local v0.2 surrogate implementation passed 49 tests, which is NOT a valid claim for this Claude-integrated branch. CI reports failure with unavailable logs; full current-branch tests remain a mandatory merge/deployment verification gate for the terminal agents.

Required terminal commands on the current actual checkout:

    python3.12 -m compileall -q sportsliveinfo/src
    PYTHONPATH=sportsliveinfo/src python3.12 -m unittest discover -s tests -v
    python3.12 -m py_compile sportsliveinfo/src/sportsliveinfo/*.py
    # Then build and install the HAOS App, test Ingress, sources, rights and resource usage on real hardware.

## 6. Remaining items — prioritised before first genuine test installation

| Priority | Requirement | Why open / acceptance |
|---|---|---|
| P0 | Verify full branch tests and CI | Unavailable GitHub Actions logs; actual 3.12 clone run required; do not call green without evidence |
| P0 | HAOS App store Docker build and real install | Architectures, installation, /data persistence, Ingress and restart have not been tested on owner's mini PC |
| P0 | Live validate enabled UK/FR/international EPG endpoints | 27 catalogue entries include unverified URLs; source horizons, sizes, coverage and rights unknown |
| P0 | Live validate sports API response shapes and real quotas | 16 adapters are candidates; false competition coverage and 429/partial pages must be caught |
| P0 | Public redistribution licences | Unapproved programme/derived text is blocked; find licensed source or preserve B1G direct EPG |
| P0 | B1G sli/1 read-only consumer and actual device acceptance | No tested Kotlin manifest+hash reader, local source channel matching and 10-TV use |
| P0 | Independently confirmed match broadcaster & licence | EPG candidates are not a confirmed transmission; verified live/PPV and UK/FR service edition remain outstanding |
| P1 | Home Assistant actionable persistent notifications | Documented first-run/quiet error experience not yet fully implemented and needs privilege review |
| P1 | HTTP ETag/If-Modified-Since/304 and Retry-After | Unnecessary large guide downloads and quota use still possible |
| P1 | Monthly/provider-timezone budgets | Current reservation ledger only UTC calendar daily |
| P1 | Channel-by-channel EPG minute coverage and labelled sport recall | Need empirical completeness/precision, including owner-sanctioned safe subscription inventory |
| P1 | Scalable programme storage and paging | Large EPG JSON snapshots and UI may exceed memory/CPU on HA mini PC |
| P2 | Additional tennis order of play, boxing card structure, MotoGP and sports-specific reliable live status | Provider-dependent richer sport coverage without paid plan |

**Conclusion:** Integrate Claude's code as experimental, retain all audit histories and truthful test status, prioritise actual Home Assistant/endpoint/B1G acceptance next. No source code inspection alone can promise 100% accuracy or completeness.
