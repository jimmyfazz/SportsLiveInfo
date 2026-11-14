# Channel identification and EPG source research — 14 November 2026

Status: research complete; findings implemented in SportsLiveInfo 0.3.18 (all new sources **off by default**). The owner's channel list was used for measurement only and is not in this repository. The examples below are public channel names, not entries from that list.

## 1. Question

For every channel in the owner's provider lineup, two things were investigated:
- **Identification:** which channel is it?
- **Guide:** which free guide carries its programmes, so it can be reconciled with B1G's own provider guide and linked to sport?

The pass covered all markets, not only UK/France, and also looked at renames, closures and event-only channels.

## 2. Method

| Step | Input | Output |
|---|---|---|
| Gap inventory | Owner lineup: 21,250 linear channels, 34 market sections | Per channel: resolved / guide name / closed / event slot / unresolved, plus value class (sport, news, movies…) |
| Database | iptv-org `channels.csv` / `feeds.csv` (public domain, 14 Nov) | Identity, alternative names, feeds, broadcast areas, closures and `replaced_by` |
| Guide site lists | iptv-org/epg `sites/*/*.channels.xml` (180,679 entries, 31,658 with ids) | Which guide sites carry each identified channel |
| Name grammar | Samples of unresolved names per market | Provider prefix, platform and suffix patterns (§4) |
| Renames and closures | Web research (dated sources) | §6 |
| Free guide sources | Web research plus direct download and parse of every GitHub-hosted candidate | §5 |
| Measurement | The app's own `dictionary.Resolver` before and after | §3 |
| Precision | 155 new matches checked by hand, in two samples (70 random, 85 by method) | §3.2 |

Only GitHub is reachable from the cloud development session. epgshare01.online, iptv-epg.org, i.mjh.nz, epg.pw and open-epg.com could not be opened there, so their files are marked **verify**. The *Test EPG* button on the Home Assistant mini PC checks them.

## 3. Results

### 3.1 Identification (high confidence, applied automatically)

| Scope | Before | After 0.3.18 |
|---|---|---|
| UK + Europe, default settings | 55.4 % | **60.4 %** |
| UK + Europe, sport channels | 57.8 % | **64.8 %** |
| Whole list, all optional regions on | 20.0 % | **49.1 %** |
| Whole list, sport channels, all regions | 26.7 % | **46.2 %** |

Per section, with all regions on (before → after):
- **UK and Europe:**
  - Scandinavia 44.0 → 59.7 % (C More/Viasat renames);
  - UK 52.3 → 56.1 % (Premier Sports, renames);
  - Germany 49.7 → 60.0 % (provider tags, own-market suffix);
  - Russia 43.9 → 55.3 % (Cyrillic transliteration, viju);
  - Bulgaria 58.1 → 64.3 %, Greece 56.1 → 61.1 %, France 65.5 → 66.9 %, Portugal 52.3 → 54.8 %.
- **World sections** (0 % before, because the dictionary was Europe-only):
  - North America: US 40.2 %, Canada 45.9 %.
  - Asia: India 59.9 %, Pakistan 62.8 %, Vietnam 66.2 %, Nepal 51.8 %, Philippines 48.0 %.
  - Latin America 59.1 %, MENA 40.8 %, Iran 36.7 %, Africa 34.2 %, Caribbean 28.3 %.
  - Oceania: Australia 45.6 %, New Zealand 83.3 %.

### 3.2 Precision

- **First sample (70 new matches): 66 correct.** Four errors, all fixed before release:
  - "|NIGERIA| AIT" matched Ghana's AIT TV. Fixed by the country tag.
  - "DSTV | MTV" matched MTV Portugal through a broadcast area. Fixed: the DStv tag means South Africa.
  - The other two came from the same cause, the first country in a multi-country section winning. Fixed by pooling: such names now come back ambiguous.
- **Second sample (85 new matches, by method):**
  - No match picked the wrong *country*.
  - The successor matches follow the database's `replaced_by` data, e.g. HBO Signature → HBO Drama and C More Sport (FI) → MTV Urheilu.
  - A few successor matches could not be confirmed independently (e.g. a small Indian channel replaced by another). They are as reliable as the database entry.
  - One short global brand was wrong: "CNN" in an Arabic section → CNN Business Arabic, through a database alternative name. It is left as found.
- **Six names that were high before are now ambiguous** (Cyrillic transliteration created a second candidate). None are wrong; ambiguous names are only suggested to the owner.

### 3.3 Guide availability for identified channels

The iptv-org site lists name, for each identified channel, the operator or guide sites that publish its schedule. Share of identified channels with at least one site:

| Section | Share | Section | Share |
|---|---|---|---|
| UK | 95 % | Italy | 99 % |
| France | 95 % | Netherlands | 99 % |
| Germany | 98 % | US | 91 % |
| Portugal | 94 % | India | 84 % |
| Spain | 85 % | MENA | 65 % |
| Poland | 82 % | Africa | 48 % |
| Scandinavia | 82 % | Caribbean | 31 % |
| Turkey | 71 % | Greece | 16 % |
| Iran, Nepal, Pakistan | ≤ 12 % | | |

Most of those sites are scrapers (iptv-org/epg grabber targets), not downloadable XMLTV files. The downloadable free files are in §5.

## 4. Provider name grammar found

| Pattern | Examples (synthetic or generic) | Rule |
|---|---|---|
| Country in bars | `|SENEGAL| `, `|AR| ` | Removed; in multi-country sections the country narrows the lookup |
| Code + language/region | `IN-TM | `, `IN-NEWS | `, `UK-PUNJ | `, `CA-F | ` | Removed |
| Code + colon | `EG: `, `IRQ: `, `ALG: `, `LB: `, `Ar: ` | Removed; country tag |
| Platform + market | `JOYN DE: `, `MG DE: `, `DE ||VIP| `, `Shahid | `, `JAWWY | `, `DSTV | ` | Removed; platform → country (DStv → ZA, Shahid/Jawwy → SA) |
| Bracket chains | `(MX) (IZ) `, `US (Faith) `, `AF (AZ) `, `Carib (FLOW) ` | Removed in world sections |
| Platform word | `Claro ` (Latin America) | Removed |
| Trailing marks | `(FL)`, `(C)`, `|TN|`, `(720p)` | Removed |
| Own-market suffix | `… HD DE` in a German list | Fallback |
| US/CA locals | `NBC 5 (KXXX) City` | Callsign → network feed |
| Glued quality | `DAZN 1HD` | Removed |

Market codes are removed only once, and only the channel's own market code ("US USA Network" keeps "USA"; "Al Jazeera" keeps "Al").

## 5. Free guide sources

Rights: **no source states a licence permitting republication of programme data.** All of them are for private matching on the owner's own collector and TVs only, in line with the stop/go gate. iptv-org code and data are public domain, and M3UPT's code is MIT, but neither licence covers the scraped schedules.

### 5.1 Added in 0.3.18 (off by default)

| Source id | Coverage | Verified 14 Nov |
|---|---|---|
| `mjh_skysportnow_nz` | Sky Sport NZ 1–9, Premier League, Select, ESPN/ESPN2; 7 days | Downloaded and parsed: 14 ch, 1,833 programmes, 0.1 MB |
| `mjh_kayo_au` | Fox Sports 503–506, Fox Cricket/League/Footy, ESPN, Racing.com | 12 ch, 1,078 programmes |
| `mjh_plex_gb` | UK FAST: Stingray, Qwest TV, Eurovision Sport and others | 371 ch, 15,138 programmes, 3.4 days |
| `mjh_samsung_gb` | UK FAST: Vevo, Rakuten TV, Sky Sports Stories/Classics, DAZN Ringside, talkSPORT | 278 ch, about 17 hours ahead |
| `mjh_pluto_gb` | UK FAST | 183 ch, about 1 day ahead |
| `es_doblem` | Spain including Movistar Plus+ (M+ LaLiga, Liga de Campeones, Vamos), DAZN LaLiga, LaLiga Hypermotion | 627 ch, 82,444 programmes (95 MB uncompressed) |
| `fr_mena_grab` | France (about 800 ch), beIN Sports MENA 1–9/Max/Xtra/AFC, beIN FR/EN, OSN, MBC; 9 days | 1,361 ch, 191,319 programmes (130 MB) |
| `pt_m3upt` | Portugal: Sport TV 1–7, DAZN 1–5, Eurosport; 7 days | 293 ch, 53,185 programmes, iptv-org ids |
| `epgshare_<cc>` (verify) | DE, ES, IT, NL, CH, SE, NO, DK, FI, TR, RO, BG, HU, CZ, SK, HR, BA, AL, SA, EG; `epgshare_bein` (beIN MENA) | Tags listed by two independent lists; not reachable from the cloud |
| `iptv_epg_<cc>` (verify) | SE, NO, DK, TR, PT, PL, RU, AL, BG, CZ, HU, RO | Listed on the publisher's page; not reachable from the cloud |

All the sources above passed the app's own streaming parser within their size limits. The largest needed 6.4 s and about 375 MB peak with every guide held in memory at once.

The repository's Foxtel guide was **not added**: its data was stale (October).

### 5.2 Found but not added

- **Not added yet:**
  - **Sky Go NZ** (`SkyGo/epg.xml.gz`): 100 channels and 3 months ahead, but 6.7 MB compressed and 68 MB expanded. Sky Sport Now covers the sport subset.
  - **iptvx.one:** Russia, Ukraine and CIS, 3,329 channels, about 60 MB. Terms unknown.
  - **daoudeddy/xmltv-epg:** beIN, OSN and elCinema as GitHub release files. Last commit January 2025, so freshness is unverified.
  - **Rytec mirrors:** they ask users not to poll often.
  - **epg.pw** and **open-epg.com:** not reachable from the cloud, and their terms are unknown.
- **Grabber only, not hosted:**
  - The iptv-org/epg site configs: tv.nu, allente, digiturk, tv.mail.ru, ipko.tv, tvprofil, movistarplus.es, osn.com, bein.com and others.
  - Running the grabber on the mini PC would need Node.js. Each site has its own terms.
- **Dead or stale:** globetvapp/epg (removed), xmltv.se (archived), tdtplay/epgs and shaxxx/epg (stale since 2023–24).

## 6. Renames, closures and event-only channels

The table lists **high-impact changes since 2020** with dated sources. Facts gathered only from search extracts are marked *unverified*. The resolver relies on the database's `replaced_by` and adds an alias only where the database lacks the rename.

| Old name(s) | Now | Date |
|---|---|---|
| BT Sport 1–4, Ultimate | TNT Sports 1–4, Ultimate | 18 Jul 2023 |
| Viaplay Sports 1/2 (UK) | Premier Sports 1/2 | 9 Apr 2024 |
| Sky Sports Arena | Sky Sports+ | 2024 *(month unverified)* |
| Sky Showcase, Sky Max | Sky One (relaunched) | 24 Feb 2026 |
| ITVBe | ITV Quiz | 9 Jun 2025 |
| Dave, Drama, Yesterday, W / Gold, Alibi, Eden | U&Dave, U&Drama, U&Yesterday, U&W / U&Gold, U&Alibi, U&Eden | 16 Jul 2024 / Nov 2024 |
| Eurosport 1/2 UK and IE | Content moved to TNT Sports | 28 Feb 2025 |
| Chérie 25 | RMC Life | 1 Oct 2025 |
| C8, NRJ 12 | Closed (Gulli moved to DTT 12) | 28 Feb 2025 |
| Réels TV / OF TV | T18 / Novo19 | Jun / Sep 2025 |
| OCS Max, Pulp, Géants; Ciné+ Premier | OCS (one channel); Ciné+ Famiz → Family, Club → Festival | 3 Jul 2024 |
| Game One, J-One, Paramount Network FR, BET FR, MTV music channels (Europe) | Closed | 31 Dec 2025 |
| RMC Sport 2 | Now event-only RMC Sport Live 2 | 2 Jul 2024 |
| C More (SE) channels | TV4 (Hits, Fotboll, Hockey, Sport Live 1–4) | 14 Aug 2023 |
| Viasat Sport / Film / Series (Nordic) | V Sport / V Film / V Series | 1 Jun 2020 |
| Viasat Explore/History/Nature, TV1000 (Russia) | viju channels | 1 Mar 2023 |
| FOX (Turkey) | NOW | 12 Feb 2024 |
| Fox (NL/BE, Balkans, PT, ES) / Fox (PL) | Star Channel / FX | 2023–24 |
| Boomerang (CEE, PT, Nordic, Turkey, MENA, Western Europe) | Cartoonito | 2023–24 |
| Eleven Sports 1–6 (Portugal) | DAZN 1–6 | about Aug 2023 *(unverified)* |
| SSC 1–5, SSC Extra (Saudi Arabia) | Closed; league rights moved to Thmanyah | 5 Oct 2025 |
| Movistar Plus+ | Movistar Plus / M+ | 14 May 2026 |
| Sky Cinema Highlights / Family (DE) | Sky Cinema Blockbuster / Feelgood | May 2026 |

**Event-only channel families** (fixture-bound; never mapped to a fixed guide channel):
- France: Canal+ Live 1–19, beIN Sports MAX 4–10, RMC Sport Live 2–4, Eurosport 360.
- Germany: Sky Sport Bundesliga 1–10 and Sky Sport 1–10.
- UK: TNT Sports 5–10.
- Spain: the numbered Movistar Liga de Campeones channels and the numbered DAZN LaLiga channels.
- Nordic: TV4 Sport Live 1–4 and TV 2 Sport X.
- Elsewhere: beIN Sports MAX (MENA) and Eurosport 3–9 pop-ups.

Still uncertain (re-check later):
- the name and launch date of the Game One/J-One relaunch;
- a reported BBC Three closure in 2027;
- the outcome of Turkey's NOW rename order;
- whether CMA Media renames RMC Sport.

## 7. Remaining gaps and recommendations

1. **Owner (Home Assistant):** enable only the sources for channels you actually watch. In priority order:
   1. `mjh_skysportnow_nz` (NZ sport);
   2. `es_doblem` (Spanish sport);
   3. `fr_mena_grab` (beIN MENA and France, large);
   4. `pt_m3upt`;
   5. the UK FAST guides, if you watch Stingray or Vevo channels.

   Run *Test EPG* first on every "verify" source.
2. **Owner (Home Assistant):** switch on a dictionary region only for regions you watch. Each one makes the published dictionary larger for every TV: Europe alone is about 3 MB, all regions about 9.5 MB (1.3 MB compressed).
3. **B1G (Codex):** implement the 0.3.18 resolver rules and pass `schemas/fixtures/sli-v1/dictionary-cases.json` and `matching-cases.json`. See [the feed contract §4.0](FEED_CONTRACT_SLI_V1.md).
4. **Still unidentified:** about 8,500 distinct names.
   - Mostly US/Canada regional sports alternates, numbered "sports pack" or "event" slots, Latin American and Caribbean local stations, Iranian and Kurdish satellite channels, and FAST music channels.
   - Many are absent from the public database. Guide-name matching on the TV, against the provider's own guide, is the route for them.
5. **Not run here:** live tests of the "verify" sources (hosts blocked in the cloud session); B1G-side use on a device; a schedule-fingerprint check of the new guides against existing ones (it needs the guides stored on Home Assistant).
