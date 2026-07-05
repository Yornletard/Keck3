# Guide de Migration : Keck1 → Keck3

## Résumé des changements

| Aspect | Keck1 | Keck3 |
|--------|-------|-------|
| **Architecture** | Client-serveur HTTP | Monolithe embarqué |
| **Backend** | Symfony 3.4 (PHP) | Python pur |
| **Base de données** | Oracle | Open Prod (intégration native) |
| **Déploiement** | 2 composants (serveur + client) | 1 seul composant |
| **Communication** | HTTP synchrone | HTTP + gestion d'erreurs |

## Étapes de migration

### Phase 1 : Préparation
- [ ] Configurer le compte Open Prod avec les droits API appropriés
- [ ] Obtenir la clé API Open Prod (`OPEN_PROD_API_KEY`)
- [ ] Archiver l'ancienne base Oracle (backup)
- [ ] Documenter l'URL de base Open Prod

### Phase 2 : Déploiement Keck3
- [ ] Cloner/télécharger Keck3 sur le poste du banc
- [ ] Créer le fichier `.env` avec les paramètres Open Prod
- [ ] Installer Python 3.8+ (si absent)
- [ ] Tester la connexion port série avec `python -c "from core.serial_reader import SerialReader; SerialReader.list_available_ports()"`
- [ ] Lancer `start_keck3.cmd` ou `start_keck3.sh` en test
- [ ] Vérifier les logs dans `logs/keck3.log`

### Phase 3 : Parallélisation (optionnel)
Pour éviter la coupure de service, on peut faire fonctionner Keck1 et Keck3 en parallèle :
- Keck3 envoie les données à Open Prod
- KeckCapture continue d'envoyer à Keck1/Oracle (sans modification)
- Validation des données dans Open Prod
- Après validation : arrêter Keck1, garder Keck3

### Phase 4 : Basculement
- [ ] Arrêter KeckCapture/Keck1
- [ ] S'assurer que Keck3 fonctionne correctement
- [ ] Surveiller les logs pendant les premiers jours
- [ ] Migrer les données historiques Oracle → Open Prod (script externe)

### Phase 5 : Nettoyage
- [ ] Archiver le code Keck1 et KeckCapture
- [ ] Mettre à jour la documentation interne
- [ ] Formez les opérateurs sur les nouveaux logs (fichier au lieu de web UI)

## Points d'attention

### API Open Prod
**À faire :** Vérifier que les endpoints existent dans Open Prod
```
POST /api/machinedata/electricalcontrol
POST /api/machinedata/heatcontrol
```

Si les endpoints n'existent pas, il faudra :
1. Les créer dans Open Prod
2. Adapter les payloads Keck3 (`api/models.py` et `run.py`)

### Mappage des données
Comparer les champs envoyés par Keck1 vs Keck3 :

**Keck1 → Oracle :**
```
HeatControl:
  - id
  - create_date
  - first_result_date
  - fab_order_number
  - status_code_id
  - operator_id
  - machine_id

HeatControlResult:
  - id
  - date_time
  - temperature
  - way_number
  - heat_control_id
```

**Keck3 → Open Prod :**
```json
{
  "frame": ["ligne1", "ligne2"],
  "datetime": "2025-07-05T14:30:00",
  "results": [
    {"wayNumber": 1, "temperature": 75.5, "datetime": "2025-07-05T14:30:00"},
    {"wayNumber": 2, "temperature": 76.2, "datetime": "2025-07-05T14:30:00"}
  ]
}
```

Vous devrez éventuellement adapter le payload si Open Prod attend un schéma différent.

## Rollback

En cas de problème :
1. Arrêter Keck3
2. Restaurer Keck1 et KeckCapture
3. Investiguer les logs Keck3 dans `logs/keck3.log`
4. Fixer le problème et retenter

## Tests

### Test de connexion port série
```python
from core.serial_reader import SerialReader
sr = SerialReader()
sr.connect()
sr.list_available_ports()
```

### Test de connexion API
```python
from api.client import OpenProdAPIClient
client = OpenProdAPIClient()
# Vérifier que client.session.headers contient le Bearer token
```

### Test d'une trame
```python
from api.models import DataParser
frame = (["ligne1"], ["12.5", "3.2"])
control_type = DataParser.classify_frame(frame)
data = DataParser.parse_heat_control(frame)
```

## Support

Pour les problèmes :
1. Consulter `logs/keck3.log` (logs complets)
2. Vérifier la configuration `.env`
3. Tester les endpoints Open Prod manuellement avec `curl` ou Postman
4. Valider la clé API Open Prod
