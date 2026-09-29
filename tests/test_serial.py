"""Tests du choix de port série et du découpage des lignes."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.serial_reader import choose_port, split_fields  # noqa: E402

MATCH = 'USB|FTDI|Prolific|CH340|CP210|UART'


def port(device, description, hwid='', manufacturer=None):
    return SimpleNamespace(device=device, description=description, hwid=hwid, manufacturer=manufacturer)


class ChoosePortTest(unittest.TestCase):
    def test_configured_port_wins(self):
        self.assertEqual(choose_port([port('COM7', 'x')], 'COM3', MATCH), 'COM3')

    def test_auto_prefers_recognised_adapter_over_bluetooth(self):
        ports = [port('COM3', 'Standard Serial over Bluetooth link'),
                 port('COM4', 'Standard Serial over Bluetooth link'),
                 port('COM5', 'USB Serial Port', 'USB VID:PID=0403:6001', 'FTDI')]
        self.assertEqual(choose_port(ports, 'auto', MATCH), 'COM5')

    def test_auto_single_unknown_port_is_used(self):
        self.assertEqual(choose_port([port('COM1', 'Communications Port')], 'auto', MATCH), 'COM1')

    def test_auto_refuses_ambiguity(self):
        ports = [port('COM1', 'Communications Port'), port('COM3', 'Bluetooth link')]
        self.assertIsNone(choose_port(ports, 'auto', MATCH))
        self.assertIsNone(choose_port([], 'auto', MATCH))


class SplitFieldsTest(unittest.TestCase):
    def test_nul_and_spaces(self):
        self.assertEqual(split_fields('29/10/2018 13:51:10\r\n'), ['29/10/2018', '13:51:10'])
        self.assertEqual(split_fields('111111111\x00 00000001\x00  00000375\x00'), ['111111111', '00000001', '00000375'])
        self.assertIsNone(split_fields('\x00\r\n'))


if __name__ == '__main__':
    unittest.main()


class ReconnectTest(unittest.TestCase):
    """Le handle perdu doit être fermé avant toute réouverture (sinon Windows refuse l'accès au port)."""

    def test_lost_port_is_closed_then_reopened(self):
        from unittest.mock import patch, MagicMock
        import serial as pyserial
        from core.serial_reader import SerialReader

        handles = []

        def fake_serial(**kwargs):
            handle = MagicMock()
            handle.is_open = True
            handle.readline.side_effect = pyserial.SerialException('ClearCommError failed')
            handles.append(handle)
            return handle

        with patch('core.serial_reader.serial.Serial', side_effect=fake_serial):
            reader = SerialReader('COM3')
            self.assertTrue(reader.connect())
            self.assertIsNone(reader.read_line())          # perte du port
            self.assertFalse(reader.is_connected)
            handles[0].close.assert_called_once()           # handle libéré immédiatement
            self.assertTrue(reader.connect())               # réouverture sur le même port
            self.assertEqual(reader.port, 'COM3')
            self.assertEqual(len(handles), 2)
            reader.disconnect()
            handles[1].close.assert_called_once()
