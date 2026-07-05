#!/usr/bin/env python
"""
Keck3 - Interface Web Ultra-Simple
Une seule fenêtre du navigateur, pas de build, pas de Node.js
"""

from flask import Flask, render_template_string, jsonify
import threading
import queue
import time
from datetime import datetime
from typing import Optional, Dict, Any

from core.logger import setup_logger
from core.serial_reader import SerialReader
from api.client import OpenProdAPIClient
from api.models import DataParser
from config import SERIAL_PORT, OPEN_PROD_BASE_URL, OPEN_PROD_API_KEY
from update_manager import UpdateManager

logger = setup_logger(__name__)

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

# State globale
state = {
    'status': 'stopped',
    'stats': {
        'electrical_count': 0,
        'heat_count': 0,
        'success_count': 0,
        'error_count': 0,
    },
    'history': [],
    'logs': [],
    'port_status': 'disconnected',
    'api_status': 'disconnected',
    'version': None,
    'update_available': False,
}

class Keck3WebUI:
    """Logic pour Keck3 Web UI."""

    def __init__(self):
        self.serial_reader = SerialReader(SERIAL_PORT)
        self.api_client = OpenProdAPIClient(OPEN_PROD_BASE_URL, OPEN_PROD_API_KEY)
        self.is_running = False
        self.thread_reader = None

    def log_ui(self, level: str, message: str):
        """Ajoute un log."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_line = f"[{timestamp}] {level:8} | {message}"
        state['logs'].insert(0, log_line)
        state['logs'] = state['logs'][:100]

    def add_history(self, control_type: str, status: str, details: Dict):
        """Ajoute à l'historique."""
        entry = {
            'time': datetime.now().strftime("%H:%M:%S"),
            'type': control_type,
            'status': status,
            'details': details,
        }
        state['history'].insert(0, entry)
        state['history'] = state['history'][:50]

    def _data_reader_loop(self):
        """Boucle de lecture (thread)."""
        self.log_ui("INFO", "Lecture données démarrée")

        if not self.serial_reader.connect():
            self.log_ui("ERROR", "Impossible de se connecter au port série")
            state['port_status'] = 'error'
            return

        self.log_ui("INFO", f"Connecté au port {SERIAL_PORT}")
        state['port_status'] = 'connected'
        state['api_status'] = 'connected'

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

    def _process_frame(self, frame: tuple):
        """Traite une trame."""
        control_type = DataParser.classify_frame(frame)

        if control_type == 'electrical':
            self._process_electrical(frame)
        elif control_type == 'heat':
            self._process_heat(frame)

    def _process_electrical(self, frame: tuple):
        """Traite contrôle électrique."""
        self.log_ui("INFO", "→ Contrôle électrique")

        electrical_data = DataParser.parse_electrical_control(frame)
        if electrical_data is None:
            self.log_ui("ERROR", "Parse électrique échoué")
            state['stats']['error_count'] += 1
            self.add_history('Électrique', '✗ Parse Error', {})
            return

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
            state['stats']['electrical_count'] += 1
            state['stats']['success_count'] += 1
            self.add_history('Électrique', '✓ OK', {
                'continuity': electrical_data.continuity_test,
                'hv_voltage': electrical_data.hv_voltage_test,
            })
        else:
            self.log_ui("ERROR", "✗ Transmission électrique échouée")
            state['stats']['error_count'] += 1
            self.add_history('Électrique', '✗ Transmission Error', {})

    def _process_heat(self, frame: tuple):
        """Traite contrôle thermique."""
        self.log_ui("INFO", "→ Contrôle thermique")

        heat_data_list = DataParser.parse_heat_control(frame)
        if heat_data_list is None:
            self.log_ui("ERROR", "Parse thermique échoué")
            state['stats']['error_count'] += 1
            self.add_history('Thermique', '✗ Parse Error', {})
            return

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
            state['stats']['heat_count'] += 1
            state['stats']['success_count'] += 1
            temps = [f"V{d.way_number}:{d.temperature}°" for d in heat_data_list]
            self.add_history('Thermique', '✓ OK', {'temps': ', '.join(temps[:3])})
        else:
            self.log_ui("ERROR", "✗ Transmission thermique échouée")
            state['stats']['error_count'] += 1
            self.add_history('Thermique', '✗ Transmission Error', {})

    def start(self):
        """Démarre la lecture."""
        self.is_running = True
        self.thread_reader = threading.Thread(target=self._data_reader_loop, daemon=True)
        self.thread_reader.start()

    def stop(self):
        """Arrête la lecture."""
        self.is_running = False
        if self.thread_reader:
            self.thread_reader.join(timeout=5)

# Instance globale
keck3_ui = Keck3WebUI()

# ============================================================================
# ROUTES FLASK
# ============================================================================

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Keck3 - Banc de Contrôle D1118</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: #f0f0f0;
            padding: 20px;
            min-height: 100vh;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
        }

        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            background: rgba(0, 0, 0, 0.3);
            padding: 20px;
            border-radius: 8px;
        }

        h1 {
            font-size: 28px;
            font-weight: 700;
        }

        .header-info {
            display: flex;
            gap: 30px;
            font-size: 14px;
        }

        .status-item {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .status-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: #ff6b6b;
        }

        .status-dot.ok {
            background: #51cf66;
        }

        .status-dot.connecting {
            background: #ffd43b;
            animation: pulse 1s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        .card {
            background: rgba(0, 0, 0, 0.2);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
        }

        .card-title {
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.2);
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 15px;
        }

        .stat-box {
            background: rgba(0, 0, 0, 0.3);
            padding: 15px;
            border-radius: 6px;
            text-align: center;
        }

        .stat-label {
            font-size: 12px;
            opacity: 0.8;
            margin-bottom: 8px;
        }

        .stat-value {
            font-size: 28px;
            font-weight: 700;
            color: #51cf66;
        }

        .stat-value.error {
            color: #ff6b6b;
        }

        .history-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }

        .history-table th {
            background: rgba(0, 0, 0, 0.3);
            padding: 12px;
            text-align: left;
            font-weight: 600;
            border-bottom: 1px solid rgba(255, 255, 255, 0.2);
        }

        .history-table td {
            padding: 12px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }

        .status-ok {
            color: #51cf66;
        }

        .status-error {
            color: #ff6b6b;
        }

        .logs-container {
            background: rgba(0, 0, 0, 0.4);
            padding: 15px;
            border-radius: 6px;
            font-family: 'Courier New', monospace;
            font-size: 12px;
            max-height: 300px;
            overflow-y: auto;
            line-height: 1.6;
        }

        .log-line {
            margin-bottom: 4px;
            opacity: 0.9;
        }

        .log-info {
            color: #74c0fc;
        }

        .log-error {
            color: #ff6b6b;
        }

        .log-success {
            color: #51cf66;
        }

        .log-warning {
            color: #ffd43b;
        }

        button {
            background: #4c6ef5;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            margin-top: 15px;
            transition: background 0.2s;
        }

        button:hover {
            background: #364dd0;
        }

        button:disabled {
            background: #868e96;
            cursor: not-allowed;
        }

        .footer {
            text-align: center;
            margin-top: 30px;
            opacity: 0.7;
            font-size: 12px;
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- HEADER -->
        <div class="header">
            <div>
                <h1>KECK3 - Banc de Contrôle D1118</h1>
                <div style="font-size: 12px; opacity: 0.7; margin-top: 5px;">
                    Version: <span id="version-current">--</span> |
                    <a href="#" id="check-update-link" style="color: #4c6ef5; text-decoration: none;">Vérifier les mises à jour</a>
                </div>
            </div>
            <div class="header-info">
                <div class="status-item">
                    <span class="status-dot ok" id="port-dot"></span>
                    <span id="port-text">Port: --</span>
                </div>
                <div class="status-item">
                    <span class="status-dot ok" id="api-dot"></span>
                    <span id="api-text">Open Prod: --</span>
                </div>
                <div class="status-item">
                    <button id="update-btn" style="display: none; margin: 0;">
                        ⬆ Mise à jour disponible
                    </button>
                </div>
            </div>
        </div>

        <!-- STATISTIQUES -->
        <div class="card">
            <div class="card-title">📊 Statistiques</div>
            <div class="stats-grid">
                <div class="stat-box">
                    <div class="stat-label">Contrôles Électriques</div>
                    <div class="stat-value" id="stat-electrical">0</div>
                </div>
                <div class="stat-box">
                    <div class="stat-label">Contrôles Thermiques</div>
                    <div class="stat-value" id="stat-heat">0</div>
                </div>
                <div class="stat-box">
                    <div class="stat-label">Succès</div>
                    <div class="stat-value" id="stat-success">0</div>
                </div>
                <div class="stat-box">
                    <div class="stat-label">Erreurs</div>
                    <div class="stat-value error" id="stat-error">0</div>
                </div>
            </div>
        </div>

        <!-- HISTORIQUE -->
        <div class="card">
            <div class="card-title">📋 Historique des contrôles (20 derniers)</div>
            <table class="history-table">
                <thead>
                    <tr>
                        <th>Heure</th>
                        <th>Type</th>
                        <th>Statut</th>
                        <th>Détails</th>
                    </tr>
                </thead>
                <tbody id="history-body">
                    <tr>
                        <td colspan="4" style="text-align: center; opacity: 0.5;">En attente...</td>
                    </tr>
                </tbody>
            </table>
        </div>

        <!-- LOGS -->
        <div class="card">
            <div class="card-title">📝 Logs en direct</div>
            <div class="logs-container" id="logs-container">
                <div class="log-line log-info">[En attente...]</div>
            </div>
        </div>

        <!-- FOOTER -->
        <div class="footer">
            <p>Keck3 v1.0 | Mise à jour automatique toutes les 500ms</p>
        </div>
    </div>

    <script>
        // Auto-refresh tous les 500ms
        setInterval(updateUI, 500);

        // Vérifier les updates au démarrage
        checkVersion();
        setInterval(checkVersion, 300000); // Chaque 5 minutes

        function updateUI() {
            fetch('/api/status')
                .then(r => r.json())
                .then(data => {
                    // Stats
                    document.getElementById('stat-electrical').textContent = data.stats.electrical_count;
                    document.getElementById('stat-heat').textContent = data.stats.heat_count;
                    document.getElementById('stat-success').textContent = data.stats.success_count;
                    document.getElementById('stat-error').textContent = data.stats.error_count;

                    // Status dots
                    updateDot('port-dot', 'port-text', data.port_status);
                    updateDot('api-dot', 'api-text', data.api_status);

                    // Historique
                    updateHistory(data.history);

                    // Logs
                    updateLogs(data.logs);
                });
        }

        function checkVersion() {
            fetch('/api/version')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('version-current').textContent = data.current || '--';

                    fetch('/api/check-update', { method: 'POST' })
                        .then(r => r.json())
                        .then(update_data => {
                            if (update_data.has_updates) {
                                document.getElementById('update-btn').style.display = 'inline';
                            }
                        });
                });
        }

        // Gestionnaire pour le lien de vérification
        document.getElementById('check-update-link').addEventListener('click', function(e) {
            e.preventDefault();
            checkVersion();
            alert('Vérification des mises à jour...');
        });

        // Gestionnaire pour le bouton de mise à jour
        document.getElementById('update-btn').addEventListener('click', function() {
            if (confirm('Appliquer les mises à jour maintenant ? (L\'app sera redémarrée)')) {
                this.disabled = true;
                this.textContent = '⟳ Mise à jour en cours...';

                fetch('/api/apply-update', { method: 'POST' })
                    .then(r => r.json())
                    .then(data => {
                        if (data.success) {
                            alert('Mises à jour appliquées ! Redémarrage...');
                            setTimeout(() => location.reload(), 3000);
                        } else {
                            alert('Erreur: ' + data.message);
                            this.disabled = false;
                            this.textContent = '⬆ Mise à jour disponible';
                        }
                    });
            }
        });

        function updateDot(dotId, textId, status) {
            const dot = document.getElementById(dotId);
            const text = document.getElementById(textId);

            if (status === 'connected') {
                dot.className = 'status-dot ok';
                text.textContent = dotId.includes('port') ? '✓ Port série: Connecté' : '✓ Open Prod: Connecté';
            } else if (status === 'disconnected') {
                dot.className = 'status-dot';
                text.textContent = dotId.includes('port') ? '○ Port série: --' : '○ Open Prod: --';
            } else if (status === 'error') {
                dot.className = 'status-dot';
                text.textContent = dotId.includes('port') ? '✗ Port série: Erreur' : '✗ Open Prod: Erreur';
            }
        }

        function updateHistory(history) {
            const tbody = document.getElementById('history-body');

            if (!history || history.length === 0) {
                tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; opacity: 0.5;">En attente...</td></tr>';
                return;
            }

            tbody.innerHTML = history.slice(0, 20).map(h => `
                <tr>
                    <td>${h.time}</td>
                    <td>${h.type}</td>
                    <td class="${h.status.includes('OK') ? 'status-ok' : 'status-error'}">${h.status}</td>
                    <td style="opacity: 0.8; font-size: 11px;">${JSON.stringify(h.details).substring(0, 30)}</td>
                </tr>
            `).join('');
        }

        function updateLogs(logs) {
            const container = document.getElementById('logs-container');

            if (!logs || logs.length === 0) {
                container.innerHTML = '<div class="log-line log-info">[En attente...]</div>';
                return;
            }

            container.innerHTML = logs.slice(0, 50).map(log => {
                let cls = 'log-info';
                if (log.includes('ERROR')) cls = 'log-error';
                else if (log.includes('✓')) cls = 'log-success';
                else if (log.includes('WARNING')) cls = 'log-warning';

                return `<div class="log-line ${cls}">${log}</div>`;
            }).join('');

            // Auto-scroll
            container.scrollTop = 0;
        }

        // Première mise à jour
        updateUI();
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    """Page principale."""
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/status')
def api_status():
    """API endpoint pour le statut."""
    return jsonify({
        'status': state['status'],
        'stats': state['stats'],
        'history': state['history'],
        'logs': state['logs'],
        'port_status': state['port_status'],
        'api_status': state['api_status'],
    })

@app.route('/api/start', methods=['POST'])
def api_start():
    """Démarre l'acquisition."""
    if state['status'] == 'running':
        return jsonify({'error': 'Already running'}), 400

    state['status'] = 'running'
    keck3_ui.start()
    return jsonify({'status': 'started'})

@app.route('/api/stop', methods=['POST'])
def api_stop():
    """Arrête l'acquisition."""
    state['status'] = 'stopped'
    keck3_ui.stop()
    return jsonify({'status': 'stopped'})

@app.route('/api/version')
def api_version():
    """Récupère les infos de version."""
    manager = UpdateManager()
    return jsonify(manager.get_version_info())

@app.route('/api/check-update', methods=['POST'])
def api_check_update():
    """Vérifie les mises à jour disponibles."""
    manager = UpdateManager()
    has_updates = manager.check_updates()
    state['update_available'] = has_updates
    return jsonify({
        'has_updates': has_updates,
        'current': manager.get_current_version(),
        'latest': manager.get_latest_version(),
    })

@app.route('/api/apply-update', methods=['POST'])
def api_apply_update():
    """Applique les mises à jour."""
    manager = UpdateManager()
    success = manager.apply_update()
    return jsonify({
        'success': success,
        'message': 'Mises à jour appliquées' if success else 'Erreur lors de la mise à jour',
        'current': manager.get_current_version(),
    })

def main():
    """Point d'entrée."""
    print()
    print("=" * 60)
    print("KECK3 - Web UI")
    print("=" * 60)
    print()
    print("🌐 Ouvrez votre navigateur : http://localhost:5000")
    print()
    print("Appuyez sur Ctrl+C pour arrêter")
    print()

    try:
        # Démarrer la lecture au lancement
        keck3_ui.start()
        state['status'] = 'running'

        # Lancer Flask
        app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        print("\n\nArrêt...")
        keck3_ui.stop()
    except Exception as e:
        print(f"Erreur: {e}")
        logger.error(f"Erreur: {e}", exc_info=True)

if __name__ == '__main__':
    main()
