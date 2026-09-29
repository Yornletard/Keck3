"""Test de bout en bout de run.py : faux port série, faux éditeur Open Prod, fausse imprimante, vraie file locale."""

import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.publisher import PublishResult  # noqa: E402
from core.outbox import Outbox  # noqa: E402
from core.serial_reader import split_fields  # noqa: E402
from tests.test_models import ELECTRICAL_FRAME, HEAT_FRAME  # noqa: E402


class FakeSerial:
    def __init__(self, lines):
        self.lines = list(lines)
        self.is_connected = False
        self.port = 'FAKE'

    def connect(self):
        self.is_connected = True
        return True

    def disconnect(self):
        self.is_connected = False

    def read_line(self):
        if not self.lines:
            time.sleep(0.02)
            return None
        return split_fields(self.lines.pop(0))


class FakePublisher:
    """Réponses scriptées par n° de série : liste de PublishResult consommés dans l'ordre."""
    is_configured = True

    def __init__(self, script=None):
        self.calls = []
        self.script = {k: list(v) for k, v in (script or {}).items()}

    def publish(self, kind, control, frame=None):
        self.calls.append((kind, control))
        queue = self.script.get(control.serial_number)
        if queue:
            return queue.pop(0)
        return PublishResult(ok=True, ids=[len(self.calls)])


class FakePrinter:
    def __init__(self):
        self.jobs = []

    def print_barcode(self, data, qty=1):
        self.jobs.append(('barcode', data))
        return True

    def print_serial_number(self, data, qty=1):
        self.jobs.append(('serial', data))
        return True


class FakeAPI:
    last_error = None

    def check_connection(self):
        return True

    def close(self):
        pass


def as_lines(frame):
    return [' '.join(frame[0]), ' '.join(frame[1])]


class EndToEndTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        programs = root / 'programs.json'
        programs.write_text(json.dumps({"1": {"name": "CALORIBAC", "product_code": "260434", "duration": 0,
                                              "labels": ["CALORIBAC 260434", "220-240 V", ""]}}), encoding='utf-8')
        import config
        import run
        self.run = run
        self._patched = [(config, 'PROGRAMS_FILE', config.PROGRAMS_FILE), (run, 'PROGRAMS_FILE', run.PROGRAMS_FILE),
                         (run, 'MACHINES_FILE', run.MACHINES_FILE),
                         (run, 'OPEN_PROD_DB', run.OPEN_PROD_DB), (run, 'OPEN_PROD_API_KEY', run.OPEN_PROD_API_KEY),
                         (run, 'OUTBOX_BACKOFF', run.OUTBOX_BACKOFF)]
        config.PROGRAMS_FILE = run.PROGRAMS_FILE = programs
        run.MACHINES_FILE = root / 'machines.json'
        run.OPEN_PROD_DB = run.OPEN_PROD_API_KEY = 'test'  # indépendant du .env du poste
        run.OUTBOX_BACKOFF = (0.1, 0.1)
        self.outbox = Outbox(root / 'outbox')

    def tearDown(self):
        for module, name, value in self._patched:
            setattr(module, name, value)
        self.tmp.cleanup()

    def _app(self, lines, publisher=None):
        publisher = publisher or FakePublisher()
        printer = FakePrinter()
        app = self.run.Keck3Application(serial_reader=FakeSerial(lines), api_client=FakeAPI(),
                                        publisher=publisher, label_printer=printer, outbox=self.outbox)
        events = []
        app.add_listener(lambda e, d: events.append((e, d)))
        return app, publisher, printer, events

    @staticmethod
    def _wait(condition, timeout=3.0):
        deadline = time.time() + timeout
        while time.time() < deadline and not condition():
            time.sleep(0.02)
        return condition()

    def test_full_scenario(self):
        # ligne orpheline, contrôle électrique OK (durée 0 → étiquettes), trame incomplète recalée, chauffe statut 0
        lines = ['00000001 00000002'] + as_lines(ELECTRICAL_FRAME) + [as_lines(HEAT_FRAME)[0]] + as_lines(HEAT_FRAME)
        app, publisher, printer, events = self._app(lines)
        self.assertTrue(app.start())
        self.assertTrue(self._wait(lambda: len(publisher.calls) >= 2 and self.outbox.counts() == (0, 0)))
        app.stop()

        self.assertEqual([k for k, _ in publisher.calls], ['electrical', 'heat'])
        self.assertEqual(publisher.calls[0][1].serial_number, 'F111111111-1')
        self.assertEqual(publisher.calls[1][1].temperature, 45.0)
        self.assertEqual([k for k, _ in printer.jobs], ['barcode', 'serial'])
        self.assertEqual(app.machines.program_number_for('F111111111-1'), 1)
        names = [e for e, _ in events]
        self.assertIn('api', names)
        self.assertIn('queued', names)
        self.assertIn('printed', names)
        self.assertEqual(names.count('transmitted'), 2)

    def test_heat_ok_prints_only_for_heat_programs(self):
        # programme 1 = durée 0 → une chauffe OK ne doit PAS imprimer
        line2 = ['111111111', '00000001', '00000375', '00001850', '00000001'] + ['0'] * 35
        lines = as_lines(ELECTRICAL_FRAME) + as_lines((HEAT_FRAME[0], line2))
        app, publisher, printer, events = self._app(lines)
        self.assertTrue(app.start())
        self.assertTrue(self._wait(lambda: len(publisher.calls) >= 2))
        app.stop()
        self.assertEqual(len(printer.jobs), 2)  # uniquement celles du contrôle électrique

    def test_transient_failure_is_replayed_and_label_printed_after_acceptance(self):
        publisher = FakePublisher({'F111111111-1': [
            PublishResult(ok=False, error='timeout', transient=True),
            PublishResult(ok=False, error='timeout', transient=True),
        ]})
        app, publisher, printer, events = self._app(as_lines(ELECTRICAL_FRAME), publisher)
        self.assertTrue(app.start())
        self.assertTrue(self._wait(lambda: len(publisher.calls) >= 3 and self.outbox.counts() == (0, 0)))
        app.stop()
        self.assertEqual(len(publisher.calls), 3)  # 2 pannes puis acceptation
        self.assertEqual([k for k, _ in printer.jobs], ['barcode', 'serial'])
        transmitted = [d for e, d in events if e == 'transmitted']
        self.assertEqual([d['ok'] for d in transmitted], [False, False, True])

    def test_definitive_refusal_is_parked_without_label(self):
        publisher = FakePublisher({'F111111111-1': [PublishResult(ok=False, error='Invalid parameter')]})
        app, publisher, printer, events = self._app(as_lines(ELECTRICAL_FRAME), publisher)
        self.assertTrue(app.start())
        self.assertTrue(self._wait(lambda: self.outbox.counts() == (0, 1)))
        app.stop()
        self.assertEqual(len(publisher.calls), 1)
        self.assertEqual(printer.jobs, [])
        failed = json.loads(next(self.outbox.failed_directory.glob('*.json')).read_text(encoding='utf-8'))
        self.assertEqual(failed['last_error'], 'Invalid parameter')

    def test_pending_entries_survive_restart(self):
        # 1er run : Open Prod en panne, le contrôle reste en file ; 2e run : il est rejoué et imprimé
        down = FakePublisher({'F111111111-1': [PublishResult(ok=False, error='down', transient=True)] * 50})
        app, _, printer, _ = self._app(as_lines(ELECTRICAL_FRAME), down)
        self.assertTrue(app.start())
        self.assertTrue(self._wait(lambda: len(down.calls) >= 1))
        app.stop()
        self.assertEqual(self.outbox.counts(), (1, 0))
        self.assertEqual(printer.jobs, [])

        app2, up, printer2, _ = self._app([])
        self.assertTrue(app2.start())
        self.assertTrue(self._wait(lambda: self.outbox.counts() == (0, 0)))
        app2.stop()
        self.assertEqual(up.calls[0][1].serial_number, 'F111111111-1')
        self.assertEqual([k for k, _ in printer2.jobs], ['barcode', 'serial'])

    def test_start_refused_while_previous_reader_alive(self):
        class BlockingSerial(FakeSerial):
            def read_line(self):
                time.sleep(0.3)
                return None
        app = self.run.Keck3Application(serial_reader=BlockingSerial([]), api_client=FakeAPI(),
                                        publisher=FakePublisher(), label_printer=FakePrinter(), outbox=self.outbox)
        self.assertTrue(app.start())
        self.assertFalse(app.start())  # jamais deux lecteurs sur le même port
        self.assertEqual(sum(1 for t in threading.enumerate() if t.name == 'DataReader'), 1)
        app.stop()
        self.assertFalse(app.is_reader_alive)
        self.assertFalse(app.is_publisher_alive)


if __name__ == '__main__':
    unittest.main()
