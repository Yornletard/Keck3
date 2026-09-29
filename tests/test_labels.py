"""Tests de la génération d'étiquettes SBPL et de la règle d'impression."""

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.labels import (  # noqa: E402
    LabelBuilder, MachineRegistry, Program, ProgramCatalog, should_print,
)

LABELS_DIR = Path(__file__).resolve().parent.parent / 'labels'

CALORIBAC = Program(code=1, name='CALORIBAC', product_code='260434', duration=0,
                    labels=('CALORIBAC 260434', '220-240 V~50 Hz  300 W     IPX3', 'Ligne 3'))
WITH_HEAT = Program(code=2, name='ETUVE', product_code='999999', duration=45)


class LabelBuilderTest(unittest.TestCase):
    def setUp(self):
        self.builder = LabelBuilder(LABELS_DIR)
        self.original_barcode = (LABELS_DIR / 'barcode.sbpl').read_bytes()

    def test_barcode_label_replaces_all_placeholders(self):
        label = self.builder.barcode_label('F123456-7', CALORIBAC, now=datetime(2026, 9, 11))
        for needle in (b'NUMERO_OF', b'YEAR', b'LIBELLE1', b'LIBELLE2', b'LIBELLE3'):
            self.assertNotIn(needle, label)
        self.assertIn(b'F123456-7', label)
        self.assertIn(b'\x01B1126\x17', label)  # champ YEAR → "26" (\x01 = préfixe SBPL, \x17 = fin)
        self.assertIn(b'CALORIBAC 260434', label)
        self.assertIn(b'220-240 V~50 Hz  300 W     IPX3', label)

    def test_barcode_label_keeps_binary_tail(self):
        label = self.builder.barcode_label('F1-1', CALORIBAC)
        self.assertTrue(label.endswith(self.original_barcode[-64:]))

    def test_serial_label_replaces_code_and_both_serials(self):
        label = self.builder.serial_number_label('F123456-7', CALORIBAC)
        self.assertNotIn(b'NUMEROSERIECB', label)
        self.assertNotIn(b'\x01B01CODE\x17', label)
        self.assertEqual(label.count(b'F123456-7'), 2)
        self.assertIn(b'\x01B01260434\x17', label)

    def test_missing_label_text_becomes_empty(self):
        label = self.builder.barcode_label('F1-1', WITH_HEAT)
        self.assertIn(b'\x01B05\x17', label)

    def test_every_occurrence_of_a_marker_is_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'serial_number.sbpl').write_bytes(b'A NUMEROSERIECB B NUMEROSERIECB C NUMEROSERIECB CODE')
            label = LabelBuilder(Path(tmp)).serial_number_label('F9-9', CALORIBAC)
            self.assertEqual(label, b'A F9-9 B F9-9 C F9-9 260434')


class ShouldPrintTest(unittest.TestCase):
    def test_electrical_only_program(self):
        self.assertTrue(should_print('electrical', True, CALORIBAC))
        self.assertFalse(should_print('heat', True, CALORIBAC))
        self.assertFalse(should_print('electrical', False, CALORIBAC))

    def test_program_with_heat_control(self):
        self.assertFalse(should_print('electrical', True, WITH_HEAT))
        self.assertTrue(should_print('heat', True, WITH_HEAT))
        self.assertFalse(should_print('heat', False, WITH_HEAT))

    def test_unknown_program(self):
        self.assertFalse(should_print('electrical', True, None))


class CatalogAndRegistryTest(unittest.TestCase):
    def test_catalog_from_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'programs.json'
            path.write_text(json.dumps({
                "1": {"name": "CALORIBAC", "product_code": "260434", "duration": 0,
                      "labels": ["CALORIBAC 260434", "220-240 V"]},
            }), encoding='utf-8')
            catalog = ProgramCatalog(path)
            program = catalog.get(1)
            self.assertEqual(len(catalog), 1)
            self.assertEqual(program.product_code, '260434')
            self.assertEqual(program.labels, ('CALORIBAC 260434', '220-240 V'))
            self.assertEqual(program.label(2), '')
            self.assertIsNone(catalog.get(99))
            self.assertIsNone(catalog.get(None))

    def test_missing_catalog_is_empty(self):
        self.assertEqual(len(ProgramCatalog(Path('/nonexistent/programs.json'))), 0)

    def test_malformed_catalog_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'programs.json'
            path.write_text('{"1": {"name": "X", "duration": "quarante"}, "2": {"name": "Y"},', encoding='utf-8')
            self.assertEqual(len(ProgramCatalog(path)), 0)  # JSON invalide → vide, sans exception
            path.write_text('{"1": {"name": "X", "duration": "quarante"}, "2": {"name": "Y"}}', encoding='utf-8')
            catalog = ProgramCatalog(path)
            self.assertEqual(len(catalog), 1)  # entrée invalide ignorée, l'autre chargée
            self.assertEqual(catalog.get(2).name, 'Y')

    def test_registry_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'machines.json'
            MachineRegistry(path).remember('F1-1', 7)
            self.assertEqual(MachineRegistry(path).program_number_for('F1-1'), 7)
            self.assertIsNone(MachineRegistry(path).program_number_for('F2-2'))
            self.assertFalse(path.with_suffix('.json.tmp').exists())

    def test_registry_is_bounded_and_survives_io_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = MachineRegistry(Path(tmp) / 'machines.json', max_entries=3)
            for i in range(5):
                registry.remember(f'F{i}-1', i)
            self.assertIsNone(registry.program_number_for('F0-1'))
            self.assertEqual(registry.program_number_for('F4-1'), 4)
            self.assertEqual(len(MachineRegistry(Path(tmp) / 'machines.json')._machines), 3)
            # dossier inexistant et non créable → loggé, pas propagé
            broken = MachineRegistry(Path('/nonexistent-root-dir/x/machines.json'))
            broken.remember('F9-9', 1)
            self.assertEqual(broken.program_number_for('F9-9'), 1)


if __name__ == '__main__':
    unittest.main()
