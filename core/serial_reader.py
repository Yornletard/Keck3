import serial
import serial.tools.list_ports
from typing import Optional, List
from core.logger import setup_logger
from config import SERIAL_PORT, SERIAL_BAUDRATE, SERIAL_PARITY, SERIAL_TIMEOUT

logger = setup_logger(__name__)

class SerialReader:
    """Lecteur de données depuis le banc de contrôle via port série."""

    def __init__(self, port: Optional[str] = None):
        self.port = port or SERIAL_PORT
        self.baudrate = SERIAL_BAUDRATE
        self.parity = SERIAL_PARITY
        self.timeout = SERIAL_TIMEOUT
        self.serial = None
        self.is_connected = False

    @staticmethod
    def list_available_ports() -> List[tuple]:
        """Retourne la liste des ports série disponibles."""
        ports = list(serial.tools.list_ports.comports())
        logger.info(f"Ports disponibles: {len(ports)}")
        for port, desc, addr in ports:
            logger.info(f"  - {port}: {desc} ({addr})")
        return ports

    def connect(self) -> bool:
        """Établit la connexion au port série."""
        try:
            logger.info(f"Connexion au port {self.port} (vitesse: {self.baudrate} baud)...")
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                parity=self.parity,
                timeout=self.timeout
            )
            self.serial.flushInput()
            self.serial.flushOutput()
            self.is_connected = True
            logger.info(f"Connecté au banc de contrôle D1118 sur {self.port}")
            return True
        except serial.SerialException as e:
            logger.error(f"Erreur de connexion au port série: {e}")
            self.is_connected = False
            return False

    def disconnect(self):
        """Ferme la connexion au port série."""
        if self.serial and self.serial.is_open:
            self.serial.close()
            self.is_connected = False
            logger.info("Déconnecté du port série")

    def read_line(self) -> Optional[List[str]]:
        """Lit une ligne complète et la parse."""
        if not self.is_connected:
            logger.warning("Port série non connecté")
            return None

        try:
            raw_line = self.serial.readline().decode('ASCII').strip()
            if not raw_line:
                return None

            data = raw_line.split(" ")
            data = [d.strip() for d in data if d.strip()]
            return data if data else None

        except UnicodeDecodeError as e:
            logger.warning(f"Erreur de décodage: {e}")
            return None
        except Exception as e:
            logger.error(f"Erreur lors de la lecture: {e}")
            return None

    def read_frame(self) -> Optional[tuple]:
        """Lit une trame complète de données (2 lignes)."""
        frame = []
        for i in range(2):
            line = self.read_line()
            if line is None:
                return None
            frame.append(line)
            logger.debug(f"Ligne {i+1}: {line}")

        return tuple(frame)

    def close(self):
        """Alias pour disconnect()."""
        self.disconnect()
