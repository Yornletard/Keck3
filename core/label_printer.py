import os
import sched
import time
from pathlib import Path
from typing import Optional
from core.logger import setup_logger
from config import LABEL_SHARE_PATH, LABEL_PRINTER_BARCODE, LABEL_PRINTER_SERIAL, LABEL_SCAN_INTERVAL

logger = setup_logger(__name__)

# Import win32print seulement sur Windows
try:
    import win32print
    HAS_WIN32PRINT = True
except ImportError:
    HAS_WIN32PRINT = False
    logger.warning("win32print non disponible - impression désactivée (Windows uniquement)")

class LabelPrinter:
    """Gère l'impression automatique des étiquettes."""

    def __init__(self):
        self.scheduler = sched.scheduler(time.time, time.sleep)
        self.label_path_barcode = Path(LABEL_SHARE_PATH) / "label_barcode.txt"
        self.label_path_serial = Path(LABEL_SHARE_PATH) / "label_serial_number.txt"
        self.printer_barcode = LABEL_PRINTER_BARCODE
        self.printer_serial = LABEL_PRINTER_SERIAL
        self.is_running = False

    def start(self):
        """Démarre le scan périodique des étiquettes."""
        if not HAS_WIN32PRINT:
            logger.warning("Impression d'étiquettes désactivée (win32print non disponible)")
            return

        logger.info("Démarrage du service d'impression d'étiquettes...")
        self.is_running = True
        self.scheduler.enter(LABEL_SCAN_INTERVAL, 1, self._scan_for_labels, ())
        self.scheduler.run()

    def _scan_for_labels(self):
        """Scan les fichiers d'étiquettes et lance l'impression."""
        try:
            # Scan code-barres
            if self.label_path_barcode.is_file():
                logger.info(f"Étiquette code-barres détectée: {self.label_path_barcode}")
                self._print_label(self.label_path_barcode, self.printer_barcode)

            # Scan numéro de série
            if self.label_path_serial.is_file():
                logger.info(f"Étiquette numéro de série détectée: {self.label_path_serial}")
                self._print_label(self.label_path_serial, self.printer_serial)

        except Exception as e:
            logger.error(f"Erreur lors du scan des étiquettes: {e}")
        finally:
            if self.is_running:
                self.scheduler.enter(LABEL_SCAN_INTERVAL, 1, self._scan_for_labels, ())

    def _print_label(self, label_path: Path, printer_name: str, qty: int = 1):
        """Imprime une étiquette."""
        if not HAS_WIN32PRINT:
            logger.warning(f"Impression non disponible pour {label_path}")
            return

        try:
            with open(label_path, 'rb') as f:
                raw_data = f.read()

            for _ in range(qty):
                try:
                    h_printer = win32print.OpenPrinter(printer_name)
                    win32print.StartDocPrinter(h_printer, 1, ("Étiquette", None, "RAW"))
                    try:
                        win32print.StartPagePrinter(h_printer)
                        win32print.WritePrinter(h_printer, raw_data)
                        win32print.EndPagePrinter(h_printer)
                        logger.info(f"Étiquette imprimée sur {printer_name}")
                    finally:
                        win32print.EndDocPrinter(h_printer)
                except Exception as e:
                    logger.error(f"Erreur lors de l'impression: {e}")
                finally:
                    win32print.ClosePrinter(h_printer)

            # Supprime le fichier après impression
            label_path.unlink()
            logger.info(f"Fichier d'étiquette supprimé: {label_path}")

        except IOError as e:
            logger.error(f"Erreur de lecture du fichier {label_path}: {e}")
        except Exception as e:
            logger.error(f"Erreur lors de l'impression: {e}")

    def stop(self):
        """Arrête le service d'impression."""
        self.is_running = False
        logger.info("Service d'impression d'étiquettes arrêté")
