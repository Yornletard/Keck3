from typing import Optional, Union
from core.logger import setup_logger
from config import LABEL_PRINTER_BARCODE, LABEL_PRINTER_SERIAL

logger = setup_logger(__name__)

# Import win32print seulement sur Windows
try:
    import win32print
    HAS_WIN32PRINT = True
except ImportError:
    HAS_WIN32PRINT = False
    logger.warning("win32print non disponible - impression désactivée (Windows uniquement)")

class LabelPrinter:
    """Gère l'impression immédiate des étiquettes vers les imprimantes réseau."""

    def __init__(self):
        self.printer_barcode = LABEL_PRINTER_BARCODE
        self.printer_serial = LABEL_PRINTER_SERIAL

    def print_barcode(self, raw_data: Union[bytes, str], qty: int = 1) -> bool:
        """Imprime immédiatement vers l'imprimante code-barres."""
        return self._print_to_printer(raw_data, self.printer_barcode, "Barcode", qty)

    def print_serial_number(self, raw_data: Union[bytes, str], qty: int = 1) -> bool:
        """Imprime immédiatement vers l'imprimante numéro de série."""
        return self._print_to_printer(raw_data, self.printer_serial, "Serial Number", qty)

    def print_to_printer(self, raw_data: Union[bytes, str], printer_name: str,
                        label_name: str = "Label", qty: int = 1) -> bool:
        """Imprime vers une imprimante spécifiée."""
        return self._print_to_printer(raw_data, printer_name, label_name, qty)

    def _print_to_printer(self, raw_data: Union[bytes, str], printer_name: str,
                         label_name: str, qty: int = 1) -> bool:
        """Effectue l'impression vers l'imprimante spécifiée."""
        if not HAS_WIN32PRINT:
            logger.warning(f"Impression {label_name} non disponible (win32print manquant - Windows seulement)")
            return False

        # Convertir string en bytes si nécessaire
        if isinstance(raw_data, str):
            raw_data = raw_data.encode('ascii')

        try:
            for attempt in range(qty):
                try:
                    h_printer = win32print.OpenPrinter(printer_name)
                    win32print.StartDocPrinter(h_printer, 1, (label_name, None, "RAW"))
                    try:
                        win32print.StartPagePrinter(h_printer)
                        win32print.WritePrinter(h_printer, raw_data)
                        win32print.EndPagePrinter(h_printer)
                        logger.info(f"✓ {label_name} imprimé sur {printer_name} (copie {attempt + 1}/{qty})")
                    finally:
                        win32print.EndDocPrinter(h_printer)
                except Exception as e:
                    logger.error(f"✗ Erreur impression {label_name} copie {attempt + 1}: {e}")
                    return False
                finally:
                    try:
                        win32print.ClosePrinter(h_printer)
                    except:
                        pass

            return True

        except Exception as e:
            logger.error(f"✗ Erreur lors de l'impression {label_name}: {e}")
            return False

    def list_network_printers(self) -> list:
        """Liste les imprimantes réseau disponibles (Windows seulement)."""
        if not HAS_WIN32PRINT:
            logger.warning("Listage des imprimantes non disponible (Windows seulement)")
            return []

        try:
            printers = []
            # Récupère les imprimantes locales
            flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            for printer in win32print.EnumPrinters(flags):
                printers.append(printer[2])

            logger.info(f"Imprimantes disponibles: {len(printers)}")
            for p in printers:
                logger.info(f"  - {p}")
            return printers

        except Exception as e:
            logger.error(f"Erreur lors de la listage des imprimantes: {e}")
            return []
