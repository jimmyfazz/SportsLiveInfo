# Seeded tables review (owner checklist)

Status: **needs owner review.** Written 20 Nov 2026 for the follow-ups branch. Every entry below was seeded by an agent in S2 (CHANGELOG "Channel hints": "seeded from the owner's B1G tiers and `UK_BROADCAST_MATCHING.md`"). The B1G tier source (`SportsChannelPriorityPolicy.kt`) is in the B1 repository, not this one, so no entry could be checked against it here.

Source labels used below:
- **UNVERIFIED - from agent seed**: no repo document states it. The only support is the seed comment in `sportsliveinfo/src/sportsliveinfo/hints.py`.
- **Repo**: a repo document states or implies it (cited).

How to correct a table without a code release: Publishing page, "Correct the seeded tables", or config keys `broadcaster_rank_override` / `rights_holder_prior_override` (JSON text, validated on save, empty = built-in). Formats are at the end. The next feed uses the override; the fixtures and the built-in tables do not change.

What the tables do (so you know what a wrong entry costs):
- `broadcaster_rank` only orders links that already bind (after sport affinity, before published rank). It never creates a link and never lifts an uncorroborated link above a corroborated one (`docs/FEED_CONTRACT_SLI_V1.md` section 4.3, "Channel hints").
- The rights-holder prior is **off by default** (`rights_holder_prior` false). When on it suggests links with `binds: false`, only when nothing binds, never in the blackout window, never for unconfirmed, postponed, cancelled or finished events (`hints.rights_holder_prior`).

## 1. broadcaster_rank (GB, best first)

Broadcaster ids and the channel-id prefixes they cover are in `hints.BROADCASTERS`. Entries not listed for a sport come after, by tier. Sport "default" is used when a sport has no row.

| Sport | Order | Source of the claim |
|---|---|---|
| football | Sky Sports (`sky_sports`) > TNT Sports (`tnt_sports`) > BBC (`bbc`) > ITV / STV / UTV (`itv`) > Premier Sports (`premier_sports`) > Channel 4 (`channel_4`) > Channel 5 (`channel_5`) > S4C (`s4c`) > Eurosport (`eurosport`) > LaLiga TV (`laliga_tv`) > Club channels (`club_tv`) | Seed comment: Sky/TNT/Premier before free-to-air for football (B1G tiers). UNVERIFIED - from agent seed. `UK_BROADCAST_MATCHING.md` only mentions Premier League blackout and TNT Sports 1 as an example programme. |
| motorsport | Sky Sports (`sky_sports`) > Channel 4 (`channel_4`) > BBC (`bbc`) > ITV / STV / UTV (`itv`) > Eurosport (`eurosport`) > Premier Sports (`premier_sports`) | Seed comment: Sky F1. `UK_BROADCAST_MATCHING.md` hard case F1: "Sky Sports F1 and possible Channel 4 highlights". Sky first: Repo (that note). Order of the rest: UNVERIFIED - from agent seed. |
| cricket | Sky Sports (`sky_sports`) > BBC (`bbc`) > Channel 4 (`channel_4`) > ITV / STV / UTV (`itv`) > Channel 5 (`channel_5`) | Seed comment: Sky cricket specialist. Order UNVERIFIED - from agent seed. `UK_BROADCAST_MATCHING.md` covers cricket play windows only, not broadcasters. |
| rugby | Sky Sports (`sky_sports`) > Premier Sports (`premier_sports`) > TNT Sports (`tnt_sports`) > BBC (`bbc`) > ITV / STV / UTV (`itv`) > S4C (`s4c`) > Channel 4 (`channel_4`) | Seed comment: rugby specialists. `UK_BROADCAST_MATCHING.md` covers union/league name clashes only. UNVERIFIED - from agent seed. |
| rugby_union | Sky Sports (`sky_sports`) > Premier Sports (`premier_sports`) > TNT Sports (`tnt_sports`) > BBC (`bbc`) > ITV / STV / UTV (`itv`) > S4C (`s4c`) > Channel 4 (`channel_4`) | As rugby. UNVERIFIED - from agent seed. |
| rugby_league | Sky Sports (`sky_sports`) > Premier Sports (`premier_sports`) > BBC (`bbc`) > Channel 4 (`channel_4`) > ITV / STV / UTV (`itv`) | UNVERIFIED - from agent seed. |
| tennis | Sky Sports (`sky_sports`) > BBC (`bbc`) > Eurosport (`eurosport`) > TNT Sports (`tnt_sports`) > Channel 4 (`channel_4`) | UNVERIFIED - from agent seed (`UK_BROADCAST_MATCHING.md` hard case Tennis covers timing, not broadcasters). |
| golf | Sky Sports (`sky_sports`) > BBC (`bbc`) > Eurosport (`eurosport`) > TNT Sports (`tnt_sports`) | UNVERIFIED - from agent seed. |
| boxing | Sky Sports (`sky_sports`) > TNT Sports (`tnt_sports`) > Premier Sports (`premier_sports`) > Channel 5 (`channel_5`) > ITV / STV / UTV (`itv`) | `UK_BROADCAST_MATCHING.md` hard case: boxing PPV, DAZN subscription vs PPV, event-only channels. DAZN is not in this table at all. Order UNVERIFIED - from agent seed. |
| mma | TNT Sports (`tnt_sports`) > Sky Sports (`sky_sports`) > Premier Sports (`premier_sports`) | UNVERIFIED - from agent seed. |
| darts | Sky Sports (`sky_sports`) > ITV / STV / UTV (`itv`) > BBC (`bbc`) > Channel 4 (`channel_4`) > Premier Sports (`premier_sports`) | UNVERIFIED - from agent seed. |
| snooker | BBC (`bbc`) > Eurosport (`eurosport`) > ITV / STV / UTV (`itv`) > Sky Sports (`sky_sports`) > Channel 4 (`channel_4`) | UNVERIFIED - from agent seed. |
| horse_racing | Racing TV (`racing_tv`) > ITV / STV / UTV (`itv`) > Sky Sports (`sky_sports`) > Channel 4 (`channel_4`) > Channel 5 (`channel_5`) | UNVERIFIED - from agent seed. |
| american_football | Sky Sports (`sky_sports`) > BBC (`bbc`) > ITV / STV / UTV (`itv`) > Channel 4 (`channel_4`) | UNVERIFIED - from agent seed. |
| basketball | Sky Sports (`sky_sports`) > TNT Sports (`tnt_sports`) > Premier Sports (`premier_sports`) | UNVERIFIED - from agent seed. |
| default | Sky Sports (`sky_sports`) > TNT Sports (`tnt_sports`) > BBC (`bbc`) > ITV / STV / UTV (`itv`) > Channel 4 (`channel_4`) > Channel 5 (`channel_5`) > Premier Sports (`premier_sports`) > Eurosport (`eurosport`) | Seed. UNVERIFIED - from agent seed. |

Specialist affinity (`SPORT_AFFINITY`, channel -> sports it is the natural home of) is also seeded and is not overridable; it is listed in `hints.py`.

## 2. Rights-holder prior (competition -> channels)

| Competition | Channels (most likely first) | Blackout rule | Source of the claim |
|---|---|---|---|
| `football.premier_league` | `gb.sky.sports.premier_league`, `gb.sky.sports.main_event`, `gb.tnt.sports.1` | Saturday 14:30-15:30 London time: no prior | Premier League blackout: Repo (`UK_BROADCAST_MATCHING.md` hard case, `FEED_CONTRACT_SLI_V1.md` section 4.3: "Saturday 14:30-15:30"). The window 14:30-15:30 and the channel list: UNVERIFIED - from agent seed. |
| `football.champions_league` | `gb.tnt.sports.1` | none | UNVERIFIED - from agent seed. `UK_BROADCAST_MATCHING.md` uses "TNT Sports 1, Live UEFA Champions League" only as a synthetic example. |
| `football.europa_league` | `gb.tnt.sports.1` | none | UNVERIFIED - from agent seed. |
| `football.conference_league` | `gb.tnt.sports.1` | none | UNVERIFIED - from agent seed. |
| `motorsport.f1` | `gb.sky.sports.f1` | none | Sky Sports F1 named in `UK_BROADCAST_MATCHING.md` (Repo) as a rights holder with "possible Channel 4 highlights or particular live rights" needing event-specific checks. |

Blackout window constants: Saturday only, 14:30 to 15:30 inclusive, Europe/London (`hints.BLACKOUT_FROM`, `BLACKOUT_TO`). Not overridable per window; the override can only switch the rule on or off for a competition.

## 3. What is known and what must be verified (as of 20 Nov 2026)

I did not assert anything the sources below do not support. Web search was available and used once; results are summarised, not copied.

Reasonably confident (sourced):
- Premier League UK live rights 2025/26 to 2028/29 are held by Sky Sports and TNT Sports, with BBC Sport holding free-to-air highlights of all matches. Sources: [Premier League announcement](https://www.premierleague.com/en/news/3807882), [SVG Europe](https://www.svgeurope.org/blog/headlines/premier-league-seals-6-7-billion-uk-rights-deal-with-sky-sports-tnt-sports-and-bbc-sport-for-2025-26-season-onwards/?print=1). This supports `gb.sky.sports.*` and `gb.tnt.sports.1` for `football.premier_league`.
- The Champions League UK rights change from the 2027/28 season: Paramount+ takes most matches and Prime Video keeps a Tuesday first pick (reported by [Broadcast](https://www.broadcastnow.co.uk/broadcasting/paramount-and-prime-video-win-uk-and-ireland-champions-league-rights/5211201.article), [FourFourTwo](https://fourfourtwo.com/competition/explained-how-paramounts-gbp1bn-champions-league-deal-will-look-for-uk-fans)). Until then (the 2026/27 season now running) TNT Sports is the holder; that is consistent with `gb.tnt.sports.1` today but the table will be wrong from August 2027.
- Europa League and Conference League were reported (search summary, one aggregator) to move from TNT Sports to Sky Sports from 2027. Verify before relying on it.
- Sky has exclusive live F1 in the UK (search summary only; not confirmed for 2026 in detail).

Verify before ticking (not established here):
- Whether Prime Video's Tuesday pick and any TNT Sports Champions League matches this season mean `gb.tnt.sports.1` is not the only prior (Prime Video has no linear channel id in the registry, so a prior cannot name it).
- Premier League matches: which of Sky or TNT shows a given match varies; TNT Sports channel numbers (1 to 4) and Sky Main Event vs Premier League channel vary by match. The prior lists Sky Premier League, Sky Main Event and TNT Sports 1 only.
- F1 free-to-air arrangements (Channel 4 highlights or live races) for the 2026 and 2027 seasons.
- Every `broadcaster_rank` row in section 1: no row was derived from a repo document or a rights source. They are plausible orderings by "who is likely to be the primary UK home", not rights facts.
- Cricket, rugby, tennis, golf, boxing, MMA, darts, snooker, horse racing, American football and basketball: nothing was checked. DAZN, Amazon Prime Video, Paramount+, Netflix and other non-linear holders are absent because they have no registry channel id.
- The Saturday 14:30-15:30 blackout is stated in the repo and is the usual "3 pm" rule, but the exact window is a seed choice, and it ignores the lunchtime/evening exceptions and TNT-held Saturday lunchtime games (the prior does not apply to them anyway since 12:30 is outside the window).

## 4. Owner checklist

Tick = correct as is. Edit = write the correction in the override (formats below).

broadcaster_rank:
- [ ] football: sky_sports > tnt_sports > bbc > itv > premier_sports > channel_4 > channel_5 > s4c > eurosport > laliga_tv > club_tv
- [ ] motorsport: sky_sports > channel_4 > bbc > itv > eurosport > premier_sports
- [ ] cricket: sky_sports > bbc > channel_4 > itv > channel_5
- [ ] rugby: sky_sports > premier_sports > tnt_sports > bbc > itv > s4c > channel_4
- [ ] rugby_union: sky_sports > premier_sports > tnt_sports > bbc > itv > s4c > channel_4
- [ ] rugby_league: sky_sports > premier_sports > bbc > channel_4 > itv
- [ ] tennis: sky_sports > bbc > eurosport > tnt_sports > channel_4
- [ ] golf: sky_sports > bbc > eurosport > tnt_sports
- [ ] boxing: sky_sports > tnt_sports > premier_sports > channel_5 > itv
- [ ] mma: tnt_sports > sky_sports > premier_sports
- [ ] darts: sky_sports > itv > bbc > channel_4 > premier_sports
- [ ] snooker: bbc > eurosport > itv > sky_sports > channel_4
- [ ] horse_racing: racing_tv > itv > sky_sports > channel_4 > channel_5
- [ ] american_football: sky_sports > bbc > itv > channel_4
- [ ] basketball: sky_sports > tnt_sports > premier_sports
- [ ] default: sky_sports > tnt_sports > bbc > itv > channel_4 > channel_5 > premier_sports > eurosport

rights_holder_prior:
- [ ] football.premier_league: gb.sky.sports.premier_league, gb.sky.sports.main_event, gb.tnt.sports.1; blackout Sat 14:30-15:30
- [ ] football.champions_league: gb.tnt.sports.1
- [ ] football.europa_league: gb.tnt.sports.1
- [ ] football.conference_league: gb.tnt.sports.1
- [ ] motorsport.f1: gb.sky.sports.f1
- [ ] Decide whether `rights_holder_prior` should be switched on at all (it ships off; currently `False`).
- [ ] Decide what happens to the Champions League, Europa League and Conference League rows before the 2027/28 season.

## 5. Override formats

Config key `broadcaster_rank_override` (JSON text; replaces only the sports named, `default` replaces the fallback order):

```json
{"football": ["sky_sports", "tnt_sports", "bbc"], "default": ["sky_sports", "bbc"]}
```

Rules: object with at least one key; keys are lower-case sport ids or `default`; each value is a list of 1 to 40 distinct broadcaster ids from `hints.BROADCASTERS`; at most 20,000 bytes.

Config key `rights_holder_prior_override` (replaces only the competitions named; an empty `channels` list removes that competition's prior; `blackout` true/false switches the Saturday window rule on or off for that competition, absent leaves the built-in setting):

```json
{"football.premier_league": {"channels": ["gb.sky.sports.premier_league", "gb.tnt.sports.1"], "blackout": true},
 "football.europa_league": {"channels": []}}
```

Rules: competition ids look like `football.premier_league`; channel ids must be curated registry ids (or ones already in the built-in prior), at most 10 and distinct; no other fields. An invalid value is refused whole when saved; a stored value that is somehow invalid is ignored and the built-in table is used.
