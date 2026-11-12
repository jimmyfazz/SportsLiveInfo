# SportsLiveInfo

**Private research and development repository — 12 November 2026**

SportsLiveInfo is a planned **zero-subscription-cost UK sports-fixture and television-broadcast intelligence service**. It answers: **What sport is taking place on a specified date, who is playing, when and where does it take place, and which UK channel or platform is showing it live?**

The objective is a reliable, normalised, explainable sports calendar, **not** an IPTV/streaming service, live score platform, betting product, or LLM-dependent system.

## Scope

- Football: Premier League, Champions League, Europa League, World Cup, international matches and other major domestic/European competitions.
- Formula One: Grand Prix, circuit/country and practice/qualifying/sprint/race sessions.
- Tennis, rugby union and league, cricket, boxing (including heavyweight title events and PPV), plus future expansion.
- UK local times, named competitors/teams, location, event status, broadcaster(s), coverage-start versus sporting-start, PPV versus subscription versus free-to-air, provenance and freshness.
- Views for today, tomorrow, the next seven days, by sport, by broadcaster, and live now **only where live status is verified**.
- Future optional integration with the B1 Android TV application's sports rail and existing channel/EPG matching.

## Core decision

Use **independent fixture adapters + independent UK EPG/broadcaster adapters + deterministic normalisation and reconciliation**, producing one stable JSON contract. No paid APIs or paid LLMs are prerequisites. Never infer that a rights-holder shows every match; never fabricate a missing UK TV channel.

## Documentation index

1. [Research findings and feasibility](docs/RESEARCH_FINDINGS_2026-11-12.md)
2. [Free API and source registry](docs/SOURCE_REGISTRY.md)
3. [UK EPG and broadcast matching](docs/UK_BROADCAST_MATCHING.md)
4. [Architecture and operational design](docs/ARCHITECTURE.md)
5. [Canonical data/API contract](docs/DATA_CONTRACT.md)
6. [Licensing, sourcing and £0 hosting](docs/LICENSING_AND_HOSTING.md)
7. [Implementation delivery plan](docs/DELIVERY_PLAN.md)
8. [Forensic test and acceptance matrix](docs/TEST_PLAN.md)
9. [Optional B1 Android integration](docs/B1_INTEGRATION.md)
10. **[PRIMARY: Home Assistant mini PC directly installed — deployment decision](docs/HOME_ASSISTANT_BARE_METAL_PRIMARY.md)**
11. [ALTERNATIVE ONLY: Home Assistant under Proxmox / LXC](docs/HOME_ASSISTANT_PROXMOX_HOSTING.md)
12. **[MANDATORY: HA first-run setup wizard, individual API saves, GitHub schedule and non-intrusive notifications](docs/HOME_ASSISTANT_FIRST_RUN_WIZARD_AND_NOTIFICATIONS.md)**
13. [Instructions for coding agents](AGENTS.md)

## Project status

**Research documented; production aggregator NOT yet implemented.** No API key has been created, no provider accuracy benchmark has yet been run, no JSON feed has been deployed, and no broadcaster matching has been demonstrated end-to-end. Provider limits and terms are subject to change.

## Deployment selected (12 November 2026)

**Primary host: the owner's always-on personal home mini PC running Home Assistant directly on hardware (not Proxmox).** Assuming its installation type is Home Assistant OS, build SportsLiveInfo as a private local Home Assistant App, an independently managed container. All ten personal B1G TVs will read the **same versioned JSON snapshot** from a proposed separate GitHub public feed, never query sporting-provider APIs themselves. The collector publishes over outbound HTTPS only; **no incoming access to the home computer or network**. Actual Home Assistant OS/App support must be confirmed before installation. See [primary deployment specification](docs/HOME_ASSISTANT_BARE_METAL_PRIMARY.md). Public distribution of provider-derived data is subject to a source-by-source licence gate; no public feed exists yet.

## Priority

Build the smallest legal, measurable vertical slice: football/F1 fixtures + canonical contract + local EPG XMLTV import + provenance-aware channel match + tests. Then expand sports and deploy scheduled collection.

## Privacy / distribution

This GitHub repository is currently private by choice. Keep it private during development. Private status does **not** waive provider licences; do not publish scraped broadcast datasets or credentials. GitHub Pages is not available from a private repository on GitHub Free; consult [hosting notes](docs/LICENSING_AND_HOSTING.md).

External URLs, product limits and licence conditions below were checked or identified for verification on **12 November 2026**. They are research leads, not contractual warranties.
