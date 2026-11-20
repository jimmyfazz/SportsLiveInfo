"""Link diagnostics on a stored SportsLiveInfo snapshot: the binds dry run and the link-coverage gap histogram.

    PYTHONPATH=sportsliveinfo/src python3 tools/link_report.py --db /data/sportsliveinfo.sqlite3 [--titles] [--public]

Read-only. Reads the materialised ``sports`` snapshot (private, full merge; ``--public`` reads ``sports-public``) and
prints JSON: what switching ``binds_rule`` from "legacy" to "narrow" changes (binds true->false per market, the demoted
links) and why events have no channel link (``broadcast_gap`` histogram, overall and per tier). Titles are printed only
with ``--titles`` and never leave this terminal; the health asset carries ids and counts only.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sportsliveinfo" / "src"))

from sportsliveinfo import feed, link_report  # noqa: E402
from sportsliveinfo.storage import Store  # noqa: E402


def report_from_store(store, *, public=False, titles=False):
    snapshot = store.snapshot("sports-public" if public else "sports") or {}
    events = (snapshot.get("data") or {}).get("events") or []
    policy = feed.link_policy(store.config())
    return {"snapshot": "sports-public" if public else "sports",
            "generated_at": (snapshot.get("data") or {}).get("generated_at"),
            "binds_rule_in_force": policy.binds_rule,
            "binds_dry_run": link_report.dry_run_binds(events, private=not public, titles=titles,
                                                       own_epg=policy.own_epg),
            "link_coverage": link_report.link_coverage(events, private=not public, tier_of=feed.event_tier)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--db", required=True, help="path to the App's SQLite file (Home Assistant: /data/...)")
    parser.add_argument("--public", action="store_true", help="read the approved-source (public) snapshot")
    parser.add_argument("--titles", action="store_true", help="include event titles in the demoted list (local only)")
    args = parser.parse_args(argv)
    path = Path(args.db)
    if not path.is_file():
        parser.error("no such database: %s" % path)
    print(json.dumps(report_from_store(Store(path), public=args.public, titles=args.titles), indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
