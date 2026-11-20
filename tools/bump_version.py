#!/usr/bin/env python3
"""Release version bump and consistency check (audit 15 Nov, release mechanics).

The App version lives in three places that must agree: ``sportsliveinfo/config.yaml`` (``version``), the
``ARG BUILD_VERSION`` default in ``sportsliveinfo/Dockerfile`` and ``__version__`` in
``sportsliveinfo/src/sportsliveinfo/__init__.py``.

    python3 tools/bump_version.py --check              # exit 1 when the three disagree (CI runs this)
    python3 tools/bump_version.py 0.3.25 --title "Operations hardening"
    python3 tools/bump_version.py 0.3.25 --dry-run     # show what would change

A bump rewrites the three files and, in ``sportsliveinfo/CHANGELOG.md``, inserts ``## X.Y.Z - <title>`` above the
newest section and turns every ``## Unreleased - <topic>`` heading above the previous release into a ``### <topic>``
subsection of it. It never commits. Afterwards run ``PYTHONPATH=sportsliveinfo/src python3 tools/generate_feed_fixtures.py``
(the manifest carries the version) and the unit gate.
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "config.yaml": ("sportsliveinfo/config.yaml", re.compile(r'^(version:\s*")([^"]+)(")', re.M)),
    "Dockerfile": ("sportsliveinfo/Dockerfile", re.compile(r"^(ARG BUILD_VERSION=)(\S+)()", re.M)),
    "__init__.py": ("sportsliveinfo/src/sportsliveinfo/__init__.py", re.compile(r'^(__version__\s*=\s*")([^"]+)(")', re.M)),
}
CHANGELOG = "sportsliveinfo/CHANGELOG.md"
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
_HEADING = re.compile(r"^## (.*)$", re.M)
_UNRELEASED = re.compile(r"^## Unreleased(?:\s*[\u2014-]\s*(.*))?\s*$")
_RELEASED = re.compile(r"^## \d+\.\d+\.\d+\b")


def read_versions(root=ROOT):
    """{file name: version string or None} for the three version files."""
    out = {}
    for name, (path, pattern) in FILES.items():
        try:
            match = pattern.search(Path(root, path).read_text(encoding="utf-8"))
        except OSError:
            match = None
        out[name] = match.group(2) if match else None
    return out


def versions_agree(versions):
    values = set(versions.values())
    return len(values) == 1 and None not in values


def changelog_with_release(text, version, title):
    """CHANGELOG text with the release heading inserted and the unreleased topics nested under it."""
    lines = text.split("\n")
    first = next((i for i, line in enumerate(lines) if line.startswith("## ")), len(lines))
    end = next((i for i, line in enumerate(lines) if i >= first and _RELEASED.match(line)), len(lines))
    for index in range(first, end):
        match = _UNRELEASED.match(lines[index])
        if match:
            lines[index] = "### " + ((match.group(1) or "").strip() or "Other changes")
    heading = "## %s — %s" % (version, title or "Release")
    lines[first:first] = [heading, ""]
    return "\n".join(lines)


def bump(root, version, title=None, dry_run=False):
    """Rewrite the three version files and the CHANGELOG. Returns the list of files changed."""
    if not SEMVER.match(version):
        raise ValueError("version must look like 0.3.25")
    changed = []
    for name, (path, pattern) in FILES.items():
        target = Path(root, path)
        text = target.read_text(encoding="utf-8")
        if not pattern.search(text):
            raise ValueError("no version found in " + path)
        updated = pattern.sub(lambda m: m.group(1) + version + m.group(3), text, count=1)
        if updated != text:
            changed.append(path)
            if not dry_run:
                target.write_text(updated, encoding="utf-8")
    log = Path(root, CHANGELOG)
    text = log.read_text(encoding="utf-8")
    if not re.search(r"^## %s\b" % re.escape(version), text, re.M):
        changed.append(CHANGELOG)
        if not dry_run:
            log.write_text(changelog_with_release(text, version, title), encoding="utf-8")
    return changed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("version", nargs="?", help="new version, e.g. 0.3.25")
    parser.add_argument("--title", help="CHANGELOG heading text")
    parser.add_argument("--check", action="store_true", help="only verify that the three files agree")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.check or not args.version:
        versions = read_versions()
        print(", ".join("%s=%s" % item for item in versions.items()))
        if not versions_agree(versions):
            print("version files disagree: run tools/bump_version.py <version>", file=sys.stderr)
            return 1
        return 0
    try:
        changed = bump(ROOT, args.version, args.title, args.dry_run)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(("would change: " if args.dry_run else "changed: ") + (", ".join(changed) or "nothing"))
    if not args.dry_run:
        print("next: PYTHONPATH=sportsliveinfo/src python3 tools/generate_feed_fixtures.py && run the unit gate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
