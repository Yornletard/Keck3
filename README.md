# Keck3 - Test Control Data Acquisition System

Keck3 est l'application Python de nouvelle génération pour l'acquisition et la transmission des données du banc de contrôle (D1118) directement vers Open Prod (ERP).

## 🚀 Démarrage ultra-rapide

### Windows
```bash
Double-clic sur start_ui.cmd
# Automatique : crée l'env, installe dépendances, lance l'app
```

### Mac/Linux
```bash
./start_ui.sh
# Automatique : crée l'env, installe dépendances, lance l'app
```

**C'est tout.** Une fenêtre s'ouvre, vous êtes prêt.

## 📊 Interface graphique

Interface native desktop ultra-simple :
- ✓ Statut en temps réel (port série, Open Prod)
- ✓ Statistiques (électrique, thermique, erreurs)
- ✓ Historique des 20 derniers contrôles
- ✓ Logs en direct
- ✓ Configuration facile (bouton ⚙)

→ Voir [UI_SIMPLE.md](UI_SIMPLE.md) pour les détails

## Architecture

**Avant (Keck1 + KeckCapture):**
- KeckCapture (Python) → API HTTP → Keck1 (Serveur Symfony) → Base de données Oracle

**Maintenant (Keck3):**
- Keck3 (Python embarqué) → API Open Prod → Stockage intégré dans Open Prod

## Fonctionnalités

- Lecture temps réel depuis le banc de contrôle (port série D1118)
- Transmission des données de contrôle électrique et thermique
- Impression **immédiate** vers imprimantes réseau
- Intégration native avec Open Prod
- Interface graphique native (PySimpleGUI)
- Logging complet et traçabilité
- Gestion robuste des erreurs et reconnexions

## Installation

```bash
cd /Users/yornletard/Sites/Keck3
python -m venv venv
source venv/bin/activate  # macOS/Linux
# ou
venv\Scripts\activate  # Windows

pip install -r requirements.txt
```

## Configuration

Créer un fichier `.env` à la racine du projet :

```env
# Open Prod API
OPEN_PROD_BASE_URL=https://open-prod.matferbourgeat.com
OPEN_PROD_API_KEY=your_api_key_here

# Serial Port
SERIAL_PORT=COM3
SERIAL_BAUDRATE=9600

# Label Printing (noms d'imprimantes réseau - Windows)
LABEL_PRINTER_BARCODE=\\misrv-imp\MI-IMPCB-M1-01
LABEL_PRINTER_SERIAL=\\misrv-imp\MI-IMPCB-M1-02

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/keck3.log
```

## Démarrage

```bash
python run.py
```

## Structure du projet

```
Keck3/
├── run.py                 # Point d'entrée principal
├── config.py              # Configuration centralisée
├── requirements.txt       # Dépendances Python
├── README.md
│
├── core/
│   ├── __init__.py
│   ├── serial_reader.py   # Lecture du port série
│   ├── label_printer.py   # Gestion impression d'étiquettes
│   └── logger.py          # Logging centralisé
│
├── api/
│   ├── __init__.py
│   ├── client.py          # Client API Open Prod
│   └── models.py          # Modèles de données
│
├── data/
│   └── (données locales)
└── logs/
    └── (fichiers logs)
```

## Types de contrôles

### Contrôle Électrique
- Test de continuité
- Test de tension HV
- Test de perte d'intensité HV
- Test d'isolation
- Test de tension puissance
- Test d'intensité puissance
- Test d'intensité puissance calculée

### Contrôle Thermique
- Mesures de température par voies (jusqu'à N voies)
- Horodatage précis

## Intégration Open Prod

Les données sont synchronisées directement avec les entités suivantes dans Open Prod :
- Machines
- Contrôles électriques & résultats
- Contrôles thermiques & résultats
- Opérateurs
- Codes de statut
