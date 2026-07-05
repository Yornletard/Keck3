# Architecture Keck3

## Vue d'ensemble

Keck3 est une application Python embarquée qui remplace le système client-serveur Keck1 + KeckCapture.

### Avant (Keck1/KeckCapture)
```
Banc D1118 → Port Série → KeckCapture (Python) → HTTP POST → Keck1 (Symfony) → Oracle DB
                                                    ↓
                                          (impression étiquettes)
```

### Maintenant (Keck3)
```
Banc D1118 → Port Série → Keck3 (Python) → HTTP POST → Open Prod API → Intégration ERP
                                 ↓
                         (impression étiquettes)
```

## Architecture modulaire

### `core/` - Couche métier
- **logger.py** : Configuration centralisée du logging avec rotation de fichiers
- **serial_reader.py** : Interface pour la lecture du port série
- **label_printer.py** : Gestion de l'impression des étiquettes (Windows via win32print)

### `api/` - Couche API
- **client.py** : Client HTTP pour Open Prod avec retry automatique
- **models.py** : Modèles de données et parsing des trames

### Fichiers racine
- **run.py** : Point d'entrée, orchestration des threads
- **config.py** : Configuration centralisée (variables d'environnement)

## Flux de données

### Contrôle Électrique
1. Banc D1118 envoie trame : `[ligne1] [ligne2_avec_7_valeurs]`
2. SerialReader lit et parse les 2 lignes
3. DataParser.classify_frame() → type = 'electrical' (len(line2) < 13)
4. DataParser.parse_electrical_control() → ElectricalControlData
5. OpenProdAPIClient.post_electrical_control() → transmission API
6. Réponse loggée et traitée

### Contrôle Thermique
1. Banc D1118 envoie trame : `[ligne1] [ligne2_avec_N_valeurs]`
2. SerialReader lit et parse les 2 lignes
3. DataParser.classify_frame() → type = 'heat' (len(line2) >= 13)
4. DataParser.parse_heat_control() → List[HeatControlData]
5. OpenProdAPIClient.post_heat_control() → transmission API
6. Réponse loggée et traitée

### Impression d'Étiquettes (Thread parallèle)
1. LabelPrinter.start() lance un scheduler
2. Scan toutes les 5s les répertoires réseau
3. Détecte `label_barcode.txt` ou `label_serial_number.txt`
4. Imprime via win32print (Windows) ou logging (autres systèmes)
5. Supprime le fichier après impression

## Gestion des erreurs

### Reconnexion port série
- Si la connexion échoue au démarrage : arrêt
- Si la connexion se perd pendant l'exécution : création automatique d'une nouvelle
- Logging détaillé pour faciliter le diagnostic

### Retry API
- Maximum 3 tentatives par défaut
- Délai de 2s entre les tentatives
- Logs en cas d'échec

### Parsing de trames
- Si parsing échoue : ligne loggée comme warning, continue
- Les trames invalides n'arrêtent pas l'app

## Configuration

Toute la configuration vient du fichier `.env` ou des valeurs par défaut dans `config.py`.

Variables clés :
- `OPEN_PROD_BASE_URL` : URL de l'API Open Prod
- `OPEN_PROD_API_KEY` : Clé d'authentification API
- `SERIAL_PORT` : Port série (COM3, /dev/ttyUSB0, etc.)
- `LOG_LEVEL` : Niveau de verbosité (DEBUG, INFO, WARNING, ERROR)

## Logging

- Fichier : `logs/keck3.log` (rotation à 10MB)
- Levels : DEBUG (parsing détaillé), INFO (événements), WARNING (anomalies), ERROR (problèmes)
- Format : `timestamp - module - level - message`

## Points d'extensibilité

1. **Nouveaux types de contrôle** : ajouter dans `DataParser.classify_frame()` + parsing + endpoint API
2. **Nouvelles imprimantes** : ajouter dans `LabelPrinter` avec driver correspondant
3. **Validation custom** : ajouter règles dans les parsers de `DataParser`
4. **Métriques/monitoring** : hooker un client Prometheus/Grafana

## Déploiement

### Windows
```bash
start_keck3.cmd  # Crée venv, installe deps, démarre
```

### macOS/Linux
```bash
./start_keck3.sh  # Crée venv, installe deps, démarre
```

### Docker (optionnel)
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["python", "run.py"]
```

## Améliorations par rapport à Keck1

1. ✅ **Élimination du serveur** : plus de couche web, moins de latence
2. ✅ **Integration directe** : stockage immédiatement dans Open Prod
3. ✅ **Resilience** : retry automatique, reconnexion port série
4. ✅ **Logging complet** : traçabilité de chaque événement
5. ✅ **Scalabilité** : threads indépendants, pas de blocage
6. ✅ **Maintenance** : code Python moderne, type hints, documentation
