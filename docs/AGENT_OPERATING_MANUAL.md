# Agent operating manual — SportsLiveInfo (every AI agent, every session)

**Owner instruction (15 Nov 2026):** one set of working rules for every agent: Claude Code, Codex/ChatGPT, terminal or cloud. The B1 repository has the same manual for the TV app (`jimmyfazz/B1`, `docs/AGENT_OPERATING_MANUAL.md`). What is true now is in [`CURRENT_STATUS.md`](CURRENT_STATUS.md) and the latest handover ([`HANDOVER_2026-11-15_SPORTSLIVEINFO_B1G.md`](HANDOVER_2026-11-15_SPORTSLIVEINFO_B1G.md)). The binding product rules are in [`../AGENTS.md`](../AGENTS.md).

## 1. Start of every session

1. Read [`CURRENT_STATUS.md`](CURRENT_STATUS.md), this manual and the latest handover.
2. `git fetch origin && git status && git log --oneline -5 origin/main`. Work from current `origin/main`.
3. List open pull requests in this repo **and in B1**. Never start a parallel fix for something already in progress.
4. Write down the owner's request in one line and the observable result that proves it ("ITV1 is the first link for Spain v England in the published feed").

## 2. The design rule (owner)

**SportsLiveInfo makes the decisions; B1G follows the feed.** The owner will not update ten TVs for each fix. Put every decision here and publish it as data: fixtures, channel links and their order (`rank`), whether a link may name the channel (`binds`), the LIVE window (`live_until_utc`), channel identities (dictionary, `guide_map`), tiers and featured fixtures. A new kind of decision needs a contract addition ([`FEED_CONTRACT_SLI_V1.md`](FEED_CONTRACT_SLI_V1.md) §4.3) and a one-time B1G reader change. Every addition must be backward compatible.

## 3. Diagnose before changing

- Root cause with evidence: file:line, the live feed (`LiveSports-EPG/v1/manifest.json` and its assets), the App log on Home Assistant, or a reproduced case.
- Build tests from the real case (see `tests/test_ranking_and_reruns.py`).
- No guessed fixes. A change that only moves a number is not a fix.

## 4. Gate, release and deploy

```sh
python3 -m compileall -q sportsliveinfo/src tests
PYTHONPATH=sportsliveinfo/src python3 -m unittest discover -q -s tests   # a MemoryError line from a mock is expected
PYTHONPATH=sportsliveinfo/src python3 tools/generate_feed_fixtures.py     # after any wire or version change
```

- CI (`.github/workflows/verify.yml`) runs on every PR. This repo is public, so Actions run.
- After a wire change, copy `schemas/fixtures/sli-v1/v1` into B1's `platforms/android/app/src/test/resources/sli-v1-6/` so B1's interop test reads the same golden feed.
- Release and Home Assistant deploy: follow handover §3 exactly. Bump every version file; the owner merges; back up the App first; refresh the store; update; check the version and the "Ingress HTTP ready" log line; check the next published manifest.
- One task per branch from `origin/main`, small PRs, and **the owner merges**. Never merge or deploy without the owner's request in that conversation.

## 5. Rules that must not break

- No public EPG programme text unless its public rights are documented. Guide-listed events and loose links stay in the private feed.
- TVs are read-only: no keys, tokens or uploads from a TV. The owner's channel list, stream URLs and credentials never reach any feed, log or commit.
- No paid providers or paid CI without the owner. No LLM calls at runtime.
- Never claim a merge, deploy or test you did not check. Report what you did not run as **NOT RUN**.

## 6. Recording what you did

Every PR updates `sportsliveinfo/CHANGELOG.md`, [`CURRENT_STATUS.md`](CURRENT_STATUS.md) when the state changes, and [`IMPLEMENTATION_PROGRESS.md`](IMPLEMENTATION_PROGRESS.md) with real results. Do not add new "start here" banners; update the status page. Superseded documents move to `docs/archive/` with `git mv` and fixed links.

## 7. When to stop and ask the owner

Ask before:
- merging, deploying or changing Home Assistant;
- spending money or adding a provider;
- publishing new kinds of data publicly;
- deleting branches or files.
