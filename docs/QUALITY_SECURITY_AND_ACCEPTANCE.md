# Quality engineering, security, operational resilience and objective acceptance

> **Current documentation context — reviewed 12 November 2026.** This is the release acceptance plan. Existing flat tests cover part of the design; the current full suite is not green. Do not treat target test directories, metrics or privacy assertions as deployed proof.
> **Repository roles:** [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is the public App source and installation repository; [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is PUBLIC daily data only. [Current status and evidence](CURRENT_STATUS.md).

**Mandatory QA plan 1.0 — 12 Nov 2026.** Both EPG and sports engine require independent demonstrable functionality before 'complete'. End-to-end launch thresholds below remain unmeasured. Offline tests cover a subset of invariants; current offline test results and transport limits are recorded in [CURRENT_STATUS.md](CURRENT_STATUS.md).

## 1. Objective definitions of completeness

- **Supported channel scope:** country + canonical service + region/edition + source/rights eligibility + dates + user-important priority. Only services that pass selection/licence tests count as `supported`; all excluded services still appear in an exceptions report with reason, never silently vanish.
- **EPG channel coverage:** for each supported service, count continuous valid programme time in next 24/72/168h, local timezone, valid title/detail, verified service identity, freshness and licensing. A service with only today's first two hours is NOT complete.
- **Event coverage:** for each declared priority competition/sport/date, independently compare source events with dated official competition calendar/reference, count named participants, scheduled time/precision, venue/session and status.
- **Live TV accuracy:** test specific event→programme→canonical service per territory, time overlap and transmission type; never award "confirmed" for rights ownership alone.
- **Consumer mapping:** per-TV current-account mapping precision, source identity, hidden channel/category handling, rejected ambiguous and manually overridden cases.
- **Accuracy vs completeness:** report precision and recall separately with abstention, unknown, partial-coverage and unavailable-source statuses. No unmeasured "100%" claim.

## 2. Target test-suite layout (current tests are flat `tests/test_*.py`)

- `tests/unit`: JSON schema, alias identity, source namespace, interval coverage, quota arithmetic, time offsets, sport hierarchy, EPG quality overlay, venue/participants normalization.
- `tests/contract`: provider payload fixtures pinned with version/date (synthetic or permitted redacted samples), response pagination, malformed content, 429, missing keys, spec changed, empty response, profile/unavailable.
- `tests/integration`: multi-source ingest→store→link→publish staged assets, event-to-EPG negative, source lineage, individual source outage, licence gate, restart.
- `tests/ui`: first-run HA Ingress supplier Save/Test, GitHub repo+token Save/Test, schedule Save/Next Run, resume after power failure, finished wizard no reappearance, notifications.
- `tests/android` in B1: golden JSON parser, name/source matching, manual user override, account switch, visible source projection, disabled source and 10/11 rail.
- `tests/performance`: 27k–50k local channels indexed resolver, large compressed XMLTV (bounded bytes and expanded size), boot-to-first-usable-feed, low-memory HAOS and parallel 10 client reads.
- `tests/security`: repo/asset secret scanning, public publishing denies restricted fields, CSRF/Ingress, SSRF source URL denylist, path traversal, XML entity/bomb protection, exhausted storage.
- `tests/system`: HAOS mini PC install/restore, loss of WAN, git publish delay, B1 devices Fire TV/Shield and focus/guide/playback.

## 3. EPG must-pass scenarios

1. UK Sky Sports Main Event/PL/F1/NFL/news and TNT 1–4, Premier Sports 1–2; France 2/3, TF1, CANAL+ main/sport/sport360, beIN Sports numbered, RMC Sport where source/rights and subscription permit. Include regional BBC and Belgian/Swiss/French variants.
2. Correct ID even with `UK | SKY SPORTS MAIN EVENT FHD`; but reject `Sky News`↔`Sky Sports News`, `BBC One Scotland`↔national, `Sky Sports+`↔standard, `Canal Sport 360`↔Canal+ Sport, `beIN 1`↔2 and +1↔regular.
3. Different EPG source IDs for same canonical channel; same ID reused across unrelated feeds; no accidental wrong match.
4. Provider generic `Live Football` and verified source detailed club match; make reversible title-specific overlay when event/channel/time verified; preserve baseline interval and source provenance. Conflicting broadcaster programmes must not overwrite.
5. French UTC+1/+2 vs UK UTC+0/+1 around differing DST change weekends; explicit offset in XMLTV retained.
6. Completely hidden category/channel, hidden on one TV but visible on another, manual source change, explicit mapping suppression, multiple IPTV accounts and changed lineup.
7. Source after generation commit but guide horizon not advanced; stale data distinguished from successful collection.
8. Corrupt compressed feed, oversized expansion, duplicate programmes, negative or overlapping intervals, no programmes, unknown language; source quarantined and last-good shown.

## 4. Sports must-pass scenarios

1. Football EPL/UCL/Europa/World Cup/international and other priority domestic competitions, including no-match date, late postponement, fixture swapped/changed time and a competition omitted by one free provider.
2. F1 race weekend venue/circuit/country FP/quali/sprint/race, overseas UK-time conversion and race vs highlights confusion. Motorsport series may have race/stage rather than fixture endpoint; do not fetch fixtures for race-only sport.
3. Tennis match time TBC/not-before; multiple court matches; grand slam session not mistaken for match.
4. Boxing PPV card and fighter pair, headline vs undercard, coverage vs first bout vs estimated main-event walk; stream might be OTT without XMLTV.
5. Cricket five-day match visible on all relevant UK dates, rain/session and timezone, ODI/T20 tournaments.
6. Rugby league vs union, named teams/sport competition and local UK/FR broadcast.
7. Two API providers agreeing but sharing same upstream: never count as independent confidence; conflicting official calendar marked reviewed.
8. EPG detects fixture absent from a limited free API: preserve EPG-only candidate, never delete as non-existent or incorrectly confirm as live.
9. Empty result with successful 200 vs missing pages/429/5xx: source completeness flags and negative evidence handled correctly.

## 5. Licence and personal-data protection

- Per-source `allowed_usage` matrix and terms date; **public feed default deny**. Public means anyone can fetch even though the app is for 10 family TVs. No silent unauthorised copying or republishing EPG programme text.
- Live provider keys stored only on HAOS and never displayed after save; GitHub publishing token scoped to one feed repo, no B1 device writes. Secrets must be redacted even in URL query strings, HTTP logs, debug dumps and HA notifications.
- Source registry/config user edits must prevent SSRF via internal IPs, loopback, metadata endpoints and redirect chaining; use explicit trusted HTTPS allowlist for automatic source fetch and admin approvals for others.
- XML parser prohibits external entities and document type resolution; reject decompression bombs, malformed Unicode, oversize response or provider returning HTML login page.
- Ingress only via Home Assistant authentication; no open host port or WAN port forward. Mutating endpoints require admin, CSRF protection and proper origin handling.
- Supervisor `/data/options.json` may contain plaintext credentials at rest; HA backup may include them. Do not claim masked input field = encrypted disk. Document token rotation and restore.
- Service should not access other HA instance configs, cameras, property devices, home-user data or hardware. Home Assistant household automations must continue normally if collector crashes.
- B1G optional owner-initiated **sanitised** catalogue export contains only safe channel hints and no stream URLs, credentials, provider server, viewing history or direct account identities; never auto-send to GitHub.
- Protect app Python dependencies with pinned hashes/known version and security audit; no `pip install` at app runtime.

## 6. Operations, quotas and incident policy

- Two separate scheduler lanes: EPG feed/version checks and sports provider calls, bounded resource/slot quotas so large French XMLTV never blocks 05:00 sports snapshot.
- All timestamps stored UTC; UK local-time scheduling in Europe/London with BST and overnight handling; reset provider quotas in provider's designated timezone (frequently UTC) separately.
- Provider per-key daily+monthly budget: planned, spent, remaining, reserve; per minute rate, request page count, 429 retry-after, breaker cooldown. Do not use '10 TVs × 11 cards' as quota estimation.
- Failures are classified transient, prolonged or owner-action required. Quiet dashboard for occasional 503; one deduped Home Assistant persistent notification for invalid API key, exhausted daily quota affecting scope, expired GitHub token, persistent unpublishable feed or corrupt storage; include last-good, B1 impact, next retry and action. Never send push by default.
- Idempotent jobs, nonoverlap, persisted progress and bounded catch-up after HAOS reboot. No backlog storm. Last-good feed retained in on-disk state and on GitHub until validated replacement.
- Run EPG source checks after *real upstream revision*, not hard-coded assumptions about source's scheduled GitHub Actions runs.
- Health telemetry per sports/EPG separately; per-country/competition/priority, false positive audit and source lineage.
- The PUBLIC daily-feed repo `jimmyfazz/LiveSports-EPG` exists; live publication stays disabled until owner authorization and source-rights gates. The public App source repository is separate. No new public SportsLiveInfo/HAOS endpoint is required.

## 7. Proposed acceptance metrics (targets, not achieved)

| Dimension | Proposed launch threshold or rule |
|---|---|
| Public export permission | Every exported field has recorded rights/permission; 0 unknown/restricted programme data |
| Wrong auto EPG channel in hard negative corpus | 0 |
| Verified channel identity precision | >=99.5% on held-out manually labelled test sample, report abstention and per-region n |
| Event-to-TV confirmed precision | >=99.5%, independent event/EPG verification, report sample size |
| High-priority competition recall | >=95% of independent verified fixtures *per supported competition* with documented exceptions |
| EPG 24h schedule availability | >=95% of source-eligible *priority visible services*, report 72/168h separately |
| Incorrect UK/FR DST conversions in deterministic corpus | 0 |
| Wrong sporting live vs TV programme status in hard negatives | 0 |
| Provider API calls from B1G in central mode | 0 |
| GitHub writes from B1G | 0 |
| Absent source/wrong page/invalid JSON | Degraded with last-good, no false 'no sport today' or erased guide |
| Secrets in public feed or logs | 0 |
| 10 B1G TV users | Different hidden settings/streams, same cached rights-cleared common assets, no extra provider calls |
| HAOS household performance | No material unresponsiveness; quantify baseline before assigning hard limits |

**Success is not an arbitrary percentage alone.** Publish denominators, dated reference list, coverage/unknown rate and unhandled rights. If legal limitations prevent publication of most EPG data, record this as a blocked requirement and preserve direct B1 source fallback rather than claiming success.

## 8. Test data and reporting template

A dated run report must include: tested HEAD SHA and environment; provider source and terms status; source requests/budget; country/channel counts; competition/date sample; EPG 0/24/72/168h coverage; per-channel false-positive mapping; source time difference; event recall/precision; public output permission; incident/notification results; Android runtime build/pass; HA memory/CPU disk impact; rollback test; open deviations. Save reports in `docs/reports/YYYY-MM-DD-*.md` only if they contain no provider payload secrets or sensitive account inventory.

## 9. Zero-downtime recovery and stop rules

1. First local dry-run, no public publishing.
2. If published feed fails validation or licences unknown, **do not** upload. Keep previous public last-good and alert owner.
3. If a new EPG has wrong channel identity or fixture-to-broadcast link, quarantine it, don't retune TV; provide a minimal correction switch.
4. If HAOS App CPU/memory threatens household automation responsiveness, pause heavy feeds and retain old data.
5. If two agents change the same interface without review, block merge until contract reconciliation tests pass.
6. B1G always has provider-native EPG and local view cache as fallback; central source outage cannot make the Guide blank.
