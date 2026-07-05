import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

BASE_DIR = Path(__file__).parent

# Open Prod API Configuration
OPEN_PROD_BASE_URL = os.getenv('OPEN_PROD_BASE_URL', 'https://open-prod.matferbourgeat.com')
OPEN_PROD_API_KEY = os.getenv('OPEN_PROD_API_KEY', '')

# Serial Port Configuration
SERIAL_PORT = os.getenv('SERIAL_PORT', 'COM3')
SERIAL_BAUDRATE = int(os.getenv('SERIAL_BAUDRATE', 9600))
SERIAL_PARITY = 'N'
SERIAL_TIMEOUT = 30

# Label Printing Configuration (Noms des imprimantes réseau connectées)
# Windows: obtenir avec: python -c "from core.label_printer import LabelPrinter; LabelPrinter().list_network_printers()"
LABEL_PRINTER_BARCODE = os.getenv('LABEL_PRINTER_BARCODE', r'\\misrv-imp\MI-IMPCB-M1-01')
LABEL_PRINTER_SERIAL = os.getenv('LABEL_PRINTER_SERIAL', r'\\misrv-imp\MI-IMPCB-M1-02')

# Logging Configuration
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = os.getenv('LOG_FILE', str(BASE_DIR / 'logs' / 'keck3.log'))
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# Data Storage
DATA_DIR = BASE_DIR / 'data'
DATA_DIR.mkdir(exist_ok=True)

LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

# API Endpoints
API_ENDPOINTS = {
    'electrical_control': '/api/machinedata/electricalcontrol',
    'heat_control': '/api/machinedata/heatcontrol',
}

# Retry Configuration
MAX_RETRIES = 3
RETRY_DELAY = 2

# Machine Control Data Thresholds
ELECTRICAL_CONTROL_DATA_LENGTH = 13
