import re
from typing import List, Optional

import serial
import serial.tools.list_ports
from serial.tools.list_ports_common import ListPortInfo

from core.logger import setup_logger
from config import SERIAL_PORT, SERIAL_PORT_MATCH, SERIAL_BAUDRATE, SERIAL_PARITY, SERIAL_TIMEOUT

logger = setup_logger(__name__)


def split_fields(raw_line: str) -> Optional[List[str]]:
    """Découpe une ligne du banc en champs : octets NUL retirés, séparateur espace."""
    cleaned = raw_line.replace('\x00', '').strip()
    if not cleaned:
        return None
    fields = [part for part in cleaned.split(' ') if part.strip()]
    return fields or None


def choose_port(ports: List[ListPortInfo], configured: str, match: str) -> Optional[str]:
    """Port à ouvrir : celui configuré, sinon ('auto') un adaptateur reconnu, sinon l'unique port présent.

    Un poste Windows expose souvent des ports virtuels (Bluetooth, carte mère) qui
    s'ouvrent sans erreur mais ne reçoivent jamais rien : en mode auto on ne prend
    un port arbitraire que s'il est seul.
    """
    if configured and configured.lower() != 'auto':
        return configured
    pattern = re.compile(match, re.IGNORECASE) if match else None
    if pattern:
        recognised = [p for p in ports if pattern.search(f"{p.description} {p.hwid} {p.manufacturer or ''}")]
        if recognised:
            return recognised[0].device
    if len(ports) == 1:
        return ports[0].device
    return None


class SerialReader:
    """Lecteur de données depuis le banc de contrôle via port série."""

    def __init__(self, port: Optional[str] = None):
        self.configured_port = port or SERIAL_PORT
        self.port: Optional[str] = None
        self.baudrate = SERIAL_BAUDRATE
        self.parity = SERIAL_PARITY
        self.timeout = SERIAL_TIMEOUT
        self.serial: Optional[serial.Serial] = None
        self.is_connected = False

    @staticmethod
    def list_available_ports() -> List[ListPortInfo]:
        """Retourne la liste des ports série disponibles."""
        ports = list(serial.tools.list_ports.comports())
        logger.info(f"Ports disponibles: {len(ports)}")
        for port in ports:
            logger.info(f"  - {port.device}: {port.description} ({port.hwid})")
        return ports

    def resolve_port(self) -> Optional[str]:
        """Port à ouvrir. Une fois choisi, il est conservé pour les reconnexions."""
        if self.port:
            return self.port
        ports = list(serial.tools.list_ports.comports())
        chosen = choose_port(ports, self.configured_port, SERIAL_PORT_MATCH)
        if chosen is None:
            listing = ', '.join(f"{p.device} ({p.description})" for p in ports) or 'aucun'
            logger.error(f"Impossible de choisir un port série en mode auto (ports: {listing}). "
                         f"Fixer SERIAL_PORT ou SERIAL_PORT_MATCH dans .env")
        return chosen

    def _close_handle(self) -> None:
        if self.serial is not None:
            try:
                self.serial.close()
            except (serial.SerialException, OSError) as e:
                logger.debug(f"Fermeture du port ignorée: {e}")
            self.serial = None

    def connect(self) -> bool:
        """Établit la connexion au port série (ferme d'abord un éventuel handle resté ouvert)."""
        self._close_handle()
        self.port = self.resolve_port()
        if not self.port:
            self.is_connected = False
            return False
        try:
            logger.info(f"Connexion au port {self.port} (vitesse: {self.baudrate} baud)...")
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                parity=self.parity,
                timeout=self.timeout
            )
            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()
            self.is_connected = True
            logger.info(f"Connecté au banc de contrôle D1118 sur {self.port}")
            return True
        except (serial.SerialException, OSError) as e:
            logger.error(f"Erreur de connexion au port série: {e}")
            self._close_handle()
            self.is_connected = False
            return False

    def disconnect(self) -> None:
        """Ferme la connexion au port série."""
        was_open = self.serial is not None and self.serial.is_open
        self.is_connected = False
        self._close_handle()
        if was_open:
            logger.info("Déconnecté du port série")

    def read_line(self) -> Optional[List[str]]:
        """Lit une ligne et la découpe en champs.

        ``None`` = rien reçu avant le timeout, ou erreur. Une erreur de port ferme
        le handle et passe ``is_connected`` à False pour déclencher une reconnexion.
        """
        if not self.is_connected or self.serial is None:
            return None

        try:
            raw_line = self.serial.readline().decode('ascii', errors='replace')
        except (serial.SerialException, OSError) as e:
            logger.error(f"Port série perdu: {e}")
            self.is_connected = False
            self._close_handle()
            return None

        return split_fields(raw_line)

    def close(self) -> None:
        """Alias pour disconnect()."""
        self.disconnect()
