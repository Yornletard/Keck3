# Keck3 Project Instructions

## Project Context

Keck3 replaces the legacy Keck1 + KeckCapture system with a modern, embedded Python application. Instead of a client-server architecture with Oracle database, Keck3 communicates directly with Open Prod ERP.

**Key files:**
- Entry point: `run.py`
- Configuration: `config.py`
- Core modules: `core/` (serial I/O, logging, labels + label printing)
- API integration: `api/` (Open Prod client, data models)

## Development Guidelines

### Code style
- Type hints required for functions
- Snake_case for functions/variables
- PascalCase for classes
- Comments only for "why", not "what"
- No logging in functions called frequently (use at module level)

### Module responsibility
- `core/serial_reader.py`: Serial port I/O only
- `core/logger.py`: Logging setup (don't log in other modules)
- `core/labels.py`: Program catalog, SBPL label generation, print decision rule (ported from keck1 PrintService)
- `core/label_printer.py`: Windows label printing via win32print
- `api/client.py`: Open Prod generic API (Odoo-like: `getToken` + `endpoint` with method/model/values), token renewal, retry logic
- `api/publisher.py`: maps a Keck3 control to Open Prod `create` calls using `data/openprod_mapping.json`
- `api/models.py`: D1118 frame protocol parsing (source of truth = legacy keck1 `MachineService`; real frames in `tests/`)
- `core/outbox.py`: persistent local queue (`data/outbox/`), one JSON per control, idempotency key
- `run.py`: Orchestration, two threads (serial reader → outbox; publisher → Open Prod + labels), events for the UI
- `web_ui.py`: Flask dashboard observing `run.py` events (no business logic)

### Adding features
1. New control type? → Add parser to `api/models.py`, endpoint to `run.py`
2. New Open Prod model/field to feed? → Edit `data/openprod_mapping.json` (no code); new API method → `api/client.py`
3. New configuration? → Add to `config.py` with env var + default
4. New error handling? → Log it, don't catch and hide

## Testing

Run `python test_setup.py` before each session to verify:
- Dependencies installed
- Configuration loaded
- Serial ports available
- Unit tests pass (`tests/`: real D1118 frames, SBPL labels) — or `python -m unittest discover tests`
- Programs catalog present (`data/programs.json`)

Never change the frame parsing without checking against keck1 (`~/Sites/keck1/src/AppBundle/Services/MachineService.php`).

## Deployment

### Windows
```bash
start_keck3.cmd  # Auto-creates venv, installs deps, starts app
```

### macOS/Linux
```bash
./start_keck3.sh  # Auto-creates venv, installs deps, starts app
```

### Configuration (required before first run)
1. Copy `.env.example` → `.env`
2. Set `OPEN_PROD_API_KEY` (get from admin)
3. Verify `SERIAL_PORT` matches your machine
4. Test: `python test_setup.py`
5. Run: `python run.py`

## Common Tasks

### Add a new control type
1. Edit `api/models.py`: add parser method
2. Edit `run.py`: add handler method
3. Add corresponding endpoint in `api/client.py`
4. Test with `python test_setup.py`

### Debug serial data
```python
from core.serial_reader import SerialReader
sr = SerialReader()
sr.connect()
while True:
    line = sr.read_line()
    print(f"Raw: {line}")
```

### Debug API calls
```bash
LOG_LEVEL=DEBUG python run.py  # Shows all requests/responses
```

### Check if Open Prod API is reachable
```bash
# Serveur interne (réseau Matfer ou VPN Kerio), certificat non reconnu → -k. Bases : matfer_production, qhse_test (tests).
curl -k -X POST -H "Content-Type: application/json" \
  -d '{"db":"qhse_test","id_secret":"CLE_API_UTILISATEUR"}' \
  https://misrv-opp1.matferbourgeat.com/web/api/getToken
# → {"jsonrpc":"2.0","result":{"data":"<token>"}}  (jeton valable 2 h)
```
L'`id_secret` est la clé API personnelle créée dans Open Prod (avatar > Mes préférences > Sécurité du compte).
Open Prod API doc: `~/Documents/openprod/site/doc_python/addons/web.controllers.html` (section `openprod_api`).

## Known Limitations

- Label printing only works on Windows (requires win32print)
- On Unix, label printing silently logs instead of printing
- Serial port lost at runtime → reconnection attempts every 5 s
- Open Prod down → controls wait in `data/outbox/` (replayed with backoff, survive restarts); refused ones land in `data/outbox/failed/`
- Target Open Prod models/fields (mapping file) still to be validated with Objectif-PI / Matfer Industrie setup

## Migration Notes

See `MIGRATION.md` for step-by-step instructions to switch from Keck1 to Keck3.

Key differences from Keck1:
- No web UI (logs only)
- No database (Open Prod handles storage)
- Simpler debugging (single monolithic app)
- Faster response time (no HTTP round-trip through server)

## File Organization

```
Keck3/
├── run.py              # Entry point
├── config.py           # Config + env vars
├── requirements.txt    # Python deps
├── .env.example        # Config template
├── test_setup.py       # Diagnostic script
├── start_keck3.cmd     # Windows launcher
├── start_keck3.sh      # Unix launcher
│
├── web_ui.py           # Flask dashboard
├── printer_test.py     # Printer discovery / test print
├── programs.example.json
├── openprod_mapping.example.json
│
├── core/
│   ├── logger.py       # Logging setup
│   ├── serial_reader.py # Serial port I/O
│   ├── labels.py       # Programs, SBPL templates, print rule
│   ├── outbox.py       # Persistent local queue
│   └── label_printer.py # Windows label printing
│
├── api/
│   ├── client.py       # Open Prod API client (getToken + endpoint)
│   ├── publisher.py    # Control → Open Prod record mapping
│   └── models.py       # D1118 protocol parsing
│
├── labels/             # SBPL templates (from keck1)
├── tests/              # unittest suite
│
└── docs/
    ├── README.md       # User guide
    ├── ARCHITECTURE.md # Technical design
    ├── MIGRATION.md    # Migration guide
    └── TROUBLESHOOTING.md # Common issues
```

## Performance Considerations

- Threads are independent (no shared state)
- Serial reads block but have timeout (30s default)
- API calls retry with exponential backoff
- Logs rotate at 10MB (keep max 5 files)
- No database → minimal memory footprint

## Security Notes

- API key stored in `.env` (not in code)
- `.env` not committed to git (only `.env.example`)
- HTTPS enforced for Open Prod API
- No credentials logged (even at DEBUG level)
