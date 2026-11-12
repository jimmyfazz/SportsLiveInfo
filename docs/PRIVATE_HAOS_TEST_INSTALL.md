# Test-install private SportsLiveInfo in Home Assistant OS

**Status:** 12 November 2026 — documented installation procedure, **not yet run on the owner's HAOS**.
**For:** a private GitHub source repository; no publication of source code, provider credentials or stream URLs.

Home Assistant Supervisor reads either a reachable Git repository or the local `local_apps` folder. The private `jimmyfazz/SportsLiveInfo` source cannot be assumed cloneable by the Supervisor's ordinary Git URL without authentication. **Do not add the public `LiveSports-EPG` repository to the Apps store: it contains only JSON data/distribution documentation.**

Reference: [Home Assistant contributors: Your first app](https://contributors.home-assistant.io/apps/first-app/), [How apps work](https://contributors.home-assistant.io/apps/how-apps-work/), [Test your app](https://contributors.home-assistant.io/apps/guides/testing/).

## First installation on the owner's Mac + HAOS

1. On a Mac browser **signed in to GitHub with access to the private repository**, open [SportsLiveInfo](https://github.com/jimmyfazz/SportsLiveInfo). Switch to the desired branch (for the GUI work, `feat/haos-operator-dashboard-ux-20261112`). Choose **Code → Download ZIP**; extract it on the Mac. Alternatively use your existing authenticated Git client to clone/checkout the branch. Never copy an authentication token into the app files.
2. Locate the **inner** `sportsliveinfo` folder in the extracted repository. It must directly contain `config.yaml`, `Dockerfile`, `src/sportsliveinfo/`, `icon.png`, `logo.png`, `DOCS.md`, `README.md` and `CHANGELOG.md`. Do not copy the outer repository directory as the app itself.
3. On Home Assistant OS, install and configure the **Samba share** app (or use the Terminal & SSH app). On the Mac open Finder → **Go → Connect to Server** (`Cmd`+`K`) → `smb://homeassistant.local` (or the local hostname already configured), then sign in using the Samba account. This is a LAN share, not internet/port-forwarding.
4. Open the shared `local_apps` folder (older shares may also call it `addons`). Copy the inner app folder into it so the result is **`local_apps/sportsliveinfo/config.yaml`**, not `local_apps/SportsLiveInfo-main/sportsliveinfo/config.yaml` nested incorrectly.
5. In HAOS, open **Settings → Apps → Install app**. Refresh/reload the store if necessary. Under **Local apps** select **SportsLiveInfo**, install, then enable **Start on boot** and start. Ingress entry point: **Open web UI**. The full app slug for this local installation is `local_sportsliveinfo`.
6. On first start, use **Sources & API keys** to enable only needed services. `jolpica` is enabled by default; EPG collection is disabled by default. Test a no-key sports source before adding optional keys. Set London-time refresh slots and finish setup. Publishing to GitHub is strictly **optional**, remains disabled by default and is rights-gated. Do not paste a GitHub publishing token into any source files or HAOS shell.
7. Check **Overview**, **Live today**, **Sports events**, **EPG coverage** and **Diagnostics**. A blank sports/EPG catalogue before a successful collection is expected. Confirm there is no external/host port exposed and no automatic public JSON publication.

## Updating a private development build

1. Download the newer branch ZIP (or update the authenticated Mac checkout).
2. Stop the `local_sportsliveinfo` app. Copy the new contents of the *inner* `sportsliveinfo` folder into the existing `local_apps/sportsliveinfo` directory; **do not delete the HAOS app's private `/data` volume**.
3. Reload the app store and select **Rebuild** (or use `ha apps rebuild local_sportsliveinfo` from HA's authorised Terminal & SSH environment), then start. Rebuild is important because the same experimental `version` may be reused on test branches.
4. Confirm saved sources and masked keys are still present. Export a backup before an experimental upgrade. A backup containing /data is sensitive because it can include API keys.

## Troubleshooting

| Symptom | Check |
|---|---|
| Local app does not appear | Ensure `local_apps/sportsliveinfo/config.yaml` is the actual path; reload store; inspect **Settings → System → Logs → Supervisor** for schema/clone failures. |
| Start/build fails | Inspect app **Log** and Supervisor logs, verify amd64/aarch64 supported, Docker build labels and base-image pull. No local Docker/device build has been verified yet. |
| UI cannot open | Use **Open web UI** through Home Assistant Ingress, not a host IP:8099 URL. Check the Supervisor proxy peer IP against `SLI_INGRESS_TRUSTED_IPS` only if authenticated requests are denied; never disable ingress security as a shortcut. |
| Source test fails | Check network/DNS, API key status, daily request budget and licence/region restrictions; an XMLTV feed with expired programmes intentionally fails validation. |
| No public feed | This is expected until the owner's fine-grained publishing token, explicit source rights and a reviewed preview are all present. Never use a local IPTV subscription playlist as a public test fixture. |

## Release limits

This installation procedure has not been verified on the target mini PC. Until actual device checks pass, the app remains experimental. A one-click public app repository is a **separate distribution decision**: it would require publicly accessible app packaging/image while the full GitHub source stays private, and an authenticated/reproducible build pipeline. Do not change the private repository visibility to solve testing.
