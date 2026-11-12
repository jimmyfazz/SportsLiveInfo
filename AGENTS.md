# AGENTS.md — implementation guidance

Read README.md and all docs before major changes; start with docs/DELIVERY_PLAN.md and **docs/HOME_ASSISTANT_BARE_METAL_PRIMARY.md**. **The owner selected an always-on personal-home mini PC with Home Assistant installed directly to the hardware, without Proxmox.** Treat Proxmox, Synology and office Windows/Linux machines only as fallbacks. Confirm Home Assistant OS is the installation type before implementing the App package. Outbound-only GitHub publishing, 10 B1G TVs and per-provider quota isolation are required.

**Critical architecture:** The collector is one standalone Python engine. **Primary packaging: Home Assistant OS local App on the physical personal-home mini PC**, if HAOS confirmed. Do not put collector, scraper, EPG parser, rate-limiter or GitHub publisher inside a Home Assistant Core custom integration. Thin HA health sensors are optional. No TV calls sporting-provider APIs; no public home-network ingress. Private repository stays private, proposed separate public feed must be rights-cleared before publication.

## Required Home Assistant UI and notifications

**Mandatory:** Read [docs/HOME_ASSISTANT_FIRST_RUN_WIZARD_AND_NOTIFICATIONS.md](docs/HOME_ASSISTANT_FIRST_RUN_WIZARD_AND_NOTIFICATIONS.md) before App/UI implementation. Build **HA Ingress** first-run wizard (not a literal OS splash): individual supplier cards with correct signup URLs, masked API key, per-source **Save** and **Test Connection**; providers without keys clearly labelled; non-publishable sources gated; separate GitHub feed-repo/token Save/Test; GMT/BST-aware fetch and publication scheduler Save; wizard auto-opens only on first run, resumable, manually reopened later. Operational dashboard + quiet Home Assistant persistent notifications with dedup, comprehensive remediation, severity/cooldown and redaction. Treat the wizard, scheduling, and HA notifications as *acceptance-critical*, not optional design polish. HA Core API notification access via `homeassistant_api: true` is powerful; security-review or use a least-privilege companion integration. Never allow UI form field changes to erase unrelated saved keys.

## FORCED scope and source-of-truth: B1G UK sports EPG and rail

Read [docs/B1_FORENSIC_EPG_SPORTS_API_SCOPE_AUDIT_2026-11-12.md](docs/B1_FORENSIC_EPG_SPORTS_API_SCOPE_AUDIT_2026-11-12.md) before any API/EPG/B1G work. B1's existing enhanced UK feed is **farleyflex/epg-guide**, generated daily at 06:00 UTC via iptv-org from third-party guides; source updates have landed hours late. Treat EPG programme accuracy separately from freshness, and source publishing rights separately from public fetch availability.

Central engine must support **EPG source-specific programme corrections plus daily sports fixtures**, subject to explicit redistribution rights. Do not merely append another XMLTV source after generic provider entries: verified detailed programmes need quality-aware precedence, manual user choices take priority, source identity cannot rely on literal farleyflex URL matching. The B1G consumer alone resolves local playable stream channels, account scope, visibility and user overrides.

The only observed user-entered third-party API keys in Android Settings are **API-Sports, TMDB, OMDb**. Move **API-Sports / sport fixture API keys** to Home Assistant only. **DO NOT** bring TMDB, OMDb, movie/TV posters, hero art, IPTV account credentials, credentialed provider XMLTV, stream URLs, or local per-user mappings into SportsLiveInfo. TheSportsDB public test-key team crest/standings should remain a B1 feature for now. No unlicensed EPG redistribution.

Important B1 corrective candidates from this audit: free-fixture API missing coverage must not suppress independently credible EPG fixtures; event status is not equivalent to broadcasting programme time; Android sports rank currently caps including PPV at 10 whereas Mac uses 10 plus 1 optional PPV. All such fixes belong in separately reviewed B1 code changes, not silent changes to SportsLiveInfo.

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
