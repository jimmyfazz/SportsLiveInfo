# Current implementation and verification status

**13 November 2026 · SportsLiveInfo 0.3.4 integration.** This revision combines the mobile dashboard, regional EPG and sports work with [Claude’s 13 November audit](CODE_AUDIT_AND_FIXES_2026-11-13.md). The public [SportsLiveInfo source repository](https://github.com/jimmyfazz/SportsLiveInfo) builds the Home Assistant App. [LiveSports-EPG](https://github.com/jimmyfazz/LiveSports-EPG) is the separate data destination. Credentials, private guide programmes and App settings stay on Home Assistant.

- **Dashboard:** Compact mobile navigation, scoped refresh, group source saves, collapsible settings, current Live Today estimates, UK-date event filtering and pagination.
- **Collector:** Separate full-discovery timestamp, safe retention on incomplete sports responses, source-specific guide errors, expired guide tests and scheduler heartbeat. Guide matching loads one saved feed at a time. Full indexed SQLite programme storage and host resource profiling remain open.
- **Coverage:** Retains US/Canada EPG repairs and adds opt-in regional sources, tennis and the expanded boxing and multi-sport catalogue. Provider entitlements, specialist boxing/PPV listings and local Sky/iptv-org grabber integration still require validation.
- **Publication:** `sli/1.0` preview and optional rights-gated publishing, with a rights register and serialized preview/publish operations. The feed carries no private programme rows. Provisional channel matches cannot establish playability.
- **Packaging:** Configuration, build metadata and Python runtime all identify 0.3.4. Existing local installations should follow the [in-place upgrade steps](../sportsliveinfo/DOCS.md).

## Validation

```sh
python3.12 -m compileall -q sportsliveinfo/src
PYTHONPATH=sportsliveinfo/src python3.12 -m unittest discover -s tests -q
```

**Local result:** 199 tests passed (v0.3.8, 13 Nov 2026; adds the UK/Europe channel identity dictionary, provider prefix grammar, standard XMLTV prologue handling and retires four dead guides). A rights-approved publication to LiveSports-EPG succeeded from Home Assistant on 13 Nov 2026 (commit `a1743de`, 3,284 events). Chromium could not start because the runner blocked socket creation. The offline suite includes fixture-retention, guide expiry and corrupt input, broadcaster matching and index equivalence, feed integrity, credential persistence and Ingress tests. Actual Docker builds, Supervisor upgrade and restart, live source measurements, rights-approved publication, and B1G device acceptance remain open. See [implementation progress](IMPLEMENTATION_PROGRESS.md) for the integration receipt and [document index](DOCUMENTATION_INDEX.md) for earlier records.
