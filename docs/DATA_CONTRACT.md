# Canonical JSON and API contract — proposal v0.1

**Not an implemented API.** Fixtures and broadcasts are distinct linked entities. All instants end in Z and are UTC. UK display dates/times use Europe/London. Unknown is null or explicit state, never an invented value.

## Proposed external read endpoints (future)

- GET /api/v1/events?date=YYYY-MM-DD&region=GB&sport=football
- GET /api/v1/events?from=YYYY-MM-DD&to=YYYY-MM-DD&region=GB
- GET /api/v1/events/live?region=GB (only genuine live status, with freshness)
- GET /api/v1/channels/{channel_id}/events?date=YYYY-MM-DD
- GET /api/v1/health
- Static equivalent: /data/YYYY-MM-DD.json, /data/seven_days.json, /data/health.json

The client should not need to know a provider's event IDs or event status vocabulary. Pagination and provider quotas are hidden within the aggregator.

## Example illustrative envelope (fictional data; NOT real fixtures)

    {
      "schema_version": "0.1",
      "date_local": "2026-11-12",
      "timezone": "Europe/London",
      "region": "GB",
      "generated_at": "2026-11-12T08:00:00Z",
      "expires_at": "2026-11-12T08:30:00Z",
      "coverage": {"state": "partial", "sources_checked": 2, "warnings": []},
      "events": [{
        "id": "sli_evt_example_001",
        "sport": "football",
        "subsport": null,
        "competition": {"name": "Illustrative League", "id": null},
        "event_type": "match",
        "title": "Team A v Team B",
        "participants": [
          {"id": null, "name": "Team A", "role": "home"},
          {"id": null, "name": "Team B", "role": "away"}
        ],
        "venue": {"name": null, "city": null, "country": null, "circuit": null},
        "start_utc": "2026-11-12T19:45:00Z",
        "start_precision": "scheduled",
        "end_utc": null,
        "status": "scheduled",
        "status_checked_at": "2026-11-12T08:00:00Z",
        "broadcasts": [{
          "region": "GB",
          "service": "Example Sports",
          "channel": "Example Sports 1",
          "epg_channel_id": null,
          "platform": "linear",
          "entitlement": "subscription",
          "transmission": "live",
          "coverage_start_utc": "2026-11-12T19:00:00Z",
          "confidence": "confirmed",
          "evidence": [{"source": "example-epg", "source_url": null, "observed_at": "2026-11-12T08:00:00Z"}]
        }],
        "source_events": [{"provider": "example-fixtures", "provider_event_id": "x1", "observed_at": "2026-11-12T08:00:00Z"}],
        "last_verified_at": "2026-11-12T08:00:00Z",
        "warnings": []
      }]
    }

## Enums and validation rules

- status: scheduled, in_progress, suspended, completed, postponed, cancelled, unknown.
- event_type: match, tournament_session, practice, qualifying, sprint, race, boxing_card, boxing_bout, other.
- start_precision: exact, scheduled, not_before, estimated, tbc.
- transmission: live, delayed_live, highlights, replay, preview, unknown.
- entitlement: free_to_air, subscription, pay_per_view, free_streaming, unknown.
- confidence: confirmed, probable, unverified, conflicting; *not_televised_confirmed* may be a separate explicit broadcast-status field.
- A "live now" filter MUST NOT rely solely on start_utc < now; source live status or carefully qualified ongoing session corroboration required.
- Boxing optional fields: card_start_utc, main_event, ring_walk_estimate_utc, ring_walk_precision, ppv_event_id.
- F1 optional fields: season, grand_prix, circuit, country, round, session_type.
- Cricket optional fields: format, day_number, session_start_utc, session_end_utc, play_state.

## Identity, duplication and evidence

- Stable canonical IDs (hash of sport/competition/external stable ID where possible); maintain a crosswalk to all provider event IDs and name aliases.
- Never merge two F1 sessions, two tennis singles matches, two legs of a tie, or both cricket fixtures in a doubleheader merely because date/participants match.
- Broadcast claims are multiplicities (Sky Sports F1 and other concurrently licensed transmissions) not a single "channel" field.
- Include last-retrieved time for each underlying source and dataset-level completeness. If source licence forbids republication, omit that content from public feeds until authorised.
