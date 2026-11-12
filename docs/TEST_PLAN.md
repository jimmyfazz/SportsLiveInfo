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

## Operational acceptance

- Test without credentials must pass deterministically with sample data.
- Real service integration tests require explicitly configured secret keys; never execute them automatically on untrusted pull requests.
- All output contract fields validated and sample JSON annotated fictional.
- After any provider API change, re-run schema tests and mark source degraded if parser can't validate.
- Legal review gate must pass before outward publishing.
