#!/usr/bin/env python
"""
Keck3 - Test Control Data Acquisition System
Acquisition des données du banc de contrôle D1118, transmission à Open Prod
et impression des étiquettes.

Deux threads : le lecteur série (parse et met en file) et le publieur (rejoue la
file vers Open Prod, imprime les étiquettes une fois le contrôle accepté).
"""

import signal
import sys
import threading
import time
from types import FrameType
from typing import Callable, List, Optional, Sequence, Union

from core.logger import setup_logger
from core.serial_reader import SerialReader
from core.label_printer import LabelPrinter
from core.labels import LabelBuilder, MachineRegistry, Program, ProgramCatalog, should_print
from core.outbox import Outbox, OutboxEntry
from api.client import OpenProdAPIClient
from api.publisher import ControlPublisher, PublishResult
from api.models import DataParser, ElectricalControlData, HeatControlData, is_header_line
from config import (
    SERIAL_PORT,
    SERIAL_RECONNECT_DELAY,
    OPEN_PROD_BASE_URL,
    OPEN_PROD_DB,
    OPEN_PROD_API_KEY,
    OPEN_PROD_MAPPING_FILE,
    OUTBOX_DIR,
    OUTBOX_BACKOFF,
    LABELS_DIR,
    PROGRAMS_FILE,
    MACHINES_FILE,
    PRINT_LABELS,
    PRINT_REQUIRES_API_SUCCESS,
    STOP_TIMEOUT,
)

logger = setup_logger(__name__)

Listener = Callable[[str, dict], None]
Control = Union[ElectricalControlData, HeatControlData]
Frame = Sequence[Sequence[str]]


class Keck3Application:
    """Application principale de Keck3.

    Émet des événements (``port``, ``api``, ``frame``, ``queued``, ``transmitted``,
    ``printed``, ``outbox``, ``error``) vers les ``listeners`` : c'est par là que
    l'interface web observe l'activité sans dupliquer la logique métier.
    """

    def __init__(self, serial_reader: Optional[SerialReader] = None,
                 api_client: Optional[OpenProdAPIClient] = None,
                 publisher: Optional[ControlPublisher] = None,
                 label_printer: Optional[LabelPrinter] = None,
                 outbox: Optional[Outbox] = None):
        self.serial_reader = serial_reader or SerialReader(SERIAL_PORT)
        self.api_client = api_client or OpenProdAPIClient(OPEN_PROD_BASE_URL, OPEN_PROD_DB, OPEN_PROD_API_KEY)
        self.publisher = publisher or ControlPublisher(self.api_client, OPEN_PROD_MAPPING_FILE)
        self.label_printer = label_printer or LabelPrinter()
        self.outbox = outbox or Outbox(OUTBOX_DIR)
        self.label_builder = LabelBuilder(LABELS_DIR)
        self.programs = ProgramCatalog(PROGRAMS_FILE)
        self.machines = MachineRegistry(MACHINES_FILE)
        self.listeners: List[Listener] = []
        self.is_running = False
        self.thread_data_reader: Optional[threading.Thread] = None
        self.thread_publisher: Optional[threading.Thread] = None
        self._wake_publisher = threading.Event()

    # ------------------------------------------------------------------ events
    def add_listener(self, listener: Listener) -> None:
        self.listeners.append(listener)

    def _emit(self, event: str, **data) -> None:
        for listener in self.listeners:
            try:
                listener(event, data)
            except Exception as e:  # un observateur cassé ne doit pas arrêter l'acquisition
                logger.error(f"Listener en erreur sur '{event}': {e}")

    def _emit_outbox(self) -> None:
        pending, failed = self.outbox.counts()
        self._emit('outbox', pending=pending, failed=failed)

    # --------------------------------------------------------------- lifecycle
    @property
    def is_reader_alive(self) -> bool:
        return self.thread_data_reader is not None and self.thread_data_reader.is_alive()

    @property
    def is_publisher_alive(self) -> bool:
        return self.thread_publisher is not None and self.thread_publisher.is_alive()

    def start(self) -> bool:
        """Démarre l'application. Refuse si un thread précédent tourne encore (jamais deux lecteurs sur le port)."""
        if self.is_reader_alive or self.is_publisher_alive:
            logger.error("Démarrage refusé : l'instance précédente n'est pas encore arrêtée")
            return False

        logger.info("=" * 60)
        logger.info("Démarrage de Keck3")
        logger.info("=" * 60)

        if not OPEN_PROD_API_KEY or not OPEN_PROD_DB:
            logger.error("OPEN_PROD_DB / OPEN_PROD_API_KEY non configurés. Vérifiez le fichier .env")
            self._emit('error', message="Open Prod non configuré (OPEN_PROD_DB / OPEN_PROD_API_KEY)")
            return False
        if not self.publisher.is_configured:
            logger.warning(f"Aucun mapping Open Prod ({OPEN_PROD_MAPPING_FILE}) : les contrôles resteront en file")
        if len(self.programs) == 0:
            logger.warning(f"Aucun programme dans {PROGRAMS_FILE} : aucune étiquette ne pourra être imprimée")

        api_ok = self.api_client.check_connection()
        self._emit('api', status='connected' if api_ok else 'error', error=self.api_client.last_error)

        pending, failed = self.outbox.counts()
        if pending or failed:
            logger.info(f"File locale: {pending} contrôle(s) en attente, {failed} refusé(s)")
        self._emit_outbox()

        SerialReader.list_available_ports()
        if not self.serial_reader.connect():
            logger.error("Impossible de se connecter au port série")
            self._emit('port', status='error', port=self.serial_reader.port)
            return False
        self._emit('port', status='connected', port=self.serial_reader.port)

        self.is_running = True
        self._wake_publisher.set()
        # Threads non daemon : un contrôle en cours d'envoi ou d'impression n'est pas tué à l'arrêt.
        self.thread_publisher = threading.Thread(target=self._publisher_loop, name="Publisher", daemon=False)
        self.thread_data_reader = threading.Thread(target=self._data_reader_loop, name="DataReader", daemon=False)
        self.thread_publisher.start()
        self.thread_data_reader.start()
        logger.info("Application Keck3 démarrée")
        return True

    def stop(self) -> None:
        """Arrête l'application proprement : termine le traitement en cours avant de rendre la main."""
        if self.is_running:
            logger.info("Arrêt de Keck3...")
        self.is_running = False
        self._wake_publisher.set()
        self.serial_reader.disconnect()  # débloque une lecture en attente
        deadline = time.monotonic() + STOP_TIMEOUT
        for thread in (self.thread_data_reader, self.thread_publisher):
            if thread is not None and thread.is_alive():
                thread.join(timeout=max(0.0, deadline - time.monotonic()))
                if thread.is_alive():
                    logger.warning(f"Le thread {thread.name} n'a pas terminé en {STOP_TIMEOUT}s")
        self.api_client.close()
        logger.info("Keck3 arrêté")

    def wait(self) -> None:
        """Bloque tant que l'acquisition tourne (compatible Windows, sans signal.pause)."""
        while self.is_running and self.is_reader_alive:
            self.thread_data_reader.join(timeout=0.5)

    # ------------------------------------------------------------ acquisition
    def _data_reader_loop(self) -> None:
        """Boucle de lecture : assemble les trames de 2 lignes, se recale sur la ligne date."""
        logger.info("En attente des données du banc de contrôle D1118...")
        buffer_frame: List[Sequence[str]] = []

        while self.is_running:
            if not self.serial_reader.is_connected:
                self._reconnect()
                buffer_frame = []
                continue

            try:
                line = self.serial_reader.read_line()
            except Exception as e:
                logger.error(f"Erreur dans la boucle de lecture: {e}")
                continue

            if line is None:
                continue

            if is_header_line(line):
                if buffer_frame:
                    logger.warning(f"Trame incomplète abandonnée: {buffer_frame}")
                buffer_frame = [line]
                continue

            if not buffer_frame:
                logger.warning(f"Ligne orpheline ignorée (pas de ligne date avant): {line}")
                continue

            buffer_frame.append(line)
            frame = tuple(buffer_frame)
            buffer_frame = []
            try:
                self._process_frame(frame)
            except Exception as e:
                logger.error(f"Erreur de traitement de la trame {frame}: {e}", exc_info=True)
                self._emit('error', message=str(e))

        logger.info("Lecteur de données arrêté")

    def _reconnect(self) -> None:
        if not self.is_running:
            return
        self._emit('port', status='error', port=self.serial_reader.port)
        logger.warning(f"Port série indisponible, nouvel essai dans {SERIAL_RECONNECT_DELAY}s")
        deadline = time.monotonic() + SERIAL_RECONNECT_DELAY
        while self.is_running and time.monotonic() < deadline:
            time.sleep(0.2)
        if self.is_running and self.serial_reader.connect():
            self._emit('port', status='connected', port=self.serial_reader.port)

    # -------------------------------------------------------------- processing
    def _process_frame(self, frame: Frame) -> None:
        logger.debug(f"Trame reçue: {frame}")
        control_type = DataParser.classify_frame(frame)
        self._emit('frame', control_type=control_type, frame=frame)

        if control_type == 'electrical':
            self._process_electrical_control(frame)
        elif control_type == 'heat':
            self._process_heat_control(frame)
        else:
            logger.warning(f"Type de contrôle non reconnu: {frame}")
            self._emit('error', message="Trame non reconnue")

    def _process_electrical_control(self, frame: Frame) -> None:
        electrical = DataParser.parse_electrical_control(frame)
        if electrical is None:
            logger.warning(f"Impossible de parser le contrôle électrique: {frame}")
            self._emit('error', control_type='electrical', message="Parse électrique échoué")
            return

        logger.info(
            f"Contrôle électrique {electrical.serial_number} (OF {electrical.fab_order_number}, "
            f"programme {electrical.program_number}, statut {electrical.status_code})"
        )
        self.machines.remember(electrical.serial_number, electrical.program_number)
        self._enqueue('electrical', electrical, frame)

    def _process_heat_control(self, frame: Frame) -> None:
        ways = DataParser.parse_heat_control(frame)
        if ways is None:
            logger.warning(f"Impossible de parser le contrôle de chauffe: {frame}")
            self._emit('error', control_type='heat', message="Parse chauffe échoué")
            return
        if not ways:
            logger.debug("Trame de chauffe sans voie active")
            return

        logger.info("Contrôle de chauffe: " + ", ".join(
            f"V{w.way_number} {w.serial_number} {w.temperature}° (statut {w.status_code})" for w in ways
        ))
        for way in ways:
            self._enqueue('heat', way, frame)

    def _enqueue(self, kind: str, control: Control, frame: Frame) -> None:
        """Persiste le contrôle avant tout envoi ; réveille le publieur."""
        entry = self.outbox.add(kind, control, frame)
        if entry is None:
            return
        self._emit('queued', control_type=kind, serial_number=control.serial_number, data=control)
        self._emit_outbox()
        self._wake_publisher.set()
        if not PRINT_REQUIRES_API_SUCCESS:
            self._maybe_print(kind, control)

    # ------------------------------------------------------------- publishing
    def _publisher_loop(self) -> None:
        """Rejoue la file vers Open Prod dans l'ordre d'arrivée, avec attente croissante en cas de panne."""
        logger.info("Publieur Open Prod démarré")
        failures = 0
        while self.is_running:
            self._wake_publisher.wait(timeout=OUTBOX_BACKOFF[min(failures, len(OUTBOX_BACKOFF) - 1)] if failures else None)
            self._wake_publisher.clear()
            if not self.is_running:
                break
            for entry in self.outbox.pending():
                if not self.is_running:
                    break
                result = self._publish_entry(entry)
                if result.ok or not result.transient:
                    failures = 0
                    continue
                failures += 1
                delay = OUTBOX_BACKOFF[min(failures - 1, len(OUTBOX_BACKOFF) - 1)]
                logger.warning(f"Open Prod indisponible ({result.error}), nouvel essai dans {delay}s")
                break  # on garde l'ordre : les suivants attendent
            else:
                failures = 0
        logger.info("Publieur Open Prod arrêté")

    def _publish_entry(self, entry: OutboxEntry) -> PublishResult:
        control = entry.to_control()
        result = self.publisher.publish(entry.kind, control, entry.frame)
        self._emit('transmitted', control_type=entry.kind, ok=result.ok, serial_number=entry.serial_number,
                   data=control, error=result.error, duplicate=result.duplicate, warning=result.warning)
        if result.ok:
            self.outbox.mark_done(entry)
            if PRINT_REQUIRES_API_SUCCESS:
                self._maybe_print(entry.kind, control)
        elif result.transient:
            self.outbox.mark_retry(entry, result.error)
        else:
            logger.error(f"Contrôle {entry.kind} {entry.serial_number} refusé par Open Prod, classé sans suite: {result.error}")
            self.outbox.mark_failed(entry, result.error)
        self._emit_outbox()
        return result

    # ---------------------------------------------------------------- printing
    def _maybe_print(self, control_type: str, control: Control) -> None:
        """Applique la règle keck1 : étiquettes si contrôle OK à l'étape finale du programme."""
        if not PRINT_LABELS:
            return

        if isinstance(control, ElectricalControlData):
            program_number: Optional[int] = control.program_number
        else:
            program_number = self.machines.program_number_for(control.serial_number)
        program = self.programs.get(program_number)

        if control.is_ok and program is None:
            logger.warning(
                f"Programme {program_number} inconnu pour {control.serial_number}: "
                f"impossible d'imprimer l'étiquette (compléter {PROGRAMS_FILE})"
            )
            self._emit('error', message=f"Programme {program_number} inconnu, pas d'étiquette")
            return

        if not should_print(control_type, control.is_ok, program):
            return

        self._print_labels(control.serial_number, program)

    def _print_labels(self, serial_number: str, program: Program) -> None:
        barcode = self.label_builder.barcode_label(serial_number, program)
        serial_label = self.label_builder.serial_number_label(serial_number, program)
        ok_barcode = self.label_printer.print_barcode(barcode)
        ok_serial = self.label_printer.print_serial_number(serial_label)
        if ok_barcode and ok_serial:
            logger.info(f"Étiquettes imprimées pour {serial_number} ({program.name})")
        else:
            logger.warning(f"Impression incomplète pour {serial_number} (code-barres: {ok_barcode}, série: {ok_serial})")
        self._emit('printed', serial_number=serial_number, ok=ok_barcode and ok_serial)


def main() -> int:
    try:
        app = Keck3Application()
    except Exception as e:
        logger.error(f"Initialisation impossible: {e}", exc_info=True)
        return 1

    def signal_handler(signum: int, frame: Optional[FrameType]) -> None:
        logger.info(f"Signal reçu ({signum})")
        app.is_running = False  # les boucles s'arrêtent après le traitement en cours

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        if not app.start():
            logger.error("Démarrage échoué")
            return 1
        app.wait()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Erreur fatale: {e}", exc_info=True)
        return 1
    finally:
        app.stop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
