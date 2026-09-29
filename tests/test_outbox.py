"""Tests de la file locale persistée."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.models import DataParser, HeatControlData  # noqa: E402
from core.outbox import Outbox, idempotency_key  # noqa: E402
from tests.test_models import ELECTRICAL_FRAME, HEAT_FRAME  # noqa: E402


class OutboxTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.outbox = Outbox(Path(self.tmp.name) / 'outbox')
        self.electrical = DataParser.parse_electrical_control(ELECTRICAL_FRAME)
        self.way = DataParser.parse_heat_control(HEAT_FRAME)[0]

    def tearDown(self):
        self.tmp.cleanup()

    def test_keys_identify_control_and_way(self):
        self.assertEqual(idempotency_key('electrical', self.electrical), 'electrical:F111111111-1:20181029T135110')
        self.assertEqual(idempotency_key('heat', self.way), 'heat:F111111111-1:20181029T135553:V1')

    def test_add_persists_and_round_trips(self):
        entry = self.outbox.add('electrical', self.electrical, ELECTRICAL_FRAME)
        self.assertIsNotNone(entry)
        self.assertTrue(entry.path.exists())
        reloaded = Outbox(self.outbox.directory).pending()
        self.assertEqual(len(reloaded), 1)
        control = reloaded[0].to_control()
        self.assertEqual(control, self.electrical)
        self.assertEqual(reloaded[0].frame[0], ['29/10/2018', '13:51:10\r\n'])

    def test_duplicate_frame_is_ignored(self):
        self.assertIsNotNone(self.outbox.add('electrical', self.electrical))
        self.assertIsNone(self.outbox.add('electrical', self.electrical))
        self.assertEqual(self.outbox.counts(), (1, 0))

    def test_pending_keeps_arrival_order(self):
        e1 = self.outbox.add('electrical', self.electrical)
        e1.created_at = '2026-01-01T10:00:00'
        self.outbox._write(e1.path, e1)
        e2 = self.outbox.add('heat', self.way)
        e2.created_at = '2026-01-01T09:00:00'
        self.outbox._write(e2.path, e2)
        self.assertEqual([e.kind for e in self.outbox.pending()], ['heat', 'electrical'])

    def test_done_retry_failed(self):
        entry = self.outbox.add('electrical', self.electrical)
        self.outbox.mark_retry(entry, 'timeout')
        again = self.outbox.pending()[0]
        self.assertEqual((again.attempts, again.last_error), (1, 'timeout'))
        self.outbox.mark_failed(again, 'Invalid parameter')
        self.assertEqual(self.outbox.counts(), (0, 1))
        self.assertIsNone(self.outbox.add('electrical', self.electrical))  # refusé = pas remis en file
        failed = json.loads(next(self.outbox.failed_directory.glob('*.json')).read_text(encoding='utf-8'))
        self.assertEqual(failed['last_error'], 'Invalid parameter')
        way_entry = self.outbox.add('heat', self.way)
        self.outbox.mark_done(way_entry)
        self.assertEqual(self.outbox.counts(), (0, 1))

    def test_corrupt_entry_is_quarantined(self):
        (self.outbox.directory / 'broken.json').write_text('{not json', encoding='utf-8')
        self.assertEqual(self.outbox.pending(), [])
        self.assertTrue((self.outbox.failed_directory / 'broken.json').exists())


if __name__ == '__main__':
    unittest.main()
