import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

BASE_DIR = Path(__file__).parent


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ('1', 'true', 'yes', 'on')


def _env_path(name: str, default: str) -> Path:
    """Chemin de .env résolu depuis le projet, pas depuis le répertoire courant (raccourci Windows, planificateur…)."""
    return BASE_DIR / os.getenv(name, default)


# Open Prod API Configuration (API générique Odoo-like : getToken puis endpoint, voir api/client.py)
OPEN_PROD_BASE_URL = os.getenv('OPEN_PROD_BASE_URL', 'https://open-prod.matferbourgeat.com')
OPEN_PROD_DB = os.getenv('OPEN_PROD_DB', '')
OPEN_PROD_API_KEY = os.getenv('OPEN_PROD_API_KEY', '')  # clé API utilisateur (Mes préférences > Sécurité du compte)
# Le serveur interne misrv-opp1 présente un certificat non reconnu : false pour ne pas le vérifier.
OPEN_PROD_VERIFY_TLS = _env_bool('OPEN_PROD_VERIFY_TLS', True)
OPEN_PROD_TOKEN_PATH = '/web/api/getToken'
OPEN_PROD_ENDPOINT_PATH = '/web/api/endpoint'

# Serial Port Configuration ('auto' = adaptateur série reconnu par SERIAL_PORT_MATCH, sinon l'unique port présent)
SERIAL_PORT = os.getenv('SERIAL_PORT', 'auto')
SERIAL_PORT_MATCH = os.getenv('SERIAL_PORT_MATCH', r'USB|FTDI|Prolific|CH340|CP210|UART')
SERIAL_BAUDRATE = int(os.getenv('SERIAL_BAUDRATE', 9600))
SERIAL_PARITY = 'N'
SERIAL_TIMEOUT = 30
SERIAL_RECONNECT_DELAY = 5

# Label Printing Configuration (Noms des imprimantes réseau connectées)
# Windows: obtenir avec: python printer_test.py
LABEL_PRINTER_BARCODE = os.getenv('LABEL_PRINTER_BARCODE', r'\\misrv-imp\MI-IMPCB-M1-01')
LABEL_PRINTER_SERIAL = os.getenv('LABEL_PRINTER_SERIAL', r'\\misrv-imp\MI-IMPCB-M1-02')
PRINT_LABELS = _env_bool('PRINT_LABELS', True)
# Comportement historique keck1 : pas d'étiquette si l'enregistrement a échoué.
PRINT_REQUIRES_API_SUCCESS = _env_bool('PRINT_REQUIRES_API_SUCCESS', True)
LABELS_DIR = BASE_DIR / 'labels'

# Logging Configuration
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = str(_env_path('LOG_FILE', 'logs/keck3.log'))
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# Data Storage
DATA_DIR = BASE_DIR / 'data'
DATA_DIR.mkdir(exist_ok=True)

LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

# Référentiels locaux (voir programs.example.json)
PROGRAMS_FILE = _env_path('PROGRAMS_FILE', 'data/programs.json')
MACHINES_FILE = DATA_DIR / 'machines.json'

# Mapping contrôle Keck3 → modèle/champs Open Prod (voir openprod_mapping.example.json)
OPEN_PROD_MAPPING_FILE = _env_path('OPEN_PROD_MAPPING_FILE', 'data/openprod_mapping.json')

# File locale persistée des contrôles à transmettre (rejouée avec attente croissante, en secondes)
OUTBOX_DIR = DATA_DIR / 'outbox'
OUTBOX_BACKOFF = (5, 15, 60, 300)

# Retry Configuration
MAX_RETRIES = 3
RETRY_DELAY = 2
REQUEST_TIMEOUT = 10
# Arrêt : délai laissé au lecteur pour finir l'envoi/impression en cours (> retries API cumulés)
STOP_TIMEOUT = 60

# Web UI
WEB_UI_HOST = os.getenv('WEB_UI_HOST', '127.0.0.1')
WEB_UI_PORT = int(os.getenv('WEB_UI_PORT', 5000))
