#!/usr/bin/env python
"""
Keck3 - Test Control Data Acquisition System
Application principale pour l'acquisition de données du banc de contrôle D1118
et transmission directe vers Open Prod.
"""

import threading
import signal
import sys
import json
from typing import Optional

from core.logger import setup_logger
from core.serial_reader import SerialReader
from core.label_printer import LabelPrinter
from api.client import OpenProdAPIClient
from api.models import DataParser
from config import (
    SERIAL_PORT,
    OPEN_PROD_BASE_URL,
    OPEN_PROD_API_KEY,
    ELECTRICAL_CONTROL_DATA_LENGTH,
)

logger = setup_logger(__name__)

class Keck3Application:
    """Application principale de Keck3."""

    def __init__(self):
        self.serial_reader = SerialReader(SERIAL_PORT)
        self.api_client = OpenProdAPIClient(OPEN_PROD_BASE_URL, OPEN_PROD_API_KEY)
        self.label_printer = LabelPrinter()
        self.is_running = False

        # Threads
        self.thread_data_reader = None
        self.thread_label_printer = None

    def start(self):
        """Démarre l'application."""
        logger.info("=" * 60)
        logger.info("Démarrage de Keck3")
        logger.info("=" * 60)

        if not OPEN_PROD_API_KEY:
            logger.error("OPEN_PROD_API_KEY non configurée. Vérifiez le fichier .env")
            return False

        self.is_running = True

        # Affiche les ports disponibles
        SerialReader.list_available_ports()

        # Lance le lecteur de port série
        logger.info(f"Tentative de connexion au port série: {SERIAL_PORT}")
        if not self.serial_reader.connect():
            logger.error("Impossible de se connecter au port série")
            self.is_running = False
            return False

        # Démarre les threads
        self.thread_data_reader = threading.Thread(
            target=self._data_reader_loop,
            name="DataReader",
            daemon=False
        )
        self.thread_data_reader.start()

        self.thread_label_printer = threading.Thread(
            target=self._label_printer_loop,
            name="LabelPrinter",
            daemon=False
        )
        self.thread_label_printer.start()

        logger.info("Application Keck3 démarrée")
        return True

    def _data_reader_loop(self):
        """Boucle principale de lecture des données du banc."""
        logger.info("Lecteur de données démarré")
        logger.info("En attente des données du banc de contrôle D1118...")

        buffer_frame = []

        while self.is_running and self.serial_reader.is_connected:
            try:
                line = self.serial_reader.read_line()

                if line is None:
                    continue

                buffer_frame.append(line)

                if len(buffer_frame) == 2:
                    self._process_frame(tuple(buffer_frame))
                    buffer_frame = []

            except KeyboardInterrupt:
                logger.info("Arrêt demandé (Ctrl+C)")
                self.is_running = False
                break
            except Exception as e:
                logger.error(f"Erreur dans la boucle de lecture: {e}")
                continue

        logger.info("Lecteur de données arrêté")

    def _process_frame(self, frame: tuple):
        """Traite une trame complète de données."""
        logger.debug(f"Trame reçue: {frame}")

        control_type = DataParser.classify_frame(frame)

        if control_type == 'electrical':
            self._process_electrical_control(frame)
        elif control_type == 'heat':
            self._process_heat_control(frame)
        else:
            logger.warning(f"Type de contrôle non reconnu: {frame}")

    def _process_electrical_control(self, frame: tuple):
        """Traite les données de contrôle électrique."""
        logger.info("Traitement contrôle électrique...")

        electrical_data = DataParser.parse_electrical_control(frame)

        if electrical_data is None:
            logger.warning("Impossible de parser les données de contrôle électrique")
            return

        # Prépare les données pour l'API
        data_payload = {
            'frame': list(frame),
            'datetime': electrical_data.datetime.isoformat(),
            'continuityTest': electrical_data.continuity_test,
            'hvVoltageTest': electrical_data.hv_voltage_test,
            'hvIntensityLossTest': electrical_data.hv_intensity_loss_test,
            'insulationTest': electrical_data.insulation_test,
            'powerVoltageTest': electrical_data.power_voltage_test,
            'powerIntensityTest': electrical_data.power_intensity_test,
            'powerCalcIntensityTest': electrical_data.power_calc_intensity_test,
        }

        logger.debug(f"Envoi données électriques: {json.dumps(data_payload, indent=2)}")

        response = self.api_client.post_electrical_control(data_payload)

        if response:
            logger.info(f"Données électriques transmises avec succès: {response}")
        else:
            logger.error("Échec de la transmission des données électriques")

    def _process_heat_control(self, frame: tuple):
        """Traite les données de contrôle thermique."""
        logger.info("Traitement contrôle thermique...")

        heat_data_list = DataParser.parse_heat_control(frame)

        if heat_data_list is None or not heat_data_list:
            logger.warning("Impossible de parser les données de contrôle thermique")
            return

        # Prépare les données pour l'API
        data_payload = {
            'frame': list(frame),
            'datetime': heat_data_list[0].datetime.isoformat(),
            'results': [
                {
                    'wayNumber': data.way_number,
                    'temperature': data.temperature,
                    'datetime': data.datetime.isoformat(),
                }
                for data in heat_data_list
            ]
        }

        logger.debug(f"Envoi données thermiques: {json.dumps(data_payload, indent=2)}")

        response = self.api_client.post_heat_control(data_payload)

        if response:
            logger.info(f"Données thermiques transmises avec succès: {response}")
        else:
            logger.error("Échec de la transmission des données thermiques")

    def _label_printer_loop(self):
        """Boucle d'impression des étiquettes."""
        try:
            self.label_printer.start()
        except Exception as e:
            logger.error(f"Erreur dans la boucle d'impression: {e}")

    def stop(self):
        """Arrête l'application proprement."""
        logger.info("Arrêt de Keck3...")
        self.is_running = False

        # Arrête les services
        self.serial_reader.disconnect()
        self.label_printer.stop()
        self.api_client.close()

        # Attend la fin des threads
        if self.thread_data_reader and self.thread_data_reader.is_alive():
            self.thread_data_reader.join(timeout=5)

        if self.thread_label_printer and self.thread_label_printer.is_alive():
            self.thread_label_printer.join(timeout=5)

        logger.info("Keck3 arrêté")

def signal_handler(signum, frame):
    """Gestionnaire de signaux pour arrêt gracieux."""
    logger.info(f"Signal reçu ({signum})")
    if app:
        app.stop()
    sys.exit(0)

if __name__ == '__main__':
    app = None

    try:
        # Enregistre les gestionnaires de signaux
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Lance l'application
        app = Keck3Application()

        if not app.start():
            logger.error("Démarrage échoué")
            sys.exit(1)

        # Garde l'app en vie
        while app.is_running:
            try:
                signal.pause()
            except (KeyboardInterrupt, AttributeError):
                break

    except Exception as e:
        logger.error(f"Erreur fatale: {e}", exc_info=True)
        if app:
            app.stop()
        sys.exit(1)
