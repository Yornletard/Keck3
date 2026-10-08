"""Tests du mapping contrôle Keck3 → enregistrement Open Prod."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.client import OpenProdError, OpenProdUnavailable  # noqa: E402
from api.models import DataParser  # noqa: E402
from api.publisher import ControlPublisher, TargetMapping  # noqa: E402
from tests.test_models import ELECTRICAL_FRAME, HEAT_FRAME  # noqa: E402

EXAMPLE = Path(__file__).resolve().parent.parent / 'openprod_mapping.example.json'


class FakeClient:
    def __init__(self, fail_with=None, existing=None):
        self.created = []
        self.reads = []
        self.fail_with = fail_with
        self.existing = existing or []
        self.next_id = 100

    def read(self, model, filters=None, fields=None, limit=None, order=None, retry=True):
        self.reads.append((model, filters, retry))
        if model == 'mrp.manufacturingorder':
            return [{'id': 4242}] if filters and filters[0][2] == 'OF111111111' else []
        return list(self.existing)

    def create(self, model, values, use_onchange=True, retry=True):
        if self.fail_with:
            raise self.fail_with
        self.created.append((model, values))
        self.next_id += 1
        return [self.next_id]


def publisher_with(client, mapping: dict) -> ControlPublisher:
    tmp = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8')
    json.dump(mapping, tmp)
    tmp.close()
    return ControlPublisher(client, Path(tmp.name))


class TargetMappingTest(unittest.TestCase):
    def test_values_follow_mapping(self):
        control = DataParser.parse_electrical_control(ELECTRICAL_FRAME)
        mapping = TargetMapping(model='m', fields={'serial_number': 'name', 'datetime': 'date_time', 'status_ok': 'is_ok'},
                                constants={'company_id': 1}, raw_frame_field='raw')
        values = mapping.values_for(control, ELECTRICAL_FRAME)
        self.assertEqual(values['name'], 'F111111111-1')
        self.assertEqual(values['date_time'], '2018-10-29 13:51:10')
        self.assertTrue(values['is_ok'])
        self.assertEqual(values['company_id'], 1)
        self.assertTrue(values['raw'].startswith('29/10/2018 13:51:10\n111111111 00000001'))
        self.assertNotIn('\x00', values['raw'])  # refusé par la base d'Open Prod
        self.assertNotIn('\r', values['raw'])
        self.assertNotIn('operator_number', values)

    def test_cast_and_summer_time_conversion(self):
        from datetime import datetime
        control = DataParser.parse_electrical_control(ELECTRICAL_FRAME)
        control.datetime = datetime(2026, 7, 1, 9, 30, 0)  # heure d'été : UTC+2
        mapping = TargetMapping(model='m', fields={'datetime': 'd', 'status_ok': 'ok'},
                                casts={'status_ok': 'int'}, datetime_timezone='Europe/Paris')
        values = mapping.values_for(control)
        self.assertEqual(values['d'], '2026-07-01 07:30:00')
        self.assertIs(values['ok'], 1)

    def test_unknown_attribute_is_rejected(self):
        control = DataParser.parse_electrical_control(ELECTRICAL_FRAME)
        with self.assertRaises(OpenProdError):
            TargetMapping(model='m', fields={'nope': 'x'}).values_for(control)


class PublisherTest(unittest.TestCase):
    def test_example_mapping_publishes_electrical_and_heat(self):
        client = FakeClient()
        publisher = ControlPublisher(client, EXAMPLE)
        self.assertTrue(publisher.is_configured)

        result = publisher.publish_electrical(DataParser.parse_electrical_control(ELECTRICAL_FRAME), ELECTRICAL_FRAME)
        self.assertTrue(result.ok)
        model, values = client.created[0]
        self.assertEqual(model, 'x_electrical_control')
        self.assertEqual(values['x_name'], 'F111111111-1')
        self.assertAlmostEqual(values['x_power_voltage_test'], 242.7)
        self.assertEqual(values['x_status_code'], 1)
        self.assertIs(values['x_is_ok'], True)
        self.assertEqual(values['x_mo_id'], 4242)  # F111111111 du banc → OF nommé OF111111111 dans Open Prod
        self.assertEqual(values['x_date_time'], '2018-10-29 12:51:10')  # heure de Paris (hiver) → UTC
        self.assertNotIn('fab_order_number', values)
        self.assertIsNone(result.warning)

        ways = DataParser.parse_heat_control(HEAT_FRAME)
        results = publisher.publish_heat(ways, HEAT_FRAME)
        self.assertEqual(len(results), 1)
        way, result = results[0]
        self.assertTrue(result.ok)
        self.assertEqual(way.way_number, 1)
        self.assertEqual(client.created[1][0], 'x_heating_measurement')
        self.assertEqual(client.created[1][1]['x_way_number'], 1)
        self.assertIs(client.created[1][1]['x_is_ok'], False)

    def test_one_record_and_one_result_per_way(self):
        client = FakeClient()
        publisher = publisher_with(client, {'heat': {'model': 'h', 'fields': {'serial_number': 'name'}}})
        line2 = ['0'] * 40
        line2[0:5] = ['1', '1', '1', '500', '1']
        line2[5:10] = ['2', '1', '1', '600', '1']
        ways = DataParser.parse_heat_control((HEAT_FRAME[0], line2))
        results = publisher.publish_heat(ways)
        self.assertEqual([r.ok for _, r in results], [True, True])
        self.assertEqual([v['name'] for _, v in client.created], ['F1-1', 'F2-1'])

    def test_dedupe_reads_before_create_and_skips_existing(self):
        client = FakeClient(existing=[{'id': 55}])
        publisher = ControlPublisher(client, EXAMPLE)
        result = publisher.publish_electrical(DataParser.parse_electrical_control(ELECTRICAL_FRAME))
        self.assertTrue(result.ok)
        self.assertTrue(result.duplicate)
        self.assertEqual(result.ids, [55])
        self.assertEqual(client.created, [])
        model, filters, retry = client.reads[0]
        self.assertEqual(model, 'x_electrical_control')
        self.assertEqual(filters, [['x_name', '=', 'F111111111-1'], ['x_date_time', '=', '2018-10-29 12:51:10']])
        self.assertFalse(retry)

    def test_create_is_never_retried_by_the_client(self):
        client = FakeClient()
        publisher = ControlPublisher(client, EXAMPLE)
        publisher.publish_heat(DataParser.parse_heat_control(HEAT_FRAME))
        self.assertEqual(client.reads[0][1][2], ['x_way_number', '=', 1])
        self.assertTrue(all(retry is False for _, _, retry in client.reads))

    def test_mapping_without_dedupe_skips_the_read(self):
        client = FakeClient()
        publisher = publisher_with(client, {'electrical': {'model': 'e', 'fields': {'serial_number': 'name'}}})
        self.assertTrue(publisher.publish_electrical(DataParser.parse_electrical_control(ELECTRICAL_FRAME)).ok)
        self.assertEqual(client.reads, [])

    def test_partial_heat_failure_keeps_other_ways(self):
        class FlakyClient(FakeClient):
            def create(self, model, values, use_onchange=True, retry=True):
                if values['name'] == 'F2-1':
                    raise OpenProdError('Invalid value')
                return super().create(model, values, use_onchange, retry)
        publisher = publisher_with(FlakyClient(), {'heat': {'model': 'h', 'fields': {'serial_number': 'name'}}})
        line2 = ['0'] * 40
        line2[0:5] = ['1', '1', '1', '500', '1']
        line2[5:10] = ['2', '1', '1', '600', '1']
        line2[10:15] = ['3', '1', '1', '700', '1']
        results = publisher.publish_heat(DataParser.parse_heat_control((HEAT_FRAME[0], line2)))
        self.assertEqual([r.ok for _, r in results], [True, False, True])
        self.assertIn('Invalid value', results[1][1].error)

    def test_empty_ids_is_a_failure(self):
        class SilentClient(FakeClient):
            def create(self, model, values, use_onchange=True, retry=True):
                return []
        publisher = publisher_with(SilentClient(), {'electrical': {'model': 'e', 'fields': {'serial_number': 'name'}}})
        result = publisher.publish_electrical(DataParser.parse_electrical_control(ELECTRICAL_FRAME))
        self.assertFalse(result.ok)

    def test_malformed_mapping_file_is_ignored(self):
        tmp = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8')
        tmp.write('{"electrical": {"model": "e",'); tmp.close()
        self.assertFalse(ControlPublisher(FakeClient(), Path(tmp.name)).is_configured)

    def test_missing_mapping_is_definitive_failure(self):
        publisher = publisher_with(FakeClient(), {'heat': {'model': 'h', 'fields': {}}})
        result = publisher.publish_electrical(DataParser.parse_electrical_control(ELECTRICAL_FRAME))
        self.assertFalse(result.ok)
        self.assertFalse(result.transient)
        self.assertIn('non configuré', result.error)

    def test_unavailable_is_transient(self):
        publisher = publisher_with(FakeClient(fail_with=OpenProdUnavailable('timeout')),
                                   {'electrical': {'model': 'e', 'fields': {'serial_number': 'name'}}})
        result = publisher.publish_electrical(DataParser.parse_electrical_control(ELECTRICAL_FRAME))
        self.assertFalse(result.ok)
        self.assertTrue(result.transient)

    def test_business_error_is_definitive(self):
        publisher = publisher_with(FakeClient(fail_with=OpenProdError('Invalid parameter')),
                                   {'electrical': {'model': 'e', 'fields': {'serial_number': 'name'}}})
        result = publisher.publish_electrical(DataParser.parse_electrical_control(ELECTRICAL_FRAME))
        self.assertFalse(result.ok)
        self.assertFalse(result.transient)

    def test_missing_relation_creates_without_link_and_warns(self):
        client = FakeClient()
        publisher = publisher_with(client, {'electrical': {
            'model': 'e', 'fields': {'serial_number': 'x_name'},
            'relations': {'fab_order_number': {'field': 'x_mo_id', 'model': 'mrp.manufacturingorder'}}}})
        line2 = list(ELECTRICAL_FRAME[1]); line2[0] = '999999'  # OF inconnu d'Open Prod
        result = publisher.publish_electrical(DataParser.parse_electrical_control((ELECTRICAL_FRAME[0], line2)))
        self.assertTrue(result.ok)
        self.assertIn("'F999999' introuvable", result.warning)
        self.assertNotIn('x_mo_id', client.created[0][1])
        self.assertEqual(client.reads[-1][0], 'mrp.manufacturingorder')

    def test_required_relation_missing_is_definitive_refusal(self):
        client = FakeClient()
        publisher = publisher_with(client, {'electrical': {
            'model': 'e', 'fields': {'serial_number': 'x_name'},
            'relations': {'fab_order_number': {'field': 'x_mo_id', 'model': 'mrp.manufacturingorder', 'required': True}}}})
        line2 = list(ELECTRICAL_FRAME[1]); line2[0] = '999999'
        result = publisher.publish_electrical(DataParser.parse_electrical_control((ELECTRICAL_FRAME[0], line2)))
        self.assertFalse(result.ok)
        self.assertFalse(result.transient)
        self.assertEqual(client.created, [])

    def test_relation_lookup_failure_is_transient(self):
        class DownClient(FakeClient):
            def read(self, model, filters=None, fields=None, limit=None, order=None, retry=True):
                if model == 'mrp.manufacturingorder':
                    raise OpenProdUnavailable('timeout')
                return super().read(model, filters, fields, limit, order, retry)
        publisher = publisher_with(DownClient(), {'electrical': {
            'model': 'e', 'fields': {'serial_number': 'x_name'},
            'relations': {'fab_order_number': {'field': 'x_mo_id', 'model': 'mrp.manufacturingorder'}}}})
        result = publisher.publish_electrical(DataParser.parse_electrical_control(ELECTRICAL_FRAME))
        self.assertFalse(result.ok)
        self.assertTrue(result.transient)

    def test_search_template_builds_the_open_prod_name(self):
        client = FakeClient()
        publisher = publisher_with(client, {'electrical': {
            'model': 'e', 'fields': {'serial_number': 'x_name'},
            'relations': {'fab_order_number': {'field': 'x_mo_id', 'model': 'mrp.manufacturingorder',
                                               'search_template': 'OF{digits}'}}}})
        result = publisher.publish_electrical(DataParser.parse_electrical_control(ELECTRICAL_FRAME))
        self.assertTrue(result.ok)
        self.assertEqual(client.reads[-1][1], [['name', '=', 'OF111111111']])
        self.assertEqual(client.created[0][1]['x_mo_id'], 4242)
        self.assertEqual(client.created[0][1]['x_name'], 'F111111111-1')  # le n° de série reste en F

    def test_unknown_timezone_disables_the_mapping(self):
        publisher = publisher_with(FakeClient(), {'electrical': {'model': 'e', 'fields': {'serial_number': 'x_name'},
                                                                 'datetime_timezone': 'Europe/Nowhere'}})
        self.assertFalse(publisher.is_configured)

    def test_unknown_cast_disables_the_mapping(self):
        publisher = publisher_with(FakeClient(), {'electrical': {'model': 'e', 'fields': {'serial_number': 'x_name'},
                                                                 'casts': {'status_ok': 'tuple'}}})
        self.assertFalse(publisher.is_configured)

    def test_missing_file_means_not_configured(self):
        publisher = ControlPublisher(FakeClient(), Path('/nonexistent/mapping.json'))
        self.assertFalse(publisher.is_configured)


if __name__ == '__main__':
    unittest.main()
