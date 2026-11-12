# Versioned feed schemas, provenance, licence gates and crash-safe publishing
**Normative design 1.0 — 12 Nov 2026.** Read with `MASTER_IMPLEMENTATION_ROADMAP.md`. Output is intended for a separately approved public feed after rights checks. **No public feed or Home Assistant WAN access is presently enabled.**

## 1. Consumers and transport

- Private HAOS App fetches sports/EPG via outbound HTTPS; keeps persistent SQLite, secrets and full permitted-local cache on mini PC. It may publish **only rights-cleared fields** to a separate static GitHub feed through an outgoing HTTPS write operation.
- Ten B1G televisions are anonymous **read-only HTTPS clients** of the published static assets, never connect to the HAOS mini PC from outside the home and never receive GitHub/provider credentials. B1 uses its existing authorised account EPG locally where public redistribution of programme information isn't permitted.
- No speculative live push service. Near-current state is bounded by provider freshness, scheduling interval and GitHub Pages/CDN deployment time. All clients must show age and not conflate 'broadcast airing' with sporting live status.
- Maintain last-good snapshot and fail gracefully offline; never publish `[]` for a provider outage.

## 2. Data domains and source mapping

**Channel / service identity:** `canonical_channel_id` unique to service+country+regional edition+variant/timeshift; `source_id + source_epg_channel_id` namespaced; string aliases have verified/unverified flags and negative conditions.

**EPG programme:** `programme_id`, `canonical_channel_id`, UTC start/end, original title, language, subtitle, description, category, live/replay/highlights flags, `source_evidence[]` and `quality_correction`. Show original source row independently and only overlay verified enhancements. Can be on a channel even if no sport occurs.

**Sport event:** `canonical_event_id`, sport/subsport, competition, event_type, stage/session, participants, UTC event start and `start_precision`, venue/location, status as of source observation, source completeness.

**Broadcast link:** `canonical_event_id -> programme_id -> canonical_channel_id` plus territory and source evidence; distinguish `coverage_start_utc`, `event_start_utc`, `ring_walk_estimate_utc` and `transmission`. Allow multiple channels/OTT services. Broadcaster rights ownership ≠ actual event broadcast.

**Source provenance:** source ID, independent upstream family and network request ID/hash; retrieved/verified/source generated time; accuracy grade, licence policy, terms checked at and restrictions; duplication lineage.

**Consumer-local:** B1 account, streamId, playlist URL/host, hidden categories/channels, manual mapping/source override, playback URL/credential are NEVER in public feed or central catalogue. B1 reads public service metadata and matches locally.

## 3. Proposed feed directory and object contracts (golden fixtures still to be coded)

    /
      manifest.json                       # small discovery pointer, published last
      assets/{revision}/channels.json     # service identity, alias and source crosswalk
      assets/{revision}/sports/2026-11-12.json
      assets/{revision}/sports/next-7-days.json
      assets/{revision}/epg/GB/2026-11-12.json.gz
      assets/{revision}/epg/FR/2026-11-12.json.gz
      assets/{revision}/health.json
      attribution.json                    # rights, licenses and source citations

**Each file is optional only when its coverage/license is explicitly reflected in manifest;** do not publish empty EPG assets just because licences are unavailable. `manifest.json` must be short and free of credentials/internal network names. Versioned asset path contains content hash or build/revision id; never mutate earlier revision assets.

Proposed manifest example (illustrative, fictional; SHA values shortened for readability, not valid output):

    {
      "schema_version": "1.0",
      "revision": "example-rev-20261112-1",
      "generated_at": "2026-11-12T04:30:00Z",
      "next_planned_refresh_at": "2026-11-12T12:00:00Z",
      "default_timezone": "Europe/London",
      "markets": ["GB", "FR"],
      "product_status": {
        "epg": {"state": "partial", "coverage_scope": "selected_service_ids"},
        "sports": {"state": "partial", "coverage_scope": "declared_priority_competitions"}
      },
      "assets": [
        {"kind": "channels", "path": "assets/example-rev-20261112-1/channels.json",
         "sha256": "EXPECTED_64_HEX_IN_REAL_DATA", "bytes": 1234, "compression": "none",
         "licence_class": "approved_public"},
        {"kind": "sports", "country": "GB", "date": "2026-11-12",
         "path": "assets/example-rev-20261112-1/sports/2026-11-12.json",
         "sha256": "EXPECTED_64_HEX_IN_REAL_DATA", "bytes": 5678, "compression": "none",
         "licence_class": "approved_public"}
      ],
      "warnings": ["EPG omitted pending source redistribution rights"]
    }

The placeholder hashes and byte sizes above MUST NOT be deployed; implementation schema validates real 64-digit lowercase hex hashes and actual file lengths. No public `auth`, `token`, `playlist` or user-private identity fields.

## 4. Versioned schemas and compatibility

- Codex owns initial `schemas/*.schema.json` (JSON Schema 2020-12) and synthetic golden samples. Claude reviews B1 consumer requirements before freeze.
- Use separate `schema_version` and `source_schema_version`; choose `1.0` only once validated. Reject unsupported major versions and keep last-good; allow additive optional minor fields; never silently reinterpret a sport's existing field semantics.
- Date query is **Europe/London local calendar date** for default sports rollup; events retain UTC instants and region-specific local date metadata. EPG shards are UTC times keyed by market/local broadcast date; cross-midnight programmes can appear in adjacent shards but unique programme IDs prevent duplicates.
- Example `start_precision` values: `scheduled`, `exact`, `not_before`, `estimated`, `tbc`; absence of actual start is null, not midnight placeholder.
- `licence_class` always available internally; public builder allows only `approved_public` and allowed field mask.
- Stable crosswalk and alias IDs must be independent of HTML display strings. Do not derive identity solely from two team names or two broadcaster terms.

## 5. Publication state machine

States: `COLLECTING` -> `VALIDATING` -> `RIGHTS_CHECKED` -> `BUILDING` -> `UPLOADING_ASSETS` -> `VERIFYING_REMOTE_ASSETS` -> `COMMITTING_MANIFEST` -> `WAITING_FOR_PUBLIC_DEPLOYMENT` -> `VERIFYING_PUBLIC` -> `PUBLISHED`. On any failure keep old manifest and last-good, persist fault diagnostic and bounded retry.

- Build new full snapshot offline; validate schema, licence mask, size, freshness, no secrets; compute hashes before upload.
- Commit new immutable assets under `assets/{revision}/`; validate GitHub/API upload success. Do not delete old assets in same release.
- Update manifest **only after asset upload**, preferably one commit that adds all assets and switches the manifest if atomic repo-tree commit can be used. Do not confuse Git atomic commit with instantaneous GitHub Pages CDN propagation.
- Read the **public Pages endpoint** and validate each referenced asset hash/bytes before declaring deployed. If Pages/CDN serves new manifest before an asset, client may retry with bounded backoff then retain last-good revision. Client must not mix assets from different manifest revisions.
- Schedule 05:00 UK availability as an **objective**, not a hard guarantee. Upstream farleyflex source may only publish after 06:00 UTC and be delayed hours. An earlier 5-day guide can still serve morning with last-success timestamp and later verified refresh.
- Public-reader requests may use Cache-Control/ETag and jitter; never trigger fresh provider queries due to new B1 device connection.
- Report `last_collection_success`, `last_authorised_payload`, `last_git_commit`, `last_public_verified`, product E/S health, source coverage and quota usage separately.

## 6. Licensing and field-level policy (default deny)

For each adapter declare `allowed_local_test`, `allowed_private_internal`, `allowed_public_event_facts`, `allowed_public_epg_programmes`, `allowed_public_derived_epg`, `allowed_public_alias_crosswalk`, `attribution`, `max_cache_age`, `must_review_terms_by`.

- No source without legal approval may contribute programme descriptions or source-derived schedule corrections to world-readable public JSON. Changing JSON formatting/shortening title does **not** magically remove contractual restrictions.
- OpenLigaDB ODbL data may permit publication subject to attribution/share-alike/database requirements; third-party icons not covered. SportsAPI, SportAPI.ai, Jolpica, Boxerbook and EPG collectors need individual contractual review for each use, not assumed from API key availability.
- Keep a machine-readable allowlist in private config and test negative paths; only an administrator can enable approved_public and must record approval evidence. A published output must not contain sources tagged blocked.
- The private SportsLiveInfo source repo need not become public. A public data repo must be explicitly created/approved separately by owner after all gates; GitHub Free does not provide Pages for a private source repo.
- If rights clearance fails, publish only permitted channel/fixture facts and use local device-owned EPG. **No change to the owner’s no-WAN-ingress decision.**

## 7. Safe importer and exporter boundaries

- Optional `Export Safe Channel Inventory` is B1 user-initiated; local file export strips server/playlist/stream URLs, username/password, device IDs, viewing history, direct stream IDs, user secrets and personal account identity; HAOS import via admin-only local Ingress.
- TV ignores hidden channels/categories, uses original providerName for matching, keeps explicit source override and auto suppression, and refuses ambiguous channel mapping. The public feed remains a union/superset within approved legal scope.
- Do not send per-TV change notifications or inventory uploads to GitHub.

## 8. Contract acceptance examples

1. Missing sport provider: `coverage.partial=true`, last-good preserved, never `events=[]` implying no event.
2. EPG source from wrong region/variant: no automatic binding; TV manual confirmation possible.
3. Generic `Live Football` provider row vs detailed EPG with differing coverage start: correction overlay only with verified same service/fixture, never destructive overwrite.
4. France region `Europe/Paris` vs UK `Europe/London` hour difference validated across March/October DST.
5. Boxing PPV programme 19:00, card 20:00, main event actual time TBC: separate fields.
6. Ten TVs with different subscription/hidden states read the **same** manifest and produce different local views without write access.
7. New manifest but absent asset due to deployment cache: B1 continues last-good revision.
8. Source licence blocked: public feed contains no prohibited content and diagnostics show why region/source omitted.

## 9. Test and deliverable checklist

- [ ] JSON Schema files with real golden examples and checksums.
- [ ] Python typed models and validation tests; Android Kotlin deserialiser contract tests.
- [ ] Licence gate tested against every field and old cached data before publish.
- [ ] Manifest transaction/rollback and Pages CDN propagation failure simulation.
- [ ] 10-TV concurrency with zero source API quota growth.
- [ ] Explicit documented public-feed approval with no opening Home Assistant ingress to WAN.
