# Changelog

## 0.2.0 — 12 November 2026

- Add private multi-country EPG channel identity hints and forward guide coverage analysis (24, 72, 168 hours), with strict country, variant and name safeguards.
- Add UK/France EPG coverage page and a separate sport fixture/event viewer in the Home Assistant Ingress UI.
- Add optional no-key OpenLigaDB Bundesliga fixture adapter and Jolpica Sprint Shootout session support.
- Add one-call sports source connection tests and full EPG parser connection tests with quota accounting.
- Preserve last-good on stale guide and invalid/partially paginated provider responses; avoid duplicate refresh queues and excessive API-Sports repeat 7-day requests.
- Preserve all previously saved API keys/source settings during version migration.
- 19 local deterministic tests including private Ingress HTTP/CSRF smoke; actual Home Assistant OS and B1G device validation still pending.
- Experimental stage: **not a production-ready or comprehensive global coverage release**; no public HA ingress, no unapproved third-party EPG redistribution.

## 0.1.0 — 12 November 2026

- Initial installable Home Assistant OS App layout, Ingress interface and setup state.
- Persistent settings, quotas and independent local sporting / international EPG collection.
- Built-in UK/FR source registry; Jolpica, football-data.org and API-Sports adapters.
- Source-level last-good cache, scheduler, status and errors.
- Default-disabled outbound licence-gated GitHub publisher foundation.
- New SportsLiveInfo app icon and wordmark logo.

Not yet a worldwide-complete EPG/sports product or a verified B1G integration.
