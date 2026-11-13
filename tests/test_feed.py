"""sli/1 feed contract: schemas, golden fixtures, content addressing, rights and atomic publishing."""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from sportsliveinfo import feed
from sportsliveinfo.engine import Engine
from sportsliveinfo.storage import Store

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "schemas" / "fixtures" / "sli-v1"
SCHEMAS = {"sli.manifest/1": "sli-manifest", "sli.taxonomy/1": "sli-taxonomy", "sli.channels/1": "sli-channels",
           "sli.events-day/1": "sli-events-day", "sli.today/1": "sli-today", "sli.health/1": "sli-health",
           "sli.identity/1": "sli-identity", "sli.dictionary/1": "sli-dictionary"}
NOW = datetime(2026, 11, 14, 14, 0, tzinfo=timezone.utc)
_spec = importlib.util.spec_from_file_location("feed_fixtures", ROOT / "tools" / "generate_feed_fixtures.py")
fixtures_tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fixtures_tool)

TYPES = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float), "boolean": bool, "null": type(None)}


def validate(value, schema, root, where="$"):
    """Minimal JSON Schema subset (type, const, enum, required, properties, items, pattern, minimum, $ref)."""
    import re
    if "$ref" in schema:
        name = schema["$ref"].split("/")[-1]
        return validate(value, root["$defs"][name], root, where)
    kinds = schema.get("type")
    if kinds:
        kinds = [kinds] if isinstance(kinds, str) else kinds
        ok = any(isinstance(value, TYPES[k]) and not (k in ("integer", "number") and isinstance(value, bool)) for k in kinds)
        assert ok, "%s: expected %s, got %r" % (where, kinds, type(value).__name__)
    if "const" in schema:
        assert value == schema["const"], "%s: expected const %r" % (where, schema["const"])
    if "enum" in schema:
        assert value in schema["enum"], where
    if isinstance(value, str) and "pattern" in schema:
        assert re.search(schema["pattern"], value), "%s: %r !~ %s" % (where, value, schema["pattern"])
    if isinstance(value, (int, float)) and "minimum" in schema:
        assert value >= schema["minimum"], where
    if isinstance(value, dict):
        for key in schema.get("required", []):
            assert key in value, "%s: missing %s" % (where, key)
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                validate(value[key], sub, root, where + "." + key)
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            validate(item, schema["items"], root, "%s[%d]" % (where, i))


def load_schema(schema_id):
    return json.loads((ROOT / "schemas" / (SCHEMAS[schema_id] + ".schema.json")).read_text())


class GoldenFixtureContractTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((FIXTURES / "v1" / "manifest.json").read_text())

    def test_fixtures_match_current_code(self):
        manifest, files = fixtures_tool.build()
        self.assertEqual(feed._json(manifest), (FIXTURES / "v1" / "manifest.json").read_bytes(),
                         "feed changed: run tools/generate_feed_fixtures.py and update the B1 reader fixtures")
        for path, data in files.items():
            self.assertEqual(data, (FIXTURES / path).read_bytes(), path)
        self.assertEqual(fixtures_tool.matching_cases(), json.loads((FIXTURES / "matching-cases.json").read_text()))

    def test_matching_cases_cover_positive_and_hard_negative_identities(self):
        cases = {(c["source_id"], c["name"]): c["canonical_id"] for c in json.loads((FIXTURES / "matching-cases.json").read_text())["cases"]}
        self.assertEqual(cases[("epgshare_my", "MYS | Astro Premier League FHD")], "my.astro.premier_league")
        # Identity-bearing qualifiers resolve to their own service, never the parent or a sibling.
        self.assertEqual(cases[("farleyflex", "Sky Sports+")], "gb.sky.sports.plus")
        self.assertEqual(cases[("farleyflex", "BBC One Scotland")], "gb.bbc.one.scotland")
        self.assertEqual(cases[("mjh_sky_uk", "TNT Sports 8")], "gb.tnt.sports.8")   # UK name in a UK guide
        for negative in [("epgshare_us", "TNT Sports 8"),
                         ("epgshare_uk", "Setanta Sports 1"), ("epgtalk_sports", "Sky Sports Main Event"), ("fr_xmltv", "beIN Sports 4")]:
            self.assertIsNone(cases[negative], negative)

    def test_every_asset_validates_and_hash_verifies(self):
        validate(self.manifest, load_schema("sli.manifest/1"), load_schema("sli.manifest/1"))
        kinds = set()
        for asset in self.manifest["assets"]:
            data = (FIXTURES / asset["path"]).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), asset["sha256"], asset["path"])
            self.assertEqual(len(data), asset["bytes"])
            self.assertIn(asset["sha256"][:24], asset["path"])
            schema = load_schema(asset["schema"])
            validate(json.loads(data), schema, schema)
            kinds.add(asset["kind"].split(":")[0])
        self.assertEqual(kinds, {"taxonomy", "channels", "identity", "dictionary", "events", "today", "health"})
        self.assertEqual(sum(a["kind"].startswith("events:") for a in self.manifest["assets"]), 8)

    def asset(self, kind):
        entry = next(a for a in self.manifest["assets"] if a["kind"] == kind)
        return json.loads((FIXTURES / entry["path"]).read_text())

    def events(self):
        out = []
        for a in self.manifest["assets"]:
            if a["kind"].startswith("events:"):
                out.extend(json.loads((FIXTURES / a["path"]).read_text())["events"])
        return {e["id"]: e for e in out}

    def test_events_are_fused_classified_and_whitelisted(self):
        events = self.events()
        self.assertEqual(len(events), 13)
        pl = events["football-data:5001"]
        self.assertEqual((pl["category_id"], pl["fixture_confidence"], pl["sources"]),
                         ("football.premier_league", "corroborated", ["api_sports", "football_data"]))
        self.assertEqual(events["api-sports:9002"]["category_id"], "football.intl.england")
        self.assertEqual(events["api-sports:9005"]["category_id"], "football.intl.england_women")
        self.assertEqual(events["api-sports:9004"]["category_id"], "football.europa_league")
        self.assertEqual(events["football-data:5002"]["category_id"], "football.champions_league")
        self.assertEqual(events["api-sports:9003"]["category_id"], "football.fa_cup")
        f1 = events["f1:2026:22:race"]
        self.assertEqual((f1["end_utc"], f1["b1g_priority_group"]), ("2026-11-21T08:00:00+00:00", "Formula 1"))
        self.assertIn("ppv", events["api-sports-mma:77"]["tags"])
        self.assertEqual(events["cricketdata:ash1:d1"]["category_id"], "cricket.intl.england")
        self.assertEqual(events["api-sports-rugby:301"]["b1g_priority_group"], "Rugby")
        allowed = set(feed.EVENT_FIELDS) | {"b1g_priority_group", "broadcasts"}
        blob = json.dumps(events)
        for event in events.values():
            self.assertLessEqual(set(event), allowed, event["id"])
            self.assertFalse(event["broadcast_verified"])
        for private in ("broadcast_candidates", "Live Premier League", "fetch_scope", "live_state", "skysportsmainevent"):
            self.assertNotIn(private, blob)

    def test_registry_is_data_for_the_reader(self):
        taxonomy = self.asset("taxonomy")
        groups = {s["id"]: s["b1g_priority_group"] for s in taxonomy["sports"]}
        self.assertEqual((groups["football"], groups["rugby_league"], groups["darts"]), ("Football", "Rugby", "Darts"))
        comp = {c["id"]: c for c in taxonomy["competitions"]}
        self.assertEqual(comp["motorsport.motogp"]["b1g_priority_group"], "Motorbike racing")
        self.assertIn("football.conference_league", comp)
        self.assertTrue(any(n["id"] == "football.intl.england" and "england" in n["nations"] for n in taxonomy["national_categories"]))
        channels = self.asset("channels")
        crosswalk = next(row for row in channels["source_crosswalk"] if row["source_id"] == "farleyflex")
        self.assertEqual(crosswalk["ids"]["skysportspremiereleague.uk"], "gb.sky.sports.premier_league")
        self.assertTrue(any(s["id"] == "ge.setanta.sports.1" for s in channels["services"]))
        self.assertTrue(any(f["id"] == "now_sports_hk" for f in channels["families"]))
        guide_ids = {g["id"] for g in channels["guide_catalogue"]}
        self.assertTrue({"epgshare_hk", "iptv_epg_ge", "mjh_nz", "mjh_au_sydney"} <= guide_ids)
        self.assertNotIn("mjh_sky_uk", guide_ids)
        self.assertFalse(any(g["automatic_fallback"] for g in channels["guide_catalogue"]))

    def test_today_references_existing_events_and_featured_row(self):
        today = self.asset("today")
        day_events = self.asset("events:" + today["date"])["events"]
        ids = {e["id"] for e in day_events}
        referenced = {i for g in today["groups"] for c in g["categories"] for i in c["event_ids"]}
        self.assertEqual(referenced, ids)
        self.assertEqual(today["featured_event_ids"], ["api-sports-rugby:301", "api-sports:9002"])
        self.assertEqual(today["groups"][0]["categories"][0]["id"], "football.intl.england")

    def test_manifest_compatibility_and_rights_blocks(self):
        m = self.manifest
        self.assertEqual((m["format_major"], m["compatibility"]["unknown_fields"], m["compatibility"]["unknown_enum_fallback"]["sport"]),
                         (1, "ignore", "other"))
        self.assertEqual(m["rights"]["epg_programmes"], "not_published")
        self.assertEqual({a["source"] for a in m["rights"]["attribution"]},
                         {"api_sports", "cricketdata", "football_data", "jolpica", "openf1", "thesportsdb",
                      "iptv_org_database"})
        jolpica = next(a for a in m["rights"]["attribution"] if a["source"] == "jolpica")
        self.assertEqual(jolpica["licence"], "CC BY-NC-SA 4.0")
        self.assertTrue({"taxonomy", "channel_registry", "guide_catalogue", "today"} <= set(m["capabilities"]))
        self.assertEqual(m["refresh"]["expected_interval_minutes"], 660)


class FeedBehaviourTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "s.sqlite3")
        self.store.configure({"setup_complete": True, "publication_approvals": ["openligadb"],
                              "github": {"enabled": True, "owner": "o", "repository": "feed", "branch": "main", "token": "t"}})

    def tearDown(self):
        self.temp.cleanup()

    def events(self, *ids):
        return {"events": [{"id": i, "source_id": "openligadb", "sport": "football", "category_id": "football.bundesliga",
                            "title": i, "start_utc": "2026-11-14T15:30:00+00:00", "start_precision": "scheduled"} for i in ids]}

    def test_unapproved_sources_omitted_and_reported(self):
        snap = self.events("openligadb:1")
        snap["events"].append({"id": "api-sports:1", "source_id": "api_sports", "sport": "football", "category_id": "x",
                               "title": "t", "start_utc": "2026-11-14T15:00:00+00:00", "start_precision": "scheduled"})
        self.store.save_snapshot("sports", snap)
        manifest, files = feed.build_feed(self.store, now=NOW)
        blob = b"".join(files.values()).decode()
        self.assertIn("openligadb:1", blob)
        self.assertNotIn("api-sports:1", blob)
        self.assertEqual(manifest["rights"]["events"]["omitted_unapproved_sources"], ["api_sports"])

    def test_content_addressing_reuses_unchanged_assets(self):
        self.store.save_snapshot("sports", self.events("openligadb:1"))
        m1, f1 = feed.build_feed(self.store, now=NOW)
        m2, _ = feed.build_feed(self.store, now=NOW.replace(minute=30))
        self.assertEqual(m1["revision"], m2["revision"], "regeneration without data change keeps the revision")
        self.store.save_snapshot("sports", self.events("openligadb:1", "openligadb:2"))
        m3, _ = feed.build_feed(self.store, now=NOW)
        paths = lambda m, k: next(a["path"] for a in m["assets"] if a["kind"] == k)
        self.assertNotEqual(m1["revision"], m3["revision"])
        self.assertEqual(paths(m1, "taxonomy"), paths(m3, "taxonomy"))
        self.assertEqual(paths(m1, "channels"), paths(m3, "channels"))
        self.assertNotEqual(paths(m1, "today"), paths(m3, "today"))

    def test_atomic_publish_uploads_only_new_files_skips_unchanged_and_retains_ten(self):
        commits = []
        engine = Engine(self.store)
        with patch.object(Engine, "_github_commit", side_effect=lambda *a, **k: commits.append(a)), \
             patch("sportsliveinfo.feed.datetime") as clock:
            clock.now.return_value = NOW
            clock.fromisoformat = datetime.fromisoformat
            self.store.save_snapshot("sports", self.events("openligadb:0"))
            first = engine.publish()
            self.assertEqual(engine.publish(), first)
            self.assertEqual(len(commits), 1, "unchanged revision is not re-committed")
            self.assertIn("v1/manifest.json", commits[0][4])
            self.assertIn("v1/manifests/%s.json" % first, commits[0][4])
            for n in range(1, 11):
                self.store.save_snapshot("sports", self.events(*["openligadb:%d" % i for i in range(n + 1)]))
                engine.publish()
        second_uploads = commits[1][4]
        self.assertFalse(any("/assets/taxonomy/" in p or "/assets/channels/" in p for p in second_uploads),
                         "unchanged registry assets are not re-uploaded")
        last_deletions = commits[-1][5]
        self.assertIn("v1/manifests/%s.json" % first, last_deletions)
        state = self.store._get("feed_state")
        self.assertEqual(len(state["revisions"]), 10)
        live = {p for h in state["revisions"] for p in h["assets"]}
        self.assertFalse(live & set(last_deletions), "never delete an asset a retained manifest references")

    def test_preview_writes_complete_feed_without_upload(self):
        self.store.save_snapshot("sports", self.events("openligadb:1"))
        with patch.object(Engine, "_github_commit") as commit:
            manifest = Engine(self.store).preview_feed(out_dir=self.temp.name)
        commit.assert_not_called()
        out = Path(self.temp.name) / "feed-preview"
        self.assertEqual(json.loads((out / "v1" / "manifest.json").read_text())["revision"], manifest["revision"])
        for asset in manifest["assets"]:
            self.assertEqual(hashlib.sha256((out / asset["path"]).read_bytes()).hexdigest(), asset["sha256"])
        self.assertEqual(self.store._get("feed_preview")["revision"], manifest["revision"])

    def test_auto_publish_only_after_a_successful_collection(self):
        self.store.configure({"sports": {"jolpica": False}})
        with patch.object(Engine, "publish") as publish:
            self.assertFalse(Engine(self.store).collect())
            publish.assert_not_called()
            self.store.configure({"github": {"auto_publish": True}})
            self.assertFalse(Engine(self.store).collect())
            publish.assert_not_called()
            self.store.configure({"sports": {"jolpica": True}})
            payload = json.dumps({"MRData": {"RaceTable": {"Races": []}}}).encode()
            with patch("sportsliveinfo.providers.fetch", return_value=payload):
                self.assertTrue(Engine(self.store).collect())
            publish.assert_called_once()


if __name__ == "__main__":
    unittest.main()
