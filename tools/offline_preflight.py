#!/usr/bin/env python3
"""Strictly offline SportsLiveInfo pre-installation gate.

Run: python3 tools/offline_preflight.py
Optional synthetic GUI previews: python3 tools/offline_preflight.py --html-preview /tmp/sli-preview
Never calls any sports API or writes to GitHub. It does not verify HAOS/Docker.
"""
import argparse
import ast
import hashlib
import json
import re
import shutil
import socket
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "sportsliveinfo"
sys.path.insert(0, str(APP / "src"))

from sportsliveinfo import __version__
from sportsliveinfo.engine import Engine
from sportsliveinfo.server import UI
from sportsliveinfo.storage import Store

ORIGINAL_CONNECT = socket.create_connection


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def packaging_gate():
    for name in ("repository.yaml", "sportsliveinfo/config.yaml", "sportsliveinfo/Dockerfile",
                 "sportsliveinfo/README.md", "sportsliveinfo/DOCS.md",
                 "sportsliveinfo/icon.png", "sportsliveinfo/logo.png",
                 "sportsliveinfo/src/sportsliveinfo/__main__.py"):
        check((ROOT / name).is_file(), "Missing required file: " + name)
    config = (APP / "config.yaml").read_text(encoding="utf-8")
    docker = (APP / "Dockerfile").read_text(encoding="utf-8")
    a = re.search(r'^version:\s*"([^"]+)"', config, re.M)
    b = re.search(r'^ARG BUILD_VERSION=([^\s]+)', docker, re.M)
    check(a is not None and b is not None, "Missing semantic version metadata")
    check(a.group(1) == b.group(1) == __version__, "Inconsistent package / image / Python version")
    check("ingress: true" in config and "ingress_port: 8099" in config,
          "Private Ingress is not configured")
    check("panel_admin: true" in config, "Home Assistant admin panel flag missing")
    check(not re.search(r"^ports\s*:", config, re.M), "Unexpected exposed host ports")
    check('io.hass.type="app"' in docker and "io.hass.arch=" in docker,
          "Home Assistant image metadata missing")
    for folder in (APP / "src", ROOT / "tests", ROOT / "tools"):
        for py in folder.rglob("*.py"):
            ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
    print("PASS: package metadata, syntax and Ingress-only configuration", flush=True)


def _offline_network(address, *args, **kwargs):
    host = str(address[0]).strip("[]").lower()
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise RuntimeError("Offline network guard refused external host: " + host)
    return ORIGINAL_CONNECT(address, *args, **kwargs)


def test_gate():
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_*.py")
    # Permit only localhost HTTP/CSRF integration checks, never provider calls.
    with patch("socket.create_connection", side_effect=_offline_network):
        outcome = unittest.TextTestRunner(verbosity=2).run(suite)
    check(outcome.wasSuccessful(), "Python unit/integration suite failed")
    print("PASS: %d offline Python tests" % outcome.testsRun, flush=True)


def synthetic_event(now):
    return {
        "id": "synthetic-only:event-1", "sport": "football",
        "category_id": "football.premier_league",
        "category_label": "Premier League", "category_priority": 1,
        "competition": "Premier League",
        "title": "Example City v Example United — SYNTHETIC",
        "participants": ["Example City", "Example United"],
        "start_utc": (now + timedelta(hours=1)).isoformat(),
        "start_precision": "scheduled", "source_id": "synthetic-only",
        "sources": ["synthetic-only"], "tags": [],
        "status_normalized": "scheduled",
        "broadcast_verified": False, "broadcasts": [], "broadcast_candidates": [],
    }


def smoke_gate(preview=None):
    with tempfile.TemporaryDirectory(prefix="sli-offline-") as tmp:
        root = Path(tmp)
        path = root / "private.sqlite3"
        store = Store(path)
        check(not store.config()["setup_complete"], "Fresh app unexpectedly marked set up")
        check(not store.config()["github"]["enabled"], "Public publishing enabled by default")
        check(not store.config()["publication_approvals"], "Source rights preapproved on fresh install")
        store.configure({"keys": {"football_data": "synthetic-secret-no-share"}})
        store.configure({"keys": {"api_sports": "second-synthetic-secret"}})
        store = Store(path)
        check(store.config()["keys"]["football_data"] == "synthetic-secret-no-share",
              "SQLite restart lost the first credential")
        check(store.config()["keys"]["api_sports"] == "second-synthetic-secret",
              "Independent credential save lost other provider")
        now = datetime.now(timezone.utc)
        store.save_snapshot("sports", {"events": [synthetic_event(now)]})
        store.save_snapshot("epg-quality:farleyflex", {
            "country": "GB", "channels": 2, "valid_programmes": 6,
            "full_coverage_channels": {"24h": 1, "72h": 0, "168h": 0},
            "families": {}, "channels_needing_attention": [], "analysed_at": now.isoformat()})
        store.job("jolpica", "test_ok", "Synthetic local smoke test")
        engine = Engine(store)
        ui = UI.__new__(UI)
        ui.server = SimpleNamespace(store=store, engine=engine, csrf="synthetic-test-csrf")
        pages = ["dashboard", "today", "events", "guide", "sources",
                 "scheduler", "publishing", "health"]
        html = {}
        for page in pages:
            value = ui.render(page, store.config(), "", {})
            check(value.startswith("<!doctype html>") and value.endswith("</html>"),
                  "Bad HTML page: " + page)
            check('aria-label="Main navigation"' in value, "Main navigation absent: " + page)
            check("synthetic-secret" not in value, "Credential appeared in page: " + page)
            html[page] = value
        check('type="submit" disabled>Publish feed now</button>' in html["publishing"],
              "Public publishing UI is not fail-closed")
        check("No public redistribution rights established" in html["sources"],
              "Private source rights warning missing")
        manifest = engine.preview_feed(out_dir=root)
        directory = root / "feed-preview"
        saved = json.loads((directory / "v1" / "manifest.json").read_text())
        check(saved["revision"] == manifest["revision"], "Preview manifest mismatch")
        check(saved["rights"]["epg_programmes"] == "not_published",
              "EPG programme text unexpectedly made public")
        check(saved["coverage"]["events"] == 0, "Unlicensed example event leaked into feed")
        for asset in saved["assets"]:
            target = directory / asset["path"]
            check(target.is_file() and target.resolve().is_relative_to(directory.resolve()),
                  "Missing or unsafe asset filename")
            data = target.read_bytes()
            check(len(data) == asset["bytes"] and hashlib.sha256(data).hexdigest() == asset["sha256"],
                  "Asset content/hash mismatch")
            check(b"synthetic-secret" not in data, "Private credential in public preview")
        if preview:
            preview.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(APP / "icon.png", preview / "icon.png")
            for page, markup in html.items():
                marked = markup.replace("<main>", '<main><div role="note" class="alert error">'
                                        "SYNTHETIC OFFLINE PREVIEW — not live data or an App install"
                                        "</div>", 1)
                (preview / (page + ".html")).write_text(marked, encoding="utf-8")
            print("Synthetic GUI preview files: " + str(preview))
        print("PASS: eight GUI views, persistent private credentials, "
              "licence-denied feed and %d SHA-256 assets" % len(saved["assets"]), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html-preview", type=Path,
                        help="Write standalone synthetic GUI HTML pages for visual review")
    args = parser.parse_args()
    try:
        packaging_gate()
        test_gate()
        smoke_gate(args.html_preview)
    except (AssertionError, OSError, ValueError, RuntimeError) as exc:
        print("OFFLINE PRE-INSTALLATION GATE FAILED: " + str(exc), file=sys.stderr)
        return 1
    print("OFFLINE SOURCE GATE PASSED; actual Docker/HAOS and live-source checks remain required.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
