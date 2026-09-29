#!/usr/bin/env python
"""
Keck3 - Interface Web
Tableau de bord Flask branché sur Keck3Application (run.py) : aucune logique
métier ici, seulement l'observation des événements et leur affichage.
"""

import threading
from datetime import datetime
from flask import Flask, render_template_string, jsonify

from core.logger import setup_logger
from run import Keck3Application
from api.models import ElectricalControlData, HeatControlData
from update_manager import UpdateManager
from config import WEB_UI_HOST, WEB_UI_PORT

logger = setup_logger(__name__)

app = Flask(__name__)
app.json.sort_keys = False

MAX_LOGS = 100
MAX_HISTORY = 50

state_lock = threading.Lock()
state = {
    'status': 'stopped',
    'stats': {
        'electrical_count': 0,
        'heat_count': 0,
        'success_count': 0,
        'error_count': 0,
        'printed_count': 0,
        'pending_count': 0,
        'failed_count': 0,
    },
    'history': [],
    'logs': [],
    'port_status': 'disconnected',
    'port': None,
    'api_status': 'disconnected',
    'update_available': False,
}


def log_ui(level: str, message: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {level:8} | {message}"
    with state_lock:
        state['logs'].insert(0, line)
        del state['logs'][MAX_LOGS:]


def add_history(control_type: str, status: str, details: str) -> None:
    entry = {'time': datetime.now().strftime('%H:%M:%S'), 'type': control_type, 'status': status, 'details': details}
    with state_lock:
        state['history'].insert(0, entry)
        del state['history'][MAX_HISTORY:]


def _describe(control_type: str, data: object) -> str:
    if control_type == 'electrical' and isinstance(data, ElectricalControlData):
        return (f"{data.serial_number} · prog {data.program_number} · statut {data.status_code} · "
                f"{data.power_voltage_test} V / {data.power_intensity_test} A")
    if control_type == 'heat' and isinstance(data, HeatControlData):
        return f"V{data.way_number} {data.serial_number} {data.temperature}° · statut {data.status_code}"
    return ''


def on_event(event: str, data: dict) -> None:
    """Observateur des événements de Keck3Application."""
    if event == 'port':
        with state_lock:
            state['port_status'] = data.get('status', 'disconnected')
            state['port'] = data.get('port')
        log_ui('INFO' if data.get('status') == 'connected' else 'ERROR',
               f"Port série {data.get('port') or '?'}: {data.get('status')}")

    elif event == 'api':
        with state_lock:
            state['api_status'] = data.get('status', 'disconnected')
        log_ui('INFO' if data.get('status') == 'connected' else 'ERROR',
               f"Open Prod: {data.get('status')}{' - ' + data['error'] if data.get('error') else ''}")

    elif event == 'queued':
        log_ui('INFO', f"⏳ {data.get('control_type')} {data.get('serial_number')} mis en file")

    elif event == 'outbox':
        with state_lock:
            state['stats']['pending_count'] = data.get('pending', 0)
            state['stats']['failed_count'] = data.get('failed', 0)

    elif event == 'frame':
        log_ui('INFO', f"→ Trame {data.get('control_type') or 'inconnue'}")

    elif event == 'transmitted':
        kind = 'Électrique' if data['control_type'] == 'electrical' else 'Thermique'
        key = 'electrical_count' if data['control_type'] == 'electrical' else 'heat_count'
        details = _describe(data['control_type'], data.get('data'))
        with state_lock:
            state['stats'][key] += 1
            if data['ok']:
                state['stats']['success_count'] += 1
                state['api_status'] = 'connected'
            else:
                state['stats']['error_count'] += 1
                state['api_status'] = 'error'
        if data['ok']:
            status = '✓ Déjà présent' if data.get('duplicate') else '✓ OK'
            if data.get('warning'):
                status = '⚠ OK sans lien OF'
                log_ui('WARNING', f"{status} {kind} : {details} — {data['warning']}")
            else:
                log_ui('INFO', f"{status} {kind} : {details}")
            add_history(kind, status, details)
        else:
            log_ui('ERROR', f"✗ {kind} non transmis : {data.get('error') or 'erreur inconnue'}")
            add_history(kind, '✗ Transmission Error', details)

    elif event == 'printed':
        with state_lock:
            if data.get('ok'):
                state['stats']['printed_count'] += 1
        log_ui('INFO' if data.get('ok') else 'WARNING',
               f"{'✓' if data.get('ok') else '✗'} Étiquettes {data.get('serial_number')}")

    elif event == 'error':
        with state_lock:
            state['stats']['error_count'] += 1
        log_ui('ERROR', data.get('message', 'Erreur'))


keck3 = Keck3Application()
keck3.add_listener(on_event)

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
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
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
                <div class="stat-box">
                    <div class="stat-label">En attente d'envoi</div>
                    <div class="stat-value" id="stat-pending">0</div>
                </div>
                <div class="stat-box">
                    <div class="stat-label">Refusés (data/outbox/failed)</div>
                    <div class="stat-value error" id="stat-failed">0</div>
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
            <p>Keck3 | Rafraîchissement toutes les 500 ms</p>
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
                    document.getElementById('stat-pending').textContent = data.stats.pending_count;
                    document.getElementById('stat-failed').textContent = data.stats.failed_count;

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
                    <td style="opacity: 0.8; font-size: 11px;">${h.details}</td>
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
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/status')
def api_status():
    with state_lock:
        return jsonify({
            'status': state['status'],
            'stats': dict(state['stats']),
            'history': list(state['history']),
            'logs': list(state['logs']),
            'port_status': state['port_status'],
            'port': state['port'],
            'api_status': state['api_status'],
        })


@app.route('/api/start', methods=['POST'])
def api_start():
    if state['status'] == 'running' or keck3.is_reader_alive:
        return jsonify({'error': 'Already running (or previous reader still stopping)'}), 400
    if not keck3.start():
        state['status'] = 'error'
        return jsonify({'error': 'Démarrage échoué (voir logs)'}), 500
    state['status'] = 'running'
    return jsonify({'status': 'started'})


@app.route('/api/stop', methods=['POST'])
def api_stop():
    keck3.stop()
    state['status'] = 'stopped'
    return jsonify({'status': 'stopped'})


@app.route('/api/version')
def api_version():
    return jsonify(UpdateManager().get_version_info())


@app.route('/api/check-update', methods=['POST'])
def api_check_update():
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
    manager = UpdateManager()
    success = manager.apply_update()
    return jsonify({
        'success': success,
        'message': 'Mises à jour appliquées, redémarrez Keck3' if success else 'Erreur lors de la mise à jour',
        'current': manager.get_current_version(),
    })


def main() -> None:
    print()
    print("=" * 60)
    print("KECK3 - Web UI")
    print("=" * 60)
    print(f"\n🌐 Ouvrez votre navigateur : http://{WEB_UI_HOST}:{WEB_UI_PORT}\n")
    print("Appuyez sur Ctrl+C pour arrêter\n")

    try:
        state['status'] = 'running' if keck3.start() else 'error'
        app.run(host=WEB_UI_HOST, port=WEB_UI_PORT, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        print("\n\nArrêt...")
    except Exception as e:
        logger.error(f"Erreur: {e}", exc_info=True)
    finally:
        keck3.stop()


if __name__ == '__main__':
    main()
