"""Tests du parser sur les trames réelles du banc D1118 (archivées dans keck1)."""

import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.models import DataParser, is_header_line, parse_header, to_int  # noqa: E402

# keck1 ApiController::testElectricalAction — trame telle que reçue (NUL + CRLF)
ELECTRICAL_FRAME = (
    ["29/10/2018", "13:51:10\r\n"],
    ["111111111\x00", "00000001\x00", "00000375\x00", "00000001\x00", "00000050\x00", "00001218\x00",
     "00000002\x00", "00000119\x00", "000002427\x00", "00000234\x00", "00000221\x00", "00000001\r\n"],
)

# keck1 ApiController::testHeatAction — 8 voies × 5 champs, seule la voie 1 est active
HEAT_FRAME = (
    ["29/10/2018", "13:55:53\r\n"],
    ["111111111\x00", "00000001\x00", "00000375\x00", "00000450\x00", "00000000\x00"] + ["00000000\x00"] * 35,
)


class HelpersTest(unittest.TestCase):
    def test_to_int_strips_nul_and_leading_zeros(self):
        self.assertEqual(to_int("000002427\x00"), 2427)
        self.assertEqual(to_int("00000001\r\n"), 1)
        self.assertEqual(to_int("abc"), 0)

    def test_header_detection(self):
        self.assertTrue(is_header_line(["29/10/2018", "13:51:10"]))
        self.assertFalse(is_header_line(["111111111\x00", "00000001"]))
        self.assertFalse(is_header_line([]))

    def test_parse_header(self):
        self.assertEqual(parse_header(["29/10/2018", "13:51:10\r\n"]), datetime(2018, 10, 29, 13, 51, 10))
        self.assertIsNone(parse_header(["29/10/2018"]))


class ElectricalTest(unittest.TestCase):
    def test_classification(self):
        self.assertEqual(DataParser.classify_frame(ELECTRICAL_FRAME), 'electrical')

    def test_parse_real_frame(self):
        data = DataParser.parse_electrical_control(ELECTRICAL_FRAME)
        self.assertIsNotNone(data)
        self.assertEqual(data.datetime, datetime(2018, 10, 29, 13, 51, 10))
        self.assertEqual(data.fab_order_number, 'F111111111')
        self.assertEqual(data.serial_number, 'F111111111-1')
        self.assertEqual(data.operator_number, 375)
        self.assertEqual(data.program_number, 1)
        self.assertEqual(data.continuity_test, 50)
        self.assertEqual(data.hv_voltage_test, 1218)
        self.assertEqual(data.hv_intensity_loss_test, 2)
        self.assertEqual(data.insulation_test, 119)
        self.assertAlmostEqual(data.power_voltage_test, 242.7)
        self.assertAlmostEqual(data.power_intensity_test, 0.234)
        self.assertAlmostEqual(data.power_calc_intensity_test, 0.221)
        self.assertEqual(data.status_code, 1)
        self.assertTrue(data.is_ok)

    def test_as_dict_exposes_fields_and_status_ok(self):
        data = DataParser.parse_electrical_control(ELECTRICAL_FRAME).as_dict()
        self.assertEqual(data['datetime'], datetime(2018, 10, 29, 13, 51, 10))
        self.assertTrue(data['status_ok'])
        self.assertIn('serial_number', data)
        self.assertIn('program_number', data)

    def test_rejects_heat_frame_and_empty_order(self):
        self.assertIsNone(DataParser.parse_electrical_control(HEAT_FRAME))
        empty = (ELECTRICAL_FRAME[0], ["00000000"] + ELECTRICAL_FRAME[1][1:])
        self.assertIsNone(DataParser.parse_electrical_control(empty))
        short = (ELECTRICAL_FRAME[0], ELECTRICAL_FRAME[1][:7])
        self.assertIsNone(DataParser.parse_electrical_control(short))


class HeatTest(unittest.TestCase):
    def test_classification(self):
        self.assertEqual(DataParser.classify_frame(HEAT_FRAME), 'heat')

    def test_parse_real_frame_single_way(self):
        ways = DataParser.parse_heat_control(HEAT_FRAME)
        self.assertEqual(len(ways), 1)
        way = ways[0]
        self.assertEqual(way.way_number, 1)
        self.assertEqual(way.datetime, datetime(2018, 10, 29, 13, 55, 53))
        self.assertEqual(way.fab_order_number, 'F111111111')
        self.assertEqual(way.serial_number, 'F111111111-1')
        self.assertEqual(way.operator_number, 375)
        self.assertAlmostEqual(way.temperature, 45.0)
        self.assertEqual(way.status_code, 0)
        self.assertFalse(way.is_ok)

    def test_multiple_ways_and_gaps(self):
        line2 = ["0"] * 40
        line2[10:15] = ["123", "7", "42", "1850", "1"]   # voie 3
        line2[35:40] = ["456", "2", "42", "600", "0"]    # voie 8
        ways = DataParser.parse_heat_control((HEAT_FRAME[0], line2))
        self.assertEqual([w.way_number for w in ways], [3, 8])
        self.assertEqual(ways[0].serial_number, 'F123-7')
        self.assertAlmostEqual(ways[0].temperature, 185.0)
        self.assertTrue(ways[0].is_ok)
        self.assertEqual(ways[1].serial_number, 'F456-2')

    def test_no_active_way_returns_empty_list(self):
        self.assertEqual(DataParser.parse_heat_control((HEAT_FRAME[0], ["0"] * 40)), [])

    def test_rejects_electrical_frame(self):
        self.assertIsNone(DataParser.parse_heat_control(ELECTRICAL_FRAME))


if __name__ == '__main__':
    unittest.main()
