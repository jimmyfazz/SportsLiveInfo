# Licensing, provenance, private development and £0 hosting

## Core rule: free != republishable

An API may be free to request but contractually restricted for commercial use, app distribution, caching, bulk download, artwork, attribution or redistribution. **A private GitHub repository does not automatically permit restricted data use.** Never assume GPL/MIT on an EPG collector also licences the programme information it processes.

Research references checked 2026-11-12:
- TheSportsDB: https://api.thesportsdb.com/docs_terms_of_use.php — free API is development-oriented; app-store publication requires paid subscriber; third-party content/image rights separately apply.
- Boxerbook: https://boxerbook.com/terms and https://boxerbook.com/developers — free personal/non-commercial/testing API; commercial usage is paid.
- Jolpica-F1: https://github.com/jolpica/jolpica-f1/blob/main/TERMS.md — CC BY-NC-SA 4.0, non-commercial.
- EPG collector https://github.com/noodlemctwoodle/epg-guide — GPLv3 code, original TV programme content rights reserved to providers.
- OpenFootball: https://github.com/openfootball/football.json — CC0 public-domain football dataset; verify upstream freshness.
- Freeview-EPG: https://github.com/dp247/Freeview-EPG — GPLv3 code, personal-use EPG reference.
- FootballData https://www.football-data.org/pricing ; SportsAPI https://sportsapi.app/ ; Tennis API https://docs.tennis-api.com/getting-started ; CricketData https://cricketdata.org/pricing — terms and redistribution permission to be rechecked before publication.

### Source approval statuses

Research / prototyping: provider terms allow the intended test use; keys private; do not share provider payload.
Internal use: check provider agreement covers the consuming app and devices/accounts; store attribution/caching restrictions.
Public feed/app distribution: require **explicitly permitted** redistribution and app-store usage. If not clear, obtain permission or exclude the source and derived restricted fields.

Store a record of approved terms, date, source URL, use category, allowed output, caching limits, attribution and reviewer decision per adapter. Never create a secret backchannel to evade limits.

## GitHub account costs and repository visibility

- Repository SportsLiveInfo was **private** when inspected on 2026-11-12. Keep private until user changes that instruction.
- GitHub Free advertises **2,000 Actions minutes/month** for private repositories on standard hosted runners (account-wide usage matters): https://github.com/pricing and https://docs.github.com/en/actions/concepts/billing-and-usage. Check current billing display, configure safeguards and avoid excessive cron runs.
- GitHub Actions can schedule as often as every 5 minutes but jobs can be late/dropped and should not be treated as hard realtime: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows.
- **GitHub Pages is only available from public repositories on GitHub Free**. Private repo Pages requires eligible paid plan: https://docs.github.com/en/pages/getting-started-with-github-pages. Do not enable Pages or publish an open feed from this private repo.
- Development alternative: a local JSON file or private CI artifact. For app integration later choose authenticated private distribution or a separately permitted public static feed on a public host; do not expose GitHub personal access tokens in Android.
- GitHub Actions secret store for API keys; GitHub code/datasets must not include provider tokens, account credentials or personally identifiable identifiers.
- A free-tier host can change quotas or suspend service. Document actual usage and avoid dependency on free hosting as a guaranteed SLA.

## Distribution decision gate

Before changing repository visibility, serving JSON to clients, or pushing an Android app publicly:
1. Written/recorded licence rights for every underlying source, including event and broadcast metadata, check whether aggregation/derived facts are allowed.
2. Scraping/robots/ToS assessment for EPG and official broadcaster schedules.
3. Attribution and images/trademarks review; omit logos if rights unclear.
4. Key storage + reasonable public API abuse/rate protection.
5. Output audit: no raw licensed EPG blocks or proprietary images unless authorised.
6. Data retention/caching rights, terms-change process, and takedown route.

This is an engineering risk register, not legal advice. No code or project licence is selected yet; do not assume repository software can be reused publicly until a licence is explicitly chosen.
