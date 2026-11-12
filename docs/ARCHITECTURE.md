# Proposed system architecture

> **Legacy exploratory design.** Read [MASTER_IMPLEMENTATION_ROADMAP.md](MASTER_IMPLEMENTATION_ROADMAP.md) for the current architecture: dual independent full **international EPG** + **sports events** pipelines, common source/canonical identities, HAOS mini-PC local App, 10 read-only B1G clients, rights-gated outbound static feed. Legacy 'no mandatory always-on server' and UK-only language below no longer applies.

## Principle

Small, modular, deterministic Python aggregator with cache, defensive fetchers, robust provenance, no paid AI and no mandatory always-on server. Keep private development outputs private.

## Logical pipeline

1. **Event source adapters** (SportsAPI, football-data.org, Jolpica-F1, tennis, cricket, rugby, boxing) fetch scoped date ranges.
2. **Normaliser** maps sport/competition/event/team/location/session and converts all time values into timezone-aware UTC fields.
3. **Deduplicator** groups by source IDs, stable competition IDs, event participants, round, location and schedule time, while guarding against doubleheaders and multi-session F1.
4. **Broadcast importers** parse permitted UK XMLTV and broadcaster event data, keeping coverage times and channel identities separately from fixture times.
5. **Reconciliation engine** matches events to programmes with negative controls, verifiable evidence and per-field source provenance.
6. **Quality engine** checks source completeness, freshness, quota use, conflicts and TV matching confidence.
7. **Publisher** emits immutable/versioned JSON snapshots and a health manifest only where the source licences allow the intended output audience.

## Candidate repository layout (implementation not yet present)

    src/sportsliveinfo/
        models.py
        time_utils.py
        normalise.py
        deduplicate.py
        broadcast_matcher.py
        quota.py
        publisher.py
        adapters/
            sportsapi.py
            football_data.py
            jolpica.py
            tennis.py
            cricket.py
            boxing.py
            rugby.py
            xmltv.py
    tests/
    fixtures/
    data/                    # development snapshots, licence-gated
    .github/workflows/       # add only when code can run
    docs/

## Runtime / dependencies

- Python 3.12+, httpx or requests (timeouts, retries and 429 backoff), defusedxml or safe XML parser, zoneinfo, dataclasses/Pydantic, RapidFuzz only if needed, SQLite for cache/state.
- Keep provider API keys in environment variables/local .env excluded by .gitignore, or GitHub Actions secrets. Do not persist credentials inside the published feed.
- Cache keyed by source/date/competition/scope with ETags if supported. Never assume a 200 response with an empty array equals "no sports today."
- Implement per-provider token budgets and minimum update interval; surface partial schedules rather than silently claiming completeness.
- No speculative runtime scraping, no headless browser unless approved by terms, no LLM in main path.

## Data lifecycle

- Query UTC dates encompassing chosen Europe/London day (a UK day straddles UTC boundaries in BST), not just one UTC date.
- Gather 7-day fixture horizon, accelerate today's updates close to event start; capture both source effective dates and ingestion timestamp.
- Revalidate broadcaster match if fixture is rescheduled, EPG changes, event passes through live/finished, or guide update indicates conflict.
- Dataset envelope includes generated_at, expires_at, source_health, completeness state and per-event verified_at.

## Hosting choices

**Private development:** local CLI + private GitHub repository + manual/scheduled GitHub Actions within private Free plan quota; store private artifacts or restricted branch data, no public Pages.
**After rights clearance:** possible public static JSON via a public non-sensitive repository and GitHub Pages, or a free-tier external static host. Verify traffic/usage terms and avoid leaking restricted data.
**Truly live status:** scheduled static snapshots alone cannot guarantee real-time state. Use status freshness indicators; add an always-on server only if the requirement justifies the costs.

## Data quality first

Maintain logs for provider availability, fixtures collected per league/day, page counts, expected versus actual coverage, duplicate collapses, start-time changes, TV match ambiguity, missing fields and licensing gates. Each event is explainable.
