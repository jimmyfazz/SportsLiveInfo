"""Sport and competition taxonomy for the "live action today" view.

Classification is deterministic and conservative: an event is only placed in a
named competition when a provider code or an exact (country-qualified) name
matches. Anything else stays in "<sport>.other" with its raw competition name.
Ambiguous names (Premier League, Championship, League Cup, Challenge Cup,
Masters, US Open) are always resolved within a sport and, where needed, a
country; never across sports.
"""
import re
import unicodedata

# sport id -> (label, typical duration in minutes used for a "probably live" estimate, display order)
SPORTS = {
    "football": ("Football", 115, 10),
    "rugby_union": ("Rugby union", 100, 20),
    "rugby_league": ("Rugby league", 100, 21),
    "rugby": ("Rugby (code unconfirmed)", 100, 22),
    "cricket": ("Cricket", 420, 25),
    "tennis": ("Tennis", 180, 30),
    "motorsport": ("Motorsport", 120, 15),
    "boxing": ("Boxing", 240, 35),
    "mma": ("MMA", 240, 36),
    "golf": ("Golf", 600, 40),
    "darts": ("Darts", 240, 42),
    "snooker": ("Snooker", 300, 44),
    "horse_racing": ("Horse racing", 300, 46),
    "cycling": ("Cycling", 300, 48),
    "athletics": ("Athletics", 180, 50),
    "bowling": ("Bowling", 180, 52),
    "esports": ("Esports", 180, 54),
    "basketball": ("Basketball", 150, 55),
    "american_football": ("American football", 210, 56),
    "ice_hockey": ("Ice hockey", 160, 57),
    "baseball": ("Baseball", 200, 58),
    "handball": ("Handball", 100, 60),
    "volleyball": ("Volleyball", 120, 61),
    "aussie_rules": ("Australian rules football", 150, 62),
    "netball": ("Netball", 90, 63),
    "other": ("Other sport", 120, 99),
}

# Provider sport labels -> taxonomy sport id.
SPORT_ALIASES = {
    "soccer": "football", "football": "football", "association football": "football",
    "rugby": "rugby", "rugby union": "rugby_union", "rugby league": "rugby_league",
    "cricket": "cricket", "tennis": "tennis",
    "motorsport": "motorsport", "motor sport": "motorsport", "formula 1": "motorsport", "f1": "motorsport",
    "boxing": "boxing", "mma": "mma", "fighting": "mma",
    "golf": "golf", "darts": "darts", "snooker": "snooker",
    "horse racing": "horse_racing", "racing": "horse_racing", "cycling": "cycling", "athletics": "athletics",
    "tenpin bowling": "bowling", "ten pin bowling": "bowling", "e sports": "esports",
    "track and field": "athletics", "motorcycle racing": "motorsport",
    "basketball": "basketball", "american football": "american_football", "nfl": "american_football",
    "ice hockey": "ice_hockey", "hockey": "ice_hockey", "baseball": "baseball",
    "handball": "handball", "volleyball": "volleyball", "australian football": "aussie_rules",
    "afl": "aussie_rules", "netball": "netball",
}

ENG = ("england",)
SCO = ("scotland",)
WORLD = ("world", "europe", "international")


def C(cid, label, priority, aliases=(), countries=None, codes=(), prefixes=()):
    return {"id": cid, "label": label, "priority": priority, "aliases": tuple(aliases),
            "countries": countries, "codes": tuple(codes), "prefixes": tuple(prefixes)}


# Ordered competition tables per sport. Lower priority sorts first on the
# Today page. Provider codes: fd = football-data.org competition code,
# as = API-Sports league id, old = OpenLigaDB league shortcut.
# API-Sports ids must be re-checked against a live /leagues response before
# they are relied on alone; names remain the fallback match.
COMPETITIONS = {
    "football": [
        C("football.premier_league", "Premier League", 5,
          ["premier league", "english premier league", "barclays premier league"], ENG + ("",), ["fd:PL", "as:39"]),
        C("football.champions_league", "UEFA Champions League", 6,
          ["uefa champions league", "champions league"], WORLD + ("",), ["fd:CL", "as:2", "old:ucl"]),
        C("football.europa_league", "UEFA Europa League", 7,
          ["uefa europa league", "europa league"], WORLD + ("",), ["as:3"]),
        C("football.conference_league", "UEFA Conference League", 8,
          ["uefa europa conference league", "uefa conference league", "europa conference league", "conference league"],
          WORLD + ("",), ["as:848"]),
        C("football.fa_cup", "FA Cup", 9, ["fa cup", "emirates fa cup", "the fa cup"], ENG + ("",), ["as:45"]),
        C("football.efl_cup", "EFL Cup (Carabao Cup)", 10,
          ["efl cup", "carabao cup", "league cup", "english league cup"], ENG + ("",), ["as:48"]),
        C("football.championship", "EFL Championship", 11,
          ["championship", "efl championship", "english league championship", "sky bet championship"], ENG + ("",),
          ["fd:ELC", "as:40"]),
        C("football.league_one", "EFL League One", 12, ["league one", "efl league one", "english league 1"], ENG, ["as:41"]),
        C("football.league_two", "EFL League Two", 13, ["league two", "efl league two", "english league 2"], ENG, ["as:42"]),
        C("football.efl_trophy", "EFL Trophy", 14, ["efl trophy", "football league trophy"], ENG),
        C("football.community_shield", "Community Shield", 14, ["community shield", "fa community shield"], ENG + ("",)),
        C("football.wsl", "Women's Super League", 15,
          ["womens super league", "fa womens super league", "wsl", "english womens super league", "barclays womens super league"], ENG + ("",)),
        C("football.womens_champions_league", "UEFA Women's Champions League", 16,
          ["uefa womens champions league", "womens champions league"], WORLD + ("",)),
        C("football.scottish_premiership", "Scottish Premiership", 17,
          ["premiership", "scottish premiership", "scottish premier league"], SCO + ("",)),
        C("football.scottish_cup", "Scottish Cup", 18, ["scottish cup", "fa cup"], SCO),
        C("football.scottish_league_cup", "Scottish League Cup", 18, ["scottish league cup", "league cup"], SCO),
        C("football.world_cup", "FIFA World Cup", 19, ["world cup", "fifa world cup"], WORLD + ("",), ["fd:WC", "as:1"]),
        C("football.euro", "UEFA European Championship", 19,
          ["euro championship", "european championship", "uefa european championship", "uefa euro"], WORLD + ("",), ["fd:EC", "as:4"]),
        C("football.nations_league", "UEFA Nations League", 20, ["uefa nations league", "nations league"], WORLD + ("",), ["as:5"]),
        C("football.wc_qualifying", "World Cup qualifying", 20, [], WORLD + ("",),
          prefixes=["world cup qualification", "world cup qualifying", "fifa world cup qualification", "world cup qualifiers"]),
        C("football.euro_qualifying", "European Championship qualifying", 20, [], WORLD + ("",),
          prefixes=["euro championship qualification", "uefa euro qualifying", "european championship qualifying"]),
        C("football.international_friendly", "International friendlies", 21,
          ["friendlies", "international friendlies", "international friendly"], WORLD + ("",), ["as:10"]),
        C("football.club_world_cup", "FIFA Club World Cup", 21, ["fifa club world cup", "club world cup"], WORLD + ("",)),
        C("football.uefa_super_cup", "UEFA Super Cup", 21, ["uefa super cup", "super cup"], WORLD),
        C("football.la_liga", "La Liga", 22, ["la liga", "primera division", "laliga", "spanish la liga"], ("spain", ""), ["fd:PD", "as:140", "old:la1"]),
        C("football.serie_a", "Serie A", 23, ["serie a", "italian serie a"], ("italy", ""), ["fd:SA", "as:135"]),
        C("football.bundesliga", "Bundesliga", 24,
          ["bundesliga", "1 bundesliga", "german bundesliga", "1 fussball bundesliga"], ("germany", ""), ["fd:BL1", "as:78", "old:bl1"]),
        C("football.ligue_1", "Ligue 1", 25, ["ligue 1", "french ligue 1", "ligue 1 mcdonalds"], ("france", ""), ["fd:FL1", "as:61"]),
        C("football.eredivisie", "Eredivisie", 26, ["eredivisie", "dutch eredivisie"], ("netherlands", ""), ["fd:DED", "as:88"]),
        C("football.primeira_liga", "Primeira Liga", 27, ["primeira liga", "liga portugal", "portuguese primeira liga"], ("portugal", ""), ["fd:PPL", "as:94"]),
        C("football.bundesliga_2", "2. Bundesliga", 28, ["2 bundesliga", "german 2 bundesliga"], ("germany", ""), ["old:bl2"]),
        C("football.liga_3", "3. Liga", 29, ["3 liga", "german 3 liga"], ("germany", ""), ["old:bl3"]),
        C("football.domestic_cups_europe", "European domestic cups", 30,
          ["copa del rey", "coppa italia", "dfb pokal", "coupe de france", "knvb beker", "taca de portugal"], None, ["old:dfb"]),
        C("football.frauen_bundesliga", "Frauen-Bundesliga", 30,
          ["frauen bundesliga", "frauen fussballbundesliga"], ("germany",), ["old:ffb1"]),
        C("football.mls", "Major League Soccer", 32, ["major league soccer", "mls"], ("usa", "")),
        C("football.brasileirao", "Brazil Série A", 33, ["campeonato brasileiro serie a", "brasileirao", "serie a"], ("brazil",), ["fd:BSA"]),
        C("football.saudi_pro_league", "Saudi Pro League", 34, ["pro league", "saudi pro league", "roshn saudi league"], ("saudi arabia",)),
        C("football.libertadores", "Copa Libertadores", 34, ["copa libertadores", "conmebol libertadores"], WORLD + ("south america", "")),
        # Markets present in the owner's provider lineup.
        C("football.liga_mx", "Liga MX", 35, ["liga mx", "liga bbva mx"], ("mexico", "")),
        C("football.argentina", "Liga Profesional (Argentina)", 35, ["liga profesional argentina", "primera division argentina", "liga profesional"], ("argentina",)),
        C("football.nwsl", "NWSL", 36, ["nwsl", "national womens soccer league"], ("usa", "")),
        C("football.a_league", "A-League", 36, ["a league", "a league men", "isuzu ute a league"], ("australia", "")),
        C("football.k_league", "K League", 37, ["k league 1", "k league"], ("south korea", "korea", "korea republic")),
        C("football.liga_1_indonesia", "Liga 1 Indonesia", 37, ["liga 1", "bri liga 1"], ("indonesia",)),
        C("football.ekstraklasa", "Ekstraklasa", 37, ["ekstraklasa", "pko bp ekstraklasa"], ("poland", "")),
        C("football.greek_super_league", "Greek Super League", 37, ["super league", "super league 1", "super league greece"], ("greece",)),
        C("football.scandinavia", "Scandinavian leagues", 38, ["allsvenskan", "eliteserien", "superliga", "superligaen", "veikkausliiga"], ("sweden", "norway", "denmark", "finland")),
        C("football.indian_super_league", "Indian Super League", 39, ["indian super league", "isl"], ("india", "")),
    ],
    "rugby_union": [
        C("rugby_union.six_nations", "Six Nations", 1, ["six nations", "six nations championship", "guinness six nations"], WORLD + ("",)),
        C("rugby_union.womens_six_nations", "Women's Six Nations", 2, ["womens six nations", "guinness womens six nations"], WORLD + ("",)),
        C("rugby_union.autumn_nations", "Autumn internationals", 2,
          ["autumn nations series", "autumn internationals", "quilter nations series", "nations championship"], WORLD + ("",)),
        C("rugby_union.world_cup", "Rugby World Cup", 2, ["rugby world cup", "world cup"], WORLD + ("",)),
        C("rugby_union.premiership", "Premiership Rugby", 3,
          ["premiership rugby", "gallagher premiership", "premiership", "prem rugby"], ENG + ("",)),
        C("rugby_union.urc", "United Rugby Championship", 4, ["united rugby championship", "urc", "pro14"], WORLD + ("",)),
        C("rugby_union.champions_cup", "European Champions Cup", 5,
          ["european rugby champions cup", "champions cup", "investec champions cup", "heineken champions cup"], WORLD + ("",)),
        C("rugby_union.challenge_cup", "European Challenge Cup", 6, ["european rugby challenge cup", "epcr challenge cup"], WORLD + ("",)),
        C("rugby_union.rugby_championship", "The Rugby Championship", 7, ["rugby championship", "the rugby championship"], WORLD + ("",)),
        C("rugby_union.test_matches", "International test matches", 7, ["internationals", "international test", "test match", "friendly international"], WORLD + ("",)),
        C("rugby_union.top_14", "Top 14", 8, ["top 14"], ("france", "")),
        C("rugby_union.super_rugby", "Super Rugby", 9, ["super rugby", "super rugby pacific"], None),
        C("rugby_union.premiership_womens", "Premiership Women's Rugby", 9, ["premiership womens rugby", "pwr"], ENG + ("",)),
    ],
    "rugby_league": [
        C("rugby_league.super_league", "Super League", 1, ["super league", "betfred super league"], ENG + ("",)),
        C("rugby_league.challenge_cup", "Challenge Cup", 2, ["challenge cup", "betfred challenge cup"], ENG + ("",)),
        C("rugby_league.internationals", "Rugby league internationals", 3, ["rugby league world cup", "rugby league internationals", "ashes series"], WORLD + ("",)),
        C("rugby_league.nrl", "NRL", 4, ["nrl", "national rugby league", "nrl premiership"], ("australia", "")),
        C("rugby_league.state_of_origin", "State of Origin", 4, ["state of origin"], ("australia", "")),
        C("rugby_league.championship", "RFL Championship", 5, ["championship", "betfred championship", "rfl championship"], ENG),
    ],
    "cricket": [
        C("cricket.ashes", "The Ashes", 2, ["the ashes", "ashes"], None),
        C("cricket.world_cup", "ICC World Cup", 3, ["icc cricket world cup", "cricket world cup", "icc mens cricket world cup"], None),
        C("cricket.t20_world_cup", "ICC T20 World Cup", 3, ["icc t20 world cup", "t20 world cup", "icc mens t20 world cup"], None),
        C("cricket.champions_trophy", "ICC Champions Trophy", 3, ["icc champions trophy", "champions trophy"], None),
        C("cricket.the_hundred", "The Hundred", 4, ["the hundred", "hundred"], ENG + ("",)),
        C("cricket.t20_blast", "T20 Blast", 5, ["t20 blast", "vitality blast", "vitality t20 blast"], ENG + ("",)),
        C("cricket.county_championship", "County Championship", 6, ["county championship", "rothesay county championship"], ENG + ("",)),
        C("cricket.ipl", "Indian Premier League", 7, ["indian premier league", "ipl"], None),
        C("cricket.big_bash", "Big Bash League", 8, ["big bash league", "bbl"], None),
        C("cricket.sa20", "SA20", 9, ["sa20"], None),
        C("cricket.other_t20_leagues", "Other T20 leagues", 10,
          ["pakistan super league", "caribbean premier league", "major league cricket", "ilt20"], None),
    ],
    "tennis": [
        C("tennis.australian_open", "Australian Open", 1, ["australian open"], None),
        C("tennis.roland_garros", "Roland-Garros (French Open)", 1, ["roland garros", "french open"], None),
        C("tennis.wimbledon", "Wimbledon", 1, ["wimbledon", "the championships wimbledon"], None),
        C("tennis.us_open", "US Open", 1, ["us open"], None),
        C("tennis.tour_finals", "ATP/WTA Finals", 2, ["atp finals", "nitto atp finals", "wta finals"], None),
        C("tennis.davis_cup", "Davis Cup", 3, ["davis cup"], None),
        C("tennis.bjk_cup", "Billie Jean King Cup", 3, ["billie jean king cup"], None),
        C("tennis.united_cup", "United Cup", 4, ["united cup"], None),
        C("tennis.atp_tour", "ATP Tour", 5, [], None, prefixes=["atp "]),
        C("tennis.wta_tour", "WTA Tour", 6, [], None, prefixes=["wta "]),
    ],
    "motorsport": [
        C("motorsport.f1", "Formula 1", 1, ["formula 1", "f1", "formula one", "fia formula one world championship"], None),
        C("motorsport.motogp", "MotoGP", 2, ["motogp", "moto gp"], None),
        C("motorsport.moto2_moto3", "Moto2 / Moto3", 3, ["moto2", "moto3", "moto 2", "moto 3"], None),
        C("motorsport.superbikes", "Superbike racing", 3,
          ["world superbike", "world superbikes", "worldsbk", "british superbikes", "british superbike championship"], None),
        C("motorsport.formula_e", "Formula E", 3, ["formula e", "abb fia formula e"], None),
        C("motorsport.wec", "World Endurance Championship", 4, ["wec", "world endurance championship", "24 hours of le mans"], None),
        C("motorsport.indycar", "IndyCar", 5, ["indycar", "indycar series"], None),
        C("motorsport.btcc", "British Touring Car Championship", 5, ["btcc", "british touring car championship"], None),
        C("motorsport.wrc", "World Rally Championship", 6, ["wrc", "world rally championship"], None),
        C("motorsport.f2_f3", "Formula 2 / Formula 3", 7, ["formula 2", "formula 3", "fia formula 2", "fia formula 3"], None),
        C("motorsport.nascar", "NASCAR", 8, [], None, prefixes=["nascar"]),
    ],
    "boxing": [
        C("boxing.ppv", "Boxing pay-per-view", 0, ["boxing ppv", "boxing box office"], None),
        C("boxing.premium", "Premium boxing", 1, ["premium boxing"], None),
        C("boxing.world_title", "World title fights", 1, [], None, prefixes=["world title", "wbc", "wba", "ibf", "wbo", "undisputed"]),
        C("boxing.british_title", "British & European titles", 2, [], None, prefixes=["british title", "european title", "commonwealth title"]),
    ],
    "mma": [
        C("mma.ufc", "UFC", 1, [], None, prefixes=["ufc"]),
        C("mma.pfl", "PFL", 2, [], None, prefixes=["pfl"]),
        C("mma.one", "ONE Championship", 3, [], None, prefixes=["one championship", "one fight night"]),
        C("mma.bellator", "Bellator", 4, [], None, prefixes=["bellator"]),
    ],
    "golf": [
        C("golf.majors", "Majors", 1, ["the masters", "masters tournament", "pga championship", "us open", "u s open", "the open", "the open championship"], None),
        C("golf.ryder_cup", "Ryder Cup / Solheim Cup", 1, ["ryder cup", "solheim cup"], None),
        C("golf.dp_world_tour", "DP World Tour", 3, ["dp world tour", "european tour"], None),
        C("golf.pga_tour", "PGA Tour", 4, ["pga tour"], None),
        C("golf.lpga", "LPGA / LET", 5, ["lpga tour", "ladies european tour", "lpga"], None),
        C("golf.liv", "LIV Golf", 6, ["liv golf"], None),
    ],
    "darts": [
        C("darts.world_championship", "PDC World Championship", 1, ["pdc world championship", "pdc world darts championship", "world darts championship"], None),
        C("darts.premier_league", "Premier League Darts", 2, ["premier league", "premier league darts", "bethard premier league"], None),
        C("darts.majors", "PDC majors", 3,
          ["world matchplay", "grand slam of darts", "world grand prix", "uk open", "players championship finals", "european championship", "world masters"], None),
    ],
    "snooker": [
        C("snooker.world_championship", "World Snooker Championship", 1, ["world championship", "world snooker championship"], None),
        C("snooker.uk_championship", "UK Championship", 2, ["uk championship"], None),
        C("snooker.masters", "The Masters", 2, ["the masters", "masters"], None),
        C("snooker.ranking_events", "Ranking events", 4, [], None, prefixes=["snooker", "championship league"]),
    ],
    "horse_racing": [
        C("horse_racing.festivals", "Major festivals", 1,
          ["cheltenham festival", "grand national", "royal ascot", "the derby", "epsom derby", "glorious goodwood", "aintree"], None),
    ],
    "cycling": [
        C("cycling.grand_tours", "Grand Tours", 1, ["tour de france", "giro d italia", "vuelta a espana", "la vuelta"], None),
    ],
    "athletics": [
        C("athletics.diamond_league", "Diamond League", 1, ["diamond league", "wanda diamond league"], None),
        C("athletics.world_championships", "World Athletics Championships", 1, ["world athletics championships"], None),
        C("athletics.road_races", "World Athletics road races", 2, [], None, prefixes=["world athletics road races"]),
    ],
    "bowling": [
        C("bowling.pba", "PBA Tour", 1, ["pba", "pba tour", "professional bowlers association"], None),
    ],
    "esports": [
        C("esports.blast_premier", "BLAST Premier", 1, ["blast premier"], None),
    ],
    "basketball": [
        C("basketball.nba", "NBA", 1, ["nba"], ("usa", "")),
        C("basketball.wnba", "WNBA", 2, ["wnba"], ("usa", "")),
        C("basketball.euroleague", "EuroLeague", 2, ["euroleague"], None),
        C("basketball.super_league", "British Basketball", 3, ["super league basketball", "bbl"], ("united kingdom", "england", "")),
    ],
    "american_football": [
        C("american_football.nfl", "NFL", 1, ["nfl"], ("usa", "")),
        C("american_football.ncaa", "College football", 2, ["ncaa", "ncaaf"], ("usa", "")),
    ],
    "ice_hockey": [
        C("ice_hockey.nhl", "NHL", 1, ["nhl"], ("usa", "canada", "")),
        C("ice_hockey.eihl", "Elite Ice Hockey League", 2, ["elite league", "eihl", "elite ice hockey league"], ("united kingdom", "great britain", "england", "")),
    ],
    "baseball": [C("baseball.mlb", "MLB", 1, ["mlb"], ("usa", ""))],
    "aussie_rules": [C("aussie_rules.afl", "AFL", 1, ["afl", "afl premiership", "australian football league"], ("australia", ""))],
}

# Featured national teams. Football and cricket internationals get their own
# category (the user-facing "England internationals today" row); other sports
# keep their competition category and only gain a tag.
NATIONS = {
    "england": ("england", "England"),
    "england women": ("england_women", "England Women"),
    "england w": ("england_women", "England Women"),
    "england u21": ("england_u21", "England U21"),
    "scotland": ("scotland", "Scotland"),
    "scotland women": ("scotland_women", "Scotland Women"),
    "wales": ("wales", "Wales"),
    "wales women": ("wales_women", "Wales Women"),
    "northern ireland": ("northern_ireland", "Northern Ireland"),
    "republic of ireland": ("ireland", "Republic of Ireland"),
    "ireland": ("ireland", "Ireland"),
    "france": ("france", "France"),
    "great britain": ("great_britain", "Great Britain"),
    "british and irish lions": ("lions", "British & Irish Lions"),
}

NATIONAL_CATEGORIES = {
    "football": {
        "england": ("football.intl.england", "England (men) internationals", 1),
        "england_women": ("football.intl.england_women", "England Women internationals", 2),
        "england_u21": ("football.intl.england_u21", "England U21", 4),
        "scotland": ("football.intl.home_nations", "Scotland, Wales, Northern Ireland & Ireland internationals", 3),
        "wales": ("football.intl.home_nations", "Scotland, Wales, Northern Ireland & Ireland internationals", 3),
        "northern_ireland": ("football.intl.home_nations", "Scotland, Wales, Northern Ireland & Ireland internationals", 3),
        "ireland": ("football.intl.home_nations", "Scotland, Wales, Northern Ireland & Ireland internationals", 3),
    },
    "cricket": {
        "england": ("cricket.intl.england", "England (men) internationals", 1),
        "england_women": ("cricket.intl.england_women", "England Women internationals", 2),
    },
}

# National sides only count as "internationals" where the competition is
# plausibly international; a club called e.g. "Wales Bonner FC" never matches
# because the participant name must be exactly the nation.
_INTERNATIONAL_FOOTBALL = {"football.world_cup", "football.euro", "football.nations_league", "football.wc_qualifying",
                           "football.euro_qualifying", "football.international_friendly", "football.other"}
_PPV = re.compile(r"\b(?:ppv|box office|pay per view)\b")
_PUNCT = re.compile(r"[^a-z0-9 ]+")
_SPACE = re.compile(r"\s+")


def norm(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch)).casefold()
    value = value.replace("&", " and ").replace("'", "").replace("’", "")
    value = _PUNCT.sub(" ", value)
    return _SPACE.sub(" ", value).strip()


def sport_id(raw):
    value = norm(raw)
    if value in SPORTS:
        return value
    return SPORT_ALIASES.get(value, "other")


def _country_ok(entry, country):
    allowed = entry["countries"]
    return allowed is None or country in allowed


def _match(table, name, country, codes):
    for entry in table:
        if codes and any(code in entry["codes"] for code in codes):
            return entry
    for entry in table:
        if name in entry["aliases"] and _country_ok(entry, country):
            return entry
    for entry in table:
        if any(name.startswith(p) for p in entry["prefixes"]) and _country_ok(entry, country):
            return entry
    return None


def nation_tags(participants):
    tags = []
    for participant in participants or []:
        found = NATIONS.get(norm(participant))
        if found:
            tags.append(found[0])
    return tags


def classify(event):
    """Return a new event dict with sport/category/tags fields; never mutates input."""
    out = dict(event)
    sport = sport_id(event.get("sport"))
    name = norm(event.get("competition"))
    country = norm(event.get("competition_country"))
    codes = [c for c in [event.get("competition_code")] if c]
    entry = None
    if sport == "rugby":
        # Provider did not state the code; only a named competition can decide it.
        for code in ("rugby_union", "rugby_league"):
            entry = _match(COMPETITIONS[code], name, country, codes)
            if entry:
                sport = code
                break
    else:
        entry = _match(COMPETITIONS.get(sport, []), name, country, codes)
    if entry:
        category = (entry["id"], entry["label"], entry["priority"])
    else:
        category = (sport + ".other", event.get("competition") or "Other " + SPORTS[sport][0].lower(), 90)
    nations = nation_tags(event.get("participants"))
    extra_tags = set()
    if sport in ("boxing", "mma") and _PPV.search(norm(" ".join(str(event.get(k) or "") for k in ("title", "competition", "event_type")))):
        extra_tags.add("ppv")
    if sport == "boxing":
        description = norm(" ".join(str(event.get(k) or "") for k in ("title", "competition", "event_type")))
        if "ppv" in extra_tags or "ppv" in event.get("tags", []):
            category = ("boxing.ppv", "Boxing pay-per-view", 0)
        elif re.search(r"\bpremium\b", description):
            category = ("boxing.premium", "Premium boxing", 1)
    national = NATIONAL_CATEGORIES.get(sport, {})
    international_context = sport != "football" or category[0] in _INTERNATIONAL_FOOTBALL
    for nation in nations:
        if nation in national and international_context:
            category = national[nation]
            break
    out.update({
        "sport": sport,
        "sport_label": SPORTS[sport][0],
        "category_id": category[0],
        "category_label": category[1],
        "category_priority": category[2],
        "competition_id": entry["id"] if entry else None,
        "tags": sorted(set(event.get("tags", [])) | extra_tags | {"team:" + n for n in nations}),
    })
    return out


def typical_minutes(sport):
    return SPORTS.get(sport, SPORTS["other"])[1]


def sport_order(sport):
    return SPORTS.get(sport, SPORTS["other"])[2]
