# AGENTS.md — controlling instructions for Codex, Claude and other development agents

## READ BEFORE CODE

1. [Master implementation roadmap](docs/MASTER_IMPLEMENTATION_ROADMAP.md) — **normative phases and dual-product scope**.
2. [Forensic audit](docs/AUDIT_2026-11-12_FORENSIC_SPEC_AND_ARCHITECTURE.md) — prioritized defects and unverified assumptions.
3. [International EPG and sports sources](docs/INTERNATIONAL_EPG_AND_SPORTS_SOURCE_EXPANSION.md) — factual/terms checks.
4. [Feed contract/licence gate](docs/FEED_CONTRACTS_AND_PUBLICATION.md), [QA/security](docs/QUALITY_SECURITY_AND_ACCEPTANCE.md).
5. [Codex and Claude collaboration](docs/CODEX_CLAUDE_COLLABORATION.md) — **exclusive worktrees and file owners**.
   [PR-sized task backlog](docs/WORK_PACKAGE_BACKLOG.md) and [implementation progress/handover](docs/IMPLEMENTATION_PROGRESS.md) are mandatory operating records.
6. [Primary HAOS architecture](docs/HOME_ASSISTANT_BARE_METAL_PRIMARY.md), [wizard and notification spec](docs/HOME_ASSISTANT_FIRST_RUN_WIZARD_AND_NOTIFICATIONS.md).
7. [B1 channel identity](docs/CHANNEL_IDENTITY_AND_EPG_ALLOCATION_SPEC.md), [subscription regions](docs/SUBSCRIPTION_DRIVEN_MULTIREGION_EPG.md), [B1 read-only](docs/B1G_READ_ONLY_FEED_AND_INVENTORY_POLICY.md).

Later owner decisions override historical UK-only or optional-B1 language in older files. **Products E (international EPG) and S (multi-sport events) are independently comprehensive, equally mandatory deliverables.** A correct 10-card rail does not complete the EPG; a good EPG does not complete events.

## Locked decisions

- Private `jimmyfazz/SportsLiveInfo` source repo; deploy on owner's continuously powered personal mini PC with **Home Assistant OS expected directly on hardware** (verify installation type/CPU architecture). Proxmox is an alternative only.
- One HAOS App hosts standalone Python collection engines, scheduler, cache, permission checks, health and **Ingress-only admin** setup. No core integration required for heavy collection, no incoming WAN port, no remote Home Assistant exposure. HA notifications quiet/deduped; secure status dashboard.
- User registers free permitted sport APIs **once** in App wizard with per-provider separate masked Save and Test; URL/doc/terms shown accurately; no-key/restricted/nonimplemented suppliers distinguished. Configure EPG source priorities, GitHub destination and source-aware GMT/BST scheduler.
- Central output may be published via **outbound HTTPS only** to a distinct public static GitHub feed **only once public redistribution rights and owner approval are established**. Source private repo stays private. Source/rights/field gate defaults to deny.
- All ten B1 Android TVs are **read-only consumers**. No TV API registrations, Github writes, public or home inbound connections, private account uploads or secret exposure. Each B1 client locally maps stable canonical broadcast service + EPG source to its own current account/stream, honouring hidden channel/category, manual mapping, suppression, time shift and service region. No guessed stream.
- **Never centralise TMDB, OMDb, VOD metadata, posters, hero images or other per-title artwork.** Those B1G APIs/caches stay on TV. Do not introduce any TV artwork proxy or cloud calls to HAOS.

## Source and accuracy laws

- Free API is not necessarily licensed for public data redistribution; repository licence is not ownership of programme text. No unlawful scraping or publication. No provider image republishing without rights.
- Sport fixture, EPG programme, canonical broadcaster, per-device stream, and event→broadcast relation are distinct models. Confidence must be earned by exact IDs, verified aliases, region/variant/time and independent evidence, not just matching names, rights ownership or airing programme.
- Keep both **EPG-only** and **fixture-only** candidates with explicit uncertainty. A partial/empty free-fixture API response must not remove valid EPG event. A missing EPG programme must not make fixture disappear.
- Track source lineage: farleyflex may mirror iptv-org/mytelly; two copies are not two independent confirmations.
- Explicitly handle UK/Paris daylight savings, midnight, long cricket matches, tennis not-before, F1 race sessions, boxing PPV card vs main event vs ring walk. Unknown times/channels/status always explicit.
- Quota and rate budgets per account/day/month and provider timezone. SportsAPI docs conflict 100/1000 daily; plan conservatively pending authenticated verification. No per-TV upstream calls. No LLM in runtime path, no paid API by default.
- Source freshness is **not** actual EPG accuracy. Farleyflex workflow scheduled 06:00 UTC may commit hours late; use actual source SHA/version and programme horizon, with morning last-good refresh and later checks.
- Non-sensitive synthetic/contract test fixtures only in Git. Never upload actual IPTV account inventory, stream URLs, access tokens, private EPG URLs, home network addresses or playback history.
- Avoid heavy concurrent XMLTV parsing on HAOS; bounded decompression, streaming XML, timeouts and resource monitoring so household lights/heating/automations continue normally.

## Work organisation

- Codex: leads package, core contracts, sports adapters, scheduler, persistence, public-licence publisher.
- Claude: leads international EPG source ingestion/identity/coverage, Ingress UI, eventually B1 Android read-only client.
- Schemas/JSON golden fixtures freeze first, reciprocal review mandatory. Use **separate Git worktrees, dedicated branches, PRs and tests**; no concurrent edits of shared file. No speculative merge claims. Distinct parallel EPG and sports work should begin immediately after P0.
- Each task must report source-code or documentation baseline, actual tests, coverage measurements, licences, open blockers and rollback. Update `docs/IMPLEMENTATION_PROGRESS.md` when engineering starts.
- Enforce hard-negative mapping/rights tests; no fake accomplishments. Supplier quota/terms date and source accuracy must be reverified before production.
- Build unit tests without provider keys first; only keyed smoke tests with owner-supplied secrets and permission gate. Public feed repo must not be created or published silently.

## Initial delivery packages

1. P0 scaffolding, versioned schemas, synthetic EPG+sport fixtures and green CI.
2. In parallel: Claude P1E international source/parser/identity and Codex P1S sporting fixtures/events.
3. Quota/coverage/source-drift and evidentiary linking; accurate generic-to-detailed EPG overlay.
4. HAOS Ingress first-run wizard, source+country coverage, GitHub publishing credentials/test, scheduler and quiet Home Assistant errors.
5. Outbound-only rights-approved asset/manifest delivery, versioned B1 consumer, local channel match with hidden/account state, ten-TV validation.
6. Independent objective acceptance on EPG completeness and sport event accuracy.

**Current development status (12 Nov 2026):** research and detailed specification only. Do not report these packages implemented until actual code, tests and device results exist.
