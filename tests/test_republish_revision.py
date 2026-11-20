"""tools/republish_revision.py (audit CA-07): a rollback is a NEW revision with a fresh generated_at, because B1G
ignores a manifest older than the one it holds. Tests cover the pure manifest builder and the dry-run/apply CLI."""
import contextlib
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from test_feed import load_schema, validate

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("republish_revision", ROOT / "tools" / "republish_revision.py")
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

UTC = timezone.utc
NOW = datetime(2026, 11, 21, 9, 0, 0, tzinfo=UTC)


class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.old = json.loads((ROOT / "schemas/fixtures/sli-v1/v1/manifest.json").read_text())
        self.current = dict(self.old, revision="c" * 20, generated_at="2026-11-21T08:00:00+00:00")

    def test_new_revision_has_fresh_times_and_the_old_asset_set(self):
        manifest = tool.build_rollback_manifest(self.old, self.current, NOW)
        self.assertEqual(manifest["generated_at"], "2026-11-21T09:00:00+00:00")
        self.assertEqual(manifest["refresh"]["expires_at"], "2026-11-23T09:00:00+00:00")
        self.assertEqual(manifest["assets"], self.old["assets"])
        self.assertEqual(manifest["previous_revision"], "c" * 20)
        self.assertEqual(manifest["rollback_of"], self.old["revision"])
        self.assertNotEqual(manifest["revision"], self.old["revision"])
        self.assertRegex(manifest["revision"], r"^[0-9a-f]{20}$")
        self.assertIn("Rollback", manifest["notices"][-1])
        self.assertEqual(manifest["refresh"].get("collected_at"), self.old["refresh"].get("collected_at"))
        validate(manifest, load_schema("sli.manifest/1"), load_schema("sli.manifest/1"))

    def test_input_is_not_modified_and_result_is_deterministic(self):
        before = json.dumps(self.old, sort_keys=True)
        first = tool.build_rollback_manifest(self.old, self.current, NOW)
        self.assertEqual(json.dumps(self.old, sort_keys=True), before)
        self.assertEqual(first, tool.build_rollback_manifest(self.old, self.current, NOW))

    def test_a_clock_behind_the_current_manifest_is_refused(self):
        with self.assertRaises(ValueError):
            tool.build_rollback_manifest(self.old, self.current, datetime(2026, 11, 21, 7, 0, tzinfo=UTC))
        with self.assertRaises(ValueError):
            tool.build_rollback_manifest({"revision": "a" * 20, "assets": []}, self.current, NOW)

    def test_no_current_manifest_is_allowed_and_missing_assets_are_listed(self):
        manifest = tool.build_rollback_manifest(self.old, None, NOW)
        self.assertIsNone(manifest["previous_revision"])
        first = manifest["assets"][0]["path"]
        self.assertEqual(tool.missing_assets(manifest, lambda p: p != first), [first])
        self.assertEqual(tool.corrupt_assets(manifest, lambda p: b"x"), [a["path"] for a in manifest["assets"]])


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        (self.repo / "v1" / "manifests").mkdir(parents=True)
        body = b'{"schema":"x"}'
        path = "v1/assets/taxonomy/%s.json" % hashlib.sha256(body).hexdigest()[:24]
        (self.repo / path).parent.mkdir(parents=True)
        (self.repo / path).write_bytes(body)
        self.old = {"revision": "a" * 20, "generated_at": "2026-11-19T12:00:00+00:00",
                    "refresh": {"expires_at": "2026-11-21T12:00:00+00:00"},
                    "assets": [{"kind": "taxonomy", "path": path, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}]}
        bad = dict(self.old, revision="b" * 20, generated_at="2026-11-20T12:00:00+00:00")
        (self.repo / ("v1/manifests/%s.json" % ("a" * 20))).write_text(json.dumps(self.old))
        (self.repo / "v1/manifest.json").write_text(json.dumps(bad))

    def run_tool(self, *extra):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = tool.main(["--repo", str(self.repo), "--revision", "a" * 20, *extra])
        return code, out.getvalue()

    def test_dry_run_writes_nothing(self):
        before = (self.repo / "v1/manifest.json").read_bytes()
        code, text = self.run_tool()
        self.assertEqual(code, 0)
        self.assertIn("DRY RUN", text)
        self.assertEqual((self.repo / "v1/manifest.json").read_bytes(), before)
        self.assertEqual(len(list((self.repo / "v1/manifests").iterdir())), 1)

    def test_apply_writes_a_newer_manifest_and_its_revision_copy(self):
        code, _ = self.run_tool("--apply")
        self.assertEqual(code, 0)
        written = json.loads((self.repo / "v1/manifest.json").read_text())
        self.assertGreater(datetime.fromisoformat(written["generated_at"]), datetime(2026, 11, 20, 12, tzinfo=UTC))
        self.assertEqual(written["previous_revision"], "b" * 20)
        self.assertEqual((self.repo / ("v1/manifests/%s.json" % written["revision"])).read_bytes(),
                         (self.repo / "v1/manifest.json").read_bytes())

    def test_missing_asset_stops_the_run(self):
        for p in (self.repo / "v1/assets").rglob("*.json"):
            p.unlink()
        with self.assertRaises(SystemExit) as raised:
            self.run_tool("--apply")
        self.assertIn("no longer in the working tree", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
