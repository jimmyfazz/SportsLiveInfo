# SportsLiveInfo — forensic source, EPG, manifest, B1G and operator-experience audit

**Inspection date:** 12 November 2026  
**Source baseline:** private \`jimmyfazz/SportsLiveInfo\` main \`7051240b557353211056b0afeb5007b5ca342185\`, prior to this report; public output repository \`jimmyfazz/LiveSports-EPG\` is a separate public README-only repository.  
**Status labels:** SOURCE-VERIFIED = implementation present in inspected code; SPECIFIED = design documented only; CANDIDATE = provider named but live data/reuse rights not validated; FIX-IN-PR = code added on this audit branch; EXTERNAL-TEST = not yet reproduced on HAOS/Android. Do not equate an HTTP 200, a configured provider or a passing parser fixture with comprehensive coverage or a license to redistribute data.

## Executive assessment

**The two products must be developed and accepted independently, then joined safely**:

- **EPG supplement (not replacement):** preserve the native B1G subscription/provider XMLTV, user-selected mappings, hidden categories/channels, source precedence, and per-account local stream IDs. SportsLiveInfo should propose *verified improvements or gap-fill candidates*, never overwrite the original schedule merely because a new source exists. Source-specific programme rows are currently private to HAOS and *not published in sli/1*. This is a **material gap** between the user's intended enhanced Guide and what the public feed can currently deliver.
- **Sports intelligence:** independently discover matches, sessions and cards with correct local UK date/time, competition, team/venue, live status/precision, actual UK/FR broadcast evidence and appropriate non-playable unknown states. The 24-sport taxonomy and 16 adapters are extensive scaffolding but not proof of fixture recall or exact channel carriage.
- **Distribution:** \`sli/1\` publishes a rights-gated, versioned static identity/taxonomy/event feed; the ten B1G TVs have no write credentials and do not contact Home Assistant. The public repo is a distribution endpoint, **not** a Home Assistant Apps installer repository. HAOS remains local-only.
- **Operator experience:** the current Publishing page has token input but *not* a creation walkthrough or safe test button. This branch implements a step-by-step fine-grained token guide and authenticated **GET-only connection test**, with strict explanation that a read test does not prove write access.

## 1. Inspected code: actual responsibilities

| Module / artefact | Verified functionality | Principal review concern |
|---|---|---|
| \`server.py\` | HA Ingress pages: first run, source/key Save/Test, UK time, EPG diagnostics, GitHub publish, scheduler, CSRF, admin link, source health | Token onboarding too terse; no licence-approval wizard; page lists guide candidates as though suffix-based URL verification were meaningful; no HA persistent notification bridge |
| \`engine.py\` | Quota-reserving per-source refresh, threads, source failure tracking, last-good, UK-time schedule, publication, Git Data API | No conditional GET/304; API source account daily/monthly quota family; fresh manifest may include old snapshots; Git CDN verification absent; source completeness unresolved |
| \`providers.py\` | 16 sports adapters and 27 EPG sources/candidates, HTTPS source allowlist, cautious XMLTV streaming and time normalisation | Coverage by specific competition unknown; candidate feeds may be 404/stale/restricted; XMLTV still produces a full in-memory programme list; live OpenF1 is a paid plan |
| \`guide.py\` | Country-aware channel aliases, farleyflex XMLTV crosswalk, family classification, 24/72/168h coverage and generic-title metrics | Generic family ≠ exact broadcaster; only one curated ID crosswalk; unknown UK/FR subregions and real subscription-specific catalogues; coverage not paired with redistribution rights |
| \`linking.py\` | Source-family de-duplication, participant/sport comparison, EPG text matching, provisional broadcaster candidates, UK Today grouping | Event-to-programme comparison traverses all indexed guide rows per event; large country guides may be slow; provisional evidence cannot drive Watch/play |
| \`taxonomy.py\` | 24 sports, many competition IDs, national/team tags, classifier and default sport durations | Matching by name/prefix can misclassify; multi-country league homonyms and real provider league IDs need measured negative tests |
| \`feed.py\` | Public \`sli/1\` contract, content-addressed assets, 8 dates, hashes, event field whitelist, source approvals/attribution and health | **No EPG programme supplement asset**; source URL \`url_verified\` inferred from a display-label string; no reliable per-item source age/conflict/coverage completeness; broadcast proof field is manually asserted |
| \`storage.py\` | SQLite kv/snapshot/job/UTC-day calls, transactional quota reservation, scheduled-slot claims | Big JSON snapshots, no indexed programme store; no monthly account-wide quota; token at rest in HAOS backup; source freshness/responses not versioned |
| \`supplement.py\` | Conservative suggestion-only original-to-detailed title proposal | Not yet invoked in publication pipeline or Android; requires independently verified per-event broadcast evidence; no authorised public supplement schema |
| \`config.yaml\`, \`Dockerfile\`, \`repository.yaml\`, logo/icon | Home Assistant OS Apps repository structure, private Ingress with no host port, Supervisor metadata | No successful physical HAOS install, backup/restore, Docker build or resource profile |
| \`schemas/\`, \`tests/\`, \`tools/generate_feed_fixtures.py\` | v1 schemas, golden fixtures and offline test suites | New code and schemas need full combined-branch CI and Kotlin consumer contract; GitHub checks have been failing with inaccessible logs |
| \`docs/*\` | Extensive Claude audit, master plan, sources and B1 integration handover | Some historical prose predates the verified public output repository and claims an installation-ready/full EPG capability without independent test evidence |

## 2. Prioritised forensic findings register

**P0 = necessary before a credible fully functioning B1G EPG/sports rollout; P1 = major enhancement/reliability; P2 = subsequent expansion.** This is an ordered implementation backlog; candidate features are not checked off until actual tests and source permissions pass.

| ID | Priority | Concrete finding | Correction / acceptance |
|---|---|---|---|
| TF-01 | P0 | Publishing screen gives no practical steps for acquiring a minimally scoped GitHub token and no Test Connection | **FIX-IN-PR:** provider-independent seven-step UI and GitHub GET-only verification of public repo/branch. Save and Test distinct; token never logged/uploaded to TV |
| TF-02 | P0 | User has a separate public \`LiveSports-EPG\` repo but no live manifest | Confirm \`jimmyfazz/LiveSports-EPG/main\` as destination. No publication until fine-grained token and field-specific rights approval; reject idea that public data repo installs HAOS App |
| TF-03 | P0 | \`sli/1\` publishes identity/events but \`rights.epg_programmes=not_published\`; **no actual enhanced EPG programmes reach B1G** | Add additive \`sli.epg-supplements/1\` assets **only for independently verified and redistributable content**. Include canonical channel ID, territory/edition, UTC coverage start/end, source IDs/families, explicit rights, confidence, original/suggested display fields, effective/expiry dates and conflict markers. B1 locally overlays only when relevant and user opts in |
| TF-04 | P0 | B1G SportsLiveInfo consumer is not implemented | Implement feature-flagged Android read-only manifest + SHA256 verify + bounded cache/last-good + server independence; ensure per-account manual mapping, visible-only projection and fallback never broken |
| TF-05 | P0 | Current verified broadcaster logic is not a tested, independent event-to-programme publication pipeline | Implement provenance-based independent live broadcast confirmation; forbid rights-owner-only, generic-title-only, highlights/replay, other territory, event-only multiplex assumptions |
| TF-06 | P0 | Licence checks are source-name approvals, not immutable per-field evidence permissions | Maintain source field-use matrix (public event facts, programme titles/descriptions, derived titles, aliases, attribution, source family, expiry); publish default DENY and retain approval evidence/version. A manual \`publication_approvals\` list is not proof rights were granted |
| TF-07 | P0 | 27 EPG entries include "(verify)" URLs and many unproven endpoints; a URL configured in code is not actual coverage | Perform dated source-by-source response, licensing, program-duration, country/region, duplicate/overlap and last-seen tests. Auto-disable/review failing candidates rather than treating HTTP 200 as success |
| TF-08 | P0 | 16 sports adapters do not prove competitive coverage: a free response may omit entire leagues | Build competition-ID allowlist and per-competition day completeness ledger; independent official reference benchmark incl football Europa, UCL, FA Cup, F1 weekends, rugby, cricket, tennis and boxing |
| TF-09 | P0 | Current guide/canonical registry is sparse for real UK/French subscription lineups | Owner-triggered secret-free import; matching by source namespace + country + edition + time shift, not just normalised names; no per-TV uploads or secret/public stream IDs |
| TF-10 | P0 | Normal B1G baseline may be correct despite a secondary guide disagreeing | Preserve provider programme and display an evidence-scored overlay or bounded gap fill only. Reject unknown times/other-language editions, preserve user manual choices and hidden categories |
| TF-11 | P0 | Manifest timestamps refer to generation, not age/completeness of every contributing source | Per-source \`collected_at\`, \`observed_at\`, \`source_generated_at\`, \`coverage_until\`, \`status\`, \`incomplete_scope\`, source family and SLA; never imply refreshed sport data merely because EPG was fetched |
| TF-12 | P0 | No verified Home Assistant installation on mini PC or combined green CI | Test actual HAOS (amd64/aarch64), app repository discovery, Docker build, Ingress auth, key Save/Test, /data survive reboot/restore and watchdog; run entire suite from exact source HEAD |
| TF-13 | P1 | Large EPG+events crossing via nested scan in \`linking.broadcast_candidates\`: O(events × qualifying guide rows) | Partition by window, canonical channel, sport and tokens; interval tree or indexed time buckets; benchmark 25k/100k/300k programmes and multi-thousand events on HA mini PC |
| TF-14 | P1 | XMLTV parser streams decompression but stores every programme as a Python dict and a duplicate JSON SQLite snapshot | Incremental source staging in indexed SQLite, batch commits and bounded programme lifecycle; compare runtime memory, disk, parse time and Home Assistant responsiveness |
| TF-15 | P1 | Whole-guide coverage-collapse detector is based on count of programmes in 24h, not programme minutes per channel | Per-channel rolling coverage minutes/valid intervals; classify large deletions vs legitimate seasonal schedule changes; keep last-good for affected channel only, not entire guide when possible |
| TF-16 | P1 | Source URLs \`url_verified\` are currently inferred from display name lacking "(verify)" | Replace with dated persisted endpoint validation result including actual HTTP state, schema, programmes, country, and \`last_tested\`. Default UNKNOWN; never publish \`true\` based on label text |
| TF-17 | P1 | No conditional HTTP ETag/Last-Modified handling or quota-neutral 304 result | Store response validators + SHA and only parse changed EPG, bounded 304 logic; nightly refresh after actual upstream revision; avoid daily large rescans |
| TF-18 | P1 | Provider daily quota ledger is endpoint-specific UTC-day; several products share account/key and some impose monthly caps | Ledger by key/provider family and endpoint, UTC/provider reset time, minute/day/month, \`Retry-After\`, budgets by required competition and fallback |
| TF-19 | P1 | GitHub output publication successful in Git API does not prove anonymous static feed is visible or complete | Verify \`manifest.json\` and all mandatory referenced assets via anonymous HTTPS GET, digest/bytes, allow CDN propagation and rollback to last-good; do not mark published until verified |
| TF-20 | P1 | Broadcast candidates are computed from full EPG with little independence evidence; source mirrors can be treated as multiple sources | Maintain data-lineage graph and official per-programme corroboration, count mirrors as single evidence source; no verified Watch until hard gates met |
| TF-21 | P1 | Source-derived multilingual EPG titles/categories do not have a fully governed translation model | Preserve original title and language (BCP47), optional licensed translated title with translator/provenance and locale; do NOT mistranslate teams/club names, sport subtype, channel edition, or timeshift |
| TF-22 | P1 | Sports event models differ by match/race/session/card/tournament, and v1 feed compresses optional semantics | Schema-specific event hierarchy, \`start_precision\`, actual vs estimated vs not-before, programme vs event start; multi-day cricket, F1 sessions, tennis court schedules and boxing walk |
| TF-23 | P1 | \`sli/1\` lacks explicit per-field conflict/correction semantics and source-age checks B1G can enforce | Add small versioned \`evidence\`, \`confidence\`, \`original_source\`, \`expiry_utc\`, \`recommended_action\` and \`reason_codes\` to additive 1.x contract; negative fixtures and Kotlin golden tests |
| TF-24 | P1 | Persistent Home Assistant notifications are only specified, not built | Dedupe on source+error family, cooldown, recovery clear; actual HAOS permissions/bridge security review; no push alerts by default |
| TF-25 | P1 | Save/Test UI shows all configured provider candidates even if source rights or login state do not support actual use | Provider registry \`no-key\`, \`key required\`, \`tested\`, \`quota exhausted\`, \`terms review\`, \`offline\`, \`unsupported\`. Test reports source coverage evidence and never pretends to grant publication rights |
| TF-26 | P1 | Source code at rest stores provider keys/GitHub token in private SQLite/HAOS backups but mask is only visual | Document backup security, key rotation, filesystem permissions and token expiry/reauthorisation; best-effort secret redaction in exceptions; evaluate encrypted-at-rest HAOS secrets option |
| TF-27 | P1 | Dashboard health aggregates source requests without per-lane error and accuracy trend | Separate EPG and sports health panels: last source success, stale hours, guide hours by channel, match recall, exceptions, rights coverage, quota remaining, latest public SHA and B1 consumer age |
| TF-28 | P1 | Automatic App install readiness and SHA verification not fully confirmed | Pin reproducible Python/Alpine dependencies, test on supported Docker architectures, validate configuration yaml and panel appearance, restart and upgrade paths |
| TF-29 | P2 | No source inventory diff view showing when a channel was removed/renamed/added | Ingress owner-only channel-change import diff, safe schema fingerprint and explicit mapping review; local TV hidden changes remain invisible to host |
| TF-30 | P2 | Additional sport-source families not implemented beyond 16 adapter registry | Priority new tennis, boxing, sport-wide coverage and official calendar adapters under documented source-rights and quota budgets; then MotoGP, darts, snooker, golf, WEC/Formula E, NHL/NFL/NBA, women's competitions |
| TF-31 | P2 | Several other countries and editions are only identified by naming heuristics | Opt-in international source registry by country/territory/edition with UK+FR first, IE/BE/CH/DE/ES/IT/PT/NL next as actual subscription requires, then AU/CA/US and diaspora services |
| TF-32 | P2 | Developer agents can confuse the public output repo with the private Home Assistant App source | Pin two repo roles and read-only TV security invariant in README, startup instructions, B1 handover and release gate; never ask TV to configure GitHub credentials |

## 3. Further candidate providers and data sources — researched, NOT activated

| Source / approach | Value | Status / caution |
|---|---|---|
| [Tennis API](https://docs.tennis-api.com/getting-started) | ATP/WTA tournaments, calendar, order of play, not-before starts and match events | Official documentation: FREE 50/day, 4 req/sec. Key signup via RapidAPI. Copyright/redistribution of results must be reviewed. Add optional tennis specialist adapter and explicit tournament/day completeness |
| [Boxerbook](https://boxerbook.com/developers) | Cards/bouts, schedule, national broadcasters/where-to-watch; actual event→country evidence | Official terms effective 3 Nov 2026: free personal/non-commercial point access with attribution, but copying/bulk and commercial redistribution require separate permission. Do not upload source-derived broadcaster data to public feed without approval |
| [Open Boxing](https://www.openboxing.org/api/) | World-title scheduled bouts as supplemental benchmark | Emerging/incomplete; cannot alone cover undercards/PPV, verify maintained endpoint/terms |
| [IPTV-org API](https://github.com/iptv-org/api) | International channel names, alternative names, country, languages, guide source IDs / service identity crosswalks | Useful metadata/discovery, **not** automatic licence for captured EPG programme titles or any stream; do not use IPTV-org stream list to assign B1G local playback |
| [OpenF1](https://openf1.org/docs/) | F1 historical sessions, session timing and cross-check | Official docs: historical free, **live paid**. Existing adapter cannot be represented as a free live F1 result source |
| [CricketData.org](https://cricketdata.org/pricing/) | 100 free/day cricket matches, ODI/T20/Test and internationals | Existing adapter; improve source-scope completeness, Test-day spanning and valid broadcast evidence |
| [OpenLigaDB](https://www.openligadb.de/en/license) | Open community league fixtures and cross-check | Existing adapter; primarily German leagues, ODbL obligations. Not a comprehensive UK football provider |
| Official competition fixtures/calendar exports | Six Nations, F1, UEFA, ATP/WTA, ICC, BBC/ITV/Sky published programme pages where permitted | High-quality truth references; data rights, API availability, scrape prohibitions and source-specific freshness must be checked independently |
| UK/FR multi-guide catalogues | Existing EPG Share, farleyflex, XMLTV France, programme-tv/Télérama candidates; later licensed BE/CH/IE/ES/DE etc | Multi-source identity helps recognise unusual names, but collected program title != permitted public redistribution |
| Historical/lower-cost fixture reference | OpenFootball CC0 or similarly legal reference archives | Useful fallback/historical benchmark; regeneration timestamp does not guarantee underlying fixture freshness |

**Provider admission checklist:** evidence of actually working URL, official documentation and signup, stable scope, payload example dated, rate + daily/monthly reset, coverage per competition/channel, complete pagination, source lineage/independence, permitted local caching, public event/EPG derivative rights, attribution, error/empty semantics, and last verified date. A source is only promoted to production when all relevant checks pass.

## 4. Mandatory source→canonical→B1G transformation pipeline

\`\`\`
LEGALLY PERMITTED SPORTS/API SOURCES          AUTHORISED EPG PROGRAMME SOURCES
 ┌─ fixture, session, bout/card ┐            ┌─ source ID / region / programme ┐
 └──────────────┬───────────────┘            └────────────────┬────────────────┘
                ▼                                           ▼
     Validate response, quota, pages                 Validate bounded XMLTV
     source age & competition scope                  source/channel/programme dates
                ▼                                           ▼
    Canonical event+team+competition                 Canonical source-specific
    sport-specific hierarchy and UTC                 broadcaster ID + edition
                └──────────────────┬────────────────────────┘
                                   ▼
                         Independent evidence join
                  (event ↔ programme ↔ channel/territory)
                                   ▼
                        Licensed field-level policy
                    public event facts and, separately,
                    *approved* EPG display suggestions only
                                   ▼
                    Contract/schema/manifest validation
                 sha256, expiry, per-source freshness, revision
                                   ▼
                           outbound GitHub publish
                             LiveSports-EPG
                                   ▼
                     B1G read-only snapshot client
                      ↓ local account and stream ID
                  manual EPG/user settings + hidden flags
                                   ▼
                      Original B1G guide preserved
                 OPTIONAL quality overlay/gap-fill on TV
                           + verified Sports Today
\`\`\`

**Do not conflate** \`canonical channel\` with a physical local stream, \`programme start\` with \`kickoff\`, \`live coverage\` with game live state, \`UK rights holder\` with an actual showing, or \`source name similarity\` with evidence of identical regional editions.

## 5. Proposed additive EPG supplement contract — target, not implemented

To supplement rather than replace the provider baseline, propose a new optional \`epg_supplements/GB/YYYY-MM-DD\` and \`FR\` asset in \`sli/1.x\`; the literal format below is a **design example only**, not a current API:

\`\`\`json
{
  "schema": "sli.epg-supplements/1",
  "market": "GB",
  "date": "2026-11-14",
  "programmes": [{
    "canonical_channel_id": "gb.sky.sports.main_event",
    "service_variant": "linear",
    "canonical_event_id": "fictional-event-id",
    "programme_start_utc": "2026-11-14T14:30:00Z",
    "programme_end_utc": "2026-11-14T17:30:00Z",
    "event_start_utc": "2026-11-14T15:00:00Z",
    "title_original": "Live Football",
    "title_suggestion": "Example Club A v Example Club B",
    "language": "en-GB",
    "transmission": "live",
    "evidence_level": "verified_programme",
    "evidence_source_ids": ["official-example"],
    "rights_class": "approved_public",
    "recommended_action": "suggest_title_only",
    "expiry_utc": "2026-11-15T02:00:00Z",
    "confidence": "verified",
    "source_captured_at": "2026-11-12T16:00:00Z"
  }]
}
\`\`\`

**Caution:** The hypothetical title and facts above cannot automatically become authorised by renaming or paraphrasing third-party source rows; publication of an original/generic title itself might be prohibited. A real publisher must omit fields without permission, preserve data lineage for *every* output field, reject unknown sources, and avoid publishing internal account/stream identifiers. Canonical ID, territory, edition, specific programme and source evidence must be verified before Android considers displaying a supplement.

Reader behaviour: validate schema and manifest SHA; look up local visible stream by current account; respect manual source override/suppression; match identical canonical service and compatible intervals; apply only allowed field changes, never splice/switch stream or delete original schedule; retain original title and time internally for instant undo. If wrong or stale, drop the supplement without blanking Guide. Test source conflict and full off/on rollback.

## 6. Prioritised release sequence

**Stage A — immediate (operator + security):** token wizard, nonpublishing test, documentation and regression tests (this branch). Do not enable public publishing.

**Stage B — backend correctness:** run full merged-tree tests/CI, packaging installer HAOS verification; source-level metadata rights registry; per-country and competition coverage ledger; date/UTC validation; source age and reliable cache/304.

**Stage C — EPG full product:** licensed UK/FR source selection, canonical service crosswalk, private coverage audit, permission-gated supplementary schema, channel-level quality overlay, B1 local matching and user review. Do not claim success on Guide until both general-TV and sports programmes are tested.

**Stage D — sports full product:** tennis/rugby/cricket/boxing/F1/football competitions with quality/recall by sport; session/card hierarchy; per-event/channel verified and provisional broadcasters explicitly distinct, PPV and OTT.

**Stage E — distribution:** freeze contract fixtures, SHA validation, public rights gate and anonymous URL verification; implement B1 Android reader + cache, 10-TV quota neutrality and manual/hidden projections.

**Stage F — acceptance:** first HAOS install/reboot/restore; a real verified source per priority EPG market and competition; user-approved subscriptions; measured no-wrong-channel hard negatives; negative/partial provider/corrupt data; a rights-cleared public feed; first one TV, then ten. Keep the App labelled experimental until evidence supports promotion.

### Suggested objective gates (proposals, NOT achieved)

- 100% public output fields with explicit permitted rights and source evidence; 0 secrets/stream URLs.
- 0 wrong auto-channel mapping in labelled hard-negative suite, with >=99.5% channel precision on broader independently labelled test inventory and explicit abstention.
- >=95% fixture recall per *supported* declared priority competition (source/licence conditional).
- >=95% of selected source-eligible priority channels with a 24h forward guide and channel-specific 72/168h gap reporting.
- 0 extra upstream sporting API calls caused by each additional B1G TV reading the static feed.
- Original B1G Guide and playable streams still work when SportsLiveInfo unavailable/stale/rights-blocked.
- No public inbound connection to HAOS, and no meaningful degradation to household automations during worst-case EPG parsing.

## 7. Security and technical debt checklist

- GitHub token is stored in HAOS SQLite/backups; mask is visual, not at-rest encryption. Do not copy it into Issues, public feed, commit, screenshots or provider logs.
- Expiration/rotation should create a low-noise notification rather than repeated 401/403 messages. Fine-grained token scoped to public feed repo only; App code repo stays private.
- The Git Data API writer should validate repo/branch metadata and public anonymous manifest after commit. Do not treat GitHub's accepted commit as deployed on CDN.
- Existing GitHub Actions reports have failed with inaccessible logs: investigate runner/tooling and run the complete Python suite at the exact merged revision. Source review is not an executed test.
- Source input URLs and source mirror lineage are untrusted; never pass token-bearing redirects to another host; use bounded content, timeouts and safe XML.
- Config and UI actions are authenticated by Ingress/CSRF, but HAOS admin privilege and external proxy/access assumptions require actual installation testing.
- The current build has no HA persistent notification code, only local diagnostics. Add deduped persistent notification with a least-privilege model once the threat surface is reviewed.
- Consider breaking the 36 kB monolithic Ingress \`server.py\`, large \`providers.py\` and \`taxonomy.py\` into provider/UI/domain modules with contracts without changing behaviour; add tests per extraction.
- Separate no-key source end-user labels and \`Test Connection\` health from permission to republish. Do not mislabel an untested URL as verified because it lacks "(verify)" in a display label.
- Keep your Home Assistant App install repository separate from the now existing public static-data output repo. The public data repo itself cannot be installed as a Home Assistant App.

## Sources and revalidation

- GitHub fine-grained personal access token guide: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens
- GitHub token endpoint permissions: https://docs.github.com/en/rest/authentication/permissions-required-for-fine-grained-personal-access-tokens
- IPTV-org identity/guide directories: https://github.com/iptv-org/api
- Tennis API: https://docs.tennis-api.com/getting-started
- OpenF1: https://openf1.org/docs/
- Boxerbook: https://boxerbook.com/developers ; https://boxerbook.com/terms
- CricketData.org: https://cricketdata.org/pricing/
- Internal requirements: \`docs/MASTER_IMPLEMENTATION_ROADMAP.md\`, \`docs/CHANNEL_IDENTITY_AND_EPG_ALLOCATION_SPEC.md\`, \`docs/FEED_CONTRACT_SLI_V1.md\`, \`docs/FORENSIC_INTEGRATION_AND_CORRECTIONS_2026-11-12.md\`.

**Final assessment:** Operator setup can be greatly simplified, but neither public EPG supplementation nor actual match-to-broadcaster verification is complete. The opportunity with the largest user benefit is *rights-cleared, confidence-scored source-derived EPG supplementary rows while retaining B1G's original programmes*. The opportunity with the largest sports benefit is more complete competition-scoped fixture discovery and independently verified UK/FR event carriage. Implement both as first-class products and require full cross-language contract tests.
