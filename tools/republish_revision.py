#!/usr/bin/env python3
"""Roll the public feed back by republishing a retained earlier revision as a NEW revision (RUNBOOK section 5).

Why a new revision: B1G ignores any manifest whose ``generated_at`` is older than the one it already holds, so
restoring the old manifest bytes changes nothing on the TVs. This tool builds a manifest from a previous revision's
asset set with a fresh ``generated_at``/``expires_at``, a new ``revision`` id and ``previous_revision`` pointing at the
manifest being replaced. ``refresh.collected_at`` is left as it was: the data really is that old.

Dry run by default: it prints what it would write. ``--apply`` writes ``v1/manifest.json`` and
``v1/manifests/<new revision>.json`` into the clone; committing and pushing stay manual (one commit, no force-push).

    python3 tools/republish_revision.py --repo ~/LiveSports-EPG --revision <old revision>            # dry run
    python3 tools/republish_revision.py --repo ~/LiveSports-EPG --revision <old revision> --apply
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = "v1"
EXPIRES_AFTER = timedelta(hours=48)       # same as feed.build_feed


def _json(value):
    # The App's own serialisation (feed._json): sorted keys, compact separators.
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _stamp(moment):
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def _parse(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def build_rollback_manifest(old, current, now):
    """The manifest that republishes ``old``'s asset set. Pure: no file or network access.

    ``current`` is the manifest being replaced (its revision becomes ``previous_revision`` and its ``generated_at``
    must be older than ``now``, or readers would ignore the result too)."""
    if not isinstance(old, dict) or not old.get("assets") or not old.get("revision"):
        raise ValueError("the old manifest has no revision or assets")
    now = now.astimezone(timezone.utc).replace(microsecond=0)
    if current and current.get("generated_at") and now <= _parse(current["generated_at"]):
        raise ValueError("now (%s) is not newer than the current manifest's generated_at (%s): check the clock"
                         % (_stamp(now), current["generated_at"]))
    manifest = json.loads(json.dumps(old))
    manifest["generated_at"] = _stamp(now)
    manifest["revision"] = hashlib.sha256(("rollback:%s:%s" % (old["revision"], _stamp(now))).encode()).hexdigest()[:20]
    manifest["previous_revision"] = (current or {}).get("revision")
    manifest["rollback_of"] = old["revision"]
    refresh = manifest.setdefault("refresh", {})
    refresh["expires_at"] = _stamp(now + EXPIRES_AFTER)
    notices = list(manifest.get("notices") or [])
    notices.append("Rollback: republished revision %s (originally generated %s) at %s." % (
        old["revision"], old.get("generated_at"), _stamp(now)))
    manifest["notices"] = notices
    return manifest


def missing_assets(manifest, exists):
    """Paths of the manifest's assets for which ``exists(path)`` is false (retention drops old revisions' assets)."""
    return [a["path"] for a in manifest.get("assets") or [] if not exists(a["path"])]


def corrupt_assets(manifest, read):
    """Paths whose bytes no longer match the manifest's sha256 (``read(path)`` returns bytes)."""
    return [a["path"] for a in manifest.get("assets") or []
            if hashlib.sha256(read(a["path"])).hexdigest() != a.get("sha256")]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", required=True, type=Path, help="local clone of the feed repository (LiveSports-EPG)")
    parser.add_argument("--revision", required=True, help="revision id to republish (file v1/manifests/<id>.json)")
    parser.add_argument("--apply", action="store_true", help="write the new manifest files (default: dry run)")
    args = parser.parse_args(argv)

    old_path = args.repo / ROOT / "manifests" / ("%s.json" % args.revision)
    current_path = args.repo / ROOT / "manifest.json"
    if not old_path.is_file():
        sys.exit("No retained manifest %s (the App keeps the last 10 revisions; older ones are in git history)" % old_path)
    old = json.loads(old_path.read_text(encoding="utf-8"))
    current = json.loads(current_path.read_text(encoding="utf-8")) if current_path.is_file() else None
    try:
        manifest = build_rollback_manifest(old, current, datetime.now(timezone.utc))
    except ValueError as exc:
        sys.exit(str(exc))
    gone = missing_assets(manifest, lambda p: (args.repo / p).is_file())
    if gone:
        sys.exit("%d asset file(s) of that revision are no longer in the working tree (restore them from git "
                 "history first), e.g. %s" % (len(gone), gone[0]))
    bad = corrupt_assets(manifest, lambda p: (args.repo / p).read_bytes())
    if bad:
        sys.exit("%d asset file(s) do not match their sha256, e.g. %s" % (len(bad), bad[0]))
    data = _json(manifest)
    print("%s: republish %s (generated %s) as %s, generated_at %s, expires_at %s, %d assets, replaces %s" % (
        "APPLY" if args.apply else "DRY RUN", old["revision"], old.get("generated_at"), manifest["revision"],
        manifest["generated_at"], manifest["refresh"]["expires_at"], len(manifest["assets"]),
        manifest["previous_revision"]))
    if not args.apply:
        print("Nothing written. Re-run with --apply, then commit v1/manifest.json and v1/manifests/%s.json as one new "
              "commit (see docs/RUNBOOK.md section 5)." % manifest["revision"])
        return 0
    (args.repo / ROOT / "manifests" / ("%s.json" % manifest["revision"])).write_bytes(data)
    current_path.write_bytes(data)
    print("Written. Commit and push as a normal commit (no force-push).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
