# Forensic quality, integration and acceptance tests

## No invented coverage claims

Before deployment, collect a reproducible, dated benchmark of **actual UK events** and channels. No provider is assumed complete or accurate from marketing claims alone. Record query date/time, source endpoint version, sample geography, competition, event ID, expected field values, discrepancy type, API response health, source licence status.

## Fixture completeness benchmark matrix

- Football: normal Premier League weekend including simultaneous kickoffs, Saturday blackout, midweek Champions League, Europa League Thursday, international qualifiers/friendlies, World Cup/Euros, women's and domestic cup competitions.
- F1: weekend with practice, qualifying, sprint and race; weekend without sprint; winter/off-season; Grand Prix venue/country; race moved or cancelled.
- Tennis: Grand Slam mixed singles and doubles schedule, order of play TBC, "not before", rain delay, ongoing session spanning midnight UK.
- Rugby: union versus league, Six Nations, Premiership, URC, international match.
- Cricket: Test match Day 2/3/4, rain delay, ODI, T20, World Cup and time-zone-shifted overseas cricket.
- Boxing: heavyweight PPV, multiple fights on one card, ring walk estimate versus event broadcast, pay-per-view broadcaster absent from linear guide.
- No-event day, API 200-empty when provider failed, partial page, 429/503 outage, fixture postponement and reschedule.

## Broadcast matching negative and positive corpus

- Match in EPG with both teams, competition, "Live", earlier coverage start -> confirmed.
- Identical teams but programme "Highlights" or "Replay" -> **never confirmed live**.
- Same competition generic programme with multiple simultaneous fixtures -> provisional/unknown.
- Two channels simulcasting one match -> preserve both.
- EPG lists foreign broadcaster but GB request -> omit.
- Rights holder generally owns competition but fixture not on EPG -> unknown, not guessed.
- Channel has studio build-up ending before sporting start -> do not silently claim full live coverage.
- Fixture across BST/GMT transition; fixture UTC day differs from UK local day.
- F1 qualifying and race on different dates; highlights airing next day.
- Specific boxing card on OTT-only PPV absent from XMLTV -> use approved event notice, else unknown.
- Cricket multi-day match with EPG on day 3 -> include on day 3.
- Boxing display: main card vs undercard vs ring walk "approximate", never claim exact from heuristic.

## Proposed measurable metrics (targets are proposals, not achieved)

1. **Event recall by competition**: percentage of benchmark verified scheduled events represented in our feed. Set separate goals for high-priority/secondary sports after source sampling.
2. **Broadcast precision**: fraction of "confirmed GB live channel" outputs supported by programme/official per-event evidence. Strictly prioritise false-positive avoidance; target >= 99% for trusted confirmations in test corpus.
3. **False live positives**: aim zero in repeat/highlights/blackout synthetic cases.
4. **Start-time accuracy**: compare independent official sporting start and coverage start separately; account for "not before" and "estimate" precision.
5. **Coverage flag correctness**: if a source is down, paginated response incomplete, or a sport untested, output must say partial/unknown.
6. **Quotas**: automated smoke tests cannot exceed the provider's documented daily/minute budget.
7. **Freshness**: each source and event has retrieved_at/verified_at; stale items visibly labelled.
8. **Stability**: no provider error crashes whole run, no duplicate cards, no corrupted published snapshot.

## Home Assistant first-run wizard / notification acceptance

Specification: [HOME_ASSISTANT_FIRST_RUN_WIZARD_AND_NOTIFICATIONS.md](HOME_ASSISTANT_FIRST_RUN_WIZARD_AND_NOTIFICATIONS.md).
- [ ] First Open Web UI launches HA Ingress wizard, not an exposed WAN port. Existing normal HA credentials apply; only admins can edit.
- [ ] Individual provider cards include factual signup/doc links and separate Save and Test, with proper masked credentials, no-key, disabled, restricted, quota and authentication statuses.
- [ ] Save A does not overwrite B; interruption/restart/upgrade retains each key; errors/retries do not leak secrets.
- [ ] Separate GitHub repo/branch/path/token Save/Test; correct missing repo/token permission/Pages failure; publication OFF without licence clearance.
- [ ] Schedule Save, GMT/BST handling, 04:00 collection and pre-05:00 intended publish, additional later refreshes and provider-specific quota reset.
- [ ] First-run completion persists, wizard does not auto-open after completion, owner can revisit all settings manually.
- [ ] Partial provider outage shows dashboard status; repeated actionable failure creates a **single stable-ID HA notification** with provider/error/impact/last-good/next-retry/action; recovery resolves without alert spam.
- [ ] Notification API access security reviewed and scoped appropriately; no credentials in HA notifications, public GitHub, UI responses or logs.
- [ ] Concurrent B1G 10-TV JSON downloads result in zero incremental upstream provider quota usage.

## Critical B1 integration EPG and API-scope tests

See [B1 forensic EPG and credentials audit](B1_FORENSIC_EPG_SPORTS_API_SCOPE_AUDIT_2026-11-12.md).
- [ ] Entire Sky Sports/TNT/Premier standard-service current and upcoming windows compared with licensed/official source; generic provider programmes upgraded only with matching channel/time-window and verified better detail.
- [ ] Source SHA / true generation time correctly distinguishes 05:00 morning snapshot from later upstream farleyflex update.
- [ ] 17 stable source aliases, Sky Sports+, TNT5-8, regional and +1 variants tested without unsafe remap; existing provider manual overrides/disabled sources preserved.
- [ ] Valid EPG event omitted by a partial or empty API-Sports free-tier response is not silently deleted.
- [ ] Sports Today 'On now' reflects genuine event state, not solely programme live window or start+heuristic duration.
- [ ] Ten body cards plus optional PPV boxing headline (Mac rule) confirmed or intentional Android difference explicitly documented.
- [ ] Ten TV clients, one public snapshot: no sport provider keys stored on TVs; supplier requests don't increase with clients.
- [ ] HA wizard does not request TMDB/OMDb, VOD artwork, IPTV account/playlist credentials or TheSportsDB public test key.
- [ ] No raw/copy-derived third-party programme descriptions published publicly without documented source licence; denied public EPG uses B1's own source and last-good guide.

## Operational acceptance

- Test without credentials must pass deterministically with sample data.
- Real service integration tests require explicitly configured secret keys; never execute them automatically on untrusted pull requests.
- All output contract fields validated and sample JSON annotated fictional.
- After any provider API change, re-run schema tests and mark source degraded if parser can't validate.
- Legal review gate must pass before outward publishing.
