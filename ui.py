#!/usr/bin/env python
"""
Keck3 - Interface graphique simple
UI desktop avec PySimpleGUI - Installation et utilisation ultra-simples
"""

import PySimpleGUI as sg
import threading
import queue
import time
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path

from core.logger import setup_logger
from core.serial_reader import SerialReader
from core.label_printer import LabelPrinter
from api.client import OpenProdAPIClient
from api.models import DataParser
from config import SERIAL_PORT, OPEN_PROD_BASE_URL, OPEN_PROD_API_KEY

logger = setup_logger(__name__)

# Configuration PySimpleGUI
sg.theme('DarkBlue3')
sg.set_options(font=('Courier', 10))

class Keck3UI:
    """Interface graphique pour Keck3."""

    def __init__(self):
        self.serial_reader = SerialReader(SERIAL_PORT)
        self.api_client = OpenProdAPIClient(OPEN_PROD_BASE_URL, OPEN_PROD_API_KEY)
        self.label_printer = LabelPrinter()

        self.is_running = False
        self.thread_reader = None

        # Queue pour communication thread-safe
        self.queue = queue.Queue()

        # Stats
        self.stats = {
            'electrical_count': 0,
            'heat_count': 0,
            'success_count': 0,
            'error_count': 0,
            'last_update': None,
        }

        # Historique (max 100 entrées)
        self.history = []

        # Logs
        self.logs = []

    def log_ui(self, level: str, message: str):
        """Ajoute un log pour l'UI."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_line = f"[{timestamp}] {level:8} | {message}"
        self.logs.append(log_line)
        self.logs = self.logs[-100:]  # Garder max 100 logs
        self.queue.put(('log', log_line))

    def add_history(self, control_type: str, status: str, details: Dict):
        """Ajoute une entrée à l'historique."""
        entry = {
            'time': datetime.now().strftime("%H:%M:%S"),
            'type': control_type,
            'status': status,
            'details': details,
        }
        self.history.insert(0, entry)
        self.history = self.history[:50]  # Max 50 entrées
        self.queue.put(('history', entry))

    def update_stats(self, stat_name: str, value: Any = None):
        """Met à jour les stats."""
        if value is None:
            self.stats[stat_name] = self.stats.get(stat_name, 0) + 1
        else:
            self.stats[stat_name] = value
        self.stats['last_update'] = datetime.now()
        self.queue.put(('stats', self.stats.copy()))

    def _data_reader_loop(self):
        """Boucle de lecture (thread)."""
        self.log_ui("INFO", "Lecture données démarrée")

        if not self.serial_reader.connect():
            self.log_ui("ERROR", "Impossible de se connecter au port série")
            self.queue.put(('status', 'error'))
            return

        self.log_ui("INFO", f"Connecté au port {SERIAL_PORT}")
        self.queue.put(('status', 'connected'))

        buffer_frame = []

        while self.is_running:
            try:
                line = self.serial_reader.read_line()
                if line is None:
                    time.sleep(0.1)
                    continue

                buffer_frame.append(line)

                if len(buffer_frame) == 2:
                    self._process_frame(tuple(buffer_frame))
                    buffer_frame = []

            except Exception as e:
                self.log_ui("ERROR", f"Erreur lecture: {e}")
                time.sleep(0.5)

        self.serial_reader.disconnect()
        self.log_ui("INFO", "Lecture données arrêtée")
        self.queue.put(('status', 'stopped'))

    def _process_frame(self, frame: tuple):
        """Traite une trame."""
        control_type = DataParser.classify_frame(frame)

        if control_type == 'electrical':
            self._process_electrical(frame)
        elif control_type == 'heat':
            self._process_heat(frame)
        else:
            self.log_ui("WARNING", f"Type non reconnu: {frame}")

    def _process_electrical(self, frame: tuple):
        """Traite contrôle électrique."""
        self.log_ui("INFO", "→ Contrôle électrique")

        electrical_data = DataParser.parse_electrical_control(frame)
        if electrical_data is None:
            self.log_ui("ERROR", "Parse électrique échoué")
            self.update_stats('error_count')
            self.add_history('Électrique', '✗ Parse Error', {})
            return

        # Transmission API
        payload = {
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

        response = self.api_client.post_electrical_control(payload)

        if response:
            self.log_ui("INFO", "✓ Données électriques transmises")
            self.update_stats('electrical_count')
            self.update_stats('success_count')
            self.add_history('Électrique', '✓ OK', {
                'continuity': electrical_data.continuity_test,
                'hv_voltage': electrical_data.hv_voltage_test,
            })
        else:
            self.log_ui("ERROR", "✗ Transmission électrique échouée")
            self.update_stats('error_count')
            self.add_history('Électrique', '✗ Transmission Error', {})

    def _process_heat(self, frame: tuple):
        """Traite contrôle thermique."""
        self.log_ui("INFO", "→ Contrôle thermique")

        heat_data_list = DataParser.parse_heat_control(frame)
        if heat_data_list is None:
            self.log_ui("ERROR", "Parse thermique échoué")
            self.update_stats('error_count')
            self.add_history('Thermique', '✗ Parse Error', {})
            return

        # Transmission API
        payload = {
            'frame': list(frame),
            'datetime': heat_data_list[0].datetime.isoformat(),
            'results': [
                {
                    'wayNumber': data.way_number,
                    'temperature': data.temperature,
                }
                for data in heat_data_list
            ]
        }

        response = self.api_client.post_heat_control(payload)

        if response:
            self.log_ui("INFO", "✓ Données thermiques transmises")
            self.update_stats('heat_count')
            self.update_stats('success_count')
            temps = [f"V{d.way_number}:{d.temperature}°" for d in heat_data_list]
            self.add_history('Thermique', '✓ OK', {'temps': ', '.join(temps[:3])})
        else:
            self.log_ui("ERROR", "✗ Transmission thermique échouée")
            self.update_stats('error_count')
            self.add_history('Thermique', '✗ Transmission Error', {})

    def _build_layout(self):
        """Construit l'interface."""
        header = [
            [
                sg.Text('KECK3 - Banc de Contrôle D1118',
                       font=('Arial', 14, 'bold'),
                       key='title'),
                sg.Push(),
                sg.Button('⚙', size=(3, 1), key='config'),
                sg.Button('❌', size=(3, 1), key='quit'),
            ],
        ]

        status = [
            [
                sg.Text('Port Série:', size=(12, 1)),
                sg.Text('--', size=(20, 1), key='port_status'),
                sg.Text('Open Prod:', size=(12, 1)),
                sg.Text('--', size=(20, 1), key='api_status'),
            ],
        ]

        stats = [
            [
                sg.Frame('Statistiques', layout=[
                    [
                        sg.Text('Contrôles électriques:', size=(20, 1)),
                        sg.Text('0', size=(6, 1), key='electrical_count'),
                        sg.Text('Contrôles thermiques:', size=(20, 1)),
                        sg.Text('0', size=(6, 1), key='heat_count'),
                    ],
                    [
                        sg.Text('Succès:', size=(20, 1)),
                        sg.Text('0', size=(6, 1), key='success_count'),
                        sg.Text('Erreurs:', size=(20, 1)),
                        sg.Text('0', size=(6, 1), key='error_count'),
                    ],
                ], size=(90, 5))
            ],
        ]

        history = [
            [
                sg.Frame('Historique des contrôles (derniers 20)', layout=[
                    [
                        sg.Table(
                            values=[],
                            headings=['Heure', 'Type', 'Statut', 'Détails'],
                            max_col_width=20,
                            size=(88, 10),
                            key='history_table',
                            auto_size_columns=True,
                        ),
                    ],
                ], size=(90, 12))
            ],
        ]

        logs = [
            [
                sg.Frame('Logs en direct', layout=[
                    [
                        sg.Multiline(
                            size=(88, 8),
                            key='logs',
                            disabled=True,
                            autoscroll=True,
                        ),
                    ],
                ], size=(90, 10))
            ],
        ]

        layout = [
            header,
            [sg.HorizontalSeparator()],
            status,
            [sg.HorizontalSeparator()],
            stats,
            [sg.HorizontalSeparator()],
            history,
            [sg.HorizontalSeparator()],
            logs,
        ]

        return layout

    def run(self):
        """Lance l'interface."""
        layout = self._build_layout()
        window = sg.Window('Keck3', layout, finalize=True, size=(920, 800))

        # Démarrer la lecture
        self.is_running = True
        self.thread_reader = threading.Thread(
            target=self._data_reader_loop,
            daemon=True
        )
        self.thread_reader.start()

        # Boucle UI
        while True:
            event, values = window.read(timeout=100)

            # Traiter les messages de la queue
            try:
                while True:
                    msg_type, msg_data = self.queue.get_nowait()

                    if msg_type == 'status':
                        if msg_data == 'connected':
                            window['port_status'].update('✓ Connecté', text_color='green')
                            window['api_status'].update('✓ Connecté', text_color='green')
                        elif msg_data == 'error':
                            window['port_status'].update('✗ Erreur', text_color='red')

                    elif msg_type == 'stats':
                        window['electrical_count'].update(str(msg_data['electrical_count']))
                        window['heat_count'].update(str(msg_data['heat_count']))
                        window['success_count'].update(str(msg_data['success_count']))
                        window['error_count'].update(str(msg_data['error_count']))

                    elif msg_type == 'history':
                        history_data = [
                            [h['time'], h['type'], h['status'], str(h['details'])[:30]]
                            for h in self.history[:20]
                        ]
                        window['history_table'].update(values=history_data)

                    elif msg_type == 'log':
                        current_logs = window['logs'].get()
                        window['logs'].update(current_logs + msg_data + '\n')

            except queue.Empty:
                pass

            # Événements
            if event == sg.WINDOW_CLOSED or event == 'quit':
                break

            elif event == 'config':
                self._show_config_window()

        # Fermer
        self.is_running = False
        window.close()
        self.thread_reader.join(timeout=5)

    def _show_config_window(self):
        """Affiche la fenêtre de configuration."""
        layout = [
            [
                sg.Text('Port Série:', size=(15, 1)),
                sg.Input(SERIAL_PORT, size=(25, 1), key='port'),
                sg.Button('Détecter'),
            ],
            [
                sg.Text('Open Prod URL:', size=(15, 1)),
                sg.Input(OPEN_PROD_BASE_URL, size=(40, 1), key='url'),
            ],
            [
                sg.Text('Clé API:', size=(15, 1)),
                sg.Input(OPEN_PROD_API_KEY, size=(40, 1), key='api_key', password_char='•'),
            ],
            [sg.HorizontalSeparator()],
            [
                sg.Button('Sauvegarder'),
                sg.Button('Annuler'),
            ],
        ]

        window = sg.Window('Configuration Keck3', layout)

        while True:
            event, values = window.read()
            if event == sg.WINDOW_CLOSED or event == 'Annuler':
                break
            elif event == 'Sauvegarder':
                sg.popup_ok('Configuration sauvegardée\n(À implémenter)', title='Info')
                break
            elif event == 'Détecter':
                ports = SerialReader.list_available_ports()
                if ports:
                    sg.popup_ok(f"Ports trouvés:\n" + "\n".join([p[0] for p in ports]))
                else:
                    sg.popup_error("Aucun port trouvé")

        window.close()

def main():
    """Point d'entrée."""
    try:
        app = Keck3UI()
        app.run()
    except Exception as e:
        sg.popup_error(f"Erreur: {e}\n\nConsultez les logs pour plus de détails.")
        logger.error(f"Erreur UI: {e}", exc_info=True)

if __name__ == '__main__':
    main()
