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

### 2. Erreur : "Authentification échouée"

**Symptôme:**
```
Authentification échouée - clé API invalide
```

**Solutions:**
- Vérifier que `OPEN_PROD_API_KEY` est définie dans `.env`
- Vérifier que la clé est correcte (pas d'espaces avant/après)
- Vérifier que l'utilisateur Open Prod a les permissions API
- Tester manuellement avec curl:
```bash
curl -H "Authorization: Bearer YOUR_API_KEY" https://open-prod.matferbourgeat.com/api/health
```

---

### 3. Erreur : "Ressource non trouvée (404)"

**Symptôme:**
```
Statut HTTP 404: Not Found
```

**Solutions:**
- Vérifier que les endpoints existent dans Open Prod:
  - `/api/machinedata/electricalcontrol`
  - `/api/machinedata/heatcontrol`
- Vérifier que `OPEN_PROD_BASE_URL` dans `.env` est correct
- Consulter la documentation Open Prod pour les URLs exactes

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
Aucune ligne "Étiquette imprimée" dans les logs
```

**Solutions:**
1. Keck3 dépend de `win32print` (Windows seulement)
2. Vérifier que vous êtes sur Windows:
```python
import sys
print(sys.platform)  # Doit être 'win32'
```
3. Installer win32print:
```bash
pip install pywin32
python -m pip install --upgrade pywin32
```
4. Vérifier les chemins dans `.env`:
   - `LABEL_SHARE_PATH` accessible
   - `LABEL_PRINTER_BARCODE` existe
   - `LABEL_PRINTER_SERIAL` existe
5. Tester l'accès réseau:
```bash
# Windows
net use \\172.18.50.26\labels
dir \\172.18.50.26\labels
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
