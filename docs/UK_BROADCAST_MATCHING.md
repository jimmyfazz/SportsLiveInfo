# UK EPG and live-broadcast reconciliation

> **Current documentation context — reviewed 12 November 2026.** The UK cases below remain useful requirements within the international product. Current linking creates provisional candidates; it does not independently certify a live transmission or playable local stream.
> **Repository roles:** [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo) is the public App source and installation repository; [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is PUBLIC daily data only. [Current status and evidence](CURRENT_STATUS.md).

## Why this is separate from fixture retrieval

**Fixture:** "Team A v Team B, Champions League, kick-off 20:00".
**Programme:** "TNT Sports 1, Live UEFA Champions League, coverage 19:00".
**Broadcast link:** a **verified association** between a particular fixture and programme in the UK, not an assumption that a rights holder carries every match.

## Collection contract

- Ingest authorised XMLTV or provider-supplied EPG with channel ID, canonical channel, title, subtitle, description, UTC start/end, language, image link provenance and EPG source.
- Support multiple named channels simulcasting same event. Never discard alternatives before deduplication.
- For OTT/PPV platforms lacking linear EPG, ingest separately validated event/programme links, keeping URL and entitlement evidence.
- Capture UK country/jurisdiction; outside-UK channels are never accepted as UK broadcasts just because their branding resembles UK channels.
- Preserve **programme coverage start**, **event start**, **event window**, **replay/recorded highlights** and **event source timezone** independently.

## Exact matching approach

1. Normalise Unicode, case, punctuation, sponsor prefixes, competition aliases, common abbreviations and club names. Keep canonical IDs plus observed strings; never modify a source's raw fields.
2. Identify negative classifications first: highlights, replay, repeat, delayed, classic, preview, analysis, magazine, rerun, recorded. "Live" in a programme title is not sufficient if classified as a rerun.
3. Extract home/away names (or fighter pair), event category, competition, venue and keywords from EPG. When competitors are both named, support either order. Support tournament sessions with no opponent names.
4. Require plausible event time overlap (not exact kick-off equality). A 19:00 coverage start for a 20:00 kick-off is normal; a programme tomorrow cannot confirm today's match.
5. Check sport, competition and both competitors where available. An individual team or generic competition title alone is too weak for automatic confirmed status.
6. Verify broadcaster is a UK channel/platform and the programme carries this **specific** live event.
7. Reconcile competing guides and official broadcast notices; store matching evidence, last verification, negative evidence and confidence.
8. Return multi-channel output including distinct linear variants (Main Event and dedicated sports channel) and OTT access method.

## Confidence model — proposed, not experimentally calibrated

- **confirmed:** named fixture matches a permitted broadcaster EPG/official broadcast listing with competition, event identity and plausible start-window; no replay/highlights indicators.
- **probable:** strong likely match but programme is generic or one evidence dimension absent; show as provisional.
- **unverified:** fixture known, no reliable UK broadcast match. Broadcast array may be empty.
- **conflicting:** sources disagree about event, time, channel or live/replay state; preserve both claims, flag for review.
- **not_televised_confirmed:** only when an authoritative notice explicitly states the fixture is unavailable live in UK; never derive solely from absence of EPG.

Avoid false precision: a numeric score can assist ranking but must not replace mandatory gates for "confirmed". Keep evidence JSON explainable.

## Domain-specific hard cases

- **Premier League Saturday blackout**: rights holders do not necessarily show every game live; check actual listings and restrictions.
- **F1**: race vs qualifying/sprint/practice; team sport match parsing does not apply. Sky Sports F1 and possible Channel 4 highlights or particular live rights require event-specific checks.
- **Boxing PPV**: card coverage vs undercard vs main-event ring walks; DAZN subscription vs separately purchased PPV; event-only channels omitted from regular EPG.
- **Tennis**: court matches may be "not before" times or "followed by"; generic Wimbledon coverage does not prove a specific singles match starts when the broadcast begins.
- **Cricket**: 3–5-day play windows, lunch/tea breaks, resumption days, rain delays.
- **Rugby**: union and league competitions; similar team names across competitions.
- **UK time**: record UTC; convert using Europe/London including BST changes; support overnight matches and events beginning the previous UTC day.

## EPG source boundaries

The GPL licence of an EPG collector applies to collector software, **not automatically to broadcaster programme data**. Do not copy the full programme schedule into a public feed without provider permission. For B1, match against the user's legitimately configured EPG on-device when appropriate. Public output should contain only fields explicitly cleared for redistribution.

## Acceptance examples (synthetic)

- Kick-off 20:00, programme live coverage 19:00: **match allowed** if event identity confirmed.
- Same teams, programme labelled "Highlights" at 22:30: **no live match**.
- Generic "Champions League Live" 20:00, four concurrent fixtures: **do not assign any particular match without corroboration**.
- "Formula One: Qualifying Highlights" Sunday for Saturday session: **no live-session confirmation**.
- Boxing main card 19:00, ring walk unknown: **ring_walk_utc = null**.
