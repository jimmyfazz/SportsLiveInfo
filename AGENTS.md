# AGENTS.md — implementation guidance

Read README.md and all docs before major changes; start with docs/DELIVERY_PLAN.md and **docs/HOME_ASSISTANT_PROXMOX_HOSTING.md** for current deployment requirements: existing Proxmox/Home Assistant host, outbound-only GitHub publishing, 10 B1G TVs, per-provider quota isolation.

**Critical architecture:** The collector is one standalone Python engine. Package it as a **Home Assistant OS App** when HAOS VM is confirmed, or independent Proxmox LXC/container; do not put collector, scraper, EPG parser, rate-limiter or GitHub publisher inside a Home Assistant custom integration. Thin HA health sensor integration is optional. No TV calls sporting-provider APIs; no public home-network ingress.

## Non-negotiable requirements

1. Zero recurring subscription cost for the initial private prototype. Avoid paid data services and language-model inference. Provider adapters must be pluggable; never tie the whole app to one provider.
2. Sports event identity and UK television broadcast identity are **separate records**. Never infer a channel merely from general rights-holder announcements.
3. Persist UTC instants; present dates/times in Europe/London, handling BST/GMT and midnight. Distinguish coverage start from actual sport start.
4. Never invent missing venue, ring walk, tennis order-of-play, channel, PPV status or live status. Represent unknown explicitly.
5. Preserve source URL/id, retrieved_at, last-confirmed-at, source priority, licence restriction, freshness and matching evidence.
6. Fail gracefully if providers are inaccessible, API quota is exhausted, or schedules disagree. Stale data is visibly labelled; no silent fabricated fallbacks.
7. Do not scrape sites that prohibit automation/republishing, circumvent authentication, defeat bot controls or publish restricted raw data. Free access is NOT a redistribution licence; private development is not a licence exemption.
8. Keep secrets in local environment variables and GitHub Actions secrets only; mask logs, never ship keys to clients.
9. Write deterministic, unit-tested adapters and normalisation/matching logic. Prefer Python standard library, httpx/requests, XML parser, SQLite, and RapidFuzz if needed.
10. New scope/fixes must update tests, docs/SOURCE_REGISTRY.md if sources change, and docs/DELIVERY_PLAN.md. Separate research-verified facts from implementation-tested conclusions.
11. No unapproved publication. GitHub Free + private repo supports Actions within account allowance but not private GitHub Pages; deployment choice remains open.
12. B1 integration is optional and separate; B1's existing EPG and channels must be reused only with authorised, user-provided data and without disrupting playback.

## First engineering increment

- Build canonical Pydantic or dataclass event/broadcast models (see DATA_CONTRACT).
- Implement fixture adapters for football-data.org and Jolpica-F1; SportsAPI only when a test key is configured and terms reviewed.
- XMLTV parser + time-overlap/team-alias matching, including negative detection for repeats/highlights.
- CLI: sportsliveinfo collect --date YYYY-MM-DD --tz Europe/London --output data/YYYY-MM-DD.json
- Deterministic tests with committed synthetic fixtures; no live web calls in CI.
- Provider health/quota logs and licence gate before any publishing.
- Produce a real limited-sample accuracy report; do not declare coverage percentages by assumption.

**State as at 2026-11-12:** Research documents only. Do not claim the application or live API is implemented.
