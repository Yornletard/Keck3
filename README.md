# Keck3 - Test Control Data Acquisition System

Keck3 est l'application Python de nouvelle génération pour l'acquisition et la transmission des données du banc de contrôle (D1118) directement vers Open Prod (ERP).

## 🚀 Démarrage ultra-rapide

### Windows
```bash
Double-clic sur start_web_ui.cmd
# ✓ Crée l'env automatiquement
# ✓ Installe les dépendances
# ✓ Lance le serveur
# ✓ Ouvre http://localhost:5000
```

### Mac/Linux
```bash
./start_web_ui.sh
# ✓ Crée l'env automatiquement
# ✓ Installe les dépendances  
# ✓ Lance le serveur
# ✓ Ouvre http://localhost:5000
```

**C'est tout.** Puis ouvrez votre navigateur sur `http://localhost:5000`

## 📊 Interface Web

Dashboard moderne et responsive :
- ✓ Statut en temps réel (port série, Open Prod)
- ✓ Statistiques dynamiques (électrique, thermique, erreurs, succès)
- ✓ Historique des 20 derniers contrôles
- ✓ Logs en direct (mise à jour chaque 500ms)
- ✓ Design sombre professionnel
- ✓ Fonctionne sur Windows/Mac/Linux

## Architecture

**Avant (Keck1 + KeckCapture):**
- KeckCapture (Python) → API HTTP → Keck1 (Serveur Symfony) → Base de données Oracle

**Maintenant (Keck3):**
- Keck3 (Python embarqué) → API Open Prod → Stockage intégré dans Open Prod

## Fonctionnalités

- Lecture temps réel depuis le banc de contrôle (port série D1118)
- Transmission des données de contrôle électrique et thermique
- Impression **immédiate** des deux étiquettes (code-barres + n° de série) selon la règle keck1
- Intégration native avec Open Prod
- Tableau de bord web (Flask) optionnel
- Logging complet et traçabilité
- Reconnexion automatique du port série, recalage des trames sur la ligne date
- File locale persistée : aucun contrôle perdu si Open Prod est en panne, aucun doublon au rejeu

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
# Open Prod API (générique : getToken + endpoint)
OPEN_PROD_BASE_URL=https://open-prod.matferbourgeat.com
OPEN_PROD_DB=nom_de_la_base
OPEN_PROD_API_KEY=id_secret_oauth2

# Serial Port ('auto' = adaptateur USB série reconnu, sinon l'unique port présent)
SERIAL_PORT=auto
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
├── web_ui.py              # Tableau de bord Flask (observe run.py)
├── printer_test.py        # Test des imprimantes
├── programs.example.json  # Modèle du référentiel des programmes
├── openprod_mapping.example.json # Modèle du mapping contrôle → modèle Open Prod
│
├── core/
│   ├── serial_reader.py   # Lecture du port série
│   ├── labels.py          # Programmes, gabarits SBPL, règle d'impression
│   ├── outbox.py          # File locale persistée des contrôles à transmettre
│   ├── label_printer.py   # Envoi aux imprimantes (Windows)
│   └── logger.py          # Logging centralisé
│
├── api/
│   ├── client.py          # Client API Open Prod (getToken + endpoint)
│   ├── publisher.py       # Mapping contrôle Keck3 → enregistrement Open Prod
│   └── models.py          # Protocole D1118 : parsing des trames
│
├── labels/                # Gabarits SBPL (repris de keck1)
├── tests/                 # Tests unitaires (trames réelles, étiquettes)
├── data/                  # programs.json, machines.json, outbox/ (non versionnés)
└── logs/
```

## Types de contrôles

Le protocole détaillé (champs, facteurs d'échelle, n° de série `F{OF}-{n}`) est décrit dans `ARCHITECTURE.md`.

### Contrôle Électrique
- Test de continuité
- Test de tension HV
- Test de perte d'intensité HV
- Test d'isolation
- Test de tension puissance
- Test d'intensité puissance
- Test d'intensité puissance calculée

### Contrôle Thermique
- 8 voies, chaque voie = une machine (OF, n° de série, opérateur, température, statut)
- Horodatage du banc

## Intégration Open Prod

L'API Open Prod est générique (Odoo-like) : Keck3 crée des enregistrements dans des **modèles** Open Prod via
`POST /web/api/endpoint` (`method=create`). Le modèle et les champs cibles sont décrits dans
`data/openprod_mapping.json` (modèle : `openprod_mapping.example.json`). ⚠️ Les modèles cibles doivent être
validés avec Objectif-PI avant la mise en prod du 21/09/2026 — voir `ARCHITECTURE.md`.

## Tests

```bash
python test_setup.py              # diagnostic complet + tests unitaires
python -m unittest discover tests # tests seuls
```
