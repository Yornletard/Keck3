# Guide de Dépannage Keck3

## Problèmes courants et solutions

### 1. Erreur : "Port série non trouvé"

**Symptôme:**
```
Erreur de connexion au port série: could not open port COM3: PermissionError
```

**Solutions:**
- Vérifiez que le port dans `.env` est correct (`SERIAL_PORT=COM3`)
- Vérifiez que le banc D1118 est branché et allumé
- Lancez `python test_setup.py` pour voir les ports disponibles
- Fermez toute autre application utilisant le port (Keck1, KeckCapture, etc.)

**Windows:**
- Ouvrir le Gestionnaire de périphériques
- Vérifier le port COM du banc D1118
- Installer le driver FTDI si manquant

**Mac/Linux:**
```bash
ls /dev/tty*
# Chercher /dev/ttyUSB0, /dev/ttyACM0, etc.
# Mettre à jour SERIAL_PORT dans .env
```

---

### 2. Erreur : jeton Open Prod refusé

**Symptôme:**
```
Connexion Open Prod impossible: Invalid database / Invalid id_secret
```

**Solutions:**
- Vérifier `OPEN_PROD_DB` (nom de la base) et `OPEN_PROD_API_KEY` (`id_secret` OAuth2) dans `.env`
- Vérifier que l'utilisateur lié à l'`id_secret` a les droits d'écriture sur les modèles du mapping
- Tester manuellement:
```bash
curl -X POST -H "Content-Type: application/json" -d '{"db":"DB","id_secret":"SECRET"}' \
  https://open-prod.matferbourgeat.com/web/api/getToken
```

---

### 2b. Des contrôles s'accumulent dans `data/outbox/`

**Symptôme:** compteur « En attente d'envoi » qui monte dans l'interface, logs `Open Prod indisponible (...), nouvel essai dans Ns`.

**Cause:** Open Prod injoignable ou en erreur passagère. Les contrôles sont conservés et rejoués automatiquement
(toutes les 5 s, 15 s, 60 s puis 5 min), y compris après un redémarrage de Keck3. Rien à faire, sauf vérifier le
réseau / l'instance Open Prod. Les étiquettes sortent au retour.

**Fichiers dans `data/outbox/failed/`:** contrôles **refusés** par Open Prod (champ `last_error` dans le fichier).
Corriger la cause (mapping, valeur, droits) puis redéposer le fichier dans `data/outbox/` pour le rejouer.

### 3. Erreur : "Mapping Open Prod non configuré" ou "Invalid parameter name"

**Symptôme:**
```
Échec de la transmission du contrôle électrique F123-1: Mapping Open Prod non configuré pour 'electrical'
Échec de la transmission ...: Invalid parameter name ...
```

**Solutions:**
- Copier `openprod_mapping.example.json` vers `data/openprod_mapping.json` et y mettre les modèles/champs validés avec Objectif-PI
- Lister les champs d'un modèle : `method=read_fields` (voir `api/client.py::read_fields`)
- Vérifier que `OPEN_PROD_BASE_URL` dans `.env` est l'URL de l'instance Matfer Industrie

---

### 4. Pas de données reçues du banc

**Symptôme:**
```
En attente des données du banc de contrôle D1118...
(aucune données)
```

**Solutions:**
1. Vérifier que le banc D1118 est bien connecté au port série
2. Tester le port série directement:
```python
import serial
ser = serial.Serial('COM3', 9600)  # Remplacer COM3 par le vrai port
line = ser.readline()
print(line)
```
3. Vérifier les paramètres séries dans `.env`:
   - `SERIAL_PORT` correct
   - `SERIAL_BAUDRATE=9600`
4. Redémarrer le banc D1118
5. Vérifier les câbles de connexion

---

### 5. Étiquettes ne s'impriment pas

**Symptôme:**
```
Aucune ligne "Code-barres imprimé" ou "Numéro de série imprimé" dans les logs
```

**Solutions:**
1. Keck3 dépend de `win32print` (Windows seulement)
2. Vérifier que vous êtes sur Windows:
```python
import sys
print(sys.platform)  # Doit être 'win32'
```
3. Installer/mettre à jour win32print:
```bash
pip install pywin32
python -m pip install --upgrade pywin32
```
4. Vérifier les noms d'imprimantes dans `.env`:
```bash
# Lister les imprimantes disponibles
python -c "from core.label_printer import LabelPrinter; LabelPrinter().list_network_printers()"
```
5. Copier les noms exacts dans `.env`:
```env
LABEL_PRINTER_BARCODE=\\serveur\imprimante1
LABEL_PRINTER_SERIAL=\\serveur\imprimante2
```
6. Vérifier que les imprimantes sont accessibles:
```bash
# Windows
ping \\serveur
# Ou depuis l'Explorateur : \\serveur
```

---

### 6. Application crash au démarrage

**Symptôme:**
```
Traceback (most recent call last):
  ...
Exception: ...
Keck3 arrêté
```

**Solutions:**
1. Lancer `python test_setup.py` pour diagnostiquer
2. Vérifier les permissions du répertoire:
```bash
chmod 755 /Users/yornletard/Sites/Keck3
chmod 755 /Users/yornletard/Sites/Keck3/logs
```
3. Lancer en mode debug:
```bash
LOG_LEVEL=DEBUG python run.py
```
4. Consulter `logs/keck3.log` pour les détails

---

### 7. Performance lente ou lag

**Symptôme:**
```
Les données mettent longtemps à arriver dans Open Prod
```

**Solutions:**
1. Vérifier la latence réseau:
```bash
ping open-prod.matferbourgeat.com
# Doit être < 100ms
```
2. Augmenter le timeout API (config.py):
```python
timeout=10  # Actuellement 10s, essayer 30s
```
3. Vérifier les autres processus:
```bash
# Windows: Task Manager
# Linux/Mac: top, Activity Monitor
```
4. Réduire `LOG_LEVEL` à INFO ou WARNING (moins de I/O disque)

---

### 8. Fichiers log trop volumineux

**Symptôme:**
```
logs/keck3.log > 500MB
```

**Solutions:**
1. Réduire `LOG_LEVEL` à INFO au lieu de DEBUG
2. Les logs rotatent automatiquement à 10MB (5 fichiers max)
3. Nettoyer manuellement si besoin:
```bash
rm logs/keck3.log.1
rm logs/keck3.log.2
```

---

### 9. Erreur : "Impossible de créer l'environnement virtuel"

**Windows:**
```bash
python -m venv venv
# Erreur: Microsoft Visual C++ 14.0 is required
```

**Solutions:**
- Installer les build tools: https://visualstudio.microsoft.com/downloads/
- Ou utiliser Python pré-compilé (moins de dépendances)

**Mac/Linux:**
```bash
python3 -m venv venv
# Erreur: module 'distutils' not found
```

Solutions:
```bash
# Ubuntu/Debian
sudo apt-get install python3-venv

# Mac
brew install python3
```

---

### 10. Connexion réseau instable

**Symptôme:**
```
Erreur de connexion vers https://open-prod.matferbourgeat.com
(puis reconnexion après 2s, normalement fonctionne)
```

**Solutions:**
- Comportement normal : Keck3 retry automatiquement
- Vérifier la stabilité du réseau
- Si problèmes persistants:
  - Vérifier le proxy/firewall
  - Contacter l'admin réseau
  - Peut-être augmenter `MAX_RETRIES` dans `config.py`

---

## Logs et diagnostic

### Où sont les logs?
```
/Users/yornletard/Sites/Keck3/logs/keck3.log
```

### Afficher les logs en temps réel (Unix)
```bash
tail -f logs/keck3.log
```

### Filtrer par niveau
```bash
# Erreurs uniquement
grep ERROR logs/keck3.log

# Warnings et erreurs
grep -E "WARNING|ERROR" logs/keck3.log

# Dernières 50 lignes
tail -50 logs/keck3.log
```

### Format des logs
```
2025-07-05 14:30:00,123 - Keck3.run - INFO - Démarrage de Keck3
2025-07-05 14:30:01,456 - Keck3.core.serial_reader - INFO - Connecté au port COM3
2025-07-05 14:30:02,789 - Keck3.api.client - INFO - Requête POST /api/machinedata/electricalcontrol réussie
```

### Niveau de log recommandé
- **Production:** INFO
- **Débogage:** DEBUG (génère beaucoup de logs)

Changer le niveau dans `.env`:
```
LOG_LEVEL=DEBUG
```

---

## Contacter le support

Si vous ne pouvez pas résoudre le problème:
1. Collecter les logs (`logs/keck3.log`)
2. Lancer `python test_setup.py > test_results.txt`
3. Inclure le fichier `.env` (sans la clé API!)
4. Décrire le problème en détail

Envoyer à: support@matferbourgeat.com
