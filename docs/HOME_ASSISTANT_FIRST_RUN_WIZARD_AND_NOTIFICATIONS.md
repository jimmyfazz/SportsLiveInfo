# SportsLiveInfo Home Assistant App — first-run setup wizard, credentials, scheduler, GitHub and notifications

**Specification date:** 12 November 2026  
**Decision:** MANDATORY for the planned private Home Assistant OS App on the always-on home mini PC (direct HAOS installation, no Proxmox).  
**Status:** detailed implementation specification, **NOT built, installed or runtime tested**.  
**Audience:** developers, coding agents, UI designers and test engineers.

## Executive requirement

The first time the owner opens SportsLiveInfo from Home Assistant, show a **simple, guided first-run welcome/setup screen** (the user called it a splash screen) with:
1. A recognisable, individual card for **every supported/eligible sporting-data supplier**, including what sports it covers, a direct signup/API-key link, masked key-entry field where needed, an **individual Save button**, and a connection/validation status.
2. A simple GitHub publishing setup for the **separate proposed public feed repository**: repository owner/name, branch, permitted JSON path(s), a masked fine-grained GitHub token, **Save** and **Test Connection**. Never confuse the private source repository with the public data destination.
3. Easy schedule controls for sporting API fetch times, UK timezone and GitHub publishing, with visible preview of next jobs and separate **Save Schedule**.
4. A review/Finish screen stating what is configured and what is missing or restricted.

After completing setup the welcome wizard **must not appear automatically again** on restart, Home Assistant update, or ordinary opening. Replace it with a persistent SportsLiveInfo dashboard and Settings pages where every entry can be edited at any time. A **Run Setup Again** action is available from Settings, but must not erase credentials or data without explicit confirmation.

On errors at any future time, use discreet **Home Assistant notifications outside the wizard**, a clear dashboard health section, and detailed local logs. Do **not** interrupt television playback, Home Assistant automations or the owner with repetitive pop-ups, mobile push by default, or spurious "no sport today" failures.

## 1. Actual Home Assistant mechanism — not a literal OS boot splash

Implement as a **Home Assistant App with a small embedded web UI via Ingress** (Home Assistant's own authenticated UI). Do not require inbound ports or a second login. The relevant App configuration is `ingress: true`, `panel_admin: true`, `panel_title: SportsLiveInfo`, with the internal `ingress_port` matching the local web service. Routes/assets must work under the dynamically allocated ingress base path (relative URLs, correct X-Ingress-Path handling); server allows Supervisor ingress origin only. Source: https://contributors.home-assistant.io/apps/guides/ingress/

Distinguish the user-visible setup wizard from the native Home Assistant App **Configuration** tab. The latter uses Supervisor `options`/`schema` and is appropriate for basic defaults; an individual per-supplier **Save/Test** workflow with dynamic provider list requires an app-owned Ingress UI. Do not claim Supervisor automatically supplies this custom wizard. Source: https://contributors.home-assistant.io/apps/guides/options/

### State machine

Persist an explicit schema-versioned setup record in app-managed `/data` (not memory):
- `NEW`: first install, no setup complete; launch directly into wizard.
- `IN_PROGRESS`: supplier/GitHub/schedule entries saved individually. Resume at last step after browser closes, HA reboot or crash.
- `READY_LOCAL`: permitted sources and schedule configured, but public GitHub publisher intentionally disabled or not licensed; local collection may operate and wizard can be marked finished with an **explicit, prominent publication disabled** state.
- `READY_PUBLISH`: configured, validated publisher and licence gates passed; scheduler and publishing can operate.
- `DEGRADED`: formerly ready but a provider or publication connection fails; **dashboard/notifications, never repeat first-run wizard**.
- `MIGRATION_REQUIRED`: configuration schema changed; show one controlled settings banner, never reset stored credentials or force first-run splash.

Only consider setup completed after the owner explicitly selects **Finish Setup**, and valid coverage/configuration checks pass. Require any **enabled** API-key supplier to have a saved key or be marked **Needs attention**, and show how this affects coverage. A provider need not be enabled if legally ineligible or unnecessary. Do not force signups to every listed API: some have no key, duplicate coverage or restrictive non-commercial/redistribution terms.

## 2. Visual/layout and UX acceptance

Design for normal desktop/tablet Home Assistant use with adequate mobile responsiveness:
- Header: **SportsLiveInfo / Welcome / Set up your live sports information**, 4 numbered steps, progress; no autoplay video, blocking modal, excessive logos, flashing animation or marketing copy.
- Steps (sidebar/tabs): **1. Sports APIs** → **2. UK TV sources** → **3. GitHub publishing** → **4. Schedule & review**.
- Each step has short help text, Back/Next controls, auto-persist navigation position, explicit Save at each supplier and on schedules.
- Cards are grouped by sport (Football; All sports; F1; Tennis; Boxing; Cricket; Rugby; UK broadcasting) and sorted by "recommended for personal prototype", "optional supplementary", "no key needed", "restricted/not approved". Search/filter cards if registry expands.
- Each supplier card contains supplier name, website **Open Signup**, **API documentation**, sports/competitions covered, key required? yes/no, free quota displayed as **last checked estimate**, permissions/rights status, enable toggle if eligible, masked key field with reveal control, **Save**, **Test Connection**, and one-line status.
- Test Connection is available per provider and may use **one quota-accounted validation request**; response distinguishes invalid credential, rate limit, blocked licence, endpoint not reachable, API changed, test pending and verified auth. **Verified key does not mean data is accurate, complete or legally publishable.**
- Per-card Save never overwrites, clears or invalidates another supplier's key. If no API key is required show **No API key required** and a harmless **Test Source** action; do not present a fake key field.
- A separate **Recommended minimum setup** summary shows what is likely to cover the chosen sports and what remains missing. Do not force all registrations in order to see Next.
- Provider signup links are *external*, never embedded as forms that gather supplier usernames/passwords; only API tokens are entered here.
- Never display stored keys after saving. Show `Configured ••••1234` only if safe last-four masking, otherwise `Configured`. Provide **Replace Key** and separately confirmed **Remove Key**.
- Highlight errors beside the actual input/action, with precise remediation and an expandable technical detail. A supplier error must not disable other suppliers or erase valid form data.
- All UI controls keyboard accessible, labelled and screen-reader friendly; sufficient focus contrast and responsive spacing.
- Saved settings remain editable in a **Settings > Sporting APIs / UK TV / GitHub / Schedule / Notifications / Advanced** structure after first run.

### Simple supplier card (illustrative design, not a running UI)

    Football-data.org                    Football: EPL, UCL, World Cup
    Free account • key required           Quota/terms: [last checked]
    [Get free API key] [Documentation]
    API key: [••••••••••••••••] [Show]
    [Save] [Test Connection]    Status: Connected / Not set / Needs attention

Each card operates independently. All provider cards should offer a `How to obtain key` disclosure with three short steps and a direct signup URL. Do not imply that all sports or UK channels are covered by one registered provider.

## 3. Initial provider cards and truthful classifications

Use the audited source registry as the single data source for card rendering and permission status. **Availability, quotas, and licences are unverified until adapter-specific tests and terms review.** Initial candidates:

| Source/card | Area | Credentials handling | Setup state |
|---|---|---|---|
| SportsAPI.app | Multi-sport / fixtures | Account key if current plan requires it | Candidate: rate/terms and complete pagination must be checked |
| SportAPI.ai (distinct provider) | Wider football | Key if required | Candidate: account/redistribution terms must be checked |
| football-data.org | Premier League, UCL, World Cup and select competitions | API token | Primary targeted football candidate |
| API-Sports (separate service products) | Football/rugby/F1 supplemental | Key, with sub-product selection | Candidate: price/free rights/coverage to verify |
| Tennis API | ATP/WTA fixtures | API key | Candidate: validate available tournament coverage |
| CricketData.org | Cricket | API key | Candidate: validate free scheduling rights and quotas |
| Boxerbook | Boxing cards and broadcasters | Key | Restricted personal/testing use; never automatically approve for public-feed publishing |
| BoxingAPI.net | Upcoming boxing bouts | Key if required | Candidate: validate actual free fields and rights |
| TheSportsDB | Broad supplementary metadata and TV research | Development/free access key where applicable | Development/restricted; app publication limitation; must not be auto-approved |
| Jolpica-F1 | Race/circuit/session schedule | No API key for public endpoints | Free non-commercial licence; source/test, publication subject to rights review |
| OpenLigaDB | Additional community fixture data | No key for open API | Open Database Licence conditions apply |
| OpenFootball JSON | Public-domain historical/fixture reference | No key | Staleness warning; not sole authority for today's events |
| Open Boxing | Specific boxing title information | No key where public endpoint is available | Coverage and reuse rights to verify |
| Official competition calendar feeds (e.g. Six Nations) | Rugby/other fixtures | Usually no API key, permitted calendar feed | Specific feed/terms check |
| Authorised UK XMLTV/EPG and broadcast references | UK linear TV coverage | URL/import/configuration; possibly user-authorised credentials | Separate step; never promise a generic free UK rights API |

- Include a **manual future provider registry** mechanism so adding/removing adapters does not require rewriting the wizard; disabled adapters show `Not implemented` with a reason and NO pretend save capability.
- Provider-specific signup URLs and how-to instructions must be maintained with dates in `docs/SOURCE_REGISTRY.md`. Never guess direct signup URLs if unavailable; link to verified supplier home/developer page and label it.
- Some suppliers are useful for internal cross-check but *not authorised for public redistribution*: the wizard must make this plain, prevent public export of disallowed derived content, and allow the collector to continue using legally permitted alternatives.
- A new supplier introduced in later updates appears in **Settings > Sporting APIs** with a one-time optional `New provider available` banner; **do not reset completed first-run state**.

## 4. UK television coverage setup

The separate TV-source step includes:
- The default territory **United Kingdom**, user-adjustable only intentionally.
- Source entries for authorised XMLTV files or feeds, permitted official broadcaster data, and a clear status `B1G local EPG matching available later`.
- Test EPG feed retrieval/parsing, sample UK channel count, last updated time and permitted reuse conditions.
- User-selectable `SportsLiveInfo broadcasts verified in feed` or `defer broadcast matching to each B1G device's authorised EPG` where central redistribution permissions are missing.
- Show live versus highlights/repeats distinction and why no channel will be invented. Do not ask for illegal stream links, IPTV passwords or bypassing broadcaster access controls.
- Optional skip if broadcaster data is not yet ready, with the incomplete-field warning.

## 5. GitHub feed destination — separately saved

**Source code remains** `jimmyfazz/SportsLiveInfo` **PRIVATE**. Proposed output is a DIFFERENT, separate public static-data repository, not yet created or authorised. Never automatically make a repo public or create a publishing target without owner approval.

GitHub setup screen fields:
- `GitHub account/owner`: default suggestion `jimmyfazz`, editable.
- `Feed repository`: suggested `SportsLiveInfoFeed` (**proposed name only**, do not claim it exists).
- `Default branch`: `main` unless repository verification says otherwise.
- `Output directory / file`: e.g. `data/today.json` and `data/next-7-days.json`; disallow traversal/arbitrary destinations.
- `Public read URL`: populated **after** confirming static hosting/Pages and actual deployment URL; do not invent or assume one.
- `GitHub write credential`: masked fine-grained personal access token restricted to the single feed repo, Contents: read/write where appropriate, or later a scoped GitHub App installation credential.
- `Publish enabled`: default **OFF** until rights gate and initial validation are complete.
- `Publish only on changed content`: default ON; version/hash; backup last-good.
- `Save GitHub Settings` (independent of sport API saves) and `Test GitHub Connection` (verify owner/repository/branch and token permissions as far as possible; explicit separate dry-run write is required to prove write access).
- If test fails, show whether repository missing, token unauthorised/expired, branch incorrect, repo private when public expected, GitHub API rate limited, publication prohibited by source licence, Pages not deployed, or endpoint unreachable.
- Never ask for the GitHub password. No repository/token is embedded in Android B1G; TVs only fetch rights-approved public HTTPS JSON.
- Public upload includes only explicitly cleared fields. For restricted metadata, collector keeps local cache but omits it from exported payload; no clever masking/rewriting to evade provider terms.

GitHub setup is optional for an initial **READY_LOCAL** installation; but show **No B1G remote feed until publication is approved and configured**.

## 6. Scheduler setup: clear, editable, quota-aware

Display `Timezone: Europe/London (GMT/BST automatic)` prominently. The owner can set all times, enable/disable update windows, and choose additional intervals without knowing cron syntax.

Default *starting recommendations*, subject to provider limits and live benchmark:
- **04:00 UK**: today's fixtures, 7-day priorities, UK broadcast refresh, validate.
- **After successful 04:00 collection**: publish changed, licensed JSON aiming for B1G's **05:00 UK** check. Never promise exact deployment time: GitHub Pages propagation is asynchronous.
- **12:00 UK**: refresh today's remaining fixtures/TV, publish changes after validation.
- **17:00 UK**: evening/late event changes, publish changes.
- **Optional 21:00 UK**: overnight/special-event update if quota budget allows.
- **Tomorrow/next 7 days**: optional daily advance horizon, without downloading every sport/league on each run.
- **B1G**: clients check latest snapshot around 05:00, on app start/wake, and periodically while active; this doesn't consume any supplier credits.
- **Manual Refresh Now** and **Publish Now** buttons in the normal dashboard, subject to approval/budget. Show estimate `requests this run`, used today, remaining today, provider reset times and relevant rate windows before an optional quota-consuming run.

Controls: collection windows toggle + local HH:MM picker; per-source update interval/priority (advanced); publication policy `on changed valid snapshot` (default) / `scheduled` / `manual`; local retention; network retry window; pause/resume; Save Schedule; `Next collection`, `Next possible publish`, `Last success`, `B1G feed updated`.

### Scheduler correctness

- Store IANA timezone and UTC instants; handle transition into/out of BST, wall-clock 04:00 once per local date, no phantom double-run; use stable job IDs and persisted scheduler.
- Provider quotas reset on provider-specific declared timezone, **not** automatically Europe/London. Account for per-minute and daily limits, pagination and multi-source overlap.
- Deduplicate simultaneous requests; all ten TVs consume **zero upstream provider calls**.
- No overlapping collection job; safe per-provider retries/backoff and `Retry-After` handling.
- After Home Assistant reboot/Internet outage, compute catch-up window with quota check; do not fire every missed schedule in a burst.
- Keep existing published and local **last-good snapshot** on failed runs; mark freshness, never send an empty schedule just because the API failed.
- Download/publish need not run at the same minute; publishing waits for validation and explicit licence gate.
- Provider keys and GitHub token stay on HAOS mini PC; B1G read-only HTTPS clients.

## 7. Non-intrusive Home Assistant notifications OUTSIDE wizard

### Owner experience

- Normal working condition: **no routine notification**. SportsLiveInfo dashboard shows a small status line with last successful fetch/publish and next job.
- Recoverable isolated failures: log and show an **amber warning on SportsLiveInfo dashboard**, with an optional Home Assistant notification only if it persists and affects coverage.
- Action-required failures or repeated failures: create **one Home Assistant persistent notification** with useful text and a link to SportsLiveInfo diagnostics.
- Critical failures: public feed stale past a configurable threshold, all selected provider sources unavailable, app storage failure, loss of GitHub publication for a full expected cycle, unauthorised token, or licence gate blocking publishing; show a persistent notification. Do not send mobile push/siren/pop-up by default.
- Repeat of same incident: **update the existing notification** instead of generating multiple new ones. Use a stable `notification_id` per incident category/provider and a cooldown; on confirmed recovery, dismiss the corresponding notification or replace it with a quiet resolved status in dashboard. Prevent re-alerting an acknowledged incident on every refresh.
- All previous and current incidents remain available within **SportsLiveInfo > Diagnostics > Error history**, even if HA notification is dismissed.
- Let owner optionally choose `Information only (dashboard)`, `Warnings after N failures`, or `Action required only`; initial default is **action-required only** with persistent notifications. Separate opt-in for urgent mobile push/email (not automatic).

### Notification text requirements

Each alert should have:
1. Concise subject and severity;
2. Specific failing supplier or GitHub publication component;
3. **What failed** and a meaningful sanitized error message/code (401/403, 429, timeout, parser, etc.);
4. **Effect on B1G** (still using cached feed, missing one sport, stale since particular local time, publishing blocked);
5. **Last successful attempt** and the next retry time;
6. Clear action (e.g. replace key, verify permissions, check quota, check source URL) and link/path to Settings or Diagnostics.

Example (fictional):

    SportsLiveInfo — Football API needs attention
    Source: football-data.org
    Error: 401 Unauthorized — supplied API key rejected
    Impact: Football fixtures cannot be refreshed. B1G remains on the
    last verified feed from 04:10 UK; tennis/F1 continue normally.
    Last successful fetch: 11 Nov, 17:00 UK
    Next attempt: 12 Nov, 12:00 UK
    Action: Open SportsLiveInfo > Settings > Sporting APIs, replace
    the key, Save, and Test Connection.
    Diagnostic code: SLI-PROVIDER-AUTH-001

### Home Assistant integration strategy and permissions

Home Assistant supports `persistent_notification.create` with `notification_id` (same ID overwrites), and `persistent_notification.dismiss`:
- https://www.home-assistant.io/actions/persistent_notification.create/
- https://www.home-assistant.io/integrations/persistent_notification/

Technical App path: `homeassistant_api: true` permits using the Supervisor Core REST proxy `http://supervisor/core/api/services/persistent_notification/create` with app `SUPERVISOR_TOKEN`; standard Home Assistant REST service payload. **Security warning:** `homeassistant_api: true` grants broad Home Assistant Core administrator API access to the App. Do NOT enable without explicit security review, minimum attack surface and ingress-only access. Sources: https://contributors.home-assistant.io/apps/supervisor-api/core/ and https://contributors.home-assistant.io/apps/reference/configuration/

**Preferred least-privilege alternative when feasible:** a very small Home Assistant companion custom integration reads a local incident/health state produced by the App and calls `persistent_notification.create` through Home Assistant's own internal API; the long-running sport collector still stays outside HA Core. Evaluate security and maintenance burden versus the direct Core API route. Document the actual chosen method before implementation. Do not ask for an owner-issued long-lived HA admin token just to generate notices if avoidable.

### Error taxonomy and default handling

| Code family | Condition | Default presentation |
|---|---|---|
| SLI-PROVIDER-AUTH | 401/403, invalid/expired provider key | HA notification when enabled source cannot recover; in-card red action |
| SLI-PROVIDER-QUOTA | 429, daily quota depletion, unexpected high consumption | Dashboard amber; HA notice if blocks important coverage |
| SLI-PROVIDER-NET | Timeout, DNS, TLS, server 5xx | Retry/backoff, dashboard warning; HA notice after threshold |
| SLI-SCHEMA | Supplier changed JSON schema or missing required fields | Provider warning; retained last-good data; HA notice if persistent |
| SLI-COVERAGE | Critical league absent, pagination incomplete, conflicting fixture times | Dashboard amber, confidence/incompleteness; avoid fabricated claims |
| SLI-TV | EPG missing, UK channel ambiguous, rights unknown | Warning/unknown broadcast; HA notification only systemic outage |
| SLI-GITHUB-AUTH | Token invalid, no repository permission | HA action-required, pause publishing, keep last-good public feed |
| SLI-GITHUB-PUBLISH | Push failed, branch missing, Pages failed or stale CDN | Retry; HA notice when scheduled publishing deadline missed |
| SLI-LICENCE | Source lacks permission for proposed public output | Block only restricted fields, visible action-required |
| SLI-CACHE | Low disk, SQLite failure/corruption, invalid published snapshot | HA critical if no usable last-good snapshot |
| SLI-SCHEDULER | Missed run, time-zone error, overlapping jobs, crash | Dashboard/HA depending missed 05:00 output |
| SLI-SETUP | Setup not completed or optional key omitted | Wizard status / dashboard only; no noisy recurring HA notices |

**Never include** a provider API key, GitHub token, full private raw response, embedded password, internal network address, or unapproved personal information in HA notifications or logs.

## 8. Secure storage, backups, startup behaviour

- Store key material in a restricted, persistent App configuration store under `/data`, access limited to App process. Prefer Home Assistant Supervisor `password` option fields or a secure supported secret mechanism where practical. The Supervisor's `/data/options.json` contains **resolved plaintext secret values**, so it is not itself encrypted-at-rest. Do not falsely claim Home Assistant masks in the UI mean encryption. Assess whether a dedicated minimal-permission secret file is preferable for dynamic per-provider saves.
- Secrets must not be returned by the app UI's "list providers" endpoint; never echo them on load; store only a configured boolean and non-sensitive key identifier.
- Use CSRF protection for all ingress UI state-changing requests, server-side field validation, authentication provided by HA ingress, admin-only control, and safe relative URL routing.
- Separate credentials from non-secret settings and version schema; atomic writes; tests for failed write, restart, backup/restore, upgrade/migration, multi-tab editing, concurrent Save and accidental Remove.
- HAOS backup may contain secrets: describe and recommend protecting/encrypting backups and retaining them securely. No browser localStorage/sessionStorage for API credentials.
- Publisher token scoped narrowly to eventual **feed repository**, not owner-wide; prevent unapproved toggling of public publishing.
- Collector can run/restart while wizard is incomplete, but only activated providers with valid credentials run; no public publishing until setup completed **and** rights verified. Use conservative resource scheduling so HA household automations are unaffected.

## 9. Acceptance matrix — REQUIRED before marking wizard 'done'

- [ ] On first-ever Open Web UI, wizard appears, with appropriate provider cards and accurate signup/docs links (no misleading unavailable key fields).
- [ ] Each enabled key-required provider has separate masked input, **Save**, **Test Connection**; a saved key survives app restart and upgrade; saving provider A doesn't erase B.
- [ ] No-key providers visibly say so; restricted/unimplemented suppliers cannot be implicitly enabled for public publication.
- [ ] Wrong key gives correct one-source error; valid key verified with minimal quota; show last test status and time; HTTP errors do not leak keys.
- [ ] Wizard supports Back/Next, interruption/resume, partial completion, editing mistakes, and no forced full-provider registration.
- [ ] GitHub settings have an independent Save/Test, narrow token/repo permission, clear distinction between private source and separate proposed public feed, and default publish OFF until licence clearance.
- [ ] Scheduled collection, local timezone, quota estimate, GitHub change-only publishing, Next Run preview and Save Schedule are functional after implementation.
- [ ] Test 05:00 B1G freshness, UK GMT/BST dates, catch-up after outage, 429, publication delay and last-good fallback.
- [ ] Finish Setup persists and **never reopens automatically** on normal restart, update or later supplier addition; owner can re-open intentionally.
- [ ] Normal operation produces no notifications. Three repeated provider failures produce at most one updated HA notice; transient failures remain in dashboard.
- [ ] HA notice is comprehensive but concise, contains actual impact/recovery and a diagnostic code; no credentials in notification or logs.
- [ ] Notification recovery/dismissal works, historic errors remain in app diagnostics, owner can snooze/adjust severity.
- [ ] Test Home Assistant API permissions/security before enabling direct Core notification calls. Prefer least-privilege notification bridge if reasonable.
- [ ] Ten concurrent B1G clients download cached feed and do **not** increase provider API-call counters.
- [ ] No inbound WAN ports opened; Home Assistant lighting/heating/blinds continue unaffected.
- [ ] This is documented as a **specification** until actual app/UI code, installation, runtime tests and device verification are complete.

## 10. Authoritative references

- [Home Assistant embedded Ingress web UI](https://contributors.home-assistant.io/apps/guides/ingress/)
- [Home Assistant App configuration options, schema and password input](https://contributors.home-assistant.io/apps/guides/options/)
- [Home Assistant App API permissions](https://contributors.home-assistant.io/apps/reference/configuration/)
- [Home Assistant Core REST proxy](https://contributors.home-assistant.io/apps/supervisor-api/core/)
- [Persistent notification create and stable IDs](https://www.home-assistant.io/actions/persistent_notification.create/)
- [Persistent notifications integration](https://www.home-assistant.io/integrations/persistent_notification/)
- [GitHub fine-grained token permissions](https://docs.github.com/en/rest/authentication/permissions-required-for-fine-grained-personal-access-tokens)
- [SportsLiveInfo source registry](SOURCE_REGISTRY.md)
- [Primary bare-metal Home Assistant OS deployment](HOME_ASSISTANT_BARE_METAL_PRIMARY.md)
