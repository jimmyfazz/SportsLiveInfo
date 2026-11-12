import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from sportsliveinfo.storage import Store
from sportsliveinfo.engine import Engine
from sportsliveinfo.providers import decode_xmltv, f1_events, verify_url, xmltv_time


class SportsLiveInfoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'app.sqlite3')

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_run_and_independent_key_saves(self):
        self.assertFalse(self.store.config()['setup_complete'])
        self.store.configure({'keys': {'football_data': 'a'}})
        self.store.configure({'keys': {'api_sports': 'b'}})
        self.assertEqual(self.store.config()['keys'], {'football_data': 'a', 'api_sports': 'b'})
        self.store.configure({'setup_complete': True})
        self.assertTrue(Store(Path(self.tmp.name) / 'app.sqlite3').config()['setup_complete'])

    def test_source_failure_keeps_last_good(self):
        engine = Engine(self.store)
        self.store.configure({'setup_complete': True, 'epg': {'farleyflex': True}, 'sports': {'jolpica': False}})
        self.store.save_snapshot('epg:farleyflex', {'channels': {'a': 'A'}, 'programmes': [{'title': 'Old'}]})
        with patch('sportsliveinfo.providers.fetch', side_effect=RuntimeError('offline')):
            engine.collect()
        self.assertEqual(self.store.snapshot('epg:farleyflex')['data']['programmes'][0]['title'], 'Old')
        self.assertEqual(self.store.recent_jobs()[1]['state'], 'failed')

    def test_xmltv_time_and_dtd(self):
        xml = b'<tv><channel id="BBCOne.uk"><display-name>BBC One</display-name></channel><programme channel="BBCOne.uk" start="20261025013000 +0100" stop="20261025023000 +0000"><title>News</title></programme></tv>'
        parsed = decode_xmltv(xml, 'uk')
        self.assertEqual(parsed['programmes'][0]['start_utc'], '2026-10-25T00:30:00+00:00')
        self.assertEqual(parsed['programmes'][0]['end_utc'], '2026-10-25T02:30:00+00:00')
        with self.assertRaises(ValueError):
            decode_xmltv(b'<!DOCTYPE tv [<!ENTITY x "secret">]><tv/>', 'uk')

    def test_safe_urls(self):
        for url in ['http://api.jolpi.ca/ergast/f1/current.json', 'https://127.0.0.1/x', 'https://api.jolpi.ca.evil.invalid/x']:
            with self.assertRaises(ValueError):
                verify_url(url)
        verify_url('https://api.jolpi.ca/ergast/f1/current.json')

    def test_publication_denied_without_license(self):
        self.store.configure({'setup_complete': True, 'github': {'enabled': True}})
        with self.assertRaisesRegex(ValueError, 'approved'):
            Engine(self.store).publish()

    def test_f1_calendar(self):
        src = {'MRData': {'RaceTable': {'Races': [
            {'season': '2026', 'round': '4', 'raceName': 'Example Grand Prix', 'date': '2026-05-02', 'time': '13:00:00Z',
             'Circuit': {'circuitName': 'Circuit Example', 'Location': {'country': 'Example'}},
             'Qualifying': {'date': '2026-05-01', 'time': '14:00:00Z'}}]}}}
        events = f1_events(json.dumps(src).encode())
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]['broadcasts'], [])
        self.assertFalse(events[0]['broadcast_verified'])

    def test_quota_reservations(self):
        self.assertEqual(self.store.increment('test', 2), 1)
        self.assertEqual(self.store.increment('test', 2), 2)
        with self.assertRaises(RuntimeError):
            self.store.increment('test', 2)

if __name__ == '__main__':
    unittest.main()
