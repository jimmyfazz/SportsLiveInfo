import json
import tempfile
import time
import unittest
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from ingress_test_support import IngressTestClient
from sportsliveinfo import coverage, dictionary, feed
from sportsliveinfo.storage import Store

M3U = """#EXTM3U
#EXTINF:-1 tvg-id="ExampleSport1.uk" tvg-name="UK: Example Sport 1" group-title="UK | Sport",UK: Example Sport 1 HD
http://provider.example/live/USER/SECRETPASS/101.ts
#EXTINF:-1 tvg-id="" group-title="INT | France",FR | Exemple Cinema
http://provider.example/live/USER/SECRETPASS/102.ts
#EXTINF:-1 tvg-id="" group-title="UK | Kids",UK: Example Kids
http://provider.example/live/USER/SECRETPASS/103.ts
#EXTINF:-1 tvg-id="" group-title="Movies VOD",A Film (2024)
http://provider.example/movie/USER/SECRETPASS/900.mp4
#EXTINF:-1 tvg-id="" group-title="LIVE | EPL Events",EPL 05 | Northtown United vs Southport Rovers (Sat 17:30 UK)
http://provider.example/live/USER/SECRETPASS/501.ts
#EXTINF:-1 tvg-id="" group-title="Radio",RADIO: Example FM
http://provider.example/live/USER/SECRETPASS/700.ts
"""

DICT_CHANNELS = """id,name,alt_names,network,owners,country,categories,is_nsfw,launched,closed,replaced_by,website
ExampleSport1.uk,Example Sport 1,,,,UK,sports,FALSE,,,,
ExempleCinema.fr,Exemple Cinema,,,,FR,movies,FALSE,,,,
ExampleKids.uk,Example Kids,,,,UK,kids,FALSE,,,,
"""
FEEDS = "channel,id,name,alt_names,is_main,broadcast_area,timezones,languages,format\n"


def index(source_id, channels):
    return {"source_id": source_id, "channels": channels, "programmes": {cid: 50 for cid in channels},
            "first": None, "last": None}


class LineupParsingTests(unittest.TestCase):
    def test_stream_urls_and_credentials_are_never_kept(self):
        entries = coverage.parse_lineup(M3U)
        self.assertNotIn("SECRETPASS", json.dumps(entries))
        self.assertNotIn("provider.example", json.dumps(entries))
        self.assertEqual(entries[0], {"category": "UK | Sport", "name": "UK: Example Sport 1 HD",
                                      "tvg_id": "ExampleSport1.uk", "kind": "linear"})
        kinds = {e["name"]: e["kind"] for e in entries}
        self.assertEqual(kinds["A Film (2024)"], "vod")
        self.assertEqual(kinds["RADIO: Example FM"], "radio")
        self.assertEqual(kinds["EPL 05 | Northtown United vs Southport Rovers (Sat 17:30 UK)"], "event_slot")

    def test_stream_urls_never_become_channel_names(self):
        """Audit 15 Nov (P1): URLs, which may carry the provider login, are never stored."""
        urls = "http://h.example:80/user/pass/1.ts\nhttps://h.example/get.php?username=u&password=p\n"
        self.assertEqual(coverage.parse_lineup(urls), [])
        late_header = "\n" * 60 + "#EXTM3U\n#EXTINF:-1 group-title=\"UK\",BBC One\nhttp://h.example/user/pass/1.ts\n"
        indented = '  #EXTINF:-1 group-title="UK",BBC Two\n  http://h.example/user/pass/2.ts\n'
        for text, name in ((late_header, "BBC One"), (indented, "BBC Two")):
            entries = coverage.parse_lineup(text)
            self.assertEqual([e["name"] for e in entries], [name])
            self.assertFalse(any("://" in v or "pass" in v for e in entries for v in e.values()))

    def test_plain_text_lists(self):
        entries = coverage.parse_lineup("UK | Sport\tSky Example 1\nFR | TF Example\n")
        self.assertEqual([(e["category"], e["name"]) for e in entries],
                         [("UK | Sport", "Sky Example 1"), ("", "FR | TF Example")])

    def test_market_and_genre(self):
        self.assertEqual(coverage.market_of("INT | France", "Any"), "FR")
        self.assertEqual(coverage.market_of("SK: France", "Any"), "FR")       # country word before platform code
        self.assertEqual(coverage.market_of("UK | Entertainment", "Any"), "GB")
        self.assertEqual(coverage.market_of("", "DE | Example"), "DE")
        self.assertEqual(coverage.market_of("INR | Malayalam", "Any"), "IN")
        self.assertIsNone(coverage.market_of("Other", "Something"))
        self.assertEqual(coverage.genre_of("UK | Kids", "Example Junior"), "kids")
        self.assertEqual(coverage.genre_of("", "Anything", ("movies",)), "movies")    # dictionary category first
        self.assertEqual(coverage.genre_of("", "Example Documentary Discovery"), "documentary")
        self.assertEqual(coverage.classify_kind("SPORTS | FloSports", "Flo Racing 05"), "event_slot")


class CoverageReportTests(unittest.TestCase):
    def test_every_genre_counted_and_guides_recommended(self):
        lineup = coverage.parse_lineup(M3U)
        document = dictionary.build_document(DICT_CHANNELS, FEEDS, "")
        enabled = [index("uk_freeview", {"ExampleKids.uk@HD": "Example Kids HD"})]
        surveyed = [index("m3upt_sky", {"ExampleSport1.uk": "Example Sport 1"}),
                    index("fr_mena_grab", {"ExempleCinema.fr": "Exemple Cinema"})]
        report = coverage.build_report(lineup, dictionary_document=document, enabled_indexes=enabled,
                                       surveyed_indexes=surveyed, now=datetime(2026, 11, 14, 16, tzinfo=timezone.utc))
        rows = {r["name"]: r for r in report["rows"]}
        self.assertNotIn("A Film (2024)", rows)                                  # VOD is not a channel
        self.assertNotIn("RADIO: Example FM", rows)
        sport = rows["UK: Example Sport 1 HD"]
        self.assertEqual((sport["state"], sport["match"], sport["guide_source"]),
                         ("guide_available", "provider_id", "m3upt_sky"))       # the provider's tvg-id, exactly
        cinema = rows["FR | Exemple Cinema"]
        self.assertEqual((cinema["genre"], cinema["identity"], cinema["match"]),
                         ("movies", "ExempleCinema.fr", "dictionary_id"))
        kids = rows["UK: Example Kids"]
        self.assertEqual((kids["genre"], kids["state"]), ("kids", "guide_enabled"))
        self.assertEqual(rows["EPL 05 | Northtown United vs Southport Rovers (Sat 17:30 UK)"]["state"], "slot_from_name")
        self.assertIn("genre:movies", report["totals"])
        self.assertIn("genre:kids", report["totals"])
        # Recommendations need at least 3 new channels per guide; the tiny example has fewer.
        self.assertEqual(report["recommendations"], [])


class CoverageIngressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "s.sqlite3")
        self.store.configure({"setup_complete": True})
        self.client = IngressTestClient(self.store, "x", memory=True)

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def test_upload_is_stored_locally_and_never_published(self):
        boundary = "----slitest"
        body = ("--%s\r\nContent-Disposition: form-data; name=\"csrf\"\r\n\r\nx\r\n"
                "--%s\r\nContent-Disposition: form-data; name=\"action\"\r\n\r\nlineup_upload\r\n"
                "--%s\r\nContent-Disposition: form-data; name=\"lineup\"; filename=\"list.m3u\"\r\n"
                "Content-Type: audio/x-mpegurl\r\n\r\n%s\r\n--%s--\r\n") % (boundary, boundary, boundary, M3U, boundary)
        request = urllib.request.Request(self.client.base, data=body.encode(), method="POST",
                                         headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
        page = self.client.open(request).read().decode()
        self.assertIn("stored on this Home Assistant only", page)
        stored = self.store.snapshot(coverage.LINEUP_PRODUCT)["data"]["entries"]
        self.assertEqual(len(stored), 6)
        self.assertNotIn("SECRETPASS", json.dumps(stored))
        for _ in range(50):                                     # the report is built in the background
            if (self.store.snapshot(coverage.REPORT_PRODUCT) or {}).get("data", {}).get("rows"):
                break
            time.sleep(0.1)
        csv_text = self.client.open(self.client.base + "coverage.csv").read().decode()
        self.assertIn("UK: Example Kids", csv_text)
        manifest, files = feed.build_feed(self.store, now=datetime(2026, 11, 14, 16, tzinfo=timezone.utc))
        published = b"".join(files.values()).decode("utf-8", errors="replace")
        self.assertNotIn("Example Kids", published)             # the channel list is never in any feed file
        self.assertNotIn("Exemple Cinema", published)

    def upload(self, action, field, filename, content):
        boundary = "----slitest"
        body = ("--%s\r\nContent-Disposition: form-data; name=\"csrf\"\r\n\r\nx\r\n"
                "--%s\r\nContent-Disposition: form-data; name=\"action\"\r\n\r\n%s\r\n"
                "--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n"
                "Content-Type: text/plain\r\n\r\n%s\r\n--%s--\r\n") % (
            boundary, boundary, action, boundary, field, filename, content, boundary)
        request = urllib.request.Request(self.client.base, data=body.encode(), method="POST",
                                         headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
        return self.client.open(request).read().decode()

    def wait_for(self, product):
        for _ in range(80):
            if (self.store.snapshot(product) or {}).get("data"):
                return self.store.snapshot(product)["data"]
            time.sleep(0.1)
        self.fail("%s was not built" % product)

    def test_b1g_export_is_compared_channel_by_channel(self):
        self.upload("lineup_upload", "lineup", "list.m3u", M3U)
        self.wait_for(coverage.REPORT_PRODUCT)
        entries = self.store.snapshot(coverage.LINEUP_PRODUCT)["data"]["entries"]
        rows = [coverage.reconcile_channel(entry) for entry in entries]       # what a conforming TV exports
        rows[0]["identity"] = "ExampleSport1.uk@Plus1"                       # one wrong: a +1 feed
        import csv
        import io
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=coverage.TV_FIELDS, lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)
        page = self.upload("tv_export_upload", "tv_export", "b1g.csv", out.getvalue())
        self.assertIn("stored on this Home Assistant only", page)
        for _ in range(80):
            comparison = (self.store.snapshot(coverage.COMPARISON_PRODUCT) or {}).get("data") or {}
            if comparison.get("counts"):
                break
            time.sleep(0.1)
        counts = comparison["counts"]
        self.assertEqual(counts["compared"], 6)
        self.assertEqual(counts["identity_only_tv"], 1)
        self.assertEqual(counts["serious"], 1)                              # a +1 identity is a serious error
        self.assertFalse(comparison["passes"])
        page = self.client.open(self.client.base + "?page=coverage").read().decode()
        self.assertIn("Compare with B1G", page)
        self.assertIn("does not pass yet", page)
        manifest, files = feed.build_feed(self.store, now=datetime(2026, 11, 14, 16, tzinfo=timezone.utc))
        self.assertNotIn("Example Kids", b"".join(files.values()).decode("utf-8", errors="replace"))
        self.upload("tv_export_upload", "tv_export", "bad.csv", "not,a,b1g,export\r\n1,2,3,4")
        self.assertEqual(len(self.store.snapshot(coverage.TV_EXPORT_PRODUCT)["data"]["rows"]), 6)  # refused

    def test_wrong_csrf_upload_is_refused(self):
        boundary = "----slitest"
        body = ("--%s\r\nContent-Disposition: form-data; name=\"csrf\"\r\n\r\nWRONG\r\n"
                "--%s\r\nContent-Disposition: form-data; name=\"action\"\r\n\r\nlineup_upload\r\n--%s--\r\n") % (
            boundary, boundary, boundary)
        request = urllib.request.Request(self.client.base, data=body.encode(), method="POST",
                                         headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
        with self.assertRaises(Exception):
            self.client.open(request)
        self.assertIsNone(self.store.snapshot(coverage.LINEUP_PRODUCT))


if __name__ == "__main__":
    unittest.main()
