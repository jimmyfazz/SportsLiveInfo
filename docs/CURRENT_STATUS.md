# Current implementation and verification status

**Reviewed 12 November 2026. Source baseline:** `579541fa9a8f7f0108e454f654221c01049b6e76` on `main`. This revision updates documentation and deterministic test infrastructure/fixtures; it changes no production application code, schemas, golden fixtures, Home Assistant settings or repository visibility.

This is the current status reference. The master roadmap governs required scope; `FEED_CONTRACT_SLI_V1.md` and `schemas/` describe the implemented wire format. Dated audits retain their original baselines and findings; they are not current deployment receipts. See [document index](DOCUMENTATION_INDEX.md) for each document's role.

## Repository roles and operating boundary

| Repository | Visibility | Role |
|---|---|---|
| [jimmyfazz/SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) | **Private; stays private** | Source, documentation, tests and Home Assistant App installation package |
| [jimmyfazz/LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) | **Public** | Daily static data-feed destination; never the App installation repository |

Owner reconfirmed these roles during this review. GitHub's contents API returned only `README.md` in the public feed repository on 12 November 2026; no live `v1/manifest.json` was present. Repository existence is separate from feed publication or data-rights approval. Publishing and automatic publishing default OFF; no configured credentials or approvals on the owner's installation were inspected.

The intended collector host is the owner's always-on home mini PC, with Home Assistant directly installed. Exact installation type, architecture, App build/install, restart and backup/restore remain unverified. The connected Home Assistant MCP exposed entity/device tools but no Supervisor or App inspection tools in this session. A name-filtered query found no exposed SportsLiveInfo entity; this does **not** prove the App is absent. The owner's existing authenticated remote administration is separate from SportsLiveInfo: the project requires no new WAN ports, public App endpoint, or TV connection to Home Assistant. Do not commit the owner's private Home Assistant URL.

## Implemented source versus remaining acceptance

The package, `config.yaml` and Dockerfile build-version default all identify **0.3.0**, with `stage: experimental`. Source exists under `sportsliveinfo/src/sportsliveinfo/`; it is not an empty scaffold.

| Area | Source present | Remaining work / evidence |
|---|---|---|
| App package | Supervisor config, Dockerfile labels, amd64/aarch64 declarations, Ingress/admin panel, icon/logo | Real Docker builds and HAOS installation; private local delivery documented in the [operator guide](../sportsliveinfo/DOCS.md) |
| Operator UI | Resumable settings, provider Save/Test, source enablement, Live today, events filters, guide coverage, schedule, publishing, diagnostics, CSRF and trusted-peer checks | Actual Supervisor Ingress verification; full specification acceptance and HA persistent notifications |
| Persistence/operations | SQLite WAL, private settings and snapshots, daily UTC request ledger, durable scheduler claims, last-good preservation, bounded collection lanes | Schema migration/restore evidence, monthly and provider-timezone quotas, ETag/304/Retry-After and resource profiling |
| Sports | **16 adapter registry entries**, event normalization, source fusion, partial-scope retention and status/precision labels | Live source/endpoint and quota checks, measured recall per competition, specialist tennis/boxing and fuller sport hierarchy |
| Taxonomy | **24 sports, 127 competition rows** | Taxonomy entries are categories, not proof of provider coverage |
| EPG | **27 candidate feeds across 15 source markets**, bounded streaming XMLTV, private programme snapshots and 24/72/168-hour diagnostics | Source rights, live horizons/accuracy and large-feed memory tests; inventory-driven expansion |
| Channel identity | Service tables in **8 markets**, exact source crosswalk, **41 lineup families**, hard-negative cases | Complete verified service/variant catalogue and measured on-device matching; families are diagnostic, not stream identities |
| Event → broadcast | Provisional EPG candidates; publication requires `broadcast_verified`, rule `approved_v1` and evidence | Reviewed independent verification rule and real per-event/territory evidence; no guessed playable channel |
| EPG enhancement | `supplement.py` evaluates conservative suggestion-only overlays without mutating provider rows | No public programme-supplement asset/schema or B1G rendering integration; original provider Guide remains primary |
| Static output | `sli/1.0` builder, six schemas, golden fixtures, local preview, Git Data API atomic commit writer, retention of ten manifest revisions | Source redistribution approval, authorized live publish and anonymous asset/deployment verification |
| B1G / ten TVs | Contract and synthetic matching cases in this repo; separate B1 handover documented | Android reader, local account/channel mapping, Guide integration and one-then-ten-TV acceptance are not verified by this review |

Counts were measured by importing `providers`, `taxonomy` and `guide` from the pinned source. The registry contains **10 API-Sports adapters**, sharing one key setting, plus Jolpica, OpenF1, OpenLigaDB, football-data.org, TheSportsDB and CricketData.org. Three optional private sports-key settings are API-Sports, football-data.org and CricketData.org; other entries use no owner-entered key. These are source configuration facts, not newly checked supplier free-tier entitlements. Jolpica is initially selected, collection waits for setup completion, all EPG and newly added sources default disabled. Do not claim every sports source defaults disabled.

## Implemented public contract

`v1/manifest.json` references content-addressed taxonomy, channels/guide catalogue, eight daily event assets, Today grouping and optional health. The current exporter sends **no EPG programme rows or EPG-derived provisional broadcast candidates**. Catalogue URLs and coverage counts do not constitute full Guide delivery.

All contributors to a fused event must be in `publication_approvals`; the builder uses an event-field whitelist. The current gate is source-level, with a conservative all-contributors check; the richer per-field licence/evidence state machine in the design is not fully implemented. A token connection test uses GET requests and neither enables publishing nor proves Contents-write capability. An atomic Git commit does not prove simultaneous CDN availability. B1G must validate complete revisions and retain last-good.

## Validation receipt from this review

The pinned GitHub files were materialized locally with exact UTF-8 contents and original binary assets because direct shell GitHub DNS was unavailable. Tests used that complete source snapshot, not a substitute implementation.

```sh
python3.12 -m compileall -q sportsliveinfo/src
PYTHONPATH=sportsliveinfo/src python3.12 -m unittest discover -s tests -v
```

**macOS, Python 3.12.15, 12 November 2026:** compilation passed; **88 tests passed**. The two feed-rights test inputs now go through the production taxonomy classifier and use a pinned clock. Three ingress tests share a transport helper: they use real loopback HTTP when permitted and dispatch through the real HTTP handler/parser using in-memory streams when the runner denies socket binds. Two additional tests cover the forced in-memory CSRF and origin behavior.

This runner denied loopback binds, so this run does **not** verify the real socket transport, actual Home Assistant Supervisor/Ingress behavior, Docker build, live provider quality/rights, or TV acceptance. Golden feed/hash fixtures passed unchanged. GitHub Actions evidence must be read separately from this local receipt; the previous run had no readable step logs.

Historical 7-, 19-, 43-, 55- and 86-test receipts apply only to their recorded revisions. Do not use them as the current suite result. No new live source, licence or device verification occurred.

## Next work and release gates

1. Confirm readable GitHub Actions evidence for this revision and exercise the real loopback HTTP transport in a runner that permits socket binds.
2. Build/install the private App on the real HAOS host, verify Ingress, settings, restart, restore and household resource impact.
3. Independently validate selected EPG and sports endpoints, rights, quota resets, completeness and source lineage. Record measured coverage separately for both products.
4. Finish approved broadcast evidence and the versioned, rights-cleared programme-supplement contract; preserve provider EPG and local manual/hidden choices.
5. Complete scoped publication/deployment verification and the B1G read-only reader, then validate one TV and all ten.

International full-channel EPG and worldwide sports events remain equally required. TMDB/OMDb, movie/series metadata, posters, hero art, IPTV credentials, stream URLs and per-TV preferences stay outside this collector/public feed.

## Maintaining these documents

Update this file and `IMPLEMENTATION_PROGRESS.md` with source SHA, exact commands/results and evidence whenever status changes. Update the operator guide for real behavior and `FEED_CONTRACT_SLI_V1.md` plus schemas/fixtures for wire changes. Keep dated audits as historical evidence with an explicit link here; never silently relabel an old finding as newly verified. Provider prices, limits, terms and external B1 source baselines need a separate dated recheck before use. Documentation rollback is a revert of the documentation commit; no runtime state needs migration.
