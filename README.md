# SportsLiveInfo

**Private project specification and development programme — 12 November 2026**  
**Current status (12 Nov 2026):** First installable **Home Assistant OS App v0.1.0** source is now under [`sportsliveinfo/`](sportsliveinfo/) with `repository.yaml`, Ingress setup, SQLite, bounded UK/FR EPG imports and F1/football provider adapters. Seven offline tests and a local first-run HTTP smoke test passed; **not yet installed or tested on Home Assistant OS**, and not yet a complete international EPG/sport provider or B1G client. No public-data feed has been authorised or deployed.

SportsLiveInfo is a **self-hosted, no-subscription-cost sports and international electronic programme guide (EPG) intelligence application**, planned as a Home Assistant OS App on the owner's always-on home mini PC.

## Two equally important products

**Product E — Comprehensive international EPG:** UK (Sky Sports, TNT, Premier, BBC/ITV and other channels), France (general and sport channels), and further countries/channels discovered from the owner's own B1G subscription inventory. Import permitted sources and provider-native guide schedules; validate coverage, names and intervals; unify canonical broadcaster identity; improve generic programme descriptions where accurately verified. The full B1G Guide needs comprehensive multi-day programme data, **not just information for the Sports Today rail**.

**Product S — Comprehensive sports event intelligence:** football (domestic, European, internationals, women’s); F1 and other motorsport; tennis; rugby union and league; cricket; boxing (including PPV); and expandable sports including darts, snooker, golf, MMA, basketball, NFL, cycling, etc. Collect participants, competition, venue/circuit, precise/estimated UK time, event status and **independently verified actual broadcaster**. B1G shows 10 Home sports cards with optional distinct PPV headline/11th card as relevant.

Both products have independent provider coverage, completeness benchmarks and acceptance gates. A programme airing now does not prove an event is live; a broadcaster's league rights do not prove a specific match is available on its channel.

## Owner-confirmed operating topology

1. **Home Assistant** on the personal-home mini PC collects sport and EPG data with API keys configured **once** in a first-run Home Assistant Ingress wizard. Configure authorised sources, a scheduler, optional local safe inventory import and quiet diagnostic notifications.
2. The collector maintains private local cache/state and publishes **only rights-cleared** versioned JSON over an **outbound HTTPS connection** to a proposed separate public static GitHub feed. The code repository **stays private**. A feed repo has **not** been created; publishing remains disabled until source terms and owner approval are established.
3. **Ten B1G Android televisions read the same published feed anonymously over HTTPS.** TVs do not call sports API providers, upload channel lists, write to GitHub or hold GitHub tokens.
4. Every TV locally matches canonical TV services to its **actual** IPTV playlist, respects hidden categories/channels, manual EPG mapping and local stream access, and retains existing EPG as a fallback.
5. **No incoming internet access to Home Assistant, no router port forwarding, no public Home Assistant address.** Public GitHub is only a distribution channel for authorised static files.

**Excluded:** central TMDB/OMDb, movie/series metadata, posters/hero artwork, IPTV stream URLs, playback proxy, subscription credentials or per-TV hidden-channel uploads. TMDB and OMDb remain optional local B1G integrations.

## Authoritative build documents — Codex and Claude start here

| Order | Document | Purpose |
|---|---|---|
| 1 | **[Master implementation roadmap](docs/MASTER_IMPLEMENTATION_ROADMAP.md)** | Phased implementation, two-product scope, architecture decisions, exit gates |
| 2 | **[Forensic audit and risk register](docs/AUDIT_2026-11-12_FORENSIC_SPEC_AND_ARCHITECTURE.md)** | 34 findings with priorities, corrections and required proof |
| 3 | **[International EPG and sporting sources](docs/INTERNATIONAL_EPG_AND_SPORTS_SOURCE_EXPANSION.md)** | Regions, guides, sports, official references, quotas and rights |
| 4 | **[Feed contracts and publishing](docs/FEED_CONTRACTS_AND_PUBLICATION.md)** | Canonical JSON, service identities, licence gates, versioning, manifests and last-good |
| 5 | **[Quality and security acceptance](docs/QUALITY_SECURITY_AND_ACCEPTANCE.md)** | Test suite, metrics, HAOS stability, privacy, resilience and release conditions |
| 6 | **[Codex and Claude collaboration](docs/CODEX_CLAUDE_COLLABORATION.md)** | Parallel branches/worktrees, task ownership, PR order and terminal prompts |
| 7 | **[PR-sized work-package backlog](docs/WORK_PACKAGE_BACKLOG.md)** | Concrete CORE/EPG/SPORT/HA/PUB/B1 tasks with owners, dependencies and acceptance tests |
| 8 | **[Implementation status and agent handover](docs/IMPLEMENTATION_PROGRESS.md)** | Honest baseline and required test/PR receipts |
| 9 | [Agent instructions](AGENTS.md) | Non-negotiable development rules and read order |

**Detailed supporting specifications:**
- [Existing B1G EPG/API forensic audit](docs/B1_FORENSIC_EPG_SPORTS_API_SCOPE_AUDIT_2026-11-12.md) and [B1 integration](docs/B1_INTEGRATION.md)
- [Universal channel identity and EPG allocation](docs/CHANNEL_IDENTITY_AND_EPG_ALLOCATION_SPEC.md)
- [Subscription-driven UK/France/world EPG](docs/SUBSCRIPTION_DRIVEN_MULTIREGION_EPG.md)
- [B1G read-only/inventory policy](docs/B1G_READ_ONLY_FEED_AND_INVENTORY_POLICY.md)
- [Codex local subscription inventory handover](docs/CODEX_B1G_SUBSCRIPTION_INVENTORY_HANDOVER.md)
- [Primary bare-metal Home Assistant host](docs/HOME_ASSISTANT_BARE_METAL_PRIMARY.md)
- [Mandatory first-run wizard, API entry, scheduler and notifications](docs/HOME_ASSISTANT_FIRST_RUN_WIZARD_AND_NOTIFICATIONS.md)
- [Source registry](docs/SOURCE_REGISTRY.md), [licensing and hosting](docs/LICENSING_AND_HOSTING.md), [original research](docs/RESEARCH_FINDINGS_2026-11-12.md)

**Historical/reference documents:** `docs/ARCHITECTURE.md`, `docs/DATA_CONTRACT.md`, `docs/DELIVERY_PLAN.md`, `docs/TEST_PLAN.md`, `docs/UK_BROADCAST_MATCHING.md`, `docs/HOME_ASSISTANT_PROXMOX_HOSTING.md`. Where older docs say UK-only, optional B1 consumption, identical generic/start times or prioritize fixtures over EPG, the master roadmap and confirmed owner requirements take precedence.

## Recommended first engineering milestones

- **P0:** Python package skeleton, tests and versioned canonical schemas; freeze contract and agree interface between agents.
- **P1E (Claude):** bounded XMLTV, source-specific channel identities and UK+France EPG pipeline with source coverage tests.
- **P1S (Codex):** canonical sports/event models and free-fixture providers with competition and source-completeness tests.
- **P2:** independently expand both EPG regions and priority sports, benchmark against actual source/official data within permitted licences.
- **P3–P4:** event/programme/broadcaster verification, first-run HAOS App wizard, scheduler, SQLite last-good, quiet notifications, rights gate.
- **P5–P6:** authorised GitHub publisher, B1 read-only feed client, one TV then ten, security/HA resource/EPG+sport acceptance report.
- **P7:** measured international and new-sport expansion without paid API dependency.

**Progress labels matter:** researched ≠ coded ≠ tested ≠ source-licence-approved ≠ deployed. No account setup or key is assumed completed, no blanket worldwide accuracy claim, and no public EPG redistribution without appropriate permission.

The source plan is free-first, but supplier limits and programme-data rights are subject to change. Maintain dated verification; prefer false-positive avoidance over blindly allocating the wrong EPG or sport channel.
