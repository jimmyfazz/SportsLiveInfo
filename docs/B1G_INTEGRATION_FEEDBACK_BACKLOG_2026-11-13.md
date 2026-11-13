# B1G integration: SportsLiveInfo producer backlog and B1G feedback import

**Dated:** 13 November 2026 · **Status:** BACKLOG. **NOT IMPLEMENTED.**

**Full review and rationale:** B1 repo `docs/SPORTSLIVEINFO_B1G_INTEGRATION_REVIEW_2026-11-13.md`. That review covers the sports rail redesign, EPG matching, and the owner-initiated feedback loop.

**Evidence:** live feed revision `1fe6052e6bcaa722b30d` (13 Nov 2026 17:38 UTC, App 0.3.6), all assets sha256-verified.

## 1. What the live feed shows

| Measure | Value | Consequence |
|---|---|---|
| Events | 3,398 (848 today, 2,512 tomorrow) | Broad coverage |
| Day 3–8 events | 2–11 per day | **"Up next" on TVs will be nearly empty.** The API-Sports free plan effectively covers today and tomorrow only |
| `*.other` categories | 3,079 of 3,398 (91 %) | TVs cannot rank the long tail; labels fall back to raw competition names |
| `category_priority` ≤ 20 | 212 events | The useful core is small |
| Largest day asset | 1.56 MB raw / 120 KB gzip | Heavy for Fire TV parse and memory; needs tiering |
| `verified_broadcasts` | 0 (`broadcast_candidates`, `epg_programmes` not published) | B1G must link events to channels locally from its own provider guide |
| Corroborated events | 7 | Most events rest on one source |
| Precision issues | Golf and snooker rounds at `00:00` marked `scheduled`; two events without `status_normalized` | Wrong TV labels |

## 2. Producer backlog (priority order)

1. **FEED-T1: tiered event assets.**
   - Publish `events-core:<day>` alongside the current `events:<day>`, which becomes the "all" tier.
   - **Core** holds featured events; `category_priority` ≤ 50; competitions in the B1G household preferences when imported (§3); and events any imported B1G link evidence shows as watchable.
   - Mark core as `required` for today and tomorrow. TVs fetch core by default.
   - Contract: an additive asset kind, so the format stays at minor version 0 and old readers ignore it.
2. **FEED-H1: forward horizon.** Fill days 3–8 from round or season endpoints:
   - football-data.org competition matches (10 req/min);
   - TheSportsDB `eventsnextleague` / `eventsround`;
   - OpenLigaDB matchdays;
   - Jolpica (already in place).
   
   Respect existing budgets and pacing. Mark events from these endpoints `reported` until they are corroborated.
3. **TAX-1: taxonomy coverage.**
   - Add competitions seen in live data: EFL League One and Two (present), WSL, EIHL, Euroleague, NBA, NHL, NFL, NCAA football, UFC, DP World Tour, Autumn Nations, rugby Test matches, Nations League.
   - Map API-Sports league ids to `competition_id` so names do not drive classification.
   - Target: below 50 % `*.other` for events with `category_priority` ≤ 50.
4. **DQ-1: data quality.**
   - A date-only session at `00:00` must be published as `date_only`.
   - Normalise cricket participants ("England Cricket" → "England").
   - Always emit `status_normalized`.
   - Add `end_utc` estimates from taxonomy `typical_minutes`, flagged as estimated.
5. **REG-1: registry growth, after the household inventory is imported.** Add beIN (language suffixes G/N/F are identity-bearing), Canal+, RMC Sport, TNT Sports 5-10 names for non-crosswalk guides, DAZN, Premier Sports and Viaplay. Each comes with hard-negative fixtures in `matching-cases.json`. Ground every entry in channels the household actually has.
6. **LIVE-1 (optional; needs an owner decision on commit volume):** a small `today-status` asset republished every 15 min during busy windows only. B1G computes live state locally, so this is not required.

## 3. B1G feedback import (SLI-HA-FB-1)

This implements the AUD-009 "owner-triggered safe inventory import" within the binding policy in [B1G read-only feed and inventory policy](B1G_READ_ONLY_FEED_AND_INVENTORY_POLICY.md).

- **Ingress page "B1G feedback"** with two ways to import:
  1. **LAN pull.** The owner enters the address and code shown by a TV's one-shot export server. The App makes one outbound GET:
     - RFC1918 or link-local addresses only;
     - no redirects;
     - a 10 s timeout;
     - at most 2 MB, gzip-aware.
  2. **File upload.** This is a dedicated multipart action with its own size cap, separate from the current 12 KB form limit.
- **Schema `b1g-feedback/1`** has sections `meta`, `inventory`, `unmatched`, `links`, `missed`, `guide_sources` and optional `preferences`. The field definitions are in the B1 review §5.3. Reject any document containing URL-like values in inventory fields, stream-id-like keys, or unknown top-level sections.
- **Storage:** HA `/data` only. Per-TV opaque alias; replace-on-reimport per alias; delete button.
- **Uses:**
  - **Coverage planning view:** household channels against registry coverage and guide health, showing which guides would help.
  - **Registry suggestion queue:** the owner accepts or rejects each suggestion, with hard-negative checks run automatically.
  - **Private household broadcast map:** used for collection prioritisation and as a labelled accuracy benchmark.
  - **Missed-event list:** taxonomy and source discovery.
- **Hard rule, with a test:** `feed.build_feed` never reads feedback tables. Only owner-accepted registry entries flow into the `channels` asset. Publishing observed broadcasts (`broadcasts[]` as canonical service ids) requires a separate owner rights decision and is **off by default**.
